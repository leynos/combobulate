"""Kill the vocabulary-matching mutants a corpus sweep leaves alive (VO-9, VO-10).

The mutation census over :mod:`docs_validation.trust_audit` leaves survivors in
`matcher.py` where the mutation changes a *reported position*, or which of two
overlapping rules claims a token. The existing suites assert that the right
words are reported; they rarely assert *where*. Each case here supplies the one
source the mutant needs. The module-walk cases live in
:mod:`test_trust_audit_module_survivors`; the split is by what each case needs
to know, so each module stays within the repository's module-length limit.

Four families are equivalents rather than gaps, and this module records why.
``_refuse_opaque_macros``'s ``strict=False`` is a keyword-only default that
``zip`` takes as ``False`` anyway, so ``None`` and omission are indistinguishable;
the same function's message suffix is asserted by :mod:`test_trust_audit_crates`
and is mutated in the *second* line of an implicitly concatenated literal, which
the corpus sweep reports without the case being a gap. ``_is_verus_context``'s
``start <= index`` versus ``start < index`` cannot differ because a region's
first index is always the token after ``verus!``'s ``{`` or after an attribute's
``[``, and neither is an identifier. ``_statement_end``'s ``start`` bound cannot
matter either: a ``use`` is lexed with its ``;`` present, so the first search
succeeds before the bound is reached.

Examples
--------
>>> scan('kani::assume(x);').items
(TrustItem(item='assume', line=1, column=7),)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import TrustAuditError, scan
from docs_validation.trust_audit.matcher import _is_bare_use, _statement_end
from docs_validation.trust_audit.lexer import tokenize


def items(text: str, **options) -> tuple[tuple[str, int, int], ...]:
    """Return ``(item, line, column)`` for each item the scan reports."""
    return tuple((item.item, item.line, item.column) for item in scan(text, **options).items)


class ReportingOnce(unittest.TestCase):
    """Require one token reported once, and two tokens on one line kept apart."""

    def test_a_token_matching_two_rules_is_reported_once(self):
        """Require the duplicate test, since a Kani path inside a Verus attribute hits two."""
        self.assertEqual(items('#[cfg_attr(kani, kani::stub(x))]'), (('stub', 1, 24),),
                         'a token reached by two rules must be reported once')

    def test_two_uses_on_one_line_stay_distinguishable(self):
        """Require the column in the duplicate test, not the line alone.

        DL-16 compares a multiset of ``(item, location)`` pairs, so collapsing
        two same-line uses into one makes a record that covers both look like it
        covers neither.
        """
        self.assertEqual(items('kani::assume(a); kani::assume(b);'),
                         (('assume', 1, 7), ('assume', 1, 24)),
                         'two uses on one line must keep their own columns')

class LiteralScanning(unittest.TestCase):
    """Require a proc-macro crate's literal to report its Kani vocabulary."""

    def test_an_ordinary_kani_qualified_word_inside_a_literal_is_reported(self):
        """Require the positive case, so the filter case is not vacuous."""
        self.assertEqual(items('let s = "kani::assume(x)";', procedural_macro=True),
                         (('assume', 1, 16),),
                         'a proc-macro literal must report the Kani item it spells')

    def test_a_kani_qualified_word_outside_the_vocabulary_is_not_reported(self):
        """Require the Kani filter, so ``kani::assert`` is not mistaken for trust.

        The bare-word pass that follows finds nothing here either, because
        ``assert`` is not vocabulary. A filter that accepted the complement
        would report precisely the words that are *not* trust.
        """
        self.assertEqual(items('let s = "kani::assert(x)";', procedural_macro=True), (),
                         'a Kani path to a non-trust item must report nothing')

    def test_a_literal_spanning_lines_reports_the_line_of_its_item(self):
        """Require the newline count, which is what makes a multi-line literal locatable."""
        self.assertEqual(items('let s = "a\nkani::assume(x)";', procedural_macro=True),
                         (('assume', 2, 7),),
                         'an item on a later line of a literal must report that line')

    def test_a_literal_item_after_a_newline_reports_its_column(self):
        """Require the column to be measured from the last newline, not the token start."""
        self.assertEqual(items('let s = "a\n  kani::assume(b)";', procedural_macro=True),
                         (('assume', 2, 9),),
                         'an item after a newline must report its column within that line')

class BareUse(unittest.TestCase):
    """Require rule (iii) to claim a bare word, and only a bare word."""

    def test_a_word_after_a_path_separator_is_not_bare(self):
        """Require ``::`` to exclude the word, which rule (i) already covers."""
        tokens = tokenize('x::assume')
        self.assertFalse(_is_bare_use(tokens, 2),
                         'a word after :: belongs to a path, not a bare use')

    def test_a_word_after_a_field_access_is_not_bare(self):
        """Require ``.`` to exclude the word, since a method is not a bare use."""
        tokens = tokenize('x.assume')
        self.assertFalse(_is_bare_use(tokens, 2),
                         'a word after . is a field or method, not a bare use')

    def test_a_word_at_the_start_of_a_file_is_bare(self):
        """Require index zero to be admitted rather than indexed backwards.

        Reading ``tokens[index - 1]`` at index zero would silently inspect the
        file's *last* token, making the first word's answer depend on the end of
        the file.
        """
        tokens = tokenize('assume(x)')
        self.assertTrue(_is_bare_use(tokens, 0),
                        'the first token of a file has no predecessor and is bare')

    def test_a_word_after_an_identifier_is_bare(self):
        """Require the positive case, so the exclusions are not vacuous."""
        tokens = tokenize('f(assume)')
        self.assertTrue(_is_bare_use(tokens, 2),
                        'a word neither after :: nor after . is a bare use')

    def test_the_predecessor_is_read_not_the_successor(self):
        """Require the *preceding* token, which is the one that decides the rule.

        Here the word follows a plain ``(`` and precedes the path separator.
        Reading forwards would see ``::`` and call it qualified, so the one
        ``assume`` a record must cover would go unreported.
        """
        tokens = tokenize('f(assume::x)')
        self.assertTrue(_is_bare_use(tokens, 2),
                        'the rule must consult the token before the word, not after')

class StatementBounds(unittest.TestCase):
    """Require a ``use`` tree's root to be read up to its own semicolon."""

    def test_the_semicolon_ends_the_search(self):
        """Require the search to report the first ``;`` so a later statement is not read."""
        tokens = tokenize('use a; b;')
        self.assertEqual(_statement_end(tokens, 0), 2,
                         'the first semicolon must end the statement')

    def test_a_statement_without_a_semicolon_ends_at_end_of_file(self):
        """Require the end of file to be the bound when no ``;`` appears."""
        tokens = tokenize('use a')
        self.assertEqual(_statement_end(tokens, 0), len(tokens),
                         'a statement with no semicolon must end at the last token')

class VerusRegionEdges(unittest.TestCase):
    """Require a Verus region's bounds to include its own vocabulary and no more."""

    def test_the_first_token_of_a_body_is_inside_it(self):
        """Require the region to start at the token after ``{``, not after that one.

        A region that starts one token late leaves the body's first statement
        outside it, so ``verus! { assume(x); }`` reports nothing. That is the
        failing direction DL-17 exists to prevent: the audit says the proof has
        no trust in it.
        """
        self.assertEqual(items('verus! { assume(x); }'), (('assume', 1, 10),),
                         'the first token of a verus! body must be inside its region')

    def test_a_word_before_the_macro_is_not_inside_the_body(self):
        """Require the region to begin after ``verus!``, so earlier code is not adopted.

        A region starting before the macro would report an ordinary ``external``
        that merely sits earlier in the file as Verus trust, at a location the
        author would not recognise.
        """
        self.assertEqual(items('external verus! { assume(y); }'), (('assume', 1, 19),),
                         'only the body of a verus! macro is a Verus region')

    def test_a_bare_verus_call_is_not_a_verus_body(self):
        """Require all three of ``verus``, ``!``, and ``{`` before a body is claimed.

        ``verus(a);`` is an ordinary call. Accepting ``verus`` or ``!`` alone
        makes it look like a macro body and then fails to find the ``{`` the
        body needs, refusing a file that is valid Rust.
        """
        self.assertEqual(items('verus(a);'), (),
                         'a call to a function named verus is not a macro body')

    def test_an_attribute_region_stops_at_its_own_closer(self):
        """Require the region to end before ``]``, not after it.

        A region ending past the attribute's ``]`` adopts the item the attribute
        decorates, so ``#[verifier(x)] external;`` reports that item as trust
        even though the attribute says nothing about it.
        """
        self.assertEqual(items('#[verifier(x)] external;'), (),
                         'an attribute region must not extend past its own bracket')

    def test_a_cfg_attr_region_stops_at_its_own_closer(self):
        """Require the same bound for the ``cfg_attr`` form that carries Verus."""
        self.assertEqual(items('#[cfg_attr(verus_verify, x)] external;'), (),
                         'a cfg_attr region must not extend past its own bracket')

class DeduplicationIdentity(unittest.TestCase):
    """Require the duplicate test to compare the item and the position together."""

    def test_two_different_items_at_one_position_are_both_reported(self):
        """Require the item comparison, so distinct words are not merged.

        The check exists to stop one token being reported twice. Comparing only
        the position would drop every second item sharing a location, which for
        a literal scan is the common case: two vocabulary words in one string.
        """
        self.assertEqual(items('let s = "kani::assume(kani::stub(x))";', procedural_macro=True),
                         (('assume', 1, 16), ('stub', 1, 29)),
                         'two different items at distinct offsets must both be reported')

    def test_one_item_reported_twice_keeps_its_first_position(self):
        """Require the line and column in the duplicate test, not the item alone.

        ``kani::assume`` is matched by the qualified rule and again by the word
        rule at the same offset. Dropping the second is what keeps the report a
        set; a test that compared only the item would also drop a *second*
        genuine use of the same word elsewhere in the file.
        """
        self.assertEqual(items('kani::assume(a); kani::assume(b);'),
                         (('assume', 1, 7), ('assume', 1, 24)),
                         'the same item at two offsets must be reported at both')

class UnrelatedTextIsNotTrust(unittest.TestCase):
    """Require a vocabulary word to need a context before it is reported."""

    def test_a_field_named_assume_is_not_a_bare_use(self):
        """Require ``.`` to exclude the word, since a field is not a trust use.

        The mutant reads the token at ``None`` rather than at the index, which
        makes the exclusion look at the wrong token. A file that imports from a
        trust root would then report a field or method named ``assume``.
        """
        self.assertEqual(items('use kani::assume;\nfn f() { x.assume; }'),
                         (('assume', 1, 11),),
                         'a field named assume is not a bare trust use')

    def test_a_bare_use_before_no_import_is_still_reported(self):
        """Require the positive direction of rule (iii), so the filter is not vacuous."""
        self.assertEqual(items('use kani::assume;\nfn f() { assume(1); }'),
                         (('assume', 1, 11), ('assume', 2, 10)),
                         'a bare use in a file importing a trust root must be reported')

class StatementAndImportBounds(unittest.TestCase):
    """Require a ``use`` statement to be read from its own keyword onwards."""

    def test_a_use_after_another_statement_is_still_read(self):
        """Require the search to start at the statement, not at the file's first token.

        Starting at index zero finds the *previous* statement's ``;`` as this
        statement's end, so the root is never read and the import is invisible.
        Rule (iii) then stops applying and the file's bare uses go unreported.
        """
        self.assertEqual(items('use a;\nuse kani::assume;\nfn f() { assume(1); }'),
                         (('assume', 2, 11), ('assume', 3, 10)),
                         'a use after another statement must still be read')

    def test_an_import_after_code_is_still_found(self):
        """Require the walk to continue past non-``use`` tokens rather than stop.

        An import usually follows the module's opening code. Stopping at the
        first non-``use`` token would find only imports at the very top of the
        file and silently disable rule (iii) everywhere else.
        """
        self.assertEqual(items('fn f() {}\nuse kani::assume;\nfn g() { assume(1); }'),
                         (('assume', 2, 11), ('assume', 3, 10)),
                         'an import after code must still be discovered')

class NestedAttributeRecognition(unittest.TestCase):
    """Require a ``cfg_attr`` search to read its own contents and no further.

    ``_carries_verus`` scans the tokens between a ``cfg_attr``'s predicate and
    the attribute's closer. Its start and end are both load-bearing: starting
    too late misses a Verus head that comes first, and ending at ``None`` runs
    past the bracket into whatever the file writes next. Either way a Verus
    word is reported as trust in an attribute that does not carry it, or one
    that does is missed.
    """

    def test_a_verus_head_immediately_after_the_predicate_is_seen(self):
        """Require the search to start at ``open_index + 2``, its documented start.

        ``#[cfg_attr verus_verify assume]`` is not valid Rust attribute syntax,
        but it is what a lexer sees if the author wrote the predicate without
        parentheses. The Verus head is then the first token the search must
        inspect; starting one further along skips it and the region is lost.
        """
        self.assertEqual(items('#[cfg_attr verus_verify assume]'),
                         (('assume', 1, 25),),
                         'a verus head at the search start must create a region')

    def test_a_cfg_attr_without_verus_does_not_reach_a_later_attribute(self):
        """Require the search to stop at ``close_index`` rather than run on.

        A ``#[verifier]`` attribute written *after* a plain ``cfg_attr`` is a
        separate attribute with its own region. Searching past the first
        attribute's closer would let the second attribute's head satisfy the
        first one's test, reporting the first attribute's words as trust even
        though nothing in it is Verus.
        """
        self.assertEqual(items('#[verifier] #[cfg_attr(feature, assume)] external;'), (),
                         'a cfg_attr region must not borrow a later attribute head')

    def test_a_verus_attribute_after_a_plain_cfg_attr_is_not_attributed_to_it(self):
        """Require the end bound in the other direction, where the Verus word is real.

        The trailing ``#[verifier]`` makes ``external`` trust through its own
        region. A search that ran to the end of the file would instead also
        attribute the ``assume`` from the earlier attribute, reporting trust in
        a position no Verus context covers.
        """
        self.assertEqual(items('#[cfg_attr(feature, assume)] #[verifier] external;'), (),
                         'a later verifier attribute must not retroactively cover an earlier one')

class RegionBoundaries(unittest.TestCase):
    """Require a ``verus!`` body's found position and end to be the body's own."""

    def test_an_unclosed_verus_body_is_refused_rather_than_ignored(self):
        """Require the scan to reach ``verus!{`` at the end of the file.

        The region finder walks up to the last token it can look three ahead
        from. Stopping earlier would skip a ``verus!`` immediately followed by
        the file's final token, and the unclosed body it opens would go
        unreported instead of refusing.
        """
        with self.assertRaises(TrustAuditError) as raised:
            scan('verus!{')
        self.assertIn('unclosed', str(raised.exception),
                      'an unclosed verus body must be refused')

class PositionalReporting(unittest.TestCase):
    """Require every reported position to be the item's own, not a nearby one."""

    def test_the_same_item_on_two_lines_is_reported_twice(self):
        """Require the line in the duplicate test, not the item alone.

        Two ``kani::assume`` calls on separate lines are two trust sites and
        must be reported separately. Comparing only the item would collapse
        them into one, and the record would be certified against half the trust
        the file contains.
        """
        self.assertEqual(items('kani::assume(a);\nkani::assume(b);'),
                         (('assume', 1, 7), ('assume', 2, 7)),
                         'the same item on two lines must be reported at both')

    def test_a_literal_spanning_lines_locates_each_word_on_its_own_line(self):
        """Require the *last* newline to be measured from, not the first.

        The column inside a multi-line literal is counted from the newline
        directly before the word. Measuring from the first newline in the
        prefix would place every word after the second line at a column offset
        by the earlier lines' lengths, so two uses in one literal could collide
        or be reported at positions no editor shows.
        """
        self.assertEqual(items('let s = "a\n  kani::assume(b)\n  kani::stub(c)";',
                               procedural_macro=True),
                         (('assume', 2, 9), ('stub', 3, 9)),
                         'each word in a multi-line literal must be located on its own line')

class OpaqueMacroMessages(unittest.TestCase):
    """Require the refusal to name the macro and its position, not only say why."""

    def test_the_refusal_names_the_macro_and_where_it_is(self):
        """Require the location prefix, so a reader can find the macro."""
        with self.assertRaises(TrustAuditError) as raised:
            scan('fn f() {\n  include!("x.rs");\n}')
        self.assertIn('include! at line 2, column 3', str(raised.exception),
                      'the refusal must name the macro and its position')


if __name__ == '__main__':
    unittest.main()
