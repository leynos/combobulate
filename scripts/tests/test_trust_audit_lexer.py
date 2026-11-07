"""Hold the trust-audit lexer to each literal form's own terminator (VO-9).

`test_trust_audit.py` asks whether the *rule* reports the right words in the
right contexts. This module asks the prior question: whether the lexer hands the
rule the right tokens at all. The two are different failures with different
consequences — a wrong rule is a wrong audit, while a wrong lexer resumes
mid-literal and reports that literal's contents as code, which is a wrong audit
in the unsafe direction.

Each case therefore places a recognisable vocabulary word on both sides of the
construct under test. A lexer that stops short of the real terminator reports
the body; one that overruns loses the code after it. Asserting the whole token
stream, rather than merely that a word appears, is what separates a lexer that
read the form correctly from one that happened to agree on one input.

Examples
--------
>>> [token.text for token in tokenize("'a';")]
[';']
>>> literal_body('r#"a"#')
(3, 'a')
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import TrustAuditError, literal_body, tokenize


def stream(text: str) -> list[tuple[str, str]]:
    """Return each token's kind and text, which is what the matcher can see."""
    return [(token.kind.value, token.text) for token in tokenize(text)]


def texts(text: str) -> list[str]:
    """Return each token's text alone, for cases where the kind is not in doubt."""
    return [token.text for token in tokenize(text)]


def code_texts(text: str) -> list[str]:
    """Return the text of every token that is not a literal.

    A literal contributes one opaque token carrying its whole span, so a case
    about *where a literal ends* is clearer stated as "no literal leaked into
    these tokens" than as a list that repeats the span back.
    """
    return [token.text for token in tokenize(text) if token.kind.value != 'literal']


def refusal(build) -> str:
    """Return the message a call refused with, or an empty string when it did not."""
    try:
        build()
    except TrustAuditError as error:
        return str(error)
    return ''


class CharacterLiteralOrLifetime(unittest.TestCase):
    """Separate ``'a'`` from ``'a``, which differ by one quote and nothing else.

    Reading a character literal as a lifetime leaves its closing quote to open
    a new literal, and everything up to the next quote is then read as code.
    These cases pin both directions of that decision, and the exact number of
    characters each form consumes.
    """

    def test_a_character_literal_is_not_left_to_open_a_second_literal(self):
        """Require ``'x'`` to be consumed whole, with the code after it visible."""
        self.assertEqual(texts("let c = 'x';\nkani::assume(y);"),
                         ['let', 'c', '=', ';', 'kani', '::', 'assume', '(', 'y', ')', ';'],
                         'a character literal must not swallow the code after it')

    def test_an_escaped_character_literal_is_consumed_whole(self):
        """Require the escape branch, which a three-character lookahead cannot see.

        ``'\\''`` has its closing quote behind a backslash, so the ``<= index+2``
        test that recognises ``'x'`` is false here and only the escape branch
        keeps the literal from ending early.
        """
        self.assertEqual(texts("let c = '\\'';\nkani::assume(y);"),
                         ['let', 'c', '=', ';', 'kani', '::', 'assume', '(', 'y', ')', ';'],
                         'an escaped character literal must end at its real closing quote')

    def test_a_lifetime_does_not_consume_the_code_after_it(self):
        """Require a lifetime to stop at its identifier, leaving what follows."""
        self.assertEqual(texts("fn f<'a>(x: &'a u8) {}\nkani::assume(y);"),
                         ['fn', 'f', '<', '>', '(', 'x', ':', '&', 'u8', ')', '{', '}', 'kani',
                          '::', 'assume', '(', 'y', ')', ';'],
                         'a lifetime must consume only its own identifier')

    def test_a_character_literal_at_the_very_end_is_still_consumed(self):
        """Require the closing quote to be found when it is the last character.

        ``'x'`` with nothing after it is exactly the boundary where a
        length check written as ``>`` rather than ``>=`` misreads the literal as
        a lifetime and leaves a stray quote behind.
        """
        self.assertEqual(stream("'x'"), [], 'a literal at end of input is a literal, not a lifetime')

    def test_a_lifetime_at_the_very_end_is_consumed(self):
        """Require the identifier branch to run at end of input too."""
        self.assertEqual(stream('&' + "'a"), [('punct', '&')],
                         'a lifetime at end of input must not leave its name as code')

    def test_a_quote_before_an_identifier_that_is_not_closed_is_a_lifetime(self):
        """Require ``'ab`` to be a lifetime even when two characters follow it.

        The lifetime branch may consume an identifier of any length, so the
        three-character test must look for the *closing* quote rather than
        count characters to the end of the input.
        """
        self.assertEqual(stream("'ab kani"), [('ident', 'kani')],
                         'a multi-character lifetime must consume its whole name')

    def test_an_escaped_quote_in_a_character_literal_is_refused_when_unterminated(self):
        """Refuse ``'\\`` rather than resuming after the backslash."""
        self.assertIn('unterminated character literal', refusal(lambda: tokenize("'\\")),
                      'an unterminated escaped character literal must be refused by name')


class QuotedLiteralForms(unittest.TestCase):
    """Consume each string form to its own terminator, including raw fences."""

    def test_a_raw_string_with_one_hash_ends_at_quote_hash(self):
        """Require ``r#"…"#`` to end at ``"#``, not at the first ``"``."""
        self.assertEqual(code_texts('let s = r#"a "quoted" kani::assume(x);"#;\nkani::assume(y);'),
                         ['let', 's', '=', ';', 'kani', '::', 'assume', '(', 'y', ')', ';'],
                         'a raw string must not leak its body nor swallow later code')

    def test_a_raw_string_with_two_hashes_ends_at_two_hashes(self):
        """Require ``r##"a "# b"##`` to end at ``"##``, not at ``"#``."""
        self.assertEqual(code_texts('let s = r##"a "# b"##;\nkani::assume(y);'),
                         ['let', 's', '=', ';', 'kani', '::', 'assume', '(', 'y', ')', ';'],
                         'a two-hash raw string must end only at its own fence')

    def test_a_byte_string_opens_at_its_quote_rather_than_its_prefix(self):
        """Require the prefix and quote to be consumed together.

        Measuring the ``b`` alone would leave an empty ``b""`` to be read as a
        literal that ends before it starts, and the body would run to the next
        string in the file.
        """
        self.assertEqual(code_texts('if f(&b""[..]) {}\nkani::assume(y);'),
                         ['if', 'f', '(', '&', '[', '..', ']', ')', '{', '}', 'kani', '::',
                          'assume', '(', 'y', ')', ';'],
                         'an empty byte string must end at its own closing quote')

    def test_a_c_string_opens_at_its_quote_rather_than_its_prefix(self):
        """Require the same for ``c"…"``, which is a C string rather than a byte one."""
        self.assertEqual(code_texts('let s = c"a kani::assume(x);";\nkani::assume(y);'),
                         ['let', 's', '=', ';', 'kani', '::', 'assume', '(', 'y', ')', ';'],
                         'a C string must not leak its body')

    def test_adjacent_literals_stay_separate(self):
        """Require each literal to end at its own closing quote."""
        self.assertEqual(code_texts('g("a", "b");\nkani::assume(y);\nf(&b""[..]);\ng("c");'),
                         ['g', '(', ',', ')', ';', 'kani', '::', 'assume', '(', 'y', ')', ';',
                          'f', '(', '&', '[', '..', ']', ')', ';', 'g', '(', ')', ';'],
                         'each literal must end at its own closing quote')

    def test_an_escaped_quote_does_not_end_a_string(self):
        """Require a backslash to claim exactly the character after it."""
        self.assertEqual(code_texts('let s = "a \\" kani::assume() b";\nkani::assume(y);'),
                         ['let', 's', '=', ';', 'kani', '::', 'assume', '(', 'y', ')', ';'],
                         'an escaped quote must stay inside its literal')

    def test_a_literal_token_starts_where_the_literal_starts(self):
        """Require the position to be taken before the literal is consumed.

        The token's line and column describe its opening fence; taking them
        after the body has advanced the cursor would point at the closing quote.
        """
        literal = next(token for token in tokenize('let s = "a";') if token.kind.value == 'literal')
        self.assertEqual((literal.line, literal.column), (1, 9),
                         'a literal token is positioned at its opening quote')

    def test_a_literal_on_a_later_line_is_positioned_there(self):
        """Require the same when the literal follows a newline."""
        literal = next(token for token in tokenize('let s =\n  "a";') if token.kind.value == 'literal')
        self.assertEqual((literal.line, literal.column), (2, 3),
                         'a literal token carries the line its opening quote is on')

    def test_an_unterminated_string_names_the_form_it_wanted(self):
        """Require each unterminated form to be refused by its own name.

        The four names are what a record's author sees, so a message that said
        only "unterminated" would leave the mistake to be found by hand.
        """
        for text, expected in (('"abc', 'unterminated string'),
                               ('b"abc', 'unterminated byte or C string'),
                               ('c"abc', 'unterminated byte or C string'),
                               ('r#"abc', 'unterminated raw string')):
            with self.subTest(text=text):
                self.assertIn(expected, refusal(lambda t=text: tokenize(t)),
                              'an unterminated literal must be refused by its own name')


class PunctuatorPreference(unittest.TestCase):
    """Prefer the longest punctuator, because a split one changes what follows."""

    def test_every_multi_character_punctuator_is_taken_whole(self):
        """Require each listed form to win over its prefix."""
        for text, expected in (('a::b', '::'), ('a->b', '->'), ('a=>b', '=>'), ('a..=b', '..='),
                               ('a&&b', '&&'), ('a||b', '||'), ('a!=b', '!='), ('a==b', '=='),
                               ('a<=b', '<='), ('a>=b', '>=')):
            with self.subTest(text=text):
                self.assertIn(('punct', expected), stream(text),
                              'the longest punctuator must be preferred')

    def test_a_two_dot_range_is_preferred_over_a_single_dot(self):
        """Require ``..`` to beat ``.``, which would otherwise split the range."""
        self.assertEqual([kind for kind, _ in stream('a..b')],
                         ['ident', 'punct', 'ident'],
                         'a range must be one punctuator, not two dots')

    def test_an_unmatched_opener_is_taken_one_character_at_a_time(self):
        """Require the fallback to consume exactly one character.

        ``::<`` is listed as a punctuator only when it appears; a single ``<``
        must stay a single token so the matcher's bracket walks still balance.
        """
        self.assertEqual(stream('a::<b>'),
                         [('ident', 'a'), ('punct', '::'), ('punct', '<'), ('ident', 'b'),
                          ('punct', '>')],
                         'a lone angle bracket must stay a single token')


class TriviaAndPositions(unittest.TestCase):
    """Consume comments and whitespace without moving the tokens that follow."""

    def test_a_line_comment_ends_at_the_newline(self):
        """Require the code after a line comment to keep its own line number."""
        self.assertEqual([(token.text, token.line)
                          for token in tokenize('// kani::assume(x);\nkani::stub(a);')],
                         [('kani', 2), ('::', 2), ('stub', 2), ('(', 2), ('a', 2), (')', 2),
                          (';', 2)],
                         'a line comment must end at its newline')

    def test_a_line_comment_at_end_of_input_consumes_the_rest(self):
        """Require the no-newline branch, which has no terminator to find."""
        self.assertEqual(stream('kani::assume(x); // trailing'),
                         [('ident', 'kani'), ('punct', '::'), ('ident', 'assume'), ('punct', '('),
                          ('ident', 'x'), ('punct', ')'), ('punct', ';')],
                         'a final line comment must consume to end of input')

    def test_a_nested_block_comment_ends_at_its_outer_close(self):
        """Require nesting depth to be counted, not the first ``*/`` found."""
        self.assertEqual(texts('/* /* kani::assume(x); */ kani::stub(a); */ kani::should_panic();'),
                         ['kani', '::', 'should_panic', '(', ')', ';'],
                         'a nested block comment must not end at the inner terminator')

    def test_a_multiline_comment_counts_lines(self):
        """Require newlines inside a comment to be counted for the code after it."""
        self.assertEqual([(token.text, token.line) for token in tokenize('/*\n\n*/ a')],
                         [('a', 3)], 'a comment spanning two newlines must advance three lines')

    def test_carriage_return_is_trivia(self):
        """Require CRLF to be whitespace rather than an identifier."""
        self.assertEqual(texts('a\r\nb'), ['a', 'b'], 'a carriage return is trivia')

    def test_an_unterminated_block_comment_names_where_it_opened(self):
        """Require the opening position, which is where the mistake is."""
        self.assertIn('opened at line 1, column 1', refusal(lambda: tokenize('/* /* */')),
                      'an unterminated block comment must name where it opened')

    def test_an_empty_block_comment_consumes_exactly_its_four_characters(self):
        """Require ``/**/`` to close on its own ``*/`` rather than run past it.

        The opener and the closer are adjacent here, so a lexer that consumes
        one character too many on either side reads the closer as body and then
        reports the comment unterminated — or, worse, resumes inside it.
        """
        self.assertEqual(texts('/**/ x'), ['x'], 'an empty block comment must close at its own */')

    def test_a_block_comment_closes_immediately_after_its_body(self):
        """Require the closer to be recognised when it follows the body directly."""
        self.assertEqual(texts('/*k*/ y'), ['y'], 'a comment with no spaces must close at */')

    def test_a_closer_consumes_only_its_own_two_characters(self):
        """Require ``*/`` to claim exactly ``*`` and ``/``, not the code after them.

        A closer measured as three characters eats the first character of
        whatever follows the comment. Where that character is whitespace the
        mistake is invisible, because trivia consumption absorbs it; here the
        comment is followed immediately by an identifier, and eating its first
        letter turns ``x`` into nothing at all.
        """
        self.assertEqual(texts('/*a*/x'), ['x'],
                         'a block comment closer must not consume the code after it')


class LiteralBodies(unittest.TestCase):
    """Recover a literal's content, which is what a proc-macro crate is scanned for.

    :func:`literal_body` is the only way a string's *content* reaches the
    matcher, so an off-by-one here is an under-report: a trust word spelled at
    the end of a raw literal would never be seen.
    """

    def test_every_raw_fence_yields_the_whole_body(self):
        """Require the closing fence to be measured as the opening one minus its prefix.

        A raw string opens with ``r#"`` and closes with ``"#``. Measuring the
        terminator symmetrically drops the body's last character, and for a
        proc-macro crate that means a trust word at the very end is missed.
        """
        for source, expected in (('r"a"', 'a'), ('r#"a"#', 'a'), ('r##"ab"##', 'ab'),
                                 ('br#"x"#', 'x')):
            with self.subTest(source=source):
                self.assertEqual(literal_body(source)[1], expected,
                                 'a raw literal must yield its whole body')

    def test_a_raw_fence_reports_where_the_body_starts(self):
        """Require the offset to be the fence's own width."""
        self.assertEqual([literal_body(source)[0] for source in
                          ('r"a"', 'r#"a"#', 'r##"ab"##', 'br#"x"#')],
                         [2, 3, 4, 4],
                         'the offset is the opening fence width')

    def test_an_empty_body_is_empty_at_every_form(self):
        """Require empty content rather than a stray quote."""
        for source in ('r""', 'r#""#', 'b""', 'c""', '""'):
            with self.subTest(source=source):
                self.assertEqual(literal_body(source)[1], '', 'an empty literal has an empty body')

    def test_a_prefixed_literal_reports_its_prefix_width(self):
        """Require ``b``/``c`` to be counted, since the quote follows them."""
        self.assertEqual([literal_body(source) for source in ('b"ab"', 'c"ab"', '"ab"')],
                         [(2, 'ab'), (2, 'ab'), (1, 'ab')],
                         'a prefixed literal starts its body after the prefix and quote')

    def test_a_non_literal_is_refused_by_name(self):
        """Refuse a token that is not a string, which means a caller passed the wrong kind."""
        self.assertIn('is not a string literal', refusal(lambda: literal_body('abc')),
                      'a non-literal must be refused as such')


if __name__ == '__main__':
    unittest.main()
