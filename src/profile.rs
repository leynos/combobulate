//! Features and target facts compiled into this build of Combobulate.
//!
//! The report exists so an embedder can tell which backends the binary it is
//! holding actually contains, without inspecting Cargo's build plan. It states
//! compiled features and target facts only: it is not a capability report, and
//! nothing may infer supported operations from it.

use combobulate_kernel::TargetFacts;

/// Features and target facts compiled into this build of Combobulate.
///
/// Every accessor is `const`, so a build profile can be folded into constant
/// context and a test can assert against it without runtime construction.
///
/// ```
/// use combobulate::BuildProfile;
///
/// const PROFILE: BuildProfile = BuildProfile::current();
/// assert_eq!(
///     PROFILE.target_usize_bits(),
///     usize::BITS,
///     "the profile must report the compilation target's pointer width"
/// );
/// ```
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BuildProfile {
    /// Whether this build enabled the `macros` feature.
    has_macros: bool,
    /// Whether this build enabled the `polars` feature.
    has_polars: bool,
    /// Width of `usize` on the compilation target, in bits.
    target_usize_bits: u32,
}

impl BuildProfile {
    /// Features and target facts for the crate this code was compiled into.
    #[must_use]
    pub const fn current() -> Self {
        Self {
            has_macros: cfg!(feature = "macros"),
            has_polars: cfg!(feature = "polars"),
            target_usize_bits: TargetFacts::current().usize_bits(),
        }
    }

    /// Whether the `macros` feature is compiled into this build.
    #[must_use]
    pub const fn has_macros(self) -> bool { self.has_macros }

    /// Whether the `polars` feature is compiled into this build.
    #[must_use]
    pub const fn has_polars(self) -> bool { self.has_polars }

    /// Width of `usize` on the compilation target, in bits.
    #[must_use]
    pub const fn target_usize_bits(self) -> u32 { self.target_usize_bits }

    /// The optional backends compiled into this build, in report order.
    ///
    /// The native backend is always present, because it is the facade itself,
    /// and `Display` writes it before these. Returning only the optional names
    /// keeps the always-present name out of the iterator, so the report cannot
    /// be rendered with no backend at all.
    fn optional_backend_names(self) -> impl Iterator<Item = &'static str> {
        self.has_macros
            .then_some("macros")
            .into_iter()
            .chain(self.has_polars.then_some("polars"))
    }
}

impl core::fmt::Display for BuildProfile {
    /// Renders the one-line report, e.g.
    /// `features: native, macros, polars; target usize: 64 bits`.
    fn fmt(&self, formatter: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        formatter.write_str("features: native")?;
        for name in self.optional_backend_names() {
            formatter.write_str(", ")?;
            formatter.write_str(name)?;
        }
        write!(formatter, "; target usize: {} bits", self.target_usize_bits)
    }
}

#[cfg(test)]
mod tests {
    //! Checks the report against the features this test binary was built with.

    use rstest::rstest;

    use super::BuildProfile;

    /// Renders the report for each combination of the two optional backends.
    ///
    /// `Display` walks an iterator over the compiled optional backends, so the
    /// loop body is reached only when at least one feature is enabled. A
    /// native-only build compiles both flags to `false`, which would leave the
    /// separator and name writes unexecuted — and that is the profile the
    /// coverage gate measures. Constructing each combination here renders the
    /// loop in every profile, including the one that compiles it unreachable.
    #[rstest]
    #[case::native(false, false, "native")]
    #[case::macros(true, false, "native, macros")]
    #[case::polars(false, true, "native, polars")]
    #[case::both(true, true, "native, macros, polars")]
    fn display_names_each_compiled_backend(
        #[case] has_macros: bool,
        #[case] has_polars: bool,
        #[case] expected_backends: &str,
    ) {
        let profile = BuildProfile {
            has_macros,
            has_polars,
            target_usize_bits: usize::BITS,
        };
        let bits = profile.target_usize_bits();
        let expected = format!("features: {expected_backends}; target usize: {bits} bits");
        assert_eq!(
            profile.to_string(),
            expected,
            "the report must name exactly the optional backends the profile records"
        );
    }

    #[test]
    fn current_reports_the_compiled_features() {
        let profile = BuildProfile::current();
        assert_eq!(
            profile.has_macros(),
            cfg!(feature = "macros"),
            "the profile must report the `macros` feature exactly as compiled"
        );
        assert_eq!(
            profile.has_polars(),
            cfg!(feature = "polars"),
            "the profile must report the `polars` feature exactly as compiled"
        );
    }

    #[test]
    fn current_reports_the_target_pointer_width() {
        assert_eq!(
            BuildProfile::current().target_usize_bits(),
            usize::BITS,
            "the profile must report the target's usize width, not a host constant"
        );
    }
}
