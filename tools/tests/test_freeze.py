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


class BaseRevisionIntegration(unittest.TestCase):
    """The checker reads the base revision from Git rather than trusting the head."""

    def setUp(self) -> None:
        """Create a temporary Git work tree for base-revision integration cases."""
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

    def write(self, value: DecisionRegister) -> None:
        """Write a decision register into the temporary work tree."""
        (self.root / 'spec/decisions.json').write_text(json.dumps(value), encoding='utf-8')

    def test_no_base_revision_reports_that_the_check_did_not_run(self) -> None:
        """Report an explicit skip when the caller provides no base revision."""
        self.assertIn('not run', check_frozen(ValidationContext(self.root), None), 'a skipped check says so')

    def test_register_absent_at_base_has_nothing_frozen(self) -> None:
        """Allow a register introduced after the base because it has no frozen history."""
        self.write(register(ACCEPTED))
        summary = check_frozen(ValidationContext(self.root), 'HEAD')
        self.assertIn('no frozen registers', summary, 'a new register freezes nothing yet')

    def test_head_edit_of_committed_acceptance_fails(self) -> None:
        """Compare committed base content with the work tree and reject an accepted edit."""
        self.write(register(ACCEPTED))
        self.git('add', 'spec/decisions.json')
        self.git('commit', '-q', '-m', 'Accept D04')
        self.write(register(ACCEPTED | {'decided_option': 'B'}))
        with self.assertRaisesRegex(AssertionError, 'Accepted decision D04 was edited'):
            check_frozen(ValidationContext(self.root), 'HEAD')

    def test_unknown_base_revision_fails(self) -> None:
        """Reject a base revision that Git cannot resolve to the frozen register."""
        with self.assertRaisesRegex(AssertionError, 'Cannot read spec/decisions.json at base revision'):
            check_frozen(ValidationContext(self.root), 'no-such-revision')


if __name__ == '__main__':
    unittest.main()
