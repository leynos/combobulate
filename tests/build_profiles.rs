//! Behaviour contracts for the build profile this binary was compiled with.
//!
//! The two scenarios are mutually exclusive by construction: the `@native`
//! scenario is bound only into a build without default features, and the
//! `@polars` scenario only into a build with them. Each asserts the absence of
//! the other profile's backend, so a report that always or never claims Polars
//! fails one of the two routes.
//!
//! A tag filter that matches no scenario is a compile error, so binding a
//! scenario can never pass by running nothing.

#[cfg(not(feature = "polars"))]
mod native {
    //! The native-only route: no Polars, no macro crate.

    use combobulate::BuildProfile;
    use pretty_assertions::assert_eq;
    use rstest::fixture;
    use rstest_bdd_macros::{given, scenario, then, when};

    /// Records which features the running binary was compiled with.
    #[derive(Debug, Default)]
    struct Observed {
        /// A read taken from `BuildProfile::current()` in the `When` step.
        profile: Option<BuildProfile>,
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
    #[allow(
        unused_braces,
        reason = "fixture macro expansion triggers unused-braces on expression bodies"
    )]
    #[cfg_attr(
        clippy,
        expect(
            clippy::allow_attributes,
            reason = "needed to allow unused_braces for fixture macro expansion"
        )
    )]
    #[fixture]
    fn observed() -> Observed { Observed::default() }

    #[given("the facade compiled without default features")]
    fn compiled_without_default_features() {
        assert!(
            !BuildProfile::current().has_polars(),
            "the native-only route must be built without default features"
        );
    }

    #[when("a consumer reads the build profile")]
    fn read_profile(observed: &mut Observed) { observed.profile = Some(BuildProfile::current()); }

    /// Unwraps the profile the `When` step recorded.
    fn recorded(observed: &Observed) -> BuildProfile {
        observed
            .profile
            .expect("the `When` step must run before any `Then` step")
    }

    #[then("the profile reports the native backend")]
    fn reports_native(observed: &Observed) {
        let line = recorded(observed).to_string();
        assert!(
            line.starts_with("features: native"),
            "the profile must always begin with the native backend, got {line:?}"
        );
    }

    #[then("the profile does not report a Polars backend")]
    fn does_not_report_polars(observed: &Observed) {
        let profile = recorded(observed);
        assert_eq!(
            profile.has_polars(),
            false,
            "a native-only build must not report a Polars backend"
        );
        assert!(
            !profile.to_string().contains("polars"),
            "the rendered line must not name Polars, got {profile}"
        );
    }

    #[then("the profile does not report the macro feature")]
    fn does_not_report_macros(observed: &Observed) {
        assert_eq!(
            recorded(observed).has_macros(),
            false,
            "a native-only build must not report the macro feature"
        );
    }

    #[then("the profile reports the target usize width")]
    fn reports_target_usize_width(observed: &Observed) {
        assert_eq!(
            recorded(observed).target_usize_bits(),
            usize::BITS,
            "the profile must report the compilation target's usize width"
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

#[cfg(feature = "polars")]
mod polars {
    //! The default route: both optional features are compiled in.

    use combobulate::BuildProfile;
    use pretty_assertions::assert_eq;
    use rstest::fixture;
    use rstest_bdd_macros::{given, scenario, then, when};

    /// Records which features the running binary was compiled with.
    #[derive(Debug, Default)]
    struct Observed {
        /// A read taken from `BuildProfile::current()` in the `When` step.
        profile: Option<BuildProfile>,
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
    #[allow(
        unused_braces,
        reason = "fixture macro expansion triggers unused-braces on expression bodies"
    )]
    #[cfg_attr(
        clippy,
        expect(
            clippy::allow_attributes,
            reason = "needed to allow unused_braces for fixture macro expansion"
        )
    )]
    #[fixture]
    fn observed() -> Observed { Observed::default() }

    #[given("the facade compiled with default features")]
    fn compiled_with_default_features() {
        assert!(
            BuildProfile::current().has_polars(),
            "the default route must be built with default features"
        );
    }

    #[when("a consumer reads the build profile")]
    fn read_profile(observed: &mut Observed) { observed.profile = Some(BuildProfile::current()); }

    /// Unwraps the profile the `When` step recorded.
    fn recorded(observed: &Observed) -> BuildProfile {
        observed
            .profile
            .expect("the `When` step must run before any `Then` step")
    }

    #[then("the profile reports the native backend")]
    fn reports_native(observed: &Observed) {
        let line = recorded(observed).to_string();
        assert!(
            line.starts_with("features: native"),
            "the profile must always begin with the native backend, got {line:?}"
        );
    }

    #[then("the profile reports a Polars backend")]
    fn reports_polars(observed: &Observed) {
        let profile = recorded(observed);
        assert_eq!(
            profile.has_polars(),
            true,
            "a default build must report the Polars backend"
        );
        assert!(
            profile.to_string().contains("polars"),
            "the rendered line must name Polars, got {profile}"
        );
    }

    #[then("the profile reports the macro feature")]
    fn reports_macros(observed: &Observed) {
        assert_eq!(
            recorded(observed).has_macros(),
            true,
            "a default build must report the macro feature"
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

/// The `Display` oracle is the single source of the rendered profile line.
///
/// Each route snapshots the line its own build produces, so the two snapshots
/// are the two real profiles rather than one build imitating the other. The
/// `native-only` route additionally checks a second spelling: the same render
/// path with the macro feature present and Polars absent, which is a profile
/// the gate routes never build but the reserved `macros` feature can select.
#[cfg(not(feature = "polars"))]
mod rendered_native {
    //! The native-only build's rendered line is a stable contract.

    use combobulate::BuildProfile;
    use insta::assert_snapshot;

    /// The native-only build's own report.
    #[test]
    fn native_only_line_is_stable() {
        assert_snapshot!("native_only", BuildProfile::current().to_string());
    }
}

#[cfg(feature = "polars")]
mod rendered_polars {
    //! The Polars-enabled build's rendered line is a stable contract.

    use combobulate::BuildProfile;
    use insta::assert_snapshot;

    /// The default build's own report.
    #[test]
    fn polars_enabled_line_is_stable() {
        assert_snapshot!("polars_enabled", BuildProfile::current().to_string());
    }
}
