//! Parameterized boundary cases for the shipped elementwise addition (SC-12).
//!
//! The kernel may take no dev-dependency (VO-1), so its own tests are plain
//! `#[test]` functions using only `core`. The cases that read best as a table
//! live here, in the root package, where `rstest` is available. Both suites
//! call the one shipped body; neither has a copy of it.
//!
//! The runtime cases are what the `const` evaluation and the Verus root are
//! compared against, so a boundary that this suite misses would leave B01's
//! "one body, three readers" claim narrower than it reads.

use combobulate_kernel::elementwise_add::{AddFailure, add_i64_into};
use rstest::rstest;

/// Runs one addition into a scratch buffer and returns the result with it.
///
/// The buffer's initial value is distinctive so a failure that wrote anything
/// is visible, which is what SC-09's atomic-commit rule forbids.
fn add(lhs: &[i64], rhs: &[i64], width: usize) -> (Result<(), AddFailure>, Vec<i64>) {
    let mut out = vec![7_i64; width];
    let result = add_i64_into(lhs, rhs, &mut out);
    (result, out)
}

/// An agreeing, in-range call publishes the pointwise sum.
#[rstest]
#[case::single(&[1], &[2], &[3])]
#[case::several(&[1, 2, 3], &[10, 20, 30], &[11, 22, 33])]
#[case::negatives(&[-1, -2], &[-3, -4], &[-4, -6])]
#[case::mixed_signs(&[-5, 5], &[5, -5], &[0, 0])]
#[case::empty(&[], &[], &[])]
#[case::upper_bound(&[i64::MAX - 1], &[1], &[i64::MAX])]
#[case::lower_bound(&[i64::MIN + 1], &[-1], &[i64::MIN])]
fn agreeing_shapes_publish_the_pointwise_sum(
    #[case] lhs: &[i64],
    #[case] rhs: &[i64],
    #[case] expected: &[i64],
) {
    let (result, out) = add(lhs, rhs, lhs.len());

    assert_eq!(result, Ok(()), "an in-range call must succeed");
    assert_eq!(out, expected, "every position must hold its own sum");
}

/// A length disagreement reports `LengthMismatch` and writes nothing.
#[rstest]
#[case::rhs_shorter(&[1, 2, 3], &[1, 2], 3)]
#[case::rhs_longer(&[1, 2], &[1, 2, 3], 3)]
#[case::output_shorter(&[1, 2, 3], &[1, 2, 3], 2)]
#[case::output_longer(&[1, 2, 3], &[1, 2, 3], 4)]
#[case::one_empty_operand(&[], &[1], 1)]
fn length_disagreement_is_named_and_publishes_nothing(
    #[case] lhs: &[i64],
    #[case] rhs: &[i64],
    #[case] width: usize,
) {
    let (result, out) = add(lhs, rhs, width);

    assert_eq!(
        result,
        Err(AddFailure::LengthMismatch),
        "a shape disagreement must be reported as such"
    );
    assert_eq!(
        out,
        vec![7_i64; width],
        "a length failure must not touch the output"
    );
}

/// An overflow names the least failing position and writes nothing.
#[rstest]
#[case::first_position(&[i64::MAX, 0], &[1, 0], 0)]
#[case::middle_position(&[0, i64::MAX, 0], &[0, 1, 0], 1)]
#[case::last_position(&[0, 0, i64::MAX], &[0, 0, 1], 2)]
#[case::upper_bound_is_the_least(&[i64::MAX, i64::MAX], &[1, 1], 0)]
#[case::lower_bound(&[i64::MIN], &[-1], 0)]
#[case::deep_negative(&[i64::MIN, 0], &[-1, i64::MAX], 0)]
fn overflow_names_the_least_position_and_publishes_nothing(
    #[case] lhs: &[i64],
    #[case] rhs: &[i64],
    #[case] position: usize,
) {
    let (result, out) = add(lhs, rhs, lhs.len());

    assert_eq!(
        result,
        Err(AddFailure::Overflow { position }),
        "the least overflowing position must be the one named"
    );
    assert_eq!(
        out,
        vec![7_i64; lhs.len()],
        "an overflow must not write even the positions that would have fit"
    );
}

/// Both I64 boundaries are successes, so the range check is not off by one.
#[rstest]
#[case::upper(&[i64::MAX, i64::MIN], &[0, 0], &[i64::MAX, i64::MIN])]
#[case::to_upper(&[i64::MAX - 1, 0], &[1, 0], &[i64::MAX, 0])]
#[case::to_lower(&[i64::MIN + 1, 0], &[-1, 0], &[i64::MIN, 0])]
fn the_range_ends_are_inclusive(
    #[case] lhs: &[i64],
    #[case] rhs: &[i64],
    #[case] expected: &[i64],
) {
    let (result, out) = add(lhs, rhs, lhs.len());

    assert_eq!(result, Ok(()), "a sum that lands on a boundary is in range");
    assert_eq!(
        out, expected,
        "the boundary sums must be published unchanged"
    );
}

/// Only the least overflow is named, however many positions overflow.
#[rstest]
#[case::all(&[i64::MAX, i64::MAX, i64::MAX], &[1, 1, 1], 0)]
#[case::from_second(&[0, i64::MAX, i64::MAX], &[0, 1, 1], 1)]
fn one_overflow_is_named_even_when_several_occur(
    #[case] lhs: &[i64],
    #[case] rhs: &[i64],
    #[case] position: usize,
) {
    let (result, _) = add(lhs, rhs, lhs.len());

    assert_eq!(
        result,
        Err(AddFailure::Overflow { position }),
        "several overflows must still name exactly the least one"
    );
}
