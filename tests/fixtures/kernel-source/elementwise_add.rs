//! A seeded kernel submodule: every substitute-body rule broken once.
//!
//! Each construct here is legal Rust that would compile, and each one is what
//! technical design §17.7 forbids: an allocation declaration, a second body
//! behind a verifier-only `cfg`, a Kani-only definition, and a relaxation of
//! the core-only lints. The root above is clean, so a scan that reached only
//! `lib.rs` would report nothing here — which is what makes this tree the
//! negative control for the widened VO-6 scan rather than a sample of its
//! findings.
//!
//! The file seeds the VO-6 rules and nothing else. In particular it carries no
//! trust vocabulary: `tests/` is audited as shipped source by
//! `scripts/docs_validation/trust_audit_check.py`, so a seeded `external_body`
//! or `assume` here would fail `make design-check` rather than demonstrate
//! anything about this scan. The trust audit has its own corpus under
//! `tools/verifier-fixtures/`.

extern crate alloc;
extern crate std;

#[cfg(not(verus_keep_ghost))]
pub const fn add_i64_into(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> bool {
    let _ = (lhs, rhs, out);
    false
}

#[cfg(verus_keep_ghost)]
pub fn verified_copy(lhs: &[i64]) -> usize { lhs.len() }

#[cfg(kani)]
fn kani_witness() -> bool { true }

#[allow(clippy::std_instead_of_core)]
#[expect(clippy::alloc_instead_of_core, reason = "seeded for the VO-6 scan")]
fn relaxed() -> usize { 0 }
