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
    let source = format!("uses: owner/action@{reference}\n");
    let changed =
        repoint_action(&source, "owner/action", "main").expect("the action fixture must exist");
    assert_eq!(
        changed, "uses: owner/action@main\n",
        "mutation must replace the current pin"
    );
    assert_ne!(
        changed, source,
        "each current-pin fixture must actually change"
    );
}

/// A coordinated bump must move every call site of the same action.
///
/// The quoted cases place the quoted value first, which is where an
/// over-greedy reference extraction would silently leave later unquoted sites
/// behind and consume the closing quote.
#[rstest]
#[case("", "")]
#[case("\"", "\"")]
#[case("'", "'")]
fn every_call_site_is_repointed(#[case] open: &str, #[case] close: &str) {
    let current = "a".repeat(40);
    let source = format!(
        "jobs:\n  one:\n    steps:\n      - uses: {open}owner/action@{current}{close}\n  \
         two:\n    steps:\n      - uses: owner/action@{current}\n"
    );
    let replacement = "b".repeat(40);
    let changed = repoint_all_actions(&source, "owner/action", &replacement)
        .expect("the action fixture must exist");
    assert!(
        !changed.contains(&current),
        "no call site may keep the previous reference: {changed}"
    );
    assert_eq!(
        changed
            .matches(&format!("owner/action@{replacement}"))
            .count(),
        2,
        "every call site must take the new reference: {changed}"
    );
    assert!(
        changed.contains(&format!("{open}owner/action@{replacement}{close}")),
        "the bump must preserve call-site quoting: {changed}"
    );
}

/// Flow mappings end a value at `}` or `,` with no intervening space.
///
/// Treating either delimiter as part of the reference consumes it and leaves
/// invalid YAML, so the bumped document must still parse.
#[test]
fn flow_mapping_call_sites_keep_their_delimiters() {
    let current = "a".repeat(40);
    let replacement = "b".repeat(40);
    let source = format!(
        "jobs:\n  one:\n    steps:\n      - {{uses: owner/action@{current}}}\n  two:\n    \
         steps:\n      - {{uses: owner/action@{current}, name: two}}\n"
    );
    let changed = repoint_all_actions(&source, "owner/action", &replacement)
        .expect("the action fixture must exist");
    assert!(
        !changed.contains(&current),
        "no call site may keep the previous reference: {changed}"
    );
    let document: Value =
        serde_yaml::from_str(&changed).expect("a bumped flow mapping must remain valid YAML");
    for job in ["one", "two"] {
        let uses = document
            .get("jobs")
            .and_then(|jobs| jobs.get(job))
            .and_then(|entry| entry.get("steps"))
            .and_then(Value::as_sequence)
            .and_then(|steps| steps.first())
            .and_then(|step| step.get("uses"))
            .and_then(Value::as_str)
            .expect("each flow-mapping step must keep its action reference");
        assert_eq!(
            uses,
            format!("owner/action@{replacement}"),
            "the bumped reference must stay intact in job {job}"
        );
    }
    assert!(
        changed.contains(&format!("owner/action@{replacement}}}")),
        "the closing brace must survive the bump: {changed}"
    );
    assert!(
        changed.contains(&format!("owner/action@{replacement},")),
        "the flow separator must survive the bump: {changed}"
    );
}

/// Comments and other scalars are not call sites.
///
/// A workflow that mentions the action in prose, or restates it in a `with:`
/// input, must keep those mentions when a fixture repoints the real steps.
#[test]
fn only_uses_values_are_repointed() {
    let current = "a".repeat(40);
    let comment_ref = "c".repeat(40);
    let replacement = "b".repeat(40);
    let source = format!(
        "# pinned at owner/action@{comment_ref}\njobs:\n  one:\n    steps:\n      - uses: \
         owner/action@{current}\n        with:\n          pinned: owner/action@{current}\n      - \
         uses: owner/action@{current}\n"
    );
    let changed = repoint_all_actions(&source, "owner/action", &replacement)
        .expect("the action fixture must exist");
    assert!(
        changed.contains(&comment_ref),
        "a comment reference must survive: {changed}"
    );
    assert!(
        changed.contains(&format!("pinned: owner/action@{current}")),
        "a non-uses scalar must survive: {changed}"
    );
    assert_eq!(
        changed
            .matches(&format!("uses: owner/action@{replacement}"))
            .count(),
        2,
        "both call sites must be repointed: {changed}"
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
    assert_eq!(
        changed
            .matches(&format!("uses: owner/action@{replacement}"))
            .count(),
        1,
        "only the first call site must change: {changed}"
    );
    assert_eq!(
        changed
            .matches(&format!("uses: owner/action@{current}"))
            .count(),
        1,
        "the remaining call site must keep its reference: {changed}"
    );
}
