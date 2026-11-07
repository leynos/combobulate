//! The crate-private Polars backend, compiled only under the `polars` feature.
//!
//! The module exists so the Polars-enabled profile has a real compilation and
//! link target: building it proves the pinned Polars release integrates with
//! the facade and its build standard. It claims no capability. Task 1.2.6 owns
//! the capability statuses and must not infer them from this module.

/// Builds an `Int64` series and collects a trivial `LazyFrame`.
///
/// This is a wiring proof rather than an operation: it exercises Polars'
/// eager constructor, its lazy plan, and its collect step, so a build that
/// compiles and links this module has a working Polars dependency.
///
/// # Errors
///
/// Returns Polars' own error when the frame cannot be constructed or the
/// collected frame reports its height.
///
/// The function is crate-private; the facade's `#[doc(hidden)]` probe makes
/// the link target reachable from an integration test and a doctest.
pub(crate) fn collected_height() -> polars::prelude::PolarsResult<usize> {
    // The traits carry `Series::new` and `DataFrame::lazy`; the feature set is
    // deliberately minimal, so neither is re-exported as an inherent method.
    use polars::prelude::{
        DataFrame,
        IntoColumn,
        IntoLazy as _,
        NamedFrom as _,
        PolarsResult,
        Series,
    };

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

    // The body reports a failure by panicking rather than by returning Polars'
    // error. A `Result`-returning test that also asserts is rejected by
    // `clippy::panic_in_result_fn`, and the workspace denies that lint. So the
    // fallible read is unwrapped once here, and the assertion is infallible.
    #[test]
    fn int64_series_round_trips_through_lazy_collection() {
        let Ok(height) = super::collected_height() else {
            panic!("the pinned Polars release must collect the probe frame")
        };
        assert_eq!(
            height, 3,
            "the selected feature set must preserve all three rows"
        );
    }
}
