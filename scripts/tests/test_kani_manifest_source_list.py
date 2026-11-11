"""Require a manifest's source list to bind a path to a digest (DL-16, VO-12).

The evidence gate reads a log-parser manifest and audits the sources it names.
That list is producer-adjacent JSON, so the reader must refuse the shapes that
would otherwise become an audit of something else: a bare string read as one
path per character, a number iterated as if it were a list, or — after DL-16 —
a path with no digest to check it against. Each case here is a mutant the
census over :mod:`docs_validation.kani_log` left alive because the outcome
suites assert verdicts rather than the list the scanner is handed.

The reader is all-or-nothing. Dropping a malformed entry and returning the
rest would audit only the sources the author remembered to bind, while the
record still claimed the whole list — an audit of a narrower scope than the
record names. One bad entry therefore refuses the list, which is why every
refusal case below asserts ``None`` rather than ``()``: the two lead the
author to different repairs.

These live apart from ``test_kani_binding_survivors`` because they test the
manifest reader's *input shape*, while that module tests the decision and
binding surfaces built on top of it.

Examples
--------
A manifest naming a path without a digest has no auditable source list::

    _manifest_sources({'sources': ['a.rs']}) is None  # True
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.kani_log.shell import _manifest_sources


class ManifestSourceList(unittest.TestCase):
    """Require a manifest's source list to bind every entry to a digest, or none.

    ``_manifest_sources`` hands its result to the scanner, which opens each
    path in turn. A ``str`` is a ``Sequence``, so a manifest writing
    ``"sources": "src/lib.rs"`` would otherwise be read as one path per
    *character* and the scanner would look for a file called ``s``.

    DL-16 binds the audit to the sources a manifest names, so a list holding an
    entry without a digest is refused whole: the scanner could read that file
    but had nothing to check it against, and a source that drifted after the
    manifest was written would be audited as though it had not. Keeping the
    remaining entries would be worse still, because the record would claim
    coverage of a source the audit never opened.
    """

    def test_a_string_source_list_is_refused(self):
        """Require the ``str`` exclusion, which is the whole reason it is written out.

        A single string is not a list of sources, and splitting it into
        characters would make every one of them a path the scanner tries to
        open. Refusing the list makes the caller refuse the manifest.
        """
        self.assertIsNone(_manifest_sources({'sources': 'abc'}),
                          'a string source list must not be read as one path per character')

    def test_a_non_sequence_source_list_is_refused(self):
        """Require the ``Sequence`` test, since a number cannot be iterated at all.

        A manifest is producer-adjacent JSON, so a wrong type here is plausible.
        Without the test the caller raises ``TypeError`` out of the gate instead
        of refusing the manifest.
        """
        self.assertIsNone(_manifest_sources({'sources': 5}),
                          'a source field that is not a sequence must refuse the list')

    def test_a_list_of_bound_sources_is_returned(self):
        """Require the positive case, so the guards are not vacuously empty."""
        document = {'sources': [
            {'path': 'a.rs', 'sha256': 'aa'},
            {'path': 'b.rs', 'sha256': 'bb'},
        ]}
        self.assertEqual(_manifest_sources(document), (('a.rs', 'aa'), ('b.rs', 'bb')),
                         'a fully bound list must be returned in order')

    def test_one_malformed_entry_refuses_the_whole_list(self):
        """Require a mixed list to be refused, not trimmed to its valid entries.

        This is the regression for a reader that filtered the list. Every entry
        here is well formed except one, so a filtering reader would audit two
        sources and report a clean result for a record claiming three.
        """
        document = {'sources': [
            {'path': 'a.rs', 'sha256': 'aa'},
            2,
            {'path': 'b.rs', 'sha256': 'bb'},
        ]}
        self.assertIsNone(_manifest_sources(document),
                          'one malformed entry must refuse the list rather than be dropped')

    def test_a_bare_path_is_refused(self):
        """Require an unbound path to refuse the list, since nothing can check it.

        A manifest written before DL-16's digest binding names bare paths. It is
        refused rather than silently accepted, which is what makes the digest
        check load-bearing instead of decorative.
        """
        self.assertIsNone(_manifest_sources({'sources': ['a.rs']}),
                          'an unbound path must refuse the source list')

    def test_an_empty_digest_refuses_the_list(self):
        """Require an empty digest to be refused, since it would match nothing.

        ``''`` is not a digest of any file, so keeping the entry would report a
        digest mismatch for a manifest that never bound one.
        """
        self.assertIsNone(_manifest_sources({'sources': [{'path': 'a.rs', 'sha256': ''}]}),
                          'an empty digest must refuse the source list')

    def test_an_entry_without_a_path_refuses_the_list(self):
        """Require the path half of the binding to be checked too.

        A digest alone names nothing to open, so an entry carrying only
        ``sha256`` is as unusable as a bare path.
        """
        self.assertIsNone(_manifest_sources({'sources': [{'sha256': 'aa'}]}),
                          'an entry naming no path must refuse the source list')

    def test_an_empty_source_list_is_distinct_from_a_refusal(self):
        """Require ``()`` to survive, so the caller can tell the two apart.

        A manifest that declares no sources is malformed in its own way, but the
        author's repair differs from that of an unbound entry, so the reader
        reports the two separately.
        """
        self.assertEqual(_manifest_sources({'sources': []}), (),
                         'an empty list is a manifest with no sources, not an unusable one')


if __name__ == '__main__':
    unittest.main()
