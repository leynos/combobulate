"""Prove the freeze check separates an ADR file move from an accepted-decision edit.

A canonical ADR rename changes only the decision's ``adr`` pointer, so the
base-revision freeze rule would reject it as an edit. These cases drive the
production Git and working-tree readers against a disposable repository and
show that only a verified move qualifies: both paths canonical, the
destination new at the base, the old path gone, and the bytes unchanged.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.freeze import check_frozen
from docs_validation.revision_reader import (
    git_bytes_at_revision, git_head_revision, git_json_at_revision, working_tree_bytes,
)

DecisionRecord = dict[str, object]
DecisionRegister = dict[str, list[DecisionRecord]]

OLD_PATH = 'docs/adrs/adr-0002-governance-authority.md'
NEW_PATH = 'docs/adrs/adr-0002-governance-authority-and-exceptions.md'
ACCEPTED: DecisionRecord = {'id': 'D04', 'subject': 'Package licence', 'lifecycle': 'accepted',
                            'decided_option': 'A', 'supersedes': [], 'superseded_by': None}
EDITED = r'Accepted decision D04 was edited \(adr\)'


def register(record: DecisionRecord) -> DecisionRegister:
    """Wrap one decision record in the minimal register the freeze check reads."""
    return {'decisions': [record]}


class AdrRelocationIntegration(unittest.TestCase):
    """The freeze check verifies ADR moves through the production file readers."""

    def setUp(self) -> None:
        """Create one temporary Git repository with a spec directory."""
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
                        '-c', 'commit.gpgsign=false', *args], cwd=self.root, check=True,
                       capture_output=True)

    def commit_accepted_decision(self, adr_content: bytes) -> str:
        """Commit an accepted decision linked to the canonical old ADR path."""
        adr = self.root / OLD_PATH
        adr.parent.mkdir(parents=True, exist_ok=True)
        adr.write_bytes(adr_content)
        self.write_register(OLD_PATH)
        self.git('add', 'spec/decisions.json', OLD_PATH)
        self.git('commit', '-q', '-m', 'Accept a decision with an ADR')
        return git_head_revision(self.root)

    def write_register(self, adr_path: str) -> None:
        """Write the current register pointing at the named ADR path."""
        (self.root / 'spec/decisions.json').write_text(
            json.dumps(register(ACCEPTED | {'adr': adr_path})), encoding='utf-8'
        )

    def relocate(self, destination: str = NEW_PATH) -> None:
        """Move the old ADR to the destination and point the register at it."""
        (self.root / OLD_PATH).rename(self.root / destination)
        self.write_register(destination)

    def copy_without_removing_old(self) -> None:
        """Write an identical ADR at the destination while leaving the original."""
        destination = self.root / NEW_PATH
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((self.root / OLD_PATH).read_bytes())
        self.write_register(NEW_PATH)

    def check_with_file_readers(self, base_revision: str) -> str:
        """Run the freeze check with the production Git and working-tree readers."""
        return check_frozen(
            ValidationContext(self.root), base_revision,
            partial(git_json_at_revision, self.root),
            partial(git_bytes_at_revision, self.root),
            partial(working_tree_bytes, self.root),
        )

    def test_byte_identical_adr_move_preserves_accepted_decision(self) -> None:
        """Allow an ADR filename correction when the accepted decision is unchanged."""
        base_revision = self.commit_accepted_decision(b'# Governance authority\n\nAccepted policy.\n')
        self.relocate()

        summary = self.check_with_file_readers(base_revision)

        self.assertIn('spec/decisions.json', summary,
                      'an unchanged accepted decision remains frozen after its ADR moves')

    def test_edited_adr_content_does_not_qualify_as_a_relocation(self) -> None:
        """Reject an ADR pointer change when the moved document also changes."""
        base_revision = self.commit_accepted_decision(b'# Original\n')
        self.relocate()
        (self.root / NEW_PATH).write_bytes(b'# Rewritten\n')

        with self.assertRaisesRegex(AssertionError, EDITED):
            self.check_with_file_readers(base_revision)

    def test_adr_pointer_change_does_not_qualify_while_old_path_remains(self) -> None:
        """Reject a pointer rewrite that leaves the original ADR in place."""
        base_revision = self.commit_accepted_decision(b'# Governance authority\n')
        self.copy_without_removing_old()

        with self.assertRaisesRegex(AssertionError, EDITED):
            self.check_with_file_readers(base_revision)

    def test_adr_pointer_change_does_not_qualify_when_destination_already_existed(self) -> None:
        """Reject a pointer rewrite to a pre-existing duplicate rather than a moved file."""
        self.commit_accepted_decision(b'# Governance authority\n')
        self.copy_without_removing_old()
        self.git('add', NEW_PATH)
        self.git('commit', '-q', '-m', 'Add duplicate ADR')
        base_revision = git_head_revision(self.root)
        (self.root / OLD_PATH).unlink()

        with self.assertRaisesRegex(AssertionError, EDITED):
            self.check_with_file_readers(base_revision)

    def test_non_canonical_destination_does_not_qualify_as_a_relocation(self) -> None:
        """Reject a move to a path outside the canonical ADR naming scheme."""
        base_revision = self.commit_accepted_decision(b'# Governance authority\n')
        self.relocate('docs/adrs/renamed.md')

        with self.assertRaisesRegex(AssertionError, EDITED):
            self.check_with_file_readers(base_revision)


if __name__ == '__main__':
    unittest.main()
