//! The seeded-mutant Verus root: each wrong body must fail its named clause.
//!
//! Every wrapper below states K0 to K5 for the shipped specification and then
//! calls a deliberately wrong implementation. A mutant "rejects" only when the
//! failing obligation is a postcondition inside that wrapper's own source
//! region and the intended clause is among the failures, which is what makes
//! the verdict evidence about the contract rather than about some other line.
//!
//! The mutants are a sanity sample. `lemma_contract_determinate` is the
//! completeness argument; these show that a solver actually catches the
//! classes of mistake the specification exists to exclude.
//!
//! Each wrapper is verified separately, with `--verify-root
//! --verify-function=<name>`, so the names share no substring and one mutant's
//! failure cannot be attributed to another.

#![feature(proc_macro_hygiene)]
#![allow(dead_code)]

use vstd::prelude::*;

#[path = "elementwise_add_contract.rs"]
mod contract;
#[path = "../src/elementwise_add.rs"]
mod elementwise_add;

verus! {

use crate::contract::{all_in_range, in_range_at, k1, k2, k3, k4, k5, same_len};
use crate::elementwise_add::{AddFailure, add_i64_into};
use vstd::seq_lib::*;

/// M-err: always report a length mismatch.
///
/// K2 rejects the always-`Err` body through its success premise, and K3
/// rejects it because a shape agreement may not report `LengthMismatch`.
pub fn mutant_err(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> (r: Result<(), AddFailure>)
    ensures
        k1(lhs@, rhs@, old(out)@, final(out)@, r),
        k2(lhs@, rhs@, old(out)@, final(out)@, r),
        k3(lhs@, rhs@, old(out)@, final(out)@, r),
        k4(lhs@, rhs@, old(out)@, final(out)@, r),
        k5(lhs@, rhs@, old(out)@, final(out)@, r),
{
    let _ = (lhs, rhs, out);
    Err(AddFailure::LengthMismatch)
}

/// M-late: report the overflow one position too late.
///
/// K4 rejects it whenever the least overflow is not the last position, which
/// its premise is chosen to make reachable.
pub fn mutant_late(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> (r: Result<(), AddFailure>)
    ensures
        k1(lhs@, rhs@, old(out)@, final(out)@, r),
        k2(lhs@, rhs@, old(out)@, final(out)@, r),
        k3(lhs@, rhs@, old(out)@, final(out)@, r),
        k4(lhs@, rhs@, old(out)@, final(out)@, r),
        k5(lhs@, rhs@, old(out)@, final(out)@, r),
{
    match add_i64_into(lhs, rhs, out) {
        // `saturating_add` rather than `+` keeps the mutation's own
        // arithmetic total, so the only failing obligation is K4 rather than
        // an incidental overflow check.
        Err(AddFailure::Overflow { position }) => {
            Err(AddFailure::Overflow { position: position.saturating_add(1) })
        }
        other => other,
    }
}

/// M-ok-on-overflow: swallow an overflow and report success.
///
/// K1 rejects it: an `Ok` result has to carry the pointwise sum, which an
/// overflowing position cannot.
pub fn mutant_ok_on_overflow(
    lhs: &[i64],
    rhs: &[i64],
    out: &mut [i64],
) -> (r: Result<(), AddFailure>)
    ensures
        k1(lhs@, rhs@, old(out)@, final(out)@, r),
        k2(lhs@, rhs@, old(out)@, final(out)@, r),
        k3(lhs@, rhs@, old(out)@, final(out)@, r),
        k4(lhs@, rhs@, old(out)@, final(out)@, r),
        k5(lhs@, rhs@, old(out)@, final(out)@, r),
{
    match add_i64_into(lhs, rhs, out) {
        Err(AddFailure::Overflow { .. }) => Ok(()),
        other => other,
    }
}

/// M-mismatch-write: write the output while rejecting the shape.
///
/// K5 rejects it, because a failure must leave the output exactly as it was.
pub fn mutant_mismatch_write(
    lhs: &[i64],
    rhs: &[i64],
    out: &mut [i64],
) -> (r: Result<(), AddFailure>)
    ensures
        k1(lhs@, rhs@, old(out)@, final(out)@, r),
        k2(lhs@, rhs@, old(out)@, final(out)@, r),
        k3(lhs@, rhs@, old(out)@, final(out)@, r),
        k4(lhs@, rhs@, old(out)@, final(out)@, r),
        k5(lhs@, rhs@, old(out)@, final(out)@, r),
{
    let n = lhs.len();
    if rhs.len() != n || out.len() != n {
        if !out.is_empty() {
            out[0] = 0;
        }
        return Err(AddFailure::LengthMismatch);
    }
    add_i64_into(lhs, rhs, out)
}

/// M-early-write: write the wrapped sum, then report the overflow.
///
/// K5 rejects it too, and here the write sits at the very position that
/// overflowed, which is the failure mode a one-pass kernel would have.
pub fn mutant_early_write(
    lhs: &[i64],
    rhs: &[i64],
    out: &mut [i64],
) -> (r: Result<(), AddFailure>)
    ensures
        k1(lhs@, rhs@, old(out)@, final(out)@, r),
        k2(lhs@, rhs@, old(out)@, final(out)@, r),
        k3(lhs@, rhs@, old(out)@, final(out)@, r),
        k4(lhs@, rhs@, old(out)@, final(out)@, r),
        k5(lhs@, rhs@, old(out)@, final(out)@, r),
{
    match add_i64_into(lhs, rhs, out) {
        Err(AddFailure::Overflow { position }) => {
            if position < out.len() {
                let sum = lhs[position].wrapping_add(rhs[position]);
                out[position] = sum;
            }
            Err(AddFailure::Overflow { position })
        }
        other => other,
    }
}

}
