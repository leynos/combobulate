//! Combobulate: inspectable array and typed-collection algebra.
//!
//! The array algebra and `comb!` notation are not implemented yet. This
//! release publishes the workspace layout and its build profiles: a `#![no_std]`
//! kernel that owns target facts, a procedural-macro crate waiting for the
//! notation, an optional Polars backend, and this facade. See the repository
//! design documents for the intended contracts.

#![forbid(unsafe_code)]

mod profile;

#[cfg(feature = "polars")]
pub(crate) mod polars_backend;

pub use profile::BuildProfile;

/// Builds an `Int64` series and collects a trivial frame, proving that the
/// pinned Polars release compiles and links.
///
/// The item is hidden from the documented API because it is a wiring probe,
/// not an operation: it exists so an integration test can execute the backend
/// the build links. `tests/polars_backend.rs` is that test.
///
/// ```
/// assert_eq!(
///     combobulate::polars_backend_probe()?,
///     3,
///     "the pinned Polars release must collect all three rows"
/// );
/// # Ok::<(), polars::error::PolarsError>(())
/// ```
///
/// # Errors
///
/// Returns Polars' own error when the frame cannot be constructed or
/// collected.
#[cfg(feature = "polars")]
#[doc(hidden)]
pub fn polars_backend_probe() -> polars::prelude::PolarsResult<usize> {
    polars_backend::collected_height()
}
