//! Scheduling, staging, sharing and the dispatch identity.

use combobulate_kernel::elementwise_add::AddFailure;
use rstest::rstest;

use super::{NativeExecutor, dispatch_add};
use crate::{
    array::Array,
    error::{Failure, Stage},
    expr::{AExpr, OperationId, add, identity},
};

/// An expression over `width` ones, whose sums stay small.
fn expr_of(width: usize) -> AExpr { Array::from_i64(vec![1; width]).expr() }

/// The executor every case uses.
fn engine() -> NativeExecutor { NativeExecutor::sequential() }

#[test]
fn a_single_input_collects_to_its_own_buffer() {
    let array = Array::from_i64(vec![4, 5, 6]);
    let collected = array.expr().collect().expect("an input cannot fail");
    assert_eq!(
        collected.as_i64_slice().map(<[i64]>::as_ptr),
        array.as_i64_slice().map(<[i64]>::as_ptr),
        "collecting an input must return its buffer, not a copy (FACADE-3)"
    );
}

#[rstest]
#[case::then(0)]
#[case::then_nonempty(3)]
fn identity_collects_to_the_inputs_buffer(#[case] width: usize) {
    let array = Array::from_i64(vec![7; width]);
    let collected = array
        .expr()
        .then(&identity())
        .collect()
        .expect("identity cannot fail");
    assert_eq!(
        collected.as_i64_slice().map(<[i64]>::as_ptr),
        array.as_i64_slice().map(<[i64]>::as_ptr),
        "identity through collect must return the input's buffer (FACADE-3)"
    );
}

#[test]
fn preparing_and_executing_an_identity_keeps_the_inputs_buffer() {
    let array = Array::from_i64(vec![1, 2]);
    let plan = array
        .expr()
        .then(&identity())
        .prepare(&engine())
        .expect("an identity has no shape to disagree about");
    let executed = plan.execute().expect("an identity cannot overflow");
    assert_eq!(
        executed.as_i64_slice().map(<[i64]>::as_ptr),
        array.as_i64_slice().map(<[i64]>::as_ptr),
        "execute must return the input's buffer (FACADE-3)"
    );
}

#[test]
fn add_sums_pointwise_into_a_new_buffer() {
    let left = Array::from_i64(vec![1, 2, 3]);
    let right = Array::from_i64(vec![10, 20, 30]);
    let sum = add()
        .apply(&left.expr(), &right.expr())
        .collect()
        .expect("equal lengths fit");
    assert_eq!(
        sum.as_i64_slice(),
        Some(&[11_i64, 22, 33][..]),
        "add sums the operands position by position"
    );
    assert!(
        sum.as_i64_slice().map(<[i64]>::as_ptr) != left.as_i64_slice().map(<[i64]>::as_ptr)
            && sum.as_i64_slice().map(<[i64]>::as_ptr) != right.as_i64_slice().map(<[i64]>::as_ptr),
        "an addition must publish its own buffer (FACADE-3)"
    );
    assert_eq!(
        (left.as_i64_slice(), right.as_i64_slice()),
        (Some(&[1_i64, 2, 3][..]), Some(&[10_i64, 20, 30][..])),
        "add must leave both operands as they were"
    );
}

#[test]
fn an_overflowing_expression_still_prepares_and_fails_only_at_execution() {
    let huge = Array::from_i64(vec![i64::MAX]).expr();
    let one = Array::from_i64(vec![1]).expr();
    let plan = add()
        .apply(&huge, &one)
        .prepare(&engine())
        .expect("an overflow is not a static failure (FACADE-6)");
    let error = plan.execute().expect_err("MAX + 1 leaves the I64 range");
    assert_eq!(
        error.stage(),
        Stage::Execution,
        "an overflow is discovered while values are summed"
    );
    assert_eq!(
        error.failures(),
        &[Failure::IntegerOverflow {
            operation: OperationId::ADD,
            position: 0,
        }][..],
        "the failure must name the least overflowing position"
    );
}

#[test]
fn a_length_mismatch_fails_at_preparation() {
    let error = add()
        .apply(&expr_of(3), &expr_of(2))
        .prepare(&engine())
        .expect_err("unequal lengths cannot be prepared");
    assert_eq!(
        error.stage(),
        Stage::Preparation,
        "a shape disagreement is settled before any kernel runs"
    );
    assert_eq!(
        error.failures(),
        &[Failure::ShapeAgreement {
            operation: OperationId::ADD,
            lhs_len: 3,
            rhs_len: 2,
        }][..],
        "the failure must name the lengths that disagree"
    );
}

#[test]
fn an_add_over_a_mismatch_reports_one_failure() {
    let inner = add().apply(&expr_of(3), &expr_of(2));
    let error = add()
        .apply(&inner, &expr_of(1))
        .prepare(&engine())
        .expect_err("a mismatch beneath is still a static failure");
    assert_eq!(
        error.failures(),
        &[Failure::ShapeAgreement {
            operation: OperationId::ADD,
            lhs_len: 3,
            rhs_len: 2,
        }][..],
        "the root cause is reported once, not once per ancestor"
    );
}

#[test]
fn two_independent_mismatches_are_reported_left_first() {
    let left = add().apply(&expr_of(3), &expr_of(2));
    let right = add().apply(&expr_of(5), &expr_of(4));
    let error = add()
        .apply(&left, &right)
        .prepare(&engine())
        .expect_err("both halves disagree");
    assert_eq!(
        error.failures(),
        &[
            Failure::ShapeAgreement {
                operation: OperationId::ADD,
                lhs_len: 3,
                rhs_len: 2,
            },
            Failure::ShapeAgreement {
                operation: OperationId::ADD,
                lhs_len: 5,
                rhs_len: 4,
            },
        ][..],
        "independent disagreements are all reported, left before right"
    );
}

#[test]
fn a_mismatch_below_a_shared_node_is_reported_once() {
    let shared = add().apply(&expr_of(3), &expr_of(2));
    let error = add()
        .apply(&shared, &shared)
        .prepare(&engine())
        .expect_err("the shared subterm disagrees");
    assert_eq!(
        error.failures().len(),
        1,
        "one shared node is one root cause, however many consumers it has"
    );
}

#[test]
fn a_shared_subterm_occupies_one_step() {
    let shared = expr_of(2);
    let plan = add()
        .apply(&shared, &shared)
        .prepare(&engine())
        .expect("equal shapes agree");
    assert_eq!(
        plan.steps.len(),
        2,
        "one input and one addition are the whole schedule, not three steps"
    );
    assert_eq!(
        plan.execute().expect("1 + 1 fits").as_i64_slice(),
        Some(&[2, 2][..]),
        "the shared operand is summed with itself"
    );
}

#[test]
fn a_shared_subterm_is_evaluated_once_at_every_level() {
    // `x(k+1) = add(x(k), x(k))` visits 2^62 nodes if it is not memoized.
    let mut chain = Array::from_i64(vec![1]).expr();
    for _ in 0..62 {
        chain = add().apply(&chain, &chain);
    }
    let collected = chain.collect().expect("62 doublings fit in I64");
    assert_eq!(
        collected.as_i64_slice(),
        Some(&[1 << 62][..]),
        "each level doubles the one below it"
    );
}

#[test]
fn the_first_unmemoized_failure_is_the_overflowing_level() {
    let mut chain = Array::from_i64(vec![1]).expr();
    for _ in 0..63 {
        chain = add().apply(&chain, &chain);
    }
    let error = chain.collect().expect_err("2^63 exceeds I64::MAX");
    assert_eq!(
        error.failures(),
        &[Failure::IntegerOverflow {
            operation: OperationId::ADD,
            position: 0,
        }][..],
        "the level whose sum leaves the range is the one reported"
    );
}

#[test]
fn the_dispatch_route_is_the_verified_kernel() {
    let identity = add().operation_id();
    assert_eq!(
        (identity.name(), identity.catalogue_id()),
        ("add", "V001"),
        "the add descriptor must cite the catalogue entry this kernel implements"
    );
    let mut out = [0_i64; 2];
    dispatch_add(&[1, 2], &[10, 20], &mut out).expect("equal shapes fit");
    assert_eq!(
        out,
        [11, 22],
        "the dispatch function must run the checked elementwise kernel"
    );
    assert_eq!(
        dispatch_add(&[1], &[1, 2], &mut out),
        Err(AddFailure::LengthMismatch),
        "the kernel's own length check must still refuse a short operand"
    );
}

/// A plan's `Debug` reports its schedule as step kinds, not as buffers.
///
/// The view exists so a failing test can print a plan without dumping every
/// input; that contract is only observable through the rendering itself. The
/// operands hold multi-digit values that no structural number in the view
/// could produce, so a derived `Debug` — which prints the buffers — is caught
/// by looking for them rather than by a risky single-digit check.
#[test]
fn a_plan_renders_its_step_kinds_and_no_elements() {
    let left = Array::from_i64(vec![111, 222, 333]).expr();
    let right = Array::from_i64(vec![444, 555, 666]).expr();
    let plan = add()
        .apply(&left, &right)
        .prepare(&engine())
        .expect("equal shapes agree");
    let rendered = format!("{plan:?}");
    assert!(
        rendered.contains(r#"steps: ["input", "input", "add"]"#),
        "the view must list the step kinds in schedule order, got {rendered}"
    );
    assert!(
        ["111", "444"].iter().all(|value| !rendered.contains(value)),
        "the view must not print operand buffers, got {rendered}"
    );
}

#[test]
fn a_plan_can_be_executed_more_than_once() {
    let values = Array::from_i64(vec![1, -1]).expr();
    let plan = add()
        .apply(&values, &values)
        .prepare(&engine())
        .expect("equal shapes agree");
    let first = plan.execute().expect("1 + 1 and -1 + -1 fit");
    let second = plan.execute().expect("a plan is reusable");
    assert_eq!(
        first.as_i64_slice(),
        second.as_i64_slice(),
        "a prepared plan holds only immutable inputs, so it yields one answer"
    );
    assert!(
        first.as_i64_slice().map(<[i64]>::as_ptr) != second.as_i64_slice().map(<[i64]>::as_ptr),
        "each execution allocates its own destination"
    );
}
