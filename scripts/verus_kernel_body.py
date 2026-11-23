"""Build the body-tier mutant root the kernel proofs verify.

The M-wrap tier exists to show that the shipped body's own annotations catch a
wrong body, not only a wrong wrapper. That needs two things kept together: the
mutation of the shipped source, and the generated root that compiles it. They
live here rather than in the driver so the driver stays a pipeline over
verdicts, and so the mutation can be unit-tested without a solver.

Nothing here runs a verifier or writes outside the caller's scratch directory.
"""

from __future__ import annotations


def wrapping_body(shipped: str) -> str:
    """Replace the shipped arithmetic with wrapping addition, as M-wrap.

    The plan's mutant is `checked_add` replaced by `wrapping_add`, so the
    body adds with wrapping arithmetic and detects an overflow only where the
    wrapping sum lands on `i64::MIN` — the one value a wrapping add can reach
    from many pairs. Both the detection and the write are replaced: with only
    the detection wrong, pass 2 still proves each write in range and the run
    would say nothing about wrapping behaviour.

    Raises
    ------
    RuntimeError
        When the shipped source no longer has the shapes being replaced,
        since a mutation that matched nothing would verify the shipped body
        and call it a rejected mutant.
    """
    sites = (
        (
            "lhs[scan].checked_add(rhs[scan]).is_none()",
            "lhs[scan].wrapping_add(rhs[scan]) == i64::MIN",
        ),
        (
            "out[write_at] = lhs[write_at] + rhs[write_at];",
            "out[write_at] = lhs[write_at].wrapping_add(rhs[write_at]);",
        ),
    )
    mutated = shipped
    for original, replacement in sites:
        if original not in mutated:
            raise RuntimeError(
                f"the body mutation no longer matches {original!r} in the shipped "
                "source; the mutation must fail rather than silently producing an "
                "unmutated copy"
            )
        mutated = mutated.replace(original, replacement)
    return mutated


WRAP_ROOT = """//! Generated root for the body-tier wrapping mutant.
#![no_std]
#![feature(proc_macro_hygiene)]
use vstd::prelude::*;

#[path = "contract.rs"]
mod contract;
#[path = "elementwise_add.rs"]
mod elementwise_add;

verus! {
pub fn wrap(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> (r: Result<(), elementwise_add::AddFailure>) {
    elementwise_add::add_i64_into(lhs, rhs, out)
}
}
"""
