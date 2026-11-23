//! Focused Make command-selection and NUL-record regression tests.

use camino::Utf8Path;

use super::{
    harness::{ExecutorFailure, MakeHarness, MakeOptions},
    records::{EnvironmentValue, GitHubToken, Invocation},
};

/// Checks Make selects Nextest when the controlled version probe succeeds.
///
/// The two gate profiles each contribute a Nextest run and a doctest run, in
/// that order, so the four assertions share one shape: the argument vector at a
/// known position must equal an expected one. Naming that shape once keeps the
/// case about the expected commands rather than about the reading of them.
#[test]
fn available_nextest_selects_the_nextest_run_branch() {
    let harness = MakeHarness::new().expect("create the Make harness");
    let output = harness
        .run_make_test(MakeOptions {
            nextest_available: true,
            ..MakeOptions::default()
        })
        .expect("run Make with the Nextest probe enabled");
    let invocations = harness.invocations().expect("read controlled invocations");

    assert!(
        output.status.success(),
        "the Nextest Make route must succeed"
    );
    let expected = [
        (
            0,
            vec!["nextest", "--version"],
            "the first Cargo call must probe Nextest",
        ),
        (
            5,
            vec!["fetch", "--locked"],
            "the test recipe must fetch, success-gated, before its first test run",
        ),
        (
            6,
            vec!["nextest", "run", "--all-targets", "--no-default-features"],
            "a successful Nextest probe must select its run command for the first gate profile",
        ),
        (
            7,
            vec!["test", "--doc", "--workspace", "--no-default-features"],
            "doctests must still follow Nextest",
        ),
        (
            8,
            vec!["nextest", "run", "--all-targets"],
            "the Polars-enabled profile must run in its own Nextest invocation",
        ),
        (
            9,
            vec!["test", "--doc", "--workspace"],
            "the Polars-enabled profile must run in its own doctest invocation",
        ),
    ];
    for (position, arguments, message) in expected {
        assert_arguments_at(&invocations, position, &arguments, message);
    }
}

/// Checks the plain `cargo test` branch fetches before its first test run.
///
/// With no Nextest the recipe falls back to `cargo test`, which no Nextest
/// setup script covers, so the recipe's own success-gated fetch is what keeps
/// the nested builds off a cold, resolving cache.
#[test]
fn unavailable_nextest_fetches_before_the_first_plain_cargo_test() {
    let harness = MakeHarness::new().expect("create the Make harness");
    let output = harness
        .run_make_test(MakeOptions::default())
        .expect("run Make with the Nextest probe disabled");
    let invocations = harness.invocations().expect("read controlled invocations");

    assert!(
        output.status.success(),
        "the plain Cargo route must succeed"
    );
    assert_arguments_at(
        &invocations,
        5,
        &["fetch", "--locked"],
        "the test recipe must fetch, success-gated, before its first test run",
    );
    assert_arguments_at(
        &invocations,
        6,
        &["test", "--all-targets", "--no-default-features"],
        "the plain Cargo test branch must run only after that fetch",
    );
}

/// Checks a failed fetch in the test recipe stops it before any test or Act run.
///
/// Fetches are numbered from 1: the first two belong to preparation and the
/// third is the test recipe's own, so failing it proves the recipe waits on it.
#[test]
fn failed_test_recipe_fetch_runs_no_test_and_no_act() {
    let harness = MakeHarness::new().expect("create the Make harness");
    let output = harness
        .run_make_test(MakeOptions {
            with_act: true,
            fail_fetch_invocation: Some(3),
            ..MakeOptions::default()
        })
        .expect("run Make with the recipe's fetch failing");
    let invocations = harness.invocations().expect("read controlled invocations");

    assert!(
        !output.status.success(),
        "a failed fetch in the test recipe must fail make"
    );
    assert!(
        invocations.iter().all(|call| call.executable != "act"),
        "Act must not start after a failed fetch"
    );
    let runs_tests = |call: &Invocation| {
        matches!(
            call.arguments.first().map(String::as_str),
            Some("test" | "nextest")
        ) && call.arguments.get(1).map(String::as_str) != Some("--version")
    };
    assert!(
        !invocations.iter().any(runs_tests),
        "no test command may run after the recipe's fetch failed"
    );
}

/// Asserts the Cargo call at `position` received exactly `expected` arguments.
fn assert_arguments_at(
    invocations: &[Invocation],
    position: usize,
    expected: &[&str],
    message: &str,
) {
    let actual = invocations.get(position).map(|call| {
        call.arguments
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>()
    });
    assert_eq!(actual, Some(expected.to_vec()), "{message}");
}

/// Checks a failing build preflight stops before repository commands or Act.
#[test]
fn failed_preflight_stops_before_cargo_tests_and_act() {
    let harness = MakeHarness::new().expect("create the Make harness");
    let output = harness
        .run_make_test(MakeOptions {
            with_act: true,
            failure: Some(ExecutorFailure::Preflight),
            ..MakeOptions::default()
        })
        .expect("run Make with a controlled preflight failure");
    let invocations = harness.invocations().expect("read controlled invocations");

    assert!(
        !output.status.success(),
        "preflight failure must fail make test"
    );
    assert_eq!(
        invocations
            .iter()
            .map(|call| call.executable.as_str())
            .collect::<Vec<_>>(),
        vec!["cargo", "check-build-tools"],
        "preflight failure must prevent Cargo test commands and nested Act"
    );
}

/// Checks a caller backend and linker reach preflight unchanged. The backend is
/// not itself rejected, so the failure is injected to stop the run there.
#[test]
fn caller_backend_and_linker_reach_preflight_unchanged() {
    let harness = MakeHarness::new().expect("create the Make harness");
    let output = harness
        .run_make_test(MakeOptions {
            with_act: true,
            failure: Some(ExecutorFailure::Preflight),
            caller_backend: Some("cranelift"),
            caller_linker: Some("clang"),
            ..MakeOptions::default()
        })
        .expect("run Make with a caller backend");
    let invocations = harness.invocations().expect("read controlled invocations");

    assert!(
        !output.status.success(),
        "the injected preflight failure must fail make test"
    );
    assert_eq!(
        invocations
            .iter()
            .map(|call| call.executable.as_str())
            .collect::<Vec<_>>(),
        vec!["cargo", "check-build-tools"],
        "the caller backend must not be silently removed or reach tests"
    );
    assert_eq!(
        invocations
            .get(1)
            .and_then(|call| call.environment.get("CARGO_PROFILE_DEV_CODEGEN_BACKEND")),
        Some(&EnvironmentValue::Value("cranelift".to_owned())),
        "preflight must observe the inherited backend"
    );
    assert_eq!(
        invocations.get(1).and_then(|call| call
            .environment
            .get("CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER")),
        Some(&EnvironmentValue::Value("clang".to_owned())),
        "preflight must observe the inherited non-wrapper coverage linker"
    );
}

/// Verifies NUL records round-trip empty, tabbed, and multiline values exactly.
#[test]
fn nul_records_preserve_unusual_arguments_and_environment_values() {
    let harness = MakeHarness::new().expect("create the Make harness");
    let arguments = ["", "tab\tinside", "line one\nline two"];
    let caller_flags = "-C\tdebuginfo=1\n-Zthreads=8";
    let invocations = harness
        .record_probe(&arguments, caller_flags)
        .expect("record unusual child arguments and environment");
    let invocation = invocations.first().expect("record-only call must exist");
    let expected_arguments = arguments
        .iter()
        .map(|argument| (*argument).to_owned())
        .collect::<Vec<_>>();

    assert_eq!(
        invocation.arguments, expected_arguments,
        "NUL framing must preserve empty, tabbed, and multiline arguments"
    );
    assert_eq!(
        invocation.environment.get("RUSTFLAGS"),
        Some(&EnvironmentValue::Value(caller_flags.to_owned())),
        "NUL framing must preserve tabs and newlines in environment values"
    );
    assert_eq!(
        invocation.environment.get("ACT"),
        Some(&EnvironmentValue::Empty),
        "the record must distinguish an empty value from an unset variable"
    );
    assert_eq!(
        invocation.environment.get("CARGO_ENCODED_RUSTFLAGS"),
        Some(&EnvironmentValue::Unset),
        "the record must retain unset state beside empty values"
    );
    assert_eq!(
        invocation.github_token,
        GitHubToken::Unset,
        "token recording must expose only presence state"
    );
    assert_eq!(
        Utf8Path::new(&invocation.working_directory),
        Utf8Path::new(env!("CARGO_MANIFEST_DIR")),
        "record-only execution must retain the requested working directory"
    );
}
