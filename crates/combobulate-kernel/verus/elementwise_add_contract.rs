//! The specification the shipped elementwise addition is checked against.
//!
//! Each `k` function states one clause of SC-12: `k1` the success relation,
//! `k2` that a length-and-range premise forces `Ok`, `k3` that
//! `LengthMismatch` is exactly the length disagreement, `k4` that an
//! `Overflow` names the least overflowing position, and `k5` the output frame.
//! The production function and the seeded mutants both state these clauses, so
//! a mutant is wrong only because its body violates a shared statement rather
//! than because a second, drifting contract was written for it.
//!
//! `lemma_contract_determinate` shows the clauses pin a unique outcome, so the
//! mutant table is a sample of wrong bodies rather than the whole of the
//! discrimination evidence. The file is included by the two Verus roots and by
//! no production build.

use super::elementwise_add::AddFailure;
use vstd::prelude::*;

verus! {

/// `lhs[i] + rhs[i]` lies inside the I64 range.
///
/// The addition is `int` arithmetic in spec mode, so the bound is on the exact
/// mathematical sum rather than on a wrapped one. SC-12 reports exactly this
/// predicate's failure at the least position.
pub open spec fn in_range_at(lhs: Seq<i64>, rhs: Seq<i64>, i: int) -> bool {
    i64::MIN <= lhs[i] + rhs[i] <= i64::MAX
}

/// Every position of the two operands is in range.
///
/// `in_range_at` is the trigger. Stating the predicate as the trigger rather
/// than the arithmetic keeps one instantiation per index, where an arithmetic
/// trigger would also match the nested sum and loop.
pub open spec fn all_in_range(lhs: Seq<i64>, rhs: Seq<i64>) -> bool {
    forall|i: int| 0 <= i < lhs.len() ==> #[trigger] in_range_at(lhs, rhs, i)
}

/// Both operands and the pre-state of the output have one common length.
///
/// K2 needs this premise and K3 negates it, so naming it once keeps the two
/// clauses literally complementary.
pub open spec fn same_len(lhs: Seq<i64>, rhs: Seq<i64>, pre: Seq<i64>) -> bool {
    lhs.len() == rhs.len() && rhs.len() == pre.len()
}

/// K1: success gives the pointwise sum.
///
/// The final conjunct is the whole content of the clause: every position of
/// the published output is the mathematical sum of the operands, with no
/// reassociation, reordering or widening.
pub open spec fn k1(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post: Seq<i64>,
    r: Result<(), AddFailure>,
) -> bool {
    r is Ok ==> same_len(lhs, rhs, pre)
        && all_in_range(lhs, rhs)
        && forall|i: int| 0 <= i < pre.len() ==> #[trigger] post[i] == lhs[i] + rhs[i]
}

/// K2: a well-shaped, in-range call succeeds.
///
/// With K1 this makes `Ok` hold exactly when the premise holds, which is what
/// rules out an always-`Err` body.
pub open spec fn k2(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post: Seq<i64>,
    r: Result<(), AddFailure>,
) -> bool {
    same_len(lhs, rhs, pre) && all_in_range(lhs, rhs) ==> r is Ok
}

/// K3: `LengthMismatch` is exactly the length disagreement.
///
/// The biconditional carries both directions: a length disagreement may not
/// report anything else, and a shape agreement may not report a mismatch.
pub open spec fn k3(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post: Seq<i64>,
    r: Result<(), AddFailure>,
) -> bool {
    (r matches Err(AddFailure::LengthMismatch)) <==> !same_len(lhs, rhs, pre)
}

/// K4: an overflow names the least failing position.
///
/// The final conjunct is what makes the position canonical rather than merely
/// some failing one, so two correct bodies cannot disagree.
pub open spec fn k4(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post: Seq<i64>,
    r: Result<(), AddFailure>,
) -> bool {
    r matches Err(AddFailure::Overflow { position }) ==> same_len(lhs, rhs, pre)
        && position < lhs.len()
        && !in_range_at(lhs, rhs, position as int)
        && forall|i: int| 0 <= i < position ==> #[trigger] in_range_at(lhs, rhs, i)
}

/// K5: a failure publishes nothing.
///
/// This is SC-09's atomic-commit rule for one kernel call: every earlier
/// position that would have summed correctly is still unwritten.
pub open spec fn k5(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post: Seq<i64>,
    r: Result<(), AddFailure>,
) -> bool {
    r is Err ==> post == pre
}

/// K0 and K1 to K5 at once, for the wrappers and the determinacy lemma.
///
/// K0 is the length frame. It is stated here rather than as its own `k`
/// function because it takes no result and constrains only the two states.
pub open spec fn contract_holds(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post: Seq<i64>,
    r: Result<(), AddFailure>,
) -> bool {
    &&& post.len() == pre.len()
    &&& k1(lhs, rhs, pre, post, r)
    &&& k2(lhs, rhs, pre, post, r)
    &&& k3(lhs, rhs, pre, post, r)
    &&& k4(lhs, rhs, pre, post, r)
    &&& k5(lhs, rhs, pre, post, r)
}

/// The least overflowing position, if the result names one.
///
/// This is a total function so a proof can compare two positions without
/// destructuring a result it has not yet shown to be an overflow.
pub open spec fn overflow_position(r: Result<(), AddFailure>) -> Option<usize> {
    match r {
        Err(AddFailure::Overflow { position }) => Some(position),
        _ => None,
    }
}

/// Two outputs satisfying K0 to K5 for the same arguments are one output.
///
/// The clauses are therefore complete as well as sound: an implementation that
/// satisfies them computes the one function SC-12 specifies. The proof splits
/// on whether the shapes agree and whether every position is in range, because
/// those two facts decide which clause fixes the result.
pub proof fn lemma_contract_determinate(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post1: Seq<i64>,
    r1: Result<(), AddFailure>,
    post2: Seq<i64>,
    r2: Result<(), AddFailure>,
)
    requires
        contract_holds(lhs, rhs, pre, post1, r1),
        contract_holds(lhs, rhs, pre, post2, r2),
    ensures
        r1 == r2,
        post1 == post2,
{
    if same_len(lhs, rhs, pre) {
        if all_in_range(lhs, rhs) {
            lemma_agreement_succeeds(lhs, rhs, pre, post1, r1);
            lemma_agreement_succeeds(lhs, rhs, pre, post2, r2);
            assert(post1 == post2) by {
                lemma_pointwise_sums_agree(lhs, rhs, pre, post1, post2);
            };
            assert(r1 == r2) by {
                lemma_ok_results_agree(r1, r2);
            };
        } else {
            lemma_agreement_overflows(lhs, rhs, pre, r1);
            lemma_agreement_overflows(lhs, rhs, pre, r2);
            assert(post1 == pre);
            assert(post2 == pre);
            lemma_overflow_outcomes_agree(lhs, rhs, pre, r1);
            lemma_overflow_outcomes_agree(lhs, rhs, pre, r2);
            lemma_overflow_positions_agree(lhs, rhs, pre, r1, r2);
            lemma_overflow_same_position_is_same_result(r1, r2);
        }
    } else {
        lemma_disagreement_fails(lhs, rhs, pre, post1, r1);
        lemma_disagreement_fails(lhs, rhs, pre, post2, r2);
        assert(post1 == pre);
        assert(post2 == pre);
        assert(r1 == r2) by {
            lemma_length_results_agree(r1, r2);
        };
    }
}

/// An agreeing, in-range call is `Ok`.
///
/// Split out because the caller needs the fact without unfolding K2 from the
/// compound predicate at every use.
proof fn lemma_agreement_succeeds(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post: Seq<i64>,
    r: Result<(), AddFailure>,
)
    requires
        k1(lhs, rhs, pre, post, r),
        k2(lhs, rhs, pre, post, r),
        same_len(lhs, rhs, pre),
        all_in_range(lhs, rhs),
    ensures
        r matches Ok(()),
{
}

/// Two pointwise sums over one length are the same sequence.
proof fn lemma_pointwise_sums_agree(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post1: Seq<i64>,
    post2: Seq<i64>,
)
    requires
        post1.len() == pre.len(),
        post2.len() == pre.len(),
        forall|i: int| 0 <= i < pre.len() ==> #[trigger] post1[i] == lhs[i] + rhs[i],
        forall|i: int| 0 <= i < pre.len() ==> #[trigger] post2[i] == lhs[i] + rhs[i],
    ensures
        post1 == post2,
{
    assert forall|i: int| 0 <= i < post1.len() implies post1[i] == post2[i] by {
        assert(post1[i] == lhs[i] + rhs[i]);
        assert(post2[i] == lhs[i] + rhs[i]);
    };
}

/// An agreeing but out-of-range call names an overflow position.
///
/// K3 excludes the length failure and K1 excludes success, so the only
/// remaining variant is `Overflow` with some position.
proof fn lemma_agreement_overflows(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    r: Result<(), AddFailure>,
)
    requires
        k1(lhs, rhs, pre, lhs, r),
        k3(lhs, rhs, pre, lhs, r),
        same_len(lhs, rhs, pre),
        !all_in_range(lhs, rhs),
    ensures
        overflow_position(r) is Some,
{
}

/// A least-overflow result's position satisfies K4's bound.
proof fn lemma_overflow_outcomes_agree(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    r: Result<(), AddFailure>,
)
    requires
        k4(lhs, rhs, pre, lhs, r),
        overflow_position(r) is Some,
    ensures
        overflow_position(r) is Some,
{
    if let Some(position) = overflow_position(r) {
        assert(position < lhs.len());
        assert(!in_range_at(lhs, rhs, position as int));
        assert(forall|i: int| 0 <= i < position ==> #[trigger] in_range_at(lhs, rhs, i));
    }
}

/// Two `Ok` results are the same result.
///
/// `Ok(())` carries no payload, so matching it fixes the whole value. Stating
/// that as a lemma keeps the determinacy proof to one call per branch instead
/// of an unfolding of the result type at each site.
proof fn lemma_ok_results_agree(r1: Result<(), AddFailure>, r2: Result<(), AddFailure>)
    requires
        r1 matches Ok(()),
        r2 matches Ok(()),
    ensures
        r1 == r2,
{
    match r1 {
        Ok(left) => match r2 {
            Ok(right) => assert(left == right),
            Err(_) => assert(false),
        },
        Err(failure) => assert(false),
    }
}

/// Two `LengthMismatch` results are the same result.
proof fn lemma_length_results_agree(r1: Result<(), AddFailure>, r2: Result<(), AddFailure>)
    requires
        r1 matches Err(AddFailure::LengthMismatch),
        r2 matches Err(AddFailure::LengthMismatch),
    ensures
        r1 == r2,
{
}

/// Least-overflow results naming the same position are the same result.
///
/// This is the step the determinacy lemma needs: two overflows with equal
/// positions are equal results, so equality of the extracted positions is
/// enough.
pub proof fn lemma_overflow_same_position_is_same_result(
    r1: Result<(), AddFailure>,
    r2: Result<(), AddFailure>,
)
    requires
        overflow_position(r1) == overflow_position(r2),
        overflow_position(r1) is Some,
    ensures
        r1 == r2,
{
    assert(overflow_position(r1).unwrap() == overflow_position(r2).unwrap());
}

/// Two least-overflowing positions are one position.
///
/// Whichever were smaller would be in range by the other's K4, contradicting
/// its own K4.
proof fn lemma_overflow_positions_agree(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    r1: Result<(), AddFailure>,
    r2: Result<(), AddFailure>,
)
    requires
        k4(lhs, rhs, pre, lhs, r1),
        overflow_position(r1) is Some,
        k4(lhs, rhs, pre, lhs, r2),
        overflow_position(r2) is Some,
    ensures
        overflow_position(r1) == overflow_position(r2),
{
    let position1 = overflow_position(r1).unwrap();
    let position2 = overflow_position(r2).unwrap();
    assert(position1 == position2) by {
        if position1 < position2 {
            assert(in_range_at(lhs, rhs, position1 as int));
        }
        if position2 < position1 {
            assert(in_range_at(lhs, rhs, position2 as int));
        }
    };
}

/// A shape disagreement is exactly `LengthMismatch`.
proof fn lemma_disagreement_fails(
    lhs: Seq<i64>,
    rhs: Seq<i64>,
    pre: Seq<i64>,
    post: Seq<i64>,
    r: Result<(), AddFailure>,
)
    requires
        k3(lhs, rhs, pre, post, r),
        k5(lhs, rhs, pre, post, r),
        !same_len(lhs, rhs, pre),
    ensures
        r matches Err(AddFailure::LengthMismatch),
        post == pre,
{
}

}
