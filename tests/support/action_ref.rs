//! Shared action-path and immutable-reference checks for workflow contracts.

/// The shared action that provisions Rust in every workflow.
pub(crate) const SETUP_RUST_PATH: &str = "leynos/shared-actions/.github/actions/setup-rust";

/// Returns the action path before its trailing `@` reference, if any.
pub(crate) fn action_path(uses: &str) -> &str {
    uses.rsplit_once('@').map_or(uses, |(path, _)| path)
}

/// Requires a full lowercase hexadecimal commit reference, independently of its value.
pub(crate) fn is_sha_pinned(uses: &str) -> bool {
    uses.rsplit_once('@').is_some_and(|(_, reference)| {
        reference.len() == 40
            && reference
                .bytes()
                .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    })
}

/// Checks the expected action identity and an immutable commit-shaped reference.
pub(crate) fn matches_pinned_action(uses: &str, expected_path: &str) -> bool {
    action_path(uses) == expected_path && is_sha_pinned(uses)
}

/// Replaces the action's current source reference without coupling fixtures to its SHA.
pub(crate) fn repoint_action(source: &str, path: &str, replacement: &str) -> Option<String> {
    let prefix = format!("{path}@");
    let (_, suffix) = source.split_once(&prefix)?;
    let current_ref = suffix.split_whitespace().next()?;
    Some(source.replacen(
        &format!("{prefix}{current_ref}"),
        &format!("{prefix}{replacement}"),
        1,
    ))
}

#[cfg(test)]
mod tests {
    //! Shape and bump regressions shared by all action-reference consumers.

    use rstest::rstest;

    use super::{SETUP_RUST_PATH, is_sha_pinned, matches_pinned_action, repoint_action};

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
}
