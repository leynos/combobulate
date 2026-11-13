//! Shape and relationship regressions for the prover release-pin readers.

use rstest::rstest;

use crate::{
    pins::{
        PinError,
        kani_version,
        pinned_ref,
        pinned_repository,
        verus_checksum_row,
        verus_version,
    },
    script_pin::{ScriptDependency, script_dependency, script_matches_reference},
};

/// One repository-relative path used by every diagnostic in these cases.
const FILE: &str = "pin";

/// The REF path used by the relationship cases.
const REFERENCE: &str = "tools/rust-prover-tools/REF";

/// A synthetic digest keeps checksum cases independent of the live release.
const DIGEST: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

/// Reports whether a reader failed with a diagnostic naming `fragment`.
fn fails_with<T>(result: Result<T, PinError>, fragment: &str) -> bool {
    result
        .err()
        .is_some_and(|error| error.to_string().contains(fragment))
}

/// Builds a PEP 723 script whose dependency list is `dependencies`.
fn script_with(dependencies: &str) -> String {
    format!(
        "# /// script\n# requires-python = \">=3.14\"\n# dependencies = [{dependencies}]\n# ///\n"
    )
}

/// Current and future-shaped Kani releases are accepted.
#[rstest]
#[case("1.2.3\n")]
#[case("1.3.0\n")]
#[case("1.4.0\n")]
fn kani_versions_are_accepted(#[case] text: &str) {
    assert!(
        kani_version("tools/kani/VERSION", text).is_ok(),
        "Kani release {text:?} must be accepted"
    );
}

/// A Kani release is three numeric components on one terminated line.
#[rstest]
#[case("1.2\n", "Kani release")]
#[case("1.2.3.4\n", "Kani release")]
#[case("1.02.3\n", "Kani release")]
#[case("v1.2.3\n", "Kani release")]
#[case("1.2.3", "newline")]
#[case("1.2.3\r\n", "one line")]
#[case("1.2.3\n1.3.0\n", "one line")]
fn kani_versions_are_rejected(#[case] text: &str, #[case] fragment: &str) {
    assert!(
        fails_with(kani_version("tools/kani/VERSION", text), fragment),
        "Kani pin {text:?} must fail with {fragment:?}"
    );
}

/// Current and future-shaped Verus releases are accepted.
#[rstest]
#[case("0.2027.01.15.abc1234\n")]
#[case("0.2027.02.20.def5678\n")]
fn verus_versions_are_accepted(#[case] text: &str) {
    assert!(
        verus_version("tools/verus/VERSION", text).is_ok(),
        "Verus release {text:?} must be accepted"
    );
}

/// A Verus release keeps its date and abbreviated-commit shape.
#[rstest]
#[case("0.2027.1.15.abc1234\n")]
#[case("0.2027.13.15.abc1234\n")]
#[case("0.2027.01.32.abc1234\n")]
#[case("0.2027.01.15.ABC1234\n")]
#[case("0.2027.01.15.abc123\n")]
#[case("1.2027.01.15.abc1234\n")]
#[case("0.2027.01.15.abc1234 extra\n")]
fn verus_versions_are_rejected(#[case] text: &str) {
    assert!(
        fails_with(verus_version("tools/verus/VERSION", text), "Verus release"),
        "Verus pin {text:?} must be rejected"
    );
}

/// A synthetic row binds the archive name derived from the parsed version.
#[test]
fn checksum_rows_are_accepted() {
    for version in ["0.2027.01.15.abc1234", "0.2027.02.20.def5678"] {
        let text = format!("{DIGEST}  verus-{version}-x86-linux.zip\n");
        assert!(
            verus_checksum_row("tools/verus/SHA256SUMS", &text, version).is_ok(),
            "checksum row for {version} must be accepted"
        );
    }
}

/// Malformed checksum rows name the rule they broke.
#[test]
fn checksum_rows_are_rejected() {
    let version = "0.2027.01.15.abc1234";
    let archive = format!("verus-{version}-x86-linux.zip");
    let mut short = DIGEST.to_owned();
    short.pop();
    let rows = [
        (
            "uppercase digest",
            format!("{}  {archive}\n", DIGEST.to_uppercase()),
            "lowercase",
        ),
        ("short digest", format!("{short}  {archive}\n"), "lowercase"),
        ("single separator", format!("{DIGEST} {archive}\n"), "row"),
        (
            "wrong archive",
            format!("{DIGEST}  verus-0.2027.02.20.def5678-x86-linux.zip\n"),
            "archive",
        ),
        (
            "extra row",
            format!("{DIGEST}  {archive}\nextra\n"),
            "one line",
        ),
    ];
    for (description, text, fragment) in rows {
        assert!(
            fails_with(
                verus_checksum_row("tools/verus/SHA256SUMS", &text, version),
                fragment
            ),
            "checksum row with {description} must fail with {fragment:?}"
        );
    }
}

/// A REF file with one repository and one lowercase revision is accepted.
#[test]
fn reference_fields_are_accepted() {
    let revision = "a".repeat(40);
    let text =
        format!("repository: https://example.test/tools.git\nbranch: main\nref: {revision}\n");
    assert_eq!(
        pinned_ref(REFERENCE, &text),
        Ok(revision.as_str()),
        "a 40-character lowercase ref must be accepted"
    );
    assert_eq!(
        pinned_repository(REFERENCE, &text),
        Ok("https://example.test/tools.git"),
        "a whitespace-free repository must be accepted"
    );
}

/// A malformed or duplicated REF field names the rule it broke.
#[test]
fn reference_fields_are_rejected() {
    let rows = [
        ("short revision", format!("ref: {}\n", "a".repeat(39))),
        ("uppercase revision", format!("ref: {}\n", "A".repeat(40))),
        (
            "trailing material",
            format!("ref: {} extra\n", "a".repeat(40)),
        ),
        ("missing revision", "branch: main\n".to_owned()),
        (
            "two revisions",
            format!("ref: {}\nref: {}\n", "a".repeat(40), "b".repeat(40)),
        ),
    ];
    for (description, text) in &rows {
        assert!(
            fails_with(pinned_ref(REFERENCE, text), "ref"),
            "REF row with {description} must be rejected"
        );
    }
    assert!(
        fails_with(
            pinned_repository(REFERENCE, "repository: https://example.test/a b\n"),
            "whitespace"
        ),
        "a repository containing whitespace must be rejected"
    );
}

/// The helper's Git source and revision are read from embedded metadata.
#[test]
fn script_helper_source_is_read() {
    let revision = "a".repeat(40);
    let source = script_with(&format!(
        "\"tree-sitter==0.25.2\",\n#   \"rust-prover-tools @ git+https://example.test/tools.git@{revision}\""
    ));
    assert_eq!(
        script_dependency("script.py", &source),
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
        script_dependency("script.py", &source),
        Ok(ScriptDependency {
            repository: "https://example.test/tools.git".to_owned(),
            revision,
        }),
        "a bare comment line and a normalized helper name must be accepted"
    );
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
            fails_with(script_dependency("script.py", source), fragment),
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
            fails_with(script_dependency("script.py", source), fragment),
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
    let outcome = script_matches_reference(&script, &reference);
    assert_eq!(
        outcome.is_ok(),
        is_expected_to_match,
        "script {repository}@{revision} against REF must match only when identical: {outcome:?}"
    );
}

/// The reader's file label must survive into the diagnostic.
#[test]
fn diagnostics_name_the_file() {
    assert!(
        fails_with(kani_version(FILE, "0.67\n"), FILE),
        "a diagnostic must name the file it read"
    );
}
