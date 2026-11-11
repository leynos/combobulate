//! Behaviour contracts for the build profile this binary was compiled with.
//!
//! Cargo selects `macros` and `polars` independently, so four builds exist and
//! each route binds the scenarios that describe its own. The two single-feature
//! routes exist because every other route turns both features on or both off:
//! a `BuildProfile::current()` that reported each flag as the other's would
//! pass a default build and a native-only build alike, and only a build with
//! exactly one feature can tell them apart.
//!
//! Every route asserts its own backend is reported and the other is absent, so
//! a report that always or never claims one of them fails at least one route. A
//! tag filter that matches no scenario is a compile error, so binding a
//! scenario can never pass by running nothing.
//!
//! Only the `Given` steps are gated. `rstest-bdd` keys its step registry by
//! keyword and pattern and panics when two definitions share one, so the four
//! routes each own a mutually exclusive gate around their own `Given`, while
//! every `Then` reads the recorded profile and is therefore the same code on
//! all four. Keeping them in one ungated module means a route cannot silently
//! assert a weaker claim than its neighbours.

mod shared {
    //! The scenario world and the steps every profile route shares.
    //!
    //! The routes differ only in which features are compiled in. The recorded
    //! read, the `When` step that fills it, and every assertion about the
    //! recorded profile are the same code on all four, so they live here once:
    //! a change to the world's shape cannot then leave one route reading a
    //! field the other no longer has.

    use combobulate::BuildProfile;
    use pretty_assertions::assert_eq;
    use rstest::fixture;
    use rstest_bdd_macros::{then, when};

    /// Records which features the running binary was compiled with.
    #[derive(Debug, Default)]
    pub(super) struct Observed {
        /// A read taken from `BuildProfile::current()` in the `When` step.
        pub(super) profile: Option<BuildProfile>,
    }

    /// Supplies the scenario's world.
    ///
    /// `#[scenario]` resolves each parameter by looking for a fixture of the
    /// same name, so this function is what makes `observed: Observed` bind.
    //
    // `fn_single_line = true` in `rustfmt.toml` puts this body on one line, and
    // `#[fixture]` then expands it into a nested single-expression block, which
    // is what `unused_braces` rejects. The attribute pair is the workaround the
    // maintainer sanctions for that expansion (see
    // `weaver-test-macros::allow_fixture_expansion_lints`, which emits exactly
    // these two attributes): the `allow` suppresses the lint on the expansion,
    // and the `expect` keeps `clippy::allow_attributes` satisfied for using
    // `allow` rather than `expect` on a lint that only fires in the expansion.
    //
    // The `expect` is not behind `cfg(clippy)`. Clippy rejects that wrapper
    // with `unnecessary_clippy_cfg`, and the plain wrapper is also what the
    // driver emits, so the two agree on one spelling.
    #[allow(
        unused_braces,
        reason = "fixture macro expansion triggers unused-braces on expression bodies"
    )]
    #[expect(
        clippy::allow_attributes,
        reason = "needed to allow unused_braces for fixture macro expansion"
    )]
    #[fixture]
    pub(super) fn observed() -> Observed { Observed::default() }

    #[when("a consumer reads the build profile")]
    pub(super) fn read_profile(observed: &mut Observed) {
        observed.profile = Some(BuildProfile::current());
    }

    /// Unwraps the profile the `When` step recorded.
    pub(super) fn recorded(observed: &Observed) -> BuildProfile {
        let Some(profile) = observed.profile else {
            panic!("the `When` step must run before any `Then` step")
        };
        profile
    }

    #[then("the profile reports the native backend")]
    pub(super) fn reports_native(observed: &Observed) {
        let line = recorded(observed).to_string();
        assert!(
            line.starts_with("features: native"),
            "the profile must always begin with the native backend, got {line:?}"
        );
    }

    #[then("the profile reports a Polars backend")]
    pub(super) fn reports_polars(observed: &Observed) {
        let profile = recorded(observed);
        assert!(
            profile.has_polars(),
            "a build with the polars feature must report a Polars backend"
        );
        assert!(
            profile.to_string().contains("polars"),
            "the rendered line must name Polars, got {profile}"
        );
    }

    #[then("the profile does not report a Polars backend")]
    pub(super) fn does_not_report_polars(observed: &Observed) {
        let profile = recorded(observed);
        assert!(
            !profile.has_polars(),
            "a build without the polars feature must not report a Polars backend"
        );
        assert!(
            !profile.to_string().contains("polars"),
            "the rendered line must not name Polars, got {profile}"
        );
    }

    #[then("the profile reports the macro feature")]
    pub(super) fn reports_macros(observed: &Observed) {
        assert!(
            recorded(observed).has_macros(),
            "a build with the macros feature must report it"
        );
    }

    #[then("the profile does not report the macro feature")]
    pub(super) fn does_not_report_macros(observed: &Observed) {
        assert!(
            !recorded(observed).has_macros(),
            "a build without the macros feature must not report it"
        );
    }

    #[then("the profile reports the target usize width")]
    pub(super) fn reports_target_usize_width(observed: &Observed) {
        assert_eq!(
            recorded(observed).target_usize_bits(),
            usize::BITS,
            "the profile must report the compilation target's usize width"
        );
    }
}

#[cfg(all(not(feature = "macros"), not(feature = "polars")))]
mod native_only {
    //! The native-only route: no macros, no Polars.

    use combobulate::BuildProfile;
    use rstest_bdd_macros::{given, scenario};

    use super::shared::{Observed, observed};

    #[given("the facade compiled without default features")]
    fn compiled_without_default_features() {
        let profile = BuildProfile::current();
        assert!(
            !profile.has_macros() && !profile.has_polars(),
            "the native-only route must be built without default features, got {profile}"
        );
    }

    #[scenario(
        path = "tests/features/build_profiles.feature",
        name = "A native-only build reports no Polars backend",
        tags = "@native"
    )]
    fn native_only_reports_no_polars_backend(observed: Observed) {
        // The `When` step must have run; otherwise the `Then` steps are
        // asserting against an unset profile.
        assert!(
            observed.profile.is_some(),
            "every `Then` step depends on the `When` step recording a profile"
        );
    }
}

#[cfg(all(feature = "macros", not(feature = "polars")))]
mod macros_only {
    //! The macros-only route: the `comb!` notation's crate without Polars.
    //!
    //! This is the profile a `BuildProfile::current()` that swapped the two
    //! flags would misreport, and no other route builds it.

    use combobulate::BuildProfile;
    use rstest_bdd_macros::{given, scenario};

    use super::shared::{Observed, observed};

    #[given("the facade compiled without default features but with the macros feature")]
    fn compiled_with_macros_alone() {
        let profile = BuildProfile::current();
        assert!(
            profile.has_macros() && !profile.has_polars(),
            "the macros-only route must be built with the macros feature alone, got {profile}"
        );
    }

    #[scenario(
        path = "tests/features/build_profiles.feature",
        name = "A macros-only build reports the macro feature and no Polars backend",
        tags = "@macros"
    )]
    fn macros_only_reports_no_polars_backend(observed: Observed) {
        assert!(
            observed.profile.is_some(),
            "every `Then` step depends on the `When` step recording a profile"
        );
    }
}

#[cfg(all(feature = "macros", feature = "polars"))]
mod default_profile {
    //! The default route: both optional features are compiled in.

    use combobulate::BuildProfile;
    use rstest_bdd_macros::{given, scenario};

    use super::shared::{Observed, observed};

    #[given("the facade compiled with default features")]
    fn compiled_with_default_features() {
        let profile = BuildProfile::current();
        assert!(
            profile.has_macros() && profile.has_polars(),
            "the default route must be built with default features, got {profile}"
        );
    }

    #[scenario(
        path = "tests/features/build_profiles.feature",
        name = "The default build reports the Polars backend",
        tags = "@polars"
    )]
    fn default_reports_the_polars_backend(observed: Observed) {
        assert!(
            observed.profile.is_some(),
            "every `Then` step depends on the `When` step recording a profile"
        );
    }
}

#[cfg(all(not(feature = "macros"), feature = "polars"))]
mod polars_only {
    //! The Polars-only route: the backend without the macro crate.
    //!
    //! The mirror image of `macros_only`, and the other profile a swapped
    //! report would misdescribe.

    use combobulate::BuildProfile;
    use rstest_bdd_macros::{given, scenario};

    use super::shared::{Observed, observed};

    #[given("the facade compiled without default features but with the polars feature")]
    fn compiled_with_polars_alone() {
        let profile = BuildProfile::current();
        assert!(
            !profile.has_macros() && profile.has_polars(),
            "the polars-only route must be built with the polars feature alone, got {profile}"
        );
    }

    #[scenario(
        path = "tests/features/build_profiles.feature",
        name = "A Polars-only build reports the Polars backend and no macro feature",
        tags = "@polars-only"
    )]
    fn polars_only_reports_no_macros(observed: Observed) {
        assert!(
            observed.profile.is_some(),
            "every `Then` step depends on the `When` step recording a profile"
        );
    }
}

mod rendered {
    //! The rendered profile line is a stable contract in every profile.
    //!
    //! The four `cfg`s partition the feature space, so exactly one test is
    //! compiled per build and each snapshots the line its own build produces.
    //! They sit in one module rather than one per route so the shapes stay
    //! visibly parallel: a route that lost its assertion is then a missing arm
    //! here rather than an absent module nobody notices.

    use combobulate::BuildProfile;
    use insta::assert_snapshot;

    /// The native-only build's own report.
    #[cfg(all(not(feature = "macros"), not(feature = "polars")))]
    #[test]
    fn native_only_line_is_stable() {
        assert_snapshot!("native_only", BuildProfile::current().to_string());
    }

    /// The macros-only build's own report.
    #[cfg(all(feature = "macros", not(feature = "polars")))]
    #[test]
    fn macros_only_line_is_stable() {
        assert_snapshot!("macros_only", BuildProfile::current().to_string());
    }

    /// The default build's own report.
    #[cfg(all(feature = "macros", feature = "polars"))]
    #[test]
    fn polars_enabled_line_is_stable() {
        assert_snapshot!("polars_enabled", BuildProfile::current().to_string());
    }

    /// The polars-only build's own report.
    #[cfg(all(not(feature = "macros"), feature = "polars"))]
    #[test]
    fn polars_only_line_is_stable() {
        assert_snapshot!("polars_only", BuildProfile::current().to_string());
    }
}
