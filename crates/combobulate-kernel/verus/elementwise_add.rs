//! The positive Verus root: the shipped body satisfies SC-12.
//!
//! The root includes the contract module and the production file, so the
//! verified body and the executed body are one source. It runs with no
//! `--verify-*` flag, because `--verify-root` would select only this module and
//! would leave the included body unchecked — the wiring probe demonstrated
//! exactly that gap.
//!
//! Besides the wrapper, the file holds witnesses that inhabit the premises of
//! K1, K3 and K4. A witness is an example the solver checks, so a contract
//! whose premises are unsatisfiable cannot pass by being vacuously true, and
//! the determinacy lemma is applied rather than merely stated.

#![feature(proc_macro_hygiene)]
#![allow(dead_code)]

use vstd::prelude::*;

#[path = "elementwise_add_contract.rs"]
mod contract;
#[path = "../src/elementwise_add.rs"]
mod elementwise_add;

verus! {

use crate::contract::{
    all_in_range, contract_holds, in_range_at, k1, k3, k4, lemma_contract_determinate, same_len,
};
use crate::elementwise_add::{AddFailure, add_i64_into};
use vstd::seq_lib::*;

/// The exported contract: every clause holds of the shipped call.
///
/// This is the wrapper the acceptance evidence names. It states K0 to K5 as
/// separate conjuncts, so a reader can see that the production `verus_spec`
/// implies the exported specification rather than restating it by hand.
pub fn add_i64_into_contract(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> (r: Result<
    (),
    AddFailure,
>)
    ensures
        final(out)@.len() == old(out)@.len(),
        k1(lhs@, rhs@, old(out)@, final(out)@, r),
        crate::contract::k2(lhs@, rhs@, old(out)@, final(out)@, r),
        k3(lhs@, rhs@, old(out)@, final(out)@, r),
        k4(lhs@, rhs@, old(out)@, final(out)@, r),
        crate::contract::k5(lhs@, rhs@, old(out)@, final(out)@, r),
{
    add_i64_into(lhs, rhs, out)
}

/// K1's premise is inhabited: three in-range positions.
///
/// Without this, K1's implication could be vacuous. The postcondition states
/// the sums explicitly, so the witness also pins the expected output.
pub fn witness_success() -> (out: [i64; 3])
    ensures
        out@ == seq![11_i64, 22, 33],
        same_len(seq![1_i64, 2, 3], seq![10_i64, 20, 30], seq![0_i64, 0, 0]),
        all_in_range(seq![1_i64, 2, 3], seq![10_i64, 20, 30]),
{
    let mut out = [0_i64; 3];
    let r = add_i64_into(&[1, 2, 3], &[10, 20, 30], &mut out);
    assert(r is Ok);
    assert(out@[0] == 11);
    assert(out@[1] == 22);
    assert(out@[2] == 33);
    out
}

/// K3's premise is inhabited: two lengths against one.
pub fn witness_length_mismatch() -> (r: Result<(), AddFailure>)
    ensures
        r == Err(AddFailure::LengthMismatch),
        !same_len(seq![1_i64, 2], seq![10_i64], seq![0_i64]),
{
    let mut out = [0_i64; 1];
    let r = add_i64_into(&[1, 2], &[10], &mut out);
    assert(r matches Err(AddFailure::LengthMismatch));
    assert(out@ == seq![0_i64]);
    r
}

/// K4's premise is inhabited: the least overflow is position 1, not 0.
///
/// The second assertion is what makes the witness discriminate: a body that
/// reported position 0 would satisfy "some overflowing position" but not
/// "the least one".
pub fn witness_least_overflow() -> (r: Result<(), AddFailure>)
    ensures
        r == Err(AddFailure::Overflow { position: 1 }),
        same_len(seq![0_i64, i64::MAX], seq![0_i64, 1], seq![0_i64, 0]),
        in_range_at(seq![0_i64, i64::MAX], seq![0_i64, 1], 0),
        !in_range_at(seq![0_i64, i64::MAX], seq![0_i64, 1], 1),
{
    let mut out = [0_i64; 2];
    let r = add_i64_into(&[0, i64::MAX], &[0, 1], &mut out);
    let ghost lhs = seq![0_i64, i64::MAX];
    let ghost rhs = seq![0_i64, 1];
    assert(in_range_at(lhs, rhs, 0)) by { reveal(in_range_at); };
    assert(!in_range_at(lhs, rhs, 1)) by { reveal(in_range_at); };
    assert(r is Err) by {
        if r is Ok {
            assert(all_in_range(lhs, rhs));
        }
    };
    assert(!(r matches Err(AddFailure::LengthMismatch))) by {
        assert(same_len(lhs, rhs, seq![0_i64, 0]));
    };
    assert(out@ == seq![0_i64, 0]);
    r
}

/// The determinacy lemma applies to the shipped function's outcome.
///
/// Stating the lemma is not evidence that it says anything about this body.
/// This witness supplies the premise and then *uses* the lemma: the concrete
/// call satisfies `contract_holds`, and every other outcome at the same input
/// is therefore the one that call produced. Applying the lemma to two equal
/// outcomes would establish nothing, because its conclusion would then be
/// reflexivity rather than a fact about the clauses.
pub proof fn witness_determinacy()
    ensures
        contract_holds(
            seq![1_i64, 2, 3],
            seq![10_i64, 20, 30],
            seq![0_i64, 0, 0],
            seq![11_i64, 22, 33],
            Ok(()),
        ),
        forall|post: Seq<i64>, r: Result<(), AddFailure>|
            contract_holds(
                seq![1_i64, 2, 3],
                seq![10_i64, 20, 30],
                seq![0_i64, 0, 0],
                post,
                r,
            ) ==> post == seq![11_i64, 22, 33] && r == Ok(()),
{
    assert forall|post: Seq<i64>, r: Result<(), AddFailure>|
        contract_holds(
            seq![1_i64, 2, 3],
            seq![10_i64, 20, 30],
            seq![0_i64, 0, 0],
            post,
            r,
        ) implies post == seq![11_i64, 22, 33] && r == Ok(())
    by {
        lemma_contract_determinate(
            seq![1_i64, 2, 3],
            seq![10_i64, 20, 30],
            seq![0_i64, 0, 0],
            seq![11_i64, 22, 33],
            Ok(()),
            post,
            r,
        );
    }
}

}
