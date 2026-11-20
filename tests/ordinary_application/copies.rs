//! FACADE-3: the ordinary path copies no buffer it does not have to.
//!
//! Every case compares data pointers, which is the only observation that can
//! distinguish sharing a buffer from copying one. A case that expects sharing
//! asserts equality; the addition case asserts inequality as well, so the
//! comparison is not vacuously satisfied by an implementation that always
//! returns the same pointer.

use combobulate::{Array, add, identity};
use rstest::rstest;

use super::{buffer_ptr, engine};

#[rstest]
#[case::empty(vec![])]
#[case::one(vec![9])]
#[case::many(vec![1, 2, 3, 4])]
fn construction_keeps_the_vectors_original_buffer(#[case] values: Vec<i64>) {
    let original = values.as_ptr();
    let array = Array::from_i64(values);
    assert_eq!(
        array.as_i64_slice().map(<[i64]>::as_ptr),
        Some(original),
        "moving a Vec into an Array must not copy its elements"
    );
}

#[rstest]
#[case::then(3)]
#[case::apply(3)]
#[case::then_empty(0)]
fn identity_keeps_the_input_buffer_through_every_spelling(#[case] width: usize) {
    let array = Array::from_i64(vec![5; width]);
    let origin = buffer_ptr(&array);
    let through_then = array.expr().then(&identity());
    let through_apply = identity().apply(&array.expr());
    for (spelling, outcome) in [
        ("then", through_then.collect()),
        ("apply", through_apply.collect()),
    ] {
        let collected = outcome.expect("identity cannot fail");
        assert_eq!(
            buffer_ptr(&collected),
            origin,
            "identity through {spelling} must return the input's buffer"
        );
    }
}

#[rstest]
#[case::collect(3)]
#[case::prepare_then_execute(3)]
fn identity_keeps_the_input_buffer_through_collect_and_execute(#[case] width: usize) {
    let array = Array::from_i64(vec![7; width]);
    let origin = buffer_ptr(&array);
    let collected = array
        .expr()
        .then(&identity())
        .collect()
        .expect("identity cannot fail");
    let plan = array
        .expr()
        .then(&identity())
        .prepare(&engine())
        .expect("an identity has no shape to disagree about");
    let executed = plan.execute().expect("an identity cannot overflow");
    assert_eq!(
        buffer_ptr(&collected),
        origin,
        "collect must return the input's buffer"
    );
    assert_eq!(
        buffer_ptr(&executed),
        origin,
        "prepare then execute must return the input's buffer"
    );
}

#[test]
fn add_keeps_both_inputs_and_publishes_its_own_buffer() {
    let left = Array::from_i64(vec![1, 2, 3]);
    let right = Array::from_i64(vec![10, 20, 30]);
    let left_ptr = buffer_ptr(&left);
    let right_ptr = buffer_ptr(&right);
    let sum = add()
        .apply(&left.expr(), &right.expr())
        .collect()
        .expect("equal lengths fit");
    assert_eq!(
        (buffer_ptr(&left), buffer_ptr(&right)),
        (left_ptr, right_ptr),
        "an addition must leave both operand buffers untouched"
    );
    assert_eq!(
        (left.as_i64_slice(), right.as_i64_slice()),
        (Some(&[1_i64, 2, 3][..]), Some(&[10_i64, 20, 30][..])),
        "an addition must leave both operands' contents untouched"
    );
    let sum_ptr = buffer_ptr(&sum);
    assert!(
        sum_ptr != left_ptr && sum_ptr != right_ptr,
        "an addition must publish a buffer of its own, not an operand's"
    );
}

#[test]
fn a_nested_sum_reuses_an_input_only_when_it_is_that_input() {
    let values = Array::from_i64(vec![4, 5]);
    let origin = buffer_ptr(&values);
    let identity_sum = add().apply(&values.expr(), &values.expr());
    let collected = identity_sum.collect().expect("4 + 4 fits");
    assert!(
        buffer_ptr(&collected) != origin,
        "an addition always publishes its own buffer"
    );
    assert_eq!(
        collected.as_i64_slice(),
        Some(&[8, 10][..]),
        "the doubled values are the pointwise sum"
    );
}

#[test]
fn preparing_and_executing_an_input_costs_no_copy() {
    let values = Array::from_i64(vec![1, 2, 3]);
    let origin = buffer_ptr(&values);
    let plan = values
        .expr()
        .prepare(&engine())
        .expect("an input has no shape to disagree about");
    let executed = plan.execute().expect("an input cannot overflow");
    assert_eq!(
        buffer_ptr(&executed),
        origin,
        "executing an input must return the buffer the caller supplied"
    );
}
