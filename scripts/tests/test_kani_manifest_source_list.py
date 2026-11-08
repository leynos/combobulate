"""Require a manifest's source list to bind a path to a digest (DL-16, VO-12).

The evidence gate reads a log-parser manifest and audits the sources it names.
That list is producer-adjacent JSON, so the reader must refuse the shapes that
would otherwise become an audit of something else: a bare string read as one
path per character, a number iterated as if it were a list, or — after DL-16 —
a path with no digest to check it against. Each case here is a mutant the
census over :mod:`docs_validation.kani_log` left alive because the outcome
suites assert verdicts rather than the list the scanner is handed.

These live apart from ``test_kani_binding_survivors`` because they test the
manifest reader's *input shape*, while that module tests the decision and
binding surfaces built on top of it.

Examples
--------
A manifest naming a path without a digest yields no auditable source::

    _manifest_sources({'sources': ['a.rs']})  # ()
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.kani_log.shell import _manifest_sources


class ManifestSourceList(unittest.TestCase):
    """Require a manifest's source list to bind a path to a digest, or nothing.

    ``_manifest_sources`` hands its result to the scanner, which opens each
    path in turn. A ``str`` is a ``Sequence``, so a manifest writing
    ``"sources": "src/lib.rs"`` would otherwise be read as one path per
    *character* and the scanner would look for a file called ``s``.

    DL-16 binds the audit to the sources a manifest names, so an entry that
    names a path without a digest is dropped: the scanner could read the file
    but had nothing to check it against, and a source that drifted after the
    manifest was written would be audited as though it had not.
    """

    def test_a_string_source_list_yields_no_paths(self):
        """Require the ``str`` exclusion, which is the whole reason it is written out.

        A single string is not a list of sources, and splitting it into
        characters would make every one of them a path the scanner tries to
        open. Reporting nothing refuses the manifest downstream instead.
        """
        self.assertEqual(_manifest_sources({'sources': 'abc'}), (),
                         'a string source list must not be read as one path per character')

    def test_a_non_sequence_source_list_yields_no_paths(self):
        """Require the ``Sequence`` test, since a number cannot be iterated at all.

        A manifest is producer-adjacent JSON, so a wrong type here is plausible.
        Without the test the caller raises ``TypeError`` out of the gate instead
        of refusing the manifest.
        """
        self.assertEqual(_manifest_sources({'sources': 5}), (),
                         'a source field that is not a sequence must yield no paths')

    def test_a_list_of_bound_sources_is_returned(self):
        """Require the positive case, so the guards are not vacuously empty."""
        document = {'sources': [
            {'path': 'a.rs', 'sha256': 'aa'},
            2,
            {'path': 'b.rs', 'sha256': 'bb'},
        ]}
        self.assertEqual(_manifest_sources(document), (('a.rs', 'aa'), ('b.rs', 'bb')),
                         'a list of bound sources must be returned with its non-entries dropped')

    def test_a_bare_path_yields_no_source(self):
        """Require an unbound path to be dropped, since nothing can check it.

        A manifest written before DL-16's digest binding names bare paths. It is
        refused rather than silently accepted, which is what makes the digest
        check load-bearing instead of decorative.
        """
        self.assertEqual(_manifest_sources({'sources': ['a.rs']}), (),
                         'an unbound path must not become an auditable source')

    def test_an_empty_digest_yields_no_source(self):
        """Require an empty digest to be refused, since it would match nothing.

        ``''`` is not a digest of any file, so keeping the entry would report a
        digest mismatch for a manifest that never bound one.
        """
        self.assertEqual(_manifest_sources({'sources': [{'path': 'a.rs', 'sha256': ''}]}), (),
                         'an empty digest must not become an auditable source')


if __name__ == '__main__':
    unittest.main()
