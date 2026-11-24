//! Attribute scanning for the kernel source checks.
//!
//! The kernel rules are stated over attributes the compiler acts on: the lint
//! levels a root declares, and the verifier `cfg`s a file may or may not put on
//! a function. Reading them needs a real scan rather than a substring search,
//! because `#![deny(...)]` and `#[allow(...)]` differ by one character and a
//! `cfg` applies to whatever item follows it, not to the file.
//!
//! The module is a child of the source checks so its unit tests can sit beside
//! it, and it works only on text the sibling scanner has already stripped of
//! comments and literals.

use super::scanner::Code;

/// A crate-level lint level, in the order attributes can override each other.
#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum LintLevel {
    Allow,
    Warn,
    Deny,
    Forbid,
}

/// Which attributes a scan collects.
#[derive(Clone, Copy)]
pub(super) enum Scope {
    /// Only inner attributes, `#![...]`, which a root or module sets.
    Inner,
    /// Every attribute, inner or outer.
    All,
}

/// One attribute found in stripped code.
pub(super) struct Attribute<'a> {
    /// The attribute's inner text, without its `#[]` delimiters.
    pub(super) body: &'a str,
    /// The byte offset just past the attribute's closing bracket.
    pub(super) end: usize,
    /// Whether the attribute is inner, written `#![...]`.
    pub(super) is_inner: bool,
}

impl<'a> Attribute<'a> {
    /// The attribute's body with every space removed.
    ///
    /// An attribute may be written `#[cfg( kani )]`, and the compiler reads it
    /// the same way as `#[cfg(kani)]`, so comparing its shape cannot depend on
    /// spacing.
    pub(super) fn normalised(&self) -> String {
        self.body
            .chars()
            .filter(|character| !character.is_whitespace())
            .collect()
    }

    /// Split this attribute into its level name and its list.
    ///
    /// The body belongs to the attribute, so reading the two halves here keeps
    /// the parse with the data it parses rather than with a free function that
    /// takes any string.
    pub(super) fn split(&self) -> Option<Split<'a>> { split_body(self) }
}

/// Split one attribute body into its level name and its list.
///
/// The two halves are only meaningful together — a name without its list
/// cannot decide a lint, and a list without its name cannot decide a level —
/// so a split returns both or neither.
#[derive(Clone, Copy)]
pub(super) struct Split<'a> {
    /// The attribute name, such as `deny`.
    pub(super) name: &'a str,
    /// The text between the parentheses, trimmed.
    pub(super) list: &'a str,
}

/// Split `deny(a, b)` into its level name and its parenthesized list.
///
/// The body is read from the attribute rather than accepted as free text,
/// because an attribute body is the only thing this can correctly split: a
/// caller that handed over some other slice would be parsing a shape no
/// attribute has.
fn split_body<'a>(attribute: &Attribute<'a>) -> Option<Split<'a>> {
    let body = attribute.body;
    let open = body.find('(')?;
    let close = body.rfind(')')?;
    if close <= open {
        return None;
    }
    Some(Split {
        name: body.get(..open)?.trim(),
        list: body.get(open + 1..close)?.trim(),
    })
}

impl<'a> Split<'a> {
    /// Yield the lint names this list sets, skipping `reason = ...` clauses.
    ///
    /// A `reason` clause is not a lint name, so treating the commas naively
    /// would let `reason = "..."` stand in for the lint it documents.
    pub(super) fn lints(self) -> impl Iterator<Item = &'a str> {
        self.list
            .split(',')
            .map(str::trim)
            .filter(|item| !item.is_empty() && !item.contains('='))
    }
}

/// Collects the attributes in `code` that fall within `scope`.
///
/// An inner attribute is crate-level only when it sits outside every brace
/// pair. `#![allow(...)]` written inside `mod tests { ... }` applies to that
/// module, not to the crate, so collecting it would let a submodule's
/// allowance stand in for the root's — the exact substitution the kernel
/// boundary exists to reject.
pub(super) fn attributes(code: &Code, scope: Scope) -> Vec<Attribute<'_>> {
    let text = code.text();
    let mut found = Vec::new();
    let mut index = 0;
    // The brace depth at `index`, carried forward rather than recomputed: a
    // rescan per attribute would make the walk quadratic in the file size.
    let mut depth = 0_usize;
    while let Some(rest) = text.get(index..) {
        let Some((offset, opener, is_inner)) = next_attribute(rest, scope) else {
            break;
        };
        let attribute_at = index + offset;
        depth = advance_depth(text, index, attribute_at, depth);
        let start = attribute_at + opener;
        let Some(tail) = text.get(start..) else {
            break;
        };
        let Some(end) = matching_bracket(tail) else {
            break;
        };
        let Some(body) = tail.get(..end) else {
            break;
        };
        if is_inner && depth > 0 && matches!(scope, Scope::Inner) {
            // The depth restriction serves the crate-level lookup: an inner
            // attribute inside a module or a function body is not a crate
            // attribute, so `Scope::Inner` skips it. `Scope::All` exists to
            // find every attribute a file carries — the per-file kernel rule
            // forbids a lint setting anywhere in a kernel file — so it must
            // still see a nested one. The walk advances past the attribute in
            // both cases, so the depth it carries stays aligned with `index`.
            index = start + end + 1;
            continue;
        }
        found.push(Attribute {
            body: body.trim(),
            end: start + end + 1,
            is_inner,
        });
        index = start + end + 1;
    }
    found
}

/// Returns the brace depth after reading `text[from..to]`.
///
/// The scan is over stripped code, so a brace in a comment or a string has
/// already been removed. Only `{` and `}` are counted: a `(` or `[` cannot
/// open a module body, and counting them would make a signature's brackets
/// look like nesting.
fn advance_depth(text: &str, from: usize, to: usize, start: usize) -> usize {
    text.get(from..to)
        .unwrap_or_default()
        .chars()
        .fold(start, |depth, character| match character {
            '{' => depth + 1,
            '}' => depth.saturating_sub(1),
            _ => depth,
        })
}

/// Returns the next attribute's offset, opener length, and inner-ness.
///
/// `#![` does not contain `#[`, so the two searches cannot find one opener at
/// two places; taking the earlier match keeps the scan in source order.
fn next_attribute(rest: &str, scope: Scope) -> Option<(usize, usize, bool)> {
    let inner = rest.find("#![").map(|at| (at, 3, true));
    let outer = if matches!(scope, Scope::All) {
        rest.find("#[").map(|at| (at, 2, false))
    } else {
        None
    };
    match (outer, inner) {
        (Some(outer_at), Some(inner_at)) => Some(if inner_at.0 < outer_at.0 {
            inner_at
        } else {
            outer_at
        }),
        (Some(found), None) | (None, Some(found)) => Some(found),
        (None, None) => None,
    }
}

/// Returns the byte offset of the `]` that closes this attribute's bracket.
pub(super) fn matching_bracket(tail: &str) -> Option<usize> {
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

/// Returns the last crate-level level set for `lint`, if any attribute sets one.
///
/// Scanning in source order keeps a later `#![allow(...)]` from being hidden by
/// an earlier `#![deny(...)]`: the last level a compiler sees is the effective
/// one, so a deny that is later allowed does not satisfy the boundary.
pub(super) fn final_lint_level(code: &Code, lint: &str) -> Option<LintLevel> {
    attributes(code, Scope::Inner)
        .iter()
        .filter_map(Attribute::split)
        .filter(|split| split.lints().any(|item| item == lint))
        .filter_map(|split| parse_lint_level(split.name))
        .next_back()
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

/// Reports whether the item after `from` is a function definition.
///
/// The item's head is read token by token, so any stack of further attributes
/// is skipped first and a qualifier such as `pub const` is walked past. A
/// `{`, `;` or `=` before the `fn` token means the item is something else — a
/// module, a use declaration, or a constant — and stops the walk.
pub(super) fn gates_a_function(code: &Code, from: usize) -> bool {
    let mut rest = code.text().get(from..).unwrap_or_default().trim_start();
    while let Some(tail) = rest.strip_prefix("#[") {
        let Some(end) = matching_bracket(tail) else {
            return false;
        };
        rest = tail.get(end..).unwrap_or_default().trim_start();
    }
    is_function_item(rest)
}

/// Reports whether the item text opens a function definition.
fn is_function_item(item: &str) -> bool {
    item.split_whitespace()
        .find_map(|token| match token {
            "fn" => Some(true),
            _ if token.contains(['{', ';', '=']) => Some(false),
            _ => None,
        })
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    //! Scan contracts for the attribute reader.
    //!
    //! Each case is a shape the compiler reads one way and a substring search
    //! would read another, so a scan that regressed to searching would fail
    //! here rather than only in the kernel check.

    use rstest::rstest;

    use super::{Attribute, Code, Scope, attributes, final_lint_level, gates_a_function};

    /// A lint list may carry a `reason`, which is not a lint name.
    #[test]
    fn reason_clauses_are_not_lint_names() {
        let code =
            Code::stripped("#![deny(clippy::std_instead_of_core, reason = \"x\")]".to_owned());
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
}
