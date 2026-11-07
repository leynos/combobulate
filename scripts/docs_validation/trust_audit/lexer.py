"""Lex Rust far enough to tell code from comments and literals (VO-9).

The scanner's whole job is to report trusted vocabulary in *code position*, so
this lexer has one obligation: never let text inside a comment or a literal be
mistaken for code, and never let code be mistaken for trivia. It never splits a
literal into identifiers, so `kani::assume` inside a doc comment or a string
cannot be read as a call. String literals are still returned, as one opaque
token, because two callers need them: `#[path = "…"]` resolves a module target
from one, and a proc-macro crate's literals can become code and are scanned
separately. Comments, character literals, and lifetimes are dropped outright.

Rust has more literal forms than a `split()` understands, and each one has a
distinct terminator: `r#"…"#` ends at `"#`, `br##"…"##` at `"##`, `c"…"` is a
C string rather than a byte string, and `'a` is a lifetime while `'a'` is a
character. Getting this wrong fails in the worst direction — the lexer stops
short of the real terminator, resumes mid-literal, and reports the literal's
contents as code. So this module models each form explicitly and raises
:class:`TrustAuditError` rather than guessing when a form never terminates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class TrustAuditError(Exception):
    """Report source the scanner refuses to audit; e.g. an unterminated block comment."""


class Kind(Enum):
    """Distinguish an identifier, one punctuator, and one whole string literal."""

    IDENT = 'ident'
    PUNCT = 'punct'
    LITERAL = 'literal'


@dataclass(frozen=True, slots=True)
class Token:
    """One code token with its 1-based position; e.g. `assume` at line 7, column 5."""

    kind: Kind
    text: str
    line: int
    column: int


# A raw string's opening fence: `r"`, `r#"`, `br##"`, `cr"`, and so on.
_RAW_START = re.compile(r'(?:b|c)?r(#*)"')
# A byte or C string's opening quote, tried only when no raw fence matched.
_PREFIXED_QUOTE = re.compile(r'(?:b|c)"')
_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
# Multi-character punctuators that change how a following `::` reads.
_PUNCTUATORS = ('::', '->', '=>', '..=', '..', '&&', '||', '::<', '!=', '==', '<=', '>=')


class _Cursor:
    """Advance over one source string, tracking 1-based line and column."""

    def __init__(self, text: str) -> None:
        """Start at the first character of ``text``, on line 1, column 1."""
        self.text = text
        self.index = 0
        self.line = 1
        self.column = 1
        # A literal's token is positioned where it starts, before it is consumed.
        self.line_before = 1
        self.column_before = 1

    @property
    def at_end(self) -> bool:
        """Report whether every character has been consumed."""
        return self.index >= len(self.text)

    def starts(self, prefix: str) -> bool:
        """Report whether the source at the cursor begins with ``prefix``."""
        return self.text.startswith(prefix, self.index)

    def take(self, count: int) -> str:
        """Consume ``count`` characters and return them, updating the position."""
        chunk = self.text[self.index:self.index + count]
        for character in chunk:
            if character == '\n':
                self.line, self.column = self.line + 1, 1
            else:
                self.column += 1
        self.index += count
        return chunk

    def skip_until(self, terminator: str, what: str) -> None:
        """Consume through ``terminator``; refuse to continue if it is absent."""
        end = self.text.find(terminator, self.index)
        if end < 0:
            raise TrustAuditError(f'unterminated {what} at line {self.line}, column {self.column}')
        self.take(end + len(terminator) - self.index)


def tokenize(text: str) -> tuple[Token, ...]:
    """Return the code tokens of a Rust source, dropping every comment and literal.

    Parameters
    ----------
    text
        Rust source text, which need not be a complete or valid crate.

    Returns
    -------
    tuple[Token, ...]
        Tokens in source order. A comment contributes nothing, and a string is
        one opaque ``LITERAL`` token carrying its content, so a vocabulary word
        inside either is never split into an identifier.

    Raises
    ------
    TrustAuditError
        If a block comment, string, raw string, or character literal never
        terminates. The scan fails closed rather than resuming mid-literal,
        because a resumed scan reads the literal's contents as code.

    Examples
    --------
    tokenize('kani::assume(false) // kani::admit') yields `kani`, `::`,
    `assume`, and the punctuation after it, and nothing for the comment.
    """
    cursor = _Cursor(text)
    tokens: list[Token] = []
    while not cursor.at_end:
        if _skip_trivia(cursor):
            continue
        literal = _consume_quote_literal(cursor)
        if literal is not None:
            tokens.append(Token(Kind.LITERAL, literal, cursor.line_before, cursor.column_before))
            continue
        matched = _IDENT.match(cursor.text, cursor.index)
        if matched:
            tokens.append(Token(Kind.IDENT, matched[0], cursor.line, cursor.column))
            cursor.take(len(matched[0]))
            continue
        if _skip_character_literal_or_lifetime(cursor):
            continue
        # The position is read before consuming, because ``_punct`` advances the
        # cursor past the token it returns. Reading afterwards would report a
        # punctuator's *end*, so an unclosed group would name the column after
        # the bracket the reader has to fix.
        line, column = cursor.line, cursor.column
        tokens.append(Token(Kind.PUNCT, _punct(cursor), line, column))
    return tuple(tokens)


def _skip_trivia(cursor: _Cursor) -> bool:
    """Consume whitespace and comments; report whether anything was consumed."""
    started = cursor.index
    while not cursor.at_end:
        if cursor.text[cursor.index] in ' \t\r\n':
            cursor.take(1)
        elif cursor.starts('//'):
            newline = cursor.text.find('\n', cursor.index)
            cursor.take(len(cursor.text) - cursor.index if newline < 0 else newline - cursor.index)
        elif cursor.starts('/*'):
            _skip_block_comment(cursor)
        else:
            break
    return cursor.index != started


def _skip_block_comment(cursor: _Cursor) -> None:
    """Consume a block comment, honouring Rust's nesting rule.

    Nesting is why a naive `find('*/')` is wrong: in `/* a /* b */ c */` it stops
    inside the comment, and everything after `c` is then read as code.
    """
    start_line, start_column = cursor.line, cursor.column
    cursor.take(2)
    depth = 1
    while depth:
        if cursor.at_end:
            raise TrustAuditError(
                f'unterminated block comment opened at line {start_line}, column {start_column}'
            )
        if cursor.starts('/*'):
            cursor.take(2)
            depth += 1
        elif cursor.starts('*/'):
            cursor.take(2)
            depth -= 1
        else:
            cursor.take(1)


def _consume_quote_literal(cursor: _Cursor) -> str | None:
    """Consume a raw, byte, or C string and return its whole source span.

    The span keeps the prefix and fences so that :func:`literal_body` can both
    recover the content and locate it inside the token. ``None`` means no
    string starts at the cursor, which is how the caller tells a literal from
    an identifier.
    """
    cursor.line_before, cursor.column_before = cursor.line, cursor.column
    start = cursor.index
    matched = _RAW_START.match(cursor.text, cursor.index)
    if matched:
        # A raw string closes with the same number of `#` it opened with:
        # `r#"…"#` ends at `"#`, and `r##"…"##` at `"##`.
        fence = f'"{matched[1]}'
        cursor.take(matched.end() - start)
        cursor.skip_until(fence, 'raw string')
        return cursor.text[start:cursor.index]
    # `_PREFIXED_QUOTE` matches the prefix *and* the opening quote, so its whole
    # match is the opening. Measuring the `b`/`c` alone and adding one would
    # consume the quote of an empty `b""` twice, and the body would then run on
    # to the next string in the file, reporting that string's contents as code.
    opening = _PREFIXED_QUOTE.match(cursor.text, cursor.index)
    if opening or cursor.starts('"'):
        what = 'byte or C string' if opening else 'string'
        cursor.take(len(opening[0]) if opening else 1)
        _consume_escaped_body(cursor, '"', what)
        return cursor.text[start:cursor.index]
    return None


def literal_body(source: str) -> tuple[int, str]:
    """Return a string literal's content offset and content.

    Parameters
    ----------
    source
        A literal token's text, as returned by :func:`tokenize`.

    Returns
    -------
    tuple[int, str]
        The content's offset within ``source`` and the content itself, so a
        caller can report a position inside the literal exactly.

    Raises
    ------
    TrustAuditError
        If ``source`` is not a string literal, which would mean a caller has
        passed the wrong token kind.

    Examples
    --------
    literal_body('r#"a"#') is ``(3, 'a')`` and literal_body('"a"') is
    ``(1, 'a')``, so both report the same content at different offsets.

    The closing fence is the opening fence without its leading ``r``/``b``/
    ``c``: a raw string opens with ``r#"`` and closes with ``"#``. Measuring it
    as the symmetric ``"#"`` a reader might expect would drop the body's last
    character, and for a proc-macro crate that means a trust item spelled at
    the very end of a raw literal is never reported.
    """
    matched = _RAW_START.match(source)
    if matched:
        terminator = f'"{matched[1]}'
        return matched.end(), source[matched.end():len(source) - len(terminator)]
    for prefix in ('b"', 'c"'):
        if source.startswith(prefix):
            return len(prefix), source[len(prefix):-1]
    if source.startswith('"'):
        return 1, source[1:-1]
    raise TrustAuditError(f'{source!r} is not a string literal')


def _consume_escaped_body(cursor: _Cursor, terminator: str, what: str) -> str:
    """Consume through the closing quote and return the body, escapes included.

    A backslash escapes exactly one following character, which is what keeps
    ``"a\\""`` from ending at the escaped quote. The escape is returned verbatim
    because no caller interprets the text; the terminator is what matters here.

    The failure names the literal's *opening* line and column. By the time the
    end is reached the cursor sits at EOF, and reporting that position would
    point at the end of the file instead of the mistake.
    """
    start, start_line, start_column = cursor.index, cursor.line, cursor.column
    while not cursor.at_end:
        if cursor.starts('\\'):
            cursor.take(2)
        elif cursor.starts(terminator):
            body = cursor.text[start:cursor.index]
            cursor.take(1)
            return body
        else:
            cursor.take(1)
    raise TrustAuditError(f'unterminated {what} at line {start_line}, column {start_column}')


def _consume_character_literal(cursor: _Cursor) -> str:
    """Consume a character literal and return its body, escapes included."""
    cursor.take(1)
    return _consume_escaped_body(cursor, "'", 'character literal')


def _skip_character_literal_or_lifetime(cursor: _Cursor) -> bool:
    """Consume a character literal or a lifetime; report whether one started here.

    `'a` is a lifetime and `'a'` is a character, and they differ by one quote.
    Reading a character literal as a lifetime would leave the closing quote to
    start a *new* literal and swallow the following code, so the two are
    separated here rather than left to a later stage.
    """
    if not cursor.starts("'"):
        return False
    following = cursor.text[cursor.index + 1:cursor.index + 2]
    if following == '\\':
        _consume_character_literal(cursor)
        return True
    if len(cursor.text) >= cursor.index + 3 and cursor.text[cursor.index + 2] == "'":
        cursor.take(3)
        return True
    cursor.take(1)
    matched = _IDENT.match(cursor.text, cursor.index)
    if matched:
        cursor.take(len(matched[0]))
    return True


def _punct(cursor: _Cursor) -> str:
    """Consume one punctuator, preferring the longest form."""
    for candidate in _PUNCTUATORS:
        if cursor.starts(candidate):
            cursor.take(len(candidate))
            return candidate
    return cursor.take(1)
