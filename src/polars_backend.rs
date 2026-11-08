//! The crate-private Polars backend, compiled only under the `polars` feature.
//!
//! The module exists so the Polars-enabled profile has a real compilation and
//! link target: building it proves the pinned Polars release integrates with
//! the facade and its build standard. It claims no capability. Task 1.2.6 owns
//! the capability statuses and must not infer them from this module.
//!
//! DL-19 confines Polars to this module, and VO-14 checks that no `polars::`
//! path reaches the rest of the facade. That is why the backend reports
//! [`BackendProbeError`] rather than Polars' own error: an error type in a
//! public signature would carry a Polars path out of the module that owns it.

use polars::prelude::{DataFrame, IntoColumn, IntoLazy as _, NamedFrom as _, PolarsResult, Series};

/// The backend could not build or collect the probe's frame.
///
/// The type deliberately names no Polars item. Polars' own error is rendered to
/// text here, at the one boundary that already depends on Polars, so the
/// facade's surface stays free of the dependency (VO-14).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BackendProbeError {
    /// Polars' own rendering of what failed.
    detail: String,
}

impl BackendProbeError {
    /// Polars' own description of the failure.
    ///
    /// An embedder reports the text as it stands; it is Polars' own wording,
    /// so it is neither translated nor prefixed here. The module's
    /// `Display` adds the backend's name, which is the form to log.
    #[must_use]
    pub fn detail(&self) -> &str { &self.detail }
}

impl core::fmt::Display for BackendProbeError {
    fn fmt(&self, formatter: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(
            formatter,
            "the Polars backend could not complete its probe: {}",
            self.detail
        )
    }
}

impl core::error::Error for BackendProbeError {}

/// Builds an `Int64` series and collects a trivial `LazyFrame`.
///
/// This is a wiring proof rather than an operation: it exercises Polars'
/// eager constructor, its lazy plan, and its collect step, so a build that
/// compiles and links this module has a working Polars dependency.
///
/// # Errors
///
/// Returns [`BackendProbeError`] when the frame cannot be constructed or the
/// collected frame reports its height, carrying Polars' own message.
///
/// The function is crate-private; the facade's `#[doc(hidden)]` probe makes
/// the link target reachable from an integration test and a doctest.
pub(crate) fn collected_height() -> Result<usize, BackendProbeError> {
    collect().map_err(|error| BackendProbeError {
        detail: error.to_string(),
    })
}

/// The Polars-typed part of the probe, kept separate so the error conversion
/// happens once and `collected_height` reads as a plain `Result`.
fn collect() -> PolarsResult<usize> {
    let values = Series::new("values".into(), &[1_i64, 2, 3]);
    let column = IntoColumn::into_column(values);
    PolarsResult::Ok(
        DataFrame::new(column.len(), vec![column])?
            .lazy()
            .collect()?
            .height(),
    )
}

#[cfg(test)]
mod tests {
    //! The enabled profile must actually link the pinned Polars release.

    // A `#[test]` that returns `Result` may contain no assertion, because the
    // workspace denies `clippy::panic_in_result_fn`. So the test is infallible
    // and folds the fallible read into the assertion: `as_ref().ok()` borrows
    // the backend's error instead of unwrapping it, so there is no panic arm
    // and no unwrap, and the single `assert_eq!` reports both the error case
    // and the wrong-height case, with the values, through one diagnostic.
    #[test]
    fn int64_series_round_trips_through_lazy_collection() {
        let collected = super::collected_height();
        assert_eq!(
            collected.as_ref().ok(),
            Some(&3),
            "the pinned Polars release must collect all three probe rows, got {collected:?}"
        );
    }

    /// The backend's error renders Polars' own text and names the backend.
    ///
    /// The success path cannot reach either method, so without this the
    /// `detail` accessor and the `Display` body would be unexercised code that
    /// still has to compile. Rendering is asserted as a whole sentence rather
    /// than a substring so a reworded message is a decision, not a silent
    /// change to what an embedder reads.
    #[test]
    fn the_probe_error_names_the_backend_and_carries_polars_message() {
        let error = super::BackendProbeError {
            detail: "something Polars said".to_owned(),
        };
        assert_eq!(
            (error.detail(), error.to_string()),
            (
                "something Polars said",
                "the Polars backend could not complete its probe: something Polars said".to_owned()
            ),
            "the backend's error must expose Polars' message and say where it came from"
        );
    }
}
