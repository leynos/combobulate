//! Regression tests for explicitly recorded unset environment expectations.

use std::collections::BTreeMap;

use rstest::{fixture, rstest};

use super::{
    ENVIRONMENT_POLICY,
    EnvironmentBoundary,
    EnvironmentValue,
    Invocation,
    assert_boundary_environment,
    assert_unset_environment,
    boundary_expectations,
};

/// Two observations ensure traversal reaches expectations after the first one.
const EXPECTATIONS: &[(&str, &str)] = &[("FIRST", "first reason"), ("LATER", "later reason")];

/// An executor record with both selected variables explicitly absent.
#[fixture]
fn invocation() -> Invocation {
    Invocation {
        executable: "controlled-executor".to_owned(),
        working_directory: "/fixture".to_owned(),
        environment: EXPECTATIONS
            .iter()
            .map(|(name, _)| ((*name).to_owned(), EnvironmentValue::Unset))
            .collect(),
        secrets: BTreeMap::new(),
        stage: "environment-check".to_owned(),
        cache_state: String::new(),
        arguments: Vec::new(),
        result: None,
    }
}

/// Explicit unset records satisfy every selected expectation.
#[rstest]
fn explicitly_unset_observations_pass(invocation: Invocation) {
    assert_unset_environment(&invocation, EXPECTATIONS);
}

/// Empty, populated, and missing observations fail at either record position.
#[rstest]
#[should_panic(expected = "first reason; executable controlled-executor, stage environment-check")]
#[case("FIRST", Some(EnvironmentValue::Empty))]
#[should_panic(expected = "first reason; executable controlled-executor, stage environment-check")]
#[case("FIRST", Some(EnvironmentValue::Value("caller".to_owned())))]
#[should_panic(expected = "first reason; executable controlled-executor, stage environment-check")]
#[case("FIRST", None)]
#[should_panic(expected = "later reason; executable controlled-executor, stage environment-check")]
#[case("LATER", Some(EnvironmentValue::Empty))]
#[should_panic(expected = "later reason; executable controlled-executor, stage environment-check")]
#[case("LATER", Some(EnvironmentValue::Value("caller".to_owned())))]
#[should_panic(expected = "later reason; executable controlled-executor, stage environment-check")]
#[case("LATER", None)]
fn contaminated_observation_fails(
    mut invocation: Invocation,
    #[case] variable: &str,
    #[case] observation: Option<EnvironmentValue>,
) {
    if let Some(value) = observation {
        invocation.environment.insert(variable.to_owned(), value);
    } else {
        invocation.environment.remove(variable);
    }
    assert_unset_environment(&invocation, EXPECTATIONS);
}

/// Policy projections preserve the distinct driver and configuration boundaries.
#[rstest]
#[case::driver(EnvironmentBoundary::Driver, vec![
    "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_PROFILE_DEV_CODEGEN_BACKEND",
    "CARGO_BUILD_TARGET", "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER", "CFLAGS", "LDFLAGS",
])]
#[case::config(EnvironmentBoundary::Config, vec![
    "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_PROFILE_DEV_CODEGEN_BACKEND",
    "CARGO_BUILD_TARGET", "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER",
])]
fn boundary_policy_retains_variable_ownership(
    #[case] boundary: EnvironmentBoundary,
    #[case] expected: Vec<&str>,
) {
    let actual = boundary_expectations(boundary)
        .into_iter()
        .map(|(variable, _)| variable)
        .collect::<Vec<_>>();
    assert_eq!(
        actual, expected,
        "the boundary must retain its complete override ownership"
    );
}

/// An executor fixture with every caller override explicitly absent.
#[fixture]
fn boundary_invocation(mut invocation: Invocation) -> Invocation {
    invocation.environment = ENVIRONMENT_POLICY
        .iter()
        .map(|(variable, ..)| ((*variable).to_owned(), EnvironmentValue::Unset))
        .collect();
    invocation
}

/// Configuration queries leave C flags outside their narrower assertion scope.
#[rstest]
fn configuration_policy_allows_unowned_c_flags(mut boundary_invocation: Invocation) {
    for variable in ["CFLAGS", "LDFLAGS"] {
        boundary_invocation
            .environment
            .insert(variable.to_owned(), EnvironmentValue::Empty);
    }
    assert_boundary_environment(&boundary_invocation, EnvironmentBoundary::Config);
}

/// Both projections traverse their last variable and keep boundary diagnostics.
#[rstest]
#[should_panic(expected = "Whitaker must not inherit caller build-selection overrides")]
#[case::driver(EnvironmentBoundary::Driver, "LDFLAGS")]
#[should_panic(expected = "Cargo configuration probes must not inherit caller route overrides")]
#[case::config(
    EnvironmentBoundary::Config,
    "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER"
)]
fn contaminated_boundary_tail_fails(
    mut boundary_invocation: Invocation,
    #[case] boundary: EnvironmentBoundary,
    #[case] variable: &str,
) {
    boundary_invocation
        .environment
        .insert(variable.to_owned(), EnvironmentValue::Empty);
    assert_boundary_environment(&boundary_invocation, boundary);
}
