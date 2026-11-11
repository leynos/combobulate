//! Gate-profile separation contracts: verifier exclusion and Polars confinement.
//!
//! The workspace ships two ordinary profiles and one verifier profile, and the
//! boundaries between them are claims about *resolved closures* rather than
//! about manifests. A requirement can say `optional = true` and still be
//! selected through a feature another dependency turns on, so every check here
//! reads what Cargo actually resolved and compares the two ordinary profiles
//! against each other.
//!
//! Each rule is exercised against the live workspace and against a canned
//! fixture that would otherwise let it pass vacuously.

use std::{collections::HashSet, error::Error};

use googletest::prelude::*;

/// Live Cargo reads and the `cargo tree` predicates the boundaries use.
///
/// The module is shared with `workspace_boundaries.rs`, which needs the
/// metadata half this file does not; those items are dead code here and live
/// there. `expect` rather than `allow` so the exception fails loudly once the
/// last unused item is gone and the declaration can be retired.
#[expect(
    dead_code,
    reason = "the shared support module serves two test binaries"
)]
#[path = "support/live_cargo.rs"]
mod cargo;

use cargo::{metadata::FACADE, tree};

/// The Polars release AC-04 and task 1.2.6 are calibrated against.
///
/// Written as it appears in `cargo tree` output so the assertion reads the
/// resolved version rather than trusting the manifest's requirement.
const PINNED_POLARS: &str = "polars v0.55.2";

/// The package name the resolved-feature edges are read from.
const POLARS_PACKAGE: &str = "polars";

/// The features the pinned Polars release must select, and no others.
///
/// `default-features = false` in the facade's requirement makes this list the
/// whole set rather than a minimum: Cargo adds nothing that is not named here
/// or reached through `lazy`'s own closure, so equality is the correct
/// comparison and a substituted feature fails rather than passing unnoticed.
const PINNED_POLARS_FEATURES: &[&str] = &["lazy", "polars-lazy"];

/// VO-3: every ordinary profile's facade closure carries no verifier runtime.
///
/// Both ordinary profiles are checked. VO-3 names `native-only` and
/// `polars-enabled` together, and checking only the first would pass while the
/// profile that ships to consumers — the one whose closure is larger, because
/// Polars brings its own dependency tree — carried a verifier through a
/// feature-gated edge the smaller closure never reaches.
#[test]
fn ordinary_profiles_exclude_verifiers() -> Result<(), Box<dyn Error>> {
    for arguments in [
        &[
            "-p",
            FACADE,
            "--no-default-features",
            "--target",
            "all",
            "-e",
            "all",
        ][..],
        &["-p", FACADE, "--target", "all", "-e", "all"][..],
    ] {
        let tree = cargo::live_tree(arguments)?;
        assert_that!(
            tree::verifier_packages(&tree),
            is_empty(),
            "the facade closure for {arguments:?} must carry no verifier runtime"
        );
    }
    Ok(())
}

/// VO-3 non-vacuity: a facade that reached a verifier must be reported.
#[test]
fn verifier_leaks_are_reported() {
    let reported = tree::verifier_packages(include_str!("fixtures/cargo/facade-reaches-vstd.tree"));
    assert_that!(reported, contains(eq("vstd")));
}

/// VO-4: Polars reaches exactly one profile, at exactly the pinned release.
///
/// The two closures are compared to each other rather than to a literal, so
/// the positive case witnesses the negative one: if the native-only closure
/// also carried Polars the difference would be empty, and if the Polars-enabled
/// closure did not the difference would be too.
///
/// The enabled profile is also checked for the *resolved features*, not merely
/// for the package and its version. VO-4 pins the release **and** its features,
/// and the feature set is what the AC-04 calibration was taken against:
/// `default-features = false` means the manifest's list is the whole set, so a
/// default feature re-enabled by another dependency would compile backend code
/// the measurement never saw while the version assertion still passed.
#[test]
fn polars_appears_only_when_enabled() -> Result<(), Box<dyn Error>> {
    let native_tree = cargo::live_tree(&[
        "-p",
        FACADE,
        "--no-default-features",
        "--target",
        "all",
        "-e",
        "all",
    ])?;
    let polars_tree = cargo::live_tree(&["-p", FACADE, "--target", "all", "-e", "all"])?;

    assert_that!(tree::backend_packages(&native_tree), is_empty());
    assert_that!(polars_tree, contains_substring(PINNED_POLARS));

    let native_packages: HashSet<String> = tree::package_names(&native_tree).into_iter().collect();
    let added: HashSet<String> = tree::package_names(&polars_tree)
        .into_iter()
        .filter(|package| !native_packages.contains(package))
        .collect();
    assert_that!(added, contains(eq(&"polars".to_owned())));
    assert_that!(native_packages.contains("polars"), eq(false));

    let features: HashSet<String> = tree::features_of(&polars_tree, POLARS_PACKAGE)
        .into_iter()
        .collect();
    let pinned: HashSet<String> = PINNED_POLARS_FEATURES
        .iter()
        .map(|feature| (*feature).to_owned())
        .collect();
    assert_that!(
        features,
        eq(&pinned),
        "the polars-enabled closure must select exactly the pinned feature set"
    );
    Ok(())
}

/// VO-4 non-vacuity: the feature reader separates a package from its lookalikes.
///
/// `features_of` matches on a name boundary, so the two ways it could return
/// the right answer for the wrong reason are pinned here: a sibling package
/// whose name merely starts with the target's must not contribute, and a
/// package the tree does not mention must report nothing. Without the first
/// case a prefix bug would smuggle `polars-buffer`'s `default` feature into the
/// `polars` set; without the second, a reader that returned every feature line
/// would pass the live case only as long as nothing else was in the tree.
#[test]
fn feature_edges_are_attributed_to_the_named_package() {
    let tree = include_str!("fixtures/cargo/facade-polars-features.tree");
    let mut reported = tree::features_of(tree, POLARS_PACKAGE);
    reported.sort();
    assert_that!(
        reported,
        eq(&vec!["lazy".to_owned() as String, "polars-lazy".to_owned()]),
        "only the named package's own feature edges may be reported"
    );
    assert_that!(
        tree::features_of(tree, "absent-package"),
        is_empty(),
        "a package the tree does not mention must report no features"
    );
}
