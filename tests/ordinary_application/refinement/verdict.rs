//! The bridge between the model and the crate's own vocabulary.
//!
//! The comparison is between the model's verdict and the crate's, so neither
//! side may borrow the other's types to state it. `Verdict` is the model's
//! reading, `expectation` produces it from the specification, and `observed`
//! produces it from a real run. A failure kind the model cannot describe reads
//! `None`, which makes a comparison fail rather than pass by omission.

use combobulate::{AExpr, Failure, Stage};

use super::model::{self, Denotation, Outcome};

/// A run's outcome, stated in the model's vocabulary.
#[derive(Debug, PartialEq, Eq)]
pub(super) enum Verdict {
    /// The run produced these values.
    Values(Vec<i64>),
    /// The run failed at `stage`, for these reasons.
    Failed {
        /// The stage's word, as the crate renders it.
        stage: &'static str,
        /// One entry per reported failure.
        failures: Vec<Option<Outcome>>,
    },
}

/// What the lifecycle contract says a run of `graph` produces.
///
/// Preparation precedes execution, so a graph with a static disagreement
/// reports that disagreement: the value error its operands would also produce
/// is never reached.
pub(super) fn expectation(graph: &super::generator::Graph) -> Verdict {
    let static_failures = model::static_failures(graph);
    if !static_failures.is_empty() {
        return Verdict::Failed {
            stage: stage_word(Stage::Preparation),
            failures: static_failures.into_iter().map(Some).collect(),
        };
    }
    match model::eval(graph, graph.root(), &mut std::collections::HashMap::new()) {
        Denotation::Values(values) => Verdict::Values(values),
        Denotation::Failed(failure) => Verdict::Failed {
            stage: stage_word(Stage::Execution),
            failures: vec![Some(failure)],
        },
    }
}

/// What a run of `expression` produced, stated in the model's vocabulary.
pub(super) fn observed(expression: &AExpr) -> Verdict {
    match expression.collect() {
        Ok(array) => Verdict::Values(array.as_i64_slice().unwrap_or_default().to_vec()),
        Err(error) => Verdict::Failed {
            stage: stage_word(error.stage()),
            failures: error.failures().iter().map(describe).collect(),
        },
    }
}

/// What preparation of `expression` reported, in the model's vocabulary.
pub(super) fn observed_preparation(expression: &AExpr) -> Vec<Option<Outcome>> {
    match expression.prepare(&super::super::engine()) {
        Ok(_) => Vec::new(),
        Err(error) => error.failures().iter().map(describe).collect(),
    }
}

/// The word the crate renders a stage with.
///
/// The comparison is on words, not on the enum, so a stage that changed its
/// rendering could not pass by comparing equal to itself.
pub(super) fn stage_word(stage: Stage) -> &'static str {
    match stage {
        Stage::Preparation => "preparation",
        Stage::Execution => "execution",
        _ => "another stage",
    }
}

/// The model's reading of one crate failure.
fn describe(failure: &Failure) -> Option<Outcome> {
    match failure {
        Failure::ShapeAgreement {
            lhs_len, rhs_len, ..
        } => Some(Outcome::Shape {
            lhs_len: *lhs_len,
            rhs_len: *rhs_len,
        }),
        Failure::IntegerOverflow { position, .. } => Some(Outcome::Overflow {
            position: *position,
        }),
        _ => None,
    }
}
