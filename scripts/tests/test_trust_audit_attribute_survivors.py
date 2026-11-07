"""Kill attribute-region and import mutants a corpus sweep leaves alive (VO-9).

The mutation census over :mod:`docs_validation.trust_audit.matcher` leaves
survivors in the attribute arithmetic and in the file-scoped import rule. Both
decide *what a source reports* rather than whether it scans, so a corpus of
clean crates never reaches the boundary the mutation moves: every attribute in
it has more than one token between its brackets, and every ``use`` in it is
already an identifier spelled ``use``.

Each case here is asserted at the helper that owns the arithmetic, because the
mutations move a *region bound* and a region one token short still reports the
same items for most inputs. Reading the helper's own answer is what makes the
boundary the subject of the case rather than an accident of a whole-file scan.

Several families are equivalents rather than gaps, and this module records
why. ``_verus_attribute_regions``'s head guard has three variants that all
agree: ``open_index - 1 < close_index`` is true whenever the guarded form's
``open_index + 1 < close_index`` is, so the guard never fires; and
``open_index + 1 <= close_index`` and ``open_index + 1 < close_index`` differ
only at ``open_index + 1 == close_index``, which is the empty attribute ``#[]``
whose head token is the ``]``. ``]`` is not a Verus head, so both forms return
no region. A survivor no input can distinguish is not a test gap;
:class:`EmptyAttributeHasNoHead` pins the second argument as an observation.

Two settled survivors in the same file are equivalent for reasons that do
not belong to any one case, so they are recorded here.
``_module_references``'s name bound cannot matter: when ``index + 1`` is the
last token the name is still read and then fails the following-token test,
which needs a token after the name; when the name is absent both forms fall
through the same ``continue``. ``_path_attribute``'s walk starting at index
``0`` rather than ``1`` cannot matter because no attribute can open at token
zero: an opener is always preceded by its ``#`` and possibly a ``!``, so a
``]`` at index zero is never in ``spans`` and both walks answer ``-1``.

Examples
--------
>>> _verus_attribute_regions(tokenize('#[verifier]'), 1, 3)
((2, 2),)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import TrustAuditError, scan
from docs_validation.trust_audit.lexer import tokenize
from docs_validation.trust_audit.matcher import (
    _Context,
    _imported_roots,
    _verus_attribute_regions,
)
from docs_validation.trust_audit.structure import attribute_spans


def regions(source: str) -> tuple[tuple[int, int], ...]:
    """Return every Verus region the attribute spans of ``source`` yield."""
    tokens = tokenize(source)
    return tuple(region for open_index, close_index in attribute_spans(tokens)
                 for region in _verus_attribute_regions(tokens, open_index, close_index))


def items(source: str) -> tuple[tuple[str, int, int], ...]:
    """Return ``(item, line, column)`` for each item the scan reports."""
    return tuple((item.item, item.line, item.column) for item in scan(source).items)


class SingleHeadAttribute(unittest.TestCase):
    """Require a one-name attribute to create the region its name claims."""

    def test_a_single_name_attribute_still_opens_a_region(self):
        """Require the head guard to admit the shortest form that has a head.

        ``#[verifier]`` holds one token between its brackets, so
        ``open_index + 1`` is exactly ``close_index - 1``. Requiring two tokens
        before the closer -- which is what ``open_index + 2 < close_index``
        does -- refuses the head and the region vanishes. A ``verifier``
        attribute with no arguments is ordinary Rust, and treating it as
        carrying nothing means the item it decorates is audited as untrusted.
        """
        self.assertEqual(regions('#[verifier]'), ((2, 2),),
                         'a one-name verifier attribute must still open a region')

    def test_a_one_name_attribute_inside_a_bracket_still_reports_its_item(self):
        """Require the region to reach a word the attribute itself contains.

        The attribute's own closer is its last token, so the region cannot
        reach past it; the item has to sit inside the brackets for this case to
        observe the head at all. ``#[verifier external]`` is not valid Rust, but
        it is exactly the token sequence a one-name head produces, which is what
        the guard's arithmetic is about.
        """
        self.assertEqual(items('#[verifier external]'), (('external', 1, 12),),
                         'a one-name verifier head must make the word beside it trust')


class RegionStarts(unittest.TestCase):
    """Require a region to begin at the attribute's head, not before it."""

    def test_a_region_starts_at_the_head_rather_than_the_hash(self):
        """Require ``open_index + 1`` as the first index, not the ``#`` before
        it.

        The ``#`` is not an identifier, so starting a region there widens it
        by one token without changing what it reports for a well-formed
        attribute. Starting one token later instead is the visible direction:
        the head is excluded and a ``cfg_attr`` whose Verus name is its *first*
        argument no longer opens a region at all.
        """
        self.assertEqual(regions('#[verifier]'), ((2, 2),),
                         'a region must start at the attribute head, not the hash before it')

    def test_a_cfg_attr_region_starts_at_its_head(self):
        """Require the same start for the ``cfg_attr`` form.

        A region that begins at the ``#`` still covers the head, so the two
        agree on what they report; a region that begins at the second argument
        drops the Verus name that made it a region. The bound is therefore
        observable through the tuple, and pinning it keeps the arithmetic from
        drifting silently.
        """
        self.assertEqual(regions('#[cfg_attr(verus_verify, external)]'), ((2, 7),),
                         'a cfg_attr region must start at its own head token')


class EmptyAttributeHasNoHead(unittest.TestCase):
    """Record the equivalence: an empty attribute has no head to read."""

    def test_an_empty_attribute_opens_no_region(self):
        """Require ``#[]`` to report nothing under either guard spelling.

        With no token between the brackets, both ``<`` and ``<=`` on
        ``open_index + 1`` admit the closing ``]`` as the head -- or, for
        ``<=``, refuse it. ``]`` is not in the Verus head set, so both answer
        no region; the survivor is indistinguishable here.
        """
        self.assertEqual(regions('#[]'), (),
                         'an attribute with no head must open no region')


class ImportRule(unittest.TestCase):
    """Require only an identifier spelled ``use`` to start an import."""

    def test_an_identifier_named_use_is_the_marker_that_matters(self):
        """Require the ``and`` around the token test, so a name is no import.

        The guard skips a token that is not an identifier *or* is not spelled
        ``use``. Weakening it to ``and`` accepts any token that fails one of
        the two tests, so every identifier becomes a candidate import. A
        function named ``kani`` then looks like ``use kani::…`` and rule (iii)
        starts reporting bare vocabulary the file never imported.
        """
        self.assertEqual(items('fn kani() {}\nfn f() { assume(1); }'), (),
                         'a function named kani must not count as an import of the root')

    def test_a_use_outside_the_trust_roots_imports_nothing(self):
        """Require the root filter, so a plain import does not arm rule (iii).

        ``use std::io;`` is a ``use`` and its root is read, but ``std`` is not
        a trust root. A filter that admitted it would make every bare
        vocabulary word in the file trust, which is the over-reporting
        direction the module's own docstring accepts only where a trust root
        really was imported.
        """
        self.assertEqual(items('use std::io;\nassume(1);'), (),
                         'an import outside the trust roots must not arm the bare-use rule')


class OpaqueMacroReason(unittest.TestCase):
    """Require the refusal to state its reason in full, not merely to refuse."""

    def test_the_refusal_states_why_the_macro_cannot_be_audited(self):
        """Require the whole reason sentence, since padding it is invisible.

        The existing cases assert that *a* refusal occurred and that it names
        the macro and its position. Those assertions pass for a message padded
        with markers, so the reason itself was never pinned. A reader deciding
        whether to exempt the file needs the sentence: ``include!`` splices
        source the lexer never sees.
        """
        with self.assertRaises(TrustAuditError) as raised:
            scan('fn f() {\n  include!("x.rs");\n}')
        self.assertEqual(
            str(raised.exception),
            'include! at line 2, column 3 generates code the trust audit cannot read',
            'the refusal must state the whole reason the source cannot be audited')


class DuplicateIdentity(unittest.TestCase):
    """Require the duplicate test to compare the item as well as the position."""

    def test_two_different_items_at_one_position_are_both_kept(self):
        """Require ``existing.item == item``, so distinct words are not merged.

        The guard exists to stop one *token* being reported twice. Comparing
        only the position -- which is what the ``!=`` variant does, since the
        line and column tests still hold -- suppresses every second item that
        shares a location. The scan reaches this guard once per token, so the
        case states it where the contract lives, at the helper's own
        signature; a record author then sees two trust sites where the audit
        reported one.
        """
        token = tokenize('kani::stub(x);')[2]
        context = _Context(tokenize('kani::stub(x);'), False)
        context._report('assume', token)
        context._report('stub', token)
        self.assertEqual([item.item for item in context.items], ['assume', 'stub'],
                         'two items at one position must both be recorded')


class ImportedRootValues(unittest.TestCase):
    """Require the imported root itself to be recorded, not a placeholder."""

    def test_the_root_recorded_is_the_one_the_use_names(self):
        """Require ``roots.add(root)``, so the set carries the crate name.

        The set is what rule (iii) tests for non-emptiness and what a reader
        consults to see *why* a file's bare uses were reported. Adding a
        placeholder instead keeps the set non-empty -- so the bare-use rule
        still fires -- while discarding which root armed it. The observation
        is the set's contents, which is the only place the root is visible.
        """
        self.assertEqual(_imported_roots(tokenize('use kani::assume;')), frozenset({'kani'}),
                         'the imported trust root must be recorded by name')

    def test_a_file_with_no_trust_import_records_nothing(self):
        """Require the empty set for the negative case, so this is not vacuous."""
        self.assertEqual(_imported_roots(tokenize('use std::io;')), frozenset(),
                         'a file importing no trust root must record no root')


if __name__ == '__main__':
    unittest.main()
