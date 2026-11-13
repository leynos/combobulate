//! Repository-wide contract for GitHub Actions pin shape and consistency.

/// Shared action-path and immutable-reference checks.
#[path = "support/action_ref.rs"]
mod action_ref;
/// Discovery, pin collection, and declared-exception handling.
#[path = "support/workflow_action_pins.rs"]
mod pins;

use serde_yaml::Value;

/// A valid immutable reference used by fixtures.
const SHA_ONE: &str = "1111111111111111111111111111111111111111";
/// A second distinct immutable reference used by divergence fixtures.
const SHA_TWO: &str = "2222222222222222222222222222222222222222";

/// Builds a single-job workflow whose named steps consume the given actions.
fn workflow(actions: &[(&str, &str)]) -> String {
    let steps = actions
        .iter()
        .flat_map(|(name, action)| ["      - name: ", name, "\n        uses: ", action, "\n"])
        .collect::<String>();
    format!("jobs:\n  build:\n    steps:\n{steps}")
}

/// Parses named fixture workflow sources into the shape the contract reads.
fn documents(fixtures: &[(&str, String)]) -> Vec<(String, Value)> {
    fixtures
        .iter()
        .map(|(file, source)| {
            let document = match pins::parse_workflow(file, source) {
                Ok(document) => document,
                Err(error) => panic!("{file} fixture must parse: {error}"),
            };
            ((*file).to_owned(), document)
        })
        .collect()
}

/// The committed workflows must satisfy every pin rule and exception bound.
#[test]
fn committed_workflows_pin_every_action_to_one_revision() {
    let documents = match pins::read_workflows() {
        Ok(documents) => documents,
        Err(error) => panic!("committed workflows must be readable: {error}"),
    };
    let violations = pins::workflow_violations(&documents, pins::PIN_EXCEPTIONS);
    assert!(
        violations.is_empty(),
        "workflow action pin contract violations:\n{}",
        violations.join("\n")
    );
}

/// Equal pins pass, and a declared exception permits one known divergence.
#[test]
fn equal_pins_pass_and_a_declared_exception_permits_divergence() {
    let shared = format!("owner/setup@{SHA_ONE}");
    let excepted = format!("owner/setup@{SHA_TWO}");
    let agreeing = documents(&[
        ("ci.yml", workflow(&[("Build", shared.as_str())])),
        ("audit.yml", workflow(&[("Audit", shared.as_str())])),
    ]);
    assert!(
        pins::workflow_violations(&agreeing, &[]).is_empty(),
        "equal pins must satisfy the consistency contract"
    );
    let diverging = documents(&[
        ("ci.yml", workflow(&[("Build", shared.as_str())])),
        ("audit.yml", workflow(&[("Audit", excepted.as_str())])),
    ]);
    let exceptions = [pins::PinException {
        workflow: "audit.yml",
        path: "owner/setup",
        reason: "fixture exception",
    }];
    assert!(
        pins::workflow_violations(&diverging, &exceptions).is_empty(),
        "a declared exception must permit the audit pin to differ"
    );
    let violations = pins::workflow_violations(&diverging, &[]);
    assert_eq!(
        violations.len(),
        1,
        "without the exception the divergence must be reported: {violations:?}"
    );
    assert!(
        violations
            .first()
            .is_some_and(|violation| violation.contains("more than one revision")),
        "the violation must be the consistency check: {violations:?}"
    );
}

/// One action path resolving to two revisions must be reported in full.
#[test]
fn one_action_path_with_two_revisions_is_rejected() {
    let first = format!("owner/action@{SHA_ONE}");
    let second = format!("owner/action@{SHA_TWO}");
    let documents = documents(&[(
        "ci.yml",
        workflow(&[("First", first.as_str()), ("Second", second.as_str())]),
    )]);
    let violations = pins::workflow_violations(&documents, &[]);
    let [violation] = violations.as_slice() else {
        panic!("one divergent path must yield one violation: {violations:?}");
    };
    for expected in [
        "owner/action",
        SHA_ONE,
        SHA_TWO,
        "ci.yml:build.First",
        "ci.yml:build.Second",
    ] {
        assert!(
            violation.contains(expected),
            "diagnostic must mention {expected:?}: {violation}"
        );
    }
}

/// Floating step and job references must both fail the shape check.
#[test]
fn floating_references_are_rejected() {
    let documents = documents(&[
        ("ci.yml", workflow(&[("Floating", "owner/action@main")])),
        (
            "formal.yml",
            "jobs:\n  reuse:\n    uses: owner/repo/.github/workflows/build.yml@main\n".to_owned(),
        ),
    ]);
    let violations = pins::workflow_violations(&documents, &[]);
    assert_eq!(
        violations.len(),
        2,
        "each floating reference must be reported: {violations:?}"
    );
    assert!(
        violations
            .iter()
            .any(|violation| violation.contains("owner/action@main")
                && violation.contains("ci.yml:build.Floating")),
        "the step reference must be named: {violations:?}"
    );
    assert!(
        violations
            .iter()
            .any(|violation| violation.contains("build.yml@main")
                && violation.contains("formal.yml:reuse.job")),
        "the job-level reusable workflow must be named: {violations:?}"
    );
}

/// A folded scalar still parses into a reference the contract checks.
#[test]
fn folded_scalars_are_read_as_actions() {
    let source = concat!(
        "jobs:\n",
        "  build:\n",
        "    steps:\n",
        "      - name: Folded\n",
        "        uses: >-\n",
        "          owner/action@main\n",
    );
    let documents = documents(&[("ci.yml", source.to_owned())]);
    let violations = pins::workflow_violations(&documents, &[]);
    assert!(
        violations.first().is_some_and(|violation| {
            violation.contains("owner/action@main") && violation.contains("ci.yml:build.Folded")
        }),
        "a folded floating reference must be checked: {violations:?}"
    );
}

/// An exception permits a different pinned revision, not a mutable one.
#[test]
fn an_exception_does_not_excuse_an_unpinned_reference() {
    let documents = documents(&[("audit.yml", workflow(&[("Audit", "owner/setup@main")]))]);
    let exceptions = [pins::PinException {
        workflow: "audit.yml",
        path: "owner/setup",
        reason: "fixture exception",
    }];
    let violations = pins::workflow_violations(&documents, &exceptions);
    assert_eq!(
        violations.len(),
        1,
        "an excepted floating reference must still fail: {violations:?}"
    );
    assert!(
        violations
            .first()
            .is_some_and(|violation| violation.contains("not pinned")),
        "the violation must be the shape check: {violations:?}"
    );
}

/// An exception whose action left the workflow is stale and must fail.
#[test]
fn stale_exceptions_are_rejected() {
    let action = format!("owner/other@{SHA_ONE}");
    let documents = documents(&[("audit.yml", workflow(&[("Audit", action.as_str())]))]);
    let exceptions = [pins::PinException {
        workflow: "audit.yml",
        path: "owner/setup",
        reason: "fixture exception",
    }];
    let violations = pins::workflow_violations(&documents, &exceptions);
    assert_eq!(
        violations.len(),
        1,
        "a stale exception must yield one violation: {violations:?}"
    );
    assert!(
        violations.first().is_some_and(|violation| {
            violation.contains("stale pin exception")
                && violation.contains("audit.yml")
                && violation.contains("owner/setup")
        }),
        "the diagnostic must name the stale exception: {violations:?}"
    );
}

/// Local actions are owned here and are not subject to the pin rule.
#[test]
fn local_actions_are_not_pin_checked() {
    let documents = documents(&[("ci.yml", workflow(&[("Local", "./.github/actions/local")]))]);
    assert!(
        pins::workflow_violations(&documents, &[]).is_empty(),
        "a local composite action must not require a commit pin"
    );
}

/// Malformed or duplicate-key workflows must name the offending file.
#[test]
fn malformed_or_duplicate_workflows_name_the_file() {
    for (file, source) in [
        ("broken.yml", "jobs: [\n"),
        (
            "duplicate.yml",
            "jobs:\n  build:\n    steps: []\n  build:\n    steps: []\n",
        ),
    ] {
        match pins::parse_workflow(file, source) {
            Ok(_) => panic!("{file} must fail to parse"),
            Err(error) => assert!(
                error.to_string().contains(file),
                "diagnostic must name {file}: {error}"
            ),
        }
    }
}

/// Workflow discovery accepts committed YAML extensions regardless of case.
#[test]
fn workflow_names_accept_yaml_extensions_case_insensitively() {
    for (name, expected) in [
        ("ci.yml", true),
        ("ci.YAML", true),
        ("ci.yml.bak", false),
        ("README.md", false),
    ] {
        assert_eq!(
            pins::is_workflow_name(name),
            expected,
            "workflow extension contract: {name}"
        );
    }
}
