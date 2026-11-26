//! Checked elementwise I64 addition over caller-provided storage.
//!
//! SC-12 says an elementwise add of two equal-length I64 vectors yields their
//! pointwise mathematical sum, reports the least overflowing position when
//! one exists, and never publishes a partial result. `add_i64_into` therefore
//! works in two passes: the first finds the least failure without writing, and
//! the second writes only once the first has found none. That is what makes
//! "failed execution publishes nothing" true of the kernel itself rather than
//! a rule the caller has to remember (DL-7).
//!
//! The module is `core`-only and allocates nothing, so a `no_std` caller can
//! own the destination. The same source is the Verus subject, which is why the
//! loop specifications sit on the statements they govern rather than in a
//! proof file: one body is executed, const-evaluated and verified.

#[cfg(verus_keep_ghost)]
use vstd::prelude::*;

#[cfg(verus_keep_ghost)]
use super::contract::{all_in_range, in_range_at, same_len};

/// Why an elementwise I64 addition did not complete.
///
/// Every variant leaves the caller's output exactly as it was, so a caller may
/// reuse the buffer after any failure.
///
/// ```
/// use combobulate_kernel::elementwise_add::{AddFailure, add_i64_into};
///
/// let mut out = [0_i64; 2];
/// assert_eq!(
///     add_i64_into(&[1, 2], &[10], &mut out),
///     Err(AddFailure::LengthMismatch),
///     "mismatched lengths are a length failure"
/// );
/// assert_eq!(out, [0, 0], "a failure writes nothing");
/// ```
#[cfg_attr(verus_keep_ghost, verus_verify)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AddFailure {
    /// The operand and output lengths differ.
    LengthMismatch,
    /// `lhs[position] + rhs[position]` is outside I64, and every earlier
    /// position is in range.
    Overflow {
        /// The least position whose sum leaves the I64 range.
        position: usize,
    },
}

/// Add `lhs` and `rhs` element-wise into `out` with checked I64 arithmetic.
///
/// Every position is the mathematical sum of its operands, with no
/// reassociation, reordering or widening. The failure reported is the least
/// one: a shape disagreement outranks every overflow because it is decided
/// before any position is examined, and among overflows the smallest position
/// is named.
///
/// # Errors
///
/// Returns [`AddFailure::LengthMismatch`] when the three lengths are not all
/// equal, and [`AddFailure::Overflow`] naming the least position whose sum
/// leaves the I64 range. Either way `out` is unchanged.
///
/// # Examples
///
/// ```
/// use combobulate_kernel::elementwise_add::{AddFailure, add_i64_into};
///
/// let mut out = [0_i64; 3];
/// add_i64_into(&[1, 2, 3], &[10, 20, 30], &mut out).expect("equal shapes fit");
/// assert_eq!(out, [11, 22, 33], "the sums are written in order");
///
/// // The destination must match the operands' width, so a shorter overflow
/// // case gets its own buffer rather than a slice of the first.
/// let mut narrow = [7_i64; 2];
/// assert_eq!(
///     add_i64_into(&[0, i64::MAX], &[0, 1], &mut narrow),
///     Err(AddFailure::Overflow { position: 1 }),
///     "position 0 fits, so the later overflow is the one named"
/// );
/// assert_eq!(narrow, [7, 7], "and the failed call writes nothing");
/// ```
#[cfg_attr(verus_keep_ghost, verus_verify, verus_spec(r =>
    ensures
        // K0: the output keeps its length.
        final(out)@.len() == old(out)@.len(),
        // K1: success gives the pointwise mathematical sum.
        r is Ok ==> same_len(lhs@, rhs@, old(out)@),
        r is Ok ==> all_in_range(lhs@, rhs@),
        r is Ok ==> forall|i: int|
            0 <= i < lhs@.len() ==> #[trigger] final(out)@[i] == lhs@[i] + rhs@[i],
        // K2: a well-shaped, in-range call succeeds.
        same_len(lhs@, rhs@, old(out)@) && all_in_range(lhs@, rhs@) ==> r is Ok,
        // K3: a length mismatch is exactly the length disagreement.
        (r matches Err(AddFailure::LengthMismatch))
            <==> !same_len(lhs@, rhs@, old(out)@),
        // K4: an overflow names the least failing position.
        r matches Err(AddFailure::Overflow { position }) ==>
            same_len(lhs@, rhs@, old(out)@)
            && position < lhs@.len()
            && !in_range_at(lhs@, rhs@, position as int)
            && forall|i: int| 0 <= i < position ==> #[trigger] in_range_at(lhs@, rhs@, i),
        // K5: a failure publishes nothing.
        r is Err ==> final(out)@ == old(out)@,
))]
// The loop guards bound every index below, and K4 and K6 discharge each bound
// as a verification obligation, so the indexing is total rather than merely
// unchecked. `get` would leave a `None` arm no test could reach.
#[expect(
    clippy::indexing_slicing,
    reason = "the loop guards bound every index and Verus discharges each bound"
)]
pub const fn add_i64_into(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> Result<(), AddFailure> {
    let n = lhs.len();
    if rhs.len() != n || out.len() != n {
        return Err(AddFailure::LengthMismatch);
    }
    let mut scan = 0;
    // Pass 1: find the least overflow without writing anything.
    #[cfg_attr(
        verus_keep_ghost,
        verus_spec(invariant
            scan <= n,
            lhs@.len() == n,
            rhs@.len() == n,
            out@.len() == n,
            out@ == old(out)@,
            forall|j: int| 0 <= j < scan ==> #[trigger] in_range_at(lhs@, rhs@, j),
            decreases n - scan,
        )
    )]
    while scan < n {
        if lhs[scan].checked_add(rhs[scan]).is_none() {
            // State the failure for the solver: the invariant bounds every
            // earlier position, so only this one needs to be excluded.
            #[cfg(verus_keep_ghost)]
            proof! { assert(!in_range_at(lhs@, rhs@, scan as int)); }
            return Err(AddFailure::Overflow { position: scan });
        }
        scan += 1;
    }
    // Pass 2: every position is now known to fit, so write them all. The
    // counter is a fresh binding rather than a reset, because the two loops
    // count different things and an unrelated shadow would hide that.
    let mut write_at = 0;
    #[cfg_attr(
        verus_keep_ghost,
        verus_spec(invariant
            write_at <= n,
            lhs@.len() == n,
            rhs@.len() == n,
            out@.len() == n,
            all_in_range(lhs@, rhs@),
            forall|j: int| 0 <= j < write_at ==> #[trigger] out@[j] == lhs@[j] + rhs@[j],
            decreases n - write_at,
        )
    )]
    while write_at < n {
        // Instantiate `all_in_range` at this position so the write is known
        // not to overflow.
        #[cfg(verus_keep_ghost)]
        proof! { assert(in_range_at(lhs@, rhs@, write_at as int)); }
        out[write_at] = lhs[write_at] + rhs[write_at];
        write_at += 1;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    //! Checks the shipped object code, not the specification.
    //!
    //! These are plain `#[test]` functions using only `core`, because the
    //! kernel may take no dev-dependency (VO-1). The parameterized boundary
    //! cases live in the root package's `tests/kernel_elementwise_add.rs`.

    use super::{AddFailure, add_i64_into};

    #[test]
    fn equal_shapes_are_summed_pointwise() {
        let mut out = [0_i64; 3];
        assert_eq!(
            add_i64_into(&[1, 2, 3], &[10, 20, 30], &mut out),
            Ok(()),
            "equal shapes fit and must succeed"
        );
        assert_eq!(out, [11, 22, 33], "each position holds its own sum");
    }

    #[test]
    fn empty_vectors_succeed_and_write_nothing() {
        let mut out = [0_i64; 0];
        assert_eq!(
            add_i64_into(&[], &[], &mut out),
            Ok(()),
            "the empty vector is a shape agreement, not a failure"
        );
    }

    #[test]
    fn length_disagreement_fails_and_leaves_output_unchanged() {
        let mut out = [7_i64; 2];
        assert_eq!(
            add_i64_into(&[1, 2, 3], &[1, 2], &mut out),
            Err(AddFailure::LengthMismatch),
            "three against two is a length disagreement"
        );
        assert_eq!(out, [7, 7], "a length failure writes nothing");
        assert_eq!(
            add_i64_into(&[1, 2], &[1, 2], &mut out[..1]),
            Err(AddFailure::LengthMismatch),
            "an output shorter than the operands is also a disagreement"
        );
        assert_eq!(out, [7, 7], "and it writes nothing either");
    }

    #[test]
    fn overflow_names_the_least_position_and_writes_nothing() {
        let mut out = [7_i64; 2];
        assert_eq!(
            add_i64_into(&[0, i64::MAX], &[0, 1], &mut out),
            Err(AddFailure::Overflow { position: 1 }),
            "position 0 fits, so position 1 is the least overflow"
        );
        assert_eq!(out, [7, 7], "the first pass writes nothing at all");
    }

    #[test]
    fn an_overflow_before_another_overflow_is_the_one_named() {
        let mut out = [0_i64; 2];
        assert_eq!(
            add_i64_into(&[i64::MAX, i64::MAX], &[1, 1], &mut out),
            Err(AddFailure::Overflow { position: 0 }),
            "both positions overflow, and the least is named"
        );
    }

    // B01 requires one body to agree at runtime, in `const` and under Verus.
    // The runtime cases above and the Verus root cover the other two; this is
    // the const-evaluation evidence, and it is a compile-time constant rather
    // than a test body so an expression the const evaluator rejects would fail
    // the build rather than a run.
    const CONST_SUM: (Result<(), AddFailure>, [i64; 2]) = {
        let mut out = [0_i64; 2];
        let result = add_i64_into(&[1, 2], &[10, 20], &mut out);
        (result, out)
    };

    /// The const evaluation agrees with the runtime one, position by position.
    const CONST_SUM_IS_POINTWISE: () = assert!(
        matches!(CONST_SUM.0, Ok(())) && CONST_SUM.1[0] == 11 && CONST_SUM.1[1] == 22,
        "const evaluation must produce the same pointwise sums as the runtime call"
    );

    #[test]
    fn both_boundaries_are_successes() {
        let mut out = [0_i64; 2];
        assert_eq!(
            add_i64_into(&[i64::MAX, i64::MIN], &[0, 0], &mut out),
            Ok(()),
            "a boundary value plus zero stays in range"
        );
        assert_eq!(out, [i64::MAX, i64::MIN], "and is written unchanged");
    }

    #[test]
    fn the_const_evaluation_agrees_with_the_runtime_one() {
        // Forcing the constant to be evaluated is what makes the assertion at
        // compile time observable from a test that can fail.
        let () = CONST_SUM_IS_POINTWISE;
        assert_eq!(
            CONST_SUM,
            {
                let mut out = [0_i64; 2];
                let result = add_i64_into(&[1, 2], &[10, 20], &mut out);
                (result, out)
            },
            "the const and runtime evaluations must agree exactly"
        );
    }
}
