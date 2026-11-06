//! Non-optional macro-based Verus wiring.
#![no_std]
use vstd::prelude::*;

verus! {
/// A small executable contract checks that annotations are active.
pub fn capability(value: u8) -> (result: u8)
    requires value < 254,
    ensures result == value + 1,
{ value + 1 }

/// The seeded mutant must fail the same postcondition.
pub fn mutant(value: u8) -> (result: u8)
    requires value < 254,
    ensures result == value + 1,
{ value + 2 }
}
