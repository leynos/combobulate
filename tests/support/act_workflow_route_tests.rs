//! Direct regressions for the composed hosted CI job contract.

use std::error::Error;

use rstest::rstest;
use serde_yaml::Value;

use super::super::{
    super::{ACT_VALIDATION_WORKFLOW, CI_WORKFLOW},
    contracts_hold,
    document,
    valid_ci_route,
};

/// The committed route must satisfy both its direct boundary and composition.
#[test]
fn committed_ci_route_satisfies_its_contract() {
    let ci = committed_ci().expect("parse committed CI workflow");
    assert!(
        valid_ci_route(&ci),
        "the committed hosted route must satisfy its direct policy boundary"
    );
    assert!(
        contracts_hold(CI_WORKFLOW, ACT_VALIDATION_WORKFLOW),
        "the full hosted and manual workflow composition must remain valid"
    );
}

/// Missing, null, and wrongly typed route fields fail at their own boundary.
#[rstest]
#[case::missing_jobs(&["jobs"], None, "missing jobs")]
#[case::null_jobs(&["jobs"], Some("null"), "null jobs")]
#[case::scalar_jobs(&["jobs"], Some("build-test"), "scalar jobs")]
#[case::sequence_jobs(&["jobs"], Some("[]"), "sequence jobs")]
#[case::missing_job(&["jobs", "build-test"], None, "missing build-test job")]
#[case::null_job(&["jobs", "build-test"], Some("null"), "null build-test job")]
#[case::extra_job(&["jobs", "unexpected-job"], Some("{}"), "extra job")]
#[case::missing_steps(&["jobs", "build-test", "steps"], None, "missing steps")]
#[case::null_steps(&["jobs", "build-test", "steps"], Some("null"), "null steps")]
#[case::scalar_steps(&["jobs", "build-test", "steps"], Some("not a sequence"), "scalar steps")]
#[case::mapping_steps(&["jobs", "build-test", "steps"], Some("{}"), "mapping steps")]
#[case::missing_env(&["jobs", "build-test", "env"], None, "missing hosted environment")]
#[case::null_env(&["jobs", "build-test", "env"], Some("null"), "null hosted environment")]
#[case::scalar_env(&["jobs", "build-test", "env"], Some("not a mapping"), "scalar hosted environment")]
#[case::sequence_env(&["jobs", "build-test", "env"], Some("[]"), "sequence hosted environment")]
fn route_rejects_structural_mutations(
    #[case] path: &[&str],
    #[case] replacement: Option<&str>,
    #[case] reason: &str,
) {
    let original = committed_ci().expect("parse committed CI workflow");
    let replacement_value =
        replacement.map(|yaml| serde_yaml::from_str(yaml).expect("parse replacement"));
    rejects_route_mutation(&original, path, replacement_value, reason);
}

/// Exact environment values and cardinality remain fixed.
#[rstest]
#[case("CARGO_TERM_COLOR", None, "missing CARGO_TERM_COLOR")]
#[case("BUILD_PROFILE", None, "missing BUILD_PROFILE")]
#[case("EXTRA", Some(Value::String("unexpected".to_owned())), "extra environment")]
#[case("CARGO_TERM_COLOR", Some(Value::Bool(true)), "wrong CARGO_TERM_COLOR")]
#[case("BUILD_PROFILE", Some(Value::Number(1.into())), "wrong BUILD_PROFILE")]
fn route_rejects_environment_mutations(
    #[case] name: &str,
    #[case] replacement: Option<Value>,
    #[case] reason: &str,
) {
    let original = committed_ci().expect("parse committed CI workflow");
    rejects_route_mutation(
        &original,
        &["jobs", "build-test", "env", name],
        replacement,
        reason,
    );
}

/// Step count, known commands, and ordering remain fixed.
#[test]
fn route_rejects_step_mutations() {
    let original = committed_ci().expect("parse committed CI workflow");

    for (longer, reason) in [(false, "shorter steps"), (true, "longer steps")] {
        let mut changed = original.clone();
        let steps = route_steps_mut(&mut changed).expect("the committed steps must be a sequence");
        if longer {
            steps.push(Value::String("unexpected step".to_owned()));
        } else {
            steps.pop();
        }
        rejects_changed_route(&original, &changed, reason);
    }

    let mut unknown_step = original.clone();
    mutate_mapping_path(
        named_step_mut(&mut unknown_step, "Lint")
            .expect("the committed workflow must contain the Lint step"),
        &["run"],
        Some(Value::String("make unknown".to_owned())),
    )
    .expect("the Lint step must accept the unknown-command mutation");
    rejects_changed_route(&original, &unknown_step, "unknown step script");

    let mut changed_order = original.clone();
    route_steps_mut(&mut changed_order)
        .expect("the committed steps must be a sequence")
        .swap(0, 1);
    rejects_changed_route(&original, &changed_order, "changed step order");

    let mut changed_command = original.clone();
    mutate_mapping_path(
        named_step_mut(&mut changed_command, "Lint")
            .expect("the committed workflow must contain the Lint step"),
        &["run"],
        Some(Value::String("make typecheck".to_owned())),
    )
    .expect("the Lint step must accept the changed-command mutation");
    rejects_changed_route(&original, &changed_command, "changed lint command");
}

/// Disabled jobs, defaults, and suppressed failures remain rejected.
#[test]
fn route_rejects_execution_policy_mutations() {
    let original = committed_ci().expect("parse committed CI workflow");

    let mut disabled = original.clone();
    mutate_mapping_path(
        build_test_mut(&mut disabled).expect("the committed build-test job must be a mapping"),
        &["if"],
        Some(Value::String("false".into())),
    )
    .expect("the committed job must accept the condition mutation");
    rejects_changed_route(&original, &disabled, "disabled job");

    let mut defaults = original.clone();
    let defaults_value: Value =
        serde_yaml::from_str("{run: {shell: sh}}").expect("parse job defaults mutation");
    mutate_mapping_path(&mut defaults, &["defaults"], Some(defaults_value))
        .expect("the workflow root must accept a defaults mutation");
    rejects_changed_route(&original, &defaults, "job defaults");

    let mut suppressed = original.clone();
    mutate_mapping_path(
        named_step_mut(&mut suppressed, "Lint")
            .expect("the committed workflow must contain the Lint step"),
        &["continue-on-error"],
        Some(Value::Bool(true)),
    )
    .expect("the Lint step must accept the failure-suppression mutation");
    rejects_changed_route(&original, &suppressed, "suppressed failure");
}

fn committed_ci() -> Result<Value, Box<dyn Error>> { document(CI_WORKFLOW) }

fn mapping_value_mut<'a>(value: &'a mut Value, key: &str) -> Option<&'a mut Value> {
    value
        .as_mapping_mut()?
        .get_mut(Value::String(key.to_owned()))
}

fn build_test_mut(ci: &mut Value) -> Option<&mut Value> {
    mapping_value_mut(mapping_value_mut(ci, "jobs")?, "build-test")
}

fn route_steps_mut(ci: &mut Value) -> Option<&mut Vec<Value>> {
    mapping_value_mut(build_test_mut(ci)?, "steps")?.as_sequence_mut()
}

fn named_step_mut<'a>(ci: &'a mut Value, name: &str) -> Option<&'a mut Value> {
    route_steps_mut(ci)?
        .iter_mut()
        .find(|step| step.get("name").and_then(Value::as_str) == Some(name))
}

/// Mutates one mapping path; absence removes a key and explicit null stores null.
fn mutate_mapping_path(value: &mut Value, path: &[&str], replacement: Option<Value>) -> Option<()> {
    let (field_name, parents) = path.split_last()?;
    let parent = parents
        .iter()
        .try_fold(value, |parent, field| mapping_value_mut(parent, field))?;
    let mapping = parent.as_mapping_mut()?;
    let key = Value::String((*field_name).to_owned());
    if let Some(replacement_value) = replacement {
        let previous = mapping.insert(key, replacement_value.clone());
        assert_ne!(
            previous.as_ref(),
            Some(&replacement_value),
            "replacement must alter the fixture at {path:?}"
        );
    } else {
        assert!(
            mapping.remove(key).is_some(),
            "removal must alter the fixture at {path:?}"
        );
    }
    Some(())
}

/// Applies the sole map mutation seam before checking the complete route boundary.
fn rejects_route_mutation(
    original: &Value,
    path: &[&str],
    replacement: Option<Value>,
    reason: &str,
) {
    let mut changed = original.clone();
    assert!(
        mutate_mapping_path(&mut changed, path, replacement).is_some(),
        "the mutation path must resolve to a mapping field: {path:?}; {reason}"
    );
    rejects_changed_route(original, &changed, reason);
}

fn rejects_changed_route(original: &Value, changed: &Value, reason: &str) {
    assert_ne!(
        changed, original,
        "route mutation must change the parsed source: {reason}"
    );
    assert!(
        !valid_ci_route(changed),
        "hosted route must reject {reason}"
    );
}

/// Removing a field remains distinct from replacing it with YAML null.
#[rstest]
#[case::missing(None)]
#[case::explicit_null(Some(Value::Null))]
fn mutation_preserves_missing_and_null(#[case] replacement: Option<Value>) {
    let mut source: Value =
        serde_yaml::from_str("field: original").expect("parse mutation fixture");
    mutate_mapping_path(&mut source, &["field"], replacement.clone())
        .expect("the fixture must contain the selected mapping field");
    assert_eq!(
        source.get("field"),
        replacement.as_ref(),
        "mutation must preserve missing versus null"
    );
}

/// Mutation setup rejects no-op replacements before testing route rejection.
#[rstest]
#[case::same_value("field: original", Some(Value::String("original".to_owned())))]
#[case::missing_removal("{}", None)]
#[should_panic(expected = "must alter the fixture")]
fn unchanged_mutation_fails(#[case] yaml: &str, #[case] replacement: Option<Value>) {
    let mut source: Value = serde_yaml::from_str(yaml).expect("parse mutation fixture");
    mutate_mapping_path(&mut source, &["field"], replacement)
        .expect("the fixture must have a mapping at its root");
}

/// An invalid parent or empty path cannot silently become a route mutation.
#[rstest]
#[case::empty("field: original", &[])]
#[case::missing_parent("{}", &["missing", "field"])]
#[case::scalar_parent("parent: scalar", &["parent", "field"])]
#[case::scalar_root("scalar", &["field"])]
fn unresolved_mutation_path_leaves_fixture_unchanged(#[case] yaml: &str, #[case] path: &[&str]) {
    let original: Value = serde_yaml::from_str(yaml).expect("parse mutation fixture");
    let mut source = original.clone();
    assert_eq!(
        mutate_mapping_path(&mut source, path, Some(Value::Null)),
        None,
        "the path must resolve before a mutation can succeed"
    );
    assert_eq!(
        source, original,
        "an unresolved path must not alter the fixture"
    );
}
