//! Shape and relationship regressions for the PEP 723 helper-pin reader.

use rstest::rstest;

use crate::{
    pin_tests::{fails_with, pin_source},
    script_pin::{ScriptDependency, script_dependency, script_matches_reference},
};

/// The REF path used by the relationship cases.
const REFERENCE: &str = "tools/rust-prover-tools/REF";

/// Builds a PEP 723 script whose dependency list is `dependencies`.
fn script_with(dependencies: &str) -> String {
    format!(
        "# /// script\n# requires-python = \">=3.14\"\n# dependencies = [{dependencies}]\n# ///\n"
    )
}

/// The helper's Git source and revision are read from embedded metadata.
#[test]
fn script_helper_source_is_read() {
    let revision = "a".repeat(40);
    let source = script_with(&format!(
        "\"tree-sitter==0.25.2\",\n#   \"rust-prover-tools @ git+https://example.test/tools.git@{revision}\""
    ));
    assert_eq!(
        script_dependency(pin_source("script.py", &source)),
        Ok(ScriptDependency {
            repository: "https://example.test/tools.git".to_owned(),
            revision,
        }),
        "the helper dependency must be read from the script block"
    );
}

/// A bare `#` line is empty metadata, and helper names normalize.
#[test]
fn bare_comment_lines_and_normalized_names_are_accepted() {
    let revision = "a".repeat(40);
    let source = format!(
        concat!(
            "# /// script\n#\n# dependencies = [\"rust_prover_tools @ git+",
            "https://example.test/tools.git@{revision}\"]\n# ///\n"
        ),
        revision = revision
    );
    assert_eq!(
        script_dependency(pin_source("script.py", &source)),
        Ok(ScriptDependency {
            repository: "https://example.test/tools.git".to_owned(),
            revision,
        }),
        "a bare comment line and a normalized helper name must be accepted"
    );
}

/// PEP 508 padding before the name must not hide the helper requirement.
#[test]
fn padded_helper_requirements_are_accepted() {
    let revision = "a".repeat(40);
    for padding in [" ", "\t", "  "] {
        let source = script_with(&format!(
            "\"{padding}rust-prover-tools @ git+https://example.test/tools.git@{revision}\""
        ));
        assert_eq!(
            script_dependency(pin_source("script.py", &source)),
            Ok(ScriptDependency {
                repository: "https://example.test/tools.git".to_owned(),
                revision: revision.clone(),
            }),
            "a helper padded with {padding:?} must still be read"
        );
    }
}

/// A malformed PEP 723 block names the rule it broke.
#[test]
fn script_blocks_are_rejected() {
    let rows = [
        ("missing block", "print('hi')\n".to_owned(), "script block"),
        (
            "unclosed block",
            "# /// script\n# dependencies = []\n".to_owned(),
            "close",
        ),
        (
            "two blocks",
            "# /// script\n# ///\n# /// script\n# ///\n".to_owned(),
            "exactly one",
        ),
        (
            "non-comment line",
            "# /// script\nrequires-python = \">=3.14\"\n# ///\n".to_owned(),
            "comment",
        ),
        (
            "missing metadata space",
            "# /// script\n#dependencies = []\n# ///\n".to_owned(),
            "comment",
        ),
        (
            "no dependencies",
            "# /// script\n# requires-python = \">=3.14\"\n# ///\n".to_owned(),
            "dependencies",
        ),
    ];
    for (description, source, fragment) in &rows {
        assert!(
            fails_with(script_dependency(pin_source("script.py", source)), fragment),
            "script with {description} must fail with {fragment:?}"
        );
    }
}

/// A malformed helper requirement names the rule it broke.
#[test]
fn helper_requirements_are_rejected() {
    let revision = "a".repeat(40);
    let helper = format!("rust-prover-tools @ git+https://example.test/tools.git@{revision}");
    let rows = [
        (
            "no helper",
            script_with("\"tree-sitter==0.25.2\""),
            "rust-prover-tools",
        ),
        (
            "two helpers",
            script_with(&format!("\"{helper}\",\n#   \"{helper}\"")),
            "exactly once",
        ),
        (
            "normalized duplicate",
            script_with(&format!(
                "\"{helper}\",\n#   \"rust_prover_tools @ git+https://example.test/tools.git@{revision}\""
            )),
            "exactly once",
        ),
        (
            "padded duplicate at another revision",
            script_with(&format!(
                "\"{helper}\",\n#   \" rust-prover-tools @ git+https://example.test/tools.git@{}\"",
                "b".repeat(40)
            )),
            "exactly once",
        ),
        (
            "pinned version",
            script_with("\"rust-prover-tools==1.0.0\""),
            "@ git+",
        ),
        (
            "uppercase revision",
            script_with(&format!(
                "\"rust-prover-tools @ git+https://example.test/tools.git@{}\"",
                "A".repeat(40)
            )),
            "40 lowercase",
        ),
        (
            "short revision",
            script_with(&format!(
                "\"rust-prover-tools @ git+https://example.test/tools.git@{}\"",
                "a".repeat(39)
            )),
            "40 lowercase",
        ),
        (
            "trailing revision material",
            script_with(&format!(
                "\"rust-prover-tools @ git+https://example.test/tools.git@{revision}x\""
            )),
            "40 lowercase",
        ),
    ];
    for (description, source, fragment) in &rows {
        assert!(
            fails_with(script_dependency(pin_source("script.py", source)), fragment),
            "script with {description} must fail with {fragment:?}"
        );
    }
}

/// A well-formed script must still name the REF source exactly.
#[rstest]
#[case::matching(
    "https://example.test/tools.git",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    true
)]
#[case::other_revision(
    "https://example.test/tools.git",
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    false
)]
#[case::other_repository(
    "https://example.test/elsewhere.git",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    false
)]
fn script_must_match_the_reference(
    #[case] repository: &str,
    #[case] revision: &str,
    #[case] is_expected_to_match: bool,
) {
    let script = script_with(&format!(
        "\"rust-prover-tools @ git+{repository}@{revision}\""
    ));
    let reference = format!(
        "repository: https://example.test/tools.git\nbranch: main\nref: {}\n",
        "a".repeat(40)
    );
    let outcome = script_matches_reference(
        pin_source("script.py", &script),
        pin_source(REFERENCE, &reference),
    );
    assert_eq!(
        outcome.is_ok(),
        is_expected_to_match,
        "script {repository}@{revision} against REF must match only when identical: {outcome:?}"
    );
}
