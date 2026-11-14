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

impl Attribute<'_> {
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
}

/// Collects the attributes in `code` that fall within `scope`.
pub(super) fn attributes(code: &str, scope: Scope) -> Vec<Attribute<'_>> {
    let mut found = Vec::new();
    let mut index = 0;
    while let Some(rest) = code.get(index..) {
        let Some((offset, opener, is_inner)) = next_attribute(rest, scope) else {
            break;
        };
        let start = index + offset + opener;
        let Some(tail) = code.get(start..) else {
            break;
        };
        let Some(end) = matching_bracket(tail) else {
            break;
        };
        let Some(body) = tail.get(..end) else {
            break;
        };
        found.push(Attribute {
            body: body.trim(),
            end: start + end + 1,
            is_inner,
        });
        index = start + end + 1;
    }
    found
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
pub(super) fn final_lint_level(code: &str, lint: &str) -> Option<LintLevel> {
    attributes(code, Scope::Inner)
        .iter()
        .filter_map(|attribute| split_attribute(attribute.body))
        .filter_map(|(name, body)| parse_lint_level(name).map(|level| (level, body)))
        .rfind(|(_, body)| lint_list(body).any(|item| item == lint))
        .map(|(level, _)| level)
}

/// Splits `deny(a, b)` into its level name and its parenthesized list.
pub(super) fn split_attribute(attribute: &str) -> Option<(&str, &str)> {
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
pub(super) fn lint_list(body: &str) -> impl Iterator<Item = &str> {
    body.split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty() && !item.contains('='))
}

/// Reports whether the item after `from` is a function definition.
///
/// The item's head is read token by token, so any stack of further attributes
/// is skipped first and a qualifier such as `pub const` is walked past. A
/// `{`, `;` or `=` before the `fn` token means the item is something else — a
/// module, a use declaration, or a constant — and stops the walk.
pub(super) fn gates_a_function(code: &str, from: usize) -> bool {
    let mut rest = code.get(from..).unwrap_or_default().trim_start();
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

    use super::{Scope, attributes, final_lint_level, gates_a_function, split_attribute};

    /// A lint list may carry a `reason`, which is not a lint name.
    #[test]
    fn reason_clauses_are_not_lint_names() {
        let (name, list) = split_attribute("deny(clippy::std_instead_of_core, reason = \"x\")")
            .expect("a lint attribute must split into a level and a list");
        assert_eq!(name, "deny", "the level is the text before the parenthesis");
        assert!(
            super::lint_list(list).eq(["clippy::std_instead_of_core"]),
            "the reason clause must not be read as a lint, got {list:?}"
        );
    }

    /// Inner and outer attributes are collected by the scope asked for.
    #[rstest]
    #[case::inner_only(Scope::Inner, 1)]
    #[case::all_attributes(Scope::All, 2)]
    fn scope_selects_inner_attributes_only(#[case] scope: Scope, #[case] expected: usize) {
        let code = "#![no_std] fn probe() {} #[cfg(kani)]";
        assert_eq!(
            attributes(code, scope).len(),
            expected,
            "the inner scope must not collect outer attributes"
        );
    }

    /// An attribute's body is compared without its spacing.
    #[test]
    fn spacing_does_not_change_an_attributes_shape() {
        let code = "#[cfg( verus_keep_ghost )]";
        let scanned = attributes(code, Scope::All);
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
            gates_a_function(item, 0),
            expected,
            "the scan must classify {item:?} by the item it opens"
        );
    }

    /// The last crate-level level wins, as the compiler reads it.
    #[test]
    fn a_later_allow_overrides_an_earlier_deny() {
        let code = concat!(
            "#![deny(clippy::std_instead_of_core)]\n",
            "#![allow(clippy::std_instead_of_core)]\n"
        );
        assert!(
            matches!(
                final_lint_level(code, "clippy::std_instead_of_core"),
                Some(super::LintLevel::Allow)
            ),
            "the last level a compiler sees is the effective one"
        );
    }
}
