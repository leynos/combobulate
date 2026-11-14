//! Preparation and execution of an expression by the native executor.
//!
//! Preparing walks the graph once, iteratively, and records each node as one
//! step of a linear schedule. Every operand's step comes before the step that
//! consumes it, so execution is a plain loop with no hashing and no traversal
//! (DL-12). Preparation also collects every independent shape disagreement, in
//! the order a first-completion, left-first post-order walk reaches them, so a
//! caller learns about all of them at once rather than one per attempt (DL-9).
//!
//! A shared subterm is one node, so it appears in the schedule once however
//! many consumers refer to it. That is what keeps `add(x, x)` from doubling
//! the work at every level, which FACADE-4 measures at 62 levels.
//!
//! Execution runs the kernel only through [`dispatch_add`], the single place a
//! facade operation becomes its verified body (DL-14). An input step shares the
//! buffer it was given, so collecting an expression that is only an input
//! returns that buffer rather than a copy (FACADE-3).

use std::{
    fmt::{self, Debug, Formatter},
    sync::Arc,
};

use combobulate_kernel::elementwise_add::{AddFailure, add_i64_into};
use schedule::Walk;

use crate::{
    array::Array,
    error::{ExpressionError, Stage, failure_from_kernel},
    expr::{AExpr, NodeKind},
};

/// The only execution engine this release has.
///
/// It is a value with no resources yet. Type 017 adds scratch and policies to
/// it later, so it is `#[non_exhaustive]` and not `Copy`: a caller must build
/// one through [`NativeExecutor::sequential`] and must not rely on being able
/// to copy one.
///
/// ```
/// use combobulate::NativeExecutor;
///
/// let engine = NativeExecutor::sequential();
/// assert_eq!(
///     engine,
///     NativeExecutor::default(),
///     "the sequential engine is the default one"
/// );
/// ```
#[non_exhaustive]
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct NativeExecutor {}

impl NativeExecutor {
    /// The engine that evaluates a schedule step by step, in order.
    #[must_use]
    pub const fn sequential() -> Self { Self {} }

    /// Builds the sequence of steps that evaluates `root`.
    ///
    /// The walk is iterative and memoized by node identity: a node reached
    /// twice is expanded once, so the schedule holds one step per distinct
    /// subterm. The identity set holds node addresses only while this call
    /// runs, and the borrowed root keeps every node alive for that long, so no
    /// address can be reused mid-walk and the plan never stores one.
    ///
    /// The plan records this engine rather than merely accepting it, so the
    /// engine that can run a schedule is fixed when the schedule is built.
    /// Type 017's engines will differ in their resources, and a plan must not
    /// silently change hands between preparation and execution.
    fn schedule(&self, root: &AExpr) -> Result<PreparedPlan, ExpressionError> {
        Walk::schedule(root, self)
    }

    /// Runs a prepared schedule and returns the buffer its root occupies.
    ///
    /// Execution is a loop over the steps, because preparation already put
    /// every operand before its consumer. Inputs are lent, never copied, so an
    /// expression that is only an input returns the caller's own buffer
    /// (FACADE-3); only an addition allocates.
    ///
    /// The engine itself is stateless until type 017 gives it scratch and
    /// policies, so this body consults no field of it. The receiver is kept
    /// because the engine owns execution: a plan hands its schedule back to
    /// the engine it was prepared for, which is where those resources will
    /// live, and a free function would lose that hand-off for good.
    #[expect(
        clippy::unused_self,
        reason = "the engine owns execution and will consult its own resources from E017; keeping \
                  the receiver is what carries the plan back to its engine"
    )]
    fn run(&self, steps: &[Step], root: Slot) -> Result<Arc<Vec<i64>>, ExpressionError> {
        let mut results: Vec<Arc<Vec<i64>>> = Vec::with_capacity(steps.len());
        for step in steps {
            let value = match step {
                Step::Input(values) => Arc::clone(values),
                Step::Add { lhs, rhs } => sum(&slot(&results, *lhs), &slot(&results, *rhs))?,
            };
            results.push(value);
        }
        Ok(slot(&results, root))
    }
}

/// One position in a prepared schedule.
///
/// Slots are indices into execution's result vector, numbered in the order the
/// schedule places them. They are deliberately not exposed: a slot means
/// nothing outside the plan that produced it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) struct Slot(usize);

/// One step of a prepared schedule.
///
/// An input step holds the buffer it will publish, so publishing it copies
/// nothing. An addition step names the two slots its operands occupy rather
/// than referring to nodes, which is why the plan holds no graph at all.
#[derive(Clone)]
pub(super) enum Step {
    /// Publish a buffer the expression was given.
    Input(Arc<Vec<i64>>),
    /// Sum the values in two earlier slots.
    Add {
        /// The slot holding the left operand.
        lhs: Slot,
        /// The slot holding the right operand.
        rhs: Slot,
    },
}

/// An expression whose shape has been settled and whose steps are ordered.
///
/// A plan can be executed more than once and yields the same values each time,
/// because it holds only immutable inputs and its own instructions.
///
/// ```
/// use combobulate::{Array, NativeExecutor};
///
/// let expression = Array::from_i64(vec![1, 2, 3]).expr();
/// let plan = expression
///     .prepare(&NativeExecutor::sequential())
///     .expect("an input has no shape to disagree about");
/// let first = plan.execute().expect("an input cannot overflow");
/// let second = plan.execute().expect("a plan may be executed again");
/// assert_eq!(
///     first.as_i64_slice(),
///     second.as_i64_slice(),
///     "executing one plan twice must yield the same values"
/// );
/// ```
#[derive(Clone)]
pub struct PreparedPlan {
    /// The steps, in dependency order.
    steps: Box<[Step]>,
    /// The slot holding the expression's own value.
    root: Slot,
    /// The engine this plan was prepared for, and the one that will run it.
    engine: NativeExecutor,
}

impl PreparedPlan {
    /// Evaluate the plan and return its array.
    ///
    /// # Errors
    ///
    /// Returns an [`ExpressionError`] whose stage is [`Stage::Execution`] and
    /// which holds exactly one [`crate::Failure::IntegerOverflow`], naming the least
    /// position whose sum leaves the I64 range. Nothing is published then.
    ///
    /// # Examples
    ///
    /// ```
    /// use combobulate::{Array, NativeExecutor, add};
    ///
    /// let wide = Array::from_i64(vec![1, 2]).expr();
    /// let plan = add()
    ///     .apply(&wide, &wide)
    ///     .prepare(&NativeExecutor::sequential())
    ///     .expect("equal lengths agree");
    /// assert_eq!(
    ///     plan.execute().expect("1 + 1 fits").as_i64_slice(),
    ///     Some(&[2_i64, 4][..]),
    ///     "execution sums the operands pointwise"
    /// );
    /// ```
    pub fn execute(&self) -> Result<Array, ExpressionError> {
        self.engine
            .run(&self.steps, self.root)
            .map(Array::from_shared)
    }
}

impl Debug for PreparedPlan {
    /// Reports the schedule's shape without printing any buffer.
    ///
    /// A derived implementation would print every input's elements, which for
    /// a plan over a deep chain is both unreadable and large. The step kinds in
    /// order say everything a reader needs to judge the schedule.
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        let kinds: Vec<&str> = self
            .steps
            .iter()
            .map(|step| match step {
                Step::Input(_) => "input",
                Step::Add { .. } => "add",
            })
            .collect();
        formatter
            .debug_struct("PreparedPlan")
            .field("steps", &kinds)
            .field("root", &self.root)
            .field("engine", &self.engine)
            .finish()
    }
}

/// Reads one finished slot's value.
///
/// The schedule places every operand's step before the step that consumes it,
/// so each index a prepared plan reads is in bounds by construction. FACADE-1
/// and FACADE-4 exercise schedules of every generated shape; an index out of
/// bounds here would be a preparation bug that both would expose.
#[expect(
    clippy::indexing_slicing,
    reason = "the post-order schedule places every operand slot before its consumer, so each read \
              is in bounds by construction; FACADE-1 and FACADE-4 are the evidence"
)]
fn slot(results: &[Arc<Vec<i64>>], index: Slot) -> Arc<Vec<i64>> { Arc::clone(&results[index.0]) }

/// Sums two operand slices, translating the kernel's verdict.
///
/// The destination is allocated here and released on any failure, so a failed
/// addition publishes nothing (DL-7's frame, lifted to the facade).
fn sum(left: &[i64], right: &[i64]) -> Result<Arc<Vec<i64>>, ExpressionError> {
    let mut out = vec![0_i64; left.len()];
    dispatch_add(left, right, &mut out).map_err(|failure| {
        ExpressionError::new(
            Stage::Execution,
            vec![failure_from_kernel(failure, left.len(), right.len())],
        )
    })?;
    Ok(Arc::new(out))
}

/// Runs the verified kernel for the catalogue's `add` entry (V001).
///
/// This is the facade's only route to an arithmetic body (DL-14). A unit test
/// checks that the descriptor's identity names this kernel, so a later
/// operation cannot be routed to the wrong function without failing it.
const fn dispatch_add(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> Result<(), AddFailure> {
    add_i64_into(lhs, rhs, out)
}

/// The frames that schedule one node's children, right first so left runs
/// first.
pub(super) fn child_frames(handle: &AExpr) -> Vec<Frame> {
    match &handle.node.kind {
        NodeKind::Input(_) => Vec::new(),
        NodeKind::Add { lhs, rhs } => vec![Frame::Expand(rhs.clone()), Frame::Expand(lhs.clone())],
    }
}

/// One item of preparation's work list.
pub(super) enum Frame {
    /// Expand this node's children, then finish it.
    Expand(AExpr),
    /// Record this node now that its children are recorded.
    Finish(AExpr),
}

impl AExpr {
    /// Settle the expression's shape and order its steps.
    ///
    /// Preparation runs no kernel: it inspects the graph's cached facts only,
    /// so an expression whose execution will overflow still prepares
    /// (FACADE-6).
    ///
    /// # Errors
    ///
    /// Returns an [`ExpressionError`] whose stage is [`Stage::Preparation`],
    /// holding one [`crate::Failure::ShapeAgreement`] per root-cause disagreement in
    /// first-completion, left-first post-order.
    ///
    /// # Examples
    ///
    /// ```
    /// use combobulate::{Array, NativeExecutor, add};
    ///
    /// let wide = Array::from_i64(vec![1, 2]).expr();
    /// let narrow = Array::from_i64(vec![1]).expr();
    /// let error = add()
    ///     .apply(&wide, &narrow)
    ///     .prepare(&NativeExecutor::sequential())
    ///     .expect_err("unequal lengths cannot be prepared");
    /// assert_eq!(
    ///     error.failures().first().map(combobulate::Failure::code),
    ///     Some("ShapeAgreement"),
    ///     "the shape is the first thing a failed preparation reports"
    /// );
    /// ```
    pub fn prepare(&self, engine: &NativeExecutor) -> Result<PreparedPlan, ExpressionError> {
        engine.schedule(self)
    }

    /// Prepare and execute with the default engine.
    ///
    /// # Errors
    ///
    /// Returns whatever [`AExpr::prepare`] or [`PreparedPlan::execute`] would,
    /// with its stage saying which of the two rejected the expression.
    ///
    /// # Examples
    ///
    /// ```
    /// use combobulate::{Array, add};
    ///
    /// let values = Array::from_i64(vec![1, 2, 3]);
    /// let doubled = add().apply(&values.expr(), &values.expr()).collect();
    /// assert_eq!(
    ///     doubled.expect("3 + 3 fits").as_i64_slice(),
    ///     Some(&[2_i64, 4, 6][..]),
    ///     "collecting is preparation followed by execution"
    /// );
    /// ```
    pub fn collect(&self) -> Result<Array, ExpressionError> {
        self.prepare(&NativeExecutor::sequential())?.execute()
    }
}

mod schedule;
#[cfg(test)]
mod tests;
