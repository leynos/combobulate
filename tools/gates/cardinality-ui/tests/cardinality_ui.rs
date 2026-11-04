//! Compile-fail gate for the calibration probe's `#[must_use]` contract.
//!
//! The probe returns a value that records overflow rather than panicking, so
//! discarding it silently loses the only signal that a cardinality computation
//! overflowed. `checked_cardinality` is `#[must_use]`, and this gate keeps the
//! compiler enforcing that: the fixture denies `unused_must_use` and discards
//! the result, so the build must fail with the exact diagnostic in
//! `tests/ui/cardinality_result_must_be_used.stderr`.
//!
//! A compile-pass control sits beside it. Without one, a fixture that failed to
//! compile for an unrelated reason would still satisfy `compile_fail`, and the
//! gate would go on passing after the contract it guards had been removed.
//!
//! This package declares only the probe and `trybuild`, which is the point of
//! it. `trybuild` copies the *host package's* dependencies and development
//! dependencies into the crate it generates, so a gate hosted in the root
//! package would compile the whole root dependency graph inside the nested
//! build. The first test below asserts that this manifest stays narrow.
//!
//! The fixtures are a synchronized copy of the repository oracle in
//! `tests/ui/`, because `trybuild` reports an out-of-package case with an
//! absolute path that would not match a shared `.stderr`. The `include_str!`
//! comparisons below keep the copy honest.
//!
//! Run it with `make test-ui` or as part of `make test`.

/// Dependency names that must never reappear in this gate's manifest.
///
/// These are the root package's development dependencies. `trybuild` merges
/// the host package's dependencies into the crate it generates, so their
/// absence here is what keeps the nested build off the root package's graph.
/// `polars` is a different case: it is an optional dependency of the probe,
/// and a forward-looking guard rather than evidence about the original
/// incident. Reaching it would mean the gate had started pulling the
/// measurement stack into a compile check.
const EXCLUDED_DEPENDENCIES: &[&str] = &[
    "camino",
    "cap-std",
    "googletest",
    "polars",
    "rstest",
    "serde",
    "serde_json",
    "serde_yaml",
    "toml",
];

/// Reject code that discards the overflow-sensitive cardinality result.
#[test]
fn checked_cardinality_result_must_be_used() {
    assert_oracle_copies_match();
    trybuild::TestCases::new().compile_fail("tests/ui/cardinality_result_must_be_used.rs");
}

/// Accept code that binds the result, so the gate cannot pass for the wrong reason.
#[test]
fn bound_cardinality_result_compiles() {
    assert_oracle_copies_match();
    trybuild::TestCases::new().pass("tests/ui/cardinality_result_is_used.rs");
}

/// Keep the gate's own dependency set narrow.
///
/// `cargo metadata` is read for this package rather than the manifest being
/// parsed, because the question is what Cargo resolves, not what the text says.
#[test]
fn gate_declares_only_the_probe_and_trybuild() {
    let manifest = concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.toml");
    // Cargo sets `CARGO` for the processes it runs. The fallback keeps the
    // test runnable when it is started some other way, which is what the root
    // suite's binary lookup does.
    let cargo = std::env::var_os("CARGO").unwrap_or_else(|| "cargo".into());
    let output = std::process::Command::new(cargo)
        .args([
            "metadata",
            "--no-deps",
            "--format-version",
            "1",
            "--manifest-path",
            manifest,
        ])
        .output()
        .expect("cargo metadata must run for the gate package");
    assert!(
        output.status.success(),
        "cargo metadata must succeed for the gate package: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let metadata = String::from_utf8(output.stdout).expect("cargo metadata emits UTF-8");
    for excluded in EXCLUDED_DEPENDENCIES {
        assert!(
            !metadata.contains(&format!("\"{excluded}\"")),
            "the gate must not depend on {excluded}: trybuild copies the host \
             package's dependencies into its generated crate, so reaching it \
             would put the root graph or the measurement stack inside a \
             compile check"
        );
    }
    for required in ["cardinality-probe", "trybuild"] {
        assert!(
            metadata.contains(&format!("\"{required}\"")),
            "the gate must still depend on {required}"
        );
    }
}

/// Fail if either fixture has drifted from the repository oracle.
fn assert_oracle_copies_match() {
    assert_eq!(
        include_str!("ui/cardinality_result_must_be_used.rs"),
        include_str!("../../../../tests/ui/cardinality_result_must_be_used.rs"),
        "the gate's compile-fail input must match the repository oracle"
    );
    assert_eq!(
        include_str!("ui/cardinality_result_must_be_used.stderr"),
        include_str!("../../../../tests/ui/cardinality_result_must_be_used.stderr"),
        "the gate must preserve the repository's exact diagnostic"
    );
    assert_eq!(
        include_str!("ui/cardinality_result_is_used.rs"),
        include_str!("../../../../tests/ui/cardinality_result_is_used.rs"),
        "the gate's compile-pass control must match the repository oracle"
    );
}
