//! Shape and bump regressions shared by all action-reference consumers.

use rstest::rstest;
use serde_yaml::Value;

use super::{
    SETUP_RUST_PATH,
    is_sha_pinned,
    matches_pinned_action,
    repoint_action,
    repoint_all_actions,
};

/// Parses a workflow fixture, naming the fixture in every failure.
fn parsed(source: &str) -> Value {
    match serde_yaml::from_str(source) {
        Ok(document) => document,
        Err(error) => panic!("the workflow fixture must parse: {error}"),
    }
}

/// Reads one step's `uses` value.
fn step_uses<'a>(document: &'a Value, job: &str, index: usize) -> &'a str {
    let located = document
        .get("jobs")
        .and_then(|jobs| jobs.get(job))
        .and_then(|entry| entry.get("steps"))
        .and_then(Value::as_sequence)
        .and_then(|steps| steps.get(index))
        .and_then(|step| step.get("uses"))
        .and_then(Value::as_str);
    let Some(uses) = located else {
        panic!("{job} step {index} must declare a uses value");
    };
    uses
}

/// Reads one job's `with:` input that is itself named `uses`.
fn with_uses<'a>(document: &'a Value, job: &str, index: usize) -> &'a str {
    let located = document
        .get("jobs")
        .and_then(|jobs| jobs.get(job))
        .and_then(|entry| entry.get("steps"))
        .and_then(Value::as_sequence)
        .and_then(|steps| steps.get(index))
        .and_then(|step| step.get("with"))
        .and_then(|inputs| inputs.get("uses"))
        .and_then(Value::as_str);
    let Some(input) = located else {
        panic!("{job} step {index} must declare a uses input");
    };
    input
}

/// Reads a job-level `uses` value.
fn job_uses<'a>(document: &'a Value, job: &str) -> &'a str {
    let located = document
        .get("jobs")
        .and_then(|jobs| jobs.get(job))
        .and_then(|entry| entry.get("uses"))
        .and_then(Value::as_str);
    let Some(uses) = located else {
        panic!("{job} must declare a job-level uses value");
    };
    uses
}

/// The shared setup-rust path matches itself only when it stays pinned.
#[test]
fn setup_rust_path_names_a_pinned_action() {
    let pinned = format!("{SETUP_RUST_PATH}@{}", "a".repeat(40));
    assert!(
        matches_pinned_action(&pinned, SETUP_RUST_PATH),
        "the shared setup-rust reference must match its own path"
    );
    assert!(
        !matches_pinned_action(&format!("{SETUP_RUST_PATH}@main"), SETUP_RUST_PATH),
        "a floating setup-rust reference must not match"
    );
}

/// Only immutable lowercase hexadecimal references satisfy the pin policy.
#[rstest]
#[case("0".repeat(40), true)]
#[case("a".repeat(40), true)]
#[case("main".to_owned(), false)]
#[case("a".repeat(39), false)]
#[case("a".repeat(41), false)]
#[case("A".repeat(40), false)]
#[case("g".repeat(40), false)]
fn action_pin_requires_full_lowercase_sha(#[case] reference: String, #[case] expected: bool) {
    let uses = format!("owner/action@{reference}");
    assert_eq!(
        is_sha_pinned(&uses),
        expected,
        "reference shape contract: {reference}"
    );
    assert_eq!(
        matches_pinned_action(&uses, "owner/action"),
        expected,
        "path and reference contract"
    );
    assert!(
        !matches_pinned_action(&uses, "other/action"),
        "different actions must fail independently of pin shape"
    );
}

/// Mutation fixtures keep changing source after an immutable-reference bump.
#[rstest]
#[case("0".repeat(40))]
#[case("a".repeat(40))]
fn action_mutation_is_independent_of_current_pin(#[case] reference: String) {
    let source = format!("jobs:\n  one:\n    steps:\n      - uses: owner/action@{reference}\n");
    let changed =
        repoint_action(&source, "owner/action", "main").expect("the action fixture must exist");
    assert_eq!(
        step_uses(&parsed(&changed), "one", 0),
        "owner/action@main",
        "mutation must replace the current pin"
    );
}

/// Every call-site form a workflow can use takes the coordinated bump.
///
/// The fixture mixes block, quoted, folded, and flow values, including a flow
/// sequence that names two actions on one line. Only the references to the
/// bumped action may change.
#[test]
fn every_call_site_is_repointed() {
    let current = "a".repeat(40);
    let replacement = "b".repeat(40);
    let source = format!(
            "jobs:\n  block:\n    steps:\n      - uses: owner/action@{current}\n      - uses: \
             \"owner/action@{current}\"\n      - uses: 'owner/action@{current}'\n      - uses: \
             >-\n          owner/action@{current}\n  flow:\n    steps:\n      - {{uses: \
             owner/action@{current}}}\n      - {{uses: other/action@{current}, name: two}}\n      \
             - {{uses: owner/action@{current}, name: three}}\n  sequence:\n    steps: [{{uses: \
             owner/action@{current}}}, {{uses: other/action@{current}}}]\n"
        );
    let changed = repoint_all_actions(&source, "owner/action", &replacement)
        .expect("the action fixture must exist");
    let document = parsed(&changed);
    for index in 0..4 {
        assert_eq!(
            step_uses(&document, "block", index),
            format!("owner/action@{replacement}"),
            "block step {index} must take the new reference"
        );
    }
    assert_eq!(
        step_uses(&document, "flow", 0),
        format!("owner/action@{replacement}"),
        "a flow-mapping value must take the new reference"
    );
    assert_eq!(
        step_uses(&document, "flow", 1),
        format!("other/action@{current}"),
        "a different action on the same line must keep its reference"
    );
    assert_eq!(
        step_uses(&document, "flow", 2),
        format!("owner/action@{replacement}"),
        "a following value on the same line must take the new reference"
    );
    assert_eq!(
        step_uses(&document, "sequence", 0),
        format!("owner/action@{replacement}"),
        "a flow-sequence step must take the new reference"
    );
    assert_eq!(
        step_uses(&document, "sequence", 1),
        format!("other/action@{current}"),
        "a neighbouring flow-sequence step must keep its reference"
    );
}

/// A job-level reusable-workflow reference is a call site.
#[test]
fn job_level_uses_is_a_call_site() {
    let current = "a".repeat(40);
    let replacement = "b".repeat(40);
    let source = format!("jobs:\n  call:\n    uses: owner/action@{current}\n");
    let changed = repoint_action(&source, "owner/action", &replacement)
        .expect("the action fixture must exist");
    assert_eq!(
        job_uses(&parsed(&changed), "call"),
        format!("owner/action@{replacement}"),
        "a job-level uses value must be repointed"
    );
}

/// A `with:` input named `uses` is not a call site.
///
/// The input names the same action and an earlier reference than the real call
/// site, so a text scan that looked for the action path would move the input
/// and leave the step unchanged.
#[test]
fn with_inputs_are_not_call_sites() {
    let current = "a".repeat(40);
    let input = "c".repeat(40);
    let replacement = "b".repeat(40);
    let source = format!(
        "jobs:\n  one:\n    steps:\n      - name: input first\n        uses: \
         other/action@{input}\n        with:\n          uses: owner/action@{current}\n      - \
         uses: owner/action@{current}\n"
    );
    let changed = repoint_action(&source, "owner/action", &replacement)
        .expect("the action fixture must exist");
    let document = parsed(&changed);
    assert_eq!(
        with_uses(&document, "one", 0),
        format!("owner/action@{current}"),
        "a with input must keep its value"
    );
    assert_eq!(
        step_uses(&document, "one", 0),
        format!("other/action@{input}"),
        "an unrelated action must keep its reference"
    );
    assert_eq!(
        step_uses(&document, "one", 1),
        format!("owner/action@{replacement}"),
        "the single repoint must move the later call site"
    );
}

/// A single repoint moves only the first call site.
#[test]
fn single_repoint_moves_one_call_site() {
    let current = "a".repeat(40);
    let replacement = "b".repeat(40);
    let source = format!(
            "jobs:\n  one:\n    steps:\n      - uses: owner/action@{current}\n  two:\n    \
             steps:\n      - uses: owner/action@{current}\n"
        );
    let changed = repoint_action(&source, "owner/action", &replacement)
        .expect("the action fixture must exist");
    let document = parsed(&changed);
    assert_eq!(
        step_uses(&document, "one", 0),
        format!("owner/action@{replacement}"),
        "the first call site must change"
    );
    assert_eq!(
        step_uses(&document, "two", 0),
        format!("owner/action@{current}"),
        "the remaining call site must keep its reference"
    );
}

/// A fixture without the action reports no mutation.
#[test]
fn missing_action_reports_no_mutation() {
    let source = format!(
        "jobs:\n  one:\n    steps:\n      - uses: other/action@{}\n",
        "a".repeat(40)
    );
    assert!(
        repoint_action(&source, "owner/action", "main").is_none(),
        "a workflow that never names the action must report no mutation"
    );
    assert!(
        repoint_all_actions("jobs: [", "owner/action", "main").is_none(),
        "an unparsable workflow must report no mutation"
    );
}
