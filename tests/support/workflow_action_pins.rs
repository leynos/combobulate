//! Repository-wide shape and consistency contract for workflow action pins.
//!
//! Dependabot owns GitHub Actions pins, so a contract that restates one commit
//! SHA fails on every legitimate bump. This module instead requires each
//! reference to be a full lowercase hexadecimal commit SHA and each action path
//! to resolve to one SHA across all workflows. A deliberate difference is a
//! named exception; an exception whose action no longer appears in the named
//! workflow is stale and fails.
//!
//! The checks are pure: workflow discovery and the declared exceptions live in
//! the suites that own them, so any workflow contract can reuse the rules.

use std::{collections::BTreeMap, error::Error};

use serde_yaml::Value;

use crate::action_ref;

/// Fallible workflow discovery and parsing result.
pub(super) type Read<T> = Result<T, Box<dyn Error>>;

/// One workflow location that names an action.
#[derive(Clone, Debug)]
pub(super) struct ActionUse {
    /// Workflow filename, such as `ci.yml`.
    pub(super) workflow: String,
    /// Job key that contains the reference.
    pub(super) job: String,
    /// Step name, `step N` for an unnamed step, or `job` at job level.
    pub(super) step: String,
    /// Complete `uses:` value.
    pub(super) action: String,
}

impl ActionUse {
    /// Formats the workflow, job, and step that name the action.
    fn location(&self) -> String { format!("{}:{}.{}", self.workflow, self.job, self.step) }
}

/// A deliberate pin difference between one workflow and the shared revision.
#[derive(Clone, Copy, Debug)]
pub(super) struct PinException {
    /// Workflow filename the exception applies to.
    pub(super) workflow: &'static str,
    /// Full action path before the `@`.
    pub(super) path: &'static str,
    /// Why the difference is deliberate.
    pub(super) reason: &'static str,
}

/// Parses one workflow, naming the file in every failure.
///
/// The first parse into a mapping rejects duplicate keys, which a later
/// typed parse would silently resolve by keeping one entry.
pub(super) fn parse_workflow(file: &str, source: &str) -> Read<Value> {
    let invalid = |error: serde_yaml::Error| format!("{file}: invalid workflow YAML: {error}");
    serde_yaml::from_str::<serde_yaml::Mapping>(source).map_err(invalid)?;
    serde_yaml::from_str(source).map_err(|error| invalid(error).into())
}

/// Reports every action-pin shape, consistency, and exception violation.
pub(super) fn workflow_violations(
    documents: &[(String, Value)],
    exceptions: &[PinException],
) -> Vec<String> {
    let uses = documents
        .iter()
        .flat_map(|(workflow, document)| action_uses(workflow, document))
        .collect::<Vec<_>>();
    let mut violations = unpinned_violations(&uses);
    violations.extend(stale_exception_violations(&uses, exceptions));
    violations.extend(divergent_pin_violations(&uses, exceptions));
    violations
}

/// Collects job-level and step-level action references from one workflow.
fn action_uses(workflow: &str, document: &Value) -> Vec<ActionUse> {
    let Some(jobs) = document.get("jobs").and_then(Value::as_mapping) else {
        return Vec::new();
    };
    let mut uses = Vec::new();
    for (job_key, job) in jobs {
        let Some(job_name) = job_key.as_str() else {
            continue;
        };
        if let Some(action) = job.get("uses").and_then(Value::as_str) {
            push_use(
                &mut uses,
                UseLocation::new(workflow, job_name, "job"),
                action,
            );
        }
        for (index, step) in job
            .get("steps")
            .and_then(Value::as_sequence)
            .into_iter()
            .flatten()
            .enumerate()
        {
            let Some(action) = step.get("uses").and_then(Value::as_str) else {
                continue;
            };
            let label = step
                .get("name")
                .and_then(Value::as_str)
                .map_or_else(|| format!("step {index}"), str::to_owned);
            push_use(
                &mut uses,
                UseLocation::new(workflow, job_name, &label),
                action,
            );
        }
    }
    uses
}

/// The workflow, job, and step around one reference.
#[derive(Clone, Copy)]
struct UseLocation<'a> {
    /// Workflow filename.
    workflow: &'a str,
    /// Job key.
    job: &'a str,
    /// Step name, or `job` for a job-level reference.
    step: &'a str,
}

impl<'a> UseLocation<'a> {
    /// Groups one reference's surroundings for [`push_use`].
    const fn new(workflow: &'a str, job: &'a str, step: &'a str) -> Self {
        Self {
            workflow,
            job,
            step,
        }
    }
}

/// Records one reference unless it is a local action owned by this repository.
fn push_use(uses: &mut Vec<ActionUse>, location: UseLocation<'_>, action: &str) {
    if action.starts_with("./") {
        return;
    }
    uses.push(ActionUse {
        workflow: location.workflow.to_owned(),
        job: location.job.to_owned(),
        step: location.step.to_owned(),
        action: action.to_owned(),
    });
}

/// Requires every non-local action reference to be a full commit SHA.
fn unpinned_violations(uses: &[ActionUse]) -> Vec<String> {
    uses.iter()
        .filter(|entry| !action_ref::is_sha_pinned(&entry.action))
        .map(|entry| {
            format!(
                "{} at {} is not pinned to a 40-hex commit SHA",
                entry.action,
                entry.location()
            )
        })
        .collect()
}

/// Rejects an exception whose action the named workflow no longer uses.
fn stale_exception_violations(uses: &[ActionUse], exceptions: &[PinException]) -> Vec<String> {
    exceptions
        .iter()
        .filter(|exception| {
            !uses.iter().any(|entry| {
                entry.workflow == exception.workflow
                    && action_ref::action_path(&entry.action) == exception.path
            })
        })
        .map(|exception| {
            format!(
                "stale pin exception: {} does not use {} ({})",
                exception.workflow, exception.path, exception.reason
            )
        })
        .collect()
}

/// Reports each action path that resolves to more than one revision.
fn divergent_pin_violations(uses: &[ActionUse], exceptions: &[PinException]) -> Vec<String> {
    let mut by_path: BTreeMap<&str, BTreeMap<&str, Vec<&ActionUse>>> = BTreeMap::new();
    for entry in uses.iter().filter(|entry| !is_excepted(entry, exceptions)) {
        by_path
            .entry(action_ref::action_path(&entry.action))
            .or_default()
            .entry(entry.action.as_str())
            .or_default()
            .push(entry);
    }
    by_path
        .into_iter()
        .filter(|(_, references)| references.len() > 1)
        .map(|(path, references)| {
            let details = references
                .iter()
                .map(|(action, places)| {
                    let locations = places
                        .iter()
                        .map(|entry| entry.location())
                        .collect::<Vec<_>>()
                        .join(", ");
                    format!("{action} at {locations}")
                })
                .collect::<Vec<_>>()
                .join("; ");
            format!("{path} resolves to more than one revision: {details}")
        })
        .collect()
}

/// Checks whether a reference is covered by a declared exception.
fn is_excepted(entry: &ActionUse, exceptions: &[PinException]) -> bool {
    exceptions.iter().any(|exception| {
        entry.workflow == exception.workflow
            && action_ref::action_path(&entry.action) == exception.path
    })
}
