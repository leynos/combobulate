//! FACADE-8: diagnostics are stable, and every code is a registered one.
//!
//! A rendered sentence is what a user reads, so it is snapshotted: a wording
//! change then has to be accepted deliberately rather than slipping into a
//! release. Each snapshot is paired with an assertion on the failure's code,
//! because the code is the part a consumer matches on and must not depend on
//! how the sentence reads.

use camino::Utf8Path;
use cap_std::{ambient_authority, fs_utf8::Dir};
use combobulate::{Failure, Stage, add};
use insta::{assert_snapshot, with_settings};

use super::{engine, expr, single_failure};

/// Renders `error` and asserts the committed snapshot of it.
///
/// Snapshots live in the repository-wide `tests/snapshots` directory, not
/// beside this file, so every snapshot in the repository is found in one
/// place. `insta` prefixes the file name with this module path, which is why
/// the names below do not repeat it.
macro_rules! snapshot_error {
    ($name:literal, $error:expr) => {
        with_settings!({ snapshot_path => "../snapshots" }, {
            assert_snapshot!($name, $error.to_string());
        })
    };
}

#[test]
fn a_shape_disagreement_at_preparation() {
    let error = add()
        .apply(&expr(&[1, 2, 3]), &expr(&[1, 2]))
        .prepare(&engine())
        .expect_err("unequal lengths cannot be prepared");
    assert_eq!(
        error.failures().first().map(Failure::code),
        Some("ShapeAgreement"),
        "the snapshot's failure must be the shape disagreement"
    );
    snapshot_error!("shape_agreement", error);
}

#[test]
fn an_integer_overflow_at_execution() {
    let plan = add()
        .apply(&expr(&[i64::MAX]), &expr(&[1]))
        .prepare(&engine())
        .expect("an overflow is not a static failure");
    let error = plan.execute().expect_err("MAX + 1 leaves the I64 range");
    assert_eq!(
        error.failures().first().map(Failure::code),
        Some("IntegerOverflow"),
        "the snapshot's failure must be the integer overflow"
    );
    snapshot_error!("integer_overflow", error);
}

#[test]
fn several_shape_disagreements_at_preparation() {
    let left = add().apply(&expr(&[1, 2, 3]), &expr(&[1, 2]));
    let right = add().apply(&expr(&[1, 2, 3, 4, 5]), &expr(&[1, 2, 3, 4]));
    let error = add()
        .apply(&left, &right)
        .prepare(&engine())
        .expect_err("both halves disagree");
    assert_eq!(
        error.failures().len(),
        2,
        "the snapshot must show that a multi-failure report is readable"
    );
    snapshot_error!("two_disagreements", error);
}

#[test]
fn the_stages_render_as_their_own_words() {
    assert_eq!(
        (Stage::Preparation.to_string(), Stage::Execution.to_string()),
        ("preparation".to_owned(), "execution".to_owned()),
        "a stage must render as the word the message uses for it"
    );
}

#[test]
fn every_code_a_failure_can_report_is_registered() {
    let root = Dir::open_ambient_dir(
        Utf8Path::new(env!("CARGO_MANIFEST_DIR")),
        ambient_authority(),
    )
    .expect("the repository root must be openable");
    let text = root
        .read_to_string("spec/semantic-contracts.json")
        .expect("the semantic contract must be readable");
    let contract: serde_json::Value =
        serde_json::from_str(&text).expect("the semantic contract must be valid JSON");
    let registered: Vec<&str> = contract
        .get("error_codes")
        .and_then(serde_json::Value::as_array)
        .expect("the contract must list its error codes")
        .iter()
        .map(|code| code.as_str().expect("every error code must be a string"))
        .collect();
    // Both codes are observed from real runs rather than constructed, so a
    // code that no longer occurs cannot pass by being written in this test.
    let mismatched = add()
        .apply(&expr(&[1, 2]), &expr(&[1]))
        .prepare(&engine())
        .expect_err("unequal lengths cannot be prepared");
    let overflowing = add()
        .apply(&expr(&[i64::MAX]), &expr(&[1]))
        .prepare(&engine())
        .expect("an overflow is not a static failure")
        .execute()
        .expect_err("MAX + 1 leaves the I64 range");
    for error in [&mismatched, &overflowing] {
        let failure = single_failure(error);
        assert!(
            registered.contains(&failure.code()),
            "{} must be a registered error code, registered: {registered:?}",
            failure.code()
        );
    }
}

#[test]
fn the_error_is_displayed_with_a_single_leading_line() {
    let plan = add()
        .apply(&expr(&[1, 2, i64::MAX]), &expr(&[1, 1, 1]))
        .prepare(&engine())
        .expect("an overflow is not a static failure");
    let error = plan.execute().expect_err("the last position overflows");
    let rendered = error.to_string();
    assert!(
        rendered.starts_with("expression failed during execution"),
        "the first line must name the stage, got {rendered:?}"
    );
    assert_eq!(
        rendered.lines().count(),
        2,
        "a one-failure report is a header and one item"
    );
}
