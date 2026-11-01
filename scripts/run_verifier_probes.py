#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["rust-prover-tools @ git+https://github.com/leynos/rust-prover-tools.git@9c4a27a86c678ceac1155404f45d95ee4a14a172"]
# ///
"""Capture tool capabilities without presenting them as product proofs.

For example, ``make kani-log-corpus`` captures labelled Kani subjects and
writes digest-bound provenance for later parser qualification.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import shlex
import shutil

from cyclopts import App
from rust_prover_tools.commands import CommandSpec, run_command

from probe_provenance import (
    Z3_DISTRIBUTION, require_captured_output, _write_kani_provenance,
    _write_verus_provenance,
)
# The container recipe contract test reads it from this module.
from verifier_free_probe import run_verifier_free, _verifier_free_containerfile
from verifier_probe_support import (
    ROOT, FIXTURES, OUTPUT, _capture, _kani_environment, _native_workspace,
)

Z3_VERSION_BANNER = "Z3 version 4.16.0 - 64 bit"
VERUS_CANDIDATES = ("macro", "attributes", "companion", "single-root")


def kani_prefix(
    route: str,
    prover_tools: str,
    installation: Path,
    directory: Path,
    environment: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    """Return the command prefix and child environment for a Kani route.

    Parameters
    ----------
    route : str
        Either ``helper`` for the pinned helper or ``direct`` for the SDK.
    prover_tools : str
        Command prefix that invokes the pinned prover helper.
    installation : Path
        Installed Kani release selected for the run.
    directory : Path
        Fixture directory passed to the helper as its working directory.
    environment : dict[str, str]
        Caller environment, copied and adjusted for the direct route.

    Returns
    -------
    tuple[list[str], dict[str, str]]
        The prefix and the environment the captured commands must receive.

    Raises
    ------
    ValueError
        When the route is neither ``helper`` nor ``direct``.
    """
    if route == "helper":
        return (
            [
                *shlex.split(prover_tools),
                "kani", "exec",
                "--installation", str(installation),
                "--cwd", str(directory),
            ],
            environment,
        )
    if route == "direct":
        return (
            [str(installation / "bin/kani-driver"), "kani"],
            _kani_environment(installation, environment),
        )
    raise ValueError("route must be helper or direct")


def _kani_arguments(subject: dict, route: str) -> list[str]:
    """Return one harness subject's arguments for the selected route."""
    if route == "helper":
        return [f"--extra-arg={argument}" for argument in subject["arguments"]]
    return subject["arguments"]


def _kani_observations(
    definitions: dict,
    prefix: list[str],
    route: str,
    directory: Path,
    output_dir: Path,
    environment: dict[str, str],
    only: str | None,
) -> list[dict]:
    """Capture every selected harness subject and return its observations."""
    observations = []
    for subject in definitions["runs"]:
        if only is not None and subject["id"] != only:
            continue
        command = [*prefix, *_kani_arguments(subject, route)]
        if subject.get("external_timeout"):
            command = ["timeout", "--signal=TERM", "8s", *command]
        observations.append(
            {
                "id": subject["id"],
                "expected_exit": subject["expected_exit"],
                **_capture(
                    command, directory, output_dir / f"{subject['id']}.log", environment
                ),
            }
        )
    return observations


def _kani_in_place_observation(
    prefix: list[str],
    route: str,
    scratch: Path,
    output_dir: Path,
    environment: dict[str, str],
) -> dict:
    """Run one completed harness against the scratch kernel/facade workspace."""
    scratch_prefix = list(prefix)
    if route == "helper":
        scratch_prefix[-1] = str(scratch)
    arguments = ["--harness", "verification::target_facts", "--exact", "--verbose"]
    if route == "helper":
        arguments = [f"--extra-arg={argument}" for argument in arguments]
    return {
        "id": "in_place",
        "expected_exit": 0,
        **_capture(
            [*scratch_prefix, *arguments],
            scratch,
            output_dir / "in_place.log",
            environment,
        ),
    }


app = App()


@app.command
def kani(
    *,
    prover_tools: str,
    installation: Path,
    route: str = "helper",
    only: str | None = None,
    output_dir: Path = OUTPUT,
) -> None:
    """Capture the Kani corpus through an explicitly recorded execution route.

    Parameters
    ----------
    prover_tools : str
        Command prefix that invokes the pinned prover helper.
    installation : Path
        Installed Kani release whose SDK and driver must be used.
    route : str
        ``helper`` captures through the helper, ``direct`` through the SDK.
    only : str | None
        Capture a single labelled subject and skip provenance.
    output_dir : Path
        Directory receiving the logs and provenance file.
    """
    reference = (ROOT / "tools/rust-prover-tools/REF").read_text().split("ref: ", 1)[1].splitlines()[0]
    directory = FIXTURES / "kani-corpus"
    environment = dict(os.environ)
    prefix, environment = kani_prefix(
        route, prover_tools, installation, directory, environment
    )
    definitions = json.loads((directory / "harnesses.json").read_text())
    observations = _kani_observations(
        definitions, prefix, route, directory, output_dir, environment, only
    )
    if only is None:
        observations.append(
            _kani_in_place_observation(
                prefix, route, _native_workspace(), output_dir, environment
            )
        )
        _write_kani_provenance(directory, route, reference, observations, output_dir)
    require_captured_output(observations)


def resolve_z3(selection: str) -> tuple[Path, str]:
    """Resolve the calibrated solver and return its path and version banner.

    Parameters
    ----------
    selection : str
        A solver name or path. The default name first resolves the pinned
        ``z3-solver`` distribution, while any explicit selection is checked.

    Returns
    -------
    tuple[Path, str]
        The resolved executable and the exact version banner it reported.

    Raises
    ------
    RuntimeError
        When the default selection cannot resolve the pinned distribution, no
        solver is available, or its banner is not the calibrated one.
    """
    solver = shutil.which(selection)
    if selection == "z3":
        selected = run_command(
            CommandSpec(
                (
                    "uv",
                    "tool",
                    "run",
                    "--from",
                    Z3_DISTRIBUTION,
                    "python",
                    "-c",
                    "import shutil; print(shutil.which('z3') or '')",
                )
            )
        )
        if selected.exit_code != 0:
            # The record names the calibrated distribution, so a failed
            # resolver must not fall back to whichever z3 sits on `PATH`:
            # that binary would be recorded as the pin's own.
            raise RuntimeError(
                "the pinned z3-solver distribution could not be resolved: "
                f"{selected.stderr.strip() or 'uv exited with an error'}"
            )
        solver = selected.stdout.strip() or None
    if solver is None:
        raise RuntimeError("the pinned Z3 executable is unavailable")
    z3_path = Path(solver).resolve()
    identity = run_command(CommandSpec((str(z3_path), "--version")))
    if identity.exit_code != 0 or identity.stdout.strip() != Z3_VERSION_BANNER:
        raise RuntimeError("the solver must report the calibrated Z3 4.16.0 release")
    return z3_path, identity.stdout.strip()


def _verus_environment(z3_path: Path) -> dict[str, str]:
    """Return the child environment that binds the calibrated solver."""
    environment = dict(os.environ)
    environment.pop("RUSTUP_TOOLCHAIN", None)
    environment["VERUS_Z3_PATH"] = str(z3_path)
    environment.update(
        RUSTFLAGS="-D warnings",
        CARGO_ENCODED_RUSTFLAGS="-D\x1fwarnings",
        CARGO_PROFILE_DEV_CODEGEN_BACKEND="llvm",
    )
    return environment


def _refresh_candidate_fingerprint(directory: Path, candidate: str) -> None:
    """Touch the proof file before a build so cargo-verus reruns the selection.

    cargo-verus does not fingerprint the function-selection arguments, so a
    warm target directory would otherwise reuse another function's verdict.
    """
    (directory / f"{candidate}.rs").touch()


def _verus_command(
    binaries: Path,
    candidate: str,
    directory: Path,
    function: str,
    prover_tools: str,
) -> list[str]:
    """Return the verifier command for one candidate and one function."""
    selection = f"--verify-function={function}"
    if candidate == "single-root":
        return [
            *shlex.split(prover_tools),
            "verus",
            "run",
            "--repo-root",
            str(ROOT),
            "--proof-file",
            str(directory / "single-root.rs"),
            "--extra-arg=--crate-type=lib",
            "--extra-arg=--verify-root",
            f"--extra-arg={selection}",
        ]
    command = [
        str(binaries / "cargo-verus"), "verus", "focus",
        "--manifest-path", str(directory / candidate / "Cargo.toml"),
    ]
    if candidate == "attributes":
        command += ["--features", "verus"]
    return command + ["--", "--verify-root", selection]


def _qualified_candidates(output: Path, observations: list[dict]) -> list[str]:
    """Return candidates whose positive and mutant logs show exact counts."""
    qualified = []
    for candidate in VERUS_CANDIDATES:
        positive = (output / f"{candidate}-capability.log").read_text()
        negative = (output / f"{candidate}-mutant.log").read_text()
        statuses = [
            item["exit_code"] for item in observations if item["candidate"] == candidate
        ]
        if (
            statuses[0] == 0
            and statuses[1] != 0
            and re.search(r"(?m)^verification results:: 1 verified, 0 errors(?: \(|$)", positive)
            and "postcondition not satisfied" in negative
            and re.search(r"(?m)^verification results:: 0 verified, 1 errors(?: \(|$)", negative)
        ):
            qualified.append(candidate)
    return qualified


@app.command
def verus(
    *,
    prover_tools: str,
    z3: str = "z3",
    output_dir: Path | None = None,
    verus_installation: Path | None = None,
) -> None:
    """Compare crate wiring with the helper's supported single-root route.

    Parameters
    ----------
    prover_tools : str
        Command prefix that invokes the pinned prover helper.
    z3 : str
        Solver selection; the default resolves the pinned distribution first.
    output_dir : Path | None
        Directory receiving the logs; defaults to the fixture observations.
    verus_installation : Path | None
        Installed Verus release; defaults to the pinned installation.
    """
    directory = FIXTURES / "verus-wiring-probe"
    version = (ROOT / "tools/verus/VERSION").read_text().strip()
    binaries = verus_installation or ROOT / ".verus" / version / "verus"
    z3_path, banner = resolve_z3(z3)
    environment = _verus_environment(z3_path)
    output = output_dir or directory / "observations"
    observations = []
    for candidate in VERUS_CANDIDATES:
        for function in ("capability", "mutant"):
            _refresh_candidate_fingerprint(directory, candidate)
            observations.append(
                {
                    "candidate": candidate,
                    "function": function,
                    **_capture(
                        _verus_command(
                            binaries, candidate, directory, function, prover_tools
                        ),
                        directory,
                        output / f"{candidate}-{function}.log",
                        environment,
                    ),
                }
            )
    provenance_path = (
        output / "provenance.json" if output_dir else directory / "provenance.json"
    )
    _write_verus_provenance(provenance_path, version, z3_path, banner, observations)
    qualified = _qualified_candidates(output, observations)
    print("Qualified wiring candidates: " + ", ".join(qualified))
    if not qualified:
        raise RuntimeError(
            "no Verus candidate passed both the exact count and seeded mutant"
        )


@app.command
def verifier_free() -> None:
    """Build fixtures in a verifier-free container without bypassing host admission.

    Returns
    -------
    None
        Writes the verifier-free observation record.

    Raises
    ------
    RuntimeError
        If host admission rejects the environment or the verifier-free build
        fails.

    Examples
    --------
    The hosted observation job runs the command after a fresh runner boot::

        verifier_free()
    """
    run_verifier_free()


if __name__ == "__main__":
    app()
