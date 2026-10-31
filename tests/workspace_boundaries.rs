//! Workspace boundary contracts for the kernel, macro, and facade crates.
//!
//! The kernel must carry no backend and never be host-compiled, dependency
//! edges must point one way, ordinary profiles must exclude verifiers, and the
//! kernel must keep its `#![no_std]` allocation boundary. Each rule is a pure
//! predicate over Cargo's own output, exercised against the live workspace and
//! against canned fixtures that would otherwise let the rule pass vacuously.

use std::{error::Error, process::Command};

use googletest::prelude::*;
use rstest::rstest;

/// Dependency-direction predicates over Cargo's declared graph.
#[path = "support/workspace_metadata.rs"]
mod metadata;
/// Source checks for the kernel's `no_std` and allocation boundary.
#[path = "support/workspace_source.rs"]
mod source;
/// `cargo tree` parsing and dependency-prefix predicates.
#[path = "support/workspace_tree.rs"]
mod tree;

use metadata::{FACADE, KERNEL, MACROS, Metadata};

/// Runs `cargo metadata --no-deps` against the live workspace.
fn live_metadata() -> Result<Metadata, Box<dyn Error>> {
    let output = Command::new(env!("CARGO"))
        .args([
            "metadata",
            "--no-deps",
            "--format-version",
            "1",
            "--locked",
            "--offline",
        ])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()?;
    if !output.status.success() {
        return Err(format!(
            "cargo metadata must describe the workspace; exited with {}: {}",
            output.status,
            String::from_utf8_lossy(&output.stderr)
        )
        .into());
    }
    Ok(metadata::parse_metadata(&String::from_utf8(
        output.stdout,
    )?)?)
}

/// Runs `cargo tree` with the given package and edge selection.
fn live_tree(arguments: &[&str]) -> Result<String, Box<dyn Error>> {
    let output = Command::new(env!("CARGO"))
        .args(["tree", "--prefix", "none", "--locked", "--offline"])
        .args(arguments)
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()?;
    if !output.status.success() {
        return Err(format!(
            "cargo tree {arguments:?} must resolve; exited with {}: {}",
            output.status,
            String::from_utf8_lossy(&output.stderr)
        )
        .into());
    }
    Ok(String::from_utf8(output.stdout)?)
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

/// VO-6: the kernel keeps `#![no_std]` and its core-only lint boundary.
#[test]
fn kernel_keeps_the_no_std_boundary() -> Result<(), Box<dyn Error>> {
    let source = source::kernel_source()?;
    assert_that!(source::kernel_source_violations(&source), is_empty());
    Ok(())
}

/// VO-6 non-vacuity: comments and literals cannot stand in for attributes.
#[rstest]
#[case::line_comment(concat!(
    "// The crate is #![no_std] and denies clippy::std_instead_of_core.\n",
    "//! The alloc lint is clippy::alloc_instead_of_core.\n",
    "#![allow(dead_code)]\n"
))]
#[case::block_comment(concat!(
    "/*\n#![no_std]\nclippy::std_instead_of_core\n",
    "clippy::alloc_instead_of_core\n*/\n",
    "#![allow(dead_code)]\n"
))]
#[case::string_literals(concat!(
    "const DOC: &str = \"#![no_std] extern crate alloc\";\n",
    "const RAW: &str = r#\"clippy::std_instead_of_core\"#;\n",
    "const NESTED: &str = r##\"clippy::alloc_instead_of_core\"##;\n"
))]
fn comments_and_literals_cannot_satisfy_the_kernel_boundary(#[case] source: &str) {
    let violations = source::kernel_source_violations(source).join("; ");
    for expected in [
        "must declare #![no_std]",
        "must deny clippy::std_instead_of_core",
        "must deny clippy::alloc_instead_of_core",
    ] {
        assert_that!(violations.as_str(), contains_substring(expected));
    }
    assert_that!(
        violations.as_str(),
        not(contains_substring("must not contain extern crate alloc"))
    );
}

/// VO-6 non-vacuity: a real allocation declaration is still reported.
#[rstest]
#[case::plain("extern crate alloc;")]
#[case::interleaved_comment("extern /* keep */ crate alloc;")]
fn real_alloc_declarations_are_reported(#[case] source: &str) {
    assert_that!(
        source::kernel_source_violations(source).join("; ").as_str(),
        contains_substring("must not contain extern crate alloc")
    );
}

/// VO-6 control: the real attribute set passes the code-only check.
#[test]
fn kernel_boundary_accepts_the_real_attribute_set() {
    let source = concat!(
        "//! Kernel crate root that mentions #![no_std] in prose.\n",
        "#![no_std]\n",
        "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    );
    assert_that!(source::kernel_source_violations(source), is_empty());
}
