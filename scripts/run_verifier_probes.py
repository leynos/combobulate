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
import tomllib
from pathlib import Path
import shlex
import shutil

from cyclopts import App
from rust_prover_tools.commands import CommandSpec, run_command

from verifier_probe_support import (
    ROOT,
    FIXTURES,
    OUTPUT,
    capture,
    digest,
    kani_environment,
    native_workspace,
    require_command_statuses,
)

BASE_IMAGE = "quay.io/rockylinux/rockylinux@sha256:827d37bc128288ccf160ee318bb3cb92d591164cb217e92f8bc61e3982ae1834"
Z3_DISTRIBUTION = "z3-solver==4.16.0.0"
Z3_VERSION_BANNER = "Z3 version 4.16.0 - 64 bit"
VERUS_CANDIDATES = ("macro", "attributes", "companion", "single-root")


def verifier_free_containerfile() -> str:
    """Build the verifier-free image recipe, including `mold`'s runtime library.

    For example, the returned recipe starts ``FROM`` the pinned Rocky base and
    installs ``libatomic`` alongside the compiler package set. Clang installs
    no ``libatomic``, yet the pinned `mold` binary links against it, so omitting
    it makes every link inside the container fail before the probe's build.
    """
    return (
        f"FROM {BASE_IMAGE}\n"
        "RUN dnf install -y --setopt=install_weak_deps=False "
        "clang gcc-c++ make libatomic && dnf clean all\n"
    )


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
                "kani",
                "exec",
                "--installation",
                str(installation),
                "--cwd",
                str(directory),
            ],
            environment,
        )
    if route == "direct":
        return (
            [str(installation / "bin/kani-driver"), "kani"],
            kani_environment(installation, environment),
        )
    raise ValueError("route must be helper or direct")


def kani_arguments(subject: dict, route: str) -> list[str]:
    """Return one harness subject's arguments for the selected route."""
    if route == "helper":
        return [f"--extra-arg={argument}" for argument in subject["arguments"]]
    return subject["arguments"]


def kani_observations(
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
        command = [*prefix, *kani_arguments(subject, route)]
        if subject.get("external_timeout"):
            command = ["timeout", "--signal=TERM", "8s", *command]
        observations.append(
            {
                "id": subject["id"],
                "expected_exit": subject["expected_exit"],
                **capture(
                    command, directory, output_dir / f"{subject['id']}.log", environment
                ),
            }
        )
    return observations


def kani_in_place_observation(
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
        **capture(
            [*scratch_prefix, *arguments],
            scratch,
            output_dir / "in_place.log",
            environment,
        ),
    }


def write_kani_provenance(
    directory: Path,
    route: str,
    reference: str,
    observations: list[dict],
    output_dir: Path,
) -> None:
    """Record the tool, route, sources, and observations behind the corpus."""
    sources = [
        directory / name
        for name in (
            "src/lib.rs",
            "src/harnesses.rs",
            "harnesses.json",
            "kani-list.json",
        )
    ]
    sources.extend(
        [
            ROOT / "scripts/run_verifier_probes.py",
            ROOT / "scripts/verifier_probe_support.py",
        ]
    )
    provenance = {
        "tool": f"Kani {(ROOT / 'tools/kani/VERSION').read_text().strip()}",
        "route": route,
        "prover_tools_ref": reference,
        "stream_order": "captured stdout followed by captured stderr",
        "source_digests": {str(path.relative_to(ROOT)): digest(path) for path in sources},
        "observations": observations,
    }
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


def require_captured_output(observations: list[dict]) -> None:
    """Reject empty or missing captured output before recording a verdict."""
    if not observations or any(
        not (
            Path(item["log"]) if Path(item["log"]).is_absolute() else ROOT / item["log"]
        )
        .stat()
        .st_size
        for item in observations
    ):
        raise RuntimeError("missing verifier output cannot qualify a corpus")
    require_command_statuses(observations)


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
    observations = kani_observations(
        definitions, prefix, route, directory, output_dir, environment, only
    )
    if only is None:
        observations.append(
            kani_in_place_observation(
                prefix, route, native_workspace(), output_dir, environment
            )
        )
        write_kani_provenance(directory, route, reference, observations, output_dir)
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
        When no solver is available or its banner is not the calibrated one.
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
        if selected.exit_code == 0:
            solver = selected.stdout.strip() or None
    if solver is None:
        raise RuntimeError("the pinned Z3 executable is unavailable")
    z3_path = Path(solver).resolve()
    identity = run_command(CommandSpec((str(z3_path), "--version")))
    if identity.exit_code != 0 or identity.stdout.strip() != Z3_VERSION_BANNER:
        raise RuntimeError("the solver must report the calibrated Z3 4.16.0 release")
    return z3_path, identity.stdout.strip()


def verus_environment(z3_path: Path) -> dict[str, str]:
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


def verus_command(
    binaries: Path,
    candidate: str,
    directory: Path,
    function: str,
    prover_tools: str,
) -> list[str]:
    """Return the verifier command for one candidate and one function."""
    selection = f"--verify-function={function}"
    # cargo-verus does not fingerprint the function-selection arguments.
    (directory / f"{candidate}.rs").touch()
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
        str(binaries / "cargo-verus"),
        "verus",
        "focus",
        "--manifest-path",
        str(directory / candidate / "Cargo.toml"),
    ]
    if candidate == "attributes":
        command += ["--features", "verus"]
    return command + ["--", "--verify-root", selection]


def write_verus_provenance(
    path: Path,
    version: str,
    z3_path: Path,
    banner: str,
    observations: list[dict],
) -> None:
    """Record the Verus and solver identities behind the observations."""
    path.write_text(
        json.dumps(
            {
                "verus": version,
                "z3": str(z3_path),
                "z3_distribution": Z3_DISTRIBUTION,
                "z3_version": banner,
                "z3_sha256": digest(z3_path),
                "observations": observations,
            },
            indent=2,
        )
        + "\n"
    )


def qualified_candidates(output: Path, observations: list[dict]) -> list[str]:
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
    environment = verus_environment(z3_path)
    output = output_dir or directory / "observations"
    observations = [
        {
            "candidate": candidate,
            "function": function,
            **capture(
                verus_command(binaries, candidate, directory, function, prover_tools),
                directory,
                output / f"{candidate}-{function}.log",
                environment,
            ),
        }
        for candidate in VERUS_CANDIDATES
        for function in ("capability", "mutant")
    ]
    provenance_path = (
        output / "provenance.json" if output_dir else directory / "provenance.json"
    )
    write_verus_provenance(provenance_path, version, z3_path, banner, observations)
    qualified = qualified_candidates(output, observations)
    print("Qualified wiring candidates: " + ", ".join(qualified))
    if not qualified:
        raise RuntimeError(
            "no Verus candidate passed both the exact count and seeded mutant"
        )


@app.command
def verifier_free() -> None:
    """Build fixtures in a verifier-free container without bypassing host admission."""
    environment = dict(os.environ)
    record = FIXTURES / "verus-wiring-probe/verifier-free.json"
    if environment.get("RUSTC_WRAPPER"):
        record.write_text(
            json.dumps(
                {
                    "status": "inconclusive",
                    "reason": "Host-side admission/cache compilers do not preserve the container mount namespace.",
                    "log": "tools/verifier-fixtures/verus-wiring-probe/observations/verifier-free.log",
                },
                indent=2,
            )
            + "\n"
        )
        raise RuntimeError(
            "verifier-free isolation needs a runner without a host-side compiler wrapper; admission must not be removed"
        )
    directory = ROOT / "target/epm1-verifier-free-workspace"
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        FIXTURES / "verus-wiring-probe",
        directory / "probe",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "target", "observations", "provenance.json", "verifier-free.json"
        ),
    )
    for name in (
        ".cargo/config.toml",
        "scripts/native-clang-linker.sh",
        "scripts/build-tools-common.sh",
        "tools/mold/VERSION",
        "rust-toolchain.toml",
    ):
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    containerfile = verifier_free_containerfile()
    (directory / "Containerfile").write_text(containerfile)
    output = FIXTURES / "verus-wiring-probe/observations"
    image = "localhost/combobulate-epm1-verifier-free:20261028"
    if (
        run_command(CommandSpec(("podman", "image", "exists", BASE_IMAGE))).exit_code
        != 0
    ):
        pulled = capture(
            ["podman", "pull", BASE_IMAGE],
            ROOT,
            output / "container-pull.log",
            environment,
        )
        if pulled["exit_code"] != 0:
            raise RuntimeError("the pinned container base could not be fetched")
    built = capture(
        ["podman", "build", "--pull=never", "-t", image, str(directory)],
        ROOT,
        output / "container-build.log",
        environment,
    )
    if built["exit_code"] != 0:
        raise RuntimeError("the verifier-free build environment could not be prepared")
    home = Path.home()
    channel = tomllib.loads((ROOT / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    toolchain = home / f".rustup/toolchains/{channel}-x86_64-unknown-linux-gnu"
    paths = [
        directory,
        home / ".cargo",
        toolchain,
        home / ".local/bin/mold",
        home / ".local/bin/ld.mold",
    ]
    command = [
        "podman",
        "run",
        "--rm",
        "--network=none",
        "--userns=keep-id",
        "--security-opt=label=disable",
    ]
    for path in paths:
        command += [
            "-v",
            f"{path}:{path}" + ("" if path in (directory, home / ".cargo") else ":ro"),
        ]
    command += [
        "-v",
        f"{home}/.cargo/bin/rustup:/usr/local/bin/rustup:ro",
        "--tmpfs",
        f"{home}/.cargo/bin",
        "--workdir",
        str(directory / "probe"),
    ]
    child = {
        "HOME": str(home),
        "CARGO_HOME": str(home / ".cargo"),
        "RUSTUP_HOME": str(home / ".rustup"),
        "RUSTUP_TOOLCHAIN": channel,
        "PATH": f"{toolchain}/bin:/usr/local/bin:/usr/bin:/bin",
    }
    for key, value in child.items():
        command += ["-e", f"{key}={value}"]
    command += [
        image,
        "bash",
        "-c",
        'set -euo pipefail; ! command -v verus; ! command -v cargo-kani; test ! -e "$HOME/.kani"; rustc -vV; cargo build --offline --locked --workspace --all-features',
    ]
    observation = capture(command, ROOT, output / "verifier-free.log", environment)
    if observation["exit_code"] != 0:
        raise RuntimeError("the ordinary build failed in the verifier-free container")
    record.write_text(json.dumps({"status": "pass", **observation}, indent=2) + "\n")


if __name__ == "__main__":
    app()