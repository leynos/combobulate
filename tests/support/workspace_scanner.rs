//! Comment and literal scanning for the kernel source checks.
//!
//! The kernel boundary is a property of attributes the compiler acts on, so
//! the checks read code with comments and literals removed. That removal has
//! to follow Rust's own lexical rules closely enough not to edit the code it
//! keeps: a character literal holding a double quote must not start a string
//! skip, and a lifetime tick must not be mistaken for a character literal.

use std::{iter::Peekable, str::Chars};

/// Removes comments and literals, leaving their surrounding tokens separated.
pub(super) fn strip_comments_and_literals(source: &str) -> String {
    let mut code = String::with_capacity(source.len());
    let mut chars = source.chars().peekable();
    while let Some(ch) = chars.next() {
        match ch {
            '/' if chars.peek() == Some(&'/') => consume_line_comment(&mut chars, &mut code),
            '/' if chars.peek() == Some(&'*') => consume_block_comment(&mut chars, &mut code),
            'r' => consume_raw_string_or_keep(ch, &mut chars, &mut code),
            '"' => skip_quoted_string(&mut chars),
            '\'' => keep_lifetime_tick(ch, &mut chars, &mut code),
            _ => code.push(ch),
        }
    }
    code
}

/// Drops a line comment after its opening slash, leaving the newline behind.
fn consume_line_comment(chars: &mut Peekable<Chars<'_>>, code: &mut String) {
    chars.next();
    code.push('\n');
    skip_to_newline(chars);
}

/// Replaces a block comment with a space so the tokens either side stay apart.
fn consume_block_comment(chars: &mut Peekable<Chars<'_>>, code: &mut String) {
    chars.next();
    code.push(' ');
    skip_block_comment(chars);
}

/// Skips a raw string introduced by `r`, or keeps the `r` as ordinary code.
fn consume_raw_string_or_keep(ch: char, chars: &mut Peekable<Chars<'_>>, code: &mut String) {
    match raw_string_hashes(chars) {
        Some(hashes) => skip_raw_string(chars, hashes),
        None => code.push(ch),
    }
}

/// Keeps an apostrophe that opens no literal, because it starts a lifetime.
///
/// Dropping it would leave `&'a str` reading as `&a str`, which is still
/// parseable text but no longer faithful to the source the checks describe.
fn keep_lifetime_tick(ch: char, chars: &mut Peekable<Chars<'_>>, code: &mut String) {
    if !skip_char_literal(chars) {
        code.push(ch);
    }
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
///
/// The `#` run is probed on a clone and committed only when it matches. A raw
/// string may contain a bare `"` before its terminator (as in `r#"x""#`); a
/// probe that consumed that quote would hide the real terminator and swallow
/// the rest of the file.
fn raw_string_closes(chars: &mut Peekable<Chars<'_>>, hashes: usize) -> bool {
    let mut lookahead = chars.clone();
    if (0..hashes).all(|_| lookahead.next() == Some('#')) {
        *chars = lookahead;
        true
    } else {
        false
    }
}

/// Skips a character literal and reports whether one was consumed.
///
/// A lifetime (`'a`, `'_`, `'static`) has no closing quote, so treating every
/// `'` as a literal opener would swallow the rest of the file. A literal is
/// recognised by its closing quote, and every escaped form has to be consumed
/// before that quote is sought: `'\''`, `'\\'`, `'\n'`, `'\u{..}'`, and the
/// fixed-width hexadecimal escape `'\x22'` (which also covers the byte literal
/// form `b'\x22'`, since the `b` is already in the code stream). Consuming only
/// the backslash and the escape letter leaves the hex digits behind, so the
/// closing quote is never reached and the literal stays in the stream — where
/// the very quote it holds can start a string skip. A literal holding a double
/// quote (`'"'`) must not start that skip.
///
/// ```text
/// strip_comments_and_literals("'\"' extern crate alloc;")
/// // consumes the literal and keeps the declaration
/// strip_comments_and_literals("&'a str")
/// // consumes nothing, so the lifetime tick stays in the code
/// ```
fn skip_char_literal(chars: &mut Peekable<Chars<'_>>) -> bool {
    let mut lookahead = chars.clone();
    let closes = match lookahead.next() {
        Some('\\') => {
            match lookahead.next() {
                Some('u') if lookahead.peek() == Some(&'{') => skip_unicode_escape(&mut lookahead),
                // `\x` is the only fixed-width escape that carries payload
                // digits; every other simple escape is one character.
                Some('x') => skip_fixed_width_escape(&mut lookahead, 2),
                Some(_) => {}
                None => return false,
            }
            lookahead.next() == Some('\'')
        }
        Some(_) => {
            let closes = lookahead.peek() == Some(&'\'');
            if closes {
                lookahead.next();
            }
            closes
        }
        None => false,
    };
    if closes {
        *chars = lookahead;
    }
    closes
}

/// Consumes the fixed number of payload digits a `\x`-style escape carries.
fn skip_fixed_width_escape(chars: &mut Peekable<Chars<'_>>, digits: usize) {
    for _ in 0..digits {
        if chars.peek().is_some_and(char::is_ascii_hexdigit) {
            chars.next();
        }
    }
}

/// Consumes a `\u{..}` escape body, leaving the position after its brace.
fn skip_unicode_escape(chars: &mut Peekable<Chars<'_>>) { chars.by_ref().any(|ch| ch == '}'); }

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

#[cfg(test)]
mod tests {
    //! Literal-aware scanning contracts for the kernel boundary.
    //!
    //! The scanner reads Rust text with comments and literals stripped. A
    //! character literal holding a double quote must not start a string skip,
    //! and a lifetime tick must not be mistaken for a character literal.
    //! Either mistake would hide the attributes or the allocation declaration
    //! that follows.

    use googletest::prelude::*;
    use rstest::rstest;

    use super::{super::kernel_source_violations, strip_comments_and_literals};

    /// VO-6 non-vacuity: a literal before the declaration must not hide it.
    #[rstest]
    #[case::double_quote_literal(r#"const QUOTE: char = '"'; extern crate alloc;"#)]
    #[case::escaped_double_quote_literal(r#"const QUOTE: char = '\"'; extern crate alloc;"#)]
    #[case::hexadecimal_double_quote_literal(r"const QUOTE: char = '\x22'; extern crate alloc;")]
    #[case::hexadecimal_byte_literal(r"const QUOTE: u8 = b'\x22'; extern crate alloc;")]
    #[case::adjacent_literals(r#"const CHECK: bool = '\x22'<'"'; extern crate alloc;"#)]
    #[case::lifetime(r"fn borrow<'a>(value: &'a str) -> &'a str { value } extern crate alloc;")]
    fn character_literals_do_not_hide_alloc_declarations(#[case] source_text: &str) {
        assert_that!(
            kernel_source_violations(source_text).join("; ").as_str(),
            contains_substring("must not contain extern crate alloc")
        );
    }

    /// VO-6 control: a character literal must not hide the attributes after it.
    ///
    /// The literal `'"'` holds the same byte that opens a string. A scanner
    /// that started a string skip at that quote would consume the crate
    /// attributes and report a valid kernel as missing its boundary.
    #[test]
    fn character_literals_do_not_hide_the_kernel_attributes() {
        let source_text = concat!(
            "const QUOTE: char = '\"';\n",
            "const ESCAPED: char = '\\'';\n",
            "const HEXADECIMAL: char = '\\x22';\n",
            "#![no_std]\n",
            "#![deny(clippy::std_instead_of_core, clippy::alloc_instead_of_core)]\n"
        );
        assert_that!(
            kernel_source_violations(source_text),
            is_empty(),
            "the crate attributes after a character literal must still be read"
        );
    }

    /// VO-6 control: a lifetime tick must survive into the scanned code.
    ///
    /// Consuming nothing while dropping the apostrophe would leave the code
    /// readable but altered, so the token check has to see the tick. Lifetimes
    /// are the only construct where a `'` closes no literal, so they are the
    /// one place a silent edit would go unnoticed by the violation checks.
    #[rstest]
    #[case::borrowed_parameter(r"fn borrow<'a>(value: &'a str) {}")]
    #[case::static_bound(r"fn boxed() -> Box<dyn Send + 'static> { todo!() }")]
    #[case::placeholder(r"let _: &'_ str = value;")]
    fn lifetime_ticks_survive_the_literal_scan(#[case] source_text: &str) {
        assert_that!(
            strip_comments_and_literals(source_text).as_str(),
            contains_substring("'"),
            "a lifetime tick must not be dropped from the scanned code"
        );
    }
}
