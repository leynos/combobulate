//! Builds, formats and drops a deep chain on a deliberately small stack.
//!
//! FACADE-5 fixes 2 MiB, which is far less than a recursive walk of a
//! 100,000-node chain would need. Running there turns "would overflow the
//! stack" from a claim into a test: a derived `Debug`, a recursive traversal or
//! the default `Arc` drop aborts instead of passing.

use std::thread;

use super::{AExpr, add, identity};
use crate::array::Array;

/// The stack every case in this module runs on, from FACADE-5.
const STACK: usize = 2 * 1024 * 1024;

/// The depth of the chains these cases build.
const DEPTH: usize = 100_000;

/// An expression over a buffer of `width` ones.
fn expr_of(width: usize) -> AExpr { Array::from_i64(vec![1; width]).expr() }

/// Runs `body` on a thread with FACADE-5's stack size.
fn on_small_stack(body: impl FnOnce() + Send + 'static) {
    let handle = thread::Builder::new()
        .stack_size(STACK)
        .spawn(body)
        .expect("the thread must be created with the requested stack size");
    handle
        .join()
        .expect("the thread must finish without panicking");
}

/// A left-leaning chain of `DEPTH` additions over one-element inputs.
fn deep_chain() -> AExpr {
    let mut chain = expr_of(1);
    for _ in 0..DEPTH {
        chain = add().apply(&chain, &expr_of(1));
    }
    chain
}

#[test]
fn a_deep_chain_builds_and_drops() {
    on_small_stack(|| {
        let chain = deep_chain();
        drop(chain);
    });
}

#[test]
fn a_deep_chain_formats() {
    on_small_stack(|| {
        let chain = deep_chain();
        let rendered = format!("{chain:?}");
        assert!(
            rendered.starts_with("add(add(") && rendered.ends_with("input(1))"),
            "the rendering must present the chain's shape, got {} bytes",
            rendered.len()
        );
    });
}

/// A doubling chain formats in space linear in its node count.
///
/// `e = add().apply(&e, &e)` repeated 32 times is a valid expression of 33
/// distinct nodes. Expanding both references on every visit would produce
/// `2^32` input strings and more than 60 GB of text, so the case is a
/// regression guard rather than a style preference: it fails by taking the
/// whole machine down, which is why the depth is 32 and the assertion is on
/// the rendered length rather than on a timeout.
///
/// The `^n` form is checked too. Without it a reader could not tell a shared
/// node from two equal ones, and a formatter that silently dropped the second
/// operand would pass a length check alone.
#[test]
fn a_shared_doubling_chain_formats_in_linear_space() {
    on_small_stack(|| {
        let mut chain = expr_of(1);
        for _ in 0..32 {
            chain = add().apply(&chain, &chain);
        }
        let rendered = format!("{chain:?}");
        assert!(
            rendered.len() < 4_096,
            "33 distinct nodes must not expand to their 2^32 unfoldings; got {} bytes",
            rendered.len()
        );
        // Numbers are assigned as nodes are first reached, so the root — the
        // last node the walk opens — is the highest, and the repeat that names
        // it is the one this chain produces.
        assert!(
            rendered.contains("^32"),
            "a repeated node must be named rather than expanded, got {rendered}"
        );
    });
}

#[test]
fn identity_folding_does_not_grow_a_chain() {
    on_small_stack(|| {
        let mut chain = expr_of(1);
        for _ in 0..DEPTH {
            chain = chain.then(&identity());
        }
        assert_eq!(
            format!("{chain:?}"),
            "input(1)",
            "a chain of identities must fold away entirely"
        );
    });
}
