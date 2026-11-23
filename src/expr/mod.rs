//! Deferred expression handles over I64 arrays.
//!
//! An [`AExpr`] is a cheap, shared handle to one node of a directed acyclic
//! graph. Building an expression copies no elements and runs no kernel: it only
//! records what to do later. Two facts are cached on each node while it is
//! built — its length under the partial static model (DL-9) and whether any
//! node beneath it disagrees about length — so preparation can report shape
//! failures without walking the graph or touching a value.
//!
//! The graph is heap-shaped and arbitrarily deep, so nothing here recurses. A
//! deep chain is dropped and formatted by explicit work lists, which is what
//! keeps a 100,000-node chain within a small thread's stack (FACADE-5).

use std::{
    fmt::{self, Debug, Formatter},
    sync::Arc,
};

/// The identity of one operation in the catalogue.
///
/// The name is the word a user writes and the catalogue id is the entry that
/// specifies it, so a diagnostic can cite both without holding a reference to
/// the catalogue.
///
/// ```
/// use combobulate::{add, identity};
///
/// assert_eq!(identity().operation_id().name(), "identity");
/// assert_eq!(add().operation_id().catalogue_id(), "V001");
/// ```
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct OperationId {
    /// The verb a user writes, such as `identity`.
    name: &'static str,
    /// The catalogue entry that specifies the operation, such as `V032`.
    catalogue_id: &'static str,
}

impl OperationId {
    /// The operation that returns its operand unchanged.
    const IDENTITY: Self = Self {
        name: "identity",
        catalogue_id: "V032",
    };

    /// The operation that sums two arrays elementwise.
    pub(crate) const ADD: Self = Self {
        name: "add",
        catalogue_id: "V001",
    };

    /// The verb a user writes for this operation.
    #[must_use]
    pub const fn name(self) -> &'static str { self.name }

    /// The catalogue entry that specifies this operation.
    #[must_use]
    pub const fn catalogue_id(self) -> &'static str { self.catalogue_id }
}

impl fmt::Display for OperationId {
    /// Renders the catalogue reference, e.g. `identity (V032)`.
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} ({})", self.name, self.catalogue_id)
    }
}

/// What a node of the expression graph does.
///
/// The kinds are separate from the shared [`Node`] so the node can be
/// destructured when it is dropped. A type carrying a `Drop` implementation
/// cannot be moved out of field by field, and the iterative drop depends on
/// exactly that.
pub(crate) enum NodeKind {
    /// A materialized input, sharing its array's buffer.
    Input(Arc<Vec<i64>>),
    /// The elementwise sum of two operands.
    Add {
        /// The left operand.
        lhs: AExpr,
        /// The right operand.
        rhs: AExpr,
    },
    /// The inert leaf a node is replaced with while it is being dropped.
    ///
    /// It holds nothing, so replacing a node's kind with it allocates nothing.
    /// Using an empty [`NodeKind::Input`] instead would allocate an `Arc`
    /// control block per dropped node, which for a 100,000-node chain is
    /// 100,000 allocations the drop path does not need. The variant is never
    /// reachable from a live graph: it exists only between the `mem::replace`
    /// and the release of the fields it replaced.
    Inert,
}

/// One node of an expression graph, shared by its handles.
pub(crate) struct Node {
    /// What this node computes.
    pub(crate) kind: NodeKind,
    /// The length under the partial model, when it is known.
    pub(crate) length: Option<usize>,
    /// Whether some node at or beneath this one has contradicting operand
    /// lengths, so preparation must report a shape failure here.
    pub(crate) mismatch_below: bool,
}

impl Debug for Node {
    /// Names the node's kind and cached facts, without descending.
    ///
    /// The implementation exists because `Arc::into_inner` requires it, and it
    /// deliberately does not recurse: printing one node must not become a way
    /// to walk a deep graph. [`AExpr`]'s own `Debug` is the recursive-free view.
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        let name = match self.kind {
            NodeKind::Input(_) => "input",
            NodeKind::Add { .. } => "add",
            NodeKind::Inert => "inert",
        };
        write!(
            formatter,
            "Node {{ kind: {name}, length: {:?}, mismatch_below: {} }}",
            self.length, self.mismatch_below
        )
    }
}

impl Drop for Node {
    /// Releases the graph iteratively, so a deep chain cannot exhaust the stack.
    ///
    /// A node owns at most two children, and dropping one would recurse. The
    /// work list turns that into a loop: each handle is taken out of its `Arc`
    /// and, when it was the last holder, its children are detached and pushed.
    /// `Arc::into_inner` is what decides whether this holder must release them,
    /// so a shared subterm is walked once per owner and its children only once.
    fn drop(&mut self) {
        // `mem::replace` is what makes the detach safe to write: the node's own
        // kind is taken out and replaced with an inert leaf, so the `Drop` that
        // runs when this node's fields are released sees no children and
        // cannot recurse. The inert leaf allocates nothing.
        let own_kind = std::mem::replace(&mut self.kind, NodeKind::Inert);
        let mut work = Vec::new();
        collect_children(own_kind, &mut work);
        while let Some(handle) = work.pop() {
            // A handle that is not the last holder leaves the node alive for
            // its other owners, which will release it when they are dropped.
            let Some(mut node) = Arc::into_inner(handle) else {
                continue;
            };
            let detached = std::mem::replace(&mut node.kind, NodeKind::Inert);
            collect_children(detached, &mut work);
            // `node` is a bare `Node` here, not an `Arc`, so dropping it runs
            // this implementation again — with an inert kind, so it does
            // nothing beyond releasing an empty vector.
        }
    }
}

/// Appends the node handles one kind holds, if any.
///
/// The handles are the shared `Arc`s rather than the `AExpr` wrappers, because
/// the work list's job is to find out whether this owner is the last one; the
/// wrapper would only be unwrapped again.
fn collect_children(kind: NodeKind, work: &mut Vec<Arc<Node>>) {
    match kind {
        NodeKind::Input(_) | NodeKind::Inert => (),
        NodeKind::Add { lhs, rhs } => {
            work.push(lhs.node);
            work.push(rhs.node);
        }
    }
}

/// A deferred expression over I64 arrays.
///
/// Handles are cheap to clone and may share subterms, so an expression that
/// references one subexpression twice still has one denotation for it.
///
/// ```
/// use combobulate::{Array, add, identity};
///
/// let left = Array::from_i64(vec![1, 2, 3]).expr();
/// let right = Array::from_i64(vec![10, 20, 30]).expr();
///
/// assert_eq!(left.then(&identity()).len(), Some(3));
/// assert_eq!(add().apply(&left, &right).len(), Some(3));
/// ```
#[derive(Clone)]
pub struct AExpr {
    /// The shared node this handle refers to.
    pub(crate) node: Arc<Node>,
}

impl AExpr {
    /// Wraps a shared buffer as an input node.
    pub(crate) fn from_values(values: Arc<Vec<i64>>) -> Self {
        let length = values.len();
        Self {
            node: Arc::new(Node {
                kind: NodeKind::Input(values),
                length: Some(length),
                mismatch_below: false,
            }),
        }
    }

    /// The length under the static model, or `None` when it is unknown.
    ///
    /// `None` means the expression's shape cannot be settled without values —
    /// an operand of an addition has no length — not that the expression is
    /// wrong. A wrong shape is reported separately by preparation.
    #[must_use]
    pub fn len(&self) -> Option<usize> { self.node.length }

    /// Whether this expression is known to hold no elements.
    ///
    /// An unknown length is not empty: `false` here means "not known to be
    /// empty", which is why it cannot stand in for an emptiness test on a
    /// result that was never prepared.
    #[must_use]
    pub fn is_empty(&self) -> bool { self.node.length == Some(0) }

    /// The dtype this expression yields.
    #[must_use]
    pub const fn dtype(&self) -> crate::Dtype { crate::Dtype::I64 }

    /// Applies a unary operation, folding the identity away (DL-3).
    #[must_use]
    pub fn then(&self, operation: &Unary) -> Self { operation.apply(self) }
}


/// A unary operation that may be applied to one expression.
///
/// ```
/// use combobulate::identity;
///
/// let operation = identity();
/// assert_eq!(
///     operation.operation_id().name(),
///     "identity",
///     "the descriptor reports the verb it applies"
/// );
/// ```
#[derive(Clone, Debug)]
pub struct Unary {
    /// Which unary operation this descriptor applies.
    operation: OperationId,
}

impl Unary {
    /// The catalogue identity of this operation.
    #[must_use]
    pub const fn operation_id(&self) -> OperationId { self.operation }

    /// Applies this operation to an operand.
    ///
    /// The identity folds away (DL-3): it returns a clone of the operand's
    /// handle rather than adding a node, which preserves
    /// ⟦identity(e)⟧ = ⟦e⟧ exactly and makes buffer sharing structural.
    #[must_use]
    pub fn apply(&self, operand: &AExpr) -> AExpr { operand.clone() }
}

/// A binary operation that may be applied to two expressions.
///
/// ```
/// use combobulate::add;
///
/// assert_eq!(
///     add().operation_id().catalogue_id(),
///     "V001",
///     "the descriptor cites the catalogue entry it implements"
/// );
/// ```
#[derive(Clone, Debug)]
pub struct Binary {
    /// Which binary operation this descriptor applies.
    operation: OperationId,
}

impl Binary {
    /// The catalogue identity of this operation.
    #[must_use]
    pub const fn operation_id(&self) -> OperationId { self.operation }

    /// Applies this operation to two operands.
    ///
    /// The result's cached facts are computed here, from the operands alone: a
    /// length only when both have one and agree, and a mismatch flag when this
    /// node is itself a root-cause disagreement or an operand already carries
    /// one (DL-9). No kernel runs.
    #[must_use]
    pub fn apply(&self, lhs: &AExpr, rhs: &AExpr) -> AExpr {
        let length = match (lhs.node.length, rhs.node.length) {
            (Some(left), Some(right)) if left == right => Some(left),
            _ => None,
        };
        let mismatch_here = matches!(
            (lhs.node.length, rhs.node.length),
            (Some(left), Some(right)) if left != right
        );
        AExpr {
            node: Arc::new(Node {
                kind: NodeKind::Add {
                    lhs: lhs.clone(),
                    rhs: rhs.clone(),
                },
                length,
                mismatch_below: mismatch_here || lhs.node.mismatch_below || rhs.node.mismatch_below,
            }),
        }
    }
}

/// The identity operation.
///
/// ```
/// use combobulate::identity;
///
/// assert_eq!(identity().operation_id().catalogue_id(), "V032");
/// ```
#[must_use]
pub const fn identity() -> Unary {
    Unary {
        operation: OperationId::IDENTITY,
    }
}

/// The elementwise addition operation.
///
/// ```
/// use combobulate::add;
///
/// assert_eq!(add().operation_id().name(), "add");
/// ```
#[must_use]
pub const fn add() -> Binary {
    Binary {
        operation: OperationId::ADD,
    }
}

mod formatting;

#[cfg(test)]
mod small_stack;
#[cfg(test)]
mod tests;
