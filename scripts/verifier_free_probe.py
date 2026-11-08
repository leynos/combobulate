"""Build the verifier-free container fixture without bypassing host admission.

The workflow stages a scratch workspace, prepares the pinned base image, runs
the ordinary build inside a network-free container, and records the captured
result. Only the verifier-free probe command uses this module; the Kani and
Verus routes do not import it.
"""

from __future__ import annotations

import json
import os
import shutil
import tomllib
from pathlib import Path

from rust_prover_tools.commands import CommandSpec, run_command

from structural_digest import structural_digest
from verifier_probe_support import FIXTURES, ROOT, _capture

BASE_IMAGE = "quay.io/rockylinux/rockylinux@sha256:827d37bc128288ccf160ee318bb3cb92d591164cb217e92f8bc61e3982ae1834"

# Repository files copied beside the fixture so the container build uses the
# same toolchain, linker, and mold pins as the host.
STAGING_FILES = (
    ".cargo/config.toml",
    "scripts/native-clang-linker.sh",
    "scripts/build-tools-common.sh",
    "tools/mold/VERSION",
    "rust-toolchain.toml",
)
# Evidence records and build output are not build inputs. The hosted record is
# excluded so it can bind the staged set without hashing itself.
STAGING_IGNORES = (
    "target",
    "observations",
    "provenance.json",
    "verifier-free.json",
    "verifier-free-hosted.json",
)
# `set -e` does not abort on a failed `! command -v ...`, so each verifier check
# is an explicit branch whose failure status the shell acts on.
BUILD_SCRIPT = (
    "set -euo pipefail; "
    "if command -v verus >/dev/null 2>&1; then "
    'echo "verus must be absent" >&2; exit 1; fi; '
    "if command -v cargo-kani >/dev/null 2>&1; then "
    'echo "cargo-kani must be absent" >&2; exit 1; fi; '
    'test ! -e "$HOME/.kani"; rustc -vV; '
    "cargo build --offline --locked --workspace --all-features"
)


def _verifier_free_containerfile() -> str:
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


def _write_inconclusive_record(record: Path) -> None:
    """Record why a host compiler wrapper prevents container isolation.

    Parameters
    ----------
    record
        Path of the verifier-free JSON observation.

    Examples
    --------
    The record names the omitted log so the hosted job supplies the real one::

        _write_inconclusive_record(FIXTURES / "verus-wiring-probe/verifier-free.json")
    """
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


def staged_sources() -> list[Path]:
    """Return every repository file the verifier-free build stages.

    The list is the fixture tree minus evidence records and build output, plus
    the toolchain and linker files copied beside it. Recording a digest for
    each entry binds the hosted observation to the exact inputs it built.

    Examples
    --------
    The fixture sources and the root toolchain file are both included::

        staged_sources()
        # [PosixPath('.../verus-wiring-probe/Cargo.toml'), ..., PosixPath('.../rust-toolchain.toml')]
    """
    fixture = FIXTURES / "verus-wiring-probe"
    copied = [
        path
        for path in sorted(fixture.rglob("*"))
        if path.is_file()
        and not any(part in STAGING_IGNORES for part in path.relative_to(fixture).parts)
    ]
    return copied + [ROOT / name for name in STAGING_FILES]


def _stage_verifier_free_workspace(directory: Path) -> None:
    """Copy the probe fixture and pinned toolchain files into ``directory``.

    Parameters
    ----------
    directory
        Scratch workspace the container mounts and builds.

    Examples
    --------
    Staging is idempotent, so a rerun refreshes the copied files::

        _stage_verifier_free_workspace(ROOT / 'target/epm1-verifier-free-workspace')
    """
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        FIXTURES / "verus-wiring-probe",
        directory / "probe",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(*STAGING_IGNORES),
    )
    for name in STAGING_FILES:
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (directory / "Containerfile").write_text(_verifier_free_containerfile())


def ensure_base_image(output: Path, environment: dict[str, str]) -> None:
    """Pull the pinned base image when the local store lacks it.

    Parameters
    ----------
    output
        Observation directory receiving the pull log.
    environment
        Caller environment passed to the capture helper.

    Raises
    ------
    RuntimeError
        If the image is absent and the pinned pull fails.

    Examples
    --------
    The check reuses an image the runner already cached::

        ensure_base_image(output, dict(os.environ))
    """
    exists = run_command(CommandSpec(("podman", "image", "exists", BASE_IMAGE)))
    if exists.exit_code == 0:
        return
    pulled = _capture(
        ["podman", "pull", BASE_IMAGE],
        ROOT,
        output / "container-pull.log",
        environment,
    )
    if pulled["exit_code"] != 0:
        raise RuntimeError("the pinned container base could not be fetched")


def container_run_command(
    directory: Path, image: str, home: Path, channel: str
) -> list[str]:
    """Return the ``podman run`` vector for the verifier-free build.

    Parameters
    ----------
    directory
        Staged workspace, mounted read-write for the build.
    image
        Local image tag built from the staged container file.
    home
        Host home directory holding the Cargo and rustup installations.
    channel
        Pinned Rust toolchain channel from ``rust-toolchain.toml``.

    Returns
    -------
    list[str]
        The complete ``podman run`` argument vector, including the build
        script and the child environment.

    Examples
    --------
    Every mounted tool is read-only except the workspace and Cargo cache::

        command = container_run_command(directory, image, home, channel)
    """
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
    return command + [image, "bash", "-c", BUILD_SCRIPT]


def run_verifier_free() -> None:
    """Build the fixture in a verifier-free container and record the result.

    Raises
    ------
    RuntimeError
        If host admission rejects the environment, the base image cannot be
        fetched or built, or the ordinary build fails in the container.

    Examples
    --------
    The hosted observation job runs this after a fresh runner boot::

        run_verifier_free()
    """
    environment = dict(os.environ)
    record = FIXTURES / "verus-wiring-probe/verifier-free.json"
    if environment.get("RUSTC_WRAPPER"):
        _write_inconclusive_record(record)
        raise RuntimeError(
            "verifier-free isolation needs a runner without a host-side compiler "
            "wrapper; admission must not be removed"
        )
    directory = ROOT / "target/epm1-verifier-free-workspace"
    _stage_verifier_free_workspace(directory)
    source_digests = {
        str(path.relative_to(ROOT)): structural_digest(path)
        for path in staged_sources()
    }
    output = FIXTURES / "verus-wiring-probe/observations"
    image = "localhost/combobulate-epm1-verifier-free:20261028"
    ensure_base_image(output, environment)
    built = _capture(
        ["podman", "build", "--pull=never", "-t", image, str(directory)],
        ROOT,
        output / "container-build.log",
        environment,
    )
    if built["exit_code"] != 0:
        raise RuntimeError("the verifier-free build environment could not be prepared")
    home = Path.home()
    channel = tomllib.loads((ROOT / "rust-toolchain.toml").read_text())["toolchain"][
        "channel"
    ]
    command = container_run_command(directory, image, home, channel)
    observation = _capture(command, ROOT, output / "verifier-free.log", environment)
    if observation["exit_code"] != 0:
        raise RuntimeError("the ordinary build failed in the verifier-free container")
    record.write_text(
        json.dumps(
            {"status": "pass", "source_digests": source_digests, **observation},
            indent=2,
        )
        + "\n"
    )
