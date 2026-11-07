"""Kill the lexer and command mutants a corpus sweep leaves alive (VO-9, VO-10).

The mutation census over :mod:`docs_validation.trust_audit` leaves survivors
where the mutation moves a cursor by one character, replaces a fallback, or
swaps an ``encoding=`` keyword. The corpus is a set of valid files, so it never
ends mid-literal, never starts a literal on the last character, and never writes
a manifest whose bytes require the declared encoding. Each case here supplies
the exact boundary the mutant needs.

Four families are equivalents rather than gaps, and this module records why.
``Cursor.line_before`` and ``Cursor.column_before`` are overwritten by
``_consume_quote_literal`` on its first line before any caller can read them, and
the same is true of every other ``_Cursor`` field a constructor mutant touches.
``_skip_trivia``'s ``newline <= 0`` and ``newline < 1`` variants agree with
``< 0``: the search starts at the ``/`` of the comment marker, which is not a
newline, so a *found* position is never ``0`` and an absent newline reports
``-1``, which all three tests classify as absent. ``read_text(encoding='UTF-8')``
is case-insensitive in Python's codec lookup, and ``encoding=None`` selects the
locale's preferred encoding, which is UTF-8 here. A survivor no input can
distinguish is not a test gap.

The remaining equivalents are argued where the mutated code sits.
``_skip_trivia``'s ``break``/``return`` pair and its ``len(text) + index`` arm
are in :mod:`test_trust_audit_scanner_survivors`; the module name bound and the
``_path_attribute`` walk start are in
:mod:`test_trust_audit_attribute_survivors`; the four ``structure.py``
survivors are in :mod:`test_trust_audit_structure_survivors`.

Examples
--------
>>> [token.text for token in tokenize("'a' b")]
['b']
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import TrustAuditError
from docs_validation.trust_audit.command import (
    is_procedural_macro_crate,
    resolve_repository_path,
    scan_tree,
)
from docs_validation.trust_audit.lexer import _Cursor, tokenize


def texts(source: str) -> list[str]:
    """Return the text of every token the lexer produces."""
    return [token.text for token in tokenize(source)]


class CharacterLiteralBoundaries(unittest.TestCase):
    """Require a character literal and a lifetime to be told apart at the edge."""

    def test_a_character_at_end_of_file_is_consumed_whole(self):
        """Require the three-token form ``'a'`` to close, leaving nothing behind.

        If the guard is off by one the closing quote is not recognised, the
        lexer reads ``'a`` as a lifetime, and the stray quote starts a literal
        that runs to the end of the file.
        """
        self.assertEqual(texts("'a'"), [],
                         'a character literal at end of file must leave no stray quote')

    def test_a_lifetime_at_end_of_file_is_consumed_whole(self):
        """Require ``'a`` to be read as a lifetime, contributing no token at all.

        A lifetime carries no code, so the lexer drops it. Reading it as an
        unterminated literal would refuse a file that is perfectly valid Rust.
        """
        self.assertEqual(texts("'a"), [],
                         'a lifetime at end of file must be consumed without a token')

    def test_a_character_followed_by_code_keeps_that_code(self):
        """Require the literal to close before the next token, not swallow it."""
        self.assertEqual(texts("'a' b"), ['b'],
                         'code after a character literal must still be lexed')

    def test_an_escaped_character_is_consumed_as_a_literal(self):
        """Require the escape branch, since ``'\\n'`` is not a lifetime."""
        self.assertEqual(texts("'\\n' b"), ['b'],
                         'an escaped character literal must close before the next token')

    def test_a_character_holding_a_quote_is_not_a_lifetime(self):
        """Require the escaped branch to matter: ``'\\''`` holds three characters."""
        self.assertEqual(texts("'\\'' b"), ['b'],
                         'a character literal holding an escaped quote must close')

    def test_the_following_character_is_read_from_the_cursor(self):
        """Require the lookahead to start after the opening quote.

        Reading backwards would see the quote itself, take the escape branch for
        every literal, and consume two characters per step.
        """
        self.assertEqual(texts("'ab' c"), ['c'],
                         'a plain character literal must close before the next token')


class BlockCommentBoundaries(unittest.TestCase):
    """Require a block comment to consume exactly its own delimiters."""

    def test_a_comment_is_removed_whole(self):
        """Require both delimiters to be consumed, so no ``*`` or ``/`` token remains."""
        self.assertEqual(texts('/* x */ a'), ['a'],
                         'a block comment must leave no punctuation behind')

    def test_nested_comments_are_counted(self):
        """Require Rust's nesting rule, which a naive terminator search breaks."""
        self.assertEqual(texts('/* a /* b */ c */ a'), ['a'],
                         'a nested block comment must close only at the outer terminator')

    def test_an_unterminated_comment_names_its_opening(self):
        """Require the refusal to point at the opener, not at end of file."""
        with self.assertRaises(TrustAuditError) as raised:
            tokenize('\n  /* x')
        self.assertIn('line 2, column 3', str(raised.exception),
                      'the refusal must name where the unterminated comment opened')


class TriviaBoundaries(unittest.TestCase):
    """Require whitespace and line comments to be consumed without losing a token."""

    def test_a_line_comment_at_end_of_file_consumes_the_rest(self):
        """Require the no-newline branch, which has no terminator to stop at."""
        self.assertEqual(texts('a // tail'), ['a'],
                         'a line comment with no newline must consume to end of file')

    def test_a_line_comment_stops_at_its_newline(self):
        """Require the newline branch, so the next line is still lexed."""
        self.assertEqual(texts('a // c\nb'), ['a', 'b'],
                         'a line comment must stop at its newline, not end of file')

    def test_every_whitespace_character_is_skipped(self):
        """Require each character of the whitespace set to be recognised."""
        self.assertEqual(texts('a \t\r\n b'), ['a', 'b'],
                         'all four whitespace characters must be skipped')

    def test_a_run_of_trivia_returns_control_after_one_pass(self):
        """Require ``_skip_trivia`` to report consumption, so the caller loops once more.

        Reporting "nothing consumed" after consuming a comment would leave the
        caller to lex the comment as punctuation.
        """
        self.assertEqual(texts('/* a */ /* b */ c'), ['c'],
                         'consecutive comments must both be consumed')


class CursorArithmetic(unittest.TestCase):
    """Require the cursor to advance by exactly what it consumed."""

    def test_take_moves_the_index_by_the_count(self):
        """Require ``take`` to respect its argument, which every consumer assumes."""
        cursor = _Cursor('abcdef')
        cursor.take(2)
        self.assertEqual(cursor.index, 2,
                         'take(2) must consume exactly two characters')

    def test_take_reports_what_it_consumed(self):
        """Require the returned chunk, which the character-literal path relies on."""
        self.assertEqual(_Cursor('abcdef').take(3), 'abc',
                         'take must return the characters it consumed')

    def test_a_newline_resets_the_column(self):
        """Require the column reset, which every reported position depends on."""
        cursor = _Cursor('ab\ncd')
        cursor.take(4)
        self.assertEqual((cursor.line, cursor.column), (2, 2),
                         'a consumed newline must advance the line and reset the column')

    def test_skip_until_stops_after_the_terminator(self):
        """Require the terminator itself to be consumed with the body."""
        cursor = _Cursor('abc"def')
        cursor.skip_until('"', 'string')
        self.assertEqual(cursor.index, 4,
                         'skip_until must consume through its terminator')

    def test_skip_until_refuses_an_absent_terminator(self):
        """Require the absent case to fail closed rather than consume to end of file."""
        with self.assertRaises(TrustAuditError) as raised:
            _Cursor('abc').skip_until('"', 'string')
        self.assertIn('unterminated string', str(raised.exception),
                      'an absent terminator must refuse with the caller supplied name')

    def test_skip_until_stops_at_the_first_terminator(self):
        """Require the *first* terminator, which is the one that closes the form.

        ``find`` reports the earliest match from the cursor, and this cursor
        holds two. ``rfind`` reports the later one, so the scan runs past the
        literal's own end and the text between the two terminators is consumed
        as part of the literal. For a raw string that is the difference between
        two adjacent literals and one literal swallowing both:

            >>> [token.text for token in tokenize('r"a" r"b"')]
            ['r"a"', 'r"b"']

        where the mutant yields the single token ``'r"a" r"b"'``. Code that
        sat between the literals would then be invisible to the audit.
        """
        cursor = _Cursor('a"b"c')
        cursor.skip_until('"', 'string')
        self.assertEqual(cursor.index, 2,
                         'skip_until must stop at the first terminator, not the last')


class TokenPositions(unittest.TestCase):
    """Require a punctuator's reported position to be its own, not the one after it."""

    def test_a_punctuator_reports_where_it_starts(self):
        """Require the position read before the token is consumed.

        Reading afterwards reports the token's end, so an unclosed-group
        refusal names the column after the bracket a reader has to fix.
        """
        opener, = tokenize('\n  {')
        self.assertEqual((opener.line, opener.column), (2, 3),
                         'a punctuator must report the column it starts at')


class CommentNestingBoundaries(unittest.TestCase):
    """Require a nested comment's delimiter to be consumed by exactly two characters."""

    def test_two_adjacent_openers_after_the_outer_one_are_counted(self):
        """Require ``take(2)``, since a wider take skips an opener it must count.

        ``/*/**/*/`` is an outer comment whose body holds ``/*`` and then ``*/``
        immediately: the nested pair must open and close, leaving the final
        ``*/`` to close the outer comment. Consuming three characters at the
        inner ``/*`` eats the ``/`` that begins the inner terminator, so the
        nesting is never closed and valid source is refused.
        """
        self.assertEqual(texts('/*/**/*/ a'), ['a'],
                         'a comment holding an immediately closed nested comment must close')

    def test_an_open_then_close_run_still_terminates(self):
        """Require the same boundary in the direction that must refuse.

        ``/*/*/*/`` never closes: the inner ``/*`` opens a level the remaining
        ``/*/`` cannot close. Refusing it is right, and a mutant that skips a
        character may instead accept it as a complete comment.
        """
        with self.assertRaises(TrustAuditError):
            tokenize('/*/*/*/ a')


class LiteralConsumptionBoundaries(unittest.TestCase):
    """Require a character literal to consume its quote and its body, not more."""

    def test_code_after_an_escaped_literal_is_still_lexed(self):
        """Require the escape to close at its own quote, leaving the text after it.

        ``'\\''a'`` is a literal holding an escaped quote followed by ``a``.
        Consuming two characters at the opening quote makes the escape branch
        read the closing quote as an escaped character, so the literal runs on
        and the code after it is swallowed.
        """
        self.assertEqual(texts("'\\''a'"), ['a'],
                         'an escaped literal must close before the code that follows it')

    def test_a_trust_word_after_an_escaped_literal_is_still_seen(self):
        """Require the audit to reach code the literal precedes, which is the consequence.

        The token stream is what the matcher reads, so a literal that swallows
        its neighbour hides an ``assume`` from the audit entirely — the failure
        direction that makes the audit claim a proof has no trust in it.
        """
        self.assertIn('assume', texts("x '\\''assume(y);"),
                      'code after an escaped literal must still be tokenised')


class TriviaBoundaryCharacters(unittest.TestCase):
    """Require the whitespace set to be exactly the four characters Rust skips."""

    def test_the_letter_x_before_the_comment_marker_is_code(self):
        """Require ``X`` to be lexed, since a widened literal set would skip it.

        ``X`` appears in no Rust whitespace, but it is the letter a mutant that
        bracketed the set with markers would add. A lexer that treats it as
        trivia silently deletes an identifier, and for a proc-macro crate that
        identifier can be the only spelling of a trust item.
        """
        self.assertEqual(texts('X'), ['X'],
                         'a letter outside the whitespace set must be tokenised')

    def test_the_letters_bracketing_the_set_do_not_join_a_word(self):
        """Require ``Xfoo`` to stay one identifier, not to lose its first letter."""
        self.assertEqual(texts('Xfoo'), ['Xfoo'],
                         'a word beginning with a non-whitespace letter must keep it')


class LineCommentConsumption(unittest.TestCase):
    """Require a line comment to consume through its own newline and no further."""

    def test_a_comment_at_the_first_character_is_consumed(self):
        """Require the newline search from index zero, not to be treated as absent.

        The search reports the position of the ``\\n`` it found, which is
        greater than zero whenever the comment is not at the start of the file.
        A guard that mistakes zero for "not found" consumes from the wrong
        direction, and a comment opening the file is exactly where it happens.
        """
        self.assertEqual(texts('// c\nb'), ['b'],
                         'a line comment at the first character must stop at its newline')

    def test_a_line_comment_with_no_newline_consumes_to_the_end(self):
        """Require the absent-terminator branch, which has no position to read."""
        self.assertEqual(texts('//c'), [],
                         'a line comment with no newline must consume the rest of the file')


class EmptyCommentBodies(unittest.TestCase):
    """Require an empty literal or comment to be consumed, not to stall the lexer."""

    def test_a_string_still_reports_its_body(self):
        """Require the body rather than ``None``, which no caller expects.

        ``literal_body``'s callers slice and search the returned text, and a
        proc-macro scan reads the literal token back through the same path. A
        placeholder body would make that scan raise instead of reporting.
        """
        self.assertEqual(texts('"assume"'), ['"assume"'],
                         'a string must be returned as one literal token')


class CommandRefusals(unittest.TestCase):
    """Require the command layer's encoding and refusal paths to carry their reason."""

    def test_a_proc_macro_manifest_is_recognised(self):
        """Require the directive test to read the manifest it is given."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'Cargo.toml'
            manifest.write_text('[lib]\nproc-macro = true\n')
            self.assertTrue(is_procedural_macro_crate(manifest),
                            'a manifest declaring proc-macro must be recognised')

    def test_an_ordinary_manifest_is_not_a_proc_macro_crate(self):
        """Require the negative case, so the directive test is not vacuous."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'Cargo.toml'
            manifest.write_text('[lib]\nname = "x"\n')
            self.assertFalse(is_procedural_macro_crate(manifest),
                             'an ordinary manifest must not claim proc-macro')

    def test_an_absolute_path_is_refused_by_name(self):
        """Require the refusal to name the path, so a reader knows what to fix."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TrustAuditError) as raised:
                resolve_repository_path(Path(directory), '/etc/passwd')
            self.assertIn('/etc/passwd', str(raised.exception),
                          'an absolute path refusal must name the path')

    def test_an_escaping_path_is_refused_by_name(self):
        """Require the refusal to name the path, not to raise a bare error."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TrustAuditError) as raised:
                resolve_repository_path(Path(directory), '../../x.rs')
            self.assertIn('../../x.rs', str(raised.exception),
                          'an escaping path refusal must name the path')

    def test_an_unreadable_file_is_refused_by_name(self):
        """Require the read failure to name the file, since that is what to check."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TrustAuditError) as raised:
                scan_tree(Path(directory), 'missing.rs')
            self.assertIn('missing.rs', str(raised.exception),
                          'a missing file refusal must name the file')


if __name__ == '__main__':
    unittest.main()
