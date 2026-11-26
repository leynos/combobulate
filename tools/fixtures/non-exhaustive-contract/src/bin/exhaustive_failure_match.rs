//! A downstream exhaustive match on [`Failure`] must not compile.
//!
//! `Failure` is `#[non_exhaustive]`, so a caller may not assume it has seen
//! every variant. This file states that assumption the way a caller would
//! naturally write it — naming each variant it knows and no wildcard — and
//! `tests/non_exhaustive_contract.rs` requires the build to fail with E0004.
//!
//! The value arrives as a parameter rather than being constructed here,
//! deliberately: constructing a variant is itself `E0639`, and rustc stops
//! after the first error in a crate. A construction would therefore report the
//! wrong contract and never reach the match.
//!
//! The body is gated on a `cfg` the manifest declares and an ordinary build
//! never sets, so only the contract test compiles it.

#[cfg(nonexhaustive_contract)]
fn main() {
    use combobulate::Failure;

    fn describe(failure: Failure) -> &'static str {
        match failure {
            Failure::ShapeAgreement { .. } => "shape",
            Failure::IntegerOverflow { .. } => "overflow",
        }
    }

    let _ = describe;
}

#[cfg(not(nonexhaustive_contract))]
fn main() {}
