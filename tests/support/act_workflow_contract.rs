//! Contracts for the committed hosted and optional Act workflow routes.

use serde_yaml::Value;

/// Required jobs and the action revisions each one consumes.
#[path = "act_workflow_jobs.rs"]
mod jobs;
/// The mdtablefix version shared by the hosted and manual workflows.
#[path = "act_workflow_mdtablefix.rs"]
pub(crate) mod mdtablefix;
/// Exact conditions, environment, and source scripts for the known CI steps.
#[path = "act_workflow_policy.rs"]
mod policy;
/// Mutations proving the workflow clauses reject changed routes.
#[path = "act_workflow_contract_tests.rs"]
mod tests;

pub(super) use jobs::{
    ACTIONS,
    ANY_VALUE,
    JOBS,
    JobContract,
    action_input,
    action_inputs_match,
    job_steps,
    matches_action_revision,
    smoke_action_contracts,
    smoke_job_name,
    valid_actions,
};

use super::{
    ACT_VALIDATION_WORKFLOW,
    CI_WORKFLOW,
    WorkflowSource,
    action_ref,
    validate_mapping_keys,
};

/// Fallible workflow parsing and fixture execution result.
type Read<T> = Result<T, Box<dyn std::error::Error>>;

/// Parses the exact source while rejecting duplicate YAML mapping keys.
pub(super) fn document(source: &str) -> Read<Value> {
    validate_mapping_keys(&WorkflowSource(source))?;
    Ok(serde_yaml::from_str(source)?)
}

/// Reads a nested mapping key without making absent structure pass vacuously.
fn at<'a>(value: &'a Value, path: &[&str]) -> Option<&'a Value> {
    path.iter().try_fold(value, |node, key| {
        node.as_mapping()?.get(Value::String((*key).into()))
    })
}

/// Reads one textual YAML scalar; quoted booleans remain textual inputs.
pub(super) fn text<'a>(value: &'a Value, path: &[&str]) -> Option<&'a str> {
    at(value, path)?.as_str()
}

/// Finds the named step inside one job.
///
/// The step name alone is not unique across jobs: `Setup Rust`, `Lint`, and
/// `Verify Whitaker capability` all appear in more than one required job, so a
/// lookup without the job name would silently read whichever came first.
pub(super) fn step<'a>(document: &'a Value, job: &str, name: &str) -> Option<(usize, &'a Value)> {
    job_steps(document, job)?
        .iter()
        .enumerate()
        .find(|(_, item)| text(item, &["name"]) == Some(name))
}

/// Finds the named step in `build-test`, the job most callers read.
pub(super) fn build_test_step<'a>(document: &'a Value, name: &str) -> Option<(usize, &'a Value)> {
    step(document, "build-test", name)
}

/// Checks the independent hosted and manually requested event boundaries.
fn valid_triggers(ci: &Value, act: &Value) -> bool {
    valid_hosted_events(ci) && valid_manual_events(act)
}

/// Requires exactly the hosted PR and null manual-dispatch event entries.
fn valid_hosted_events(ci: &Value) -> bool {
    let Some(events) = at(ci, &["on"]).and_then(Value::as_mapping) else {
        return false;
    };
    events.len() == 2
        && at(ci, &["on", "workflow_dispatch"]).is_some_and(Value::is_null)
        && valid_pull_request_types(ci)
}

/// Pins the sole PR field and its ordered textual update-event types.
fn valid_pull_request_types(ci: &Value) -> bool {
    let Some(pr) = at(ci, &["on", "pull_request"]).and_then(Value::as_mapping) else {
        return false;
    };
    let Some(types) = at(ci, &["on", "pull_request", "types"]).and_then(Value::as_sequence) else {
        return false;
    };
    pr.len() == 1
        && types.iter().map(Value::as_str).eq([
            Some("opened"),
            Some("synchronize"),
            Some("reopened"),
        ])
}

/// Requires the optional full Act workflow to expose only null manual dispatch.
fn valid_manual_events(act: &Value) -> bool {
    let Some(events) = at(act, &["on"]).and_then(Value::as_mapping) else {
        return false;
    };
    events.len() == 1 && at(act, &["on", "workflow_dispatch"]).is_some_and(Value::is_null)
}

/// Checks each hosted job's path, steps, guards, and failure semantics.
fn valid_ci_route(ci: &Value) -> bool {
    valid_hosted_job_policy(ci)
        && JOBS.iter().all(|job| {
            job_steps(ci, job.name).is_some_and(|steps| {
                valid_hosted_environment(ci, job)
                    && valid_hosted_steps(job, steps)
                    && valid_ci_order(ci, job, steps)
                    && valid_ci_commands(ci, steps)
            })
        })
}

/// Requires exactly the three enabled hosted jobs and no shell or directory defaults.
fn valid_hosted_job_policy(ci: &Value) -> bool {
    let Some(jobs) = at(ci, &["jobs"]).and_then(Value::as_mapping) else {
        return false;
    };
    jobs.len() == JOBS.len()
        && JOBS.iter().all(|job| {
            jobs.contains_key(Value::String(job.name.into()))
                && at(ci, &["jobs", job.name, "if"]).is_none()
                && at(ci, &["jobs", job.name, "defaults"]).is_none()
        })
        && at(ci, &["defaults"]).is_none()
}

/// Requires exactly one job's declared environment assignments.
///
/// `GATE_PROFILE` is part of the contract because the Make targets read it:
/// without it each job would run both profiles inside one budget.
fn valid_hosted_environment(ci: &Value, job: &JobContract) -> bool {
    let Some(environment) = at(ci, &["jobs", job.name, "env"]).and_then(Value::as_mapping) else {
        return false;
    };
    environment.len() == job.env.len()
        && job
            .env
            .iter()
            .all(|(key, value)| text(ci, &["jobs", job.name, "env", key]) == Some(*value))
}

/// Requires every step in one job's fixed route to satisfy its named policy.
fn valid_hosted_steps(job: &JobContract, steps: &[Value]) -> bool {
    steps.len() == job.steps.len() && steps.iter().all(policy::known_step)
}

/// Pins the full manual Act step count, permission, and runner version.
fn valid_manual_job_policy(act: &Value, steps: &[Value]) -> bool {
    steps.len() == 8
        && text(act, &["jobs", "act-validation", "permissions", "contents"]) == Some("read")
        && text(act, &["jobs", "act-validation", "env", "ACT_VERSION"]) == Some("v0.2.89")
}

/// Pins provisioning order, read-only permissions, and unsuppressed failures.
fn valid_ci_order(ci: &Value, job: &JobContract, steps: &[Value]) -> bool {
    steps
        .iter()
        .zip(job.steps)
        .all(|(item, name)| text(item, &["name"]) == *name)
        && text(ci, &["jobs", job.name, "permissions", "contents"]) == Some("read")
        && steps
            .iter()
            .all(|item| at(item, &["continue-on-error"]).is_none())
}

/// Pins the command, cache, coverage, and Act recursion boundaries.
///
/// `Lint` appears in two jobs, so each job's lint step is checked against its
/// own profile rather than against a single shared expectations table.
fn valid_ci_commands(ci: &Value, steps: &[Value]) -> bool {
    text(
        build_test_step(ci, "Format").map_or(ci, |(_, item)| item),
        &["run"],
    ) == Some("make check-fmt")
        && valid_lint_step(ci, "build-test")
        && valid_lint_step(ci, "polars-lint")
        && text(
            build_test_step(ci, "Test under Act").map_or(ci, |(_, item)| item),
            &["run"],
        ) == Some("make test")
        && text(
            build_test_step(ci, "Test under Act").map_or(ci, |(_, item)| item),
            &["env", "WITH_ACT"],
        ) == Some("0")
        && text(
            build_test_step(ci, "Test under Act").map_or(ci, |(_, item)| item),
            &["if"],
        ) == Some("env.ACT == 'true'")
        && valid_test_step(ci)
        && valid_coverage_route(ci)
        && !steps
            .iter()
            .filter_map(|item| text(item, &["run"]))
            .any(|script| script.contains("WITH_ACT=1"))
}

/// Requires one job's lint step to build a private cold driver before `make lint`.
fn valid_lint_step(ci: &Value, job: &str) -> bool {
    step(ci, job, "Lint").is_some_and(|(_, item)| {
        text(item, &["run"]).is_some_and(|script| {
            script.trim_end() == "mkdir -p \"$DYLINT_DRIVER_PATH\"\nmake lint"
        }) && text(item, &["env", "DYLINT_DRIVER_PATH"])
            == Some("${{ runner.temp }}/combobulate-whitaker-driver")
    })
}

/// Requires the Polars test job to run the ordinary suite without nested Act.
fn valid_test_step(ci: &Value) -> bool {
    step(ci, "polars-test", "Test").is_some_and(|(_, item)| {
        text(item, &["run"]) == Some("make test")
            && text(item, &["env", "WITH_ACT"]) == Some("0")
            && at(item, &["if"]).is_none()
    })
}

/// Requires hosted coverage to use LLVM and remain skipped in Act.
fn valid_coverage_route(ci: &Value) -> bool {
    step(ci, "build-test", "Test and Measure Coverage").is_some_and(|(_, item)| {
        text(item, &["if"]) == Some("env.ACT != 'true'")
            && text(item, &["env", "CARGO_PROFILE_DEV_CODEGEN_BACKEND"]) == Some("llvm")
            && text(item, &["with", "publish-artefact"]) == Some("false")
            && text(item, &["with", "with-default-features"]) == Some("false")
            && text(item, &["with", "features"]) == Some("")
    })
}

/// Checks that the manual full Act job still reaches its supported Make route.
fn valid_manual_act_route(act: &Value) -> bool {
    let Some(steps) = at(act, &["jobs", "act-validation", "steps"]).and_then(Value::as_sequence)
    else {
        return false;
    };
    if !valid_manual_job_policy(act, steps) {
        return false;
    }
    if !valid_manual_action_prefix(steps) {
        return false;
    }
    let Some(index) = steps
        .iter()
        .position(|item| text(item, &["run"]) == Some("make test WITH_ACT=1"))
    else {
        return false;
    };
    index + 1 == steps.len()
        && steps
            .iter()
            .all(|item| at(item, &["continue-on-error"]).is_none())
}

/// Combines the independent static clauses for one production workflow pair.
pub(super) fn contracts_hold(ci_source: &str, act_source: &str) -> bool {
    let (Ok(ci), Ok(act)) = (document(ci_source), document(act_source)) else {
        return false;
    };
    valid_triggers(&ci, &act)
        && valid_actions(&ci)
        && valid_ci_route(&ci)
        && valid_manual_act_route(&act)
        && mdtablefix::versions_agree(&ci, &act)
}

/// Pins the three provisioning actions before the manual full Act command.
fn valid_manual_action_prefix(steps: &[Value]) -> bool {
    let expected_actions = [
        ("actions/checkout", "persist-credentials", "false"),
        (
            "leynos/shared-actions/.github/actions/install-mdtablefix",
            "version",
            ANY_VALUE,
        ),
        (
            "leynos/shared-actions/.github/actions/setup-rust@\
             47b337e4f230b591891656534d4ffad868131740",
            "rustflags",
            "",
        ),
    ];
    steps
        .iter()
        .take(3)
        .zip(expected_actions)
        .all(|(item, (revision, key, value))| {
            text(item, &["uses"]).is_some_and(|uses| matches_action_revision(uses, revision))
                && action_inputs_match(item, &[(key, value)])
        })
}
