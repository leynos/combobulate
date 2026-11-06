//! Executable contracts for sequential Make gates and Whitaker's flag boundary.

use std::process::Command;

/// Caller-environment assertions for the recorded gate invocations.
#[path = "support/make_gate_order_caller_environment.rs"]
mod caller_environment;
/// Expected Make stages and the executor calls they must produce.
#[path = "support/make_gate_order_commands.rs"]
mod commands;
/// Cold and failing paths for the dedicated Whitaker integration target.
#[path = "support/make_gate_order_driver_target.rs"]
mod driver_target;
/// Private command executors and their real Make harness.
#[path = "support/make_gate_order_probe.rs"]
mod probe;
/// NUL-framed invocation records shared by the test and its support modules.
#[path = "support/make_gate_order_records.rs"]
mod records;
/// NUL record parsing and repository configuration assertions.
#[path = "support/make_gate_order_whitaker.rs"]
mod whitaker;

use caller_environment::{
    assert_clean_caller,
    assert_coverage_contamination,
    assert_secret_values_redacted,
    assert_target_rustflags_isolated,
};
use commands::{
    ALL_STAGES,
    assert_all_commands,
    assert_interrogate_command,
    expected_stages_through,
};
use probe::{CallerEnvironment, GateProbe};

/// Proves the parallel composite invokes each required command in order.
#[test]
fn parallel_all_runs_each_gate_in_order() {
    let probe = GateProbe::new().expect("create private gate probes");
    let output = probe
        .run("all", None)
        .expect("execute parallel Make composite");
    assert_eq!(
        probe.stages().expect("read gate order"),
        ALL_STAGES
            .iter()
            .map(|stage| (*stage).to_owned())
            .collect::<Vec<_>>(),
        "make -j all must finish each gate before starting the next"
    );
    assert_all_commands(&probe.invocations().expect("parse complete gate records"))
        .expect("assert every expected Make gate command");
    assert!(
        output.status.success(),
        "all gates must pass: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

/// Confirms nested Make clears inherited Act mode before running the composite.
#[test]
fn inherited_with_act_does_not_reach_nested_make_all() {
    let test_binary = std::env::current_exe().expect("find current test executable");
    let output = Command::new(test_binary)
        .args([
            "--exact",
            "parallel_all_runs_each_gate_in_order",
            "--nocapture",
        ])
        .env("WITH_ACT", "1")
        .output()
        .expect("run exact gate-order test with Act enabled in its environment");
    assert!(
        output.status.success(),
        "the gate-order test must clear inherited WITH_ACT before nested Make: {}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

/// Proves a failing Python docstring gate stops `make lint` at that stage.
///
/// The `all` composite covers the same claim through its own test. This one
/// targets the `lint` target CI actually runs, so dropping `lint-python` from
/// it or swallowing its exit status fails here rather than passing silently.
#[test]
fn parallel_lint_stops_after_a_failing_interrogate_gate() {
    let probe = GateProbe::new().expect("create private gate probes");
    let output = probe
        .run("lint", Some("interrogate"))
        .expect("execute a failing parallel Make lint");
    assert!(
        !output.status.success(),
        "a failing Interrogate gate must fail make lint"
    );
    assert_eq!(
        probe.stages().expect("read lint stage order"),
        [
            "preflight",
            "prepare-dependencies",
            "prepare-ui-gate-dependencies",
            "prepare-ui-gate",
            "preflight",
            "doc",
            "clippy",
            "preflight",
            "whitaker",
            "interrogate"
        ],
        "nothing may run after a failing Interrogate gate"
    );
}

/// Checks Make stops at each representative failing stage without hiding errors.
#[test]
fn parallel_all_stops_after_the_first_failing_gate() {
    for failure in [
        "fmt",
        "gate-formatting",
        "markdown-formatting",
        "preflight",
        "clippy",
        "whitaker",
        "interrogate",
        "nextest",
        "doctest",
        "spelling",
    ] {
        let expected = expected_stages_through(failure);
        let probe = GateProbe::new().expect("create private gate probes");
        let output = probe
            .run("all", Some(failure))
            .expect("execute a failing parallel composite");
        assert!(
            !output.status.success(),
            "a failing {failure} gate must fail make all"
        );
        assert_eq!(
            probe.stages().expect("read gate order"),
            expected,
            "nothing may run after {failure}"
        );
    }
}

/// Proves caller contamination is cleared for Whitaker while Cargo reads repo config.
#[test]
fn parallel_lint_preserves_repository_route_for_clean_and_coverage_callers() {
    let probe = GateProbe::new().expect("create private gate probes");
    let contaminated = probe.run("lint", None).expect("execute parallel Make lint");
    let stages = probe.stages().expect("read lint stage order");
    let first_invocations = probe.invocations().expect("parse coverage caller records");
    let cold_config_invocations = records::parse_invocations(
        &probe
            .whitaker_records()
            .expect("read cold-cache Cargo config records"),
    )
    .expect("parse cold-cache Cargo config records");
    assert_interrogate_command(&first_invocations, 1)
        .expect("assert Interrogate invocation and Python source inventory");
    assert_contaminated_lint_run(
        &probe,
        &contaminated,
        &FirstLintRun {
            stages: &stages,
            invocations: &first_invocations,
            config_invocations: &cold_config_invocations,
        },
    );

    let clean = probe
        .run_with_environment("lint", None, CallerEnvironment::Clean)
        .expect("execute Make lint from a clean caller environment");
    let all_invocations = probe
        .invocations()
        .expect("parse clean and coverage records");
    let all_config_invocations = records::parse_invocations(
        &probe
            .whitaker_records()
            .expect("read cold- and warm-cache Cargo config records"),
    )
    .expect("parse cold- and warm-cache Cargo config records");
    assert_interrogate_command(&all_invocations, 2)
        .expect("assert both Interrogate invocations and Python source inventories");
    assert_clean_lint_run(
        &probe,
        &clean,
        &SecondLintRun {
            invocations: &all_invocations,
            config_invocations: &all_config_invocations,
        },
    );
    assert_secret_values_redacted(
        &probe.gate_records().expect("read NUL-framed gate records"),
        &probe
            .whitaker_records()
            .expect("read NUL-framed Whitaker records"),
    );
}

/// What the first lint run recorded, gathered for the assertions below.
struct FirstLintRun<'a> {
    /// Ordered stage names Make executed.
    stages: &'a [String],
    /// Every command the gate executors received.
    invocations: &'a [records::Invocation],
    /// The Cargo configuration Whitaker read on its cold cache.
    config_invocations: &'a [records::Invocation],
}

/// What the two lint runs recorded together, for the second run's assertions.
struct SecondLintRun<'a> {
    /// Every command both runs produced.
    invocations: &'a [records::Invocation],
    /// The Cargo configuration Whitaker read across both caches.
    config_invocations: &'a [records::Invocation],
}

/// Checks the first lint run, made from the coverage-contaminated caller.
///
/// Takes the recorded values rather than fetching them: the caller is a test
/// body, which may report a read failure with `expect`, while this helper is
/// outside one and must neither expect nor assert in a fallible signature.
fn assert_contaminated_lint_run(
    probe: &GateProbe,
    output: &std::process::Output,
    run: &FirstLintRun<'_>,
) {
    assert!(
        output.status.success(),
        "lint stages must pass: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        run.stages,
        [
            "preflight",
            "prepare-dependencies",
            "prepare-ui-gate-dependencies",
            "prepare-ui-gate",
            "preflight",
            "doc",
            "clippy",
            "preflight",
            "whitaker",
            "interrogate"
        ]
        .map(str::to_owned),
        "make -j lint must finish Whitaker before Interrogate"
    );
    assert_coverage_contamination(run.invocations);
    whitaker::assert_repository_route(
        run.invocations,
        run.config_invocations,
        &["cold"],
        probe.executable("dylint-drivers").as_str(),
    );
}

/// Checks the second lint run, made from a clean caller, against the first.
///
/// The accumulated records cover both runs, which is why the expected
/// Interrogate count is two.
fn assert_clean_lint_run(
    probe: &GateProbe,
    clean_output: &std::process::Output,
    run: &SecondLintRun<'_>,
) {
    assert!(
        clean_output.status.success(),
        "lint must pass with a clean caller environment: {}",
        String::from_utf8_lossy(&clean_output.stderr)
    );
    whitaker::assert_repository_route(
        run.invocations,
        run.config_invocations,
        &["cold", "warm"],
        probe.executable("dylint-drivers").as_str(),
    );
    assert_target_rustflags_isolated(run.invocations);
    assert_clean_caller(run.invocations);
}

/// Confirms no later lint stage runs after a Clippy failure.
#[test]
fn parallel_lint_never_starts_whitaker_after_clippy_failure() {
    let probe = GateProbe::new().expect("create private gate probes");
    let output = probe
        .run("lint", Some("clippy"))
        .expect("execute failing Make lint");
    assert!(
        !output.status.success(),
        "Clippy failure must fail make lint"
    );
    assert_eq!(
        probe.stages().expect("read lint stage order"),
        [
            "preflight",
            "prepare-dependencies",
            "prepare-ui-gate-dependencies",
            "prepare-ui-gate",
            "preflight",
            "doc",
            "clippy"
        ],
        "Whitaker must not start after Clippy fails"
    );
    assert!(
        probe.whitaker_records().is_err(),
        "Whitaker must not run after Clippy fails"
    );
}
