//! A downstream construction of [`NativeExecutor`] must not compile.
//!
//! `NativeExecutor` is `#[non_exhaustive]`, so a caller may not build one by
//! naming its fields: a later release may add scratch space or policies, and
//! the caller's expression would then be wrong for a reason it could not see.
//! A caller builds one through `NativeExecutor::sequential` or
//! `NativeExecutor::default`, which `covered` exercises.
//!
//! `tests/non_exhaustive_contract.rs` requires this build to fail with E0639.
//!
//! The body is gated on a `cfg` the manifest declares and an ordinary build
//! never sets, so only the contract test compiles it.

#[cfg(nonexhaustive_contract)]
fn main() {
    use combobulate::NativeExecutor;

    let _ = NativeExecutor {};
}

#[cfg(not(nonexhaustive_contract))]
fn main() {}
