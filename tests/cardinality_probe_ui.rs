//! Keep the cardinality compile-fail gate inside ordinary test discovery.
//!
//! The gate itself lives in `tools/gates/cardinality-ui`, its own Cargo
//! workspace. `trybuild` copies the host package's dependencies and development
//! dependencies into the crate it generates, so running it from this package
//! made the generated crate inherit the whole root dev-dependency graph and
//! compile it in a nested build with no clock of its own. That is the shape of
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
//! any test body runs, and this file only finds that binary and holds it to its
//! diagnostic contract under an external-command deadline. The direct
//! `make test-ui` route builds and runs the same gate.
//!
//! Two details make the lookup work, and both are load-bearing:
//!
//! * Cargo writes this package's artifacts under the new build-directory layout,
//!   `target/debug/build/<package>/<hash>/out/`, not the older `target/debug/deps/`. The walk below
//!   looks in the directory Cargo actually uses.
//! * `trybuild` reads `CARGO_MANIFEST_DIR` from its own process environment to decide which
//!   package's manifest to copy. Cargo sets that variable for every test process it starts, to
//!   *this* package. Passing it through would make the gate compile the root package's
//!   dev-dependency graph — the exact regression the gate package exists to prevent. The child
//!   environment is therefore scrubbed, and the working directory is set to the gate, which is
//!   where `trybuild` falls back to looking when the variable is absent.
//!
//! When the binary is absent — a bare `cargo test` on a cold checkout — the
//! test fails with the command that builds it rather than spending minutes
//! compiling the root dev-dependency graph inside this process.

use std::{path::Path, time::Duration};

use camino::{Utf8Path, Utf8PathBuf};
use cap_std::{ambient_authority, fs_utf8::Dir};

#[path = "support/process_deadline.rs"]
mod deadline;

use deadline::CommandDeadline;

/// Environment variable `trybuild` uses to locate the package it copies.
///
/// `trybuild` reads this from the child process. Cargo sets it to the package
/// under test — here, the root package — so it must not be inherited by the
/// gate binary, or the gate silently becomes the nested build it replaced.
const MANIFEST_DIR_VARIABLE: &str = "CARGO_MANIFEST_DIR";

/// The gate package's directory, relative to the repository root.
const GATE_DIRECTORY: &str = "tools/gates/cardinality-ui";

/// The gate binary's stem: Cargo appends a content hash to it.
const GATE_BINARY_STEM: &str = "cardinality_ui-";

/// How long the gate may run before it is treated as wedged.
///
/// The gate compiles one crate plus `trybuild`'s generated crate. The
/// measurements behind the nextest override in `.config/nextest.toml` put the
/// green hosted run at 50.3 s and the hosted profile run at 134.2 s, so this
/// bound clears the slower figure by a wide margin.
///
/// This deadline is deliberately *slower* than nextest's. Nextest terminates
/// the test process at `terminate-after = 10` (600 s); if this deadline fired
/// first, a build slowed by the shared compile queue would be reported as a
/// wedged gate and the real cause — queue contention — would be hidden behind
/// a timeout message. Measured locally while 185 builds were queued ahead, the
/// gate still completed in 443.24 s; a warm full-suite run took 195.23 s. This
/// bound clears the contended sample by 457 s. A genuinely hung build is still
/// ended well before an outer job timeout, and nextest's own diagnosis reaches
/// the operator first.
const GATE_DEADLINE: Duration = Duration::from_mins(15);

/// The gate must be run, passing, from the root suite.
#[test]
fn checked_cardinality_result_must_be_used() {
    let repository = Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let gate = repository.join(GATE_DIRECTORY);
    let binary = gate_binary(&gate).unwrap_or_else(|| {
        panic!(
            "the cardinality gate test binary is not built.\nRun `make prepare-ui-gate` (or `make \
             test-ui`) first. The gate is a separate workspace, so the root build never produces \
             it, and building it from inside this test would put a nested Cargo build under a \
             test deadline for the root package's whole dependency graph.\nLooked under \
             {gate}/target/debug/build/"
        )
    });

    let mut command = CommandDeadline::with_deadline(&binary, GATE_DEADLINE);
    command
        .command()
        .current_dir(&gate)
        .env_remove(MANIFEST_DIR_VARIABLE);
    let observed = command
        .output()
        .expect("the gate test binary must start through the bounded command boundary");

    assert!(
        !observed.exceeded_deadline(),
        "the cardinality gate must finish inside {GATE_DEADLINE:?}; it was still running after \
         {:?}.\ncommand: {}\ndirectory: {}",
        observed.duration(),
        observed.line(),
        gate
    );
    assert!(
        observed.status().success(),
        "the cardinality compile-fail gate must pass.\ncommand: {}\ndirectory: {}\nstatus: \
         {}\nstdout:\n{}\nstderr:\n{}",
        observed.line(),
        gate,
        observed.status(),
        String::from_utf8_lossy(observed.stdout()),
        String::from_utf8_lossy(observed.stderr())
    );
}

/// Finds the newest built `cardinality_ui` test binary in the gate workspace.
///
/// Cargo names test binaries with a content hash and places them where the
/// active build-directory layout says, which for this Cargo version is
/// `build/<package>/<hash>/out/`. So the search walks `target/debug/build`
/// rather than assuming a single fixed depth, and the newest match is the one
/// the last build produced. Returning `None` rather than an error keeps the
/// caller's message in charge of what to run.
fn gate_binary(gate: &Utf8Path) -> Option<Utf8PathBuf> {
    let build = gate.join("target/debug/build");
    let root = Dir::open_ambient_dir(&build, ambient_authority()).ok()?;
    let mut candidates: Vec<(cap_std::time::SystemTime, Utf8PathBuf)> = Vec::new();
    collect_gate_binaries(&root, &build, &mut candidates);
    candidates.sort_by_key(|(modified, _)| *modified);
    candidates.pop().map(|(_, path)| path)
}

/// Adds every gate test binary below `directory` to `candidates`.
///
/// The walk descends directories and records matching files, ignoring anything
/// it cannot inspect. A partially built tree is the normal case while a build
/// is running, so a transient read failure must not fail the lookup; the
/// caller reports a missing binary instead.
fn collect_gate_binaries(
    directory: &Dir,
    path: &Utf8Path,
    candidates: &mut Vec<(cap_std::time::SystemTime, Utf8PathBuf)>,
) {
    let Ok(entries) = directory.entries() else {
        return;
    };
    for entry in entries.filter_map(Result::ok) {
        let Ok(name) = entry.file_name() else {
            continue;
        };
        let child = path.join(&name);
        let Ok(file_type) = entry.file_type() else {
            continue;
        };
        if file_type.is_dir() {
            if let Ok(child_directory) = entry.open_dir() {
                collect_gate_binaries(&child_directory, &child, candidates);
            }
            continue;
        }
        if !is_gate_binary(&name) {
            continue;
        }
        if let Some(modified) = entry.metadata().ok().and_then(|meta| meta.modified().ok()) {
            candidates.push((modified, child));
        }
    }
}

/// Reports whether `name` is a gate test binary rather than build bookkeeping.
///
/// Cargo leaves the dependency-info file beside the binary under the same stem,
/// so the `.d` suffix has to be excluded or the newest match could be a text
/// file that is not executable.
fn is_gate_binary(name: &str) -> bool {
    name.starts_with(GATE_BINARY_STEM)
        && !Path::new(name)
            .extension()
            .is_some_and(|extension| extension.eq_ignore_ascii_case("d"))
}
