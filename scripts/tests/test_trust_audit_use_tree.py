"""Kill the mutants in the ``use``-tree reader the matcher depends on (DL-17).

``use kani::assume;`` and ``use kani as k;`` decide which names in a file reach
a verifier's trust surface, so the reader that finds each statement's root,
alias, and end is load-bearing for the audit's soundness. The cases here were
left alive by the mutation census over :mod:`docs_validation.trust_audit`
because the outcome suites assert what the matcher reports and never what the
reader hands it.

Two families are equivalents rather than gaps. ``statement_end``'s ``start``
bound cannot matter: a ``use`` is lexed with its ``;`` present, so the first
search succeeds before the bound is reached. ``use_alias``'s brace check before
``as`` is the guard that keeps a grouped import from renaming its crate; a
mutant that dropped it is killed here rather than argued, since
``use kani::{assume as a};`` is a real way to write the import.

Examples
--------
>>> statement_end(tokenize('use kani as k;'), 0)
5
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit.lexer import tokenize
from docs_validation.trust_audit.use_tree import alias_bindings, statement_end, use_alias, use_root


class StatementBounds(unittest.TestCase):
    """Require a ``use`` tree's root to be read up to its own semicolon."""

    def test_the_semicolon_ends_the_search(self):
        """Require the search to report the first ``;`` so a later statement is not read."""
        tokens = tokenize('use a; b;')
        self.assertEqual(statement_end(tokens, 0), 2,
                         'the first semicolon must end the statement')

    def test_a_statement_without_a_semicolon_ends_at_end_of_file(self):
        """Require the end of file to be the bound when no ``;`` appears."""
        tokens = tokenize('use a')
        self.assertEqual(statement_end(tokens, 0), len(tokens),
                         'a statement with no semicolon must end at the last token')

class ImportedRootAliases(unittest.TestCase):
    """Require an aliased trust root to be recognised as the root it names.

    Rust renames a crate on import: after ``use kani as k;``, ``k::assume`` is
    the same call as ``kani::assume``. A reader that returned only the literal
    root would leave the matcher reporting nothing for such a file, and the
    audit would describe it as trust-free while it assumed exactly what the
    vocabulary names.
    """

    def test_a_renamed_crate_is_reported_alongside_its_root(self):
        """Require `use kani as k;` to bind both names."""
        self.assertEqual(alias_bindings(tokenize('use kani as k;'), 'kani'),
                         frozenset({'kani', 'k'}),
                         'a renamed trust root must be reported with its alias')

    def test_an_unaliased_import_reports_only_the_root(self):
        """Require the plain form to keep working, so the fix is not a swap."""
        self.assertEqual(alias_bindings(tokenize('use kani::assume;'), 'kani'),
                         frozenset({'kani'}),
                         'a named import must not invent an alias')

    def test_an_alias_of_another_crate_is_not_reported(self):
        """Require an unrelated alias to stay silent, so the rule is not a wildcard."""
        self.assertEqual(alias_bindings(tokenize('use other as k;'), 'kani'),
                         frozenset({'kani'}),
                         'only an alias of the named root may be reported')

    def test_a_glob_import_binds_no_crate_alias(self):
        """Require `use kani::*;` not to be read as renaming the crate.

        A glob binds items, not the crate name, so ``k::assume`` is unrelated
        to it. Reading the statement as an alias would make every ``k::`` path
        trust.
        """
        self.assertEqual(alias_bindings(tokenize('use kani::*;'), 'kani'),
                         frozenset({'kani'}),
                         'a glob import must not become a crate alias')

    def test_a_grouped_import_renaming_a_member_binds_no_crate_alias(self):
        """Require `use kani::{assume as a};` not to rename the crate itself.

        The ``as`` belongs to the grouped member, not to the crate. Reading it
        as a crate alias would make ``a::`` — a name the file never binds —
        match every qualified ``a::`` path.
        """
        self.assertEqual(alias_bindings(tokenize('use kani::{assume as a};'), 'kani'),
                         frozenset({'kani'}),
                         'a grouped member alias must not rename the crate')


if __name__ == '__main__':
    unittest.main()
