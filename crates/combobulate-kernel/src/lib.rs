//! Target facts that checked rules must evaluate for the compilation target.
//!
//! The crate is `#![no_std]` without `alloc`: it may be compiled for a target
//! that has neither, and it must never substitute the host's pointer width for
//! the target's. Allocation can be admitted later only by an ADR-0010
//! amendment.
#![no_std]
#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]

/// Bind Kani's vocabulary when the verifier compiles this crate.
///
/// Kani refuses a `#![no_std]` input that never names it, and this kernel has
/// no harness until task 1.2.4, so the declaration is what makes it a legal
/// codegen subject for the AC-04 proof profile. It adds no dependency:
/// `cfg(kani)` is false in every ordinary build, no Cargo dependency edge is
/// created, and the workspace already declares `cfg(kani)` in its
/// `unexpected_cfgs` table. It replaces no production body, which is the
/// substitution technical design §17.7 forbids.
#[cfg(kani)]
extern crate kani;

/// Facts about the compilation target that checked rules must use.
///
/// ```
/// use combobulate_kernel::TargetFacts;
///
/// const BITS: u32 = TargetFacts::current().usize_bits();
/// assert_eq!(
///     BITS,
///     usize::BITS,
///     "the kernel reports the target's usize width"
/// );
/// ```
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TargetFacts {
    /// Width of `usize` on the target, in bits.
    usize_bits: u32,
}

impl TargetFacts {
    /// Facts for the target this crate is compiled for.
    #[must_use]
    pub const fn current() -> Self {
        Self {
            usize_bits: usize::BITS,
        }
    }

    /// Width of `usize` on the target, in bits.
    #[must_use]
    pub const fn usize_bits(self) -> u32 { self.usize_bits }
}

#[cfg(test)]
mod tests {
    //! Checks that the kernel reports the target pointer width.

    use super::TargetFacts;

    #[test]
    fn current_reports_the_target_pointer_width() {
        assert_eq!(
            TargetFacts::current().usize_bits(),
            usize::BITS,
            "the kernel must report the target's usize width, not a host constant"
        );
    }
}
