//! Mutation tests for hosted workflow and manual Act route contracts.

/// Direct regressions for the composed hosted CI route.
#[path = "act_workflow_route_tests.rs"]
mod ci_route;
/// Direct regression corpus for the independent event predicates.
#[path = "act_workflow_event_tests.rs"]
mod events;
/// Direct regression corpus for step conditions, scripts, and action interfaces.
#[path = "act_workflow_policy_tests.rs"]
mod step_policy;

use serde_yaml::Value;

use super::{ACT_VALIDATION_WORKFLOW, CI_WORKFLOW, Read, contracts_hold};

#[test]
fn hosted_gate_and_manual_act_have_distinct_routes() {
    assert!(
        contracts_hold(CI_WORKFLOW, ACT_VALIDATION_WORKFLOW),
        "the committed workflows must retain the hosted gate and manual Act route"
    );
}

#[test]
fn workflow_mutations_break_the_contract() {
    for (reason, changed) in [
        (
            "wrong Make goal",
            CI_WORKFLOW.replace("          make lint", "          make typecheck"),
        ),
        (
            "missing Act recursion guard",
            CI_WORKFLOW.replace("WITH_ACT: '0'", "WITH_ACT: '1'"),
        ),
        (
            "coverage guard removed",
            CI_WORKFLOW.replace("if: env.ACT != 'true'", "if: env.ACT == 'true'"),
        ),
        (
            "changed Whitaker action",
            super::super::action_ref::repoint_action(
                CI_WORKFLOW,
                "leynos/shared-actions/.github/actions/install-whitaker",
                "main",
            )
            .expect("the committed workflow must contain the Whitaker action"),
        ),
        (
            "changed Whitaker input",
            CI_WORKFLOW.replace("cranelift: 'true'", "cranelift: 'false'"),
        ),
        (
            "missing installer",
            CI_WORKFLOW.replacen("- name: Install Whitaker", "- name: Missing Whitaker", 1),
        ),
        (
            "suppressed failure",
            CI_WORKFLOW.replace(
                "- name: Lint\n",
                "- name: Lint\n        continue-on-error: true\n",
            ),
        ),
        (
            "unexpected executor",
            CI_WORKFLOW.replace("          make lint", "          custom-lint"),
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

#[test]
fn workflow_execution_mutations_break_the_contract() {
    for (reason, changed) in [
        (
            "disabled lint",
            CI_WORKFLOW.replace("- name: Lint\n", "- name: Lint\n        if: false\n"),
        ),
        (
            "disabled job",
            CI_WORKFLOW.replace("build-test:\n", "build-test:\n    if: false\n"),
        ),
        (
            "duplicate PR job",
            CI_WORKFLOW.replace(
                "jobs:\n",
                "jobs:\n  duplicate:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make \
                 test WITH_ACT=1\n",
            ),
        ),
        (
            "unknown shell executor",
            CI_WORKFLOW.replace("          make lint", "          cargo evil"),
        ),
        (
            "missing private cold cache",
            CI_WORKFLOW.replace(
                "DYLINT_DRIVER_PATH: ${{ runner.temp }}/combobulate-whitaker-driver",
                "DYLINT_DRIVER_PATH: ''",
            ),
        ),
        (
            "missing private cache creation",
            CI_WORKFLOW.replace(
                "          mkdir -p \"$DYLINT_DRIVER_PATH\"",
                "          echo no-cache",
            ),
        ),
        (
            "lint backend override",
            CI_WORKFLOW.replace(
                "DYLINT_DRIVER_PATH: ${{ runner.temp }}/combobulate-whitaker-driver",
                "DYLINT_DRIVER_PATH: ${{ runner.temp }}/combobulate-whitaker-driver\n          \
                 CARGO_PROFILE_DEV_CODEGEN_BACKEND: llvm",
            ),
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

/// One job-scoped mutation a contract case applies before re-checking.
///
/// The helpers are fallible rather than panicking: they live outside a
/// `#[test]` body, where the repository's strict `expect_used` lint applies,
/// and a missing structure is a test-fixture fault worth reporting.
type Mutation = fn(&mut Value) -> Read<()>;

/// Each required job is contracted on its own, so moving work between them fails.
///
/// Every mutation below touches only a `polars-*` job. A contract that resolved
/// its steps, actions, or profile from `build-test` alone would accept them.
#[test]
fn polars_job_mutations_break_the_contract() {
    for (reason, job, mutate) in [
        (
            "lost Polars profile selection",
            "polars-lint",
            clear_profile as Mutation,
        ),
        (
            "Polars job left on the native profile",
            "polars-test",
            native_profile,
        ),
        (
            "Polars lint job loses its Whitaker installer",
            "polars-lint",
            drop_installer,
        ),
        (
            "Polars test job gains a coverage measurement",
            "polars-test",
            add_coverage,
        ),
    ] {
        let source = apply_mutation(CI_WORKFLOW, job, mutate)
            .unwrap_or_else(|error| panic!("{reason}: {error}"));
        assert_ne!(source, CI_WORKFLOW, "mutation must change source: {reason}");
        assert!(
            !contracts_hold(&source, ACT_VALIDATION_WORKFLOW),
            "contract must detect {reason}"
        );
    }
}

/// Applies one job-scoped mutation and re-serializes the derived workflow.
fn apply_mutation(source: &str, job: &str, mutate: Mutation) -> Read<String> {
    let mut changed = super::document(source)?;
    mutate(polars_job(&mut changed, job)?)?;
    Ok(serde_yaml::to_string(&changed)?)
}

/// Selects one job mapping for a mutation scoped to that job alone.
fn polars_job<'a>(workflow: &'a mut Value, job: &str) -> Read<&'a mut Value> {
    workflow
        .get_mut("jobs")
        .and_then(|jobs| jobs.get_mut(job))
        .ok_or_else(|| format!("the committed workflow must declare the {job} job").into())
}

/// Removes the job environment key that selects its Make profile.
fn clear_profile(job: &mut Value) -> Read<()> {
    job.get_mut("env")
        .and_then(Value::as_mapping_mut)
        .ok_or("the job must declare its environment")?
        .remove("GATE_PROFILE");
    Ok(())
}

/// Points one job at the profile the other job measures.
fn native_profile(job: &mut Value) -> Read<()> {
    job.get_mut("env")
        .and_then(Value::as_mapping_mut)
        .ok_or("the job must declare its environment")?
        .insert("GATE_PROFILE".into(), "native-only".into());
    Ok(())
}

/// Removes the step that provisions the Whitaker dependency a lint job uses.
fn drop_installer(job: &mut Value) -> Read<()> {
    job.get_mut("steps")
        .and_then(Value::as_sequence_mut)
        .ok_or("the job must declare steps")?
        .retain(|step| {
            !step
                .get("uses")
                .and_then(Value::as_str)
                .is_some_and(|uses| uses.contains("install-whitaker"))
        });
    Ok(())
}

/// Gives a test-only job a measured coverage step the native job owns.
fn add_coverage(job: &mut Value) -> Read<()> {
    let steps = job
        .get_mut("steps")
        .and_then(Value::as_sequence_mut)
        .ok_or("the job must declare steps")?;
    let mut coverage: Value =
        serde_yaml::from_str("uses: leynos/shared-actions/.github/actions/generate-coverage@ok")?;
    coverage
        .as_mapping_mut()
        .ok_or("the coverage fixture must be a mapping")?
        .insert("if".into(), Value::String("env.ACT != 'true'".into()));
    steps.push(coverage);
    Ok(())
}

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

#[test]
fn ignores_inert_package_references() {
    for inert in [
        "# sudo apt-get install clang mold",
        "echo sudo apt-get install clang mold",
        "sudo apt-get install clang # mold",
        "sudo apt-get install other || echo clang mold",
        "sudo apt-get install clang mold\\ ",
    ] {
        assert!(
            !super::super::is_linker_install_command(inert),
            "inert package text must not satisfy installation: {inert}"
        );
    }
}

/// Immutable action bumps retain contracts without lockstep expected-SHA changes.
#[test]
fn immutable_action_bumps_preserve_workflow_contract() {
    let reference = "0".repeat(40);
    let mut ci = CI_WORKFLOW.to_owned();
    for (path, ..) in super::ACTIONS {
        if !path.contains('@') {
            ci = super::super::action_ref::repoint_action(&ci, path, &reference)
                .expect("every contracted action must exist in CI");
        }
    }
    let mut manual = ACT_VALIDATION_WORKFLOW.to_owned();
    for path in [
        "actions/checkout",
        "leynos/shared-actions/.github/actions/install-mdtablefix",
    ] {
        manual = super::super::action_ref::repoint_action(&manual, path, &reference)
            .expect("every manual provisioning action must exist");
    }
    assert!(
        contracts_hold(&ci, &manual),
        "new immutable refs must preserve workflow contracts and the setup-rust capability \
         exception"
    );
}
