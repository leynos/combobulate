//! Calibration probe: a checked cardinality function and its Kani harnesses.
//!
//! This crate exists only to measure verifier and build costs for the
//! pre-registered acceptance controls (`docs/acceptance-calibration.md`). It is
//! not the shipped kernel; task 1.2.4 owns that.

/// Return the product of `extents`, or `None` when it overflows `usize`.
///
/// A zero extent yields zero before any multiplication, so `[0, usize::MAX,
/// usize::MAX]` is `Some(0)` rather than an overflow.
///
/// ```
/// use cardinality_probe::checked_cardinality;
/// assert_eq!(checked_cardinality(&[2, 3]), Some(6));
/// assert_eq!(checked_cardinality(&[0, usize::MAX, 2]), Some(0));
/// assert_eq!(checked_cardinality(&[usize::MAX, 2]), None);
/// ```
#[must_use]
pub fn checked_cardinality(extents: &[usize]) -> Option<usize> {
    if extents.contains(&0) {
        return Some(0);
    }
    extents
        .iter()
        .try_fold(1_usize, |product, &extent| product.checked_mul(extent))
}

#[cfg(kani)]
mod verification {
    use super::checked_cardinality;

    /// Any zero extent gives zero without multiplying, whatever the other extents are.
    ///
    /// Harnesses that multiply symbolic extents (full width, or bounded below
    /// 2^16) exhausted a 900 s budget during calibration; unbounded arithmetic
    /// belongs to the Verus proof in `verus/cardinality.rs`.
    #[kani::proof]
    #[kani::unwind(4)]
    fn zero_extent_short_circuits() {
        let extents: [usize; 3] = kani::any();
        let zero_at: usize = kani::any();
        kani::assume(zero_at < extents.len() && extents[zero_at] == 0);
        let result = checked_cardinality(&extents);
        kani::cover!(
            zero_at == 2 && extents[0] == usize::MAX,
            "a late zero beside a huge extent is reachable"
        );
        assert_eq!(result, Some(0), "a zero extent gives zero");
    }

    /// An empty shape (a scalar) has cardinality one.
    #[kani::proof]
    fn scalar_has_cardinality_one() {
        let result = checked_cardinality(&[]);
        kani::cover!(result == Some(1), "the scalar case is reachable");
        assert_eq!(result, Some(1), "a scalar has one element");
    }
}
