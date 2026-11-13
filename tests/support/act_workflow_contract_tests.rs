//! Mutation tests for hosted workflow and manual Act route contracts.

/// Direct regressions for the composed hosted CI route.
#[path = "act_workflow_route_tests.rs"]
mod ci_route;
/// Job environment, cache write policy, and the manual Act route.
#[path = "act_workflow_env_tests.rs"]
mod environment;
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
///
/// The baseline is what makes the per-case check mean anything. `apply_mutation`
/// re-serialises the parsed document, and `serde_yaml` never reproduces the
/// committed bytes: comments, quoting, and layout all change. Comparing a
/// mutation's text against `CI_WORKFLOW` would therefore pass even for a no-op
/// helper, and comparing the parsed documents is what proves the helper
/// actually removed or inserted something. The baseline is also required to
/// satisfy the contract, because otherwise every case could pass for the wrong
/// reason: a round-trip that already broke the contract would make each
/// mutation's failure indistinguishable from serialization noise.
#[test]
fn polars_job_mutations_break_the_contract() {
    let baseline = apply_mutation(CI_WORKFLOW, "polars-lint", |_| Ok(()))
        .expect("the unmutated workflow must round-trip");
    assert!(
        contracts_hold(&baseline.source, ACT_VALIDATION_WORKFLOW),
        "an unmutated round-trip must still satisfy the contract"
    );
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
        let changed = apply_mutation(CI_WORKFLOW, job, mutate)
            .unwrap_or_else(|error| panic!("{reason}: {error}"));
        assert_ne!(
            changed.value, baseline.value,
            "mutation must change the document: {reason}"
        );
        assert!(
            !contracts_hold(&changed.source, ACT_VALIDATION_WORKFLOW),
            "contract must detect {reason}"
        );
    }
}

/// A mutated workflow, held both parsed and serialized.
///
/// [`contracts_hold`] reads source text, so each result is serialized for it.
/// The mutation check compares parsed values instead, because serialization
/// alone differs from the committed bytes with or without a mutation.
struct Mutated {
    /// The document as the mutation left it.
    value: Value,
    /// That document serialized, for the contract's text interface.
    source: String,
}

/// Applies one job-scoped mutation and keeps both of its representations.
fn apply_mutation(source: &str, job: &str, mutate: Mutation) -> Read<Mutated> {
    let mut changed = super::document(source)?;
    mutate(polars_job(&mut changed, job)?)?;
    Ok(Mutated {
        value: changed.clone(),
        source: serde_yaml::to_string(&changed)?,
    })
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

/// Repoints an action that the committed source must contain.
///
/// The helper lives outside a `#[test]` body, where the repository's strict
/// `expect_used` lint applies, so it panics with an explicit message instead.
fn repointed(source: &str, path: &str, reference: &str) -> String {
    let Some(changed) = super::super::action_ref::repoint_action(source, path, reference) else {
        panic!("the committed workflow must contain {path}")
    };
    changed
}

/// Immutable action bumps retain contracts without lockstep expected-SHA changes.
///
/// CI and the manual Act route receive the same synthetic reference, so this is
/// also the coordinated-bump case: agreement survives a bump that moves every
/// identity-bearing route together.
#[test]
fn immutable_action_bumps_preserve_workflow_contract() {
    let reference = "0".repeat(40);
    let mut ci = CI_WORKFLOW.to_owned();
    for (path, ..) in super::ACTIONS {
        ci = repointed(&ci, path, &reference);
    }
    let mut manual = ACT_VALIDATION_WORKFLOW.to_owned();
    for path in [
        "actions/checkout",
        "leynos/shared-actions/.github/actions/install-mdtablefix",
        super::super::action_ref::SETUP_RUST_PATH,
    ] {
        manual = repointed(&manual, path, &reference);
    }
    assert!(
        contracts_hold(&ci, &manual),
        "a coordinated immutable bump must preserve the workflow contracts"
    );
}

/// Setup-rust must agree across routes and remain a commit reference.
///
/// A one-sided bump or a floating manual reference changes behaviour, so the
/// contract must reject it even though the new value is itself SHA-shaped.
#[test]
fn setup_rust_divergence_breaks_the_contract() {
    let reference = "1".repeat(40);
    let hosted = repointed(
        CI_WORKFLOW,
        super::super::action_ref::SETUP_RUST_PATH,
        &reference,
    );
    let manual = repointed(
        ACT_VALIDATION_WORKFLOW,
        super::super::action_ref::SETUP_RUST_PATH,
        &reference,
    );
    let floating = repointed(
        ACT_VALIDATION_WORKFLOW,
        super::super::action_ref::SETUP_RUST_PATH,
        "main",
    );
    for (reason, ci, act) in [
        (
            "hosted setup-rust moved alone",
            hosted.as_str(),
            ACT_VALIDATION_WORKFLOW,
        ),
        (
            "manual setup-rust moved alone",
            CI_WORKFLOW,
            manual.as_str(),
        ),
        (
            "manual setup-rust is floating",
            CI_WORKFLOW,
            floating.as_str(),
        ),
    ] {
        assert!(
            !contracts_hold(ci, act),
            "contract must reject a setup-rust divergence: {reason}"
        );
    }
    assert_ne!(hosted, CI_WORKFLOW, "hosted mutation must change source");
    assert_ne!(
        manual, ACT_VALIDATION_WORKFLOW,
        "manual mutation must change source"
    );
    assert_ne!(
        floating, ACT_VALIDATION_WORKFLOW,
        "manual floating mutation must change source"
    );
}
