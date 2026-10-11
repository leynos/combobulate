"""Prove frozen governance records change only through new records (VO-7)."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.freeze import check_decisions_frozen, check_frozen

ACCEPTED = {'id': 'D04', 'subject': 'Package licence', 'lifecycle': 'accepted', 'decided_option': 'A',
            'supersedes': [], 'superseded_by': None}
PROPOSED = {'id': 'D05', 'subject': 'External publication policy', 'lifecycle': 'proposed',
            'decided_option': None, 'supersedes': [], 'superseded_by': None}


def register(*records: dict) -> dict:
    """Wrap decision records in a minimal register."""
    return {'decisions': [copy.deepcopy(record) for record in records]}


class DecisionFreeze(unittest.TestCase):
    """Accepted decisions are append-only; proposed ones may still change."""

    def test_unchanged_register_passes(self):
        check_decisions_frozen(register(ACCEPTED, PROPOSED), register(ACCEPTED, PROPOSED))

    def test_proposed_record_may_change(self):
        check_decisions_frozen(register(PROPOSED), register(PROPOSED | {'subject': 'Publication policy'}))

    def test_editing_an_accepted_record_fails(self):
        with self.assertRaisesRegex(AssertionError, r'Accepted decision D04 was edited \(decided_option\)'):
            check_decisions_frozen(register(ACCEPTED), register(ACCEPTED | {'decided_option': 'B'}))

    def test_deleting_an_accepted_record_fails(self):
        with self.assertRaisesRegex(AssertionError, 'Accepted decision D04 was deleted'):
            check_decisions_frozen(register(ACCEPTED), register())

    def test_supersession_may_change_only_lifecycle_and_link(self):
        superseded = ACCEPTED | {'lifecycle': 'superseded', 'superseded_by': 'D16'}
        check_decisions_frozen(register(ACCEPTED), register(superseded))
        with self.assertRaisesRegex(AssertionError, r'was edited \(subject\)'):
            check_decisions_frozen(register(ACCEPTED), register(superseded | {'subject': 'Licence'}))

    def test_superseded_record_is_fully_frozen(self):
        superseded = ACCEPTED | {'lifecycle': 'superseded', 'superseded_by': 'D16'}
        with self.assertRaisesRegex(AssertionError, r'was edited \(superseded_by\)'):
            check_decisions_frozen(register(superseded), register(superseded | {'superseded_by': 'D17'}))


class BaseRevisionIntegration(unittest.TestCase):
    """The checker reads the base revision from Git rather than trusting the head."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git('init', '-q')
        (self.root / 'spec').mkdir()
        (self.root / 'README.md').write_text('# Fixture\n', encoding='utf-8')
        self.git('add', 'README.md')
        self.git('commit', '-q', '-m', 'Start')

    def git(self, *args: str) -> None:
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.org',
                        '-c', 'commit.gpgsign=false', *args], cwd=self.root, check=True, capture_output=True)

    def write(self, value: dict) -> None:
        (self.root / 'spec/decisions.json').write_text(json.dumps(value), encoding='utf-8')

    def test_no_base_revision_reports_that_the_check_did_not_run(self):
        self.assertIn('not run', check_frozen(ValidationContext(self.root), None), 'a skipped check says so')

    def test_register_absent_at_base_has_nothing_frozen(self):
        self.write(register(ACCEPTED))
        summary = check_frozen(ValidationContext(self.root), 'HEAD')
        self.assertIn('no frozen registers', summary, 'a new register freezes nothing yet')

    def test_head_edit_of_committed_acceptance_fails(self):
        self.write(register(ACCEPTED))
        self.git('add', 'spec/decisions.json')
        self.git('commit', '-q', '-m', 'Accept D04')
        self.write(register(ACCEPTED | {'decided_option': 'B'}))
        with self.assertRaisesRegex(AssertionError, 'Accepted decision D04 was edited'):
            check_frozen(ValidationContext(self.root), 'HEAD')

    def test_unknown_base_revision_fails(self):
        with self.assertRaisesRegex(AssertionError, 'Cannot read spec/decisions.json at base revision'):
            check_frozen(ValidationContext(self.root), 'no-such-revision')


if __name__ == '__main__':
    unittest.main()
