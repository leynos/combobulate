//! Mutations proving job environment, cache policy, and the Act route stay pinned.
//!
//! These clauses differ from the step and action mutations: nothing here names
//! a step. A job can keep every ordered step and action and still change what
//! it runs by editing its environment, the one place a cache write policy and
//! a Make profile are selected. They are grouped separately so the parent
//! corpus stays within the module length limit without weakening any case.

use super::super::{ACT_VALIDATION_WORKFLOW, CI_WORKFLOW, contracts_hold};

#[test]
fn workflow_environment_mutations_break_the_contract() {
    for (reason, changed) in [
        (
            "lost coverage LLVM",
            CI_WORKFLOW.replace(
                "CARGO_PROFILE_DEV_CODEGEN_BACKEND: llvm",
                "CARGO_PROFILE_DEV_CODEGEN_BACKEND: cranelift",
            ),
        ),
        (
            "disabled PR updates",
            CI_WORKFLOW.replace("[opened, synchronize, reopened]", "[closed]"),
        ),
        (
            "different job cwd",
            CI_WORKFLOW.replace(
                "  build-test:\n",
                "  build-test:\n    defaults:\n      run:\n        working-directory: /tmp\n",
            ),
        ),
        (
            "different lint cwd",
            CI_WORKFLOW.replace(
                "- name: Lint\n",
                "- name: Lint\n        working-directory: /tmp\n",
            ),
        ),
        (
            "different lint shell",
            CI_WORKFLOW.replace("- name: Lint\n", "- name: Lint\n        shell: sh\n"),
        ),
    ] {
        assert_ne!(
            changed, CI_WORKFLOW,
            "mutation must change source: {reason}"
        );
        assert!(
            !contracts_hold(&changed, ACT_VALIDATION_WORKFLOW),
            "contract must detect {reason}"
        );
    }
    cache_mutations_break_the_contract();
    act_route_mutations_break_the_contract();
}

/// DL-03's cache clause is checked as three separate halves.
///
/// The clause is only met when compilation reaches sccache, and the declaration
/// that achieves it has parts that fail silently. The action installs the
/// binary but sets no wrapper, and Cargo ignores a wrapper it cannot run. The
/// storage backend is opt-in, so an unset backend compiles through to disk.
/// And saves are permitted only on `main`, which sccache expresses as a read
/// mode that defaults to `READ_WRITE`. Each failure is invisible in a green job,
/// so each gets its own mutation.
///
/// The save test keys on the ref rather than the event because both workflows
/// also declare `workflow_dispatch`, which may run from any branch. An event
/// test would read a branch dispatch as "not a pull request" and let it write,
/// so that regression has its own case.
fn cache_mutations_break_the_contract() {
    for (reason, changed) in [
        (
            "lost compiler wrapper",
            CI_WORKFLOW.replace("RUSTC_WRAPPER: sccache", "RUSTC_WRAPPER: ''"),
        ),
        (
            "lost cache backend",
            CI_WORKFLOW.replace(
                "SCCACHE_GHA_ENABLED: \"true\"",
                "SCCACHE_GHA_ENABLED: \"false\"",
            ),
        ),
        (
            "pull requests save to the cache",
            CI_WORKFLOW.replace(
                "'refs/heads/main' && 'READ_WRITE' || 'READ_ONLY'",
                "true && 'READ_WRITE'",
            ),
        ),
        (
            "cache write mode dropped",
            CI_WORKFLOW.replace(
                "      SCCACHE_GHA_RW_MODE: ${{ github.ref == 'refs/heads/main' && 'READ_WRITE' \
                 || 'READ_ONLY' }}\n",
                "",
            ),
        ),
        (
            // `workflow_dispatch` is declared beside `pull_request`, so an
            // event test that only guards pull requests would let a branch
            // dispatch write.
            "a dispatch may save from a branch",
            CI_WORKFLOW.replace(
                "github.ref == 'refs/heads/main'",
                "github.event_name == 'push'",
            ),
        ),
        (
            "lost wiring evidence",
            CI_WORKFLOW.replace("          sccache --show-stats", "          echo wired"),
        ),
    ] {
        assert_ne!(
            changed, CI_WORKFLOW,
            "mutation must change source: {reason}"
        );
        assert!(
            !contracts_hold(&changed, ACT_VALIDATION_WORKFLOW),
            "contract must detect {reason}"
        );
    }
}

/// Act's manual route is contracted separately from the hosted job environment.
///
/// The manual workflow may not acquire a pull-request trigger, which would make
/// it repeat the full hosted validation, and its action revision may not drift
/// off the pin the hosted route records. Neither is a `build-test` environment
/// concern, so the cases live here rather than growing the loop above.
fn act_route_mutations_break_the_contract() {
    let enabled_pr_act = ACT_VALIDATION_WORKFLOW.replace(
        "  workflow_dispatch:",
        "  pull_request:\n  workflow_dispatch:",
    );
    assert_ne!(
        enabled_pr_act, ACT_VALIDATION_WORKFLOW,
        "PR Act mutation must change source"
    );
    assert!(
        !contracts_hold(CI_WORKFLOW, &enabled_pr_act),
        "Act must not repeat full validation on pull requests"
    );
    let wrong_manual_pin =
        ACT_VALIDATION_WORKFLOW.replace("47b337e4f230b591891656534d4ffad868131740", "main");
    assert_ne!(
        wrong_manual_pin, ACT_VALIDATION_WORKFLOW,
        "manual pin mutation must change source"
    );
    assert!(
        !contracts_hold(CI_WORKFLOW, &wrong_manual_pin),
        "manual Act's action revision must stay pinned"
    );
}
