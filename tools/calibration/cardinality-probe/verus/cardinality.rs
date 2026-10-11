// Calibration probe: Verus specification and proof of checked cardinality.
// Measured for the AC-01 budget (docs/acceptance-calibration.md); not the
// shipped kernel, which task 1.2.4 owns.
use vstd::prelude::*;

verus! {

pub open spec fn product(s: Seq<u64>) -> int
    decreases s.len(),
{
    if s.len() == 0 { 1 } else { product(s.drop_last()) * s.last() }
}

proof fn lemma_zero_extent(s: Seq<u64>, i: int)
    requires 0 <= i < s.len(), s[i] == 0,
    ensures product(s) == 0,
    decreases s.len(),
{
    if i < s.len() - 1 {
        lemma_zero_extent(s.drop_last(), i);
    }
}

proof fn lemma_product_positive(s: Seq<u64>)
    requires forall|k: int| 0 <= k < s.len() ==> s[k] >= 1,
    ensures product(s) >= 1,
    decreases s.len(),
{
    if s.len() > 0 {
        lemma_product_positive(s.drop_last());
        vstd::arithmetic::mul::lemma_mul_increases(s.last() as int, product(s.drop_last()));
        vstd::arithmetic::mul::lemma_mul_is_commutative(s.last() as int, product(s.drop_last()));
    }
}

proof fn lemma_product_step(s: Seq<u64>, i: int)
    requires 0 <= i < s.len(),
    ensures product(s.take(i + 1)) == product(s.take(i)) * s[i],
{
    assert(s.take(i + 1).drop_last() =~= s.take(i));
}

proof fn lemma_product_monotone(s: Seq<u64>, i: int)
    requires 0 <= i <= s.len(), forall|k: int| 0 <= k < s.len() ==> s[k] >= 1,
    ensures product(s.take(i)) <= product(s),
    decreases s.len() - i,
{
    if i < s.len() {
        lemma_product_step(s, i);
        lemma_product_positive(s.take(i));
        vstd::arithmetic::mul::lemma_mul_increases(s[i] as int, product(s.take(i)));
        vstd::arithmetic::mul::lemma_mul_is_commutative(s[i] as int, product(s.take(i)));
        lemma_product_monotone(s, i + 1);
    } else {
        assert(s.take(i) =~= s);
    }
}

pub fn checked_cardinality(extents: &Vec<u64>) -> (result: Option<u64>)
    ensures
        result == Some(product(extents@) as u64) <==> product(extents@) <= u64::MAX,
        result.is_none() <==> product(extents@) > u64::MAX,
{
    let mut i: usize = 0;
    while i < extents.len()
        invariant
            0 <= i <= extents.len(),
            forall|k: int| 0 <= k < i ==> extents@[k] != 0,
        decreases extents.len() - i,
    {
        if extents[i] == 0 {
            proof { lemma_zero_extent(extents@, i as int); }
            return Some(0);
        }
        i += 1;
    }
    let mut acc: u64 = 1;
    let mut j: usize = 0;
    while j < extents.len()
        invariant
            0 <= j <= extents.len(),
            forall|k: int| 0 <= k < extents.len() ==> extents@[k] >= 1,
            acc as int == product(extents@.take(j as int)),
        decreases extents.len() - j,
    {
        proof { lemma_product_step(extents@, j as int); }
        match acc.checked_mul(extents[j]) {
            Some(next) => { acc = next; }
            None => {
                proof {
                    lemma_product_monotone(extents@, j as int + 1);
                }
                return None;
            }
        }
        j += 1;
    }
    proof { assert(extents@.take(extents.len() as int) =~= extents@); }
    Some(acc)
}

} // verus!

fn main() {}
