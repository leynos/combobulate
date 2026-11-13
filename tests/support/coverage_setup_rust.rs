//! Three-way setup-rust agreement across the hosted, coverage, and Act routes.
//!
//! Dependabot owns the shared revision, so the contract checks the action path
//! and commit shape, then requires all three routes to select the same value.
//! The manual route keeps `rustflags: ""`, which preserves Cargo's development
//! defaults. Keeping this contract in its own module leaves the workflow
//! contract file within the repository's length limit.

use serde_yaml::Value;

use super::{action_ref, parse_workflow, path, string};

/// One job's Rust setup action and its optional `rustflags` input.
#[derive(Clone, Copy)]
struct SetupRust<'a> {
    /// The complete `uses:` value.
    uses: &'a str,
    /// The textual input, or `None` when absent, null, or not a string.
    rustflags: Option<&'a str>,
}

/// Extracts exactly one named `Setup Rust` step from one job.
fn setup_rust<'a>(document: &'a Value, file: &str, job: &str) -> Result<SetupRust<'a>, String> {
    let steps = path(document, &["jobs", job, "steps"])
        .and_then(Value::as_sequence)
        .ok_or_else(|| format!("{file} job {job:?} must declare steps"))?;
    let setups = steps
        .iter()
        .filter(|step| string(step, &["name"]) == Some("Setup Rust"))
        .collect::<Vec<_>>();
    let [setup] = setups.as_slice() else {
        return Err(format!(
            "{file} job {job:?} must declare exactly one Setup Rust step, found {}",
            setups.len()
        ));
    };
    let uses = string(setup, &["uses"])
        .ok_or_else(|| format!("{file} job {job:?} Setup Rust step must name an action"))?;
    Ok(SetupRust {
        uses,
        rustflags: string(setup, &["with", "rustflags"]),
    })
}

/// Requires the hosted, coverage, and manual routes to select one pinned setup.
///
/// The pin value is intentionally not restated, so a Dependabot bump passes as
/// long as every route moves together. The manual `rustflags` input stays
/// asserted because an empty value is what preserves Cargo's defaults.
fn problem(ci: &Value, main: &Value, act: &Value) -> Result<(), String> {
    let hosted = setup_rust(ci, "ci.yml", "build-test")?;
    let coverage = setup_rust(main, "coverage-main.yml", "coverage-upload")?;
    let manual = setup_rust(act, "act-validation.yml", "act-validation")?;
    for (file, job, setup) in [
        ("ci.yml", "build-test", hosted),
        ("coverage-main.yml", "coverage-upload", coverage),
        ("act-validation.yml", "act-validation", manual),
    ] {
        if !action_ref::matches_pinned_action(setup.uses, action_ref::SETUP_RUST_PATH) {
            return Err(format!(
                "{file} job {job:?} must pin {}, found {:?}",
                action_ref::SETUP_RUST_PATH,
                setup.uses
            ));
        }
    }
    if hosted.uses != manual.uses || coverage.uses != manual.uses {
        return Err(format!(
            "setup-rust references must agree: ci.yml/build-test {:?}, \
             coverage-main.yml/coverage-upload {:?}, act-validation.yml/act-validation {:?}",
            hosted.uses, coverage.uses, manual.uses
        ));
    }
    if manual.rustflags != Some("") {
        return Err(format!(
            "act-validation.yml/act-validation Setup Rust must leave Cargo's defaults active; \
             rustflags is {:?}",
            manual.rustflags
        ));
    }
    Ok(())
}

/// Repoints setup-rust in one workflow source, which must contain it.
pub(crate) fn repoint(source: &str, reference: &str) -> String {
    let Some(changed) = action_ref::repoint_action(source, action_ref::SETUP_RUST_PATH, reference)
    else {
        panic!("the workflow must contain the setup-rust action")
    };
    changed
}

/// Evaluates the three-way setup contract on workflow sources.
pub(crate) fn holds(ci_source: &str, main_source: &str, act_source: &str) -> Result<(), String> {
    let ci = parse_workflow(ci_source).map_err(|error| format!("ci.yml: {error}"))?;
    let main =
        parse_workflow(main_source).map_err(|error| format!("coverage-main.yml: {error}"))?;
    let act = parse_workflow(act_source).map_err(|error| format!("act-validation.yml: {error}"))?;
    problem(&ci, &main, &act)
}
