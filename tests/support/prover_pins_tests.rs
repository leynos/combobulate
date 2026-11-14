//! Shape and relationship regressions for the prover release-pin readers.

use rstest::rstest;

use crate::pins::{
    PinError,
    PinSource,
    kani_version,
    pinned_ref,
    pinned_repository,
    verus_checksum_row,
    verus_version,
};

/// One repository-relative path used by every diagnostic in these cases.
const FILE: &str = "pin";

/// The REF path used by the relationship cases.
const REFERENCE: &str = "tools/rust-prover-tools/REF";

/// A synthetic digest keeps checksum cases independent of the live release.
const DIGEST: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

/// Reports whether a reader failed with a diagnostic naming `fragment`.
pub(crate) fn fails_with<T>(result: Result<T, PinError>, fragment: &str) -> bool {
    result
        .err()
        .is_some_and(|error| error.to_string().contains(fragment))
}

/// Builds a pin source labelled with the file a diagnostic should name.
pub(crate) fn pin_source<'a>(file: &'a str, text: &'a str) -> PinSource<'a> {
    PinSource::new(file, text)
}

/// Current and future-shaped Kani releases are accepted.
#[rstest]
#[case("1.2.3\n")]
#[case("1.3.0\n")]
#[case("1.4.0\n")]
fn kani_versions_are_accepted(#[case] text: &str) {
    assert!(
        kani_version(pin_source("tools/kani/VERSION", text)).is_ok(),
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
        fails_with(
            kani_version(pin_source("tools/kani/VERSION", text)),
            fragment
        ),
        "Kani pin {text:?} must fail with {fragment:?}"
    );
}

/// Current and future-shaped Verus releases are accepted.
#[rstest]
#[case("0.2027.01.15.abc1234\n")]
#[case("0.2027.02.20.def5678\n")]
#[case("0.2028.02.29.abc1234\n")]
#[case("0.2000.02.29.abc1234\n")]
fn verus_versions_are_accepted(#[case] text: &str) {
    assert!(
        verus_version(pin_source("tools/verus/VERSION", text)).is_ok(),
        "Verus release {text:?} must be accepted"
    );
}

/// A Verus release keeps its date and abbreviated-commit shape.
#[rstest]
#[case("0.2027.1.15.abc1234\n")]
#[case("0.2027.13.15.abc1234\n")]
#[case("0.2027.01.32.abc1234\n")]
#[case("0.2027.02.30.abc1234\n")]
#[case("0.2027.02.31.abc1234\n")]
#[case("0.2027.04.31.abc1234\n")]
#[case("0.2027.02.29.abc1234\n")]
#[case("0.2100.02.29.abc1234\n")]
#[case("0.2027.01.15.ABC1234\n")]
#[case("0.2027.01.15.abc123\n")]
#[case("1.2027.01.15.abc1234\n")]
#[case("0.2027.01.15.abc1234 extra\n")]
fn verus_versions_are_rejected(#[case] text: &str) {
    assert!(
        fails_with(
            verus_version(pin_source("tools/verus/VERSION", text)),
            "Verus release"
        ),
        "Verus pin {text:?} must be rejected"
    );
}

/// A synthetic row binds the archive name derived from the parsed version.
#[test]
fn checksum_rows_are_accepted() {
    for version in ["0.2027.01.15.abc1234", "0.2027.02.20.def5678"] {
        let text = format!("{DIGEST}  verus-{version}-x86-linux.zip\n");
        assert!(
            verus_checksum_row(pin_source("tools/verus/SHA256SUMS", &text), version).is_ok(),
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
                verus_checksum_row(pin_source("tools/verus/SHA256SUMS", &text), version),
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
        pinned_ref(pin_source(REFERENCE, &text)),
        Ok(revision.as_str()),
        "a 40-character lowercase ref must be accepted"
    );
    assert_eq!(
        pinned_repository(pin_source(REFERENCE, &text)),
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
            fails_with(pinned_ref(pin_source(REFERENCE, text)), "ref"),
            "REF row with {description} must be rejected"
        );
    }
    assert!(
        fails_with(
            pinned_repository(pin_source(
                REFERENCE,
                "repository: https://example.test/a b\n"
            )),
            "whitespace"
        ),
        "a repository containing whitespace must be rejected"
    );
}

/// The reader's file label must survive into the diagnostic.
#[test]
fn diagnostics_name_the_file() {
    assert!(
        fails_with(kani_version(pin_source(FILE, "0.67\n")), FILE),
        "a diagnostic must name the file it read"
    );
}
