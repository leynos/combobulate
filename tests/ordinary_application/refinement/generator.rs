//! The generator: drawing graphs, and building the crate's expression for one.
//!
//! Operands are named by node index, so the drawn graph is a DAG by
//! construction: two nodes naming one index are a shared subterm, which is the
//! shape FACADE-4 requires preparation to evaluate once. The size bound is what
//! keeps a case readable; an unbounded chain would fail first at the heap.

use proptest::prelude::*;

/// The longest vector a generated case may draw.
pub(super) const MAX_LEN: usize = 8;

/// The most inputs a generated case may draw.
const MAX_INPUTS: usize = 4;

/// The most nodes, inputs included, a generated graph may hold.
const MAX_NODES: usize = 12;

/// One operation a generated non-input node applies.
#[derive(Clone, Debug)]
pub(super) enum NodeSpec {
    /// The identity of node `of`.
    Identity {
        /// The operand's index.
        of: usize,
    },
    /// The pointwise sum of nodes `lhs` and `rhs`.
    Add {
        /// The left operand's index.
        lhs: usize,
        /// The right operand's index.
        rhs: usize,
    },
}

/// A generated graph: its inputs first, then one operation per later node.
#[derive(Clone, Debug)]
pub(super) struct Graph {
    /// The vectors the input nodes hold, in index order.
    pub(super) inputs: Vec<Vec<i64>>,
    /// The operation each non-input node applies, in index order.
    pub(super) nodes: Vec<NodeSpec>,
}

impl Graph {
    /// The index of the last node, which every graph rooted there reaches.
    pub(super) fn root(&self) -> usize { self.inputs.len() + self.nodes.len() - 1 }

    /// The operation of node `at`, or `None` when `at` names an input.
    pub(super) fn spec_at(&self, at: usize) -> Option<&NodeSpec> {
        at.checked_sub(self.inputs.len())
            .and_then(|index| self.nodes.get(index))
    }
}

/// One element: mostly small, with the range's extremes as a minority.
///
/// The extremes are what make an overflowing sum reachable at all, and they are
/// too important to leave to a uniform draw over the whole range.
fn element() -> impl Strategy<Value = i64> {
    prop_oneof![
        4 => -8_i64..=8,
        1 => prop_oneof![Just(0_i64), Just(1), Just(-1), Just(i64::MIN), Just(i64::MAX)],
    ]
}

/// Up to four inputs, mostly of one common length.
///
/// A common length with a minority of independent ones is what the model needs:
/// most graphs then have a definite shape, and the rest inject the kind of
/// disagreement FACADE-2 must find.
fn inputs() -> impl Strategy<Value = Vec<Vec<i64>>> {
    (0usize..=MAX_LEN, 1usize..=MAX_INPUTS).prop_flat_map(|(common, count)| {
        let lengths =
            prop::collection::vec(prop_oneof![7 => Just(common), 1 => 0usize..=MAX_LEN], count);
        let values = prop::collection::vec(prop::collection::vec(element(), MAX_LEN), count);
        (lengths, values).prop_map(|(wanted, drawn)| {
            drawn
                .into_iter()
                .zip(wanted)
                .map(|(drawn_vec, length)| drawn_vec.into_iter().take(length).collect())
                .collect()
        })
    })
}

/// Draws a graph of at most `MAX_NODES` nodes.
pub(super) fn graph() -> impl Strategy<Value = Graph> { inputs().prop_flat_map(graph_with_inputs) }

/// The operations of a graph whose inputs are `values`.
///
/// The node count is drawn first so the operations can be built knowing how
/// many nodes precede each of them.
fn graph_with_inputs(values: Vec<Vec<i64>>) -> BoxedStrategy<Graph> {
    let base = values.len();
    (0..=MAX_NODES.saturating_sub(base))
        .prop_flat_map(move |extra| node_specs(base, extra))
        .prop_map(move |specs| Graph {
            inputs: values.clone(),
            nodes: specs,
        })
        .boxed()
}

/// `extra` operations for a graph with `base` nodes already.
fn node_specs(base: usize, extra: usize) -> BoxedStrategy<Vec<NodeSpec>> {
    (0..extra).fold(Just(Vec::new()).boxed(), |drawn, step| {
        (drawn, node_spec(base + step))
            .prop_map(append_spec)
            .boxed()
    })
}

/// Appends one drawn operation to the operations before it.
fn append_spec((mut drawn, spec): (Vec<NodeSpec>, NodeSpec)) -> Vec<NodeSpec> {
    drawn.push(spec);
    drawn
}

/// One non-input node, naming only nodes that precede it.
fn node_spec(prefix: usize) -> impl Strategy<Value = NodeSpec> {
    prop_oneof![
        1 => (0..prefix).prop_map(|of| NodeSpec::Identity { of }),
        4 => ((0..prefix), (0..prefix)).prop_map(|(lhs, rhs)| NodeSpec::Add { lhs, rhs }),
    ]
}

/// Whether any node the root reaches has two consumers, so a shared subterm is
/// evaluated.
///
/// Only nodes reachable from the root are counted. A node nothing consumes is
/// never prepared, so crediting it with a shared consumer would report the
/// sharing case as exercised by a graph that never evaluates a shared subterm.
pub(super) fn shares(graph: &Graph) -> bool {
    let total = graph.inputs.len() + graph.nodes.len();
    let mut uses: Vec<usize> = vec![0; total];
    for spec in &graph.nodes {
        match spec {
            NodeSpec::Identity { of } => bump(&mut uses, *of),
            NodeSpec::Add { lhs, rhs } => {
                bump(&mut uses, *lhs);
                bump(&mut uses, *rhs);
            }
        }
    }
    let reached = reachable(graph);
    uses.iter()
        .zip(&reached)
        .any(|(count, is_reached)| *is_reached && *count > 1)
}

/// Marks every node the root's operands reach, inputs included.
///
/// The root is always the last node and every operand index is smaller, so a
/// single backwards pass marks the whole reachable set: a node is reachable
/// when the root is it, or when a reachable node names it.
fn reachable(graph: &Graph) -> Vec<bool> {
    let total = graph.inputs.len() + graph.nodes.len();
    let mut reached = vec![false; total];
    if graph.nodes.is_empty() {
        // A graph with no operations is a lone input, which the root names.
        if let Some(first) = reached.first_mut() {
            *first = true;
        }
        return reached;
    }
    mark(&mut reached, graph.root());
    // Walking backwards guarantees a node's consumers are decided before it
    // is, because consumers always have larger indices.
    for at in (graph.inputs.len()..total).rev() {
        let Some(&is_reached) = reached.get(at) else {
            continue;
        };
        if !is_reached {
            continue;
        }
        let Some(spec) = graph.nodes.get(at - graph.inputs.len()) else {
            continue;
        };
        match spec {
            NodeSpec::Identity { of } => mark(&mut reached, *of),
            NodeSpec::Add { lhs, rhs } => {
                mark(&mut reached, *lhs);
                mark(&mut reached, *rhs);
            }
        }
    }
    reached
}

/// Marks one node as reached.
fn mark(reached: &mut [bool], node: usize) {
    if let Some(flag) = reached.get_mut(node) {
        *flag = true;
    }
}

/// Counts one more consumer of `node`.
fn bump(uses: &mut [usize], node: usize) {
    if let Some(count) = uses.get_mut(node) {
        *count += 1;
    }
}
