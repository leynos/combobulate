"""Private observation storage and native-workspace construction for EP-M1.

Only run_verifier_probes uses these helpers. Product code and the evidence gate
must not import this module or use its observations as admitted proof verdicts.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from rust_prover_tools.commands import CommandSpec, run_command
from rust_prover_tools.versions import parse_tool_version

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools/verifier-fixtures"
OUTPUT = ROOT / "scripts/tests/fixtures/kani_logs"


def digest(path: Path) -> str:
    """Return the SHA-256 digest of the exact observed bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(
    argv: list[str], cwd: Path, output: Path, environment: dict[str, str]
) -> dict:
    """Capture real streams, status and digest through the helper's Cuprum boundary."""
    result = run_command(CommandSpec(tuple(argv), cwd=cwd, env=environment))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.stdout + result.stderr)
    print(f"{output}: exit {result.exit_code}", flush=True)
    return {
        "command": argv,
        "cwd": str(cwd.relative_to(ROOT)),
        "exit_code": result.exit_code,
        "log": str(output.relative_to(ROOT))
        if output.is_relative_to(ROOT)
        else str(output),
        "sha256": digest(output),
    }


def kani_environment(installation: Path, environment: dict[str, str]) -> dict[str, str]:
    """Select the matching LLVM SDK child while retaining admission wrappers.

    The helper rejects ancestor backend keys. This explicit fallback leaves
    ordinary Cargo files intact and does not replace any executable Rust body.
    """
    child = dict(environment)
    child.update(
        RUSTUP_TOOLCHAIN="nightly-2025-11-21",
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


def native_workspace() -> Path:
    """Create the planned kernel/facade scratch shape with the repository's live lints."""
    directory = ROOT / "target/epm1-native-workspace"
    directory.mkdir(parents=True, exist_ok=True)
    lints = (
        "[lints.clippy]"
        + (ROOT / "Cargo.toml").read_text().split("[lints.clippy]", 1)[1]
    )
    (directory / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["kernel", "facade"]\nresolver = "3"\n'
        + lints.replace("[lints.", "[workspace.lints.")
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


def require_command_statuses(observations: list[dict]) -> None:
    """Reject transport failures without deriving proof verdicts from exit codes."""
    for item in observations:
        if item["exit_code"] != item["expected_exit"]:
            raise RuntimeError(
                f"Kani command {item['id']} exited {item['exit_code']}; "
                f"expected {item['expected_exit']}. Inspect {item['log']}"
            )
