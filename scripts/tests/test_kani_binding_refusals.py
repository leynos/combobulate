"""Require the verdict adapter to report each refusal with its artefact and reason.

The gate can only say ``verdict-self-reported`` or ``trust-unaudited``, and it
says the same two words whether a log was tampered with, untracked, or merely
named at the wrong path. The refusal detail exists for exactly one reader — the
record's author — so it is printed to standard error, and this module is the
only thing that reads it back.

Every case here therefore drives one refusal end to end and asserts the whole
line: the record's id, the artefact class, the path as it was written, and the
reason. A refusal that reported ``None`` in place of the class, or dropped the
path, would still refuse; only an assertion on the message can tell.

The scanner's own refusals, and the read helpers both routes share, live in
``test_kani_binding_scanner_refusals.py``; the checkout and record builders
both modules use live in ``kani_binding_fixtures.py``.

Examples
--------
>>> refused_directly({'id': 'EV-1'})[:24]
"EV-1: field 'EV-1' was r"
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.evidence_binding import log_result
from docs_validation.kani_log.shell import MissingEvidence
from kani_binding_fixtures import (
    LOG,
    MANIFEST,
    record,
    refused_by,
    refused_directly,
    report,
)


class AdapterRefusals(unittest.TestCase):
    """Drive each refusal an adapter can produce and require it to be reported."""

    def test_a_path_relative_to_nowhere_is_reported_with_its_artefact(self):
        """Require the escaping path to be named with the artefact it was bound for.

        ``read_artefact`` relabels a refusal with the artefact it was asked for,
        so the class says what was being bound while the reason names the
        escape; a record's author needs both to know which line to fix.
        """
        document = record(**{'verdict_source': {'kind': 'log-parser',
                                                'log': {'path': '../outside.log', 'sha256': 'a' * 64}}})
        self.assertEqual(refused_by(log_result, document),
                         "EV-TEST: log '../outside.log' was refused: "
                         'it is not a repository-relative path',
                         'an escaping path must be reported with the artefact it was bound for')

    def test_an_absolute_path_is_reported_as_such(self):
        """Require the absolute case to reach the same refusal, not a file read."""
        document = record(**{'verdict_source': {'kind': 'log-parser',
                                                'log': {'path': '/etc/passwd', 'sha256': 'a' * 64}}})
        self.assertIn('it is not a repository-relative path', refused_by(log_result, document),
                      'an absolute path must be refused for what it is')

    def test_a_digest_mismatch_names_the_log_it_could_not_bind(self):
        """Require the tampered log to be named as a log, with the digest reason."""
        document = record(**{'verdict_source': {'kind': 'log-parser',
                                                'log': {'path': LOG, 'sha256': 'b' * 64}}})
        self.assertEqual(refused_by(log_result, document),
                         f"EV-TEST: log '{LOG}' was refused: "
                         'its digest differs from the one the record binds',
                         'a log whose bytes differ must be reported as a log refusal')

    def test_a_tampered_manifest_names_the_manifest_it_could_not_bind(self):
        """Require the same for the manifest, whose digest is checked after the log's."""
        document = record(**{'result_artefacts': [{'path': MANIFEST, 'sha256': 'c' * 64}]})
        self.assertEqual(refused_by(log_result, document),
                         f"EV-TEST: manifest '{MANIFEST}' was refused: "
                         'its digest differs from the one the record binds',
                         'a manifest whose bytes differ must be reported as a manifest refusal')

    def test_a_record_with_no_digest_says_so_rather_than_reading_the_file(self):
        """Require the empty digest to be reported, which no bytes could ever match."""
        document = record(**{'result_artefacts': [{'path': MANIFEST, 'sha256': ''}]})
        self.assertEqual(refused_by(log_result, document),
                         f"EV-TEST: manifest '{MANIFEST}' was refused: "
                         'the record binds no digest for it',
                         'an empty digest must be reported rather than compared')

    def test_a_malformed_field_names_the_record_not_a_path(self):
        """Require a shape problem to be reported against the record, with the field's reason.

        Driven through ``bind_verdict`` rather than ``log_result``: the seam
        filters a tool it has no adapter for before dispatch, so this branch is
        reachable only from the adapter itself.
        """
        self.assertEqual(refused_directly(record(**{'method': {'tool': 'verus'}})),
                         "EV-TEST: field 'EV-TEST' was refused: "
                         "the record names tool 'verus', which this adapter does not read",
                         'a shape problem must be reported as a field refusal')

    def test_a_verdict_source_that_is_not_a_mapping_is_refused_not_raised(self):
        """Require the shape check to run before the field is read.

        The check is a short-circuit ``or``: reading ``source.get`` on a string
        would raise ``AttributeError`` instead of refusing, and a refusal is what
        lets the record fall back to self-reported rather than crash the gate.
        """
        self.assertEqual(refused_directly(record(verdict_source='log-parser')),
                         "EV-TEST: field 'EV-TEST' was refused: "
                         'the record does not claim a parsed verdict',
                         'a non-mapping verdict source must be refused with its own reason')

    def test_a_log_that_names_no_path_and_digest_is_refused_with_its_own_reason(self):
        """Require the per-field check to run for a log that *is* a mapping.

        A mapping with a non-string ``path`` is the case the two-part condition
        exists for: the ``isinstance`` half alone passes it, so a condition
        joined with ``and`` would let it through to the ``KeyError`` that follows.
        """
        self.assertEqual(refused_directly(record(verdict_source={
            'kind': 'log-parser', 'log': {'path': None, 'sha256': 'a' * 64}})),
            "EV-TEST: field 'EV-TEST' was refused: the record names no log path and digest",
            'a log mapping with a non-string path must be refused, not read')

    def test_an_artefact_that_names_no_path_and_digest_is_refused_with_its_own_reason(self):
        """Require the same per-field check for the result artefact.

        The artefact is the field the record's manifest is read from, so a
        mapping with a non-string ``path`` must be refused here rather than
        surfacing later as a ``KeyError`` inside the reader.
        """
        self.assertEqual(refused_directly(record(
            result_artefacts=[{'path': 1, 'sha256': 'a' * 64}])),
            "EV-TEST: field 'EV-TEST' was refused: "
            'the bound result artefact names no path and digest',
            'an artefact mapping with a non-string path must be refused, not read')

    def test_a_result_artefacts_value_that_is_not_a_sequence_is_refused_not_raised(self):
        """Require the count check to run before ``len`` is taken."""
        self.assertEqual(refused_directly(record(result_artefacts=3)),
                         "EV-TEST: field 'EV-TEST' was refused: "
                         'the record must bind exactly one result artefact: '
                         'its harness manifest',
                         'a non-sequence result_artefacts must be refused with its own reason')


class ReportShape(unittest.TestCase):
    """Pin the one line a refusal prints."""

    def test_the_report_names_the_id_the_class_the_path_and_the_reason(self):
        """Require every part of the line, in the order a reader scans it."""
        self.assertEqual(report({'id': 'EV-1'}, MissingEvidence('log', 'a.log', 'it is not tracked')),
                         "EV-1: log 'a.log' was refused: it is not tracked",
                         'the report must name the id, the class, the path, and the reason')

    def test_a_record_without_an_id_is_still_reported(self):
        """Require the fallback label, since a malformed record may have no id at all.

        Asserted in full: the fallback is the only name a reader gets for a
        record that cannot name itself, so substituting ``None`` for it would
        leave the line starting at the artefact class with nothing to search for.
        """
        self.assertEqual(report({}, MissingEvidence('manifest', 'm.json', 'it is not valid JSON')),
                         "record: manifest 'm.json' was refused: it is not valid JSON",
                         'a record with no id must still be reported under a readable label')

    def test_the_report_quotes_the_path_rather_than_interpolating_it_bare(self):
        """Require the repr, so a path with a space or a quote stays unambiguous."""
        self.assertIn("'a path with spaces.log'",
                      report({'id': 'EV-1'}, MissingEvidence('log', 'a path with spaces.log', 'no')),
                      'the path must be quoted, not interpolated bare')
