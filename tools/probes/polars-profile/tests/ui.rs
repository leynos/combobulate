//! Measure trybuild with the ordinary suite's diagnostic oracle at the same relative path.

#[test]
fn checked_cardinality_result_must_be_used() {
    // Out-of-package cases get absolute diagnostic locations, so keep a synchronized local copy.
    assert_eq!(
        include_str!("ui/cardinality_result_must_be_used.rs"),
        include_str!("../../../../tests/ui/cardinality_result_must_be_used.rs"),
        "the measurement case must match the ordinary UI input"
    );
    assert_eq!(
        include_str!("ui/cardinality_result_must_be_used.stderr"),
        include_str!("../../../../tests/ui/cardinality_result_must_be_used.stderr"),
        "the measurement must preserve the existing diagnostic oracle"
    );
    trybuild::TestCases::new().compile_fail("tests/ui/cardinality_result_must_be_used.rs");
}
