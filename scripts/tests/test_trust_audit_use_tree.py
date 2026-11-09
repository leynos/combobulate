"""Kill the mutants in the ``use``-tree reader the matcher depends on (DL-17).

``use kani::assume;`` and ``use kani as k;`` decide which names in a file reach
a verifier's trust surface, so the reader that finds each statement's root,
alias, and end is load-bearing for the audit's soundness. The cases here were
left alive by the mutation census over :mod:`docs_validation.trust_audit`
because the outcome suites assert what the matcher reports and never what the
reader hands it.

Two families are equivalents rather than gaps. ``statement_end``'s ``start``
bound cannot matter: a ``use`` is lexed with its ``;`` present, so the first
search succeeds before the bound is reached. ``use_alias``'s exclusion of a
rename below the root is the guard that keeps a member import from renaming its
crate; a mutant that dropped it is killed here rather than argued, since
``use kani::{assume as a};`` is a real way to write the import.

The grouped spelling ``use kani::{self as k};`` is the same renaming written
with a brace, and a reader that treated every brace as "a member alias" left
``k::assume`` unreported — a file described as trust-free while it assumed
exactly what the vocabulary names. That case is why the brace is no longer what
the reader keys on.

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

from docs_validation.trust_audit.matcher import scan
from docs_validation.trust_audit.lexer import tokenize
from docs_validation.trust_audit.use_tree import (
    alias_bindings, statement_end, use_alias, use_aliases, use_root,
)


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

    def test_a_grouped_self_alias_binds_the_crate(self):
        """Require `use kani::{self as k};` to bind ``k`` for the crate.

        ``self`` inside a grouped import names the crate itself, so ``self as
        k`` is the same renaming the plain form makes. Reading the brace before
        the ``as`` as "this is a member alias" made the matcher report nothing
        for ``k::assume``, and the audit described a file as trust-free while
        it assumed exactly what the vocabulary names.
        """
        self.assertEqual(alias_bindings(tokenize('use kani::{self as k};'), 'kani'),
                         frozenset({'kani', 'k'}),
                         'a grouped self alias must rename the crate')

    def test_a_grouped_self_alias_beside_a_member_alias_binds_both_names(self):
        """Require the two grouped aliases in one statement to stay distinguishable.

        Only ``self`` renames the crate; the sibling member rename does not. A
        reader that took the statement's last ``as`` would report ``a`` here and
        miss ``k``.
        """
        tokens = tokenize('use kani::{assume as a, self as k};')
        self.assertEqual(alias_bindings(tokens, 'kani'), frozenset({'kani', 'k'}),
                         'only the self member of a grouped import renames the crate')

    def test_a_path_alias_past_the_root_binds_no_crate_alias(self):
        """Require `use kani::assume as a;` to stay a member alias.

        The qualified path is the same renaming the grouped form writes with
        braces, so the rule that excludes it must cover both spellings. A rule
        that only excluded a brace would report ``a`` here and make every
        ``a::`` path trust.
        """
        self.assertEqual(alias_bindings(tokenize('use kani::assume as a;'), 'kani'),
                         frozenset({'kani'}),
                         'a rename of a name below the root must not rename the crate')

    def test_an_absolute_root_alias_is_still_read(self):
        """Require `use ::kani as k;` to bind the alias, since the leading `::` is syntax.

        An edition-2015-style absolute path names the same crate. A reader that
        required the root to be the statement's *first* token would miss it.
        """
        self.assertEqual(alias_bindings(tokenize('use ::kani as k;'), 'kani'),
                         frozenset({'kani', 'k'}),
                         'a leading :: must not hide the crate being renamed')


class GroupedAliasReachesTheMatcher(unittest.TestCase):
    """Require a grouped crate alias to make a qualified path report (DL-17).

    The reader's own cases establish what it returns. These establish that the
    matcher, which is what the audit records, acts on it: rule (i) resolves a
    path through the name the file binds the root to, and the grouped spelling
    is one of the ways to bind it.
    """

    def test_a_grouped_alias_makes_a_qualified_path_trust(self):
        """Report `k::assume` after `use kani::{self as k};`."""
        self.assertEqual([item.item for item in scan('use kani::{self as k};\nfn f() { k::assume(x); }').items],
                         ['assume'],
                         'a grouped crate alias must reach rule (i)')

    def test_a_grouped_member_alias_makes_no_qualified_path_trust(self):
        """Leave the `a::assume` on the use line's successor alone.

        The fail-closed reading does not stretch to a name the statement did not
        bind to the crate: rule (i) is about a path rooted at the trust root, and
        ``a`` is a member of it, not the root under another name.

        Only line 2 is asserted. Rule (iii) still reports the ``assume`` named in
        the import on line 1, because a file importing from a trust root is
        scanned fail-closed — a documented superset that is not what this case
        is about.
        """
        reported = scan('use kani::{assume as a};\nfn f() { a::assume(x); }').items
        self.assertEqual([item.line for item in reported], [1],
                         'a member alias must not make a qualified path on a later line trust')


class AliasReadingAgreesBetweenItsForms(unittest.TestCase):
    """Require the single-name reader and the set reader to agree.

    Both are public, and both answer the same question about the same statement.
    A case where they disagree would make the audit depend on which one a caller
    happened to reach for.
    """

    def test_each_spelling_reports_one_alias_through_both_readers(self):
        """Require ``use_alias`` to report the name ``use_aliases`` returns."""
        for statement in ('use kani as k;',
                          'use kani::{self as k};',
                          'use kani::{assume, self as k};',
                          'use ::kani as k;'):
            with self.subTest(statement=statement):
                tokens = tokenize(statement)
                end = statement_end(tokens, 1)
                self.assertEqual(use_aliases(tokens, 1, end), frozenset({'k'}),
                                 f'{statement!r} must bind exactly k')
                self.assertEqual(use_alias(tokens, 1, end), 'k',
                                 f'{statement!r} must report k to the single-name reader')

    def test_a_statement_with_no_crate_alias_reports_none_through_both(self):
        """Require both readers to stay silent on a member-only rename."""
        tokens = tokenize('use kani::{assume as a};')
        end = statement_end(tokens, 1)
        self.assertEqual(use_aliases(tokens, 1, end), frozenset(),
                         'a member rename must bind no crate alias')
        self.assertIsNone(use_alias(tokens, 1, end),
                          'the single-name reader must not report a member rename')


if __name__ == '__main__':
    unittest.main()
