//! A downstream exhaustive match on [`Dtype`] must not compile.
//!
//! `Dtype` is `#[non_exhaustive]`, so a caller may not assume it has seen every
//! variant. This file states the assumption that is forbidden, and
//! `tests/non_exhaustive_contract.rs` requires the build to fail with E0004.
//!
//! The body is gated on a `cfg` the manifest declares and an ordinary build
//! never sets, so only the contract test compiles it.

#[cfg(nonexhaustive_contract)]
fn main() {
    use combobulate::Dtype;

    let dtype = Dtype::I64;
    let _ = match dtype {
        Dtype::I64 => "i64",
    };
}

#[cfg(not(nonexhaustive_contract))]
fn main() {}
