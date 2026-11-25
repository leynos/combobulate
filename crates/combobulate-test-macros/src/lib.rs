//! Test-only attribute macros that suppress lints triggered by macro expansion.
//!
//! A `#[fixture]` from `rstest` expands a single-expression body into a nested
//! block. Under `fn_single_line = true` in `rustfmt.toml` that expansion is
//! reported as `unused_braces`, which the workspace denies, so every fixture
//! with an expression body would need the same two attributes written by hand.
//!
//! [`allow_fixture_expansion_lints`] writes them once, at the macro boundary,
//! so the suppression is stated in one place and carries its own reason. It is
//! the estate-approved answer to this expansion; the alternative — a blanket
//! allowance or a per-fixture copy — either hides real unused braces or drifts
//! as fixtures are added.
//!
//! This crate is a test dependency only. It is not re-exported by the facade
//! and adds nothing to the shipped dependency closure.

use proc_macro::TokenStream;
use quote::quote;
use syn::{Item, parse_macro_input};

/// Allows the `unused_braces` lint for a fixture function.
///
/// Apply it above `#[rstest::fixture]`. The expansion keeps the item as
/// written and adds two attributes: an `allow` for `unused_braces`, and an
/// `expect` for `clippy::allow_attributes`, because the workspace denies a bare
/// `allow` and requires the reason it carries.
///
/// The `expect` is deliberately **not** behind `cfg(clippy)`. Clippy reports
/// that wrapper as `unnecessary_clippy_cfg` — "no need to put clippy lints
/// behind a `clippy` cfg" — which the workspace denies, so a `cfg_attr` here
/// would fail the lint gate it exists to satisfy. This repository therefore
/// emits the plain `expect`; the two spellings differ from the upstream
/// `weaver-test-macros` for exactly this reason, and the effect is the same.
///
/// The attribute passes the item through unchanged, so the example below is an
/// ordinary function: what it demonstrates is that the expansion compiles and
/// that the item keeps its name and body.
///
/// ```
/// use combobulate_test_macros::allow_fixture_expansion_lints;
///
/// #[allow_fixture_expansion_lints]
/// fn world() -> u8 { 0 }
///
/// assert_eq!(world(), 0, "the item survives the expansion unchanged");
/// ```
#[proc_macro_attribute]
pub fn allow_fixture_expansion_lints(_attribute: TokenStream, item: TokenStream) -> TokenStream {
    let parsed_item = parse_macro_input!(item as Item);

    quote! {
        #[allow(
            unused_braces,
            reason = "fixture macro expansion triggers unused-braces on expression bodies"
        )]
        #[expect(
            clippy::allow_attributes,
            reason = "needed to allow unused_braces for fixture macro expansion"
        )]
        #parsed_item
    }
    .into()
}
