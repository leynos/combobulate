//! A downstream construction of a [`Failure`] variant must not compile.
//!
//! Each `Failure` variant is `#[non_exhaustive]`, so a caller may not write one
//! field by field: a later release may add a field, and the caller's expression
//! would then be wrong for a reason it could not see.
//! `tests/non_exhaustive_contract.rs` requires this build to fail with E0639.

#[cfg(nonexhaustive_contract)]
fn main() {
    use combobulate::{Failure, identity};

    let _ = Failure::IntegerOverflow {
        operation: identity().operation_id(),
        position: 0,
    };
}

#[cfg(not(nonexhaustive_contract))]
fn main() {}
