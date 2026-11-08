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

use polars::prelude::{
    DataFrame,
    IntoColumn,
    IntoLazy as _,
    NamedFrom as _,
    PolarsError,
    PolarsResult,
    Series,
};

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

    /// Render a Polars failure into the backend's own error.
    ///
    /// The conversion is its own item rather than an inline closure so the
    /// suite can exercise it directly with a hand-built failure: the probe's
    /// own collection succeeds for every frame it builds, so the error arm is
    /// otherwise unreachable. That is also why `collected_height` folds through
    /// [`fold_collected`] instead of a `map_err` closure — a closure the suite
    /// cannot run is still a function instantiation LLVM records, and it would
    /// count against the workspace's coverage ratchet on a line no test could
    /// turn green.
    ///
    /// A `From<PolarsError>` impl would be worse than an unreachable line: it
    /// is public API, so it would hand every embedder a route from a Polars
    /// type to the facade's error, which is the leak DL-19 exists to prevent.
    fn from_polars(error: &PolarsError) -> Self {
        Self {
            detail: error.to_string(),
        }
    }
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
pub(crate) fn collected_height() -> Result<usize, BackendProbeError> { fold_collected(collect()) }

/// Folds a collected height into the facade's own result.
///
/// This is a named item rather than a `map_err` closure inside
/// [`collected_height`] because the closure would be a function instantiation
/// the suite can never execute: `collect` succeeds for every frame the probe
/// builds. LLVM would still record the closure's line, so it would count in
/// `LF` and never in `LH` and the coverage ratchet would fail on it. Naming
/// the fold makes the error arm a plain call the suite can make directly.
///
/// # Errors
///
/// Returns [`BackendProbeError`] when the collection failed, carrying Polars'
/// own message.
fn fold_collected(collected: PolarsResult<usize>) -> Result<usize, BackendProbeError> {
    match collected {
        Ok(height) => Ok(height),
        Err(error) => Err(BackendProbeError::from_polars(&error)),
    }
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

    /// A Polars failure crosses the boundary as Polars' own rendering.
    ///
    /// `collected_height` folds a live Polars error through `fold_collected`,
    /// but the probe's `collect` succeeds for every frame it builds, so the
    /// success path alone would leave both the fold's error arm and `from_polars`
    /// unexercised. A hand-built `ComputeError` renders as its bare message, so
    /// the expected detail is predictable and any future re-wrapping of Polars'
    /// text becomes a visible decision rather than a silent change to what an
    /// embedder logs.
    #[test]
    fn from_polars_carries_the_polars_message_into_the_detail() {
        let failure = polars::error::PolarsError::ComputeError(
            polars::error::ErrString::new_static("something Polars said"),
        );
        let converted = super::BackendProbeError::from_polars(&failure);
        assert_eq!(
            converted.detail(),
            "something Polars said",
            "a Polars failure must arrive as Polars' own message, not a paraphrase"
        );
    }

    /// A failed collection reaches the facade as the backend's own error.
    ///
    /// This is the arm the probe's own frame cannot reach, since `collect`
    /// succeeds for every frame it builds. Driving it through `fold_collected`
    /// with a hand-built failure keeps the branch a plain assertion target
    /// instead of code the suite could only reach by first breaking Polars.
    #[test]
    fn a_failed_collection_crosses_the_boundary_as_the_backend_error() {
        let failure = polars::error::PolarsError::ComputeError(
            polars::error::ErrString::new_static("something Polars said"),
        );
        let folded = super::fold_collected(Err(failure));
        assert_eq!(
            folded.as_ref().err().map(super::BackendProbeError::detail),
            Some("something Polars said"),
            "a failed collection must surface as the backend's error, not a panic"
        );
    }
}
