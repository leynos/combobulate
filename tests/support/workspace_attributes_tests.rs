//! Scan contracts for the attribute reader.
//!
//! Each case is a shape the compiler reads one way and a substring search
//! would read another, so a scan that regressed to searching would fail here
//! rather than only in the kernel check.

use rstest::rstest;

use super::{
    attributes::{Attribute, Scope, attributes, final_lint_level, gates_a_function},
    scanner::Code,
};

/// A lint list may carry a `reason`, which is not a lint name.
#[test]
fn reason_clauses_are_not_lint_names() {
    let code = Code::stripped("#![deny(clippy::std_instead_of_core, reason = \"x\")]".to_owned());
    let split = attributes(&code, Scope::Inner)
        .first()
        .and_then(Attribute::split)
        .expect("a lint attribute must split into a level and a list");
    assert_eq!(
        split.name, "deny",
        "the level is the text before the parenthesis"
    );
    assert!(
        split.lints().eq(["clippy::std_instead_of_core"]),
        "the reason clause must not be read as a lint, got {:?}",
        split.list
    );
}

/// Inner and outer attributes are collected by the scope asked for.
#[rstest]
#[case::inner_only(Scope::Inner, 1)]
#[case::all_attributes(Scope::All, 2)]
fn scope_selects_inner_attributes_only(#[case] scope: Scope, #[case] expected: usize) {
    let code = Code::stripped("#![no_std] fn probe() {} #[cfg(kani)]".to_owned());
    assert_eq!(
        attributes(&code, scope).len(),
        expected,
        "the inner scope must not collect outer attributes"
    );
}

/// An inner attribute inside a module is not a crate attribute.
///
/// `#![allow(...)]` written in `mod tests { ... }` applies to that module.
/// Collecting it as crate-level would let a submodule's allowance stand in
/// for the root's, which is the substitution the kernel boundary exists to
/// reject.
#[test]
fn a_nested_modules_inner_attribute_is_not_crate_level() {
    let code = Code::stripped(
        concat!(
            "#![no_std]\n",
            "mod tests {\n",
            "    #![allow(clippy::std_instead_of_core)]\n",
            "}\n"
        )
        .to_owned(),
    );
    let found = attributes(&code, Scope::Inner);
    let bodies: Vec<&str> = found.iter().map(|attribute| attribute.body).collect();
    assert_eq!(
        bodies,
        vec!["no_std"],
        "only the crate-level attribute may be collected, got {bodies:?}"
    );
}

/// `Scope::All` still sees an inner attribute inside a module.
///
/// The depth restriction exists for the crate-level lookup, which is
/// `Scope::Inner`. The per-file kernel rule uses `Scope::All` and forbids a
/// lint setting anywhere in a kernel file, so skipping a nested attribute
/// there would let `mod m { #![allow(clippy::std_instead_of_core)] }`
/// through.
#[test]
fn the_all_scope_sees_a_nested_modules_inner_attribute() {
    let code = Code::stripped(
        concat!(
            "#![no_std]\n",
            "mod m {\n",
            "    #![allow(clippy::std_instead_of_core)]\n",
            "}\n"
        )
        .to_owned(),
    );
    let bodies: Vec<&str> = attributes(&code, Scope::All)
        .iter()
        .map(|attribute| attribute.body)
        .collect();
    assert!(
        bodies
            .iter()
            .any(|body| body.contains("std_instead_of_core")),
        "the all scope must see the nested allowance, got {bodies:?}"
    );
}

/// An attribute's body is compared without its spacing.
#[test]
fn spacing_does_not_change_an_attributes_shape() {
    let code = Code::stripped("#[cfg( verus_keep_ghost )]".to_owned());
    let scanned = attributes(&code, Scope::All);
    let [attribute] = scanned.as_slice() else {
        panic!("one attribute in the source must be one attribute in the scan");
    };
    assert_eq!(
        attribute.normalised(),
        "cfg(verus_keep_ghost)",
        "a spaced attribute must compare equal to its tight spelling"
    );
}

/// A `fn` is found through the attributes and qualifiers before it.
#[rstest]
#[case::plain("fn copy() {}", true)]
#[case::qualified("pub const fn copy() -> usize { 0 }", true)]
#[case::attribute_stack("#[allow(dead_code)]\n#[verifier::external_body]\nfn copy() {}", true)]
#[case::use_item("use vstd::prelude::*;", false)]
#[case::module_item("mod witness { pub const N: usize = 1; }", false)]
#[case::constant("pub const LIMIT: usize = 1;", false)]
fn the_item_after_an_attribute_is_classified(#[case] item: &str, #[case] expected: bool) {
    assert_eq!(
        gates_a_function(&Code::stripped(item.to_owned()), 0),
        expected,
        "the scan must classify {item:?} by the item it opens"
    );
}

/// The last crate-level level wins, as the compiler reads it.
#[test]
fn a_later_allow_overrides_an_earlier_deny() {
    let code = Code::stripped(
        concat!(
            "#![deny(clippy::std_instead_of_core)]\n",
            "#![allow(clippy::std_instead_of_core)]\n"
        )
        .to_owned(),
    );
    assert!(
        matches!(
            final_lint_level(&code, "clippy::std_instead_of_core"),
            Some(super::LintLevel::Allow)
        ),
        "the last level a compiler sees is the effective one"
    );
}
