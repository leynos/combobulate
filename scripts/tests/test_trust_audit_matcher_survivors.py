"""Kill the matcher mutants a corpus sweep leaves alive (VO-9, VO-10).

The mutation census over :mod:`docs_validation.trust_audit` leaves survivors in
`matcher.py` where the mutation changes a *reported position*, a *module
reference*, or which of two overlapping rules claims a token. The existing
suites assert that the right words are reported; they rarely assert *where*, and
they never spell the module-declaration forms whose token arithmetic the mutants
move. Each case here supplies the one source the mutant needs.

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
>>> scan('mod a;').modules
(ModuleReference(name='a', path=None, line=1, column=5),)
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


def modules(text: str):
    """Return the module references a scan reports, as ``(name, path)`` pairs."""
    return tuple((reference.name, reference.path) for reference in scan(text).modules)


class ModuleDeclarations(unittest.TestCase):
    """Require every ``mod x;`` form to be found, and nothing else."""

    def test_a_plain_declaration_is_reported(self):
        """Require the basic ``mod x;`` reference, which the walk exists to find."""
        self.assertEqual(modules('mod a;'), (('a', None),),
                         'a bare module declaration must be reported')

    def test_a_declaration_with_an_inline_body_is_not_a_file(self):
        """Require ``mod x { … }`` to be skipped, since its body is already lexed.

        Reporting it would send the caller looking for a file that the crate
        does not compile, and a missing file refuses an otherwise sound proof.
        """
        self.assertEqual(modules('mod a { fn f() {} }'), (),
                         'a module with an inline body compiles no separate file')

    def test_a_declaration_after_an_inline_body_is_still_found(self):
        """Require the walk to continue past a skipped declaration.

        A walk that stopped at the first non-file module would never reach the
        declarations after it, so their trust would be invisible — the failing
        direction DL-17 exists to prevent.
        """
        self.assertEqual(modules('mod a { }\nmod b;'), (('b', None),),
                         'a declaration after an inline module must still be reported')

    def test_every_declaration_is_reported_rather_than_the_first(self):
        """Require the whole list, not the first entry."""
        self.assertEqual(modules('mod a;\nmod b;'), (('a', None), ('b', None)),
                         'each module declaration must be reported')

    def test_a_declaration_at_the_very_end_is_found(self):
        """Require the ``mod x;`` form to be recognised when the file ends there.

        The walker reads two tokens past ``mod``; reading further would drop the
        last declaration of every file, which is where a ``#[path]`` module most
        often sits.
        """
        self.assertEqual(modules('fn f() {}\nmod a;'), (('a', None),),
                         'the last declaration in a file must be reported')

    def test_a_mod_fn_name_is_not_a_declaration(self):
        """Require the ``mod`` keyword test, so a path ending in ``mod`` is skipped."""
        self.assertEqual(modules('a::mod;'), (),
                         'a path segment spelled mod is not a declaration')

    def test_the_declaration_position_is_the_module_name(self):
        """Require the reported line and column to locate the name a reader edits."""
        module, = scan('fn f() {}\nmod a;').modules
        self.assertEqual((module.line, module.column), (2, 5),
                         'a module reference must point at the module name')

    def test_an_attribute_names_the_file_the_crate_compiles(self):
        """Require the ``#[path]`` value, which overrides Rust's bare search."""
        self.assertEqual(modules('#[path = "x.rs"] mod a;'), (('a', 'x.rs'),),
                         'a path attribute must name the file the declaration compiles')

    def test_an_unrelated_attribute_before_the_path_is_walked_over(self):
        """Require the walk to continue past an attribute that is not ``#[path]``.

        The corpus holds ``#[path]`` first, so the converse order — which a real
        crate writes whenever an allow sits above the path — is what would fall
        back to the bare search and audit the wrong file.
        """
        self.assertEqual(modules('#[allow(dead_code)]\n#[path = "x.rs"]\nmod a;'),
                         (('a', 'x.rs'),),
                         'a non-path attribute must not hide the path attribute below it')

    def test_an_attribute_at_the_very_start_of_the_file_is_walked(self):
        """Require the backwards walk to reach index zero.

        A walk bounded at index 1 would stop before the attribute that opens the
        file, so ``#[path]`` in the first position would be missed.
        """
        self.assertEqual(modules('#[path = "x.rs"] mod a;')[0][1], 'x.rs',
                         'an attribute at the start of the file must be read')

    def test_a_path_after_a_visibility_modifier_is_read(self):
        """Require the visibility step, so ``pub(crate) mod x;`` keeps its path."""
        self.assertEqual(modules('#[path = "x.rs"] pub(crate) mod a;'),
                         (('a', 'x.rs'),),
                         'a visibility modifier between attribute and declaration must be crossed')


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
