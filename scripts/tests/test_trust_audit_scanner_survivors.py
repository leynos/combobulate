"""Kill the cursor and literal mutants a corpus sweep leaves alive (VO-9).

The mutation census over :mod:`docs_validation.trust_audit.lexer` leaves
survivors where the mutation moves a cursor bound by one character or replaces
a literal's body with a placeholder. Valid Rust never puts a terminator at
offset zero, never spells a character literal in the last three characters of
a file, and never asks a caller to observe a body the lexer discards, so no
corpus file distinguishes these mutants. Each case here supplies the exact
boundary, stated at the helper that owns it where the whole-file consequence
would be indistinguishable from correct behaviour.

Three families are equivalents rather than gaps, and this module records why.
``_Cursor.line_before`` and ``_Cursor.column_before`` are overwritten by
``_consume_quote_literal`` before any caller reads them, so neither the
``None`` nor the ``2`` variant can be observed. ``_skip_trivia``'s newline
guard agrees with ``< 0`` under ``<= 0`` and ``< 1`` because the search begins
at the ``/`` of the comment marker, so a found position is never ``0``. The
same function's ``len(cursor.text) + cursor.index`` variant over-counts at an
end-of-file comment, but ``take`` slices the string, so the slice stops at the
end either way; the cursor still lands on the same index and the loop still
exits, leaving the token stream identical. Its ``return`` in place of ``break``
is equivalent too: both forms stop at the first non-trivia token, and the
caller reads the report only for truthiness. When trivia was consumed the
original reports true and loops once more before stopping at that same token;
the mutant stops one iteration earlier at the same cursor position, so the
token is lexed once from the same index under either form. Verified over
sources with leading whitespace, leading comments, and trailing trivia.

Two further equivalents belong to the caller's scan rather than the lexer and
are argued in :mod:`test_trust_audit_attribute_survivors`: the exported name
bound in ``_module_references`` and the walk start in ``_path_attribute``.

Examples
--------
>>> [token.text for token in tokenize("'+'")]
[]
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit.lexer import (
    _Cursor,
    _consume_escaped_body,
    tokenize,
)


def texts(source: str) -> list[str]:
    """Return the text of every token the lexer produces."""
    return [token.text for token in tokenize(source)]


class TerminatorAtTheCursor(unittest.TestCase):
    """Require a terminator the search finds at offset zero to be found."""

    def test_a_terminator_at_the_first_character_is_consumed(self):
        """Require ``< 0`` rather than ``<= 0`` or ``< 1`` in the absent test.

        ``find`` reports ``0`` for a terminator at the cursor's own position,
        which is a *successful* search. Treating zero as "not found" -- which
        ``<= 0`` and ``< 1`` both do -- refuses source whose literal closes
        immediately, and the refusal names the cursor rather than a real
        problem. A raw string's fence is searched from just after its opening
        quote, so this case is stated at the cursor rather than through
        :func:`tokenize`.
        """
        cursor = _Cursor('"abc')
        cursor.skip_until('"', 'string')
        self.assertEqual(cursor.index, 1,
                         'a terminator at offset zero must be consumed, not refused')


class EscapedBodyValue(unittest.TestCase):
    """Require the escaped body to be the consumed text, not a placeholder."""

    def test_the_body_is_the_text_between_the_quotes(self):
        """Require the slice, since ``None`` looks like "no body".

        ``_consume_escaped_body`` returns the body alongside advancing the
        cursor. Replacing the slice with ``None`` leaves the cursor in the same
        place, so a caller that only checks the cursor cannot see the mutant;
        the return value is the contract. The cursor assertion keeps the two
        observations separate, so a mutant that stopped consuming is also
        caught here.
        """
        cursor = _Cursor('abc" rest')
        self.assertEqual(_consume_escaped_body(cursor, '"', 'string'), 'abc',
                         'the escaped body must be the text the helper consumed')
        self.assertEqual(cursor.index, 4,
                         'the helper must consume through its terminator')


class CharacterLiteralAtEndOfFile(unittest.TestCase):
    """Require a three-character literal at the end of the file to close."""

    def test_a_character_literal_in_the_last_three_characters_is_consumed(self):
        """Require ``>= cursor.index + 3``, the length ``'x'`` needs.

        The guard asks whether the closing quote is still inside the text.
        With the literal at the very end, the closing quote is the last
        character and ``len(text)`` is exactly ``index + 3``. Requiring
        ``> index + 3`` or ``>= index + 4`` refuses the form, reads ``'x`` as a
        lifetime, and then lexes the stray closing quote as the start of a new
        literal -- so the ``+`` inside the literal is reported as code, which
        for a proc-macro crate is a trust item the author never wrote.
        """
        self.assertEqual(texts("'+'"), [],
                         'a character literal at end of file must leave no token behind')


if __name__ == '__main__':
    unittest.main()
