//! Workspace boundary contracts for the kernel, macro, and facade crates.
//!
//! The kernel must carry no backend and never be host-compiled, dependency
//! edges must point one way, ordinary profiles must exclude verifiers, and the
//! kernel must keep its `#![no_std]` allocation boundary. Each rule is a pure
//! predicate over Cargo's own output, exercised against the live workspace and
//! against canned fixtures that would otherwise let the rule pass vacuously.

use std::{error::Error, process::Command, sync::OnceLock};

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

/// Builds a Cargo child with the caller's build selectors removed.
///
/// The live checks must describe the workspace, not the caller's shell. An
/// inherited `CARGO_BUILD_TARGET` would silently resolve a different target
/// than the one under test, and inherited flags would make the recorded graph
/// depend on how the suite happened to be invoked.
fn cargo_command(arguments: &[&str]) -> Command {
    let mut command = Command::new(env!("CARGO"));
    command
        .args(arguments)
        .current_dir(env!("CARGO_MANIFEST_DIR"));
    for name in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET"] {
        command.env_remove(name);
    }
    command
}

/// Builds the `cargo fetch` invocation that populates every target's packages.
fn fetch_command() -> Command { cargo_command(&["fetch", "--locked"]) }

/// Builds the `cargo tree` invocation for a package and edge selection.
fn tree_command(arguments: &[&str]) -> Command {
    let mut full = vec!["tree", "--prefix", "none", "--locked", "--offline"];
    full.extend_from_slice(arguments);
    cargo_command(&full)
}

/// Fetches every locked dependency once so the offline checks can resolve.
///
/// `cargo tree --target all` resolves platform-specific dependencies that a
/// host build never downloads. Without the fetch, the check would depend on
/// cache warmth rather than on the workspace, and a cold runner would fail.
fn fetch_locked_dependencies_once() -> Result<(), Box<dyn Error>> {
    static FETCH: OnceLock<Result<(), String>> = OnceLock::new();
    FETCH
        .get_or_init(|| match fetch_command().output() {
            Ok(output) if output.status.success() => Ok(()),
            Ok(output) => Err(format!(
                "cargo fetch --locked must populate every target; exited with {}: {}",
                output.status,
                String::from_utf8_lossy(&output.stderr)
            )),
            Err(error) => Err(format!("cargo fetch --locked could not start: {error}")),
        })
        .clone()
        .map_err(Into::into)
}

/// Runs `cargo metadata --no-deps` against the live workspace.
fn live_metadata() -> Result<Metadata, Box<dyn Error>> {
    let output = cargo_command(&[
        "metadata",
        "--no-deps",
        "--format-version",
        "1",
        "--locked",
        "--offline",
    ])
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
    fetch_locked_dependencies_once()?;
    let output = tree_command(arguments).output()?;
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

/// Contract: the live checks stay lockfile-pinned, offline, and flag-neutral.
///
/// The fetch runs first so the offline tree calls resolve every target, and no
/// caller build selector survives into either child.
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

    let fetch_arguments: Vec<String> = fetch_command()
        .get_args()
        .map(|argument| argument.to_string_lossy().into_owned())
        .collect();
    assert!(
        fetch_arguments
            .iter()
            .any(|argument| argument == "--locked"),
        "the dependency fetch must pin the lockfile: {fetch_arguments:?}"
    );

    for command in [tree, fetch_command()] {
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

/// VO-6 non-vacuity: a lint name must sit in an effective `deny`.
#[rstest]
#[case::allow_only(
    concat!(
        "#![no_std]\n",
        "#![allow(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    ),
    "the kernel crate root must deny clippy::std_instead_of_core; the kernel crate root must deny clippy::alloc_instead_of_core"
)]
#[case::warn_only(
    concat!(
        "#![no_std]\n",
        "#![warn(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    ),
    "the kernel crate root must deny clippy::std_instead_of_core; the kernel crate root must deny clippy::alloc_instead_of_core"
)]
#[case::deny_then_allow(
    concat!(
        "#![no_std]\n",
        "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n",
        "#![allow(clippy::std_instead_of_core)]\n"
    ),
    "the kernel crate root must deny clippy::std_instead_of_core"
)]
fn lint_mentions_outside_a_deny_are_reported(#[case] source: &str, #[case] expected: &str) {
    assert_eq!(
        source::kernel_source_violations(source).join("; "),
        expected,
        "only a final deny or forbid may satisfy the kernel lint boundary"
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

/// VO-6 control: a content quote inside a raw string must not hide the root.
///
/// `r#"x""#` holds a bare `"` before its terminator. A scanner that consumed
/// that quote while probing the terminator would swallow the crate attributes
/// and report a valid kernel as missing its boundary.
#[test]
fn raw_string_content_quotes_do_not_hide_the_kernel_attributes() {
    let source = concat!(
        "#![doc = r#\"x\"\"#]\n",
        "#![no_std]\n",
        "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    );
    assert_that!(
        source::kernel_source_violations(source),
        is_empty(),
        "the crate root after a raw-string content quote must still be read"
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
