//! Companion-crate verification of the shared executable source.
#![no_std]
use vstd::prelude::*;
use wiring_production::increment;

verus! {
/// The wrapper's contract depends on the shared implementation's specification.
pub fn capability(value: u8) -> (result: u8)
    requires value < 254,
    ensures result == value + 1,
{ increment(value) }

/// The seeded wrapper mutant must fail the same postcondition.
pub fn mutant(value: u8) -> (result: u8)
    requires value < 254,
    ensures result == value + 1,
{ increment(value) + 1 }
}
