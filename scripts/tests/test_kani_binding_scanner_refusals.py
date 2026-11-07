"""Require the scanner and the read helpers to refuse with their own artefact.

The verdict adapter is not the only route into a record's cited files. The
scanner runs first and independently, reading the manifest to decide which
sources to audit, and both routes open files through the same read helpers. A
scanner that raised where it should refuse would abort the gate rather than
reject one record, and a read helper that reported the wrong class would send
the record's author to the wrong artefact.

These cases therefore assert the whole refusal line, including the class and the
path, exactly as the verdict adapter's cases do in
``test_kani_binding_refusals.py``.

Examples
--------
>>> 'not tracked' in MissingEvidence('log', 'x.log', 'it is not tracked').reason
True
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.evidence_binding import log_result, trust_audit
from docs_validation.kani_log.shell import (
    MissingEvidence,
    bind_verdict,
    read_artefact,
    read_tracked,
)
from kani_binding_fixtures import (
    MANIFEST,
    ROOT,
    TOOL,
    CheckoutFixture,
    captured_against,
    digest,
    file_digest,
    record,
    refused_by,
)


class VerdictBinding(CheckoutFixture):
    """Require a bound verdict to carry the log identity it was derived from.

    The gate finds a parsed verdict by matching ``(tool, log_path,
    log_sha256)`` against the record's own citation. A result that dropped
    either half, or reported another record's path, would never be found, and
    the record would silently fall back to self-reported — a refusal in effect
    but not one anybody is told about. These cases bind real, tracked bytes so
    the adapter reaches its success paths and the result can be inspected.
    """

    def test_a_bound_verdict_carries_the_log_identity_the_gate_matches_on(self):
        """Require the path and digest to be the record's own citation."""
        checkout = self.checkout()
        document = checkout.record()
        result = bind_verdict(checkout.root, document)
        self.assertIsNotNone(result, 'a complete record must bind its log')
        self.assertEqual((result.tool, result.log_path, result.log_sha256),
                         (TOOL,
                          document['verdict_source']['log']['path'],
                          document['verdict_source']['log']['sha256']),
                         'a bound verdict must carry the tool, path, and digest the gate matches')

    def test_a_structurally_broken_log_binds_a_tool_error_with_its_identity(self):
        """Require a log the parser refuses to become a ``tool-error``, not missing evidence.

        VO-11b maps a structural refusal to ``tool-error`` so the gate rejects
        the record on its *outcome*: the log exists and is the one the record
        bound, so reporting it as missing would lose the fact that the capture
        itself was unusable. The identity still has to be carried, or the gate
        cannot find this result and cannot reject it for the right reason.
        """
        checkout = self.checkout(log='not a Kani log at all\n')
        document = checkout.record()
        result = bind_verdict(checkout.root, document)
        self.assertIsNotNone(result, 'a structurally broken log must still bind a result')
        self.assertEqual((result.tool, result.outcome), (TOOL, 'tool-error'),
                         'a structurally broken log must decide tool-error')
        self.assertEqual((result.log_path, result.log_sha256),
                         (document['verdict_source']['log']['path'],
                          document['verdict_source']['log']['sha256']),
                         'even a tool-error must carry the log identity it was derived from')


class ManifestRefusals(CheckoutFixture):
    """Drive the manifest-content refusals, whose reasons come from its own reader."""

    def test_a_manifest_that_is_not_json_is_reported_with_the_parser_error(self):
        """Require the JSON failure to be reported as a manifest refusal.

        A record may bind a manifest whose digest is correct and whose content
        is unreadable, which is the case a digest check alone cannot catch.
        """
        checkout = self.checkout(manifest='{not json')
        self.assertIn("manifest 'manifest.json' was refused: it is not valid JSON",
                      captured_against(checkout.root, log_result, checkout.record()),
                      'a manifest that is not JSON must be reported as such')

    def test_a_manifest_that_is_json_but_not_an_object_is_refused(self):
        """Require a JSON array to be refused, since a manifest is a mapping."""
        checkout = self.checkout(manifest='[]')
        self.assertEqual(captured_against(checkout.root, log_result, checkout.record()),
                         "EV-TEST: manifest 'manifest.json' was refused: it is not a JSON object",
                         'a JSON array must be refused as a non-object manifest')

    def test_a_manifest_the_decision_cannot_read_names_the_manifest(self):
        """Require a structurally valid JSON document the manifest reader refuses to be reported.

        The reader's own message is what a manifest author needs, so the
        adapter must pass it through rather than replace it with a generic one.
        """
        checkout = self.checkout(manifest=json.dumps({'harnesses': []}))
        self.assertIn('the harness manifest declares no harnesses',
                      captured_against(checkout.root, log_result, checkout.record()),
                      'a manifest the reader refuses must be reported with its reason')


class ScannerRefusals(CheckoutFixture):
    """Drive the scanner's own refusals, which gate the trust audit (DL-16)."""

    def test_a_record_binding_no_manifest_is_reported_with_its_count(self):
        """Require the empty artefact list to be refused rather than audited as empty."""
        self.assertEqual(refused_by(trust_audit, record(result_artefacts=[])),
                         "EV-TEST: manifest 'EV-TEST' was refused: the record must bind exactly "
                         'one result artefact: its harness manifest',
                         'a record with no manifest must be reported before the gate sees it')

    def test_a_record_binding_two_manifests_is_refused(self):
        """Require the count, not merely a missing array."""
        two = [{'path': MANIFEST, 'sha256': file_digest(MANIFEST)}] * 2
        self.assertIn('exactly one result artefact',
                      refused_by(trust_audit, record(result_artefacts=two)),
                      'a record binding two manifests has no single audit')

    def test_a_manifest_naming_no_sources_is_refused(self):
        """Require the empty source list to be refused, which would audit nothing."""
        checkout = self.checkout(manifest=json.dumps({'harnesses': [{'name': 'h::x', 'role': 'claim'}]}))
        self.assertIn("manifest 'manifest.json' was refused: it names no source files to audit",
                      captured_against(checkout.root, trust_audit, checkout.record()),
                      'a manifest naming no sources must be refused as unauditable')

    def test_a_source_git_does_not_track_is_reported_by_its_own_class(self):
        """Require a source refusal to be reported as a source, not as the manifest."""
        checkout = self.checkout(manifest=json.dumps({
            'harnesses': [{'name': 'h::x', 'role': 'claim'}],
            'sources': ['manifest.json', 'missing.rs'],
        }))
        self.assertIn("source 'missing.rs' was refused: "
                      'it is not a tracked file inside the repository',
                      captured_against(checkout.root, trust_audit, checkout.record()),
                      'an untracked source must be reported as a source refusal')

    def test_a_scanner_that_cannot_read_its_manifest_reports_the_manifest(self):
        """Require the scanner to report a manifest refusal rather than raise."""
        self.assertIn("manifest 'scripts/tests/fixtures/evidence/default-unwind-manifest.json'",
                      refused_by(trust_audit, record(**{'result_artefacts': [
                          {'path': MANIFEST, 'sha256': 'd' * 64}]})),
                      'a manifest the scanner cannot bind must be reported')


class ReadHelpers(CheckoutFixture):
    """Hold the two file readers to the refusals the adapters rely on."""

    def test_an_unreadable_tracked_file_becomes_a_refusal(self):
        """Require a read that fails to become ``MissingEvidence`` with the OS error.

        Git tracks a *file*; replacing a tracked file with a directory keeps it
        in the index while making the read fail, which is the only way a tracked
        path can be unreadable without relying on permissions the test would
        have to change.
        """
        checkout = self.checkout()
        tracked = checkout.root / 'run.log'
        tracked.unlink()
        tracked.mkdir()
        result = read_tracked(checkout.root, 'run.log')
        self.assertIsInstance(result, MissingEvidence,
                              'an unreadable tracked path must be refused, not raised')
        self.assertEqual((result.what, result.path),
                         ('path', 'run.log'),
                         'the refusal must name the class and the path it was asked about')
        self.assertIn('it cannot be read', result.reason,
                      'the refusal must carry the operating system error')

    def test_reading_outside_the_repository_is_refused_before_the_tracking_check(self):
        """Require containment to be decided before Git, so the reason names the escape."""
        result = read_tracked(ROOT, '../outside.log')
        self.assertEqual((result.what, result.path, result.reason),
                         ('path', '../outside.log', 'it is not a repository-relative path'),
                         'an escaping path must be refused for what it is')

    def test_a_symlink_out_of_the_repository_is_refused_for_the_escape(self):
        """Require containment to be decided on the *resolved* path, not the spelling.

        A link's path is relative and carries no ``..``, so the lexical check
        above cannot see it; only resolving it reveals the target. Following the
        link would read a file the repository does not own and bind its bytes as
        this record's evidence, which is exactly what tracking is meant to stop.
        """
        checkout = self.checkout()
        outside = Path(tempfile.mkdtemp()) / 'outside.log'
        self.addCleanup(shutil.rmtree, outside.parent)
        outside.write_text('kani::assume(x);\n', encoding='utf-8')
        checkout.root.joinpath('link.log').symlink_to(outside)
        result = read_tracked(checkout.root, 'link.log')
        self.assertEqual((result.what, result.path, result.reason),
                         ('path', 'link.log', 'it resolves outside the repository'),
                         'a symlink leaving the repository must be refused as an escape')

    def test_a_missing_digest_names_the_artefact_class_it_was_asked_about(self):
        """Require ``read_artefact`` to relabel the inner refusal with its own class."""
        result = read_artefact(ROOT, '../outside.log', 'a' * 64, 'log')
        self.assertEqual((result.what, result.path),
                         ('log', '../outside.log'),
                         'the outer reader must relabel the refusal, keeping the path')

    def test_an_untracked_path_is_reported_as_untracked(self):
        """Require the Git check's own reason, which is distinct from a digest mismatch.

        The reader's own triple is asserted as well as the line the adapter
        prints. ``read_artefact`` relabels the refusal with the class its caller
        asked for, so from the adapter's report alone the reader's ``what`` and
        ``path`` could be anything; a direct reader such as the source scanner
        sees them, and they must still name the path it was asked about.
        """
        checkout = self.checkout()
        checkout.root.joinpath('litter.log').write_text('anything\n', encoding='utf-8')
        direct = read_tracked(checkout.root, 'litter.log')
        self.assertEqual((direct.what, direct.path, direct.reason),
                         ('path', 'litter.log', 'it is not tracked by Git'),
                         'the reader must name the class and the path it refused')
        document = checkout.record(verdict_source={'kind': 'log-parser', 'log': {
            'path': 'litter.log', 'sha256': digest(b'anything\n')}})
        self.assertEqual(captured_against(checkout.root, log_result, document),
                         "EV-TEST: log 'litter.log' was refused: it is not tracked by Git",
                         'an untracked artefact must be reported as untracked')


if __name__ == '__main__':
    unittest.main()
