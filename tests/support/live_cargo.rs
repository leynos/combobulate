//! Live Cargo reads shared by the workspace boundary suites.
//!
//! Several suites ask the same question of Cargo — what does this package's
//! closure actually contain, right now, at the pinned lockfile — and each one
//! must ask it the same way. The routing below is that single answer: the
//! caller's build selectors are removed, so the child describes the workspace
//! rather than the shell that happened to invoke the suite, and both the
//! metadata and tree reads stay `--locked --offline` so a check cannot silently
//! pass against a re-resolved graph.
//!
//! Keeping the plumbing here rather than copying it per suite also keeps each
//! suite under the repository's file-length limit without narrowing what it
//! checks.

/// Dependency-direction predicates over Cargo's declared graph.
#[path = "workspace_metadata.rs"]
pub(super) mod metadata;
/// `cargo tree` parsing and dependency-prefix predicates.
#[path = "workspace_tree.rs"]
pub(super) mod tree;

use std::{
    error::Error,
    process::{Command, Output},
};

use metadata::Metadata;

/// Applies the caller-independent routing every live Cargo read requires.
///
/// The live checks must describe the workspace, not the caller's shell. An
/// inherited `CARGO_BUILD_TARGET` would silently resolve a different target
/// than the one under test, and inherited flags would make the recorded graph
/// depend on how the suite happened to be invoked. `CARGO_NET_OFFLINE` is set
/// explicitly so a cold cache reaches the recovery message instead of the
/// network, and so the setting is visible to the command-introspection
/// contract rather than inherited from whoever ran the suite.
pub(super) fn configure_cargo(command: &mut Command) {
    command
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .env("CARGO_NET_OFFLINE", "true");
    for name in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET"] {
        command.env_remove(name);
    }
}

/// Builds a Cargo child with the caller's build selectors removed.
pub(super) fn cargo_command(arguments: &[&str]) -> Command {
    let mut command = Command::new(env!("CARGO"));
    command.args(arguments);
    configure_cargo(&mut command);
    command
}

/// Builds the `cargo fetch` invocation that populates every target's packages.
///
/// The suite no longer runs this; `make prepare-dependencies` does. The
/// contract below still pins its shape, so the preparation step and the
/// offline checks cannot drift apart.
///
/// `--target` takes a target triple, not `all`, so it must not appear here:
/// a plain `cargo fetch --locked` already resolves the whole lockfile graph,
/// including the platform packages that `cargo tree --target all` reads.
pub(super) fn fetch_command() -> Command { cargo_command(&["fetch", "--locked"]) }

/// Returns the `cargo tree` argv for a package and edge selection.
///
/// The prefix is the one source of truth for both the introspected command in
/// the routing contract and the command the live check actually runs.
pub(super) fn tree_arguments<'a>(arguments: &'a [&'a str]) -> Vec<&'a str> {
    let mut full = vec!["tree", "--prefix", "none", "--locked", "--offline"];
    full.extend_from_slice(arguments);
    full
}

/// Builds the `cargo tree` invocation for a package and edge selection.
pub(super) fn tree_command(arguments: &[&str]) -> Command {
    cargo_command(&tree_arguments(arguments))
}

/// Explains how to recover when the offline tree cannot resolve a package.
///
/// The fetch that populates every target's packages is `make
/// prepare-dependencies`. It runs before this suite in every supported
/// route, because nextest gives each test its own process and a fetch inside
/// one would repeat per test. A direct `cargo test` bypasses that preparation,
/// so the failure has to say what to run instead of reporting only Cargo's
/// HTTP refusal.
pub(super) fn offline_recovery(detail: &str) -> String {
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
pub(super) fn run_read(arguments: &[&str]) -> Result<Output, Box<dyn Error>> {
    let mut command = Command::new(env!("CARGO"));
    command.args(arguments);
    configure_cargo(&mut command);
    Ok(command.output()?)
}

/// Runs `cargo metadata --no-deps` against the live workspace.
pub(super) fn live_metadata() -> Result<Metadata, Box<dyn Error>> {
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
pub(super) fn live_tree(arguments: &[&str]) -> Result<String, Box<dyn Error>> {
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
