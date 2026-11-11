//! A downstream crate that names the facade's two Polars-gated items.
//!
//! This file is expected never to build. `tests/polars_surface_ui.rs` compiles
//! it to prove the items are absent from the native-only profile, and fails if
//! the build succeeds or if it fails for any reason other than both names being
//! unresolvable.
//!
//! The two statements are deliberately separate items rather than one
//! expression, so the absence of each is a diagnostic of its own: a gate that
//! re-exported one and not the other must not be able to pass.

fn main() {
    // The error type must not exist without the backend that produces it.
    let _absent_error: Option<combobulate::BackendProbeError> = None;
    // Nor may the probe be reachable, in a path or a value position.
    let _absent_probe = combobulate::polars_backend_probe;
}
