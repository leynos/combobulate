//! The enabled profile's Polars backend is reachable from outside the crate.
//!
//! `src/polars_backend.rs` is crate-private, and its own unit test proves the
//! module compiles and links. This file proves the facade exposes that link
//! target to a dependent crate: the probe is the only route an embedder has to
//! the backend, so a probe that no external test calls could be removed without
//! any test noticing.
//!
//! The whole file is gated on the feature, so the native-only profile compiles
//! it to an empty test binary rather than failing on a missing item. That is
//! deliberate: the native-only route must be able to build every target.

#![cfg(feature = "polars")]

/// The probe collects all three rows through the facade's public surface.
#[test]
fn the_probe_reaches_the_polars_backend_from_a_dependent_crate() {
    let collected = combobulate::polars_backend_probe();
    assert_eq!(
        collected.as_ref().ok(),
        Some(&3),
        "the facade must expose the linked backend's collected height, got {collected:?}"
    );
}
