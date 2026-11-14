//! Scratch kernel matching the approved TargetFacts body.
#![no_std]
/// Facts about the compilation target.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TargetFacts { usize_bits: u32 }
impl TargetFacts {
    /// Construct facts for this compilation target.
    pub const fn current() -> Self { Self { usize_bits: usize::BITS } }
    /// Return the target width.
    pub const fn usize_bits(self) -> u32 { self.usize_bits }
}
