//! Workspace boundary contracts for the kernel, macro, and facade crates.
//!
//! The kernel must carry no backend and never be host-compiled, dependency
//! edges must point one way, ordinary profiles must exclude verifiers, and the
//! kernel must keep its `#![no_std]` allocation boundary. Each rule is a pure
//! predicate over Cargo's own output, exercised against the live workspace and
//! against canned fixtures that would otherwise let the rule pass vacuously.

use std::{
    error::Error,
    process::{Command, Output},
};

use googletest::prelude::*;
use rstest::rstest;

/// Dependency-direction predicates over Cargo's declared graph.
#[path = "support/workspace_metadata.rs"]
mod metadata;
/// `cargo tree` parsing and dependency-prefix predicates.
#[path = "support/workspace_tree.rs"]
mod tree;

use metadata::{FACADE, KERNEL, MACROS, Metadata};

/// Applies the caller-independent routing every live Cargo read requires.
///
/// The live checks must describe the workspace, not the caller's shell. An
/// inherited `CARGO_BUILD_TARGET` would silently resolve a different target
/// than the one under test, and inherited flags would make the recorded graph
/// depend on how the suite happened to be invoked.
///
/// Every live read is offline: the suite never reaches the network, and a cold
/// cache fails with the recovery message below rather than fetching mid-test.
fn live_cargo(arguments: &[&str]) -> Command {
    let mut command = Command::new(env!("CARGO"));
    command
        .args(arguments)
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .env("CARGO_NET_OFFLINE", "true")
        .env_remove("RUSTFLAGS")
        .env_remove("CARGO_ENCODED_RUSTFLAGS")
        .env_remove("CARGO_BUILD_TARGET");
    command
}

/// The `cargo fetch` arguments that populate every target's packages.
///
/// The suite never runs this; `make prepare-dependencies` does. The contract
/// below still pins its shape, so the preparation step and the offline checks
/// cannot drift apart.
///
/// `--target` takes a target triple, not `all`, so it must not appear here:
/// a plain `cargo fetch --locked` already resolves the whole lockfile graph,
/// including the platform packages that `cargo tree --target all` reads.
const FETCH_ARGUMENTS: [&str; 2] = ["fetch", "--locked"];

/// Returns the `cargo tree` argv for a package and edge selection.
///
/// The prefix is the one source of truth for both the introspected command in
/// the routing contract and the command the live check actually runs.
fn tree_arguments<'a>(arguments: &'a [&'a str]) -> Vec<&'a str> {
    let mut full = vec!["tree", "--prefix", "none", "--locked", "--offline"];
    full.extend_from_slice(arguments);
    full
}

/// Builds the `cargo tree` invocation for a package and edge selection.
fn tree_command(arguments: &[&str]) -> Command { live_cargo(&tree_arguments(arguments)) }

/// Explains how to recover when the offline tree cannot resolve a package.
///
/// The fetch that populates every target's packages is `make
/// prepare-dependencies`. It runs before this suite in every supported
/// route, because nextest gives each test its own process and a fetch inside
/// one would repeat per test. A direct `cargo test` bypasses that preparation,
/// so the failure has to say what to run instead of reporting only Cargo's
/// HTTP refusal.
fn offline_recovery(detail: &str) -> String {
    format!(
        concat!(
            "cargo tree --offline could not resolve every target's packages: {detail}\n",
            "Run `make prepare-dependencies` first. It runs `cargo fetch --locked`, ",
            "which acquires the platform crates in the lockfile that a host-only ",
            "build never downloads."
        ),
        detail = detail
    )
}

/// Runs a live Cargo read; under nextest, nextest bounds the test that calls it.
fn run_read(arguments: &[&str]) -> Result<Output, Box<dyn Error>> {
    Ok(live_cargo(arguments).output()?)
}

/// Runs `cargo metadata --no-deps` against the live workspace.
fn live_metadata() -> Result<Metadata, Box<dyn Error>> {
    let observed = run_read(&[
        "metadata",
        "--no-deps",
        "--format-version",
        "1",
        "--locked",
        "--offline",
    ])?;
    if !observed.status.success() {
        return Err(format!(
            "cargo metadata must describe the workspace; exited with {}: {}",
            observed.status,
            String::from_utf8_lossy(&observed.stderr)
        )
        .into());
    }
    Ok(metadata::parse_metadata(&String::from_utf8(
        observed.stdout,
    )?)?)
}

/// Runs `cargo tree` with the given package and edge selection.
fn live_tree(arguments: &[&str]) -> Result<String, Box<dyn Error>> {
    let observed = run_read(&tree_arguments(arguments))?;
    if !observed.status.success() {
        let detail = format!(
            "cargo tree {arguments:?} exited with {}: {}",
            observed.status,
            String::from_utf8_lossy(&observed.stderr)
        );
        return Err(offline_recovery(&detail).into());
    }
    Ok(String::from_utf8(observed.stdout)?)
}

/// Contract: the live checks stay lockfile-pinned, offline, and flag-neutral.
///
/// No caller build selector survives into the live child, and the fetch that
/// makes the offline tree calls resolvable is stated here so it cannot drift
/// away from the Make preparation step that actually runs it.
#[test]
fn live_invocations_pin_the_lockfile_and_clear_build_overrides() {
    let tree = tree_command(&["-p", KERNEL, "--target", "all"]);
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

    let cleared: Vec<String> = tree
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

/// A cold-cache failure must name the preparation step, not only Cargo's error.
#[test]
fn offline_tree_failures_name_the_preparation_step() {
    let detail = "cargo tree exited with 101: failed to download `winapi-util v0.1.11`";
    let message = offline_recovery(detail);
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
    let metadata = live_metadata()?;
    assert_that!(metadata::package_names(&metadata), contains(eq(KERNEL)));
    assert_that!(metadata::kernel_dependency_names(&metadata), is_empty());
    let kernel_tree = live_tree(&[
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
        let metadata = metadata::parse_metadata(fixture).expect("the metadata fixture must parse");
        metadata::kernel_backend_dependencies(&metadata)
    } else {
        tree::backend_packages(fixture)
    };
    assert_that!(reported, contains(eq(backend)));
}

/// VO-2: every declared edge points from the facade towards its members.
#[test]
fn dependency_direction_holds() -> Result<(), Box<dyn Error>> {
    let metadata = live_metadata()?;
    assert_that!(metadata::direction_violations(&metadata), is_empty());
    assert_that!(
        metadata::facade_depends_normally_on(&metadata, KERNEL),
        eq(true)
    );
    assert_that!(
        metadata::facade_depends_normally_on(&metadata, MACROS),
        eq(true)
    );
    Ok(())
}

/// VO-2 control: a correctly directed workspace reports no violation.
#[test]
fn valid_workspace_reports_no_violation() {
    let metadata = metadata::parse_metadata(include_str!("fixtures/cargo/workspace-valid.json"))
        .expect("the valid workspace fixture must parse");
    assert_that!(metadata::direction_violations(&metadata), is_empty());
    assert_that!(
        metadata::facade_depends_normally_on(&metadata, KERNEL),
        eq(true)
    );
    assert_that!(
        metadata::facade_depends_normally_on(&metadata, MACROS),
        eq(true)
    );
}

/// VO-2: the kernel is never compiled for the host by a macro or build script.
#[test]
fn kernel_never_host_compiled() -> Result<(), Box<dyn Error>> {
    let metadata = live_metadata()?;
    let violations = metadata::direction_violations(&metadata);
    assert_that!(
        violations.join("; ").as_str(),
        not(contains_substring("build-depend"))
    );
    let macro_tree = live_tree(&["-p", MACROS, "--target", "all", "-e", "all"])?;
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
    let metadata = metadata::parse_metadata(fixture).expect("the metadata fixture must parse");
    let violations = metadata::direction_violations(&metadata);
    assert_that!(violations.join("; ").as_str(), contains_substring(expected));
}

/// VO-3: the native-only facade closure carries no verifier runtime.
#[test]
fn ordinary_profiles_exclude_verifiers() -> Result<(), Box<dyn Error>> {
    let native_tree = live_tree(&[
        "-p",
        FACADE,
        "--no-default-features",
        "--target",
        "all",
        "-e",
        "all",
    ])?;
    assert_that!(tree::verifier_packages(&native_tree), is_empty());
    Ok(())
}

/// VO-3 non-vacuity: a facade that reached a verifier must be reported.
#[test]
fn verifier_leaks_are_reported() {
    let reported = tree::verifier_packages(include_str!("fixtures/cargo/facade-reaches-vstd.tree"));
    assert_that!(reported, contains(eq("vstd")));
}

// VO-6 cases live in `workspace_kernel_boundary.rs`. The source-boundary
// subject is separate from the dependency-graph boundaries above, and keeping
// it here pushed this file past the repository's 400-line limit.
