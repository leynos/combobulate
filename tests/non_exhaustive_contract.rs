//! The facade's `#[non_exhaustive]` contracts, as a downstream caller meets them.
//!
//! `Dtype`, `Stage`, `NativeExecutor` and `Failure`'s variants are all
//! `#[non_exhaustive]`, and every one of them was added by this release. The
//! attribute is a promise in both directions: a caller may still use the type
//! (the compile-*pass* half), and a caller may not depend on the set of variants
//! or fields being final (the compile-*fail* half). An ordinary test can only
//! observe the first, because the second is a build that must not succeed.
//!
//! So both halves are builds of `tools/fixtures/non-exhaustive-contract`, a
//! downstream crate outside the workspace that takes the facade by path with
//! default features off. `src/bin/covered.rs` must compile; each
//! `src/bin/exhaustive_*.rs` must fail with the diagnostic Rust emits when a
//! non-exhaustive item is matched exhaustively (`E0004`) or constructed
//! (`E0639`).
//!
//! Every attribute gets its own statement, because a contract that only some
//! of them are checked for would let a dropped attribute pass: `Dtype` and
//! `Stage` are matched, `Failure` is matched as an enum and each of its two
//! variants is constructed, and `NativeExecutor` is constructed.
//!
//! The fixture is a path-dependency build rather than `trybuild`, following
//! `tests/polars_surface_ui.rs`: `trybuild` copies the host package's whole
//! dev-dependency graph into a generated crate, which is the incident
//! `tests/cardinality_probe_ui.rs` exists to prevent. These are ordinary
//! consumer builds, so each failure is the same evidence at a fraction of the
//! cost.
//!
//! One binary per failing contract, deliberately: rustc stops after the first
//! error in a crate, so three statements in one file would report `E0639` and
//! never reach either `E0004`.

use std::{
    path::{Path, PathBuf},
    process::{Command, Output},
};

/// The fixture's directory, relative to the repository root.
const FIXTURE: &str = "tools/fixtures/non-exhaustive-contract";

/// The `cfg` the fixture's manifest declares and its failing bodies require.
///
/// An ordinary build never sets it, so the fixture's own `cargo build` succeeds
/// and only these contract builds compile the statements that must fail.
const GATE_CFG: &str = "nonexhaustive_contract";

/// The binary that must build, proving the types are still usable.
const COVERED_BINARY: &str = "covered";

/// Each failing contract, with the diagnostic code Rust reports for it.
///
/// The code is part of the expectation, not a convenience: a build that failed
/// because the fixture had lost the facade (`E0432`) or because a name moved
/// (`E0425`) would mean something else entirely, and accepting any failure
/// would let a dropped attribute pass as long as the fixture was broken too.
const FAILING: [(&str, &str); 6] = [
    ("exhaustive_dtype", "E0004"),
    ("exhaustive_stage", "E0004"),
    ("exhaustive_failure_match", "E0004"),
    ("exhaustive_failure", "E0639"),
    ("exhaustive_shape_agreement", "E0639"),
    ("exhaustive_executor", "E0639"),
];

/// The fixture's manifest, resolved from the repository root Cargo sets.
fn fixture_manifest() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join(FIXTURE)
        .join("Cargo.toml")
}

/// A Cargo child for the fixture, with the caller's build selectors removed.
///
/// `CARGO_TARGET_DIR` is redirected into nextest's per-test temporary directory
/// so the fixture never writes into the root workspace's `target/`, and the
/// caller's `RUSTFLAGS` is removed so the fixture's result depends on its own
/// manifest rather than on how the suite was invoked. `--offline` keeps the
/// check hermetic — the fixture's only dependency is a path — and `--locked`
/// makes a stale lockfile fail here rather than silently re-resolve.
///
/// No deadline is applied here: nextest gives this test its own process and
/// `.config/nextest.toml` owns the tier, which is the repository's standing
/// policy for tests that start `Command` children.
fn fixture_cargo(arguments: &[&str], selectors: &[(&str, &str)]) -> Command {
    let mut command = Command::new(env!("CARGO"));
    command.args(arguments);
    command.args(["--locked", "--offline", "--manifest-path"]);
    command.arg(fixture_manifest());
    command.current_dir(Path::new(env!("CARGO_MANIFEST_DIR")));
    command.env(
        "CARGO_TARGET_DIR",
        Path::new(env!("CARGO_TARGET_TMPDIR")).join("non-exhaustive-contract"),
    );
    for name in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET"] {
        command.env_remove(name);
    }
    for (name, value) in selectors {
        command.env(name, value);
    }
    command
}

/// Runs a fixture build, returning its output.
fn build(arguments: &[&str], selectors: &[(&str, &str)]) -> Output {
    fixture_cargo(arguments, selectors)
        .output()
        .expect("the fixture's Cargo child must start")
}

/// The rendered stdout and stderr of one build.
fn diagnostics(output: &Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    )
}

/// Every diagnostic code the compiler reported.
fn error_codes(diagnostics: &str) -> Vec<String> {
    diagnostics
        .split("error[")
        .skip(1)
        .filter_map(|rest| rest.split(']').next())
        .filter(|code| code.starts_with('E'))
        .map(str::to_owned)
        .collect()
}

/// The covered binary builds: every non-exhaustive type is still usable.
///
/// This is the half that would regress silently. Tightening an attribute until
/// a downstream caller could no longer match, destructure or construct what the
/// documentation promises would break real programs while every in-workspace
/// test kept passing, because a test inside the crate is not outside it.
#[test]
fn a_downstream_caller_can_still_use_every_non_exhaustive_type() {
    let output = build(&["build", "--bin", COVERED_BINARY], &[]);

    assert!(
        output.status.success(),
        "a downstream caller must still be able to match, destructure and read the non-exhaustive \
         types, but the covered binary failed to build.\ndiagnostics:\n{}",
        diagnostics(&output)
    );
}

/// Each forbidden use fails with the diagnostic that names the attribute.
#[test]
fn each_exhaustive_use_is_rejected_by_the_compiler() {
    for (binary, expected) in FAILING {
        let output = build(
            &["build", "--bin", binary],
            &[("RUSTFLAGS", &format!("--cfg {GATE_CFG}"))],
        );
        let diagnostics = diagnostics(&output);
        assert!(
            !output.status.success(),
            "the fixture's `{binary}` matches or constructs a non-exhaustive item, so it must not \
             build; a successful build means that item lost its \
             attribute.\ndiagnostics:\n{diagnostics}"
        );
        assert!(
            error_codes(&diagnostics)
                .iter()
                .any(|code| code == expected),
            "a dropped `#[non_exhaustive]` on the item `{binary}` exercises must fail with \
             {expected}, not with some unrelated diagnostics.\ndiagnostics:\n{diagnostics}"
        );
    }
}
