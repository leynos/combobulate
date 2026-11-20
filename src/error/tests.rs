//! Kernel translation, codes, stage rendering and the error's invariant.

use combobulate_kernel::elementwise_add::AddFailure;
use rstest::rstest;

use super::{ExpressionError, Failure, Stage, failure_from_kernel};
use crate::expr::OperationId;

#[test]
fn a_kernel_length_mismatch_names_the_operands_it_was_given() {
    assert_eq!(
        failure_from_kernel(AddFailure::LengthMismatch, 3, 2),
        Failure::ShapeAgreement {
            operation: OperationId::ADD,
            lhs_len: 3,
            rhs_len: 2,
        },
        "the facade must report the lengths the kernel refused"
    );
}

#[test]
fn a_kernel_overflow_names_the_position_the_kernel_found() {
    assert_eq!(
        failure_from_kernel(AddFailure::Overflow { position: 7 }, 9, 9),
        Failure::IntegerOverflow {
            operation: OperationId::ADD,
            position: 7,
        },
        "the kernel's least position must survive translation unchanged"
    );
}

#[rstest]
#[case::shape(
    Failure::ShapeAgreement {
        operation: OperationId::ADD,
        lhs_len: 1,
        rhs_len: 2,
    },
    "ShapeAgreement"
)]
#[case::overflow(
    Failure::IntegerOverflow {
        operation: OperationId::ADD,
        position: 0,
    },
    "IntegerOverflow"
)]
fn the_code_is_the_registered_name(#[case] failure: Failure, #[case] expected: &str) {
    assert_eq!(
        failure.code(),
        expected,
        "every failure must report its registered error code"
    );
}

#[rstest]
#[case::preparation(Stage::Preparation, "preparation")]
#[case::execution(Stage::Execution, "execution")]
fn the_stage_renders_as_its_own_word(#[case] stage: Stage, #[case] expected: &str) {
    assert_eq!(
        stage.to_string(),
        expected,
        "a stage must render as the word a reader expects"
    );
}

#[rstest]
#[case::shape(
    Failure::ShapeAgreement {
        operation: OperationId::ADD,
        lhs_len: 3,
        rhs_len: 2,
    },
    "add (V001) operands disagree about length: left is 3, right is 2"
)]
#[case::overflow(
    Failure::IntegerOverflow {
        operation: OperationId::ADD,
        position: 4,
    },
    "add (V001) overflows I64 at position 4"
)]
fn a_failure_renders_the_facts_that_made_it_fail(#[case] failure: Failure, #[case] expected: &str) {
    assert_eq!(
        failure.to_string(),
        expected,
        "the rendering must name the operation and the offending fact"
    );
}

#[test]
fn an_error_renders_its_stage_and_every_failure() {
    let error = ExpressionError::new(
        Stage::Preparation,
        vec![
            Failure::ShapeAgreement {
                operation: OperationId::ADD,
                lhs_len: 3,
                rhs_len: 2,
            },
            Failure::ShapeAgreement {
                operation: OperationId::ADD,
                lhs_len: 4,
                rhs_len: 1,
            },
        ],
    );
    assert_eq!(
        error.to_string(),
        concat!(
            "expression failed during preparation\n",
            "- add (V001) operands disagree about length: left is 3, right is 2\n",
            "- add (V001) operands disagree about length: left is 4, right is 1"
        ),
        "one line per failure keeps a multi-failure report readable"
    );
}

#[test]
fn the_error_reports_the_stage_and_failures_it_was_built_from() {
    let failure = Failure::IntegerOverflow {
        operation: OperationId::ADD,
        position: 1,
    };
    let error = ExpressionError::new(Stage::Execution, vec![failure]);
    assert_eq!(
        error.stage(),
        Stage::Execution,
        "the stage must be the one the caller supplied"
    );
    assert_eq!(
        error.failures(),
        &[failure][..],
        "the failures must be reported in the order they were found"
    );
}

#[test]
fn the_error_is_a_std_error_a_caller_can_box() {
    let error = ExpressionError::new(
        Stage::Execution,
        vec![Failure::IntegerOverflow {
            operation: OperationId::ADD,
            position: 0,
        }],
    );
    let boxed: Box<dyn core::error::Error + Send + Sync> = Box::new(error);
    assert!(
        boxed.source().is_none(),
        "the error has no cause of its own, so a caller need not unwind one"
    );
}
