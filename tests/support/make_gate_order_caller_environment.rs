//! Caller-environment assertions for the Make gate-order contracts.

use super::records::{EnvironmentValue, Invocation};

/// Stages that exercise the caller's routing values: rustdoc, then one Clippy
/// run per gate profile.
///
/// Under DL-18 the two Clippy runs are separate stages, so naming only
/// `"clippy"` would silently match nothing and leave this contract vacuous.
const ROUTE_STAGES: [&str; 3] = ["doc", "clippy-native-only", "clippy-polars-enabled"];

/// Checks coverage-only caller values reached Clippy before Whitaker isolation.
pub(super) fn assert_coverage_contamination(invocations: &[Invocation]) {
    for invocation in invocations
        .iter()
        .filter(|invocation| ROUTE_STAGES.contains(&invocation.stage.as_str()))
    {
        assert_env_value(
            invocation,
            "CARGO_PROFILE_DEV_CODEGEN_BACKEND",
            "llvm",
            "coverage test setup must contaminate the caller child process",
        );
        assert_env_value(
            invocation,
            "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER",
            "clang",
            "coverage test setup must retain its linker override before Whitaker",
        );
        assert_env_value(
            invocation,
            "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS",
            "-C link-arg=-fuse-ld=lld",
            "coverage setup must contaminate the child with target-specific lld flags",
        );
        assert_env_value(
            invocation,
            "CARGO_ENCODED_RUSTFLAGS",
            "-D\u{1f}warnings\u{1f}-C\u{1f}link-arg=-fuse-ld=lld",
            "coverage flags must reach the caller child process for the contract probe",
        );
    }
}

/// Confirms target-specific lld flags stop at the repository build boundary.
pub(super) fn assert_target_rustflags_isolated(invocations: &[Invocation]) {
    let checks = invocations
        .iter()
        .filter(|invocation| invocation.stage == "whitaker")
        .collect::<Vec<_>>();
    assert_eq!(
        checks.len(),
        2,
        "cold and warm Whitaker runs must both be recorded"
    );
    for invocation in checks {
        assert_eq!(
            invocation
                .environment
                .get("CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS"),
            Some(&EnvironmentValue::Unset),
            "Whitaker must not inherit target-specific lld flags after preflight"
        );
    }
}

/// Confirms an empty inherited flag value stays distinct from an unset route.
pub(super) fn assert_clean_caller(invocations: &[Invocation]) {
    for stage in ROUTE_STAGES {
        let matching = invocations
            .iter()
            .filter(|invocation| invocation.stage == stage)
            .collect::<Vec<_>>();
        assert_eq!(
            matching.len(),
            2,
            "the coverage and clean caller must each execute {stage} once"
        );
        for clean in matching.into_iter().skip(1) {
            assert_eq!(
                clean.environment.get("CARGO_ENCODED_RUSTFLAGS"),
                Some(&EnvironmentValue::Empty),
                "the clean caller's explicitly empty encoded flags must remain observable"
            );
            for variable in [
                "CARGO_PROFILE_DEV_CODEGEN_BACKEND",
                "CARGO_BUILD_TARGET",
                "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER",
            ] {
                assert_eq!(
                    clean.environment.get(variable),
                    Some(&EnvironmentValue::Unset),
                    "clean caller routing variable {variable} must remain unset"
                );
            }
        }
    }
}

/// Checks a recorded environment value with its stage in the failure message.
fn assert_env_value(invocation: &Invocation, name: &str, value: &str, reason: &str) {
    assert_eq!(
        invocation.environment.get(name),
        Some(&EnvironmentValue::Value(value.to_owned())),
        "{reason}; stage {}",
        invocation.stage
    );
}

/// Confirms records retain only secret presence, never the supplied values.
pub(super) fn assert_secret_values_redacted(gate_records: &[u8], whitaker_records: &[u8]) {
    let record_bytes = [gate_records, whitaker_records].concat();
    let records = String::from_utf8_lossy(&record_bytes);
    assert!(
        !records.contains("gate-probe-secret-must-not-be-logged"),
        "coverage tokens must never be written to probe records"
    );
    assert!(
        !records.contains("gate-probe-github-secret-must-not-be-logged"),
        "GitHub tokens must never be written to probe records"
    );
}
