"""Prove frozen governance records change only through new records (VO-7)."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.freeze import check_controls_frozen, check_decisions_frozen, check_frozen
from docs_validation.revision_reader import git_json_at_revision

DecisionRecord = dict[str, object]
DecisionRegister = dict[str, list[DecisionRecord]]

ACCEPTED: DecisionRecord = {'id': 'D04', 'subject': 'Package licence', 'lifecycle': 'accepted', 'decided_option': 'A',
            'supersedes': [], 'superseded_by': None}
PROPOSED: DecisionRecord = {'id': 'D05', 'subject': 'External publication policy', 'lifecycle': 'proposed',
            'decided_option': None, 'supersedes': [], 'superseded_by': None}


def register(*records: DecisionRecord) -> DecisionRegister:
    """Wrap decision records in a minimal register."""
    return {'decisions': [copy.deepcopy(record) for record in records]}


class DecisionFreeze(unittest.TestCase):
    """Accepted decisions are append-only; proposed ones may still change."""

    def test_unchanged_register_passes(self) -> None:
        """Accept a head register that preserves every frozen decision field."""
        check_decisions_frozen(register(ACCEPTED, PROPOSED), register(ACCEPTED, PROPOSED))

    def test_proposed_record_may_change(self) -> None:
        """Leave proposed decisions editable until they are accepted."""
        check_decisions_frozen(register(PROPOSED), register(PROPOSED | {'subject': 'Publication policy'}))

    def test_editing_an_accepted_record_fails(self) -> None:
        """Reject an in-place edit to an accepted decision's selected option."""
        with self.assertRaisesRegex(AssertionError, r'Accepted decision D04 was edited \(decided_option\)'):
            check_decisions_frozen(register(ACCEPTED), register(ACCEPTED | {'decided_option': 'B'}))

    def test_deleting_an_accepted_record_fails(self) -> None:
        """Reject deleting an accepted record instead of superseding it."""
        with self.assertRaisesRegex(AssertionError, 'Accepted decision D04 was deleted'):
            check_decisions_frozen(register(ACCEPTED), register())

    def test_supersession_may_change_only_lifecycle_and_link(self) -> None:
        """Permit the supersession fields while keeping all other accepted fields frozen."""
        superseded = ACCEPTED | {'lifecycle': 'superseded', 'superseded_by': 'D16'}
        check_decisions_frozen(register(ACCEPTED), register(superseded))
        with self.assertRaisesRegex(AssertionError, r'was edited \(subject\)'):
            check_decisions_frozen(register(ACCEPTED), register(superseded | {'subject': 'Licence'}))

    def test_superseded_record_is_fully_frozen(self) -> None:
        """Reject edits to a record after its accepted decision has been superseded."""
        superseded = ACCEPTED | {'lifecycle': 'superseded', 'superseded_by': 'D16'}
        with self.assertRaisesRegex(AssertionError, r'was edited \(superseded_by\)'):
            check_decisions_frozen(register(superseded), register(superseded | {'superseded_by': 'D17'}))


CONTROL = {'id': 'AC-03', 'registered_digest': 'a' * 64, 'digest': 'a' * 64, 'amendments': [],
           'frozen': {'decision_rule': {'thresholds': {'upper_bound_ratio': 1.25}}}}


def controls(*entries: dict, outcome_verdicts: dict | None = None) -> dict:
    """Wrap control records in a minimal register."""
    return {
        'frozen_fields': ['control'],
        'outcome_verdicts': copy.deepcopy(outcome_verdicts if outcome_verdicts is not None else {'pass': 'pass'}),
        'controls': [copy.deepcopy(entry) for entry in entries],
    }


def amendment(replaces: str, new_digest: str) -> dict:
    """Build one sponsor-approved amendment."""
    return {'date': '2026-10-12', 'approved_by': 'leynos', 'approval_reference': 'https://example.org/approval',
            'replaces': replaces, 'new_digest': new_digest, 'reason': 'Test.'}


class ControlFreeze(unittest.TestCase):
    """VO-7 for controls: frozen fields change only through an appended amendment."""

    def test_threshold_and_digest_edited_together_fail(self):
        edited = copy.deepcopy(CONTROL)
        edited['frozen']['decision_rule']['thresholds']['upper_bound_ratio'] = 1.5
        edited['digest'] = 'b' * 64
        with self.assertRaisesRegex(AssertionError, 'AC-03 changed frozen fields without an amendment'):
            check_controls_frozen(controls(CONTROL), controls(edited))

    def test_appended_amendment_passes(self):
        edited = copy.deepcopy(CONTROL) | {'digest': 'b' * 64, 'amendments': [amendment('a' * 64, 'b' * 64)]}
        check_controls_frozen(controls(CONTROL), controls(edited))

    def test_edited_amendment_fails(self):
        base = copy.deepcopy(CONTROL) | {'digest': 'b' * 64, 'amendments': [amendment('a' * 64, 'b' * 64)]}
        head = copy.deepcopy(base)
        head['amendments'][0]['reason'] = 'Rewritten.'
        with self.assertRaisesRegex(AssertionError, 'AC-03 edited or removed an amendment'):
            check_controls_frozen(controls(base), controls(head))

    def test_deleted_control_fails(self):
        with self.assertRaisesRegex(AssertionError, 'Registered control AC-03 was deleted'):
            check_controls_frozen(controls(CONTROL), controls())

    def test_outcome_verdict_mapping_is_frozen(self):
        base = controls(CONTROL)
        edited_maps = (
            ('added key', {'pass': 'pass', 'fail': 'fail'}),
            ('removed key', {}),
            ('changed value', {'pass': 'fail'}),
        )
        for change, outcome_verdicts in edited_maps:
            with self.subTest(change=change):
                with self.assertRaisesRegex(AssertionError, 'Registered outcome_verdicts mapping was edited in place',
                                            msg=f'{change} to the registered mapping must fail'):
                    check_controls_frozen(base, controls(CONTROL, outcome_verdicts=outcome_verdicts))

    def test_frozen_field_list_is_frozen(self):
        base = controls(CONTROL)
        edited = controls(CONTROL)
        edited['frozen_fields'].append('analysis')
        with self.assertRaisesRegex(AssertionError, 'Registered frozen_fields list was edited in place',
                                    msg='the digest input declaration must not change in place'):
            check_controls_frozen(base, edited)


class BaseRevisionChecks(unittest.TestCase):
    """Freeze rules consume an injected reader, independent of Git command details."""

    def setUp(self) -> None:
        """Create a temporary register and a deterministic fake base reader."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'spec').mkdir()
        self.context = ValidationContext(self.root)
        self.base: DecisionRegister | None = None
        self.reads: list[tuple[str, str]] = []

    def read_base(self, revision: str, path: str) -> dict | None:
        """Return a fixed base value and record the requested repository path."""
        self.reads.append((revision, path))
        return copy.deepcopy(self.base) if path == 'spec/decisions.json' else None

    def write(self, value: DecisionRegister) -> None:
        """Write the current register read by the freeze check."""
        (self.root / 'spec/decisions.json').write_text(json.dumps(value), encoding='utf-8')

    def test_no_base_revision_reports_that_the_check_did_not_run(self) -> None:
        """Report an explicit skip without asking the repository reader."""
        summary = check_frozen(self.context, None, self.read_base)
        self.assertIn('not run', summary, 'a skipped check says so')
        self.assertEqual(self.reads, [], 'a skipped check does not read a base revision')

    def test_register_absent_at_base_has_nothing_frozen(self) -> None:
        """Allow a register introduced after the base because it has no frozen history."""
        self.write(register(ACCEPTED))
        summary = check_frozen(self.context, 'base', self.read_base)
        self.assertIn('no frozen registers', summary, 'a new register freezes nothing yet')
        self.assertEqual(self.reads, [('base', 'spec/decisions.json'),
                                      ('base', 'spec/acceptance-controls.json')],
                         'the checker reads each frozen register from the requested base')

    def test_fake_reader_supplies_the_register_compared_with_the_head(self) -> None:
        """Compare current records with the value supplied by the repository port."""
        self.base = register(ACCEPTED)
        self.write(register(ACCEPTED | {'decided_option': 'B'}))
        with self.assertRaisesRegex(AssertionError, 'Accepted decision D04 was edited'):
            check_frozen(self.context, 'base', self.read_base)
        self.assertEqual(self.reads, [('base', 'spec/decisions.json')],
                         'the freeze rule delegates its base read to the injected port')

    def test_unchanged_base_record_passes(self) -> None:
        """Accept an unchanged accepted decision from an injected base revision."""
        self.base = register(ACCEPTED)
        self.write(register(ACCEPTED))
        summary = check_frozen(self.context, 'base', self.read_base)
        self.assertIn('spec/decisions.json', summary, 'the summary names the checked register')


class GitRevisionReaderIntegration(unittest.TestCase):
    """The production adapter reads committed JSON using Git's actual revision data."""

    def setUp(self) -> None:
        """Create one temporary Git repository for the adapter integration test."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git('init', '-q')
        (self.root / 'spec').mkdir()
        (self.root / 'README.md').write_text('# Fixture\n', encoding='utf-8')
        self.git('add', 'README.md')
        self.git('commit', '-q', '-m', 'Start')

    def git(self, *args: str) -> None:
        """Run a fixture Git command with local identity and signing disabled."""
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.org',
                        '-c', 'commit.gpgsign=false', *args], cwd=self.root, check=True, capture_output=True)

    def test_git_reader_detects_a_changed_committed_decision(self) -> None:
        """Use Git for the base snapshot, then reject the changed working-tree record."""
        context = ValidationContext(self.root)
        reader = partial(git_json_at_revision, self.root)
        self.assertIsNone(reader('HEAD', 'spec/decisions.json'),
                          'a valid base without the register is an expected absence')

        decisions = self.root / 'spec/decisions.json'
        decisions.write_text(json.dumps(register(ACCEPTED)), encoding='utf-8')
        self.git('add', 'spec/decisions.json')
        self.git('commit', '-q', '-m', 'Accept D04')
        decisions.write_text(json.dumps(register(ACCEPTED | {'decided_option': 'B'})), encoding='utf-8')

        with self.assertRaisesRegex(AssertionError, 'Accepted decision D04 was edited'):
            check_frozen(context, 'HEAD', reader)
        with self.assertRaisesRegex(AssertionError, 'Cannot read spec/decisions.json at base revision'):
            check_frozen(context, 'no-such-revision', reader)


if __name__ == '__main__':
    unittest.main()
