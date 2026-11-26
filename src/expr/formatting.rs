//! `Debug` for an expression graph, walked with an explicit work list.
//!
//! The walk is iterative because a derived `Debug` would recurse once per node
//! and overflow the stack on a deep chain (FACADE-5). It also numbers the nodes
//! it prints, so a shared subgraph renders once and is referenced afterwards
//! rather than expanded at every visit.

use std::{
    collections::HashMap,
    fmt::{self, Debug, Formatter},
    sync::Arc,
};

use super::{AExpr, NodeKind};

impl Debug for AExpr {
    /// Formats the graph as an explicit stack, never by recursion.
    ///
    /// A derived `Debug` would recurse once per node and overflow the stack on
    /// a deep chain. This prints the same shape a derived implementation would
    /// — an operation with its operand list, an input with its length — while
    /// walking the graph with its own work list.
    ///
    /// A node reached a second time is printed as `^n`, naming the node it
    /// repeats, rather than expanded again. The graph is shared, so expanding
    /// every reference makes the output exponential in the sharing depth: a
    /// doubling chain of 20 additions over one input holds 21 nodes and
    /// expands to 15.7 MB of text, and 32 additions would need more than 60 GB.
    /// Printing the repeat keeps the output linear in the node count, and the
    /// `^n` form is what tells a reader that the two operands are the same
    /// node rather than equal ones.
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        // The number each already-printed node was given, keyed by its address.
        // A map rather than a scan, because the walk visits every node of a
        // deep chain and a linear lookup per node would make formatting
        // quadratic in the node count.
        let mut seen: HashMap<usize, usize> = HashMap::new();
        let mut stack = vec![Frame::Open(self.clone())];
        while let Some(frame) = stack.pop() {
            match frame {
                Frame::Open(handle) => open_node(formatter, &handle, &mut seen, &mut stack)?,
                Frame::Close(text) => formatter.write_str(text)?,
            }
        }
        Ok(())
    }
}

/// Writes one node's opening text, scheduling what follows on `stack`.
///
/// A node already numbered is written as `^n` and its operands are not
/// scheduled, which is what keeps the output linear in the node count.
fn open_node(
    formatter: &mut Formatter<'_>,
    handle: &AExpr,
    seen: &mut HashMap<usize, usize>,
    stack: &mut Vec<Frame>,
) -> fmt::Result {
    let identity = Arc::as_ptr(&handle.node) as usize;
    if let Some(position) = seen.get(&identity) {
        return write!(formatter, "^{position}");
    }
    seen.insert(identity, seen.len());
    match &handle.node.kind {
        NodeKind::Input(values) => write!(formatter, "input({})", values.len()),
        NodeKind::Inert => formatter.write_str("inert"),
        NodeKind::Add { lhs, rhs } => {
            formatter.write_str("add(")?;
            stack.push(Frame::Close(")"));
            stack.push(Frame::Open(rhs.clone()));
            stack.push(Frame::Close(", "));
            stack.push(Frame::Open(lhs.clone()));
            Ok(())
        }
    }
}

/// One item of the iterative formatter's work list.
enum Frame {
    /// A node still to be written.
    Open(AExpr),
    /// Literal text to write between or after nodes.
    Close(&'static str),
}
