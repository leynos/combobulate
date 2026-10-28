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
    """Capture the Kani corpus through an explicitly recorded execution route."""
    directory = FIXTURES / "kani-corpus"
    environment = dict(os.environ)
    if route == "helper":
        prefix = [
            *shlex.split(prover_tools),
            "kani",
            "exec",
            "--installation",
            str(installation),
            "--cwd",
            str(directory),
        ]
    elif route == "direct":
        prefix = [str(installation / "bin/kani-driver"), "kani"]
        environment = kani_environment(installation, environment)
    else:
        raise ValueError("route must be helper or direct")
    definitions = json.loads((directory / "harnesses.json").read_text())
    observations = []
    for subject in definitions["runs"]:
        if only is not None and subject["id"] != only:
            continue
        arguments = subject["arguments"]
        if route == "helper":
            arguments = [f"--extra-arg={argument}" for argument in arguments]
        command = [*prefix, *arguments]
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
    if only is None:
        scratch = native_workspace()
        scratch_prefix = list(prefix)
        if route == "helper":
            scratch_prefix[-1] = str(scratch)
        arguments = ["--harness", "verification::target_facts", "--exact", "--verbose"]
        if route == "helper":
            arguments = [f"--extra-arg={argument}" for argument in arguments]
        observations.append(
            {
                "id": "in_place",
                "expected_exit": 0,
                **capture(
                    [*scratch_prefix, *arguments],
                    scratch,
                    output_dir / "in_place.log",
                    environment,
                ),
            }
        )
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
            "tool": "Kani 0.67.0",
            "route": route,
            "prover_tools_ref": "9c4a27a86c678ceac1155404f45d95ee4a14a172",
            "stream_order": "captured stdout followed by captured stderr",
            "source_digests": {
                str(path.relative_to(ROOT)): digest(path) for path in sources
            },
            "observations": observations,
        }
        (output_dir / "provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n"
        )
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


@app.command
def verus(
    *,
    prover_tools: str,
    z3: str = "z3",
    output_dir: Path | None = None,
    verus_installation: Path | None = None,
) -> None:
    """Compare crate wiring with the helper's supported single-root route."""
    directory = FIXTURES / "verus-wiring-probe"
    version = (ROOT / "tools/verus/VERSION").read_text().strip()
    binaries = verus_installation or ROOT / ".verus" / version / "verus"
    solver = shutil.which(z3)
    if solver is None and z3 == "z3":
        selected = run_command(
            CommandSpec(
                (
                    "uv",
                    "tool",
                    "run",
                    "--from",
                    "z3-solver==4.16.0.0",
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
    if (
        identity.exit_code != 0
        or identity.stdout.strip() != "Z3 version 4.16.0 - 64 bit"
    ):
        raise RuntimeError("the solver must report the calibrated Z3 4.16.0 release")
    environment = dict(os.environ)
    environment.pop("RUSTUP_TOOLCHAIN", None)
    environment["VERUS_Z3_PATH"] = str(z3_path)
    environment.update(
        RUSTFLAGS="-D warnings",
        CARGO_ENCODED_RUSTFLAGS="-D\x1fwarnings",
        CARGO_PROFILE_DEV_CODEGEN_BACKEND="llvm",
    )
    observations = []
    output = output_dir or directory / "observations"
    for candidate in ("macro", "attributes", "companion", "single-root"):
        for function in ("capability", "mutant"):
            selection = f"--verify-function={function}"
            # cargo-verus does not fingerprint the function-selection arguments.
            (directory / f"{candidate}.rs").touch()
            if candidate == "single-root":
                command = [
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
            else:
                command = [
                    str(binaries / "cargo-verus"),
                    "verus",
                    "focus",
                    "--manifest-path",
                    str(directory / candidate / "Cargo.toml"),
                ]
                if candidate == "attributes":
                    command += ["--features", "verus"]
                command += ["--", "--verify-root", selection]
            observations.append(
                {
                    "candidate": candidate,
                    "function": function,
                    **capture(
                        command,
                        directory,
                        output / f"{candidate}-{function}.log",
                        environment,
                    ),
                }
            )
    provenance_path = (
        output / "provenance.json" if output_dir else directory / "provenance.json"
    )
    provenance_path.write_text(
        json.dumps(
            {
                "verus": version,
                "z3": str(z3_path),
                "z3_distribution": "z3-solver==4.16.0.0",
                "z3_version": identity.stdout.strip(),
                "z3_sha256": digest(z3_path),
                "observations": observations,
            },
            indent=2,
        )
        + "\n"
    )
    qualified = []
    for candidate in ("macro", "attributes", "companion", "single-root"):
        positive = (output / f"{candidate}-capability.log").read_text()
        negative = (output / f"{candidate}-mutant.log").read_text()
        statuses = [
            item["exit_code"] for item in observations if item["candidate"] == candidate
        ]
        if (
            statuses[0] == 0
            and statuses[1] != 0
            and "1 verified, 0 errors" in positive
            and "postcondition not satisfied" in negative
            and "0 verified, 1 errors" in negative
        ):
            qualified.append(candidate)
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
    (directory / "Containerfile").write_text(
        f"FROM {BASE_IMAGE}\nRUN dnf install -y --setopt=install_weak_deps=False clang gcc-c++ make && dnf clean all\n"
    )
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
    toolchain = home / ".rustup/toolchains/nightly-2026-08-27-x86_64-unknown-linux-gnu"
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
        "RUSTUP_TOOLCHAIN": "nightly-2026-08-27",
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
