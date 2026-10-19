//! Check compile-time guarantees of the standalone cardinality calibration probe.

#[test]
fn checked_cardinality_result_must_be_used() {
    trybuild::TestCases::new().compile_fail("tests/ui/cardinality_result_must_be_used.rs");
}
