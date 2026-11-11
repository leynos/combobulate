//! Contract for the weekly verifier route's version capture.
//!
//! The route exists to notice when a pinned verifier installation rots (DL-23).
//! That claim rests on the values the capture step records: a version file
//! holding an error message, or a probe whose failure is masked, would leave a
//! green job and an artifact that cannot be trusted. These cases read the
//! committed workflow and require the capture to use the repository's own pin.

use std::error::Error;

use cap_std::{ambient_authority, fs_utf8::Dir};
use serde_yaml::Value;

/// Reports fixture and contract failures without panicking.
type TestResult<T = ()> = Result<T, Box<dyn Error>>;

/// Return a failed expectation so each case keeps its `Result` contract.
fn check(condition: bool, expectation: impl std::fmt::Display) -> TestResult {
    if condition {
        Ok(())
    } else {
        Err(expectation.to_string().into())
    }
}

/// Read one committed repository file through an explicit directory capability.
fn read(path: &str) -> TestResult<String> {
    Ok(
        Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())?
            .read_to_string(path)?,
    )
}

/// Walk a YAML document by key, reporting a missing level as `None`.
fn at<'a>(value: &'a Value, keys: &[&str]) -> Option<&'a Value> {
    keys.iter().try_fold(value, |parent, key| parent.get(*key))
}

/// Return the shell body of the workflow step with the given name.
fn step_script<'a>(workflow: &'a Value, name: &str) -> TestResult<&'a str> {
    let steps = at(workflow, &["jobs", "verifier-route", "steps"])
        .and_then(Value::as_sequence)
        .ok_or("the verifier route must declare its steps")?;
    let step = steps
        .iter()
        .find(|step| at(step, &["name"]).and_then(Value::as_str) == Some(name))
        .ok_or_else(|| format!("the workflow must contain the step {name:?}"))?;
    at(step, &["run"])
        .and_then(Value::as_str)
        .ok_or_else(|| format!("the step {name:?} must run a script").into())
}

/// Return the lines of a shell script that run, ignoring comments.
///
/// The capture step explains in a comment which invocation used to fail and
/// why, so a bare substring search over the whole body would reject the
/// explanation rather than the command. Only executed lines can run a helper.
fn executed_lines(script: &str) -> impl Iterator<Item = &str> {
    script
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
}

/// Require the capture to resolve `prover-tools` from the committed pin.
#[test]
fn version_capture_uses_the_pinned_helper_source() -> TestResult {
    let workflow: Value = serde_yaml::from_str(&read(".github/workflows/formal.yml")?)?;
    let script = step_script(&workflow, "Record the installed verifier versions")?;

    // `uv run prover-tools` resolves a command from the project environment,
    // which this repository does not have, so it cannot reach the pinned
    // helper. `|| true` would then mask the failure and leave an error message
    // under a file name that claims to record a version.
    check(
        !executed_lines(script).any(|line| line.contains("uv run prover-tools")),
        "the capture step must not resolve prover-tools from the project environment",
    )?;
    check(
        !executed_lines(script).any(|line| line.contains("|| true")),
        "a failed helper probe must fail the capture step rather than be masked",
    )?;
    check(
        executed_lines(script)
            .filter(|line| {
                line.contains("uv tool run --from \"$prover_tools_source\" prover-tools")
            })
            .count()
            == 2,
        format_args!("both helper probes must use the pinned source: {script}"),
    )?;

    // The source is read from the same pin the Makefile reads, so a moved pin
    // moves both routes. Restating either the repository URL or the commit here
    // would create the second site the pin sweep exists to catch.
    for extraction in [
        "awk '/^repository:/ { print $2 }' tools/rust-prover-tools/REF",
        "awk '/^ref:/ { print $2 }' tools/rust-prover-tools/REF",
    ] {
        check(
            script.contains(extraction),
            format_args!("the capture step must read its pin: missing {extraction}"),
        )?;
    }
    Ok(())
}

/// Require the capture to keep the facts that identify the measuring host.
#[test]
fn version_capture_retains_the_host_facts() -> TestResult {
    let workflow: Value = serde_yaml::from_str(&read(".github/workflows/formal.yml")?)?;
    let script = step_script(&workflow, "Record the installed verifier versions")?;
    for retained in [
        "> formal-results/nproc",
        "> formal-results/memory",
        "> formal-results/image",
        "> formal-results/kani-version",
        "> formal-results/verus-help",
        "--repo-root . --kani-command kani",
    ] {
        check(
            script.contains(retained),
            format_args!("the capture step must retain {retained}"),
        )?;
    }
    Ok(())
}
