//! Structural checks for the prover release-pin files.
//!
//! The pin files are the record of the configured releases, so these readers
//! check the shape of each file and the relationships between them rather than
//! restating a value that a legitimate release bump would change. Every failure
//! names the file and the rule it broke, so a maintainer can repair a pin
//! without reading this module.

use std::{
    error::Error,
    fmt::{self, Display, Formatter},
};

/// A pin file that does not satisfy the contract its consumer relies on.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct PinError {
    /// Repository-relative file the rule was checked against.
    file: String,
    /// The rule that failed, phrased for a maintainer.
    rule: String,
}

impl PinError {
    /// Records a failure of `rule` in `file`.
    pub(crate) fn new(file: &str, rule: impl Into<String>) -> Self {
        Self {
            file: file.to_owned(),
            rule: rule.into(),
        }
    }
}

impl Display for PinError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.file, self.rule)
    }
}

impl Error for PinError {}

/// Returns the sole line of a pin file and rejects every other line shape.
///
/// `make` reads `tools/kani/VERSION` with `$(shell cat)`, which strips only
/// trailing newlines. A second line or a carriage return would silently become
/// part of the installation path, so the file must end with exactly one `\n`
/// and contain no other line separator.
pub(crate) fn single_line<'a>(file: &str, text: &'a str) -> Result<&'a str, PinError> {
    let Some(line) = text.strip_suffix('\n') else {
        return Err(PinError::new(file, "must end with exactly one newline"));
    };
    if line.is_empty() {
        return Err(PinError::new(file, "must not be empty"));
    }
    if line.bytes().any(|byte| matches!(byte, b'\n' | b'\r')) {
        return Err(PinError::new(file, "must contain exactly one line"));
    }
    Ok(line)
}

/// Requires a Kani release such as `1.2.3`.
pub(crate) fn kani_version<'a>(file: &str, text: &'a str) -> Result<&'a str, PinError> {
    let version = single_line(file, text)?;
    if is_kani_version(version) {
        Ok(version)
    } else {
        Err(PinError::new(
            file,
            format!("expected a Kani release such as 1.2.3, got {version:?}"),
        ))
    }
}

/// Requires a Verus release such as `0.2027.01.15.abc1234`.
pub(crate) fn verus_version<'a>(file: &str, text: &'a str) -> Result<&'a str, PinError> {
    let version = single_line(file, text)?;
    if is_verus_version(version) {
        Ok(version)
    } else {
        Err(PinError::new(
            file,
            format!("expected a Verus release such as 0.2027.01.15.abc1234, got {version:?}"),
        ))
    }
}

/// Requires the single checksum row to bind the release the VERSION file selects.
pub(crate) fn verus_checksum_row(file: &str, text: &str, version: &str) -> Result<(), PinError> {
    let row = single_line(file, text)?;
    let Some((digest, archive)) = row.split_once("  ") else {
        return Err(PinError::new(
            file,
            "expected one '<digest>  <archive>' row",
        ));
    };
    if !is_lowercase_hex(digest, 64) {
        return Err(PinError::new(
            file,
            format!("digest must be 64 lowercase hexadecimal characters, got {digest:?}"),
        ));
    }
    let expected = format!("verus-{version}-x86-linux.zip");
    if archive == expected {
        Ok(())
    } else {
        Err(PinError::new(
            file,
            format!("archive must be {expected:?}, got {archive:?}"),
        ))
    }
}

/// Reads the single `ref:` row and requires a full lowercase commit.
pub(crate) fn pinned_ref<'a>(file: &str, text: &'a str) -> Result<&'a str, PinError> {
    let reference = sole_field(file, text, "ref: ")?;
    if is_lowercase_hex(reference, 40) {
        Ok(reference)
    } else {
        Err(PinError::new(
            file,
            format!("ref must be 40 lowercase hexadecimal characters, got {reference:?}"),
        ))
    }
}

/// Reads the single `repository:` row and requires a whitespace-free URL.
pub(crate) fn pinned_repository<'a>(file: &str, text: &'a str) -> Result<&'a str, PinError> {
    let repository = sole_field(file, text, "repository: ")?;
    if repository.is_empty() || repository.bytes().any(|byte| byte.is_ascii_whitespace()) {
        return Err(PinError::new(
            file,
            format!("repository must be a URL without whitespace, got {repository:?}"),
        ));
    }
    Ok(repository)
}

/// Reads the value of the sole line that starts with `prefix`.
fn sole_field<'a>(file: &str, text: &'a str, prefix: &str) -> Result<&'a str, PinError> {
    if text.bytes().any(|byte| byte == b'\r') {
        return Err(PinError::new(file, "must use newline line endings"));
    }
    let mut values = text.lines().filter_map(|line| line.strip_prefix(prefix));
    let Some(value) = values.next() else {
        return Err(PinError::new(
            file,
            format!("must contain one `{prefix}` row"),
        ));
    };
    if values.next().is_some() {
        return Err(PinError::new(
            file,
            format!("must contain exactly one `{prefix}` row"),
        ));
    }
    Ok(value)
}

/// Reports whether a value has three dot-separated numeric components.
fn is_kani_version(version: &str) -> bool {
    let parts = version.split('.').collect::<Vec<_>>();
    parts.len() == 3 && parts.iter().all(|part| is_numeric_component(part))
}

/// Reports whether a version component is a decimal number without a leading zero.
fn is_numeric_component(component: &str) -> bool {
    !component.is_empty()
        && component.bytes().all(|byte| byte.is_ascii_digit())
        && (component == "0" || !component.starts_with('0'))
}

/// Reports whether a value follows Verus's `0.<date>.<abbreviated-commit>` scheme.
fn is_verus_version(version: &str) -> bool {
    let parts = version.split('.').collect::<Vec<_>>();
    match parts.as_slice() {
        ["0", year, month, day, commit] => {
            year.len() == 4
                && year.bytes().all(|byte| byte.is_ascii_digit())
                && is_calendar_component(month, 12)
                && is_calendar_component(day, 31)
                && is_lowercase_hex(commit, 7)
        }
        _ => false,
    }
}

/// Reports whether a zero-padded two-digit component falls in `1..=maximum`.
fn is_calendar_component(component: &str, maximum: u8) -> bool {
    component.len() == 2
        && component.bytes().all(|byte| byte.is_ascii_digit())
        && component
            .parse::<u8>()
            .is_ok_and(|value| (1..=maximum).contains(&value))
}

/// Reports whether `value` is exactly `length` lowercase hexadecimal characters.
pub(crate) fn is_lowercase_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
}
