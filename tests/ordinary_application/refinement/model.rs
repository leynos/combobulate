//! The abstract model: static lengths, denotations, and static failures.
//!
//! Every function here is a statement of the specification, not of the crate.
//! They share no code with the implementation under test and never call the
//! kernel: sums are formed in `i128`, so no step of a check can itself
//! overflow and disagree with the model it is checking.
//!
//! The spec is copied from the plan's Verification plan:
//!
//! ```plaintext
//! len(input a)     = Some(|a.s|)
//! len(identity(e)) = len(e)
//! len(add(l, r))   = Some(m) if len(l) = Some(m) = len(r), else None
//! mismatch(n)     iff n = add(l, r), len(l) = Some(a), len(r) = Some(b), a ≠ b
//! ⟦add(l, r)⟧      = ⟦l⟧ >>= λx. ⟦r⟧ >>= λy. addv(x, y)
//! ```
//!
//! A shared node has one denotation however often it is referenced, so both
//! passes memoize by index.

use std::collections::{HashMap, HashSet};

use super::generator::{Graph, NodeSpec};

/// What the model's denotation of one node is.
#[derive(Clone, Debug)]
pub(super) enum Denotation {
    /// The node's values.
    Values(Vec<i64>),
    /// The first failure the node's evaluation met.
    Failed(Outcome),
}

/// What the model says went wrong, independent of the crate's own types.
///
/// The oracle reports what it means, not what the implementation renders: the
/// comparison is between the model's verdict and the crate's, so the oracle
/// must not borrow the crate's vocabulary to state it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum Outcome {
    /// Two operands disagreed about length.
    Shape {
        /// The left operand's length.
        lhs_len: usize,
        /// The right operand's length.
        rhs_len: usize,
    },
    /// A sum left the I64 range at the least such position.
    Overflow {
        /// The least overflowing position.
        position: usize,
    },
}

/// The model's static length of node `at`, memoized by index.
pub(super) fn length(
    graph: &Graph,
    at: usize,
    memo: &mut HashMap<usize, Option<usize>>,
) -> Option<usize> {
    if let Some(known) = memo.get(&at) {
        return *known;
    }
    let length = length_of(graph, at, memo);
    memo.insert(at, length);
    length
}

/// Computes one node's static length, consulting `memo` for its operands.
fn length_of(graph: &Graph, at: usize, memo: &mut HashMap<usize, Option<usize>>) -> Option<usize> {
    if let Some(values) = graph.inputs.get(at) {
        return Some(values.len());
    }
    match graph.spec_at(at) {
        Some(NodeSpec::Identity { of }) => self::length(graph, *of, memo),
        Some(NodeSpec::Add { lhs, rhs }) => agreed(
            self::length(graph, *lhs, memo),
            self::length(graph, *rhs, memo),
        ),
        None => None,
    }
}

/// The length two operands agree on, when both have one.
fn agreed(lhs: Option<usize>, rhs: Option<usize>) -> Option<usize> {
    match (lhs, rhs) {
        (Some(left), Some(right)) if left == right => Some(left),
        _ => None,
    }
}

/// The model's denotation of node `at`, memoized by index.
pub(super) fn eval(graph: &Graph, at: usize, memo: &mut HashMap<usize, Denotation>) -> Denotation {
    if let Some(known) = memo.get(&at) {
        return known.clone();
    }
    let denotation = denote(graph, at, memo);
    memo.insert(at, denotation.clone());
    denotation
}

/// Computes one node's denotation, consulting `memo` for its operands.
fn denote(graph: &Graph, at: usize, memo: &mut HashMap<usize, Denotation>) -> Denotation {
    if let Some(values) = graph.inputs.get(at) {
        return Denotation::Values(values.clone());
    }
    match graph.spec_at(at) {
        Some(NodeSpec::Identity { of }) => eval(graph, *of, memo),
        Some(NodeSpec::Add { lhs, rhs }) => {
            let left = eval(graph, *lhs, memo);
            let right = eval(graph, *rhs, memo);
            and_then(left, right)
        }
        None => Denotation::Failed(Outcome::Shape {
            lhs_len: 0,
            rhs_len: 0,
        }),
    }
}

/// The model's `>>=` for an addition's two operands.
fn and_then(left: Denotation, right: Denotation) -> Denotation {
    match (left, right) {
        (Denotation::Values(lhs), Denotation::Values(rhs)) => addv(&lhs, &rhs),
        // The left operand's failure wins, as the model's `>>=` says.
        (Denotation::Failed(failure), _) | (_, Denotation::Failed(failure)) => {
            Denotation::Failed(failure)
        }
    }
}

/// The model's `addv`, evaluated in `i128` so no step of the check can itself
/// overflow.
fn addv(left: &[i64], right: &[i64]) -> Denotation {
    if left.len() != right.len() {
        return Denotation::Failed(Outcome::Shape {
            lhs_len: left.len(),
            rhs_len: right.len(),
        });
    }
    let mut sums = Vec::with_capacity(left.len());
    for (position, (lhs, rhs)) in left.iter().zip(right).enumerate() {
        let wide = i128::from(*lhs) + i128::from(*rhs);
        match i64::try_from(wide) {
            Ok(sum) => sums.push(sum),
            Err(_) => return Denotation::Failed(Outcome::Overflow { position }),
        }
    }
    Denotation::Values(sums)
}

/// The state of one pass collecting the model's static failures.
#[derive(Default)]
struct StaticPass {
    /// Nodes already visited, so a shared subterm is one root cause.
    visited: HashSet<usize>,
    /// Each node's static length, memoized by index.
    lengths: HashMap<usize, Option<usize>>,
    /// The failures found so far, in first-completion left-first post-order.
    failures: Vec<Outcome>,
}

impl StaticPass {
    /// Collects the failures beneath `at`.
    fn visit(&mut self, graph: &Graph, at: usize) {
        if !self.visited.insert(at) {
            return;
        }
        match graph.spec_at(at) {
            None => (),
            Some(NodeSpec::Identity { of }) => self.visit(graph, *of),
            Some(NodeSpec::Add { lhs, rhs }) => {
                self.visit(graph, *lhs);
                self.visit(graph, *rhs);
                self.record(graph, *lhs, *rhs);
            }
        }
    }

    /// Records the mismatch this addition is the root cause of, if any.
    fn record(&mut self, graph: &Graph, lhs: usize, rhs: usize) {
        let left = length(graph, lhs, &mut self.lengths);
        let right = length(graph, rhs, &mut self.lengths);
        if let (Some(a), Some(b)) = (left, right)
            && a != b
        {
            self.failures.push(Outcome::Shape {
                lhs_len: a,
                rhs_len: b,
            });
        }
    }
}

/// The model's `static(e)`: each mismatch node once, in first-completion
/// left-first post-order.
pub(super) fn static_failures(graph: &Graph) -> Vec<Outcome> {
    let mut pass = StaticPass::default();
    pass.visit(graph, graph.root());
    pass.failures
}
