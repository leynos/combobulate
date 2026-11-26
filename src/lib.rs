//! Combobulate: inspectable array and typed-collection algebra.
//!
//! The `comb!` notation is not implemented yet, but this release carries the
//! minimal ordinary application path: materialized [`Array`] values, deferred
//! [`AExpr`] handles, and the [`identity`] and [`add`] operations that a first
//! consumer can apply to I64 vectors. The workspace also publishes its build
//! profiles, a `#![no_std]` kernel that owns target facts and the verified
//! addition, a procedural-macro crate waiting for the notation, and an
//! optional Polars backend.

#![forbid(unsafe_code)]

mod array;
mod error;
mod expr;
mod plan;
mod profile;

pub use array::{Array, Dtype};
pub use error::{ExpressionError, Failure, Stage};
pub use expr::{AExpr, Binary, OperationId, Unary, add, identity};
pub use plan::{NativeExecutor, PreparedPlan};

#[cfg(feature = "polars")]
pub(crate) mod polars_backend;

/// The Polars backend could not complete its wiring probe.
///
/// The type is the facade's own, and names no Polars item: DL-19 confines the
/// dependency to `polars_backend`, and VO-14 fails the build of the design
/// pack if a `polars::` path reaches any other module. Re-exporting Polars'
/// error here would leak that path into this file's public signature.
#[cfg(feature = "polars")]
pub use polars_backend::BackendProbeError;
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
/// # Ok::<(), combobulate::BackendProbeError>(())
/// ```
///
/// # Errors
///
/// Returns [`BackendProbeError`] when the frame cannot be constructed or
/// collected, carrying Polars' own message as text.
#[cfg(feature = "polars")]
#[doc(hidden)]
pub fn polars_backend_probe() -> Result<usize, BackendProbeError> {
    polars_backend::collected_height()
}
