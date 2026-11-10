"""Require the binder to re-derive a record's verdict and reject every tampered claim (VO-12).

VO-12 is the rule that a verifier record's verdict is evidence only when a
registered adapter re-derives it from the exact artefact the record names.
That rule has two halves and this module covers both. The positive half is one
committed record, ``bounded-kani.json``, which must reach ``bounded``: a
fixture that never admits anything proves only that the gate rejects, which is
the failure direction the gate already fails closed on.

The negative half is why the positive half means anything. Each case here takes
that same admitted record, changes exactly one thing, and requires the gate to
stop admitting it — a tampered log, a tampered manifest, an unregistered tool,
a path Git does not track, a fact that disagrees with the log, an audit the
scanner never found, and a record that renames parser evidence as a test.

Examples
--------
>>> fixture_record('bounded-kani')['method']['run_mode']
'full-profile'
>>> admit(ROOT, fixture_record('bounded-kani')).level.value
'bounded'
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.evidence_binding import checked_inputs, log_result, trust_audit
from docs_validation.evidence_gate import AdmissionContext, Level, admit_evidence
from git_fixtures import run_git

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'scripts/tests/fixtures/evidence'
MANIFEST = 'scripts/tests/fixtures/evidence/default-unwind-manifest.json'
AS_OF = datetime.date(2026, 11, 7)
KANI = frozenset({'kani'})


def fixture_record(name: str) -> dict:
    """Return one committed evidence fixture, parsed."""
    return json.loads((EVIDENCE / f'{name}.json').read_text(encoding='utf-8'))


def fixture_bindings() -> dict:
    """Return the current-profile map that makes the positive fixture's binding current."""
    return json.loads((EVIDENCE / 'bounded-kani-bindings.json').read_text(encoding='utf-8'))


def admit(root: Path, record: dict, parsers: frozenset[str] = KANI) -> object:
    """Admit one record through the real binding seam, as the CLI does."""
    logs, audits = checked_inputs(root, [record], parsers)
    return admit_evidence(record, AdmissionContext(
        exceptions={}, bindings=fixture_bindings(), as_of=AS_OF,
        log_parsers=parsers, verified_log_results=logs, verified_trust_audits=audits))


def digest(path: Path) -> str:
    """Return a file's SHA-256, which is what a record binds."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AdmittedFixture(unittest.TestCase):
    """The positive record reaches ``bounded`` and nothing weaker."""

    def test_the_committed_fixture_reaches_bounded(self):
        """Require the positive fixture to be admitted with no blocking reason."""
        admission = admit(ROOT, fixture_record('bounded-kani'))
        self.assertEqual((admission.level, admission.reasons), (Level.BOUNDED, ()),
                         'a committed log, manifest, and audit must admit the record at bounded')

    def test_the_fixture_is_bounded_rather_than_proof(self):
        """Require partial bounds to stop at ``bounded``, which is DL-10's whole point."""
        admission = admit(ROOT, fixture_record('bounded-kani'))
        self.assertIs(admission.level, Level.BOUNDED,
                      'partial bounds must not reach proof however complete the run was')

    def test_a_focused_run_does_not_reach_bounded(self):
        """Require the run mode to be read from the log, not accepted from the record.

        The record and the log disagree here, which is the case a record author
        could otherwise write past: the parser decides ``full-profile`` from the
        echoed CBMC command, so an edited record fails to match rather than
        upgrading a focused capture.
        """
        record = fixture_record('bounded-kani')
        record['method']['run_mode'] = 'focused'
        admission = admit(ROOT, record)
        self.assertIn('verdict-self-reported', admission.reasons,
                      'a record claiming a mode the log did not run is self-reported')

    def test_without_registration_the_same_record_is_self_reported(self):
        """Require registration to be what admits a parsed verdict (C-EP-10)."""
        admission = admit(ROOT, fixture_record('bounded-kani'), parsers=frozenset())
        self.assertIn('verdict-self-reported', admission.reasons,
                      'tool registration alone must be required to parse a verdict')

    def test_two_records_citing_one_log_still_admit(self):
        """Require a shared artefact to be bound once, not once per citing record.

        The gate asks that *exactly one* candidate match a record's ``(tool,
        path, digest)`` and demotes the record when the count differs. Two
        records citing the same log are two claims about one capture, so
        appending a result per record makes the count two and turns a sound
        record into ``verdict-self-reported``. Equal values came from the same
        bytes, so they are one fact.
        """
        record = fixture_record('bounded-kani')
        logs, audits = checked_inputs(ROOT, [record, record], KANI)
        self.assertEqual(len(logs), 1,
                         'one log cited by two records must bind to one result')
        self.assertEqual(len(audits), 1,
                         'one manifest audited for two records must bind to one audit')
        admission = admit_evidence(record, AdmissionContext(
            exceptions={}, bindings=fixture_bindings(), as_of=AS_OF,
            log_parsers=KANI, verified_log_results=logs, verified_trust_audits=audits))
        self.assertEqual((admission.level, admission.reasons), (Level.BOUNDED, ()),
                         'a duplicated citation must not demote the record it cites')


class ScratchCheckout:
    """Copy the tracked repository sources into a scratch Git checkout.

    The binding seam reads ``scripts/`` and ``tools/`` and requires every path
    to be Git-tracked, so a case that tampers with one file needs a real
    repository rather than a directory of loose files. This is a mixin rather
    than a ``TestCase`` so it contributes no tests of its own.
    """

    def setUp(self) -> None:
        """Copy the tracked repository sources into a scratch checkout."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for relative in ('scripts', 'tools'):
            shutil.copytree(ROOT / relative, self.root / relative,
                            ignore=shutil.ignore_patterns('__pycache__', 'target'))
        run_git(self.root, 'init', '-q')
        run_git(self.root, 'add', '-A')
        run_git(self.root, 'commit', '-q', '-m', 'Create binding fixture')

    def record(self, name: str = 'bounded-kani') -> dict:
        """Return the positive fixture, ready to be altered."""
        return copy.deepcopy(fixture_record(name))

    def _commit(self, relative: str, text: str, message: str) -> None:
        """Replace one tracked file and commit it, so Git still tracks the path."""
        (self.root / relative).write_text(text, encoding='utf-8')
        run_git(self.root, 'add', '-A')
        run_git(self.root, 'commit', '-q', '-m', message)


class TamperedEvidence(ScratchCheckout, unittest.TestCase):
    """Each tampered artefact stops the record being admitted."""

    def test_a_tampered_log_is_refused(self):
        """Require the log digest to be checked against the bytes on disk."""
        log = self.root / 'scripts/tests/fixtures/kani_logs/default_unwind.log'
        log.write_text(log.read_text(encoding='utf-8').replace('SUCCESSFUL', 'FAILED'), encoding='utf-8')
        run_git(self.root, 'add', '-A')
        run_git(self.root, 'commit', '-q', '-m', 'Tamper with the log')
        record = self.record()
        self.assertIsNone(log_result(self.root, record, KANI),
                          'a log whose bytes differ from its digest must not bind')
        self.assertIn('verdict-self-reported', admit(self.root, record).reasons,
                      'a record citing a tampered log is self-reported')

    def test_a_tampered_manifest_is_refused(self):
        """Require the manifest digest to be checked, not merely its existence."""
        manifest = self.root / 'scripts/tests/fixtures/evidence/default-unwind-manifest.json'
        document = json.loads(manifest.read_text(encoding='utf-8'))
        document['harnesses'] = document['harnesses'][:1]
        manifest.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        run_git(self.root, 'add', '-A')
        run_git(self.root, 'commit', '-q', '-m', 'Tamper with the manifest')
        record = self.record()
        self.assertIsNone(trust_audit(self.root, record, KANI),
                          'a manifest whose bytes differ from its digest must not bind')
        self.assertIn('trust-unaudited', admit(self.root, record).reasons,
                      'an unbound manifest leaves the trust claim unaudited')

    def test_an_unregistered_tool_yields_no_result(self):
        """Require the adapter to run only for a tool the repository registered."""
        record = self.record()
        record['method']['tool'] = 'z3'
        self.assertIsNone(log_result(ROOT, record, KANI),
                          'an unregistered tool must select no adapter')

    def test_an_untracked_log_is_refused(self):
        """Require a Git-tracked log, so a record cannot cite working-tree litter."""
        untracked = self.root / 'scripts/tests/fixtures/kani_logs/unreviewed.log'
        # Any bytes will do: the point is that Git does not track this file, so
        # its digest matching the record must not be enough to bind it.
        untracked.write_text('unreviewed capture\n', encoding='utf-8')
        record = self.record()
        record['verdict_source']['log'] = {
            'path': 'scripts/tests/fixtures/kani_logs/unreviewed.log',
            'sha256': digest(untracked),
        }
        missing = log_result(self.root, record, KANI)
        self.assertIsNone(missing, 'an untracked log must not bind even when its digest matches')

    def test_a_path_outside_the_repository_is_refused(self):
        """Require repository-relative paths, so a record cannot cite the host's files."""
        record = self.record()
        record['verdict_source']['log'] = {'path': '../outside.log', 'sha256': 'a' * 64}
        self.assertIsNone(log_result(ROOT, record, KANI),
                          'a path escaping the repository must not bind')

    def test_a_fact_that_disagrees_with_the_log_is_refused(self):
        """Require the gate to compare the parser's facts with the record's claims."""
        record = self.record()
        record['negative_controls'][0]['observed'] = 'not-run'
        admission = admit(ROOT, record)
        self.assertIn('verdict-self-reported', admission.reasons,
                      'a record contradicting its log must not count as parsed')

    def test_a_fabricated_empty_audit_is_refused(self):
        """Require the scanner to have found exactly the items the record lists (DL-16).

        The positive fixture audits the corpus, which the scanner reports four
        items for. Claiming an empty audit is the shape that would otherwise let
        a record hide an unbounded assumption by saying it found none.
        """
        record = self.record()
        record['trust_audit'] = {'status': 'audited', 'items': []}
        admission = admit(ROOT, record)
        self.assertIn('trust-unaudited', admission.reasons,
                      'an audit the scanner did not report as empty must not be believed')

    def test_parser_evidence_cannot_be_relabelled_as_a_test(self):
        """Require a registered parser's record to stay verifier evidence (DL-16)."""
        record = self.record()
        record['evidence_kind'] = 'test'
        record['bounds'] = {'kind': 'not-applicable', 'statement': 'Widened to a test.'}
        admission = admit(ROOT, record)
        self.assertEqual((admission.level, admission.reasons), (Level.REJECTED, ('schema-invalid',)),
                         'a Kani record may not step outside the parser by renaming its kind')


class BoundAuditStopsAtTheManifest(ScratchCheckout, unittest.TestCase):
    """Require the trust audit to read only the sources the manifest bound.

    ``bound_sources`` checks each declared source against its digest and the
    audit then reports what that source contains. The module walk is the gap: a
    manifest binding ``lib.rs`` alone still declares ``mod harnesses;``, so a
    working-tree walk would follow the declaration and report items from a file
    the manifest never bound — and a local edit to that file would change the
    item multiset a record is matched against. Refusing the unbound module is
    the same manifest-scope policy DL-16 states, one level down.
    """

    def test_a_module_outside_the_bound_set_is_refused(self):
        """Refuse the walk rather than audit a file no digest covers."""
        document = json.loads((self.root / MANIFEST).read_text(encoding='utf-8'))
        document['sources'] = document['sources'][:1]
        self._commit(MANIFEST, json.dumps(document, indent=2) + '\n', 'Narrow the manifest')
        record = self.record()
        record['result_artefacts'][0]['sha256'] = digest(self.root / MANIFEST)
        self.assertIsNone(
            trust_audit(self.root, record, KANI),
            'a module the manifest does not bind must refuse the audit, not be read')


if __name__ == '__main__':
    unittest.main()
