//! Shared expectation checks for the Makefile command-contract tests.

use std::fmt::Display;

use camino::Utf8Path;

use super::{
    RUNNER_IMAGE,
    records::{EnvironmentValue, GitHubToken, Invocation},
};

/// Returns a test result value or reports its setup failure clearly.
pub(super) fn unwrap_test_result<T, E: Display>(result: Result<T, E>, context: &str) -> T {
    match result {
        Ok(value) => value,
        Err(error) => panic!("{context}: {error}"),
    }
}

/// Checks the arguments returned by the Nextest capability probe.
pub(super) fn assert_cargo_probe(invocation: &Invocation) {
    assert_eq!(
        invocation.executable, "cargo",
        "the feature probe must use the controlled Cargo executable"
    );
    assert_eq!(
        invocation.arguments,
        vec!["nextest", "--version"],
        "the harness must record the exact nextest probe arguments"
    );
}

/// Checks that build preflight receives no extra arguments.
pub(super) fn assert_preflight_invocation(invocation: &Invocation) {
    assert_eq!(
        invocation.executable, "check-build-tools",
        "the build prerequisite must use the controlled preflight executable"
    );
    assert!(
        invocation.arguments.is_empty(),
        "the build preflight must receive no unexpected arguments"
    );
}

/// Checks that repository Cargo commands retain the warnings and frontend flags.
pub(super) fn assert_development_flags_are_present(invocation: &Invocation) {
    let Some(EnvironmentValue::Value(rustflags)) = invocation.environment.get("RUSTFLAGS") else {
        panic!("repository Cargo commands must receive assigned RUSTFLAGS");
    };
    assert!(
        rustflags.split_whitespace().any(|flag| flag == "-D")
            && rustflags.split_whitespace().any(|flag| flag == "warnings"),
        "repository Cargo commands must preserve warnings-as-errors"
    );
    assert!(
        rustflags
            .split_whitespace()
            .any(|flag| flag == "-Zthreads=8"),
        "repository Cargo commands must preserve the parallel rustc frontend"
    );
}

/// Returns one recorded invocation or reports the missing test setup clearly.
pub(super) fn invocation_at<'a>(
    invocations: &'a [Invocation],
    index: usize,
    context: &str,
) -> &'a Invocation {
    let Some(invocation) = invocations.get(index) else {
        panic!("{context}");
    };
    invocation
}

/// Checks the two preparation calls that precede every recorded test command.
///
/// Both are `fetch` forms, and their manifest distinguishes them: the root
/// fetch takes no manifest, while the gate fetch names its separate workspace.
/// Neither carries `RUSTFLAGS`, because acquisition does not read the build
/// selectors.
///
/// The slice starts at the first fetch rather than at the start of the whole
/// record. `make` evaluates `TEST_CMD`'s `$(shell cargo nextest --version)` at
/// parse time, so on the Act route a probe precedes preparation; callers pass
/// the slice already offset past whatever precedes it.
pub(super) fn assert_preparation_invocations(preparation: &[Invocation]) {
    let expected: [(&str, &[&str]); 2] = [
        ("cargo", &["fetch", "--locked"]),
        (
            "cargo",
            &[
                "fetch",
                "--locked",
                "--manifest-path",
                "tools/gates/cardinality-ui/Cargo.toml",
            ],
        ),
    ];
    for (offset, (executable, arguments)) in expected.iter().enumerate() {
        let invocation = invocation_at(
            preparation,
            offset,
            "each dependency preparation call must be recorded",
        );
        assert_eq!(
            invocation.executable, *executable,
            "dependency preparation must use the controlled Cargo executable"
        );
        assert_eq!(
            invocation.arguments, *arguments,
            "dependency preparation must pass the pinned fetch arguments"
        );
    }
}

/// Checks the gate build sits between preparation and the repository tests.
///
/// The gate must be built before the suite runs: the root UI test only
/// locates and executes the binary, so a `--no-run` build here is what keeps
/// the nested `trybuild` compile out of a test body.
pub(super) fn assert_gate_build_invocation(invocation: &Invocation) {
    assert_eq!(
        invocation.executable, "cargo",
        "the gate build must use the controlled Cargo executable"
    );
    assert_eq!(
        invocation.arguments,
        vec![
            "test",
            "--no-run",
            "--manifest-path",
            "tools/gates/cardinality-ui/Cargo.toml",
            "--test",
            "cardinality_ui",
        ],
        "the gate must be built, not run, before the suite starts"
    );
}

/// Compares the recorded preparation, gate-build, test and doctest commands.
///
/// The slice covers everything the outer `make test` recipe runs after the
/// preflight, so a preparation or gate build that drifts out of position, or a
/// `trybuild` compile that reappears inside the test body, changes this list.
pub(super) fn assert_outer_invocations_are_ordered(invocations: &[Invocation]) {
    let actual = invocations
        .iter()
        .map(|invocation| {
            invocation
                .arguments
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();

    assert_eq!(
        actual,
        vec![
            vec!["fetch", "--locked"],
            vec![
                "fetch",
                "--locked",
                "--manifest-path",
                "tools/gates/cardinality-ui/Cargo.toml",
            ],
            vec![
                "test",
                "--no-run",
                "--manifest-path",
                "tools/gates/cardinality-ui/Cargo.toml",
                "--test",
                "cardinality_ui",
            ],
            vec!["test", "--all-targets", "--all-features"],
            vec!["test", "--doc", "--workspace", "--all-features"],
        ],
        "acquisition and the gate build must precede unit and documentation tests"
    );
}

/// Checks that every recorded executor ran from the repository root.
pub(super) fn assert_invocations_use_repository_directory(invocations: &[Invocation]) {
    let repository = Utf8Path::new(env!("CARGO_MANIFEST_DIR"));
    for invocation in invocations {
        assert_eq!(
            Utf8Path::new(&invocation.working_directory),
            repository,
            "{} must run from the repository root",
            invocation.executable
        );
    }
}

/// Checks the selected CI job and all Act arguments controlled by the Makefile.
pub(super) fn assert_act_invocation_matches(invocation: &Invocation, common_directory: &Utf8Path) {
    let common_mount = format!("--volume {common_directory}:{common_directory}:ro");
    let platform = format!("ubuntu-24.04={RUNNER_IMAGE}");

    assert_eq!(
        invocation.executable, "act",
        "the final command must use the controlled Act executable"
    );
    assert_eq!(
        invocation.arguments,
        vec![
            "pull_request",
            "--bind",
            "--container-options",
            common_mount.as_str(),
            "--secret",
            "GITHUB_TOKEN",
            "--env",
            "ACT=true",
            "--platform",
            platform.as_str(),
            "--workflows",
            ".github/workflows/ci.yml",
            "--job",
            "build-test",
        ],
        "Act must receive the exact expected workflow and runner arguments"
    );
}

/// Checks caller flags and selected Act settings at their intended child boundaries.
///
/// The indexes follow the measured `make test WITH_ACT=1` route: the parse-time
/// Nextest probe, the preflight, both fetches, the gate build, Nextest, the
/// doctests, the nested Make's own Nextest probe, and finally Act.
pub(super) fn assert_forwarded_environment(invocations: &[Invocation]) {
    assert_eq!(
        invocation_at(invocations, 8, "Act invocation must be recorded").github_token,
        GitHubToken::Present,
        "the configured token must reach the controlled Act process"
    );
    assert_eq!(
        invocation_at(invocations, 8, "Act invocation must be recorded")
            .environment
            .get("WITH_ACT"),
        Some(&EnvironmentValue::Value("1".to_owned())),
        "the controlled Act process must inherit the selected Make setting"
    );
    assert_eq!(
        invocation_at(invocations, 1, "build preflight must be recorded")
            .environment
            .get("RUSTFLAGS"),
        Some(&EnvironmentValue::Value("-C debuginfo=0".to_owned())),
        "supported caller flags must reach the child preflight unchanged"
    );
    for index in [5, 6] {
        let cargo_invocation =
            invocation_at(invocations, index, "Cargo test invocation must exist");
        assert_development_flags_are_present(cargo_invocation);
        assert!(
            matches!(cargo_invocation.environment.get("RUSTFLAGS"),
                Some(EnvironmentValue::Value(flags)) if flags.contains("-C debuginfo=0")),
            "repository Cargo commands must retain supported caller flags"
        );
    }
}
