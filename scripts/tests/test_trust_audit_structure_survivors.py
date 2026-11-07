"""Kill the bracket-arithmetic mutants a corpus sweep leaves alive (VO-9, VO-10).

The mutation census over :mod:`docs_validation.trust_audit` leaves every
survivor in ``structure.py`` alive because nothing tested the module directly:
the existing suites reach these helpers only through whole-source scans, and a
corpus of real files never spells the boundary each mutant moves. Each case
here hands the helper the token sequence the mutant needs and asserts the index
the helper promises.

Three survivors are equivalent rather than untested, and this module records why
instead of silencing them. ``attribute_spans``'s ``index + 2 < len(tokens)``
weakens a guard whose false branch can only be reached when the source ends
``# !``; there both the guarded and unguarded openings fail the ``[`` test, so
no span is reported either way. In ``previous_closer`` and both opening-bracket
searches, a range that runs one index further (``-2`` instead of ``-1``) can
only visit Python's ``tokens[-1]``, and every branch that index can take either
returns the same ``-1`` the loop would have returned or leaves the search
unfinished; an index of ``-1`` is therefore indistinguishable from exhaustion.
A survivor no input can distinguish is not a test gap.

Examples
--------
>>> [token.text for token in tokenize('#[a]')]
['#', '[', 'a', ']']
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import TrustAuditError
from docs_validation.trust_audit.lexer import tokenize
from docs_validation.trust_audit.structure import (
    attribute_spans,
    matching,
    opening_bracket,
    opening_paren,
    path_value,
    previous_closer,
    skip_visibility,
)


def positions(tokens, text: str) -> list[int]:
    """Return every index at which ``tokens`` spells ``text``."""
    return [index for index, token in enumerate(tokens) if token.text == text]


def only(tokens, text: str) -> int:
    """Return the sole index at which ``tokens`` spells ``text``."""
    found = positions(tokens, text)
    if len(found) != 1:
        raise AssertionError(f'expected one {text!r} token, found {len(found)}')
    return found[0]


class Matching(unittest.TestCase):
    """Require the closer of the group actually opened, not the first one seen."""

    def test_a_group_before_the_opening_does_not_shift_the_close(self):
        """Require the search to start at the opening token.

        A ``matching`` that starts at index zero counts the earlier group's
        opener and then takes its closer as the answer, so the second group's
        span ends one group too early and every region built from it is wrong.
        """
        tokens = tokenize('{a} {b}')
        self.assertEqual(matching(tokens, 3, '{', '}'), 5,
                         'the closer reported must belong to the group opened at index 3')

    def test_nesting_is_counted_rather_than_short_circuited(self):
        """Require the depth to be restored, which is what makes nesting work."""
        tokens = tokenize('{ {} }')
        self.assertEqual(matching(tokens, 0, '{', '}'), 3,
                         'the outer closer must be reported, not the inner one')

    def test_an_unclosed_group_names_the_token_that_opened_it(self):
        """Require the refusal to carry the opener's position, which is the fix.

        The column is the *bracket's* own, not the position after it: a reader
        told column 4 for the ``{`` at column 3 edits the wrong character.
        """
        tokens = tokenize('\n  {a')
        with self.assertRaises(TrustAuditError) as raised:
            matching(tokens, 0, '{', '}')
        self.assertIn('unclosed', str(raised.exception),
                      'an unclosed group must say that it is unclosed')
        self.assertIn('line 2, column 3', str(raised.exception),
                      'the refusal must name where the unclosed group opened')


class AttributeSpans(unittest.TestCase):
    """Require both attribute forms to report the bracket that actually opens."""

    def test_an_outer_attribute_spans_from_its_bracket(self):
        """Require ``#[…]`` to open at the ``[`` immediately after ``#``."""
        tokens = tokenize('#[a]')
        self.assertEqual(attribute_spans(tokens), ((1, 3),),
                         'an outer attribute spans its own bracket pair')

    def test_an_inner_attribute_skips_the_bang(self):
        """Require ``#![…]`` to open after the ``!``, since the ``!`` is not a bracket."""
        tokens = tokenize('#![a]')
        self.assertEqual(attribute_spans(tokens), ((2, 4),),
                         'an inner attribute spans the bracket after the bang')

    def test_both_forms_in_one_source_keep_their_own_spans(self):
        """Require the two forms to be distinguished without one shifting the other."""
        tokens = tokenize('#[a] #![b]')
        self.assertEqual(attribute_spans(tokens), ((1, 3), (6, 8)),
                         'each attribute must report its own bracket pair')

    def test_a_hash_bang_with_no_bracket_reports_nothing(self):
        """Record the equivalence: a trailing ``# !`` cannot reach the guarded opening.

        The guard exists so that ``opening`` is only read when it is in range.
        With two tokens left after ``#``, the guarded form skips the read and
        the weakened form reads the ``!``; neither finds a ``[``, so the
        survivor's mutation is unobservable.
        """
        tokens = tokenize('a #!')
        self.assertEqual(attribute_spans(tokens), (),
                         'a bang with no bracket opens no attribute')


class PreviousCloser(unittest.TestCase):
    """Require the backwards walk to stop at the right boundary and keep looking otherwise."""

    def test_the_bang_of_an_inner_attribute_does_not_stop_the_walk(self):
        """Require ``!`` to be walked over, since it is part of an attribute.

        Stopping at the ``!`` would report that a second attribute in
        ``#![a] #![b]`` has no predecessor, so a ``#[path]`` run separated by
        an attribute would silently fall back to Rust's bare module search.
        """
        tokens = tokenize('#![a] #![b]')
        opener = positions(tokens, '[')[1]
        self.assertEqual(previous_closer(tokens, opener), 4,
                         'the walk must cross the bang and report the earlier closer')

    def test_an_ordinary_token_stops_the_walk(self):
        """Require a non-attribute token to end the search rather than be skipped."""
        tokens = tokenize('a [b]')
        self.assertEqual(previous_closer(tokens, 1), -1,
                         'a bracket preceded by ordinary code has no attribute before it')

    def test_a_run_of_attribute_punctuation_without_a_closer_reports_minus_one(self):
        """Require exhaustion to report ``-1``, which is the documented no-answer."""
        tokens = tokenize('# [!')
        self.assertEqual(previous_closer(tokens, 1), -1,
                         'a run with no closer must report -1')


class VisibilitySkipping(unittest.TestCase):
    """Require each visibility form to step back exactly over itself."""

    def test_pub_in_path_is_skipped_as_one_unit(self):
        """Require ``pub(in path)`` to report the index before ``pub``."""
        tokens = tokenize('pub(in crate::x) mod y;')
        close = only(tokens, ')')
        self.assertEqual(skip_visibility(tokens, close), -1,
                         'a pub(in …) modifier must step back over the whole modifier')

    def test_parentheses_that_are_not_a_visibility_are_left_alone(self):
        """Require a call's ``)`` to be reported unchanged.

        Returning a shifted index for an ordinary call would make the attribute
        walk read the call's operand as an attribute, refusing a valid module.
        """
        tokens = tokenize('x (y)')
        close = only(tokens, ')')
        self.assertEqual(skip_visibility(tokens, close), close,
                         'a parenthesis that is not pub(…) must not move the index')

    def test_an_unmatched_parenthesis_is_reported_unchanged(self):
        """Require the ``None`` opener to be handled, not indexed through."""
        tokens = tokenize(')')
        self.assertEqual(skip_visibility(tokens, 0), 0,
                         'a parenthesis with no opener must leave the index alone')

    def test_plain_pub_steps_back_one(self):
        """Require a bare ``pub`` to report the index before it."""
        tokens = tokenize('pub x')
        self.assertEqual(skip_visibility(tokens, 0), -1,
                         'a bare pub at the start must report the index before the file')

    def test_an_index_before_the_file_is_reported_unchanged(self):
        """Require ``-1`` to stay ``-1`` so the caller's loop does not start."""
        tokens = tokenize('a (b)')
        self.assertEqual(skip_visibility(tokens, -1), -1,
                         'an index before the first token must not be moved')


class OpeningBrackets(unittest.TestCase):
    """Require each backwards search to match the opener for its own closer."""

    def test_parentheses_nest(self):
        """Require the outermost ``(`` for the outermost ``)``."""
        tokens = tokenize('((a))')
        self.assertEqual(opening_paren(tokens, 4), 0,
                         'the outer parenthesis must be reported for the outer closer')

    def test_brackets_nest(self):
        """Require the outermost ``[`` for the outermost ``]``."""
        tokens = tokenize('[[a]]')
        self.assertEqual(opening_bracket(tokens, 4), 0,
                         'the outer bracket must be reported for the outer closer')

    def test_a_parenthesis_with_no_opener_reports_none(self):
        """Require ``None`` rather than a negative index or an exception."""
        tokens = tokenize('x)')
        self.assertIsNone(opening_paren(tokens, 1),
                          'an unmatched closer must report None')

    def test_a_bracket_with_no_opener_reports_none(self):
        """Require ``None`` rather than a negative index or an exception."""
        tokens = tokenize('x]')
        self.assertIsNone(opening_bracket(tokens, 1),
                          'an unmatched bracket must report None')


class PathValues(unittest.TestCase):
    """Require only a well-formed ``#[path = "…"]`` to yield a value."""

    def test_a_well_formed_path_reports_its_literal_body(self):
        """Require the literal's body, not its quotes, which is what a caller resolves."""
        tokens = tokenize('#[path = "x.rs"]')
        self.assertEqual(path_value(tokens, only(tokens, '['), only(tokens, ']')), 'x.rs',
                         'a path attribute must report the file name it names')

    def test_a_comparison_instead_of_an_assignment_is_not_a_path(self):
        """Require the ``=`` test, since ``==`` spells two tokens.

        Without it the literal two tokens later would be reported as a path
        even though the attribute says nothing about a file.
        """
        tokens = tokenize('#[path == "x.rs"]')
        self.assertIsNone(path_value(tokens, only(tokens, '['), only(tokens, ']')),
                          'an attribute that is not a path assignment must report no value')

    def test_a_similarly_named_attribute_is_not_a_path(self):
        """Require the head to be exactly ``path``, not merely to start with it."""
        tokens = tokenize('#[pathed = "x.rs"]')
        self.assertIsNone(path_value(tokens, only(tokens, '['), only(tokens, ']')),
                          'an attribute named otherwise must report no value')

    def test_a_span_too_short_to_hold_a_literal_reports_no_value(self):
        """Require ``#[path]`` to be refused rather than read past its bracket."""
        tokens = tokenize('#[path]')
        self.assertIsNone(path_value(tokens, only(tokens, '['), only(tokens, ']')),
                          'a path attribute with no assignment must report no value')


if __name__ == '__main__':
    unittest.main()
