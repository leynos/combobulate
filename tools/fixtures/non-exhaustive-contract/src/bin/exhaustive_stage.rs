//! A downstream exhaustive match on [`Stage`] must not compile.
//!
//! `Stage` is `#[non_exhaustive]`, so a caller's match must tolerate a stage a
//! later release adds. `tests/non_exhaustive_contract.rs` requires this build to
//! fail with E0004; a build that succeeded would mean the attribute had been
//! dropped and a caller's match would break on the next release instead.

#[cfg(nonexhaustive_contract)]
fn main() {
    use combobulate::Stage;

    let stage = Stage::Preparation;
    let _ = match stage {
        Stage::Preparation => "preparation",
        Stage::Execution => "execution",
    };
}

#[cfg(not(nonexhaustive_contract))]
fn main() {}
