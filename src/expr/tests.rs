//! Construction, folding, cached facts and the length model.
//!
//! The deep-chain cases live in [`super::small_stack`], because they need a
//! deliberately small stack to mean anything.

use std::sync::Arc;

use rstest::rstest;

use super::{AExpr, NodeKind, add, identity};
use crate::array::Array;

/// An expression over `width` values, with the buffer pointer it started from.
fn expr_and_origin(width: usize) -> (Option<*const i64>, AExpr) {
    let values = vec![1_i64; width];
    let origin = Some(values.as_ptr());
    (origin, Array::from_i64(values).expr())
}

/// An expression over a buffer of `width` values.
fn expr_of(width: usize) -> AExpr { expr_and_origin(width).1 }

#[rstest]
#[case::empty(0)]
#[case::one(1)]
#[case::many(3)]
fn an_input_reports_the_buffer_length(#[case] width: usize) {
    let expression = expr_of(width);
    assert_eq!(
        expression.len(),
        Some(width),
        "an input's length is the buffer's element count"
    );
    assert_eq!(
        expression.is_empty(),
        width == 0,
        "only a zero-length input is known to be empty"
    );
}

/// The data pointer of an input node's shared buffer.
///
/// `None` for any node that is not an input, which is how a case can tell an
/// operation that folded away from one that added a node.
fn input_ptr(expression: &AExpr) -> Option<*const i64> {
    match &expression.node.kind {
        NodeKind::Input(values) => Some(values.as_ptr()),
        NodeKind::Add { .. } => None,
    }
}

#[test]
fn identity_folds_to_the_operand_handle() {
    let operand = expr_of(2);
    let folded = operand.then(&identity());
    assert_eq!(
        folded.len(),
        Some(2),
        "folding must preserve the operand's length"
    );
    assert_eq!(
        folded.node.length, operand.node.length,
        "folding must leave the cached facts untouched, not recompute them"
    );
}

#[rstest]
#[case::then(0)]
#[case::then_nonempty(3)]
fn identity_through_then_keeps_the_input_buffer(#[case] width: usize) {
    let (origin, operand) = expr_and_origin(width);
    let folded = operand.then(&identity());
    assert_eq!(
        input_ptr(&folded),
        origin,
        "identity through `then` must return the input's own buffer (FACADE-3)"
    );
    assert!(
        Arc::ptr_eq(&folded.node, &operand.node),
        "folding must share the operand's node, not copy it"
    );
}

#[rstest]
#[case::apply(0)]
#[case::apply_nonempty(3)]
fn identity_through_apply_keeps_the_input_buffer(#[case] width: usize) {
    let (origin, operand) = expr_and_origin(width);
    let folded = identity().apply(&operand);
    assert_eq!(
        input_ptr(&folded),
        origin,
        "identity through `apply` must return the input's own buffer (FACADE-3)"
    );
}

#[test]
fn add_of_equal_lengths_has_that_length() {
    let sum = add().apply(&expr_of(3), &expr_of(3));
    assert_eq!(
        sum.len(),
        Some(3),
        "an addition of equal lengths has that length"
    );
}

#[test]
fn add_of_unequal_lengths_has_no_length() {
    let sum = add().apply(&expr_of(3), &expr_of(2));
    assert_eq!(
        sum.len(),
        None,
        "an addition of unequal lengths has no length under the model"
    );
}

#[test]
fn add_over_an_unknown_length_has_no_length() {
    let inner = add().apply(&expr_of(3), &expr_of(2));
    let outer = add().apply(&inner, &expr_of(3));
    assert_eq!(
        outer.len(),
        None,
        "a node above an unknown length has no length of its own"
    );
}

#[test]
fn add_keeps_both_input_buffers_and_differs_from_them() {
    let (left_origin, left) = expr_and_origin(2);
    let (right_origin, right) = expr_and_origin(2);
    let sum = add().apply(&left, &right);
    assert_eq!(
        input_ptr(&left),
        left_origin,
        "the left operand must keep its own buffer across `add` (FACADE-3)"
    );
    assert_eq!(
        input_ptr(&right),
        right_origin,
        "the right operand must keep its own buffer across `add` (FACADE-3)"
    );
    let NodeKind::Add { lhs, rhs } = &sum.node.kind else {
        panic!("an addition must build an add node");
    };
    assert!(
        !Arc::ptr_eq(&lhs.node, &right.node) && !Arc::ptr_eq(&rhs.node, &left.node),
        "an addition must not swap or alias its operands"
    );
    assert!(
        !Arc::ptr_eq(&sum.node, &left.node) && !Arc::ptr_eq(&sum.node, &right.node),
        "the output must be a new node, not one of the operands"
    );
}

#[test]
fn the_dtype_is_i64_for_every_expression() {
    assert_eq!(
        add().apply(&expr_of(1), &expr_of(1)).dtype(),
        crate::Dtype::I64,
        "every expression in this release yields I64"
    );
}

#[test]
fn a_shared_subterm_is_one_node() {
    let shared = expr_of(2);
    let sum = add().apply(&shared, &shared);
    let NodeKind::Add { lhs, rhs } = &sum.node.kind else {
        panic!("an addition must build an add node");
    };
    assert!(
        Arc::ptr_eq(&lhs.node, &shared.node) && Arc::ptr_eq(&rhs.node, &shared.node),
        "one operand handle referenced twice must resolve to one shared node"
    );
}

#[test]
fn only_the_root_cause_records_a_mismatch() {
    let disagreeing = add().apply(&expr_of(3), &expr_of(2));
    assert!(
        format!("{:?}", disagreeing.node).contains("mismatch_below: true"),
        "the add with unequal operand lengths is the root cause"
    );
    let above = add().apply(&disagreeing, &expr_of(3));
    assert!(
        format!("{:?}", above.node).contains("mismatch_below: true"),
        "an ancestor must inherit the mismatch rather than lose it"
    );
    assert_eq!(
        above.len(),
        None,
        "an ancestor of an unknown length has no length of its own"
    );
}

#[test]
fn agreeing_operands_record_no_mismatch() {
    let sum = add().apply(&expr_of(3), &expr_of(3));
    assert!(
        format!("{:?}", sum.node).contains("mismatch_below: false"),
        "equal operand lengths are not a disagreement"
    );
}
