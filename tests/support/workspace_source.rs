//! Source checks that keep the kernel `#![no_std]` and allocation-free.
//!
//! The kernel contract is about attributes the compiler acts on. A doc comment
//! or a string literal that merely names `#![no_std]` does not put the crate in
//! `no_std` mode, so every check runs over code with comments and literals
//! removed. Without that step the crate's own documentation would satisfy the
//! check after a contributor deleted the real attribute.

use std::{error::Error, iter::Peekable, str::Chars};

use cap_std::{ambient_authority, fs_utf8::Dir};

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
    for (text, description) in [
        ("#![no_std]", "declare #![no_std]"),
        (
            "clippy::std_instead_of_core",
            "deny clippy::std_instead_of_core",
        ),
        (
            "clippy::alloc_instead_of_core",
            "deny clippy::alloc_instead_of_core",
        ),
    ] {
        if !code.contains(text) {
            violations.push(format!("the kernel crate root must {description}"));
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

/// Removes comments and literals, leaving their surrounding tokens separated.
fn strip_comments_and_literals(source: &str) -> String {
    let mut code = String::with_capacity(source.len());
    let mut chars = source.chars().peekable();
    while let Some(ch) = chars.next() {
        match ch {
            '/' if chars.peek() == Some(&'/') => {
                chars.next();
                code.push('\n');
                skip_to_newline(&mut chars);
            }
            '/' if chars.peek() == Some(&'*') => {
                chars.next();
                code.push(' ');
                skip_block_comment(&mut chars);
            }
            'r' => {
                if let Some(hashes) = raw_string_hashes(&chars) {
                    skip_raw_string(&mut chars, hashes);
                } else {
                    code.push(ch);
                }
            }
            '"' => skip_quoted_string(&mut chars),
            _ => code.push(ch),
        }
    }
    code
}

/// Reports how many `#` characters open a raw string, or `None`.
fn raw_string_hashes(chars: &Peekable<Chars<'_>>) -> Option<usize> {
    let mut lookahead = chars.clone();
    let mut hashes = 0;
    while lookahead.peek() == Some(&'#') {
        lookahead.next();
        hashes += 1;
    }
    (lookahead.peek() == Some(&'"')).then_some(hashes)
}

/// Skips the remainder of a line comment, leaving its newline to the caller.
fn skip_to_newline(chars: &mut Peekable<Chars<'_>>) {
    for ch in chars.by_ref() {
        if ch == '\n' {
            return;
        }
    }
}

/// Skips a block comment, including nested block comments.
fn skip_block_comment(chars: &mut Peekable<Chars<'_>>) {
    let mut depth = 1_usize;
    while let Some(ch) = chars.next() {
        match ch {
            '/' if chars.peek() == Some(&'*') => {
                chars.next();
                depth += 1;
            }
            '*' if chars.peek() == Some(&'/') => {
                chars.next();
                depth -= 1;
                if depth == 0 {
                    return;
                }
            }
            _ => {}
        }
    }
}

/// Skips a raw string opened by `hashes` `#` characters.
fn skip_raw_string(chars: &mut Peekable<Chars<'_>>, hashes: usize) {
    for ch in chars.by_ref() {
        if ch == '"' {
            break;
        }
    }
    while let Some(ch) = chars.next() {
        if ch == '"' && raw_string_closes(chars, hashes) {
            return;
        }
    }
}

/// Consumes the closing `#` run and reports whether it completes the string.
fn raw_string_closes(chars: &mut Peekable<Chars<'_>>, hashes: usize) -> bool {
    (0..hashes).all(|_| chars.next() == Some('#'))
}

/// Skips a quoted string, honouring backslash escapes.
fn skip_quoted_string(chars: &mut Peekable<Chars<'_>>) {
    while let Some(ch) = chars.next() {
        match ch {
            '\\' => {
                chars.next();
            }
            '"' => return,
            _ => {}
        }
    }
}
