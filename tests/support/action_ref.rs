//! Shared action-path and immutable-reference checks for workflow contracts.
//!
//! Fixture mutation resolves call sites through the parsed workflow document
//! rather than by scanning its text. A `uses` value is a call site only when it
//! is a job-level `jobs.*.uses` or a step-level `jobs.*.steps[*].uses`, so a
//! comment, a folded scalar, or a `with:` input that names an action is never
//! repointed. A mutated document is serialized again, which keeps its structure
//! but not its comments or original quoting; every caller parses the result as
//! YAML.

use serde_yaml::Value;

/// The shared action that provisions Rust in every workflow.
pub(crate) const SETUP_RUST_PATH: &str = "leynos/shared-actions/.github/actions/setup-rust";

/// Returns the action path before its trailing `@` reference, if any.
pub(crate) fn action_path(uses: &str) -> &str {
    uses.rsplit_once('@').map_or(uses, |(path, _)| path)
}

/// Requires a full lowercase hexadecimal commit reference, independently of its value.
pub(crate) fn is_sha_pinned(uses: &str) -> bool {
    uses.rsplit_once('@').is_some_and(|(_, reference)| {
        reference.len() == 40
            && reference
                .bytes()
                .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    })
}

/// Checks the expected action identity and an immutable commit-shaped reference.
pub(crate) fn matches_pinned_action(uses: &str, expected_path: &str) -> bool {
    action_path(uses) == expected_path && is_sha_pinned(uses)
}

/// Replaces the reference in a `uses` value that names the expected action.
fn repointed_reference(uses: &str, path: &str, replacement: &str) -> Option<String> {
    let (action, _reference) = uses.rsplit_once('@')?;
    (action == path).then(|| format!("{path}@{replacement}"))
}

/// One coordinated, or deliberately partial, fixture mutation.
struct Repoint<'a> {
    path: &'a str,
    replacement: &'a str,
    first_only: bool,
    replaced: bool,
}

impl Repoint<'_> {
    /// Repoints one call-site value in place, once its turn has come.
    fn visit(&mut self, uses: &mut Value) {
        if self.is_done() {
            return;
        }
        let Some(text) = uses.as_str() else {
            return;
        };
        let Some(updated) = repointed_reference(text, self.path, self.replacement) else {
            return;
        };
        *uses = Value::String(updated);
        self.replaced = true;
    }

    /// Whether a partial mutation has already moved its only call site.
    fn is_done(&self) -> bool { self.replaced && self.first_only }
}

/// Repoints job-level and step-level `uses` values inside a parsed workflow.
///
/// Only the two documented call-site shapes are visited, so a `with:` input
/// named `uses` is left alone even when it names the same action.
fn repoint_document(document: &mut Value, path: &str, replacement: &str, first_only: bool) -> bool {
    let mut repoint = Repoint {
        path,
        replacement,
        first_only,
        replaced: false,
    };
    let Some(jobs) = document.get_mut("jobs").and_then(Value::as_mapping_mut) else {
        return false;
    };
    for job in jobs.values_mut() {
        let Some(entry) = job.as_mapping_mut() else {
            continue;
        };
        if let Some(uses) = entry.get_mut("uses") {
            repoint.visit(uses);
        }
        for step in entry
            .get_mut("steps")
            .and_then(Value::as_sequence_mut)
            .into_iter()
            .flatten()
        {
            if repoint.is_done() {
                break;
            }
            if let Some(uses) = step.get_mut("uses") {
                repoint.visit(uses);
            }
        }
        if repoint.is_done() {
            break;
        }
    }
    repoint.replaced
}

/// Repoints the first matching call site, or every call site.
///
/// Returns `None` when the source has no matching call site, or when it cannot
/// be parsed and serialized again. Every caller treats that as a fixture that
/// does not contain the action.
fn repointed(source: &str, path: &str, replacement: &str, first_only: bool) -> Option<String> {
    let mut document: Value = serde_yaml::from_str(source).ok()?;
    if !repoint_document(&mut document, path, replacement, first_only) {
        return None;
    }
    serde_yaml::to_string(&document).ok()
}

/// Replaces the first `uses` reference without coupling fixtures to its SHA.
pub(crate) fn repoint_action(source: &str, path: &str, replacement: &str) -> Option<String> {
    repointed(source, path, replacement, true)
}

/// Replaces every `uses` reference to the action.
///
/// A coordinated bump must move all of an action's call sites: leaving one
/// behind would make the fixture test an inconsistency rather than a bump.
pub(crate) fn repoint_all_actions(source: &str, path: &str, replacement: &str) -> Option<String> {
    repointed(source, path, replacement, false)
}

/// Shape and bump regressions shared by all action-reference consumers.
#[cfg(test)]
#[path = "action_ref_tests.rs"]
mod tests;
