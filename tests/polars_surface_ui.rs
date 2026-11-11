//! Prove the Polars-gated surface is absent without the feature and present with it.
//!
//! `src/lib.rs` gates three public items on `feature = "polars"`:
//! `BackendProbeError`, its re-export, and `polars_backend_probe`. An ordinary
//! test can only read them when the feature is on, so nothing in the suite
//! observes the negative direction: a gate accidentally removed from the
//! `BackendProbeError` re-export, or from the probe, would let both items into
//! the native-only profile and every existing test would still pass.
//!
//! So the negative direction is a *build*, not an assertion. The fixture in
//! `tools/fixtures/polars-surface-absent` is a downstream crate that takes the
//! facade with default features off and names both items; this test builds it
//! and requires that build to fail with exactly those names unresolved. A build
//! that succeeded would mean the gate had been dropped for at least one of them.
//!
//! The positive direction needs no second fixture: the `present` module below
//! only compiles when `polars` is on, so the default profile's test binary is
//! itself the proof that both items exist. That costs no extra build, which
//! matters — a second Cargo fixture build would add minutes to every gate
//! profile to restate a fact this file's own compilation already checks.
//!
//! The fixture is deliberately not `trybuild`. `trybuild` copies the host
//! package's whole dependency graph into a generated crate, which is the
//! incident `tests/cardinality_probe_ui.rs` exists to prevent; a plain
//! path-dependency fixture inherits only what an ordinary consumer would, and
//! its build failure is the same evidence at a fraction of the cost.
//!
//! It also needs no Makefile preparation, unlike the cardinality gate. That
//! gate needs `prepare-ui-gate-dependencies` because its `trybuild` fixture
//! resolves registry crates; this fixture's lockfile holds three path packages
//! and nothing from a registry, so `--locked --offline` resolves from the
//! checkout alone. It is wired the same way as
//! `tools/fixtures/native-consumer`, the other consumer fixture the suite
//! builds: no Make target names it, and `tests/native_consumer_e2e.rs` proves
//! that arrangement works cold. Adding a fetch for it would also break the
//! gate-order contract — `tests/support/make_gate_order_scripts.rs` maps every
//! Cargo invocation to a known stage and exits non-zero on an unregistered one,
//! so a new `fetch --manifest-path` in `prepare-dependencies` would be recorded
//! as `unexpected-cargo`.

use std::{
    path::{Path, PathBuf},
    process::Command,
};

/// The absence fixture's directory, relative to the repository root.
const ABSENT_FIXTURE: &str = "tools/fixtures/polars-surface-absent";

/// The two names `src/lib.rs` gates on `feature = "polars"`.
///
/// Each must appear in the fixture's failure output as an unresolved *item*.
/// Requiring both keeps a gate that exposes one and hides the other from
/// passing: the build fails either way, but only for the name that is actually
/// gated.
const GATED_NAMES: [&str; 2] = ["BackendProbeError", "polars_backend_probe"];

/// The diagnostic Rust emits for a name absent from a crate's public surface.
///
/// `E0425` is "cannot find value/type in crate": the item is not there at all.
/// `E0433` would be "failed to resolve: use of undeclared crate", which is a
/// missing *dependency* and would mean the fixture had lost the facade itself
/// rather than observed a feature gate. Requiring this exact code keeps a
/// mis-wired fixture from being read as a working absence.
const UNRESOLVED_IN_CRATE: &str = "E0425";

/// The fixture's manifest, resolved from the repository root Cargo sets.
fn fixture_manifest() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join(ABSENT_FIXTURE)
        .join("Cargo.toml")
}

/// Builds the absence fixture, returning its status and rendered diagnostics.
///
/// `CARGO_TARGET_DIR` is redirected into nextest's per-test temporary directory
/// so the fixture never writes into either workspace's `target/`, and the
/// caller's build selectors are removed so the fixture's result depends on its
/// own manifest rather than on how the suite was invoked. `--locked` makes a
/// stale fixture lockfile fail here rather than silently re-resolving, and
/// `--offline` keeps the check hermetic: the fixture's only dependency is a
/// path, so a network fetch would mean something had gone wrong.
///
/// No deadline is applied here. nextest gives this test its own process and
/// `.config/nextest.toml` owns the tier, which is the repository's standing
/// policy for tests that start `Command` children.
fn build_absent_fixture() -> std::io::Result<std::process::Output> {
    let target_dir = Path::new(env!("CARGO_TARGET_TMPDIR")).join("polars-surface-absent");
    let mut command = Command::new(env!("CARGO"));
    command
        .args([
            "build",
            "--locked",
            "--offline",
            "--message-format=short",
            "--manifest-path",
        ])
        .arg(fixture_manifest())
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .env("CARGO_TARGET_DIR", target_dir);
    for name in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET"] {
        command.env_remove(name);
    }
    command.output()
}

/// The fixture names both gated items and cannot build without the feature.
#[test]
fn the_polars_gated_items_are_absent_without_the_feature() {
    let output = build_absent_fixture().expect("the absence fixture's Cargo child must start");
    let diagnostics = format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        !output.status.success(),
        concat!(
            "the native-only profile must not expose the Polars-gated items, but the fixture ",
            "built successfully.\nA successful build means `BackendProbeError` or ",
            "`polars_backend_probe` is reachable with default features off.\ndiagnostics:\n{}"
        ),
        diagnostics
    );
    for name in GATED_NAMES {
        assert!(
            diagnostics.contains(name) && diagnostics.contains(UNRESOLVED_IN_CRATE),
            "the build must fail because `{name}` is unresolvable without the feature, not for \
             some unrelated reason.\ndiagnostics:\n{diagnostics}"
        );
    }
}

/// The same names resolve when the feature is on.
///
/// This module only compiles under `polars`, so its presence in the built test
/// binary is the positive half of the contract: a removed re-export or a
/// `cfg` narrowed from the wrong item fails this file's own compilation. The
/// body then exercises the resolved items, so the type relationship they are
/// meant to have is checked as well as their existence.
#[cfg(feature = "polars")]
mod present {
    /// Both items resolve, and the probe returns the backend's own error type.
    #[test]
    fn the_polars_gated_items_are_present_with_the_feature() {
        // Naming both items in the type of a function pointer forces the
        // compiler to resolve each one; a missing re-export fails this build.
        let probe: fn() -> Result<usize, combobulate::BackendProbeError> =
            combobulate::polars_backend_probe;
        let collected = probe();
        assert!(
            collected.is_ok(),
            "the present profile's probe must collect, got {collected:?}"
        );
    }
}

/// The fixture lives where the test says it does, so a moved fixture fails loudly.
///
/// The build above would fail with a resolution error if the manifest were
/// missing, but that message would read as a problem with the fixture's
/// dependency graph. This test names the actual fault.
#[test]
fn the_absence_fixture_manifest_is_in_the_tree() {
    let manifest = fixture_manifest();
    assert!(
        manifest.is_file(),
        "the absence fixture must exist at {}, or the absence check above has nothing to build",
        manifest.display()
    );
}
