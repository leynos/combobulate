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
    has_macros: bool,
    has_polars: bool,
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

    /// The backend names compiled into this build, in report order.
    ///
    /// The native backend is always present, because it is the facade itself;
    /// the optional backends follow in the order the profile line prints them.
    fn backend_names(self) -> impl Iterator<Item = &'static str> {
        core::iter::once("native")
            .chain(self.has_macros.then_some("macros"))
            .chain(self.has_polars.then_some("polars"))
    }
}

impl core::fmt::Display for BuildProfile {
    /// Renders the one-line report, e.g.
    /// `features: native, macros, polars; target usize: 64 bits`.
    fn fmt(&self, formatter: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        formatter.write_str("features: ")?;
        let mut names = self.backend_names();
        if let Some(first) = names.next() {
            formatter.write_str(first)?;
        }
        for name in names {
            formatter.write_str(", ")?;
            formatter.write_str(name)?;
        }
        write!(formatter, "; target usize: {} bits", self.target_usize_bits)
    }
}

#[cfg(test)]
mod tests {
    //! Checks the report against the features this test binary was built with.

    use super::BuildProfile;

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
