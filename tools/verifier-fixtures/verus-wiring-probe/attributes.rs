//! Optional attribute-based specifications leave ordinary Rust bodies intact.
#![no_std]
#[cfg(feature = "verus")]
use vstd::prelude::*;

/// A small executable contract checks that optional annotations are active.
#[cfg_attr(feature = "verus", verus_verify, verus_spec(result =>
    requires value < 254,
    ensures result == value + 1,
))]
pub fn capability(value: u8) -> u8 { value + 1 }

/// The seeded mutant must fail the same postcondition.
#[cfg_attr(feature = "verus", verus_verify, verus_spec(result =>
    requires value < 254,
    ensures result == value + 1,
))]
pub fn mutant(value: u8) -> u8 { value + 2 }
