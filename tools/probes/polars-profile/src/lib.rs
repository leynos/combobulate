//! Compile-cost probe for the proposed facade's Polars feature profile.

/// Build an Int64 series and collect a trivial lazy frame.
///
/// ```
/// assert_eq!(
///     polars_profile::collected_height()?,
///     3,
///     "the probe must collect all three rows"
/// );
/// # Ok::<(), polars::error::PolarsError>(())
/// ```
#[cfg(feature = "polars")]
pub fn collected_height() -> polars::prelude::PolarsResult<usize> {
    use polars::prelude::*;
    let values = Series::new("values".into(), &[1_i64, 2, 3]);
    Ok(DataFrame::new(values.len(), vec![values.into()])?
        .lazy()
        .collect()?
        .height())
}

#[cfg(all(test, feature = "polars"))]
mod tests {
    //! The chosen features must exercise both eager and lazy public interfaces.
    #[test]
    fn int64_series_round_trips_through_lazy_collection() {
        assert_eq!(
            super::collected_height().expect("collect the Int64 frame"),
            3,
            "the selected feature set must preserve all three rows"
        );
    }
}
