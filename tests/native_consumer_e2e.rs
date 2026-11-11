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
};

use camino::Utf8Path;
use cap_std::{ambient_authority, fs_utf8::Dir};
use serde_json::Value;

/// Package-name prefixes that may never appear in a native-only consumer.
const FORBIDDEN_PREFIXES: &[&str] = &["polars", "glam", "kani", "verus", "vstd"];

/// The `insta` snapshot the native-only profile test asserts against.
///
/// The fixture is compared with the same artefact `tests/build_profiles.rs`
/// owns rather than a second copy, so the two routes cannot drift: `insta`
/// names a snapshot after the module path that asserts it, which is why the
/// file carries the `build_profiles__rendered__` prefix. The rendering tests
/// share one `rendered` module — one `cfg`-gated test per profile — so the
/// prefix no longer names the profile; the snapshot's own name does.
const NATIVE_ONLY_SNAPSHOT: &str = "tests/snapshots/build_profiles__rendered__native_only.snap";

/// The fixture's manifest, resolved from the repository root Cargo sets.
fn fixture_manifest() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tools/fixtures/native-consumer/Cargo.toml")
}

/// The committed snapshot the fixture's output must equal.
///
/// The read goes through a capability handle rather than `std::fs`, per the
/// repository's filesystem policy: the directory the test opens is the one
/// capability it holds, and the snapshot's path is relative to it. The
/// repository root is the ambient directory Cargo sets, and opening it here is
/// the one place a test names an ambient path.
fn native_only_snapshot() -> Result<String, Box<dyn Error>> {
    let root = Dir::open_ambient_dir(
        Utf8Path::new(env!("CARGO_MANIFEST_DIR")),
        ambient_authority(),
    )?;
    let contents = root.read_to_string(NATIVE_ONLY_SNAPSHOT)?;
    Ok(snapshot_body(&contents)?.to_owned())
}

/// Extracts the rendered value from an `insta` snapshot file.
///
/// `insta` writes a YAML header delimited by `---` lines before the value. Only
/// the body is compared, so the header's metadata changes cannot fail this
/// test; the `insta` snapshot test owns that format.
///
/// The split takes the first closing delimiter, not the last: the header opens
/// with `---`, closes with a second `---`, and everything after that closing
/// line is the body. A snapshot with no closing delimiter is a malformed file,
/// so it is reported as such rather than compared header and all, which would
/// fail with a message pointing at the fixture's output rather than the
/// snapshot's format. The body may itself contain `---`; that no longer
/// matters.
fn snapshot_body(contents: &str) -> Result<&str, Box<dyn Error>> {
    let (_, body) = contents
        .strip_prefix("---\n")
        .and_then(|header| header.split_once("\n---\n"))
        .ok_or("the snapshot must open and close its header with --- lines")?;
    Ok(body.trim_end())
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
/// No deadline is applied here: nextest gives this test its own process and
/// `.config/nextest.toml` owns the tier, which is why the repository's tests
/// start plain `Command` children (see "Test timeouts" in the developers'
/// guide). Cargo's own diagnostics are returned on failure, because a
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

/// Extracts the fixture's built binary from Cargo's JSON message stream.
///
/// The profile directory and the executable name both come from Cargo rather
/// than from a literal `debug/native-consumer` path. A literal would silently
/// stop matching if the fixture were renamed or built under a custom profile,
/// and it would omit the platform's `.exe` suffix. `compiler-artifact`
/// messages carry an `executable` for binaries, tests, and build scripts, so
/// the target kind is checked as well: only a `bin` is the fixture itself, and
/// its dependencies' library artefacts carry no executable at all.
fn built_binary(stream: &str) -> Result<PathBuf, Box<dyn Error>> {
    let executable = stream
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter(is_binary_artifact)
        .find_map(|message| {
            message
                .get("executable")
                .and_then(Value::as_str)
                .map(str::to_owned)
        })
        .ok_or("Cargo reported no executable for the fixture's binary target")?;
    Ok(PathBuf::from(executable))
}

/// Reports whether a Cargo JSON message describes the fixture's own binary.
///
/// `pointer` is used rather than `Value`'s index operator because a message
/// whose shape is not the one Cargo documents must simply stop matching, not
/// panic or reach for a key that only some artifact kinds carry.
fn is_binary_artifact(message: &Value) -> bool {
    let is_artifact = message.get("reason").and_then(Value::as_str) == Some("compiler-artifact");
    let is_bin = message
        .pointer("/target/kind")
        .and_then(Value::as_array)
        .is_some_and(|kinds| kinds.iter().any(|kind| kind.as_str() == Some("bin")));
    is_artifact && is_bin
}

/// Builds the fixture and returns its `cargo tree` output and rendered profile.
fn build_and_inspect() -> Result<(String, String), Box<dyn Error>> {
    let target_dir = Path::new(env!("CARGO_TARGET_TMPDIR")).join("native-consumer");
    let manifest = fixture_manifest()
        .to_str()
        .ok_or("the fixture manifest path is not UTF-8")?
        .to_owned();

    let build = run_cargo(
        fixture_cargo(
            &[
                "build",
                "--locked",
                "--message-format=json-render-diagnostics",
                "--manifest-path",
                &manifest,
            ],
            &target_dir,
        ),
        "building the native consumer",
    )?;
    let binary = built_binary(&build)?;
    let tree = run_cargo(
        fixture_cargo(
            &[
                "tree",
                "--locked",
                "--offline",
                "--prefix",
                "none",
                "--manifest-path",
                &manifest,
            ],
            &target_dir,
        ),
        "reading the native consumer's dependency graph",
    )?;
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
fn native_consumer_reaches_no_optional_dependency() {
    let (tree, _) = built();
    let reached = forbidden_packages(&tree);
    assert!(
        reached.is_empty(),
        "a native-only consumer must reach no backend or verifier, reached {reached:?}"
    );
    assert!(
        tree.contains("combobulate v0.1.0"),
        "the graph must contain the facade by path, got:\n{tree}"
    );
}

/// The consumer's printed line equals the committed native-only snapshot.
#[test]
fn native_consumer_output_matches_the_native_only_snapshot() {
    let (_, rendered) = built();
    let expected = committed_snapshot();
    assert_eq!(
        rendered, expected,
        "the consumer must print the native-only profile line"
    );
}

/// Runs the fallible build and reports its failure as a panic.
///
/// A `#[test]` that returns `Result` may contain no assertion, because the
/// workspace denies `clippy::panic_in_result_fn`. So the fallible part is
/// confined to this helper, which returns plain values, and the tests that
/// use it stay infallible and may assert. The Cargo diagnostics are carried
/// into the panic message because Cargo's own failure otherwise reads as an
/// unrelated assertion.
fn built() -> (String, String) {
    match build_and_inspect() {
        Ok(values) => values,
        Err(error) => panic!("the native consumer must build and run: {error}"),
    }
}

/// Reads the committed native-only snapshot, reporting failure as a panic.
fn committed_snapshot() -> String {
    match native_only_snapshot() {
        Ok(snapshot) => snapshot,
        Err(error) => panic!("the committed native-only snapshot must be readable: {error}"),
    }
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

/// The binary lookup rejects a stream that names no binary target.
#[test]
fn binary_lookup_reports_a_stream_without_a_binary() {
    let library_only = concat!(
        r#"{"reason":"compiler-artifact","target":{"kind":["lib"],"name":"combobulate"},"#,
        r#""executable":null}"#,
        "\n",
        "Compiling combobulate v0.1.0\n"
    );
    assert!(
        built_binary(library_only).is_err(),
        "a stream with no bin target must report the missing executable rather than fall back to \
         a guessed path"
    );
}

/// The binary lookup takes the binary target's own reported path.
#[test]
fn binary_lookup_uses_the_reported_executable() {
    let stream = concat!(
        r#"{"reason":"compiler-artifact","target":{"kind":["lib"],"name":"combobulate"}"#,
        ",\"executable\":null}\n",
        r#"{"reason":"compiler-artifact","target":{"kind":["bin"],"name":"native-consumer"},"#,
        r#""executable":"/tmp/target/debug/native-consumer"}"#,
        "\n"
    );
    let binary = built_binary(stream);
    assert_eq!(
        binary.as_deref().ok(),
        Some(Path::new("/tmp/target/debug/native-consumer")),
        "the reported bin artifact's executable is the path to run"
    );
}
