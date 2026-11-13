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

/// One action path, name, and required inputs.
///
/// Every entry is path-only: its revision is checked for shape by
/// `action_ref::matches_pinned_action`, so a Dependabot bump does not need a
/// matching edit here.
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
    /// Ordered action paths, matched by `action_ref::matches_pinned_action`.
    pub(super) actions: &'static [&'static str],
    /// The complete job environment; `GATE_PROFILE` selects the profile.
    ///
    /// Every job also declares `RUSTC_WRAPPER: sccache` and
    /// `SCCACHE_GHA_ENABLED: "true"`, because DL-03's cache clause is about
    /// compilation that actually reaches sccache. The pinned `setup-rust`
    /// action installs the binary and exports `SCCACHE_PATH` but sets neither
    /// variable, and an absent wrapper is not itself an error — so a job
    /// without them compiled uncached while reporting nothing wrong. A wrapper
    /// Cargo cannot execute is different: it fails the build. They are
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
            action_ref::SETUP_RUST_PATH,
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
                "${{ github.ref == 'refs/heads/main' && 'READ_WRITE' || 'READ_ONLY' }}",
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
            action_ref::SETUP_RUST_PATH,
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
                "${{ github.ref == 'refs/heads/main' && 'READ_WRITE' || 'READ_ONLY' }}",
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
            Some("Test the single-feature isolation profiles"),
        ],
        actions: &["actions/checkout", action_ref::SETUP_RUST_PATH],
        env: &[
            ("CARGO_TERM_COLOR", "always"),
            ("BUILD_PROFILE", "debug"),
            ("GATE_PROFILE", "polars-enabled"),
            ("RUSTC_WRAPPER", "sccache"),
            ("SCCACHE_GHA_ENABLED", "true"),
            (
                "SCCACHE_GHA_RW_MODE",
                "${{ github.ref == 'refs/heads/main' && 'READ_WRITE' || 'READ_ONLY' }}",
            ),
        ],
    },
];

/// Every action any job names, with the inputs that action must receive.
///
/// Entries are path-only so a Dependabot bump needs no edit here. All three
/// jobs resolve their inputs from this one table, so an action shared by two
/// jobs cannot acquire two different contracts, and a job's own `actions` list
/// pins order only.
pub(crate) const ACTIONS: &[ActionContract] = &[
    (
        "actions/checkout",
        "checkout",
        &[("persist-credentials", "false")],
    ),
    (
        action_ref::SETUP_RUST_PATH,
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

/// Resolves a job's action contracts by path, preserving that job's order.
///
/// Every path a job names must appear in `ACTIONS`: that one table is the only
/// place an action's required inputs are stated, so a job cannot carry a
/// contract that disagrees with another job's. A path absent from `ACTIONS`
/// resolves to `None` and fails the caller, rather than falling back to a
/// second table that could drift from this one without any test noticing.
fn job_action_contracts(job: &JobContract) -> Option<Vec<&'static ActionContract>> {
    job.actions
        .iter()
        .map(|path| ACTIONS.iter().find(|contract| contract.0 == *path))
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

/// Matches one hosted action path, its pin shape, name, and consumed inputs.
fn matches_hosted_action(item: &Value, expected: &ActionContract) -> bool {
    let (path, name, inputs) = expected;
    text(item, &["uses"]).is_some_and(|uses| action_ref::matches_pinned_action(uses, path))
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
