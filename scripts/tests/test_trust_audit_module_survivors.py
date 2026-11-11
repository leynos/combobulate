"""Kill the module-walk mutants a corpus sweep leaves alive (VO-9, VO-10).

The mutation census over :mod:`docs_validation.trust_audit` leaves survivors in
the module half of `matcher.py`: which declarations count as files, which
attribute a declaration's ``#[path]`` comes from, and where a declaration's
position is reported. The vocabulary rules live in
:mod:`test_trust_audit_matcher_survivors`; the split is by what each case needs
to know, so this module stays within the repository's module-length limit.

Each case supplies the one source the mutant needs, because a corpus of real
crates never spells the malformed or boundary form whose token arithmetic the
mutant moves.

Examples
--------
>>> scan('mod a;').modules
(ModuleReference(name='a', path=None, line=1, column=5, enclosing=()),)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import scan


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

class ModuleDeclarationBounds(unittest.TestCase):
    """Require a declaration that ends the file to be skipped, not to raise."""

    def test_a_trailing_mod_keyword_is_not_a_declaration(self):
        """Require the bounds check on the name, so the file's last token is safe.

        The ``mod`` keyword may be the final token. Reading the name without a
        bound raises ``IndexError`` out of the scan, which is not a refusal the
        caller can report — the whole audit fails instead.
        """
        self.assertEqual(modules('fn f() {}\nmod'), (),
                         'a mod keyword with no name must be skipped')

    def test_the_walk_continues_past_a_malformed_declaration(self):
        """Require ``continue`` rather than ``break``, so one bad entry is not fatal.

        ``mod;`` names nothing and is skipped. Stopping the walk there would
        hide every later declaration, including the one that makes the rest of
        the crate visible to the audit.
        """
        self.assertEqual(modules('mod;\nmod b;'), (('b', None),),
                         'a malformed declaration must not stop the module walk')

class ModuleBodiesAndNames(unittest.TestCase):
    """Require a declaration whose name is absent or malformed to be skipped."""

    def test_a_declaration_naming_something_that_is_not_an_identifier_is_skipped(self):
        """Require the identifier test, which is the whole guard for the name.

        ``mod 1;`` is not a declaration. A weakened ``or`` would treat the
        numeric literal as a module name and report a file the crate does not
        contain, so the audit would scan the wrong source.
        """
        self.assertEqual(modules('mod 1;'), (),
                         'a module name that is not an identifier must be skipped')

    def test_a_declaration_whose_name_runs_off_the_file_is_skipped(self):
        """Require the following-token bound, which keeps ``mod a`` readable.

        A declaration with no ``;`` after its name is malformed, and reading
        the token after the name without a bound raises ``IndexError`` from
        inside the scan. Skipping it leaves the rest of the walk intact.
        """
        self.assertEqual(modules('mod a'), (),
                         'a declaration ending at the file must be skipped')

    def test_a_malformed_declaration_does_not_hide_a_later_one(self):
        """Require ``continue`` rather than ``break`` in the module walk.

        ``mod;`` names nothing. Stopping at it would hide the declaration after
        it, and that declaration is what makes the file visible to the audit.
        """
        self.assertEqual(modules('mod a;\nmod;\nmod b;'),
                         (('a', None), ('b', None)),
                         'a malformed declaration must not stop the module walk')

class EnclosingInlineModules(unittest.TestCase):
    """Require a declaration inside ``mod x { … }`` to carry the enclosing name.

    The inline module is a module in its own right, so ``mod nested { mod
    trusted; }`` compiles ``src/nested/trusted.rs`` rather than
    ``src/trusted.rs``. Without the enclosing chain the audit resolves the
    second path, and where that file exists as a decoy it reports a clean scan
    of code the crate never compiles while the real module goes unaudited.
    """

    def test_an_inline_ancestor_is_carried_outermost_first(self):
        """Require the whole chain, ordered as the paths are nested."""
        reference, = scan('mod outer { mod inner { mod leaf; } }').modules
        self.assertEqual([(module.name, module.path) for module in reference.enclosing],
                         [('outer', None), ('inner', None)],
                         'every enclosing inline module must be reported, outermost first')

    def test_an_inline_module_keeps_its_own_path_attribute(self):
        """Carry the inline module's ``#[path]``, because it replaces its directory.

        ``#[path = "thread_files"] mod thread { mod local; }`` compiles
        ``thread_files/local.rs``, not ``thread/local.rs``. The value has to
        travel with the enclosing entry so the caller can substitute it; the
        scanner does not know the declaring file, so it cannot resolve it here.
        """
        reference, = scan('#[path = "thread_files"] mod thread { mod local; }').modules
        self.assertEqual([(module.name, module.path) for module in reference.enclosing],
                         [('thread', 'thread_files')],
                         'an inline module carrying #[path] must report the attribute value')

    def test_a_top_level_declaration_carries_no_ancestor(self):
        """Require the empty chain, so the plain search is unchanged."""
        reference, = scan('mod a;').modules
        self.assertEqual(reference.enclosing, (),
                         'a declaration outside any inline module must carry no ancestor')

    def test_a_declaration_after_an_inline_body_carries_no_ancestor(self):
        """Require the closing brace to end the inline module's scope.

        The ``}`` belongs to the module that holds the inline one, so a chain
        recorded at that index must not still name it. Keeping the name would
        send every later declaration into ``src/outer/``.
        """
        reference, = scan('mod outer { }\nmod a;').modules
        self.assertEqual(reference.enclosing, (),
                         'an inline module must stop enclosing at its closing brace')

    def test_a_sibling_inline_module_does_not_nest(self):
        """Require a closed inline module to be popped before the next opens."""
        first, second = scan('mod a { mod x; }\nmod b { mod c; }').modules
        self.assertEqual(([(module.name, module.path) for module in first.enclosing],
                          [(module.name, module.path) for module in second.enclosing]),
                         ([('a', None)], [('b', None)]),
                         'a sibling inline module must not become an ancestor')


class OnlyTheModKeywordDeclares(unittest.TestCase):
    """Require ``mod`` to be the word that declares, not merely a position."""

    def test_a_unit_struct_named_before_a_semicolon_is_not_a_module(self):
        """Require the ``or``, so a non-``mod`` identifier is still skipped.

        The guard skips a token that is not an identifier *or* is not spelled
        ``mod``. Weakening it to ``and`` skips only a token failing both, so
        every identifier becomes a candidate declaration. ``struct X;`` is
        valid Rust; under the mutant the ``X`` is read as a module name and a
        phantom reference to ``src/X.rs`` appears. The audit then refuses the
        crate because that file does not exist, so a sound proof is rejected
        for a declaration the author never wrote.
        """
        self.assertEqual(modules('struct X;'), (),
                         'a unit struct must not be read as a module declaration')

    def test_a_binding_named_before_a_semicolon_is_not_a_module(self):
        """Require the same guard for the binding form, which is also valid Rust.

        ``const K: u8 = 1;\\nlet x;`` is ordinary source. The mutant reports
        ``x`` as a module, and the audit refuses ``src/lib.rs:2:5 declares
        module 'x', which resolves to none of ['src/x.rs', 'src/x/mod.rs']``.
        """
        self.assertEqual(modules('const K: u8 = 1;\nlet x;'), (),
                         'a let binding must not be read as a module declaration')

    def test_a_real_declaration_after_ordinary_code_is_still_found(self):
        """Require the positive direction, so the above is not vacuous."""
        self.assertEqual(modules('struct X;\nmod a;'), (('a', None),),
                         'a real declaration after ordinary code must still be reported')


class ModuleAttributeRun(unittest.TestCase):
    """Require a ``#[path]`` run to be read only from complete spans."""

    def test_a_bracket_outside_any_attribute_does_not_supply_a_path(self):
        """Require the span-membership test, which is what makes a ``]`` an attribute's.

        A ``]`` that closes no attribute must not be read as one. Loosening the
        guard would let any bracketed expression before a declaration supply
        the ``#[path]`` value, so ``mod`` would compile one file while the audit
        read another.
        """
        self.assertEqual(modules('[path = "z.rs"] #[cfg(x)] mod b;'),
                         (('b', None),),
                         'a bracket outside an attribute must not name a module file')


if __name__ == '__main__':
    unittest.main()
