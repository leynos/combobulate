//! Workspace boundary contracts for the kernel, macro, and facade crates.
//!
//! The kernel must carry no backend and never be host-compiled, and dependency
//! edges must point one way. Each rule is a pure predicate over Cargo's own
//! output, exercised against the live workspace and against canned fixtures
//! that would otherwise let the rule pass vacuously.
//!
//! The gate-profile boundaries — verifier exclusion and Polars confinement —
//! live in `workspace_profiles.rs`, and the kernel's source-level `#![no_std]`
//! boundary in `workspace_kernel_boundary.rs`. Splitting them keeps each file
//! under the repository's length limit without narrowing what is checked.

use std::{error::Error, ffi::OsStr};

use googletest::prelude::*;
use rstest::rstest;

/// Live Cargo reads and the predicates over its declared and resolved graphs.
///
/// The module is shared with `workspace_profiles.rs`, which needs the tree
/// half this file does not; those items are dead code here and live there.
/// `expect` rather than `allow` so the exception fails loudly once the last
/// unused item is gone and the declaration can be retired.
#[expect(
    dead_code,
    reason = "the shared support module serves two test binaries"
)]
#[path = "support/live_cargo.rs"]
mod cargo;

use cargo::{
    metadata::{KERNEL, MACROS},
    tree,
};

/// The `cargo fetch` arguments that populate every target's packages.
///
/// The suite never runs this; `make prepare-dependencies` does. The constant
/// records only the locked, target-free fetch form the offline reads assume.
/// It is not wired to the recipe, so the constant and the real fetch can drift
/// apart without failing this suite. `parallel_all_runs_each_gate_in_order` in
/// `tests/make_gate_order.rs` checks the root fetch's actual argv and working
/// directory.
///
/// `--target` takes a target triple, not `all`, so it must not appear here:
/// a plain `cargo fetch --locked` already resolves the whole lockfile graph,
/// including the platform packages that `cargo tree --target all` reads.
const FETCH_ARGUMENTS: [&str; 2] = ["fetch", "--locked"];

/// Contract: the live checks stay lockfile-pinned, offline, and flag-neutral.
///
/// No caller build selector survives into the live child. The fetch assertions
/// below check only the local constant; the Make gate test named on
/// `FETCH_ARGUMENTS` checks the fetch the recipe actually runs.
#[test]
fn live_invocations_pin_the_lockfile_and_clear_build_overrides() {
    let tree = cargo::tree_command(&["-p", KERNEL, "--target", "all"]);
    let tree_arguments: Vec<String> = tree
        .get_args()
        .map(|argument| argument.to_string_lossy().into_owned())
        .collect();
    for expected in ["--locked", "--offline"] {
        assert!(
            tree_arguments.iter().any(|argument| argument == expected),
            "the live tree check must pass {expected}: {tree_arguments:?}"
        );
    }

    // `--offline` is the argv half of the contract; this is the environment
    // half. Both must be present, because either can be dropped on its own.
    let environment: Vec<(&OsStr, Option<&OsStr>)> = tree.get_envs().collect();
    let offline_setting = environment
        .iter()
        .find(|entry| entry.0 == OsStr::new("CARGO_NET_OFFLINE"))
        .copied();
    assert_eq!(
        offline_setting,
        Some((OsStr::new("CARGO_NET_OFFLINE"), Some(OsStr::new("true")))),
        "the live tree check must set CARGO_NET_OFFLINE=true so a cold cache fails instead of \
         fetching mid-test: {environment:?}"
    );

    let fetch_arguments: Vec<String> = FETCH_ARGUMENTS
        .iter()
        .map(|argument| (*argument).to_owned())
        .collect();
    assert!(
        fetch_arguments
            .iter()
            .any(|argument| argument == "--locked"),
        "the dependency fetch must pass --locked: {fetch_arguments:?}"
    );
    assert!(
        !fetch_arguments
            .iter()
            .any(|argument| argument == "--target"),
        "cargo fetch takes a target triple, not `all`; its plain form already resolves every \
         target's packages: {fetch_arguments:?}"
    );

    for command in [tree, cargo::fetch_command()] {
        let cleared: Vec<String> = command
            .get_envs()
            .filter(|(_, value)| value.is_none())
            .map(|(name, _)| name.to_string_lossy().into_owned())
            .collect();
        for expected in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET"] {
            assert!(
                cleared.iter().any(|name| name == expected),
                "{expected} must not reach the Cargo child: {cleared:?}"
            );
        }
    }
}

/// A cold-cache failure must name the preparation step, not only Cargo's error.
#[test]
fn offline_tree_failures_name_the_preparation_step() {
    let detail = "cargo tree exited with 101: failed to download `winapi-util v0.1.11`";
    let message = cargo::offline_recovery(detail);
    for expected in [
        "make prepare-dependencies",
        "cargo fetch --locked",
        "host-only",
        detail,
    ] {
        assert!(
            message.contains(expected),
            "the cold-cache diagnostic must contain {expected:?}: {message}"
        );
    }
}

/// VO-1: the kernel declares no backend and its resolved closure carries none.
#[test]
fn kernel_excludes_backends() -> Result<(), Box<dyn Error>> {
    let metadata = cargo::live_metadata()?;
    assert_that!(
        cargo::metadata::package_names(&metadata),
        contains(eq(KERNEL))
    );
    assert_that!(
        cargo::metadata::kernel_dependency_names(&metadata),
        is_empty()
    );
    let kernel_tree = cargo::live_tree(&[
        "-p",
        KERNEL,
        "--all-features",
        "--target",
        "all",
        "-e",
        "all",
    ])?;
    assert_that!(tree::backend_packages(&kernel_tree), is_empty());
    Ok(())
}

/// VO-1 non-vacuity: a backend edge must be reported, not silently accepted.
#[rstest]
#[case::declared_edge(
    include_str!("fixtures/cargo/kernel-reaches-glam.json"),
    "glam"
)]
#[case::resolved_closure(
    include_str!("fixtures/cargo/kernel-tree-with-glam.tree"),
    "glam"
)]
fn kernel_backend_edges_are_reported(#[case] fixture: &str, #[case] backend: &str) {
    let reported = if fixture.trim_start().starts_with('{') {
        let metadata =
            cargo::metadata::parse_metadata(fixture).expect("the metadata fixture must parse");
        cargo::metadata::kernel_backend_dependencies(&metadata)
    } else {
        tree::backend_packages(fixture)
    };
    assert_that!(reported, contains(eq(backend)));
}

/// VO-2: every declared edge points from the facade towards its members.
#[test]
fn dependency_direction_holds() -> Result<(), Box<dyn Error>> {
    let metadata = cargo::live_metadata()?;
    assert_that!(cargo::metadata::direction_violations(&metadata), is_empty());
    assert_that!(
        cargo::metadata::facade_depends_normally_on(&metadata, KERNEL),
        eq(true)
    );
    assert_that!(
        cargo::metadata::facade_depends_normally_on(&metadata, MACROS),
        eq(true)
    );
    Ok(())
}

/// VO-2 control: a correctly directed workspace reports no violation.
#[test]
fn valid_workspace_reports_no_violation() {
    let metadata =
        cargo::metadata::parse_metadata(include_str!("fixtures/cargo/workspace-valid.json"))
            .expect("the valid workspace fixture must parse");
    assert_that!(cargo::metadata::direction_violations(&metadata), is_empty());
    assert_that!(
        cargo::metadata::facade_depends_normally_on(&metadata, KERNEL),
        eq(true)
    );
    assert_that!(
        cargo::metadata::facade_depends_normally_on(&metadata, MACROS),
        eq(true)
    );
}

/// VO-2: the kernel is never compiled for the host by a macro or build script.
#[test]
fn kernel_never_host_compiled() -> Result<(), Box<dyn Error>> {
    let metadata = cargo::live_metadata()?;
    let violations = cargo::metadata::direction_violations(&metadata);
    assert_that!(
        violations.join("; ").as_str(),
        not(contains_substring("build-depend"))
    );
    let macro_tree = cargo::live_tree(&["-p", MACROS, "--target", "all", "-e", "all"])?;
    assert_that!(tree::contains_package(&macro_tree, KERNEL), eq(false));
    Ok(())
}

/// VO-2 non-vacuity: each forbidden edge shape names the edge it rejects.
#[rstest]
#[case::facade_build_dependency(
    include_str!("fixtures/cargo/facade-kernel-build-dependency.json"),
    "build-depend"
)]
#[case::macros_depends_on_kernel(
    include_str!("fixtures/cargo/macros-depends-on-kernel.json"),
    KERNEL
)]
fn direction_violations_are_reported(#[case] fixture: &str, #[case] expected: &str) {
    let metadata =
        cargo::metadata::parse_metadata(fixture).expect("the metadata fixture must parse");
    let violations = cargo::metadata::direction_violations(&metadata);
    assert_that!(violations.join("; ").as_str(), contains_substring(expected));
}
