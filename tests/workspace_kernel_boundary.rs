//! The kernel's `#![no_std]` and one-executable-body boundary, from source.
//!
//! VO-6 says the kernel crate root keeps `#![no_std]` and denies the two lints
//! that keep allocation usage honest. That is a property of the source text, so
//! it is checked by scanning the source rather than by compiling it.
//!
//! EP-M5 widens the scan from the crate root to every kernel source file. The
//! crate attributes stay a root rule, because a submodule that restated them
//! would not make the crate any stricter. The one-executable-body rules apply
//! to every file, because an allocation-free body replaced behind a verifier
//! `cfg` is exactly as wrong in a submodule as in the root, and the root-only
//! scan could not see it. The seeded tree under `tests/fixtures/kernel-source/`
//! proves the difference: its root is clean and its operation module breaks
//! every rule, so a scanner that stopped at the root would report nothing.
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

use source::KernelFile;

/// The live kernel's source directory, which the widened scan walks.
const KERNEL_SOURCE: &str = "crates/combobulate-kernel/src";

/// The seeded tree whose root is clean and whose module is not.
const SEEDED_TREE: &str = "tests/fixtures/kernel-source";

/// A path constant in the form the walk takes.
fn tree(path: &str) -> &camino::Utf8Path { camino::Utf8Path::new(path) }

/// One in-memory file, for the cases that do not need a directory.
fn file(path: &str, source: &str) -> KernelFile {
    KernelFile {
        path: camino::Utf8PathBuf::from(path),
        source: source.to_owned(),
    }
}

/// Commits under `lib.rs` that keep a kernel root valid.
const CLEAN_ROOT: &str = concat!(
    "#![no_std]\n",
    "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
);

/// VO-6: the kernel keeps `#![no_std]` and its core-only lint boundary.
#[test]
fn kernel_keeps_the_no_std_boundary() {
    let source = source::kernel_source().expect("the kernel crate root must be readable");
    assert_that!(source::kernel_source_violations(&source), is_empty());
}

/// VO-6 widened: every live kernel file passes every substitute-body rule.
#[test]
fn every_kernel_file_keeps_one_executable_body() {
    let files =
        source::sources_under(tree(KERNEL_SOURCE)).expect("the kernel source must be readable");
    assert!(
        files
            .iter()
            .any(|file| file.path == camino::Utf8Path::new("elementwise_add.rs")),
        "the walk must reach the kernel's operation module, read {:?}",
        files.iter().map(|file| &file.path).collect::<Vec<_>>()
    );
    let violations = source::kernel_tree_violations(&files);
    assert!(
        violations.is_empty(),
        "the kernel must report no substitute-body violation, got {violations:#?}"
    );
}

/// VO-6 non-vacuity: the seeded module is reported, its clean root is not.
///
/// This is the case the old root-only scan failed. The fixture's `lib.rs`
/// declares both crate attributes, so every violation below belongs to
/// `elementwise_add.rs`; a scan that reported the root instead would fail the
/// last assertion.
#[test]
fn the_seeded_submodule_is_not_missed() {
    let files = source::sources_under(tree(SEEDED_TREE)).expect("the seeded tree must be readable");
    let violations = source::kernel_tree_violations(&files).join("\n");
    for expected in [
        "elementwise_add.rs: must not contain extern crate alloc",
        "elementwise_add.rs: must not contain extern crate std",
        "elementwise_add.rs: must not contain cfg(not(verus_keep_ghost))",
        "elementwise_add.rs: must not put cfg(verus_keep_ghost) on a fn item",
        "elementwise_add.rs: must not put cfg(kani) on a fn item",
        "elementwise_add.rs: must not allow clippy::std_instead_of_core",
        "elementwise_add.rs: must not expect clippy::alloc_instead_of_core",
    ] {
        assert_that!(violations.as_str(), contains_substring(expected));
    }
    assert_that!(
        violations.as_str(),
        not(contains_substring("lib.rs:"))
            .and(not(contains_substring("must declare #![no_std]")))
            .and(not(contains_substring("must deny clippy::")))
    );
}

/// VO-6 non-vacuity: a tree without a crate root is refused, not passed.
#[test]
fn a_tree_without_its_crate_root_is_reported() {
    let files = [file("elementwise_add.rs", "")];
    assert_that!(
        source::kernel_tree_violations(&files),
        contains(contains_substring("must contain its lib.rs crate root"))
    );
}

/// A submodule's `cfg` attribute over a non-function item is allowed.
///
/// ADR-0010's single-root pattern needs a verifier-only `use` and
/// `cfg_attr`-gated specification attributes in the operation module, so the
/// rule must reject only a gated function. Rejecting every `cfg` would forbid
/// the pattern the ADR mandates.
#[rstest]
#[case::verus_use("#[cfg(verus_keep_ghost)]\nuse vstd::prelude::*;")]
#[case::kani_module("#[cfg(kani)]\nmod witness { pub const N: usize = 1; }")]
#[case::const_item("#[cfg(kani)]\npub const LIMIT: usize = 1;")]
#[case::cfg_attr_on_function("#[cfg_attr(kani, allow(dead_code))]\nfn probe() {}")]
fn non_function_items_may_be_gated(#[case] source: &str) {
    assert_that!(
        source::kernel_tree_violations(&[file("lib.rs", CLEAN_ROOT), file("operation.rs", source)]),
        is_empty(),
        "gating a non-function item is the ADR-0010 pattern, not a substitute body"
    );
}

/// A gated function is reported even when other attributes precede it.
///
/// The item's head carries more than one attribute in real code, so the walk
/// must skip the rest of the stack before deciding what the gated attribute
/// applies to. A `pub const fn` and an `unsafe fn` are functions too.
#[rstest]
#[case::attribute_stack(
    "#[cfg(verus_keep_ghost)]\n#[allow(dead_code)]\n#[verifier::external_body]\npub fn copy() {}"
)]
#[case::public_const_function("#[cfg(verus_keep_ghost)]\npub const fn copy() -> usize { 0 }")]
#[case::unsafe_function("#[cfg(verus_keep_ghost)]\nunsafe fn copy() {}")]
#[case::spaced_attribute("#[cfg( verus_keep_ghost )]\nfn copy() {}")]
fn gated_functions_are_reported_through_their_attribute_stack(#[case] source: &str) {
    assert_that!(
        source::kernel_tree_violations(&[file("lib.rs", CLEAN_ROOT), file("operation.rs", source)]),
        contains(contains_substring(
            "must not put cfg(verus_keep_ghost) on a fn item"
        ))
    );
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
///
/// A weakening attribute is reported twice on the root, and that is the
/// intended reading: the root rule says its `deny` is not effective, and the
/// per-file rule says a kernel file may not allow, warn about, or expect one of
/// the two lints at all. The second message is what a submodule gets, which is
/// where the root rule cannot see it.
#[rstest]
#[case::allow_only(
    concat!(
        "#![no_std]\n",
        "#![allow(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    ),
    concat!(
        "the kernel crate root must deny clippy::std_instead_of_core; ",
        "the kernel crate root must deny clippy::alloc_instead_of_core; ",
        "must not allow clippy::std_instead_of_core; ",
        "must not allow clippy::alloc_instead_of_core"
    )
)]
#[case::warn_only(
    concat!(
        "#![no_std]\n",
        "#![warn(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
    ),
    concat!(
        "the kernel crate root must deny clippy::std_instead_of_core; ",
        "the kernel crate root must deny clippy::alloc_instead_of_core; ",
        "must not warn clippy::std_instead_of_core; ",
        "must not warn clippy::alloc_instead_of_core"
    )
)]
#[case::deny_then_allow(
    concat!(
        "#![no_std]\n",
        "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n",
        "#![allow(clippy::std_instead_of_core)]\n"
    ),
    concat!(
        "the kernel crate root must deny clippy::std_instead_of_core; ",
        "must not allow clippy::std_instead_of_core"
    )
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
