//! The PEP 723 helper pin embedded in the verifier probe script.
//!
//! `scripts/run_verifier_probes.py` must fetch the same `rust-prover-tools`
//! revision that `tools/rust-prover-tools/REF` records, but PEP 723 metadata
//! cannot read another file. These readers extract the embedded dependency so
//! the contract test can compare the two records without restating either
//! value.

use crate::pins::{PinError, PinSource, is_lowercase_hex, pinned_ref, pinned_repository};

/// The probe script whose embedded dependency must agree with the REF pin.
const SCRIPT: &str = "scripts/run_verifier_probes.py";

/// The file that owns the prover-tools repository and revision pins.
const REFERENCE: &str = "tools/rust-prover-tools/REF";

/// Requires a probe script's helper dependency to name the same source as REF.
pub(crate) fn script_matches_reference(
    script: PinSource<'_>,
    reference: PinSource<'_>,
) -> Result<(), PinError> {
    let dependency = script_dependency(script)?;
    let revision = pinned_ref(reference)?;
    let repository = pinned_repository(reference)?;
    let actual_revision = dependency.revision;
    let actual_repository = dependency.repository;
    if actual_revision != revision {
        return Err(script.error(format!(
            "must pin the REF revision {revision}, got {actual_revision}"
        )));
    }
    if actual_repository != repository {
        return Err(script.error(format!(
            "must name the REF repository {repository}, got {actual_repository}"
        )));
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
pub(crate) fn script_dependency(script: PinSource<'_>) -> Result<ScriptDependency, PinError> {
    let metadata = script_metadata(script)?;
    let document = toml::from_str::<toml::Value>(&metadata)
        .map_err(|error| script.error(format!("embedded metadata is not TOML: {error}")))?;
    let dependencies = document
        .get("dependencies")
        .and_then(toml::Value::as_array)
        .ok_or_else(|| script.error("embedded metadata must list dependencies"))?;
    let requirement = sole_helper_requirement(script, dependencies)?;
    parse_helper_requirement(script, requirement)
}

/// Extracts the TOML inside the script's sole PEP 723 metadata block.
fn script_metadata(script: PinSource<'_>) -> Result<String, PinError> {
    let mut has_block = false;
    let mut is_open = false;
    let mut metadata = String::new();
    for line in script.text().lines() {
        match line {
            "# /// script" => {
                if has_block {
                    return Err(script.error("must contain exactly one PEP 723 script block"));
                }
                has_block = true;
                is_open = true;
            }
            "# ///" if is_open => is_open = false,
            _ if is_open => {
                let text = line
                    .strip_prefix("# ")
                    .or_else(|| line.strip_prefix('#').filter(|rest| rest.is_empty()))
                    .ok_or_else(|| {
                        script.error(
                            "every PEP 723 line must be a comment of the form `# <metadata>` or \
                             `#`",
                        )
                    })?;
                metadata.push_str(text);
                metadata.push('\n');
            }
            _ => {}
        }
    }
    if is_open {
        return Err(script.error("the PEP 723 script block must close with `# ///`"));
    }
    if has_block {
        Ok(metadata)
    } else {
        Err(script.error("must contain exactly one PEP 723 script block"))
    }
}

/// Selects the single dependency whose requirement names `rust-prover-tools`.
fn sole_helper_requirement<'a>(
    script: PinSource<'_>,
    dependencies: &'a [toml::Value],
) -> Result<Requirement<'a>, PinError> {
    let mut found = None;
    for dependency in dependencies {
        let text = dependency
            .as_str()
            .ok_or_else(|| script.error("every embedded dependency must be a string"))?;
        let requirement = Requirement::parse(text);
        if requirement.is_helper() {
            if found.is_some() {
                return Err(script.error("must list rust-prover-tools exactly once"));
            }
            found = Some(requirement);
        }
    }
    found.ok_or_else(|| script.error("must list a rust-prover-tools dependency"))
}

/// A PEP 508 requirement read from the embedded dependency list.
#[derive(Clone, Copy)]
struct Requirement<'a>(&'a str);

impl<'a> Requirement<'a> {
    /// Parses a requirement, discarding the padding PEP 508 permits around it.
    ///
    /// Without this, a requirement written as `" rust-prover-tools @ ..."`
    /// yields an empty name, so a second helper requirement would go
    /// unnoticed instead of being rejected as a duplicate.
    fn parse(text: &'a str) -> Self { Self(text.trim()) }

    /// Returns the distribution name, before any version or URL marker.
    fn name(self) -> &'a str {
        self.0
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

    /// Applies PEP 503 normalization so `rust_prover_tools` cannot slip past a
    /// uniqueness check written for `rust-prover-tools`.
    fn normalized_name(self) -> String {
        let name = self.name();
        let mut normalized = String::with_capacity(name.len());
        for character in name.to_lowercase().chars() {
            push_normalized(&mut normalized, character);
        }
        normalized
    }

    /// Reports whether this requirement names the helper distribution.
    fn is_helper(self) -> bool { self.normalized_name() == "rust-prover-tools" }
}

/// Appends one PEP 503 normalized character, collapsing separator runs.
fn push_normalized(normalized: &mut String, character: char) {
    let is_separator = matches!(character, '-' | '_' | '.');
    if is_separator && normalized.ends_with('-') {
        return;
    }
    normalized.push(if is_separator { '-' } else { character });
}

/// Requires the helper requirement to be a `git+` reference with a full commit.
fn parse_helper_requirement(
    script: PinSource<'_>,
    requirement: Requirement<'_>,
) -> Result<ScriptDependency, PinError> {
    let text = requirement.0;
    let Some((name, location)) = text.split_once(" @ ") else {
        return Err(script.error("rust-prover-tools must use `@ git+<repository>@<revision>`"));
    };
    if !Requirement::parse(name).is_helper() {
        return Err(script.error(format!(
            "expected the rust-prover-tools requirement, got {name:?}"
        )));
    }
    let source = location.strip_prefix("git+").ok_or_else(|| {
        script.error("rust-prover-tools must use `@ git+<repository>@<revision>`")
    })?;
    let Some((repository, revision)) = source.rsplit_once('@') else {
        return Err(script.error("rust-prover-tools must name a revision after `@`"));
    };
    if repository.is_empty() || repository.bytes().any(|byte| byte.is_ascii_whitespace()) {
        return Err(script.error(format!(
            "rust-prover-tools repository must be a URL without whitespace, got {repository:?}"
        )));
    }
    if !is_lowercase_hex(revision, 40) {
        return Err(script.error(format!(
            "rust-prover-tools revision must be 40 lowercase hexadecimal characters, got \
             {revision:?}"
        )));
    }
    Ok(ScriptDependency {
        repository: repository.to_owned(),
        revision: revision.to_owned(),
    })
}

/// The script's file label, for callers that only have its text.
pub(crate) fn script_source(text: &str) -> PinSource<'_> { PinSource::new(SCRIPT, text) }

/// The REF file label, for callers that only have its text.
pub(crate) fn reference_source(text: &str) -> PinSource<'_> { PinSource::new(REFERENCE, text) }
