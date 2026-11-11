"""Hold the ``use``-tree reader to its contract over generated import trees (DL-17).

The example cases in :mod:`test_trust_audit_use_tree` fix the spellings somebody
thought to write down. That is the wrong shape of evidence for a recursive
reader: nesting depth, member order, and the number of renames are all
open-ended, and a rule that only holds for the handwritten depths is a rule the
audit silently stops applying one brace deeper. This module generates the trees
instead, so the contract is stated once and checked over the whole space.

Two directions matter, and they pull against each other. A crate rename the
reader *misses* hides a trust item, because ``k::assume`` then reads as an
unrelated path. A member rename the reader *invents* a crate alias from makes
every ``a::`` path in the file trust, which is a claim the source does not make.
So the generated trees carry both kinds of rename, and each assertion names
which direction it is defending.

Examples
--------
>>> alias_bindings(tokenize('use {{kani as k}};'), 'kani') == frozenset({'kani', 'k'})
True
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import given, settings
from hypothesis import strategies as st

from docs_validation.trust_audit import alias_bindings, scan, tokenize

ROOT = 'kani'
"""The trust root the generated trees import and rename."""

SPELLINGS = ('plain', 'renamed', 'grouped', 'member')
"""How one member of a generated tree may name the root.

``plain`` imports the crate under its own name, ``renamed`` writes
``kani as k``, ``grouped`` writes ``kani::{self as k}``, and ``member`` writes
``kani::{assume as a}``. The first three name the crate; the last names one of
the crate's items and must never be read as an alias of the crate.
"""

MAXIMUM_DEPTH = 4
"""The deepest brace nesting generated, which is past the depths the examples fix."""

ALIAS = st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=6).map(
    lambda drawn: 'z' + drawn)
"""A generated local name that cannot collide with a keyword or with the root.

The leading ``z`` keeps every generated name distinct from ``kani``, ``self``,
``assume``, and ``std`` without a rejection filter, so the strategy produces a
usable example on the first draw.
"""

SETTINGS = settings(max_examples=200, derandomize=True, deadline=None)
"""Run every case enough times to reach the depths and orders the examples skip.

``derandomize`` keeps the suite reproducible, so a failure reported in CI is a
failure a developer can replay rather than a one-off draw.
"""


def render(members: list[tuple[str, str]], depth: int) -> str:
    """Render one ``use`` statement whose members are nested ``depth`` braces deep.

    The members are joined in the order given, so reversing the list produces a
    statement with the same imports written the other way round. Each extra
    depth wraps the whole list in one more pair of braces, which is the nesting
    the reader recurses through.
    """
    rendered = ', '.join(_member(kind, name) for kind, name in members)
    return f'use {"{" * depth}{rendered}{"}" * depth};'


def _member(kind: str, name: str) -> str:
    """Render one member of a generated tree in the spelling ``kind`` names.

    A ``plain`` member ignores ``name``: the spelling is the bare crate, which
    binds the root under its own name whatever the drawn name was.
    """
    if kind == 'renamed':
        return f'{ROOT} as {name}'
    if kind == 'grouped':
        return f'{ROOT}::{{self as {name}}}'
    if kind == 'member':
        return f'{ROOT}::{{assume as {name}}}'
    return ROOT


def crate_aliases(members: list[tuple[str, str]]) -> frozenset[str]:
    """Return the names a generated tree binds the crate itself to.

    The crate's own name is always bound, because a statement that imports from
    the root names it whatever else it renames it to. A ``plain`` member
    contributes no alias of its own, and a ``member`` spelling binds an item
    rather than the crate.
    """
    renamed = {name for kind, name in members if kind in {'renamed', 'grouped'}}
    return frozenset({ROOT} | renamed)


def member_aliases(members: list[tuple[str, str]]) -> frozenset[str]:
    """Return the names a generated tree binds one of the crate's items to."""
    return frozenset(name for kind, name in members if kind == 'member')


def qualified_uses(statement: str, name: str) -> tuple[int, ...]:
    """Return the lines a ``name::assume`` call on the statement's successor reports.

    The call is written on line two so that anything the scanner reports from
    the import itself stays on line one and cannot be mistaken for a match on
    the qualified path.
    """
    source = f'{statement}\nfn f() {{ {name}::assume(x); }}'
    return tuple(item.line for item in scan(source).items)


class GeneratedUseTrees(unittest.TestCase):
    """Check alias discovery over trees of varied depth, order, and renaming."""

    @SETTINGS
    @given(
        members=st.lists(st.tuples(st.sampled_from(SPELLINGS), ALIAS),
                         min_size=1, max_size=4, unique_by=lambda member: member[1]),
        depth=st.integers(min_value=1, max_value=MAXIMUM_DEPTH),
        reverse=st.booleans(),
    )
    def test_every_crate_alias_is_kept_and_no_member_alias_is_invented(
            self, members, depth, reverse) -> None:
        """Require the reader to report exactly the names the tree binds the crate to.

        The comparison is equality rather than containment in either direction
        on purpose. A subset check would pass a reader that dropped a rename one
        brace deeper, and a superset check would pass one that turned
        ``kani::{assume as a}`` into a crate alias.
        """
        if reverse:
            members.reverse()
        statement = render(members, depth)
        self.assertEqual(
            alias_bindings(tokenize(statement), ROOT),
            crate_aliases(members),
            f'{statement!r} must bind exactly the crate names it writes')

    @SETTINGS
    @given(
        members=st.lists(st.tuples(st.sampled_from(('renamed', 'grouped')), ALIAS),
                         min_size=1, max_size=3, unique_by=lambda member: member[1]),
        depth=st.integers(min_value=1, max_value=MAXIMUM_DEPTH),
    )
    def test_each_crate_alias_reaches_the_qualified_path_rule(
            self, members, depth) -> None:
        """Require every rename to make ``name::assume`` report, at any depth.

        This is the fail-open direction: a rename the reader misses leaves the
        qualified call unreported, and the file is then described as trust-free
        while it assumed exactly what the vocabulary names.
        """
        statement = render(members, depth)
        aliases = crate_aliases(members)
        reached = {name for name in aliases if 2 in qualified_uses(statement, name)}
        self.assertEqual(
            reached, aliases,
            f'{statement!r} must make every bound name reach rule (i), '
            f'missing {sorted(aliases - reached)}')

    @SETTINGS
    @given(
        member_alias=ALIAS,
        crate_alias=ALIAS,
        depth=st.integers(min_value=1, max_value=MAXIMUM_DEPTH),
        reverse=st.booleans(),
    )
    def test_no_member_alias_reaches_the_qualified_path_rule(
            self, member_alias, crate_alias, depth, reverse) -> None:
        """Require ``kani::{assume as a}`` never to make ``a::assume`` trust.

        The tree also carries one genuine crate rename, so a reader that
        reported a single alias per statement would pass here for the wrong
        reason — it must keep the crate alias and still refuse the member one.
        The two names are held apart, because a statement that bound both
        spellings to one name would make the assertion depend on which member
        the reader happened to read last.
        """
        if crate_alias == member_alias:
            crate_alias += 'q'
        members = [('member', member_alias), ('renamed', crate_alias)]
        if reverse:
            members.reverse()
        statement = render(members, depth)
        self.assertNotIn(
            2, qualified_uses(statement, member_alias),
            f'a member rename in {statement!r} must not make a qualified path trust')
        self.assertIn(
            2, qualified_uses(statement, crate_alias),
            f'the crate rename in {statement!r} must keep reaching rule (i)')
        self.assertEqual(
            alias_bindings(tokenize(statement), ROOT),
            frozenset({ROOT, crate_alias}),
            f'{statement!r} must bind the crate name and no member name')


if __name__ == '__main__':
    unittest.main()
