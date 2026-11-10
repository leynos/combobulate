"""Prove the trust-audit scanner finds trust, and only where DL-17 says it may (VO-9, VO-10).

The scanner decides whether a record's ``trust_audit`` may claim ``audited``, so
a scanner that under-reports silently blesses a proof that assumed its way past
a hard case, while one that over-reports is at worst a rejected record. These
tests come in three shapes. The cross-product cases pin the rule over every
context a vocabulary word can appear in, so the contexts rather than the words
are what is under test. The property cases state the obligations the rule exists
to serve: inserting trust in code adds exactly that item, and the same text
anywhere the lexer calls trivia adds nothing. The lexical cases pin the
tokenizer forms a Rust source can take.

The repository-scale cases, the module-resolution cases, and the check that
compares the scanner with the seeded corpus live beside this module in
``test_trust_audit_crates.py`` and ``test_trust_audit_check.py``, so each file
stays within the repository's module-length limit.

Examples
--------
>>> item_names('kani::assume(x);')
('assume',)
>>> item_names('// kani::assume(x);')
()
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import (
    KANI_VOCABULARY,
    VERUS_VOCABULARY,
    VOCABULARY,
    TrustAuditError,
    scan,
)
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]


def item_names(text: str, **options) -> tuple[str, ...]:
    """Return the item names one source reports, in source order."""
    return tuple(item.item for item in scan(text, **options).items)


class VocabularyContextCrossProduct(unittest.TestCase):
    """Hold every vocabulary word to the same answer in every lexical context.

    A rule that worked for ``assume`` but not for ``external`` would pass a
    handwritten example per word and still leave a gap. Reading every word
    through every context makes the contexts the thing under test.
    """

    # (label, template, rule). Every template contains `{word}`; the rule says
    # which vocabulary makes that occurrence trust, because the three rules do
    # not admit the same words. A Kani word in a Verus body is not Verus trust,
    # and a Verus word behind `kani::` is not Kani's.
    KANI, VERUS, BOTH, ANY, NONE = 'kani', 'verus', 'both', 'any', 'none'
    CASES: ClassVar[list[tuple[str, str, str]]] = [
        ('kani path', 'kani::{word}(x);', KANI),
        ('kani path in use tree', 'use kani::{{{word}, other}};', BOTH),
        ('verus path in use tree', 'use vstd::{{{word}, other}};', BOTH),
        ('kani path in cfg_attr', '#[cfg_attr(kani, kani::{word}(x))]\nfn f() {{}}', KANI),
        ('verus body', 'verus! {{ fn f() {{ {word}(x); }} }}', VERUS),
        ('verus attribute head', '#[verifier::{word}]\nfn f() {{}}', VERUS),
        ('verus_spec attribute', '#[verus_spec({word})]\nfn f() {{}}', VERUS),
        ('verus inside cfg_attr', '#[cfg_attr(feature = "v", verifier::{word})]\nfn f() {{}}', VERUS),
        ('bare after a trust import', 'use kani::assume;\nfn f() {{ {word}(x); }}', ANY),
        ('line comment', '// kani::{word}(x);', NONE),
        ('block comment', '/* kani::{word}(x); */', NONE),
        ('nested block comment', '/* /* kani::{word}(x); */ */', NONE),
        ('doc comment', '/// kani::{word}(x);\nfn f() {{}}', NONE),
        ('string literal', 'let s = "kani::{word}(x);";', NONE),
        ('raw string literal', 'let s = r#"kani::{word}(x);"#;', NONE),
        ('byte string literal', 'let s = b"kani::{word}(x);";', NONE),
        ('field or method', 'x.{word}();', NONE),
        ('path segment', 'crate::{word}::f();', NONE),
    ]

    def test_cross_product_matches_dl_17(self):
        """Require every word to answer exactly as its context dictates."""
        for word in sorted(VOCABULARY):
            for label, template, rule in self.CASES:
                with self.subTest(word=word, context=label):
                    expected = self._expected(word, rule)
                    self.assertEqual(
                        item_names(template.format(word=word)), expected,
                        f'{word} in {label} must report exactly {expected}',
                    )

    def _expected(self, word: str, rule: str) -> tuple[str, ...]:
        """Resolve one case's expectation for one word.

        A ``use`` tree is read as rule (iii), not as a ``kani::`` path: its
        members sit after ``{`` rather than after ``::``, so every vocabulary
        word in the tree is reported once the file imports from a trust root.
        The bare-import case also reports the import itself, which is a
        ``kani::assume`` path and so satisfies rule (i) whatever word the
        template inserts afterwards.
        """
        if rule == self.KANI:
            reported = word in KANI_VOCABULARY
        elif rule == self.VERUS:
            reported = word in VERUS_VOCABULARY
        elif rule in (self.BOTH, self.ANY):
            reported = word in VOCABULARY
        else:
            reported = False
        prefix = ('assume',) if rule == self.ANY else ()
        return prefix + ((word,) if reported else ())


class RuleThreeBreadth(unittest.TestCase):
    """Pin rule (iii)'s deliberate superset so a later narrowing becomes a decision.

    DL-17's wording names a glob or an alias. A *named* import reaches the same
    bare use, and no other rule covers it, so the scanner reports it too and the
    record must then cover the item. If someone narrows the rule, these cases
    fail and the narrowing has to be argued rather than merely happening.
    """

    def test_named_import_makes_a_bare_use_trust(self):
        """Report both the named import and the bare use it reaches."""
        text = 'use kani::assume;\nfn f() { assume(x > 0); }'
        self.assertEqual(item_names(text), ('assume', 'assume'),
                         'the import and its bare use must both report')

    def test_glob_import_makes_a_bare_use_trust(self):
        """Report a bare vocabulary word after a glob import from a trust root."""
        self.assertEqual(item_names('use vstd::prelude::*;\nfn f() { assume(x); }'),
                         ('assume',), 'a glob import must make the bare use report')
        self.assertEqual(item_names('use verus_builtin::*;\nfn f() { admit(); }'),
                         ('admit',), 'every trust root must trigger rule (iii)')

    def test_import_from_an_ordinary_crate_changes_nothing(self):
        """Leave a bare word alone when the file imports no trust root."""
        self.assertEqual(item_names('use std::mem;\nfn f() { assume(x); }'), (),
                         'an unrelated import must not make a bare word trust')

    def test_extern_crate_makes_a_bare_use_trust(self):
        """Report the bare use after `extern crate kani;`.

        The declaration is the same import ``use kani;`` makes, spelled
        without a ``use``, so it triggers rule (iii) too. A reader that only
        looked for ``use`` described the file as trust-free while a bare
        ``assume`` reached Kani.
        """
        self.assertEqual(item_names('extern crate kani;\nfn f() { assume(x); }'),
                         ('assume',),
                         'an extern crate import must make the bare use report')

    def test_extern_crate_rename_makes_a_qualified_path_trust(self):
        """Report `k::assume` after `extern crate kani as k;`."""
        self.assertEqual(item_names('extern crate kani as k;\nfn f() { k::assume(x); }'),
                         ('assume',),
                         'an extern crate rename must reach rule (i)')

    def test_extern_crate_of_an_ordinary_crate_changes_nothing(self):
        """Leave a bare word alone when the ``extern crate`` is not a trust root."""
        self.assertEqual(item_names('extern crate std;\nfn f() { assume(x); }'), (),
                         'an unrelated extern crate must not make a bare word trust')


class RawIdentifiers(unittest.TestCase):
    """Require a raw identifier to be the name it spells, not a ``#`` and a word.

    Rust lets a keyword be used as a name by prefixing it with ``r#``, and a
    crate can rename an import to one. Lexing ``r#assume`` as ``r``, ``#``,
    ``assume`` leaves a punctuator between ``::`` and the name, so the
    qualified-path rule no longer sees a path and the call is invisible.
    """

    def test_a_raw_identifier_is_the_bare_name_it_spells(self):
        """Require the lexer to hand the matcher the name without its prefix."""
        self.assertEqual([item.item for item in scan('fn f() { kani::r#assume(x); }').items],
                         ['assume'],
                         'a raw identifier must report as the name it spells')

    def test_a_raw_identifier_keeps_its_own_position(self):
        """Require the column to locate the token the author wrote.

        The prefix is two characters, and pointing at the name after it would
        name a column the source does not put that word at.
        """
        item, = scan('fn f() { kani::r#assume(x); }').items
        self.assertEqual((item.line, item.column), (1, 16),
                         'a raw identifier must report where it starts')


class QualifiedPathRule(unittest.TestCase):
    """Require a ``kani::`` or ``vstd::`` path to report on its own (rule i)."""

    def test_an_ordinary_qualified_path_reports(self):
        """Keep the plain form working, so the raw case is not a swap for it."""
        self.assertEqual(item_names('fn f() { kani::assume(x); }'), ('assume',),
                         'a qualified trust path must report without any import')


class NestedRegionMatching(unittest.TestCase):
    """Close a ``verus!`` body at its own brace, however deeply it nests.

    The region is found by bracketing, and bracketing is the one part of the
    scan that can fail in both directions at once: closing too early loses
    every trust word after the first inner block, and closing too late reports
    ordinary code the region never covered. Both are silent — the audit simply
    reports a different list — so the depth count has to be exact rather than
    merely close enough for unnested examples.
    """

    def test_a_trust_word_after_a_nested_block_is_still_inside_the_body(self):
        """Require the region to survive an inner block before the trust word.

        This is the case a depth count reset to one gets wrong: the inner block
        closes the region, and ``assume`` then falls outside it and is lost.
        """
        self.assertEqual(item_names('verus! { fn f() { if x { } } fn g() { assume(q); } }'),
                         ('assume',),
                         'a nested block must not close the verus! body')

    def test_a_trust_word_after_two_nested_blocks_is_still_inside_the_body(self):
        """Require the depth count to hold at three levels, not just two."""
        self.assertEqual(item_names('verus! { fn f() { if x { if y { } } } assume(q); }'),
                         ('assume',),
                         'two nested blocks must not close the verus! body')

    def test_a_trust_word_outside_a_closed_body_is_not_reported(self):
        """Require the region to end where the body really does.

        The converse failure: a region left open reports an ordinary word after
        the macro as Verus trust, which the record would then have to cover.
        """
        self.assertEqual(item_names('verus! { fn f() { } }\nfn g() { assume(q); }'), (),
                         'code after a closed verus! body must stay outside it')

    def test_an_unclosed_body_is_refused_by_name(self):
        """Refuse a body that never closes rather than guessing where it ends."""
        with self.assertRaises(TrustAuditError) as raised:
            scan('verus! { fn f() { }')
        self.assertIn('unclosed', str(raised.exception),
                      'an unclosed group must be refused by name')

    def test_a_verus_attribute_is_found_at_each_nesting_depth(self):
        """Require a ``cfg_attr`` nest to be searched, not merely its first level."""
        for source in ('#[cfg_attr(all(), verifier::external)]\nfn f() {}',
                       '#[cfg_attr(a, cfg_attr(b, verifier::external))]\nfn f() {}',
                       '#[cfg_attr(a, cfg_attr(b, cfg_attr(c, verifier::external)))]\nfn f() {}'):
            with self.subTest(source=source):
                self.assertEqual(item_names(source), ('external',),
                                 'a Verus attribute must be found at any cfg_attr depth')

    def test_an_inner_attribute_carries_verus_vocabulary_too(self):
        """Require ``#![…]`` to be read the same as ``#[…]``.

        The two forms differ by one token, so a bracket index calibrated for one
        reads the other one token short and silently reports nothing.
        """
        self.assertEqual(item_names('#![cfg_attr(feature = "v", verifier::external)]\nfn f() {}'),
                         ('external',),
                         'an inner attribute must be recognised as an attribute')


class LexicalObligations(unittest.TestCase):
    """State the obligations the lexer exists to serve, over generated text."""

    @given(st.text())
    @settings(max_examples=200)
    def test_arbitrary_text_never_raises_an_unexpected_error(self, text):
        """Report a refusal, never a crash, for arbitrary input.

        The scanner runs over source a later edit may malform. Every outcome
        must be a scan result or a :class:`TrustAuditError`; an ``IndexError``
        would mean the lexer resumed somewhere it should have refused, and the
        audit would then report a guess.
        """
        try:
            scan(text)
        except TrustAuditError:
            pass

    @given(st.text(alphabet='abc \n\t"\'/*#()'))
    @settings(max_examples=200)
    def test_punctuation_heavy_text_never_raises_an_unexpected_error(self, text):
        """Keep the refusal total over text built from the lexer's decision points."""
        try:
            scan(text)
        except TrustAuditError:
            pass

    @given(st.text(alphabet='abc ;{}()[]', max_size=40))
    @settings(max_examples=150)
    def test_inserting_a_trust_item_adds_exactly_that_item(self, prefix):
        """Require one inserted ``kani::`` call to add exactly one item.

        Generated prefixes reach positions the handwritten cases do not: a
        prefix may open a brace, close one, or end mid-identifier. Exactly-one
        is the claim that catches double reporting as well as a miss.
        """
        before = item_names(prefix)
        after = item_names(prefix + '\nkani::assume(true);')
        self.assertEqual(after, before + ('assume',),
                         f'inserting one call must add one item; before={before}, after={after}')

    @given(st.text(alphabet='abc ;{}()[]', max_size=40))
    @settings(max_examples=150)
    def test_inserting_a_trust_item_inside_a_comment_adds_nothing(self, prefix):
        """Require the same text in a line comment to add no item."""
        self.assertEqual(item_names(prefix + '\n// kani::assume(true);'), item_names(prefix),
                         'text in a line comment must contribute nothing')

    @given(st.text(alphabet='abc ;{}()[]', max_size=40))
    @settings(max_examples=150)
    def test_inserting_a_trust_item_inside_a_literal_adds_nothing(self, prefix):
        """Require the same text in a string literal to add no item."""
        self.assertEqual(item_names(prefix + '\nlet s = "kani::assume(true);";'),
                         item_names(prefix),
                         'text in a string literal must contribute nothing')


class LexerForms(unittest.TestCase):
    """Cover each literal form whose terminator differs, with a named example.

    A property over arbitrary text cannot show that a *particular* terminator is
    understood, because the generator rarely produces ``r#"…"#`` or ``b""``.
    Each case below places code after the form, so a lexer that stopped short
    would report the following code and one that overran would miss it.
    """

    def test_raw_string_with_hashes_ends_at_its_own_fence(self):
        """Keep the code after ``r#"…"#`` visible."""
        self.assertEqual(item_names('let s = r#"a "quoted" kani::assume(x);"#;\nkani::assume(y);'),
                         ('assume',),
                         'a raw string must not leak its body, nor swallow later code')

    def test_raw_string_with_two_hashes_ends_at_two_hashes(self):
        """Keep the code after ``r##"…"#…"##`` visible."""
        self.assertEqual(item_names('let s = r##"a "# b"##;\nkani::assume(y);'), ('assume',),
                         'a two-hash raw string ends at "## , not at "#')

    def test_empty_byte_string_ends_at_its_own_quote(self):
        """Keep the code after ``b""`` visible.

        An empty byte string exposes a prefix measured without its quote: the
        closing quote is then read as a fresh opening one, and everything to the
        next string is reported as code.
        """
        self.assertEqual(item_names('if f(&b""[..]) {}\nkani::assume(y);'), ('assume',),
                         'b"" must end at its closing quote')

    def test_adjacent_literals_stay_separate(self):
        """Keep the code between two literals visible."""
        self.assertEqual(item_names('g("a", "b");\nkani::assume(y);\nf(&b""[..]);\ng("c");'),
                         ('assume',), 'each literal must end at its own closing quote')

    def test_a_raw_literal_ending_in_vocabulary_is_reported(self):
        """Report a trust word spelled at the very end of a raw literal.

        ``literal_body`` measures the closing fence as the opening one minus its
        prefix, because a raw string opens with ``r#"`` and closes with ``"#``.
        Measuring it symmetrically drops the body's last character, so for a
        proc-macro crate a word at the end of the literal is never seen.
        """
        for source in ('r#"kani::assume"#', 'r##"kani::assume"##', 'r"kani::assume"'):
            with self.subTest(source=source):
                self.assertEqual(
                    tuple(item.item for item in scan(f'let s = {source};', procedural_macro=True).items),
                    ('assume',),
                    'a raw literal must yield its whole body')

    def test_escaped_quote_does_not_end_a_string(self):
        """Keep an escaped quote inside its string."""
        self.assertEqual(item_names('let s = "a \\" kani::assume() b";\nkani::assume(y);'),
                         ('assume',), 'an escaped quote must not end the literal')

    def test_character_literal_is_not_a_lifetime(self):
        """Keep the code after ``'\\''`` visible.

        Reading a character literal as a lifetime leaves its closing quote to
        open a new literal, which then swallows the following code.
        """
        self.assertEqual(item_names("let c = '\\'';\nkani::assume(y);"), ('assume',),
                         'a character literal ends at its closing quote')

    def test_lifetime_is_not_a_character_literal(self):
        """Keep the code after a lifetime visible."""
        self.assertEqual(item_names("fn f<'a>(x: &'a u8) {}\nkani::assume(y);"), ('assume',),
                         'a lifetime must not consume the code that follows')

    def test_unterminated_string_is_refused(self):
        """Refuse a string that never closes rather than scanning past it."""
        with self.assertRaises(TrustAuditError) as raised:
            scan('let s = "kani::assume(x);')
        self.assertIn('unterminated string', str(raised.exception),
                      'the refusal must name the unterminated form')

    def test_unterminated_block_comment_is_refused(self):
        """Refuse a block comment that never closes."""
        with self.assertRaises(TrustAuditError) as raised:
            scan('/* kani::assume(x);')
        self.assertIn('unterminated block comment', str(raised.exception),
                      'the refusal must name the unterminated comment')


