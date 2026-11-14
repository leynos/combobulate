//! The failures an ordinary application path can report.
//!
//! A failure is described where it is decided, not where it is printed. The
//! shape disagreement is decided while the graph is prepared and an overflow
//! while it executes, so each carries the stage it belongs to and the
//! operation that produced it. Preparation may find several independent
//! disagreements at once; execution stops at the first failure, so it always
//! reports exactly one.
//!
//! Codes are the closed names of `spec/semantic-contracts.json`'s
//! `error_codes`, so a consumer can match on a stable string without reading a
//! rendered sentence (technical design §17.5).

use core::fmt::{self, Display, Formatter};

use combobulate_kernel::elementwise_add::AddFailure;

use crate::expr::OperationId;

/// The step of an expression's lifecycle that reported a failure.
///
/// The stage is a property of the expression, not of the failure: an overflow
/// can only be discovered once values are summed, and a shape disagreement can
/// only be discovered once the graph is known in full.
///
/// ```
/// use combobulate::Stage;
///
/// assert_ne!(
///     Stage::Preparation,
///     Stage::Execution,
///     "the two stages must stay distinguishable"
/// );
/// ```
#[non_exhaustive]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stage {
    /// The expression was rejected before any kernel ran.
    Preparation,
    /// The expression was rejected while its values were computed.
    Execution,
}

impl Display for Stage {
    /// Renders the stage as the word a reader needs, e.g. `preparation`.
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Preparation => "preparation",
            Self::Execution => "execution",
        })
    }
}

/// One reason an expression did not produce a value.
///
/// A failure names the operation and the facts that made it fail, so a caller
/// can report the problem without re-deriving it. The variants are
/// `#[non_exhaustive]`: a later release may distinguish more shapes, and a
/// caller matching on them must say what it does with an unknown one.
///
/// The variants cannot be constructed from outside the crate, so a caller
/// meets them by running an expression and reading what it reported:
///
/// ```
/// use combobulate::{Array, NativeExecutor, add};
///
/// let left = Array::from_i64(vec![1, 2, 3]).expr();
/// let right = Array::from_i64(vec![1, 2]).expr();
/// let error = add()
///     .apply(&left, &right)
///     .prepare(&NativeExecutor::sequential())
///     .expect_err("operands of different lengths cannot be prepared");
/// let [failure] = error.failures() else {
///     panic!("one disagreement is one failure");
/// };
/// assert_eq!(failure.code(), "ShapeAgreement");
/// ```
#[non_exhaustive]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Failure {
    /// Two operands of one addition have different lengths.
    #[non_exhaustive]
    ShapeAgreement {
        /// The addition whose operands disagree.
        operation: OperationId,
        /// The left operand's length.
        lhs_len: usize,
        /// The right operand's length.
        rhs_len: usize,
    },
    /// An element's sum leaves the I64 range.
    #[non_exhaustive]
    IntegerOverflow {
        /// The addition whose sum overflowed.
        operation: OperationId,
        /// The least position whose sum leaves the I64 range.
        position: usize,
    },
}

impl Failure {
    /// The registered error code naming this failure.
    ///
    /// The value is one of `spec/semantic-contracts.json`'s `error_codes`, so
    /// it is stable across releases and does not carry the rendered sentence.
    #[must_use]
    pub const fn code(&self) -> &'static str {
        match self {
            Self::ShapeAgreement { .. } => "ShapeAgreement",
            Self::IntegerOverflow { .. } => "IntegerOverflow",
        }
    }
}

impl Display for Failure {
    /// Renders the failure with the operands that produced it.
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        match self {
            Self::ShapeAgreement {
                operation,
                lhs_len,
                rhs_len,
            } => write!(
                formatter,
                "{operation} operands disagree about length: left is {lhs_len}, right is {rhs_len}"
            ),
            Self::IntegerOverflow {
                operation,
                position,
            } => write!(
                formatter,
                "{operation} overflows I64 at position {position}"
            ),
        }
    }
}

/// One or more failures from one stage of one expression's lifecycle.
///
/// Construction is infallible and every field is private, so an
/// `ExpressionError` always holds at least one failure. Preparation collects
/// every independent shape disagreement; execution stops at the first failure,
/// so an execution error holds exactly one.
///
/// ```
/// use combobulate::ExpressionError;
///
/// fn describe(error: &ExpressionError) -> String {
///     format!("{}: {}", error.stage(), error.failures().len())
/// }
///
/// // A caller formats whatever stage it is given.
/// let _ = describe;
/// ```
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExpressionError {
    /// The stage that reported the failures.
    stage: Stage,
    /// The failures, in the order they were found. Never empty.
    failures: Box<[Failure]>,
}

impl ExpressionError {
    /// Wraps the failures one stage reported.
    ///
    /// The caller's slice must be non-empty; this is the invariant the type's
    /// documentation states, and it is checked here rather than left to the
    /// reader of every construction site.
    pub(crate) fn new(stage: Stage, failures: Vec<Failure>) -> Self {
        debug_assert!(
            !failures.is_empty(),
            "an ExpressionError must hold at least one failure"
        );
        Self {
            stage,
            failures: failures.into_boxed_slice(),
        }
    }

    /// The stage that reported these failures.
    #[must_use]
    pub const fn stage(&self) -> Stage { self.stage }

    /// The failures, in the order they were found.
    ///
    /// Preparation reports shape disagreements in first-completion, left-first
    /// post-order; execution reports the single failure it stopped at.
    #[must_use]
    pub fn failures(&self) -> &[Failure] { &self.failures }
}

impl Display for ExpressionError {
    /// Renders the stage and every failure, one per line.
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        write!(formatter, "expression failed during {}", self.stage)?;
        for failure in &self.failures {
            write!(formatter, "\n- {failure}")?;
        }
        Ok(())
    }
}

impl core::error::Error for ExpressionError {}

/// Translates the kernel's failure into the facade's, naming the operands.
///
/// The kernel reports what went wrong with the values it was given; the facade
/// adds the operation that asked for it and, for a shape disagreement, the two
/// lengths the caller supplied. A kernel `LengthMismatch` cannot be turned into
/// a shape disagreement without them, which is why they are parameters rather
/// than something the facade looks up afterwards.
pub(crate) const fn failure_from_kernel(
    failure: AddFailure,
    lhs_len: usize,
    rhs_len: usize,
) -> Failure {
    match failure {
        AddFailure::LengthMismatch => Failure::ShapeAgreement {
            operation: OperationId::ADD,
            lhs_len,
            rhs_len,
        },
        AddFailure::Overflow { position } => Failure::IntegerOverflow {
            operation: OperationId::ADD,
            position,
        },
    }
}

#[cfg(test)]
mod tests;
