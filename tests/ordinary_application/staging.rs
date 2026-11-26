//! FACADE-6: each failure appears at the stage that can discover it.
//!
//! The two stages exist so a caller can tell "this expression can never work"
//! from "this expression's values did not fit". The distinction is only real
//! if a failing execution still prepares, and a shape failure never reaches
//! execution; both directions are asserted here, in code and through the
//! feature file's scenarios.

use combobulate::{ExpressionError, Failure, PreparedPlan, Stage, add};
use combobulate_test_macros::allow_fixture_expansion_lints;
use rstest_bdd_macros::{given, scenario, then, when};

use super::{engine, expr, single_failure};

/// The world the feature file's scenarios build up.
#[derive(Debug, Default)]
struct World {
    /// The plan the `When` step built, when preparation succeeded.
    plan: Option<PreparedPlan>,
    /// The error preparation reported, when it failed.
    preparation: Option<ExpressionError>,
    /// The error execution reported, when it failed.
    execution: Option<ExpressionError>,
}

// `#[fixture]` expands a single-expression body into a nested block, which
// `unused_braces` rejects. The attribute states the suppression once, at the
// macro boundary, rather than copying the pair onto every fixture.
#[allow_fixture_expansion_lints]
#[rstest::fixture]
fn world() -> World { World::default() }

#[given("two arrays of different lengths")]
fn arrays_of_different_lengths(world: &mut World) {
    let sum = add().apply(&expr(&[1, 2, 3]), &expr(&[1, 2]));
    match sum.prepare(&engine()) {
        Ok(plan) => world.plan = Some(plan),
        Err(error) => world.preparation = Some(error),
    }
}

#[given("two arrays whose sum overflows")]
fn arrays_whose_sum_overflows(world: &mut World) {
    let sum = add().apply(&expr(&[i64::MAX]), &expr(&[1]));
    match sum.prepare(&engine()) {
        Ok(plan) => world.plan = Some(plan),
        Err(error) => world.preparation = Some(error),
    }
}

#[when("a consumer prepares their sum")]
fn prepares_their_sum(_world: &mut World) {}

#[when("a consumer prepares and then executes their sum")]
fn prepares_and_executes(world: &mut World) {
    if let Some(plan) = world.plan.as_ref()
        && let Err(error) = plan.execute()
    {
        world.execution = Some(error);
    }
}

/// The error `world` recorded for `stage`, if that stage reported one.
///
/// The five `Then` steps below assert one property each of a stage's error, so
/// they share this lookup: a step that reached into `World` itself would repeat
/// the field choice and the missing-value diagnostic, and the two fields are
/// the only thing that varies between the preparation and execution cases.
///
/// `Stage` is `#[non_exhaustive]`, so a stage this scenario does not model
/// records nothing. Returning `None` rather than panicking keeps the failure
/// at the `Then` step that asked, where the diagnostic still names the stage
/// it wanted.
fn reported(world: &World, stage: Stage) -> Option<&ExpressionError> {
    match stage {
        Stage::Preparation => world.preparation.as_ref(),
        Stage::Execution => world.execution.as_ref(),
        _ => None,
    }
}

/// The error `world` recorded for `stage`, which every `Then` step requires.
fn reported_error(world: &World, stage: Stage) -> &ExpressionError {
    let diagnosed = match stage {
        Stage::Preparation => "the shape disagreement must be reported by preparation",
        _ => "the overflow must be reported by execution",
    };
    reported(world, stage).expect(diagnosed)
}

#[then("the preparation reports a shape disagreement")]
fn preparation_reports_shape(world: &World) {
    let error = reported_error(world, Stage::Preparation);
    assert_eq!(
        error.failures().first().map(Failure::code),
        Some("ShapeAgreement"),
        "the report must name the shape as the problem"
    );
}

#[then("the preparation succeeds")]
fn preparation_succeeds(world: &World) {
    assert!(
        world.preparation.is_none() && world.plan.is_some(),
        "an overflow is not a static failure, so preparation must succeed"
    );
}

#[then("the execution reports an integer overflow")]
fn execution_reports_overflow(world: &World) {
    let error = reported_error(world, Stage::Execution);
    assert_eq!(
        error.failures().first().map(Failure::code),
        Some("IntegerOverflow"),
        "the report must name the overflow as the problem"
    );
}

#[then("the reported stage is preparation")]
fn stage_is_preparation(world: &World) {
    let error = reported_error(world, Stage::Preparation);
    assert_eq!(
        error.stage(),
        Stage::Preparation,
        "a shape disagreement belongs to preparation"
    );
}

#[then("the reported stage is execution")]
fn stage_is_execution(world: &World) {
    let error = reported_error(world, Stage::Execution);
    assert_eq!(
        error.stage(),
        Stage::Execution,
        "an overflow belongs to execution"
    );
}

/// Binds the shape-disagreement scenario.
#[scenario(
    path = "tests/features/ordinary_application.feature",
    name = "A shape disagreement is reported before execution"
)]
fn shape_disagreement_is_reported_before_execution(world: World) {
    assert!(
        world.preparation.is_some(),
        "every `Then` step depends on the `Given` step having prepared"
    );
}

/// Binds the overflow scenario.
#[scenario(
    path = "tests/features/ordinary_application.feature",
    name = "An overflow is reported only from execution"
)]
fn overflow_is_reported_only_from_execution(world: World) {
    assert!(
        world.execution.is_some(),
        "every `Then` step depends on the `When` step having executed"
    );
}

#[rstest::rstest]
#[case::overflow(i64::MAX, 1, true)]
#[case::no_overflow(1, 1, false)]
fn an_overflowing_expression_prepares_and_fails_at_execution(
    #[case] left: i64,
    #[case] right: i64,
    #[case] should_overflow: bool,
) {
    let plan = add()
        .apply(&expr(&[left]), &expr(&[right]))
        .prepare(&engine())
        .expect("preparation inspects cached facts only, so no value can block it");
    let outcome = plan.execute();
    assert_eq!(
        outcome.is_err(),
        should_overflow,
        "execution must report an overflow exactly when one occurs"
    );
    if let Err(error) = outcome {
        assert_eq!(
            error.stage(),
            Stage::Execution,
            "an overflow discovered while summing belongs to execution"
        );
        let failure = single_failure(&error);
        assert!(
            matches!(failure, Failure::IntegerOverflow { position: 0, .. }),
            "the failure must name the position that overflowed, got {failure:?}"
        );
    }
}

#[test]
fn a_shape_disagreement_never_reaches_execution() {
    let error = add()
        .apply(&expr(&[1, 2, 3]), &expr(&[1, 2]))
        .prepare(&engine())
        .expect_err("unequal lengths cannot be prepared");
    assert_eq!(
        error.stage(),
        Stage::Preparation,
        "the stage must say preparation, not execution"
    );
}

#[test]
fn the_first_failure_names_the_least_position() {
    let plan = add()
        .apply(&expr(&[1, i64::MAX, i64::MAX]), &expr(&[1, 1, 1]))
        .prepare(&engine())
        .expect("an overflow is not a static failure");
    let error = plan.execute().expect_err("position 1 overflows");
    let failure = single_failure(&error);
    assert!(
        matches!(failure, Failure::IntegerOverflow { position: 1, .. }),
        "the least overflowing position is the one reported, not the last, got {failure:?}"
    );
}
