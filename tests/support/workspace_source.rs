//! Source checks that keep the kernel `#![no_std]` and allocation-free.
//!
//! The kernel contract is about attributes the compiler acts on. A doc comment
//! or a string literal that merely names `#![no_std]` does not put the crate in
//! `no_std` mode, so every check runs over code with comments and literals
//! removed. Without that step the crate's own documentation would satisfy the
//! check after a contributor deleted the real attribute.
//!
//! The lexical scanner that performs that removal lives in
//! [`scanner`], which is a child module so its own tests can sit beside it.

use std::error::Error;

use cap_std::{ambient_authority, fs_utf8::Dir};

#[path = "workspace_scanner.rs"]
mod scanner;

use scanner::strip_comments_and_literals;

/// Reads the kernel crate root from the workspace.
pub(super) fn kernel_source() -> Result<String, Box<dyn Error>> {
    let directory = Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())?;
    Ok(directory.read_to_string("crates/combobulate-kernel/src/lib.rs")?)
}

/// Reports the `no_std`, allocation, and lint rules the kernel source lacks.
///
/// Checks run over code only, so a comment or string that names an attribute
/// cannot stand in for the attribute itself.
///
/// ```text
/// kernel_source_violations("#![no_std]\n")
/// // reports the two missing lint rules
/// kernel_source_violations("// #![no_std]\n")
/// // reports the missing attribute as well
/// ```
pub(super) fn kernel_source_violations(source: &str) -> Vec<String> {
    let code = code_only(source);
    let mut violations = Vec::new();
    if !code.contains("#![no_std]") {
        violations.push("the kernel crate root must declare #![no_std]".to_owned());
    }
    for lint in [
        "clippy::std_instead_of_core",
        "clippy::alloc_instead_of_core",
    ] {
        if !matches!(
            final_lint_level(&code, lint),
            Some(LintLevel::Deny | LintLevel::Forbid)
        ) {
            violations.push(format!("the kernel crate root must deny {lint}"));
        }
    }
    for text in ["extern crate alloc", "extern crate std"] {
        if code.contains(text) {
            violations.push(format!("the kernel crate root must not contain {text}"));
        }
    }
    violations
}

/// Returns `source` with comments and string literals removed.
///
/// Whitespace is collapsed so `extern /* note */ crate alloc` still reads as
/// the declaration a violation check must see.
fn code_only(source: &str) -> String {
    strip_comments_and_literals(source)
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

/// A crate-level lint level, in the order attributes can override each other.
#[derive(Clone, Copy, PartialEq, Eq)]
enum LintLevel {
    Allow,
    Warn,
    Deny,
    Forbid,
}

/// Returns the last crate-level level set for `lint`, if any attribute sets one.
///
/// Scanning in source order keeps a later `#![allow(...)]` from being hidden by
/// an earlier `#![deny(...)]`: the last level a compiler sees is the effective
/// one, so a deny that is later allowed does not satisfy the boundary.
fn final_lint_level(code: &str, lint: &str) -> Option<LintLevel> {
    let mut level = None;
    for attribute in crate_attributes(code) {
        let Some((name, body)) = split_attribute(attribute) else {
            continue;
        };
        let Some(set) = parse_lint_level(name) else {
            continue;
        };
        if lint_list(body).any(|item| item == lint) {
            level = Some(set);
        }
    }
    level
}

/// Returns the inner text of every crate-level `#![...]` attribute.
fn crate_attributes(code: &str) -> Vec<&str> {
    let mut attributes = Vec::new();
    let mut index = 0;
    while let Some(rest) = code.get(index..) {
        let Some(offset) = rest.find("#![") else {
            break;
        };
        let start = index + offset + 3;
        let Some(tail) = code.get(start..) else {
            break;
        };
        let Some(end) = matching_bracket(tail) else {
            break;
        };
        let Some(attribute) = tail.get(..end) else {
            break;
        };
        attributes.push(attribute.trim());
        index = start + end;
    }
    attributes
}

/// Returns the byte offset of the `]` that closes this attribute's bracket.
fn matching_bracket(tail: &str) -> Option<usize> {
    let mut depth = 1_usize;
    for (position, character) in tail.char_indices() {
        match character {
            '[' => depth += 1,
            ']' => {
                depth -= 1;
                if depth == 0 {
                    return Some(position);
                }
            }
            _ => {}
        }
    }
    None
}

/// Splits `deny(a, b)` into its level name and its parenthesized list.
fn split_attribute(attribute: &str) -> Option<(&str, &str)> {
    let open = attribute.find('(')?;
    let close = attribute.rfind(')')?;
    if close > open {
        let name = attribute.get(..open)?.trim();
        let body = attribute.get(open + 1..close)?.trim();
        Some((name, body))
    } else {
        None
    }
}

/// Maps an attribute name to a lint level, ignoring attributes of other kinds.
fn parse_lint_level(name: &str) -> Option<LintLevel> {
    match name {
        "allow" => Some(LintLevel::Allow),
        "warn" => Some(LintLevel::Warn),
        "deny" => Some(LintLevel::Deny),
        "forbid" => Some(LintLevel::Forbid),
        _ => None,
    }
}

/// Yields the lint names in an attribute list, skipping `reason = ...` clauses.
fn lint_list(body: &str) -> impl Iterator<Item = &str> {
    body.split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty() && !item.contains('='))
}
