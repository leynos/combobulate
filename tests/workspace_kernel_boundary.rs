//! The kernel's `#![no_std]` and allocation boundary, read from source.
//!
//! VO-6 says the kernel crate root keeps `#![no_std]` and denies the two lints
//! that keep allocation usage honest. That is a property of the source text, so
//! it is checked by scanning the crate root rather than by compiling it.
//!
//! The scanner has to be told what a real attribute looks like. A comment that
//! mentions `#![no_std]`, or a string literal that contains it, must not satisfy
//! the boundary, and a lint that appears under `allow` or `warn` must not count
//! as a `deny`. The fixture cases below pin each of those readings, because a
//! scanner that merely substring-searches would pass every one of them.

use googletest::prelude::*;
use rstest::rstest;

/// Source checks for the kernel's `no_std` and allocation boundary.
#[path = "support/workspace_source.rs"]
mod source;

/// VO-6: the kernel keeps `#![no_std]` and its core-only lint boundary.
#[test]
fn kernel_keeps_the_no_std_boundary() {
    let source = source::kernel_source().expect("the kernel crate root must be readable");
    assert_that!(source::kernel_source_violations(&source), is_empty());
}

/// VO-6 non-vacuity: comments and literals cannot stand in for attributes.
#[rstest]
#[case::line_comment(concat!(
    "// The crate is #![no_std] and denies clippy::std_instead_of_core.\n",
    "//! The alloc lint is clippy::alloc_instead_of_core.\n",
    "#![allow(dead_code)]\n"
))]
#[case::block_comment(concat!(
    "/*\n#![no_std]\nclippy::std_instead_of_core\n",
    "clippy::alloc_instead_of_core\n*/\n",
    "#![allow(dead_code)]\n"
))]
#[case::string_literals(concat!(
    "const DOC: &str = \"#![no_std] extern crate alloc\";\n",
    "const RAW: &str = r#\"clippy::std_instead_of_core\"#;\n",
    "const NESTED: &str = r##\"clippy::alloc_instead_of_core\"##;\n"
))]
fn comments_and_literals_cannot_satisfy_the_kernel_boundary(#[case] source: &str) {
    let violations = source::kernel_source_violations(source).join("; ");
    for expected in [
        "must declare #![no_std]",
        "must deny clippy::std_instead_of_core",
        "must deny clippy::alloc_instead_of_core",
    ] {
        assert_that!(violations.as_str(), contains_substring(expected));
    }
    assert_that!(
        violations.as_str(),
        not(contains_substring("must not contain extern crate alloc"))
    );
}

/// VO-6 non-vacuity: a lint name must sit in an effective `deny`.
#[rstest]
#[case::allow_only(
    concat!(
        "#![no_std]\n",
        "#![allow(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    ),
    "the kernel crate root must deny clippy::std_instead_of_core; the kernel crate root must deny clippy::alloc_instead_of_core"
)]
#[case::warn_only(
    concat!(
        "#![no_std]\n",
        "#![warn(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    ),
    "the kernel crate root must deny clippy::std_instead_of_core; the kernel crate root must deny clippy::alloc_instead_of_core"
)]
#[case::deny_then_allow(
    concat!(
        "#![no_std]\n",
        "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n",
        "#![allow(clippy::std_instead_of_core)]\n"
    ),
    "the kernel crate root must deny clippy::std_instead_of_core"
)]
fn lint_mentions_outside_a_deny_are_reported(#[case] source: &str, #[case] expected: &str) {
    assert_eq!(
        source::kernel_source_violations(source).join("; "),
        expected,
        "only a final deny or forbid may satisfy the kernel lint boundary"
    );
}

/// VO-6 non-vacuity: a real allocation declaration is still reported.
#[rstest]
#[case::plain("extern crate alloc;")]
#[case::interleaved_comment("extern /* keep */ crate alloc;")]
fn real_alloc_declarations_are_reported(#[case] source: &str) {
    assert_that!(
        source::kernel_source_violations(source).join("; ").as_str(),
        contains_substring("must not contain extern crate alloc")
    );
}

/// VO-6 control: a content quote inside a raw string must not hide the root.
///
/// `r#"x""#` holds a bare `"` before its terminator. A scanner that consumed
/// that quote while probing the terminator would swallow the crate attributes
/// and report a valid kernel as missing its boundary.
#[test]
fn raw_string_content_quotes_do_not_hide_the_kernel_attributes() {
    let source = concat!(
        "#![doc = r#\"x\"\"#]\n",
        "#![no_std]\n",
        "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    );
    assert_that!(
        source::kernel_source_violations(source),
        is_empty(),
        "the crate root after a raw-string content quote must still be read"
    );
}

/// VO-6 control: the real attribute set passes the code-only check.
#[test]
fn kernel_boundary_accepts_the_real_attribute_set() {
    let source = concat!(
        "//! Kernel crate root that mentions #![no_std] in prose.\n",
        "#![no_std]\n",
        "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    );
    assert_that!(source::kernel_source_violations(source), is_empty());
}
