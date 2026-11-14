//! FACADE-5: a 100,000-node chain builds, prepares, executes and drops.
//!
//! The stack is deliberately 2 MiB. A recursive traversal, a recursive
//! `Debug` or the default `Arc` drop would each abort on a chain this deep, so
//! the case fails loudly rather than slowly. The chain is left-leaning, which
//! is the shape that reaches both extremes: every node has a right operand of
//! one element, so the first step of the walk is the topmost node's left
//! child, and the 100,000th is an input.
//!
//! The unit-level build, format and drop cases live beside the module they
//! exercise (`src/expr/small_stack.rs`); this case adds preparation and
//! execution, which only exist once `AExpr::prepare` does.

use std::thread;

use combobulate::{AExpr, add, identity};

use super::{engine, expr};

/// The stack FACADE-5 requires.
const STACK: usize = 2 * 1024 * 1024;

/// The depth of the chain FACADE-5 requires.
const DEPTH: usize = 100_000;

/// Runs `body` on a thread with FACADE-5's stack size.
fn on_small_stack(body: impl FnOnce() + Send + 'static) {
    thread::Builder::new()
        .stack_size(STACK)
        .spawn(body)
        .expect("the thread must be created with the requested stack size")
        .join()
        .expect("the thread must finish without panicking");
}

/// A left-leaning chain of `DEPTH` additions over `[1]`.
fn deep_chain() -> AExpr {
    let mut chain = expr(&[1]);
    for _ in 0..DEPTH {
        chain = add().apply(&chain, &expr(&[1]));
    }
    chain
}

#[test]
fn a_deep_chain_prepares_and_executes_on_a_small_stack() {
    on_small_stack(|| {
        let chain = deep_chain();
        let plan = chain
            .prepare(&engine())
            .expect("every addition in the chain has equal operand lengths");
        let collected = plan.execute().expect("100,001 fits in I64");
        assert_eq!(
            collected.as_i64_slice(),
            Some(&[100_001_i64][..]),
            "the chain sums one more element per level"
        );
        drop(chain);
        drop(plan);
        drop(collected);
    });
}

#[test]
fn a_deep_chain_of_identities_still_collects_to_its_input() {
    on_small_stack(|| {
        let mut chain = expr(&[1, 2]);
        for _ in 0..DEPTH {
            chain = chain.then(&identity());
        }
        assert_eq!(
            chain.len(),
            Some(2),
            "folding must leave the chain one input deep"
        );
        let collected = chain.collect().expect("an identity cannot fail");
        assert_eq!(
            collected.as_i64_slice(),
            Some(&[1, 2][..]),
            "a chain of identities is its input"
        );
    });
}
