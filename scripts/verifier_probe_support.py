"""Private observation storage and native-workspace construction for EP-M1.

Only the verifier probe scripts use these helpers. Product code and the
evidence gate must not import this module or use its observations as admitted
proof verdicts.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

from rust_prover_tools.commands import CommandSpec, run_command
from rust_prover_tools.versions import parse_tool_version

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools/verifier-fixtures"
OUTPUT = ROOT / "scripts/tests/fixtures/kani_logs"

# The LLVM SDK bundled with the Kani release pinned in tools/kani/VERSION.
# The version check only compares the release, so the toolchain is named here
# and recorded in the provenance: a pin bump must move both values together,
# and the record then shows which SDK actually compiled the harnesses.
KANI_SDK_TOOLCHAIN = "nightly-2025-11-21"
LINT_TABLE = re.compile(
    r"(?m)^\[(?:workspace\.)?lints\.(?P<name>[A-Za-z0-9_-]+)\]\n"
    r"(?P<body>(?:(?!^\[)[^\n]*\n?)*)"
)


def workspace_lint_tables(manifest: str) -> str:
    """Rename every lint table so a virtual workspace can inherit it.

    Only the lint tables are copied, so a table that follows them cannot make
    the scratch manifest invalid. Both ``[lints.<name>]`` and
    ``[workspace.lints.<name>]`` spellings are accepted, which keeps the probe
    working across the move planned for the three-crate workspace.

    For example, a manifest holding ``[lints.clippy]`` and ``[lints.rust]``
    yields tables named ``[workspace.lints.clippy]`` and
    ``[workspace.lints.rust]``.

    Parameters
    ----------
    manifest
        Text of the root ``Cargo.toml``.

    Returns
    -------
    str
        The concatenated ``[workspace.lints.<name>]`` tables.

    Raises
    ------
    RuntimeError
        When the manifest defines no lint table at all.
    """
    tables = [
        f"[workspace.lints.{match.group('name')}]\n{match.group('body')}"
        for match in LINT_TABLE.finditer(manifest)
    ]
    if not tables:
        raise RuntimeError("the root manifest must define at least one lint table")
    return "".join(tables)


def _digest(path: Path) -> str:
    """Return the SHA-256 digest of the exact observed bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _installation_toolchain(installation: Path) -> str:
    """Return the SDK toolchain the installed Kani release declares.

    The pin is a release, not a toolchain. ``tools/kani/VERSION`` can be bumped
    with a release that bundles a different nightly, and a separately installed
    SDK under the same version directory would otherwise pass unnoticed. The
    installation declares the toolchain it was built from, so reading it
    replaces the module constant with the value this release names. That is
    still a declaration: it identifies the toolchain the release says it
    bundles, and only the driver's own version output shows which binary
    actually ran. ``_kani_environment`` therefore checks both — the declared
    prefix here and the release version from the driver.

    Parameters
    ----------
    installation
        Installed Kani release directory.

    Returns
    -------
    str
        The bundled toolchain name, for example
        ``nightly-2025-11-21-x86_64-unknown-linux-gnu``.

    Raises
    ------
    RuntimeError
        If the installation carries no toolchain record. Reporting the constant
        instead would restore exactly the claim this check exists to avoid.

    Examples
    --------
    A record captured from a real installation names the bundled toolchain::

        _installation_toolchain(Path.home() / '.kani/kani-0.67.0')
        # 'nightly-2025-11-21-x86_64-unknown-linux-gnu'
    """
    recorded = installation / "rust-toolchain-version"
    try:
        toolchain = recorded.read_text().strip()
    except OSError as error:
        raise RuntimeError(
            f"the installed Kani release records no toolchain at {recorded}: {error}"
        ) from error
    if not toolchain:
        raise RuntimeError(f"the installed Kani release records an empty {recorded}")
    return toolchain


def _digest_text(content: str) -> str:
    """Return the SHA-256 digest of text that is not stored as its own file."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def portable_argument(argument: str) -> str:
    """Replace host-specific roots so a recorded command stays reproducible.

    The probe still executes the real argument vector. Only the copy written to
    the committed record is rewritten, so the evidence keeps the invocation
    without publishing an account name or a machine-specific worktree path.

    Parameters
    ----------
    argument
        One element of a recorded argument vector.

    Returns
    -------
    str
        The argument with the repository root and home directory replaced.

    Examples
    --------
    A path under the repository becomes relative to a stable placeholder::

        portable_argument(str(ROOT / 'tools')) == '<repo>/tools'
    """
    return argument.replace(str(ROOT), "<repo>").replace(str(Path.home()), "~")


def _capture(
    argv: list[str], cwd: Path, output: Path, environment: dict[str, str]
) -> dict:
    """Capture real streams, status and digest through the helper's Cuprum boundary."""
    result = run_command(CommandSpec(tuple(argv), cwd=cwd, env=environment))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.stdout + result.stderr)
    print(f"{output}: exit {result.exit_code}", flush=True)
    return {
        "command": [portable_argument(argument) for argument in argv],
        "cwd": str(cwd.relative_to(ROOT)),
        "exit_code": result.exit_code,
        "log": str(output.relative_to(ROOT))
        if output.is_relative_to(ROOT)
        else str(output),
        "sha256": _digest(output),
    }


def _kani_environment(installation: Path, environment: dict[str, str]) -> dict[str, str]:
    """Select the matching LLVM SDK child while retaining admission wrappers.

    The helper rejects ancestor backend keys. This explicit fallback leaves
    ordinary Cargo files intact and does not replace any executable Rust body.

    The selected toolchain is the one the installed release declares, checked
    against the module constant so a pin bump that lands a release bundling a
    different nightly fails here rather than recording a constant the run did
    not use. The declaration is not itself proof of the compiler that ran, so
    the driver is asked for its release version below and the answer is
    compared with the repository pin.
    """
    toolchain = _installation_toolchain(installation)
    if not toolchain.startswith(f"{KANI_SDK_TOOLCHAIN}-"):
        raise RuntimeError(
            f"the installed Kani release bundles {toolchain}, not {KANI_SDK_TOOLCHAIN}"
        )
    child = dict(environment)
    child.update(
        RUSTUP_TOOLCHAIN=toolchain,
        RUSTFLAGS="-D warnings",
        CARGO_ENCODED_RUSTFLAGS="-D\x1fwarnings",
        CARGO_PROFILE_DEV_CODEGEN_BACKEND="llvm",
    )
    child["LD_LIBRARY_PATH"] = os.pathsep.join(
        filter(
            None, [str(installation / "toolchain/lib"), child.get("LD_LIBRARY_PATH")]
        )
    )
    child["PATH"] = os.pathsep.join(
        [str(installation / "toolchain/bin"), str(installation / "bin"), child["PATH"]]
    )
    identity = run_command(
        CommandSpec(
            (str(installation / "bin/kani-driver"), "kani", "--version"), env=child
        )
    )
    expected = (ROOT / "tools/kani/VERSION").read_text().strip()
    if (
        identity.exit_code != 0
        or parse_tool_version(identity.stdout, tool_name="Kani") != expected
    ):
        raise RuntimeError("the selected SDK must match the repository Kani pin")
    return child


def _native_workspace() -> Path:
    """Create the planned kernel/facade scratch shape with the repository's live lints."""
    directory = ROOT / "target/epm1-native-workspace"
    directory.mkdir(parents=True, exist_ok=True)
    lints = workspace_lint_tables((ROOT / "Cargo.toml").read_text())
    (directory / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["kernel", "facade"]\nresolver = "3"\n' + lints
    )
    for name in ("kernel", "facade"):
        package = directory / name
        (package / "src").mkdir(parents=True, exist_ok=True)
        manifest = f'[package]\nname = "probe-{name}"\nversion = "0.1.0"\nedition = "2024"\nlicense = "ISC"\npublish = false\n[lints]\nworkspace = true\n'
        if name == "facade":
            manifest += '[dependencies]\nprobe-kernel = { path = "../kernel", version = "0.1.0" }\n'
        (package / "Cargo.toml").write_text(manifest)
    (
        directory / "kernel/src/lib.rs"
    ).write_text("""//! Scratch kernel matching the approved TargetFacts body.
#![no_std]
/// Facts about the compilation target.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TargetFacts { usize_bits: u32 }
impl TargetFacts {
    /// Construct facts for this compilation target.
    pub const fn current() -> Self { Self { usize_bits: usize::BITS } }
    /// Return the target width.
    pub const fn usize_bits(self) -> u32 { self.usize_bits }
}
""")
    (
        directory / "facade/src/lib.rs"
    ).write_text("""//! Scratch facade consumes the same dependency-free kernel body.
#![no_std]
#[cfg(kani)]
mod verification {
    //! A compiler-compatibility observation with a reachable target witness.
    #[kani::proof]
    fn target_facts() {
        let width = probe_kernel::TargetFacts::current().usize_bits();
        assert!(width == usize::BITS, "the kernel must report this target's width");
        kani::cover!(width == 64, "the supported target has a reachable 64-bit width");
    }
}
""")
    return directory / "facade"


def _require_command_statuses(observations: list[dict]) -> None:
    """Reject transport failures without deriving proof verdicts from exit codes."""
    for item in observations:
        if item["exit_code"] != item["expected_exit"]:
            raise RuntimeError(
                f"Kani command {item['id']} exited {item['exit_code']}; "
                f"expected {item['expected_exit']}. Inspect {item['log']}"
            )
