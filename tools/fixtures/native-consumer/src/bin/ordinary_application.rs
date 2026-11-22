//! An ordinary downstream program that uses the facade's expression path.
//!
//! `tests/native_consumer_e2e.rs` builds and runs this binary beside the
//! profile binary, so FACADE-7 is proved by a real consumer rather than by a
//! test inside the workspace: it names every public type in a signature, runs
//! the three phases a caller uses, and never mentions the kernel crate.
//!
//! Only the public API appears here. A type that grew a type parameter, a
//! method that needed a trait import, or an error that could not be formatted
//! would fail to compile in this crate, which is outside the workspace and
//! takes the facade with default features off.
//!
//! Every signature below takes or returns a facade type by name rather than
//! letting inference supply it. That is the point of the fixture: a caller
//! that only ever writes `let x = …;` would still compile against a type that
//! had become unnameable, so the parameters and return types are spelled out.

use combobulate::{
    AExpr, Array, Binary, Dtype, ExpressionError, Failure, NativeExecutor, OperationId,
    PreparedPlan, Stage, Unary, add, identity,
};

/// Runs the program's four phases and prints one line each.
fn main() {
    let input = Array::from_i64(vec![1_i64, 2, 3]);
    let right = Array::from_i64(vec![10, 20, 30]);

    println!("identity: {:?} (shared buffer: {})", identity_of(&input), keeps_buffer(&input));

    let sum = summed(&input, &right);
    println!("add: {:?}", sum);
    println!("dtype: {:?}", dtype_of(&input));

    let executor = engine();
    let prepared = prepared(&executor, &input, &right);
    println!("collect: {:?}", executed(&prepared));
    println!("operation: {}", unary_id(&identity_operation()).name());
    report_stages(&executor);
}

/// Applies the identity, starting from an [`Array`] and naming the [`Unary`].
fn identity_operation() -> Unary { identity() }

/// Applies addition, naming the [`Binary`] it builds.
fn addition() -> Binary { add() }

/// The identity's operand, as the [`AExpr`] a caller passes on.
fn expression_of(array: &Array) -> AExpr { array.expr() }

/// The values the identity yields, or an empty vector if it yielded nothing.
fn identity_of(array: &Array) -> Vec<i64> {
    values(expression_of(array).then(&identity_operation()))
}

/// Whether collecting the identity returned the buffer it was given.
fn keeps_buffer(array: &Array) -> bool {
    let shared = expression_of(array).then(&identity_operation());
    shared
        .collect()
        .is_ok_and(|collected| collected.as_i64_slice().map(<[i64]>::as_ptr) == buffer_of(array))
}

/// The elementwise sum of two arrays, collected without preparation.
fn summed(left: &Array, right: &Array) -> Vec<i64> {
    let sum = addition().apply(&expression_of(left), &expression_of(right));
    values(sum)
}

/// The dtype an [`Array`] reports, as the [`Dtype`] value itself.
fn dtype_of(array: &Array) -> Dtype { array.dtype() }

/// The engine a caller builds, named in a signature so it stays nameable.
///
/// `NativeExecutor` is `#[non_exhaustive]`, so a caller must reach it through
/// one of its constructors. Naming it here is what requires the type to stay
/// nameable; an inferred construction would not.
fn engine() -> NativeExecutor { NativeExecutor::sequential() }

/// Prepares a sum on an [`NativeExecutor`], yielding a [`PreparedPlan`].
fn prepared(
    engine: &NativeExecutor,
    left: &Array,
    right: &Array,
) -> Result<PreparedPlan, ExpressionError> {
    addition()
        .apply(&expression_of(left), &expression_of(right))
        .prepare(engine)
}

/// Executes a plan and returns its values.
fn executed(plan: &Result<PreparedPlan, ExpressionError>) -> Vec<i64> {
    match plan.as_ref().map(PreparedPlan::execute) {
        Ok(Ok(array)) => array
            .as_i64_slice()
            .map(<[i64]>::to_vec)
            .unwrap_or_default(),
        _ => Vec::new(),
    }
}

/// Collects an expression, naming the error type a failure arrives as.
fn values(expression: AExpr) -> Vec<i64> {
    let collected: Result<Array, ExpressionError> = expression.collect();
    collected
        .ok()
        .and_then(|array| array.as_i64_slice().map(<[i64]>::to_vec))
        .unwrap_or_default()
}

/// The [`Stage`] a failure came from, named in a signature so it stays nameable.
fn stage_of(error: &ExpressionError) -> Stage { error.stage() }

/// Describes each [`Stage`] and the [`Failure`] it holds.
///
/// The stage and failure are earned from a real run, because neither can be
/// constructed from outside the crate. Reading them here is what proves both
/// types, and their accessors, reach a downstream caller.
fn report_stages(engine: &NativeExecutor) {
    let disagreement = add()
        .apply(&Array::from_i64(vec![1, 2, 3]).expr(), &Array::from_i64(vec![1, 2]).expr())
        .prepare(engine)
        .expect_err("operands of different lengths cannot be prepared");
    let reported: &[Failure] = disagreement.failures();
    println!("stage: {} failures: {}", stage_of(&disagreement), codes(reported));

    let overflow = add()
        .apply(
            &Array::from_i64(vec![i64::MAX]).expr(),
            &Array::from_i64(vec![1]).expr(),
        )
        .collect()
        .expect_err("a sum past the I64 range cannot be collected");
    println!("stage: {} failures: {}", stage_of(&overflow), codes(overflow.failures()));
}

/// The diagnostic codes of some failures, joined for one printed line.
fn codes(failures: &[Failure]) -> String {
    failures
        .iter()
        .map(Failure::code)
        .collect::<Vec<&'static str>>()
        .join(", ")
}

/// The operation a [`Unary`] names, as the [`OperationId`] value.
fn unary_id(operation: &Unary) -> OperationId { operation.operation_id() }

/// The buffer of an array, or `None` when it has no elements.
fn buffer_of(array: &Array) -> Option<*const i64> {
    array.as_i64_slice().map(<[i64]>::as_ptr)
}
