//! One dependency-free executable source shared by ordinary and verifier builds.

#[cfg(verus_keep_ghost)]
use vstd::prelude::*;

/// Increment a value whose caller has reserved space for the result.
#[cfg_attr(verus_keep_ghost, verus_verify, verus_spec(result =>
    requires value < 254,
    ensures result == value + 1,
))]
pub fn increment(value: u8) -> u8 { value + 1 }
