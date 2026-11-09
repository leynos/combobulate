//! Required hosted jobs, their action revisions, and input matching.
//!
//! DL-03 shape B splits the gate profiles across three required jobs. Each job
//! is contracted independently, so a step or action cannot be moved from one
//! job to another without either job's own list disagreeing. The action tables
//! live beside the job list because a job's contract is only meaningful
//! together with the inputs its actions consume; the route clauses that read
//! them stay in the parent contract module.

use serde_yaml::Value;

use super::{action_ref, at, text};

/// Marks an input whose value is checked elsewhere rather than restated here.
pub(crate) const ANY_VALUE: &str = "<any>";

/// One action path (or capability-bound revision), name, and required inputs.
pub(crate) type ActionContract = (
    &'static str,
    &'static str,
    &'static [(&'static str, &'static str)],
);

/// One required hosted job: its ordered steps, actions, and environment.
///
/// DL-03 shape B splits the profiles across three required jobs. Each job is
/// contracted independently, so a step or action cannot be moved from one job
/// to another without either job's own list disagreeing.
pub(crate) struct JobContract {
    /// Workflow job key.
    pub(super) name: &'static str,
    /// Ordered step names; `None` for the unnamed checkout step.
    pub(super) steps: &'static [Option<&'static str>],
    /// Ordered action revisions, matched by [`matches_action_revision`].
    pub(super) actions: &'static [&'static str],
    /// The complete job environment; `GATE_PROFILE` selects the profile.
    ///
    /// Every job also declares `RUSTC_WRAPPER: sccache` and
    /// `SCCACHE_GHA_ENABLED: "true"`, because DL-03's cache clause is about
    /// compilation that actually reaches sccache. The pinned `setup-rust`
    /// action installs the binary and exports `SCCACHE_PATH` but sets neither
    /// variable, and Cargo silently ignores a wrapper it cannot run — so a job
    /// without them compiled uncached while reporting nothing wrong. They are
    /// job-level rather than per-step so the provisioning steps all inherit
    /// them, and `Report sccache wiring` resolves the wrapper on `PATH` to make
    /// the wiring observable rather than merely asserted.
    ///
    /// The third is a policy rather than a capability. DL-03 allows cache saves
    /// only on `main`, and sccache 0.16.0 and later express that with
    /// `SCCACHE_GHA_RW_MODE`, which otherwise defaults to `READ_WRITE`. So each
    /// pull-request job reads the cache and does not write it. The mode is part
    /// of the pinned environment because a job that dropped it would silently
    /// resume writing entries scoped to `refs/pull/N/merge`, which no later run
    /// of the branch reads once that ref advances.
    pub(super) env: &'static [(&'static str, &'static str)],
}

/// The three required pull-request jobs, in workflow order.
///
/// `GATE_PROFILE` is the only routing difference between the jobs: the Make
/// targets loop over `GATE_PROFILES`, so a job that omitted it would run both
/// profiles and double its own work.
pub(crate) const JOBS: &[JobContract] = &[
    JobContract {
        name: "build-test",
        steps: &[
            None,
            Some("Setup Rust"),
            Some("Log Rust compiler configuration"),
            Some("Install linker prerequisites"),
            Some("Report sccache wiring"),
            Some("Install the build standard"),
            Some("Install mdtablefix"),
            Some("Format"),
            Some("Markdown lint"),
            Some("Setup uv"),
            Some("Check spelling"),
            Some("Install test runner"),
            Some("Install cargo-audit"),
            Some("Setup Python for audit manifest extraction"),
            Some("Verify Whitaker capability"),
            Some("Install Whitaker"),
            Some("Audit dependencies"),
            Some("Lint"),
            Some("Log coverage linker configuration"),
            Some("Test and Measure Coverage"),
            Some("Test under Act"),
        ],
        actions: &[
            "actions/checkout",
            "leynos/shared-actions/.github/actions/setup-rust@\
             47b337e4f230b591891656534d4ffad868131740",
            "leynos/shared-actions/.github/actions/install-mdtablefix",
            "DavidAnson/markdownlint-cli2-action",
            "astral-sh/setup-uv",
            "actions/setup-python",
            "leynos/shared-actions/.github/actions/install-whitaker",
            "leynos/shared-actions/.github/actions/generate-coverage",
        ],
        env: &[
            ("CARGO_TERM_COLOR", "always"),
            ("BUILD_PROFILE", "debug"),
            ("GATE_PROFILE", "native-only"),
            ("RUSTC_WRAPPER", "sccache"),
            ("SCCACHE_GHA_ENABLED", "true"),
            (
                "SCCACHE_GHA_RW_MODE",
                "${{ github.event_name == 'push' && 'READ_WRITE' || 'READ_ONLY' }}",
            ),
        ],
    },
    JobContract {
        name: "polars-lint",
        steps: &[
            None,
            Some("Setup Rust"),
            Some("Log Rust compiler configuration"),
            Some("Install linker prerequisites"),
            Some("Report sccache wiring"),
            Some("Install the build standard"),
            Some("Setup uv"),
            Some("Verify Whitaker capability"),
            Some("Install Whitaker"),
            Some("Lint"),
        ],
        actions: &[
            "actions/checkout",
            "leynos/shared-actions/.github/actions/setup-rust@\
             47b337e4f230b591891656534d4ffad868131740",
            "astral-sh/setup-uv",
            "leynos/shared-actions/.github/actions/install-whitaker",
        ],
        env: &[
            ("CARGO_TERM_COLOR", "always"),
            ("BUILD_PROFILE", "debug"),
            ("GATE_PROFILE", "polars-enabled"),
            ("RUSTC_WRAPPER", "sccache"),
            ("SCCACHE_GHA_ENABLED", "true"),
            (
                "SCCACHE_GHA_RW_MODE",
                "${{ github.event_name == 'push' && 'READ_WRITE' || 'READ_ONLY' }}",
            ),
        ],
    },
    JobContract {
        name: "polars-test",
        steps: &[
            None,
            Some("Setup Rust"),
            Some("Log Rust compiler configuration"),
            Some("Install linker prerequisites"),
            Some("Report sccache wiring"),
            Some("Install the build standard"),
            Some("Install test runner"),
            Some("Test"),
        ],
        actions: &[
            "actions/checkout",
            "leynos/shared-actions/.github/actions/setup-rust@\
             47b337e4f230b591891656534d4ffad868131740",
        ],
        env: &[
            ("CARGO_TERM_COLOR", "always"),
            ("BUILD_PROFILE", "debug"),
            ("GATE_PROFILE", "polars-enabled"),
            ("RUSTC_WRAPPER", "sccache"),
            ("SCCACHE_GHA_ENABLED", "true"),
            (
                "SCCACHE_GHA_RW_MODE",
                "${{ github.event_name == 'push' && 'READ_WRITE' || 'READ_ONLY' }}",
            ),
        ],
    },
];

/// Expected paths and inputs, with the setup-rust capability-bound revision exception.
///
/// This is the `build-test` action list; the other two jobs share the prelude
/// actions but not their inputs, so each job's `actions` list pins order only.
pub(crate) const ACTIONS: &[ActionContract] = &[
    (
        "actions/checkout",
        "checkout",
        &[("persist-credentials", "false")],
    ),
    (
        "leynos/shared-actions/.github/actions/setup-rust@47b337e4f230b591891656534d4ffad868131740",
        "Setup Rust",
        &[("rustflags", ""), ("use-sccache", "true")],
    ),
    (
        "leynos/shared-actions/.github/actions/install-mdtablefix",
        "Install mdtablefix",
        &[("version", ANY_VALUE)],
    ),
    (
        "DavidAnson/markdownlint-cli2-action",
        "Markdown lint",
        &[("globs", "**/*.md")],
    ),
    ("astral-sh/setup-uv", "Setup uv", &[]),
    (
        "actions/setup-python",
        "Setup Python for audit manifest extraction",
        &[("python-version", "3.x")],
    ),
    (
        "leynos/shared-actions/.github/actions/install-whitaker",
        "Install Whitaker",
        &[("cranelift", "true")],
    ),
    (
        "leynos/shared-actions/.github/actions/generate-coverage",
        "Test and Measure Coverage",
        &[
            ("output-path", "lcov.info"),
            ("format", "lcov"),
            ("with-ratchet", "true"),
            ("publish-artefact", "false"),
            // DL-03/DL-18: measured coverage is the native-only profile, so
            // both the pull-request lane and the `main` baseline name it.
            ("with-default-features", "false"),
            ("features", ""),
        ],
    ),
];

/// Action contracts shared by every job that provisions rather than measures.
///
/// The `polars-*` jobs reuse the same checkout, Rust setup, and uv actions, so
/// resolving them from one table keeps a stray input from being accepted in a
/// job whose prelude is otherwise identical.
const PRELUDE_ACTIONS: &[ActionContract] = &[
    (
        "actions/checkout",
        "checkout",
        &[("persist-credentials", "false")],
    ),
    (
        "leynos/shared-actions/.github/actions/setup-rust@47b337e4f230b591891656534d4ffad868131740",
        "Setup Rust",
        &[("rustflags", ""), ("use-sccache", "true")],
    ),
    ("astral-sh/setup-uv", "Setup uv", &[]),
    (
        "leynos/shared-actions/.github/actions/install-whitaker",
        "Install Whitaker",
        &[("cranelift", "true")],
    ),
];

/// Resolves a job's action contracts by path, preserving that job's order.
fn job_action_contracts(job: &JobContract) -> Option<Vec<&'static ActionContract>> {
    job.actions
        .iter()
        .map(|path| {
            ACTIONS
                .iter()
                .chain(PRELUDE_ACTIONS)
                .find(|contract| contract.0 == *path)
        })
        .collect()
}

/// Names the job the real-Act smoke derives: the one with the full step set.
pub(crate) const fn smoke_job_name() -> &'static str { "build-test" }

/// The smoke job's ordered action contracts, which its fixtures rewrite.
pub(crate) const fn smoke_action_contracts() -> &'static [ActionContract] { ACTIONS }

/// Reads one job's step sequence without letting absent structure pass.
pub(crate) fn job_steps<'a>(ci: &'a Value, job: &str) -> Option<&'a [Value]> {
    at(ci, &["jobs", job, "steps"])?
        .as_sequence()
        .map(Vec::as_slice)
}

/// Converts only the YAML scalar forms accepted by known action inputs.
pub(crate) fn action_input(value: &Value, key: &str) -> Option<String> {
    match at(value, &["with", key])? {
        Value::String(text) => Some(text.clone()),
        Value::Bool(boolean) => Some(boolean.to_string()),
        Value::Number(number) => Some(number.to_string()),
        _ => None,
    }
}

/// Checks every required job's action set before a fixture could replace one.
pub(crate) fn valid_actions(ci: &Value) -> bool {
    JOBS.iter().all(|job| valid_job_actions(ci, job))
}

/// Checks one job's ordered action revisions, names, and consumed inputs.
fn valid_job_actions(ci: &Value, job: &JobContract) -> bool {
    let Some(contracts) = job_action_contracts(job) else {
        return false;
    };
    let Some(steps) = job_steps(ci, job.name) else {
        return false;
    };
    let actions = steps
        .iter()
        .filter(|item| text(item, &["uses"]).is_some())
        .collect::<Vec<_>>();
    actions.len() == contracts.len()
        && actions
            .iter()
            .zip(contracts)
            .all(|(item, expected)| matches_hosted_action(item, expected))
}

/// Matches one hosted action revision, its name exception, and consumed inputs.
fn matches_hosted_action(item: &Value, expected: &ActionContract) -> bool {
    let (revision, name, inputs) = expected;
    text(item, &["uses"]).is_some_and(|uses| matches_action_revision(uses, revision))
        && (*name == "checkout" || text(item, &["name"]) == Some(*name))
        && action_inputs_match(item, inputs)
}

/// Matches scalar input values and count, retaining absent non-mapping semantics.
pub(crate) fn action_inputs_match(item: &Value, expected: &[(&str, &str)]) -> bool {
    expected.iter().all(|(key, value)| {
        let actual = action_input(item, key);
        if *value == ANY_VALUE {
            actual.is_some_and(|text| !text.is_empty())
        } else {
            actual.as_deref() == Some(*value)
        }
    }) && at(item, &["with"])
        .and_then(Value::as_mapping)
        .map_or(0, serde_yaml::Mapping::len)
        == expected.len()
}

/// Preserves only the documented setup-rust capability pin as an exact revision.
pub(crate) fn matches_action_revision(uses: &str, expected: &str) -> bool {
    if expected.contains('@') {
        uses == expected
    } else {
        action_ref::matches_pinned_action(uses, expected)
    }
}
