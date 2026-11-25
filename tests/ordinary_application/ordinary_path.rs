//! BDD bindings for identity and add over I64 vectors.
//!
//! The feature file states the ordinary path in the vocabulary a caller uses:
//! apply a unary or binary operation, prepare, execute or collect, and read
//! the result. These steps are that vocabulary over the public API only, so a
//! scenario fails when the facade's own story changes, not when an internal
//! helper is reorganised.
//!
//! The vector placeholders parse through [`I64Vector`], whose `FromStr`
//! accepts the `[1, 2, 3]` spelling the feature uses and an empty `[]`. A
//! scenario that never applied its operation leaves the result slot empty, and
//! each `Then` step reports that rather than comparing against a placeholder.

use std::str::FromStr;

use combobulate::{Array, ExpressionError, Failure, PreparedPlan, add, identity};
use combobulate_test_macros::allow_fixture_expansion_lints;
use rstest_bdd::Slot;
use rstest_bdd_macros::{ScenarioState, given, scenario, then, when};

use super::{buffer_ptr, engine};

/// An I64 operand read from a feature-file placeholder.
///
/// The placeholder text is the same `[1, 2, 3]` a programmer writes, so the
/// feature reads like the expression it describes. Parsing lives here rather
/// than in each step because every `Given` in the file uses this one spelling
/// and a second parser would be a second rule for the same literal.
#[derive(Debug, PartialEq, Eq)]
struct I64Vector(Vec<i64>);

impl FromStr for I64Vector {
    type Err = String;

    fn from_str(text: &str) -> Result<Self, Self::Err> {
        let inner = text
            .strip_prefix('[')
            .and_then(|rest| rest.strip_suffix(']'))
            .ok_or_else(|| format!("an I64 vector must be written as [1, 2, 3], got {text:?}"))?;
        let trimmed = inner.trim();
        if trimmed.is_empty() {
            return Ok(Self(Vec::new()));
        }
        let values = trimmed
            .split(',')
            .map(|item| {
                item.trim()
                    .parse::<i64>()
                    .map_err(|error| format!("{item:?} is not an I64 value: {error}"))
            })
            .collect::<Result<Vec<i64>, String>>()?;
        Ok(Self(values))
    }
}

/// The world one scenario builds up.
///
/// Every field is a [`Slot`] because the feature's `Given` steps name one or
/// two operands in either order and define operands together with the
/// expression, so a scenario that names fewer operands than another cannot be
/// served by a fixed set of fields.
#[derive(Default, ScenarioState)]
struct World {
    /// The first operand, as the caller supplied it.
    left: Slot<Array>,
    /// The second operand, for the scenarios that add two vectors.
    right: Slot<Array>,
    /// The collected result, when a `When` step collected one.
    collected: Slot<Array>,
    /// The plan a `When` step prepared, when preparation succeeded.
    plan: Slot<PreparedPlan>,
    /// The error preparation reported, when it failed.
    preparation: Slot<ExpressionError>,
    /// The pointer of the first operand's buffer, taken before any step ran.
    left_origin: Slot<Option<*const i64>>,
    /// The pointer of the second operand's buffer, taken before any step ran.
    right_origin: Slot<Option<*const i64>>,
    /// The values the first operand held, taken before any step ran.
    left_values: Slot<Vec<i64>>,
    /// The values the second operand held, taken before any step ran.
    right_values: Slot<Vec<i64>>,
}

// `#[fixture]` expands a single-expression body into a nested block, which
// `unused_braces` rejects. The attribute states the suppression once, at the
// macro boundary, rather than copying the pair onto every fixture.
#[allow_fixture_expansion_lints]
#[rstest::fixture]
fn world() -> World { World::default() }

/// Records `array` as the first operand, as it was before any step ran.
///
/// The values are saved alongside the pointer because a shared buffer can be
/// rewritten in place: a step that compares only pointers would accept an
/// addition that overwrote its operands' storage, which is the defect the
/// "unchanged" scenario exists to rule out.
fn record_left(world: &World, array: Array) {
    world.left_origin.set(buffer_ptr(&array));
    world.left_values.set(operand_values(&array));
    world.left.set(array);
}

/// Records `array` as the second operand, as it was before any step ran.
fn record_right(world: &World, array: Array) {
    world.right_origin.set(buffer_ptr(&array));
    world.right_values.set(operand_values(&array));
    world.right.set(array);
}

/// The I64 values `array` currently holds, which an operand may not change.
fn operand_values(array: &Array) -> Vec<i64> {
    array
        .as_i64_slice()
        .expect("this scenario's operands are I64 vectors")
        .to_vec()
}

/// The first operand, which a scenario that names none has not supplied.
fn left(world: &World) -> Array {
    world
        .left
        .get()
        .expect("a scenario must supply its first operand with a `Given` step")
}

/// The second operand, which the two-operand scenarios supply.
fn right(world: &World) -> Array {
    world
        .right
        .get()
        .expect("this scenario must supply its second operand with a `Given` step")
}

/// The collected result, which a collecting `When` step must have set.
fn collected(world: &World) -> Array {
    world
        .collected
        .get()
        .expect("a scenario's `When` step must collect a result before its `Then` steps")
}

/// The error preparation reported, for the scenarios that expect one.
fn preparation_error(world: &World) -> ExpressionError {
    world
        .preparation
        .get()
        .expect("this scenario expects preparation to report an error")
}

#[given("an I64 vector {values}")]
fn an_i64_vector(world: &World, values: I64Vector) {
    record_left(world, Array::from_i64(values.0));
}

#[given("another I64 vector {values}")]
fn another_i64_vector(world: &World, values: I64Vector) {
    record_right(world, Array::from_i64(values.0));
}

#[when("identity is applied and the expression is collected")]
fn identity_is_collected(world: &World) {
    let result = left(world)
        .expr()
        .then(&identity())
        .collect()
        .expect("an identity has no shape to disagree about and cannot overflow");
    world.collected.set(result);
}

#[when("add is applied, the expression is prepared, and the plan is executed")]
fn add_is_prepared_and_executed(world: &World) {
    let sum = add().apply(&left(world).expr(), &right(world).expr());
    match sum.prepare(&engine()) {
        Ok(plan) => match plan.execute() {
            Ok(result) => world.collected.set(result),
            Err(error) => panic!("this scenario's sums all fit, but execution reported {error}"),
        },
        Err(error) => world.preparation.set(error),
    }
}

#[when("add is applied and the expression is collected")]
fn add_is_collected(world: &World) {
    let result = add()
        .apply(&left(world).expr(), &right(world).expr())
        .collect()
        .expect("this scenario adds vectors whose sums all fit");
    world.collected.set(result);
}

#[when("add is applied and the expression is prepared")]
fn add_is_prepared(world: &World) {
    let sum = add().apply(&left(world).expr(), &right(world).expr());
    match sum.prepare(&engine()) {
        Ok(plan) => world.plan.set(plan),
        Err(error) => world.preparation.set(error),
    }
}

#[then("the result is {expected}")]
fn the_result_is(world: &World, expected: I64Vector) {
    assert_eq!(
        collected(world).as_i64_slice(),
        Some(expected.0.as_slice()),
        "the collected result must be the values this scenario states"
    );
}

#[then("the result shares the input buffer")]
fn the_result_shares_the_input(world: &World) {
    let origin = world
        .left_origin
        .get()
        .expect("the `Given` step must record the input's buffer");
    assert_eq!(
        buffer_ptr(&collected(world)),
        origin,
        "identity must return the buffer it was given, not a copy"
    );
}

#[then("both inputs are unchanged")]
fn both_inputs_are_unchanged(world: &World) {
    let left_origin = world
        .left_origin
        .get()
        .expect("the first operand must be recorded");
    let left_values = world
        .left_values
        .get()
        .expect("the first operand's values must be recorded");
    let right_origin = world
        .right_origin
        .get()
        .expect("the second operand must be recorded");
    let right_values = world
        .right_values
        .get()
        .expect("the second operand's values must be recorded");
    // The pointer and the contents are separate claims. A shared buffer keeps
    // its address while its contents change, so the pointer alone would pass
    // for an addition that wrote over its first operand.
    assert_eq!(
        buffer_ptr(&left(world)),
        left_origin,
        "an addition must not replace the first operand's buffer"
    );
    assert_eq!(
        operand_values(&left(world)),
        left_values,
        "an addition must not overwrite the first operand's values in place"
    );
    assert_eq!(
        buffer_ptr(&right(world)),
        right_origin,
        "an addition must not replace the second operand's buffer"
    );
    assert_eq!(
        operand_values(&right(world)),
        right_values,
        "an addition must not overwrite the second operand's values in place"
    );
}

#[then("preparation fails with ShapeAgreement between lengths {lhs:usize} and {rhs:usize}")]
fn preparation_fails_with_shape_agreement(world: &World, lhs: usize, rhs: usize) {
    let failure = *preparation_error(world)
        .failures()
        .first()
        .expect("a failed preparation must report at least one failure");
    assert_eq!(
        failure.code(),
        "ShapeAgreement",
        "a length disagreement is the shape failure, not another one"
    );
    assert!(
        matches!(
            failure,
            Failure::ShapeAgreement {
                lhs_len: reported_lhs,
                rhs_len: reported_rhs,
                ..
            } if reported_lhs == lhs && reported_rhs == rhs
        ),
        "preparation must name the two lengths it saw ({lhs} and {rhs}), got {failure:?}"
    );
}

#[then("preparation succeeds")]
fn preparation_succeeds(world: &World) {
    assert!(
        world.plan.is_filled() && world.preparation.is_empty(),
        "this scenario's operands disagree about no shape, so preparation must succeed"
    );
}

#[then("executing the plan fails with IntegerOverflow at position {position:usize}")]
fn execution_fails_with_overflow(world: &World, position: usize) {
    let plan = world
        .plan
        .get()
        .expect("the `When` step must have prepared a plan");
    let error = plan
        .execute()
        .expect_err("this scenario's sums leave the I64 range at one position");
    let failure = *error
        .failures()
        .first()
        .expect("a failed execution must report at least one failure");
    assert!(
        matches!(
            failure,
            Failure::IntegerOverflow {
                position: reported,
                ..
            } if reported == position
        ),
        "execution must name position {position}, got {failure:?}"
    );
}

/// Binds the identity-sharing scenario.
#[scenario(
    path = "tests/features/ordinary_application.feature",
    name = "Identity shares the input buffer"
)]
fn identity_shares_the_input_buffer(world: World) {
    assert!(
        world.collected.is_filled(),
        "every `Then` step depends on the `When` step having collected"
    );
}

/// Binds the explicit-preparation addition scenario.
#[scenario(
    path = "tests/features/ordinary_application.feature",
    name = "Adding two vectors after explicit preparation"
)]
fn adding_two_vectors_after_explicit_preparation(world: World) {
    assert!(
        world.collected.is_filled(),
        "every `Then` step depends on the plan having executed"
    );
}

/// Binds the empty-vector addition scenario.
#[scenario(
    path = "tests/features/ordinary_application.feature",
    name = "Adding empty vectors"
)]
fn adding_empty_vectors(world: World) {
    assert!(
        world.collected.is_filled(),
        "every `Then` step depends on the `When` step having collected"
    );
}

/// Binds the mismatched-lengths scenario.
#[scenario(
    path = "tests/features/ordinary_application.feature",
    name = "Mismatched lengths fail at preparation"
)]
fn mismatched_lengths_fail_at_preparation(world: World) {
    assert!(
        world.preparation.is_filled(),
        "the `Then` step depends on preparation having failed"
    );
}

/// Binds the overflow-outranks-preparation scenario.
#[scenario(
    path = "tests/features/ordinary_application.feature",
    name = "Overflow fails at execution, not preparation"
)]
fn overflow_fails_at_execution_not_preparation(world: World) {
    assert!(
        world.plan.is_filled(),
        "the `Then` steps depend on preparation having succeeded"
    );
}
