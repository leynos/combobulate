//! Keep the cardinality compile-fail gate inside ordinary test discovery.
//!
//! The gate itself lives in `tools/gates/cardinality-ui`, its own Cargo
//! workspace. `trybuild` copies the host package's dependencies and development
//! dependencies into the crate it generates, so running it from this package
//! made the generated crate inherit the whole root dev-dependency graph and
//! compile it in a nested build that nothing bounded. That is the shape of
//! the incident this test exists to prevent: a `[>8160s]` test that was really
//! waiting on a nested Cargo build.
//!
//! What the nested build actually compiled is the ten direct root
//! dev-dependencies (`cargo tree -e dev`): `cardinality-probe`, `camino`,
//! `cap-std`, `googletest`, `rstest`, `serde`, `serde_json`, `serde_yaml`,
//! `toml`, and `trybuild`, plus their transitive closures. `polars` is *not*
//! among them: it is an optional dependency of the probe behind a
//! non-default feature. The observed cost is the graph, not any one member of
//! it, and the repair removes the dependency on the graph's size rather than
//! on one heavyweight crate.
//!
//! So this test does not compile the gate. `make prepare-dependencies` fetches
//! both workspaces, `make prepare-ui-gate` builds the gate's test binary before
//! any test body runs, and this file only reads the path that build recorded
//! and holds that binary to its diagnostic contract; under nextest, nextest bounds the test.
//! `make test-ui` builds the same binary through the same recipe and then runs
//! it, so both routes agree.
//!
//! The path comes from Cargo, not from a search of the build directory. A
//! preparation step lets Cargo choose where its output goes, so an inherited
//! `CARGO_TARGET_DIR` can redirect the build somewhere this test would never
//! look; and even in the default location, choosing the newest file by
//! modification time binds the run to whatever was written last rather than to
//! the build that just completed. `make prepare-ui-gate` therefore captures the
//! executable from Cargo's own `compiler-artifact` message with
//! `scripts/cardinality_ui_gate.py`, and
//! `scripts/tests/test_cardinality_ui_gate.py` keeps that selection policy
//! honest, including the redirected-target and stale-artifact cases.
//!
//! `trybuild` reads `CARGO_MANIFEST_DIR` from its own process environment to
//! decide which package's manifest to copy. Cargo sets that variable for every
//! test process it starts, to *this* package. Passing it through would make the
//! gate compile the root package's dev-dependency graph — the exact regression
//! the gate package exists to prevent. The child environment is therefore
//! scrubbed, and the working directory is set to the gate, which is where
//! `trybuild` falls back to looking when the variable is absent.
//!
//! When no record exists — a bare `cargo test` on a cold checkout — the test
//! fails with the command that builds it rather than spending minutes
//! compiling the root dev-dependency graph inside this process.

use std::process::Command;

use camino::{Utf8Path, Utf8PathBuf};
use cap_std::{ambient_authority, fs_utf8::Dir};

/// Environment variable `trybuild` uses to locate the package it copies.
///
/// `trybuild` reads this from the child process. Cargo sets it to the package
/// under test — here, the root package — so it must not be inherited by the
/// gate binary, or the gate silently becomes the nested build it replaced.
const MANIFEST_DIR_VARIABLE: &str = "CARGO_MANIFEST_DIR";

/// The gate package's directory, relative to the repository root.
const GATE_DIRECTORY: &str = "tools/gates/cardinality-ui";

/// Where the gate's preparation records the executable Cargo just built.
///
/// `scripts/cardinality_ui_gate.py` writes this file and this test reads it,
/// so the two agree on one path rather than duplicating a search. It lives
/// under `target/`, which the repository's root `.gitignore` excludes.
const GATE_BINARY_RECORD: &str = "target/cardinality-ui-binary";

/// The gate must be run, passing, from the root suite.
#[test]
fn checked_cardinality_result_must_be_used() {
    let repository = Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let gate = repository.join(GATE_DIRECTORY);
    let record = gate.join(GATE_BINARY_RECORD);
    let binary = recorded_gate_binary(&record).unwrap_or_else(|| {
        panic!(
            "the cardinality gate test binary is not built, or its build record is \
             unreadable.\nRun `make prepare-ui-gate` (or `make test-ui`) first. The gate is a \
             separate workspace, so the root build never produces it, and building it from inside \
             this test would put a nested Cargo build under a test deadline for the root \
             package's whole dependency graph.\nExpected the absolute path of the built test \
             binary in {record}"
        )
    });

    let observed = Command::new(&binary)
        .current_dir(&gate)
        .env_remove(MANIFEST_DIR_VARIABLE)
        .output()
        .expect("the gate test binary must start");

    assert!(
        observed.status.success(),
        "the cardinality compile-fail gate must pass.\ncommand: {binary}\ndirectory: \
         {gate}\nstatus: {}\nstdout:\n{}\nstderr:\n{}",
        observed.status,
        String::from_utf8_lossy(&observed.stdout),
        String::from_utf8_lossy(&observed.stderr)
    );
}

/// Reads the executable path preparation recorded for the gate's test binary.
///
/// Returning `None` rather than an error keeps the caller's message in charge
/// of what to run. A blank record is treated as absent, because a truncated
/// preparation must not be reported as an executable path. The read goes
/// through a capability opened on the record's own directory, which is the
/// gate's `target/` tree and may legitimately not exist before preparation.
fn recorded_gate_binary(record: &Utf8Path) -> Option<Utf8PathBuf> {
    let directory = Dir::open_ambient_dir(record.parent()?, ambient_authority()).ok()?;
    let text = directory.read_to_string(record.file_name()?).ok()?;
    let path = text.trim();
    if path.is_empty() {
        return None;
    }
    Some(Utf8PathBuf::from(path))
}
