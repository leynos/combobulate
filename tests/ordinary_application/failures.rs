//! FACADE-2: preparation reports every independent shape disagreement.
//!
//! The cases are the ones DL-9 names, each with its expected report. They use
//! googletest's `elements_are!` with `matches_pattern!` and `..`, because the
//! failure variants are `#[non_exhaustive]` and a pattern that does not say
//! `..` would stop compiling when a later release adds a field.

use combobulate::{Failure, add};
use googletest::prelude::*;

use super::{engine, expr};

/// The `ShapeAgreement` failure with the lengths a case expects.
fn disagreeing(lhs_len: usize, rhs_len: usize) -> impl Matcher<Failure> {
    matches_pattern!(Failure::ShapeAgreement {
        lhs_len: eq(lhs_len),
        rhs_len: eq(rhs_len),
        ..
    })
}

/// The failures preparing `expression` reports.
///
/// The report comes back as an array of the length the case expects. That is
/// the container `elements_are!` accepts: it requires both the container and
/// its element type to be `Copy`, which a `Vec` is not. A report of the wrong
/// size therefore fails here, naming both counts, rather than as a matcher
/// mismatch that would only mention the elements it saw.
fn preparation_failures<const N: usize>(expression: &combobulate::AExpr) -> [Failure; N] {
    let reported = expression
        .prepare(&engine())
        .expect_err("the case's expression must not prepare")
        .failures()
        .to_vec();
    match reported.try_into() {
        Ok(failures) => failures,
        Err(unexpected) => panic!(
            "the case expects {N} failures, preparation reported {}: {unexpected:?}",
            unexpected.len()
        ),
    }
}

#[test]
fn one_mismatch_is_reported_once() {
    let expression = add().apply(&expr(&[1, 2, 3]), &expr(&[1, 2]));
    assert_that!(
        preparation_failures::<1>(&expression),
        elements_are![disagreeing(3, 2)],
        "one disagreeing addition is one failure"
    );
}

#[test]
fn a_disagreement_beneath_a_second_addition_is_still_reported() {
    let inner = add().apply(&expr(&[1, 2, 3]), &expr(&[1, 2]));
    let expression = add().apply(&inner, &expr(&[1]));
    assert_that!(
        preparation_failures::<1>(&expression),
        elements_are![disagreeing(3, 2)],
        "the root-cause addition is reported, and its ancestor is not"
    );
}

#[test]
fn two_independent_disagreements_are_reported_left_first() {
    let left = add().apply(&expr(&[1, 2, 3]), &expr(&[1, 2]));
    let right = add().apply(&expr(&[1, 2, 3, 4, 5]), &expr(&[1, 2, 3, 4]));
    let expression = add().apply(&left, &right);
    assert_that!(
        preparation_failures::<2>(&expression),
        elements_are![disagreeing(3, 2), disagreeing(5, 4)],
        "independent disagreements are reported in left-first post-order"
    );
}

#[test]
fn a_disagreement_below_a_shared_node_is_reported_once() {
    let shared = add().apply(&expr(&[1, 2, 3]), &expr(&[1, 2]));
    let expression = add().apply(&shared, &shared);
    assert_that!(
        preparation_failures::<1>(&expression),
        elements_are![disagreeing(3, 2)],
        "a shared node is one root cause, so it is reported once"
    );
}

#[test]
fn an_agreeing_expression_reports_nothing() {
    let expression = add().apply(&add().apply(&expr(&[1, 2]), &expr(&[3, 4])), &expr(&[5, 6]));
    assert!(
        expression.prepare(&engine()).is_ok(),
        "an expression whose every addition agrees must prepare"
    );
}

#[test]
fn every_reported_failure_names_the_add_operation() {
    let left = add().apply(&expr(&[1, 2, 3]), &expr(&[1, 2]));
    let right = add().apply(&expr(&[1, 2, 3, 4, 5]), &expr(&[1, 2, 3, 4]));
    let failures = preparation_failures::<2>(&add().apply(&left, &right));
    assert_eq!(
        failures.len(),
        2,
        "the case must produce two failures to check them both"
    );
    for failure in &failures {
        let Failure::ShapeAgreement { operation, .. } = failure else {
            panic!("a preparation failure must be a shape disagreement");
        };
        assert_eq!(
            *operation,
            add().operation_id(),
            "the disagreement belongs to the addition that found it"
        );
        assert_eq!(
            operation.catalogue_id(),
            "V001",
            "the report must cite the catalogue entry the operation implements"
        );
    }
}
