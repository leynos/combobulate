//! The PEP 723 helper pin embedded in the verifier probe script.
//!
//! `scripts/run_verifier_probes.py` must fetch the same `rust-prover-tools`
//! revision that `tools/rust-prover-tools/REF` records, but PEP 723 metadata
//! cannot read another file. These readers extract the embedded dependency so
//! the contract test can compare the two records without restating either
//! value.

use crate::pins::{PinError, is_lowercase_hex, pinned_ref, pinned_repository};

/// The probe script whose embedded dependency must agree with the REF pin.
const SCRIPT: &str = "scripts/run_verifier_probes.py";

/// The file that owns the prover-tools repository and revision pins.
const REFERENCE: &str = "tools/rust-prover-tools/REF";

/// Requires a probe script's helper dependency to name the same source as REF.
pub(crate) fn script_matches_reference(script: &str, reference: &str) -> Result<(), PinError> {
    let dependency = script_dependency(SCRIPT, script)?;
    let revision = pinned_ref(REFERENCE, reference)?;
    let repository = pinned_repository(REFERENCE, reference)?;
    let actual_revision = dependency.revision;
    let actual_repository = dependency.repository;
    if actual_revision != revision {
        return Err(PinError::new(
            SCRIPT,
            format!("must pin the REF revision {revision}, got {actual_revision}"),
        ));
    }
    if actual_repository != repository {
        return Err(PinError::new(
            SCRIPT,
            format!("must name the REF repository {repository}, got {actual_repository}"),
        ));
    }
    Ok(())
}

/// The Git source a PEP 723 probe script requires for `rust-prover-tools`.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct ScriptDependency {
    /// The repository URL without the `git+` transport prefix.
    pub(crate) repository: String,
    /// The full 40-character lowercase revision.
    pub(crate) revision: String,
}

/// Reads the `rust-prover-tools` Git dependency from the script's PEP 723 block.
pub(crate) fn script_dependency(file: &str, source: &str) -> Result<ScriptDependency, PinError> {
    let metadata = script_metadata(file, source)?;
    let document = toml::from_str::<toml::Value>(&metadata)
        .map_err(|error| PinError::new(file, format!("embedded metadata is not TOML: {error}")))?;
    let dependencies = document
        .get("dependencies")
        .and_then(toml::Value::as_array)
        .ok_or_else(|| PinError::new(file, "embedded metadata must list dependencies"))?;
    let requirement = sole_helper_requirement(file, dependencies)?;
    parse_helper_requirement(file, requirement)
}

/// Extracts the TOML inside the script's sole PEP 723 metadata block.
fn script_metadata(file: &str, source: &str) -> Result<String, PinError> {
    let mut has_block = false;
    let mut is_open = false;
    let mut metadata = String::new();
    for line in source.lines() {
        match line {
            "# /// script" => {
                if has_block {
                    return Err(PinError::new(
                        file,
                        "must contain exactly one PEP 723 script block",
                    ));
                }
                has_block = true;
                is_open = true;
            }
            "# ///" if is_open => is_open = false,
            _ if is_open => {
                let text = line
                    .strip_prefix("# ")
                    .or_else(|| line.strip_prefix('#'))
                    .ok_or_else(|| PinError::new(file, "every PEP 723 line must be a comment"))?;
                metadata.push_str(text);
                metadata.push('\n');
            }
            _ => {}
        }
    }
    if is_open {
        return Err(PinError::new(
            file,
            "the PEP 723 script block must close with `# ///`",
        ));
    }
    if has_block {
        Ok(metadata)
    } else {
        Err(PinError::new(
            file,
            "must contain exactly one PEP 723 script block",
        ))
    }
}

/// Selects the single dependency whose requirement names `rust-prover-tools`.
fn sole_helper_requirement<'a>(
    file: &str,
    dependencies: &'a [toml::Value],
) -> Result<&'a str, PinError> {
    let mut found = None;
    for dependency in dependencies {
        let requirement = dependency
            .as_str()
            .ok_or_else(|| PinError::new(file, "every embedded dependency must be a string"))?;
        if requirement_name(requirement) == "rust-prover-tools" {
            if found.is_some() {
                return Err(PinError::new(
                    file,
                    "must list rust-prover-tools exactly once",
                ));
            }
            found = Some(requirement);
        }
    }
    found.ok_or_else(|| PinError::new(file, "must list a rust-prover-tools dependency"))
}

/// Returns the distribution name from a PEP 508 requirement.
fn requirement_name(requirement: &str) -> &str {
    requirement
        .split(|character: char| {
            character.is_whitespace()
                || matches!(
                    character,
                    '@' | '=' | '<' | '>' | '!' | '~' | ';' | '[' | '('
                )
        })
        .next()
        .unwrap_or_default()
}

/// Requires the helper requirement to be a `git+` reference with a full commit.
fn parse_helper_requirement(file: &str, requirement: &str) -> Result<ScriptDependency, PinError> {
    let source = requirement
        .strip_prefix("rust-prover-tools @ git+")
        .ok_or_else(|| {
            PinError::new(
                file,
                "rust-prover-tools must use `@ git+<repository>@<revision>`",
            )
        })?;
    let Some((repository, revision)) = source.rsplit_once('@') else {
        return Err(PinError::new(
            file,
            "rust-prover-tools must name a revision after `@`",
        ));
    };
    if repository.is_empty() || repository.bytes().any(|byte| byte.is_ascii_whitespace()) {
        return Err(PinError::new(
            file,
            format!(
                "rust-prover-tools repository must be a URL without whitespace, got {repository:?}"
            ),
        ));
    }
    if !is_lowercase_hex(revision, 40) {
        return Err(PinError::new(
            file,
            format!(
                "rust-prover-tools revision must be 40 lowercase hexadecimal characters, got \
                 {revision:?}"
            ),
        ));
    }
    Ok(ScriptDependency {
        repository: repository.to_owned(),
        revision: revision.to_owned(),
    })
}
