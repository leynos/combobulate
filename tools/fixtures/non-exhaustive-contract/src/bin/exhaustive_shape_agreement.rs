//! A downstream construction of [`Failure::ShapeAgreement`] must not compile.
//!
//! `Failure`'s variants are each `#[non_exhaustive]` as well as the enum, so a
//! caller may not write one field by field: a later release may add a field,
//! and the caller's expression would then be wrong for a reason it could not
//! see. `tests/non_exhaustive_contract.rs` requires this build to fail with
//! E0639.
//!
//! `exhaustive_failure` states the same contract for `IntegerOverflow`; both
//! variants carry the attribute, so both need their own statement. One binary
//! per contract, because rustc stops after the first error in a crate.
//!
//! The body is gated on a `cfg` the manifest declares and an ordinary build
//! never sets, so only the contract test compiles it.

#[cfg(nonexhaustive_contract)]
fn main() {
    use combobulate::{Failure, identity};

    let _ = Failure::ShapeAgreement {
        operation: identity().operation_id(),
        lhs_len: 1,
        rhs_len: 2,
    };
}

#[cfg(not(nonexhaustive_contract))]
fn main() {}
