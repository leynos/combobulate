//! FACADE-1's sharing facts and FACADE-4's memoization evidence.
//!
//! A shared subterm must be evaluated once, however many consumers refer to
//! it. The doubling chain is the sharpest form of the claim: without
//! memoization `x(k+1) = add(x(k), x(k))` visits 2^k nodes, so 62 levels is
//! not slow but impossible. Reaching `2^62` proves the walk is linear in the
//! number of distinct nodes, not in the number of paths.
//!
//! FACADE-5's deep chain needs a deliberately small stack and lives in its own
//! integration case; here the chain is only as deep as the arithmetic needs.

use combobulate::{Failure, add};

use super::{engine, expr, single_failure};

/// `x(k+1) = add(x(k), x(k))`, `k` levels deep, over `[1]`.
fn doubling_chain(levels: usize) -> combobulate::AExpr {
    let mut chain = expr(&[1]);
    for _ in 0..levels {
        chain = add().apply(&chain, &chain);
    }
    chain
}

#[test]
fn sixty_two_doublings_fit_and_evaluate_once() {
    let collected = doubling_chain(62)
        .collect()
        .expect("62 doublings reach 2^62, which I64 holds");
    assert_eq!(
        collected.as_i64_slice(),
        Some(&[1_i64 << 62][..]),
        "each level is twice the one below it, evaluated once"
    );
}

#[test]
fn the_sixty_third_doubling_overflows() {
    let error = doubling_chain(63)
        .collect()
        .expect_err("2^63 leaves the I64 range");
    let failure = single_failure(&error);
    assert!(
        matches!(failure, Failure::IntegerOverflow { position: 0, .. }),
        "the level whose sum overflows is the one reported, got {failure:?}"
    );
}

#[test]
fn a_shared_subterm_is_one_root_cause() {
    let shared = add().apply(&expr(&[1, 2, 3]), &expr(&[1, 2]));
    let error = add()
        .apply(&shared, &shared)
        .prepare(&engine())
        .expect_err("the shared subterm disagrees");
    assert_eq!(
        error.failures().len(),
        1,
        "one shared node is one failure, not one per consumer"
    );
}

#[test]
fn a_shared_value_is_summed_once_per_consumer() {
    let values = expr(&[1, 2, 3]);
    let collected = add().apply(&values, &values).collect().expect("3 + 3 fits");
    assert_eq!(
        collected.as_i64_slice(),
        Some(&[2_i64, 4, 6][..]),
        "referring to one value twice sums it with itself"
    );
}
