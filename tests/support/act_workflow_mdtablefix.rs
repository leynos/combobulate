//! The mdtablefix version the hosted workflow installs and the manual one must match.

use serde_yaml::Value;

use super::{action_input, action_ref, at, text};

/// The mdtablefix action's path, without a revision.
const MDTABLEFIX_ACTION: &str = "leynos/shared-actions/.github/actions/install-mdtablefix";

/// Reads the version the workflow gives its mdtablefix install step.
pub(crate) fn version(workflow: &Value) -> Option<String> {
    let jobs = at(workflow, &["jobs"])?.as_mapping()?;
    jobs.values().find_map(|job| {
        at(job, &["steps"])?.as_sequence()?.iter().find_map(|item| {
            text(item, &["uses"])
                .filter(|uses| action_ref::matches_pinned_action(uses, MDTABLEFIX_ACTION))?;
            action_input(item, "version")
        })
    })
}

/// The hosted workflow is the source of the mdtablefix version; the manual
/// Act workflow must install the same one.
pub(crate) fn versions_agree(ci: &Value, act: &Value) -> bool {
    version(ci).is_some_and(|hosted| {
        !hosted.is_empty() && version(act).as_deref() == Some(hosted.as_str())
    })
}
