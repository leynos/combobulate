//! Contract for the kernel proof route in the formal-verification workflow.
//!
//! The kernel proof earns its place by running: a job that never invokes
//! `make verus-kernel`, or one that invokes it before the pinned installation
//! it depends on, would leave the shipped `add_i64_into` and its seeded
//! mutants unexamined while the workflow still reported success. These cases
//! read the committed workflow and require that order, the failure-reporting
//! shell option, and the always-uploaded log, so a later edit cannot quietly
//! turn the proof into a step nobody reads.

use serde_yaml::Value;

const FORMAL: &str = include_str!("../.github/workflows/formal.yml");

/// Shared action-path and immutable-reference checks.
#[path = "support/action_ref.rs"]
mod action_ref;

/// The pinned action that installs the verifier from `tools/verus/VERSION`.
const INSTALL_PROVER_PATH: &str = "leynos/shared-actions/.github/actions/install-prover-tools";

/// The step that runs the shipped proof and the seeded mutants.
const KERNEL_STEP: &str = "Verify the kernel proof and reject its mutants";

/// The step that proves the pinned installation still works.
const WIRING_STEP: &str = "Run the Verus proofs and wiring candidates";

/// The step that installs Verus and its solver.
const INSTALL_STEP: &str = "Install Verus and Z3";

/// Walks a YAML document by key, reporting a missing level as `None`.
fn at<'a>(value: &'a Value, keys: &[&str]) -> Option<&'a Value> {
    keys.iter().try_fold(value, |parent, key| parent.get(*key))
}

/// Returns the string at `keys`, if the document has one there.
fn string<'a>(value: &'a Value, keys: &[&str]) -> Option<&'a str> {
    at(value, keys).and_then(Value::as_str)
}

/// Returns the Verus job's steps.
fn verus_steps(workflow: &Value) -> Result<&[Value], String> {
    at(workflow, &["jobs", "verus", "steps"])
        .and_then(Value::as_sequence)
        .map(Vec::as_slice)
        .ok_or_else(|| "the formal workflow must declare the Verus job's steps".to_owned())
}

/// Returns the index of the step called `name`.
fn step_index(steps: &[Value], name: &str) -> Result<usize, String> {
    steps
        .iter()
        .position(|step| string(step, &["name"]) == Some(name))
        .ok_or_else(|| format!("the Verus job must contain the step {name:?}"))
}

/// Returns the shell body of the step called `name`.
fn step_script<'a>(steps: &'a [Value], name: &str) -> Result<&'a str, String> {
    let step = steps
        .get(step_index(steps, name)?)
        .ok_or_else(|| format!("the step {name:?} must exist"))?;
    string(step, &["run"]).ok_or_else(|| format!("the step {name:?} must run a script"))
}

/// Returns the lines of a shell script that run, ignoring comments.
///
/// The kernel step explains in a comment why `pipefail` is set, so a bare
/// substring search would reject the explanation rather than the command.
/// Only executed lines can run a proof.
fn executed_lines(script: &str) -> impl Iterator<Item = &str> {
    script
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
}

/// Requires the kernel proof to run after the installation it depends upon.
#[test]
fn the_kernel_proof_runs_after_the_pinned_installation() -> Result<(), String> {
    let workflow: Value =
        serde_yaml::from_str(FORMAL).map_err(|error| format!("formal.yml must parse: {error}"))?;
    let steps = verus_steps(&workflow)?;
    let install = step_index(steps, INSTALL_STEP)?;
    let wiring = step_index(steps, WIRING_STEP)?;
    let kernel = step_index(steps, KERNEL_STEP)?;
    if !(install < wiring && wiring < kernel) {
        return Err(format!(
            "the kernel proof must run after the install and wiring steps, but their indices are \
             install={install}, wiring={wiring}, kernel={kernel}"
        ));
    }
    Ok(())
}

/// Requires the installation step to be the pinned shared action for Verus.
#[test]
fn the_installation_uses_the_pinned_shared_action() -> Result<(), String> {
    let workflow: Value =
        serde_yaml::from_str(FORMAL).map_err(|error| format!("formal.yml must parse: {error}"))?;
    let steps = verus_steps(&workflow)?;
    let install = steps
        .get(step_index(steps, INSTALL_STEP)?)
        .ok_or("the installation step must exist")?;
    let uses = string(install, &["uses"]).ok_or("the installation step must call an action")?;
    if !action_ref::matches_pinned_action(uses, INSTALL_PROVER_PATH) {
        return Err(format!(
            "the installation must call {INSTALL_PROVER_PATH} at an immutable revision, got \
             {uses:?}"
        ));
    }
    if string(install, &["with", "tools"]) != Some("verus") {
        return Err("the installation must provision Verus".to_owned());
    }
    Ok(())
}

/// Requires the kernel proof to report a failure rather than a `tee` status.
#[test]
fn the_kernel_proof_fails_the_step_on_a_failed_proof() -> Result<(), String> {
    let workflow: Value =
        serde_yaml::from_str(FORMAL).map_err(|error| format!("formal.yml must parse: {error}"))?;
    let steps = verus_steps(&workflow)?;
    let script = step_script(steps, KERNEL_STEP)?;
    let lines: Vec<&str> = executed_lines(script).collect();
    if !lines.contains(&"set -o pipefail") {
        return Err(
            "the kernel step must set pipefail, or a failed proof leaves a green step".to_owned(),
        );
    }
    if !lines
        .iter()
        .any(|line| line.starts_with("make verus-kernel"))
    {
        return Err("the kernel step must run make verus-kernel".to_owned());
    }
    let proof_line = lines
        .iter()
        .find(|line| line.starts_with("make verus-kernel"))
        .ok_or("the kernel step must run make verus-kernel")?;
    if !proof_line.contains("| tee ") {
        return Err("the kernel step must keep the proof log it captures".to_owned());
    }
    Ok(())
}

/// Requires the kernel log to be uploaded even when the proof fails.
#[test]
fn the_kernel_log_is_uploaded_even_on_failure() -> Result<(), String> {
    let workflow: Value =
        serde_yaml::from_str(FORMAL).map_err(|error| format!("formal.yml must parse: {error}"))?;
    let steps = verus_steps(&workflow)?;
    let kernel = step_index(steps, KERNEL_STEP)?;
    let upload = steps
        .iter()
        .skip(kernel)
        .find(|step| string(step, &["with", "name"]) == Some("verus-kernel-log"))
        .ok_or("the Verus job must upload the kernel proof log")?;
    if string(upload, &["if"]) != Some("always()") {
        return Err(
            "the log upload must run always(), or a failed proof leaves no record".to_owned(),
        );
    }
    let path = string(upload, &["with", "path"]).ok_or("the upload must name a path")?;
    if !path.contains("verus-kernel.log") {
        return Err(format!("the upload must name the kernel log, got {path:?}"));
    }
    Ok(())
}
