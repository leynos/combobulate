//! Preparation's iterative, memoized walk over an expression graph.
//!
//! The walk is its own module because it is the one part of planning that is a
//! state machine: a frame stack, a set of nodes already scheduled, and a map
//! from node to slot. Keeping it apart from the plan it produces lets the
//! schedule be read as a procedure and the plan as a value.
//!
//! The walk is a first-completion, left-first post-order traversal expressed
//! with an explicit stack. Expanding a node queues its own finish and then its
//! children, right before left, so the left child finishes first; a node
//! already scheduled is not expanded again, which is what makes a shared
//! subterm one step (DL-12).

use std::{
    collections::{HashMap, HashSet},
    sync::Arc,
};

use super::{Frame, NativeExecutor, PreparedPlan, Slot, Step, child_frames};
use crate::{
    error::{ExpressionError, Failure, Stage},
    expr::{AExpr, Node, NodeKind, OperationId},
};

/// The state preparation's iterative walk accumulates.
#[derive(Default)]
pub(super) struct Walk {
    /// Nodes still to expand or finish, innermost last.
    stack: Vec<Frame>,
    /// Nodes whose step is already recorded, so a shared subterm is one step.
    seen: HashSet<*const Node>,
    /// The slot each recorded node occupies.
    slots: HashMap<*const Node, Slot>,
    /// The steps, in dependency order.
    steps: Vec<Step>,
    /// Every root-cause shape disagreement found so far.
    mismatches: Vec<Failure>,
}

impl Walk {
    /// Walks the whole graph beneath `root` and returns its plan.
    pub(super) fn schedule(
        root: &AExpr,
        engine: &NativeExecutor,
    ) -> Result<PreparedPlan, ExpressionError> {
        let mut walk = Self::default();
        walk.stack.push(Frame::Expand(root.clone()));
        while let Some(frame) = walk.stack.pop() {
            walk.apply(frame);
        }
        walk.outcome(engine)
    }

    /// Applies one frame of the walk.
    fn apply(&mut self, frame: Frame) {
        match frame {
            Frame::Expand(handle) => self.expand(&handle),
            Frame::Finish(handle) => self.finish(&handle),
        }
    }

    /// Queues a node's children, and its own finish, unless it is already
    /// scheduled.
    fn expand(&mut self, handle: &AExpr) {
        if !self.seen.insert(Arc::as_ptr(&handle.node)) {
            return;
        }
        self.stack.push(Frame::Finish(handle.clone()));
        self.stack.extend(child_frames(handle));
    }

    /// Records a node whose children are recorded, and any failure it causes.
    fn finish(&mut self, handle: &AExpr) {
        record(
            handle,
            &mut self.slots,
            &mut self.steps,
            &mut self.mismatches,
        );
    }

    /// Returns the plan prepared for `engine`, or every disagreement found.
    fn outcome(self, engine: &NativeExecutor) -> Result<PreparedPlan, ExpressionError> {
        if !self.mismatches.is_empty() {
            return Err(ExpressionError::new(Stage::Preparation, self.mismatches));
        }
        Ok(PreparedPlan {
            root: Slot(self.steps.len().saturating_sub(1)),
            steps: self.steps.into_boxed_slice(),
            engine: engine.clone(),
        })
    }
}

/// Records one finished node's step, and any disagreement it is the cause of.
///
/// Both operands have been expanded by now, so their slots are known. A node
/// is a root-cause disagreement exactly when both operands have a known length
/// and those lengths differ, which is why an ancestor of an unknown length
/// reports nothing of its own (DL-9).
fn record(
    handle: &AExpr,
    slots: &mut HashMap<*const Node, Slot>,
    steps: &mut Vec<Step>,
    mismatches: &mut Vec<Failure>,
) {
    let here = Slot(steps.len());
    match &handle.node.kind {
        NodeKind::Input(values) => steps.push(Step::Input(Arc::clone(values))),
        NodeKind::Inert => {}
        NodeKind::Add { lhs, rhs } => {
            record_mismatch(handle, lhs, rhs, mismatches);
            // Both slots exist: the walk finishes every operand before its
            // consumer, and `seen` means a shared operand is expanded once.
            steps.push(Step::Add {
                lhs: slot_of(slots, lhs),
                rhs: slot_of(slots, rhs),
            });
        }
    }
    slots.insert(Arc::as_ptr(&handle.node), here);
}

/// Records the shape disagreement this node causes, if it causes one.
///
/// The cached flag is what makes most nodes a cheap rejection: a mismatch can
/// only lie at or beneath a node that carries it.
fn record_mismatch(handle: &AExpr, lhs: &AExpr, rhs: &AExpr, mismatches: &mut Vec<Failure>) {
    let (Some(lhs_len), Some(rhs_len)) = (lhs.node.length, rhs.node.length) else {
        return;
    };
    if handle.node.mismatch_below && lhs_len != rhs_len {
        mismatches.push(Failure::ShapeAgreement {
            operation: OperationId::ADD,
            lhs_len,
            rhs_len,
        });
    }
}

/// The slot an already-expanded operand occupies.
///
/// # Panics
///
/// Panics if `operand` has not been expanded. The walk expands both operands
/// before their consumer and expands each node once, so no caller can reach
/// that state; failing loudly is what stops a schedule from silently losing a
/// step if the guard it relies on is ever weakened. FACADE-1 and FACADE-4
/// quantify over every generated graph shape and are the evidence.
fn slot_of(slots: &HashMap<*const Node, Slot>, operand: &AExpr) -> Slot {
    slots[&Arc::as_ptr(&operand.node)]
}
