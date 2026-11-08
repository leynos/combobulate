//! Structural checks that keep the cardinality gate out of the root package.
//!
//! `trybuild` merges the host package's dependencies *and* development
//! dependencies into the crate it generates. The gate therefore lives in its
//! own workspace, so that generated crate compiles the probe and `trybuild`
//! rather than the root dependency graph. That property is the fix for the
//! incident; these checks keep it from being undone by a later tidy-up that
//! moves the gate back under the root package.
//!
//! The gate's own test asserts the same exclusion from inside the gate, where
//! it also reads `cargo metadata`. This file covers the root side: the fixture
//! oracle and the gate package's independence from the root workspace.

use camino::{Utf8Path, Utf8PathBuf};
use cap_std::{ambient_authority, fs_utf8::Dir};

/// Opens the repository root as a capability handle.
///
/// The helpers in this file return their errors rather than panicking. They
/// sit outside a `#[test]` body, where the repository's lint policy forbids
/// `expect` and `panic`, so each test body decides how a read failure is
/// reported.
fn repository() -> std::io::Result<Dir> {
    Dir::open_ambient_dir(
        Utf8Path::new(env!("CARGO_MANIFEST_DIR")),
        ambient_authority(),
    )
}

/// The gate must be its own workspace so `trybuild` sees only its manifest.
#[test]
fn gate_declares_its_own_workspace() {
    let root = repository().expect("the repository root must be openable");
    let manifest = root
        .read_to_string("tools/gates/cardinality-ui/Cargo.toml")
        .expect("the cardinality gate manifest must be readable");
    assert!(
        manifest.contains("[workspace]"),
        concat!(
            "the gate must declare `[workspace]` so it does not inherit the root package's ",
            "dev-dependencies into a nested trybuild build"
        )
    );
    assert!(
        !manifest.contains("polars"),
        concat!(
            "the gate manifest must never name polars: it is a forward-looking guard so the ",
            "measurement stack cannot be pulled into a compile check"
        )
    );
}

/// Every fixture must exist, byte-identical, on both sides.
///
/// The gate keeps its own copies because `trybuild` writes an absolute path
/// into an out-of-package case's diagnostic. Keeping the oracle in `tests/ui/`
/// means the contract is visible from the root suite.
///
/// The comparison runs in both directions on purpose. Checking only the oracle
/// would let a fixture added under the gate go unseen, and a fixture that only
/// the gate compiles is exactly the one the root suite cannot review.
#[test]
fn every_fixture_exists_on_both_sides() {
    let root = repository().expect("the repository root must be openable");
    let oracle = fixture_names(&root, "tests/ui")
        .expect("the repository fixture directory must be readable");
    let gate = fixture_names(&root, "tools/gates/cardinality-ui/tests/ui")
        .expect("the gate fixture directory must be readable");

    assert!(
        !oracle.is_empty(),
        "the repository must keep at least one cardinality fixture"
    );
    assert_eq!(
        oracle, gate,
        "the oracle and the gate must hold the same fixture names"
    );

    for name in oracle {
        assert_eq!(
            root.read(Utf8Path::new("tests/ui").join(&name))
                .expect("the oracle fixture must be readable"),
            root.read(Utf8Path::new("tools/gates/cardinality-ui/tests/ui").join(&name))
                .expect("the gate fixture copy must be readable"),
            "{name} must not drift between the oracle and the gate"
        );
    }
}

/// Lists a fixture directory's entry names in a stable order.
fn fixture_names(root: &Dir, directory: &str) -> std::io::Result<Vec<Utf8PathBuf>> {
    let mut names = root
        .read_dir(directory)?
        .map(|entry| Ok(Utf8PathBuf::from(entry?.file_name()?)))
        .collect::<std::io::Result<Vec<_>>>()?;
    names.sort();
    Ok(names)
}

/// Both a rejecting and an accepting fixture must exist.
///
/// A compile-fail gate on its own cannot distinguish "the contract held" from
/// "the fixture stopped compiling". The accepting control is what rules out the
/// second reading.
#[test]
fn the_gate_pairs_a_failing_fixture_with_a_passing_control() {
    let root = repository().expect("the repository root must be openable");
    for (name, purpose) in [
        (
            "cardinality_result_must_be_used",
            "a discarded result must still fail the build",
        ),
        (
            "cardinality_result_is_used",
            "a bound result must still compile",
        ),
    ] {
        assert!(
            root.is_file(format!("tests/ui/{name}.rs")),
            "{name}.rs must exist: {purpose}"
        );
    }
}
