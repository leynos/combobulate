//! Coordinated action bumps must satisfy every workflow contract.
//!
//! A bump fixture that leaves some call sites behind tests an inconsistency,
//! not an upgrade. These cases move every occurrence of each action, then
//! require both the workflow contracts and the repository-wide pin contract to
//! hold.

use std::collections::BTreeSet;

use serde_yaml::Value;

use super::super::contracts_hold;
use crate::{ACT_VALIDATION_WORKFLOW, CI_WORKFLOW, action_ref, pin_violations};

/// Repoints every occurrence of an action that the committed source must contain.
///
/// The helper lives outside a `#[test]` body, where the repository's strict
/// `expect_used` lint applies, so it panics with an explicit message instead.
fn repointed_all(source: &str, path: &str, reference: &str) -> String {
    let Some(changed) = action_ref::repoint_all_actions(source, path, reference) else {
        panic!("the committed workflow must contain {path}")
    };
    changed
}

/// Every `uses` value a workflow declares at job or step level.
///
/// Reading the parsed values rather than the source text is what lets a bump
/// fixture prove it moved the call sites, not merely that some text changed.
fn uses_values(source: &str) -> Vec<String> {
    let document = match serde_yaml::from_str::<Value>(source) {
        Ok(document) => document,
        Err(error) => panic!("the workflow fixture must parse: {error}"),
    };
    let Some(jobs) = document.get("jobs").and_then(Value::as_mapping) else {
        panic!("the workflow fixture must declare jobs");
    };
    let mut values = Vec::new();
    for job in jobs.values() {
        if let Some(uses) = job.get("uses").and_then(Value::as_str) {
            values.push(uses.to_owned());
        }
        for step in job
            .get("steps")
            .and_then(Value::as_sequence)
            .into_iter()
            .flatten()
        {
            if let Some(uses) = step.get("uses").and_then(Value::as_str) {
                values.push(uses.to_owned());
            }
        }
    }
    values
}

/// Every action path a workflow references at job or step level.
///
/// A coordinated bump must move each path once, not once per fixture list, so
/// the paths come from the workflow itself.
fn action_paths(source: &str) -> BTreeSet<String> {
    uses_values(source)
        .iter()
        .map(|uses| action_ref::action_path(uses).to_owned())
        .collect()
}

/// Moves every action reference in one workflow to a shared reference.
fn bumped(source: &str, reference: &str) -> String {
    action_paths(source)
        .iter()
        .filter(|path| !path.starts_with("./"))
        .fold(source.to_owned(), |current, path| {
            repointed_all(&current, path, reference)
        })
}

/// Immutable action bumps retain contracts without lockstep expected-SHA changes.
///
/// CI and the manual Act route receive the same synthetic reference, so this is
/// also the coordinated-bump case: agreement survives a bump that moves every
/// occurrence, and the repository-wide pin contract still holds.
#[test]
fn immutable_action_bumps_preserve_workflow_contract() {
    let reference = "0".repeat(40);
    let ci = bumped(CI_WORKFLOW, &reference);
    let manual = bumped(ACT_VALIDATION_WORKFLOW, &reference);
    assert_ne!(ci, CI_WORKFLOW, "the CI bump must change the source");
    assert_ne!(
        manual, ACT_VALIDATION_WORKFLOW,
        "the Act bump must change the source"
    );
    for (name, source) in [
        ("ci.yml", ci.as_str()),
        ("act-validation.yml", manual.as_str()),
    ] {
        for uses in uses_values(source)
            .into_iter()
            .filter(|uses| !uses.starts_with("./"))
        {
            assert!(
                uses.ends_with(&format!("@{reference}")),
                "{name} must take the bumped reference at every call site: {uses}"
            );
        }
    }
    assert!(
        contracts_hold(&ci, &manual),
        "a coordinated immutable bump must preserve the workflow contracts"
    );
    let violations = pin_violations(&[
        ("ci.yml", ci.as_str()),
        ("act-validation.yml", manual.as_str()),
    ]);
    assert!(
        violations.is_empty(),
        "a coordinated bump must satisfy the repository pin contract: {violations:?}"
    );
}

/// Setup-rust must agree across routes and remain a commit reference.
///
/// A one-sided bump or a floating manual reference changes behaviour, so the
/// contract must reject it even though the new value is itself SHA-shaped.
#[test]
fn setup_rust_divergence_breaks_the_contract() {
    let reference = "1".repeat(40);
    let hosted = repointed_all(CI_WORKFLOW, action_ref::SETUP_RUST_PATH, &reference);
    let manual = repointed_all(
        ACT_VALIDATION_WORKFLOW,
        action_ref::SETUP_RUST_PATH,
        &reference,
    );
    let floating = repointed_all(ACT_VALIDATION_WORKFLOW, action_ref::SETUP_RUST_PATH, "main");
    for (reason, ci, act) in [
        (
            "hosted setup-rust moved alone",
            hosted.as_str(),
            ACT_VALIDATION_WORKFLOW,
        ),
        (
            "manual setup-rust moved alone",
            CI_WORKFLOW,
            manual.as_str(),
        ),
        (
            "manual setup-rust is floating",
            CI_WORKFLOW,
            floating.as_str(),
        ),
    ] {
        assert!(
            !contracts_hold(ci, act),
            "contract must reject a setup-rust divergence: {reason}"
        );
    }
    assert_ne!(hosted, CI_WORKFLOW, "hosted mutation must change source");
    assert_ne!(
        manual, ACT_VALIDATION_WORKFLOW,
        "manual mutation must change source"
    );
    assert_ne!(
        floating, ACT_VALIDATION_WORKFLOW,
        "manual floating mutation must change source"
    );
}
