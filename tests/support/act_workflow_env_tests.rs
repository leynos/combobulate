//! Mutations proving job environment, cache policy, and the Act route stay pinned.
//!
//! These clauses differ from the step and action mutations: nothing here names
//! a step. A job can keep every ordered step and action and still change what
//! it runs by editing its environment, the one place a cache write policy and
//! a Make profile are selected. They are grouped separately so the parent
//! corpus stays within the module length limit without weakening any case.

use serde_yaml::Value;

use super::super::{
    ACT_VALIDATION_WORKFLOW,
    CI_WORKFLOW,
    JOBS,
    Read,
    contracts_hold,
    document,
};

#[test]
fn workflow_environment_mutations_break_the_contract() {
    for (reason, changed) in [
        (
            "lost coverage LLVM",
            CI_WORKFLOW.replace(
                "CARGO_PROFILE_DEV_CODEGEN_BACKEND: llvm",
                "CARGO_PROFILE_DEV_CODEGEN_BACKEND: cranelift",
            ),
        ),
        (
            "disabled PR updates",
            CI_WORKFLOW.replace("[opened, synchronize, reopened]", "[closed]"),
        ),
        (
            "different job cwd",
            CI_WORKFLOW.replace(
                "  build-test:\n",
                "  build-test:\n    defaults:\n      run:\n        working-directory: /tmp\n",
            ),
        ),
        (
            "different lint cwd",
            CI_WORKFLOW.replace(
                "- name: Lint\n",
                "- name: Lint\n        working-directory: /tmp\n",
            ),
        ),
        (
            "different lint shell",
            CI_WORKFLOW.replace("- name: Lint\n", "- name: Lint\n        shell: sh\n"),
        ),
    ] {
        assert_ne!(
            changed, CI_WORKFLOW,
            "mutation must change source: {reason}"
        );
        assert!(
            !contracts_hold(&changed, ACT_VALIDATION_WORKFLOW),
            "contract must detect {reason}"
        );
    }
    cache_mutations_break_the_contract();
    act_route_mutations_break_the_contract();
}

/// DL-03's cache clause is checked as three separate halves.
///
/// The clause is only met when compilation reaches sccache, and the declaration
/// that achieves it has parts that fail silently. The action installs the
/// binary but sets no wrapper, and an absent wrapper is not itself an error
/// (a wrapper Cargo cannot execute would fail the build instead). The storage
/// backend is opt-in, so an unset backend compiles through to disk.
/// And saves are permitted only on `main`, which sccache expresses as a read
/// mode that defaults to `READ_WRITE`. Each failure is invisible in a green job,
/// so each gets its own mutation.
///
/// The save test keys on the ref rather than the event because both workflows
/// also declare `workflow_dispatch`, which may run from any branch. An event
/// test cannot decide the mode from the event when the same workflow declares
/// more than one trigger, so that regression has its own case.
fn cache_mutations_break_the_contract() {
    for (reason, key, replacement) in [
        ("lost compiler wrapper", "RUSTC_WRAPPER", Some("''")),
        (
            "lost cache backend",
            "SCCACHE_GHA_ENABLED",
            Some("\"false\""),
        ),
        (
            "pull requests save to the cache",
            "SCCACHE_GHA_RW_MODE",
            Some("true && 'READ_WRITE'"),
        ),
        ("cache write mode dropped", "SCCACHE_GHA_RW_MODE", None),
    ] {
        for job in JOBS.iter().map(|job| job.name) {
            let changed = rewrite_job_environment(CI_WORKFLOW, job, key, replacement)
                .unwrap_or_else(|error| panic!("{reason} in {job}: {error}"));
            assert_ne!(
                changed, CI_WORKFLOW,
                "mutation must change source: {reason} in {job}"
            );
            assert!(
                !contracts_hold(&changed, ACT_VALIDATION_WORKFLOW),
                "contract must detect {reason} in {job}: a job's cache declaration is its own"
            );
        }
    }
    whole_workflow_cache_mutations_break_the_contract();
}

/// Replaces or removes one cache key in exactly one job's environment.
///
/// `str.replace` would rewrite the same line in all three jobs at once, so the
/// cases above could only ever prove detection when every job drifted together.
/// A regression that drops a key from one `polars-*` job would still pass. This
/// mutates one job's mapping instead, which is what the committed contract
/// asserts: each job's environment is checked against its own declaration.
fn rewrite_job_environment(
    source: &str,
    job: &str,
    key: &str,
    replacement: Option<&str>,
) -> Read<String> {
    let mut changed = document(source)?;
    let environment = changed
        .get_mut("jobs")
        .and_then(|jobs| jobs.get_mut(job))
        .and_then(|job| job.get_mut("env"))
        .and_then(Value::as_mapping_mut)
        .ok_or_else(|| format!("the committed workflow must declare {job}'s environment"))?;
    match replacement {
        Some(value) => environment.insert(Value::String(key.into()), Value::String(value.into())),
        None => environment.remove(Value::String(key.into())),
    };
    Ok(serde_yaml::to_string(&changed)?)
}

/// The regressions that are only visible once every job drifts together.
///
/// A dispatch reading as read-only, and the wiring evidence disappearing,
/// describe the workflow as a whole rather than one job's environment, so these
/// stay whole-source mutations.
fn whole_workflow_cache_mutations_break_the_contract() {
    for (reason, changed) in [
        (
            // `workflow_dispatch` is declared beside `pull_request`, and an
            // event test cannot separate the two: a dispatch reports its own
            // event name, so this spelling makes every dispatch read-only,
            // `main` included. The mutation is named for the mode it actually
            // selects rather than for a save it cannot cause.
            "a dispatch is read-only even from main",
            CI_WORKFLOW.replace(
                "github.ref == 'refs/heads/main'",
                "github.event_name == 'push'",
            ),
        ),
        (
            "lost wiring evidence",
            CI_WORKFLOW.replace("          sccache --show-stats", "          echo wired"),
        ),
    ] {
        assert_ne!(
            changed, CI_WORKFLOW,
            "mutation must change source: {reason}"
        );
        assert!(
            !contracts_hold(&changed, ACT_VALIDATION_WORKFLOW),
            "contract must detect {reason}"
        );
    }
}

/// Act's manual route is contracted separately from the hosted job environment.
///
/// The manual workflow may not acquire a pull-request trigger, which would make
/// it repeat the full hosted validation, and its action revision may not drift
/// off the pin the hosted route records. Neither is a `build-test` environment
/// concern, so the cases live here rather than growing the loop above.
fn act_route_mutations_break_the_contract() {
    let enabled_pr_act = ACT_VALIDATION_WORKFLOW.replace(
        "  workflow_dispatch:",
        "  pull_request:\n  workflow_dispatch:",
    );
    assert_ne!(
        enabled_pr_act, ACT_VALIDATION_WORKFLOW,
        "PR Act mutation must change source"
    );
    assert!(
        !contracts_hold(CI_WORKFLOW, &enabled_pr_act),
        "Act must not repeat full validation on pull requests"
    );
    let wrong_manual_pin =
        ACT_VALIDATION_WORKFLOW.replace("47b337e4f230b591891656534d4ffad868131740", "main");
    assert_ne!(
        wrong_manual_pin, ACT_VALIDATION_WORKFLOW,
        "manual pin mutation must change source"
    );
    assert!(
        !contracts_hold(CI_WORKFLOW, &wrong_manual_pin),
        "manual Act's action revision must stay pinned"
    );
}
