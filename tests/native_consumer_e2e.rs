//! End-to-end proof that the native-only profile serves an ordinary consumer.
//!
//! `tools/fixtures/native-consumer/` is a standalone binary crate, outside the
//! workspace, that depends on the facade by path with `default-features =
//! false`. This test builds it, runs it, reads its dependency graph, and
//! compares its output with the committed native-only snapshot. A profile that
//! only works inside its own workspace would pass every unit test and fail
//! here.

use std::{
    collections::BTreeSet,
    error::Error,
    path::{Path, PathBuf},
    process::Command,
    time::Duration,
};

/// Bounds the fixture's `cargo build`, which compiles the facade and kernel.
///
/// The fixture is small but shares the machine's compile admission queue with
/// every other agent, so the tier matches the repository's build tests rather
/// than the two-minute read tier.
const BUILD_DEADLINE: Duration = Duration::from_secs(900);

/// Bounds the dependency-graph read, which resolves but compiles nothing.
const READ_DEADLINE: Duration = Duration::from_secs(120);

/// Package-name prefixes that may never appear in a native-only consumer.
const FORBIDDEN_PREFIXES: &[&str] = &["polars", "glam", "kani", "verus", "vstd"];

/// The `insta` snapshot the native-only profile test asserts against.
///
/// The fixture is compared with the same artefact `tests/build_profiles.rs`
/// owns rather than a second copy, so the two routes cannot drift: `insta`
/// names a snapshot after the module path that asserts it, which is why the
/// file carries the `build_profiles__rendered_native__` prefix.
const NATIVE_ONLY_SNAPSHOT: &str =
    "tests/snapshots/build_profiles__rendered_native__native_only.snap";

/// Bounds the profile binary, which prints one line and returns.
const RUN_DEADLINE: Duration = Duration::from_secs(60);

/// The fixture's manifest, resolved from the repository root Cargo sets.
fn fixture_manifest() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tools/fixtures/native-consumer/Cargo.toml")
}

/// The committed snapshot the fixture's output must equal.
fn native_only_snapshot() -> Result<String, Box<dyn Error>> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(NATIVE_ONLY_SNAPSHOT);
    let contents = std::fs::read_to_string(&path)?;
    Ok(snapshot_body(&contents).to_owned())
}

/// Extracts the rendered value from an `insta` snapshot file.
///
/// `insta` writes a YAML header delimited by `---` lines before the value. Only
/// the body is compared, so the header's metadata changes cannot fail this
/// test; the `insta` snapshot test owns that format. The delimiter is searched
/// from the right because the header itself opens with it, and the body is a
/// single profile line containing no `---`.
fn snapshot_body(contents: &str) -> &str {
    contents
        .rsplit("\n---\n")
        .next()
        .unwrap_or(contents)
        .trim_end()
}

/// Builds a Cargo child with the caller's build selectors removed.
///
/// An inherited `RUSTFLAGS` would make the fixture depend on how the suite was
/// invoked, and an inherited `CARGO_TARGET_DIR` would put the binary somewhere
/// this test does not look.
fn fixture_cargo(arguments: &[&str], target_dir: &Path) -> Command {
    let mut command = Command::new(env!("CARGO"));
    command.args(arguments);
    command.current_dir(Path::new(env!("CARGO_MANIFEST_DIR")));
    command.env("CARGO_TARGET_DIR", target_dir);
    for name in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET"] {
        command.env_remove(name);
    }
    command
}

/// Runs a Cargo invocation, returning its standard output on success.
///
/// A caller-supplied deadline is not applied here: nextest gives this test its
/// own process and the repository's `.config/nextest.toml` owns the tier, so
/// the constants above document the expectation rather than duplicating the
/// mechanism. Cargo's own diagnostics are returned on failure, because a
/// resolution error otherwise reads as an unrelated assertion.
fn run_cargo(mut command: Command, description: &str) -> Result<String, Box<dyn Error>> {
    let output = command.output()?;
    if !output.status.success() {
        return Err(format!(
            "{description} failed: {}\n{}",
            output.status,
            String::from_utf8_lossy(&output.stderr)
        )
        .into());
    }
    Ok(String::from_utf8(output.stdout)?)
}

/// Builds the fixture and returns its `cargo tree` output and rendered profile.
fn build_and_inspect() -> Result<(String, String), Box<dyn Error>> {
    let target_dir = Path::new(env!("CARGO_TARGET_TMPDIR")).join("native-consumer");
    let manifest = fixture_manifest();
    let manifest = manifest
        .to_str()
        .ok_or("the fixture manifest path is not UTF-8")?;

    run_cargo(
        fixture_cargo(
            &["build", "--locked", "--manifest-path", manifest],
            &target_dir,
        ),
        "building the native consumer",
    )?;
    let tree = run_cargo(
        fixture_cargo(
            &[
                "tree",
                "--locked",
                "--offline",
                "--prefix",
                "none",
                "--manifest-path",
                manifest,
            ],
            &target_dir,
        ),
        "reading the native consumer's dependency graph",
    )?;
    let binary = target_dir.join("debug/native-consumer");
    let rendered = run_cargo(
        {
            let mut command = Command::new(&binary);
            command.env_remove("RUSTFLAGS");
            command.env_remove("CARGO_ENCODED_RUSTFLAGS");
            command
        },
        &format!("running {}", binary.display()),
    )?;
    Ok((tree, rendered.trim_end().to_owned()))
}

/// Reports every forbidden package the fixture's graph reached.
fn forbidden_packages(tree: &str) -> BTreeSet<String> {
    tree.lines()
        .filter_map(|line| line.split_whitespace().next())
        .filter(|name| {
            FORBIDDEN_PREFIXES
                .iter()
                .any(|prefix| name.starts_with(prefix))
        })
        .map(str::to_owned)
        .collect()
}

/// The consumer's graph carries no backend, no verifier, and no macro crate.
#[test]
fn native_consumer_reaches_no_optional_dependency() -> Result<(), Box<dyn Error>> {
    let (tree, _) = build_and_inspect()?;
    let reached = forbidden_packages(&tree);
    assert!(
        reached.is_empty(),
        "a native-only consumer must reach no backend or verifier, reached {reached:?}"
    );
    assert!(
        tree.contains("combobulate v0.1.0"),
        "the graph must contain the facade by path, got:\n{tree}"
    );
    Ok(())
}

/// The consumer's printed line equals the committed native-only snapshot.
#[test]
fn native_consumer_output_matches_the_native_only_snapshot() -> Result<(), Box<dyn Error>> {
    let (_, rendered) = build_and_inspect()?;
    let expected = native_only_snapshot()?;
    assert_eq!(
        rendered, expected,
        "the consumer must print the native-only profile line"
    );
    Ok(())
}

/// The build-selector removal is real, not a comment: the child sees no flags.
#[test]
fn fixture_cargo_removes_the_caller_build_selectors() {
    let command = fixture_cargo(&["--version"], Path::new("/tmp"));
    let cleared: Vec<String> = command
        .get_envs()
        .filter(|(_, value)| value.is_none())
        .map(|(name, _)| name.to_string_lossy().into_owned())
        .collect();
    for expected in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET"] {
        assert!(
            cleared.iter().any(|name| name == expected),
            "{expected} must not reach the fixture's Cargo child: {cleared:?}"
        );
    }
}

/// The stated tiers must stay ordered: the build outranks the reads.
#[test]
fn the_fixture_build_deadline_clears_a_shared_admission_queue() {
    assert!(
        BUILD_DEADLINE > READ_DEADLINE && READ_DEADLINE > RUN_DEADLINE,
        "the build compiles the facade, so its tier must exceed the read tier, which must exceed \
         the one-line run"
    );
}
