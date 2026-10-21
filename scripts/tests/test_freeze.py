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

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.context import ValidationContext
from docs_validation.freeze import check_controls_frozen, check_decisions_frozen, check_exceptions_frozen, check_frozen
from docs_validation.revision_reader import (
    git_bytes_at_revision, git_head_revision, git_json_at_revision, working_tree_bytes,
)

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
        """Reject a threshold change that bypasses the amendment history."""
        edited = copy.deepcopy(CONTROL)
        edited['frozen']['decision_rule']['thresholds']['upper_bound_ratio'] = 1.5
        edited['digest'] = 'b' * 64
        with self.assertRaisesRegex(AssertionError, 'AC-03 changed frozen fields without an amendment'):
            check_controls_frozen(controls(CONTROL), controls(edited))

    def test_appended_amendment_passes(self):
        """Accept a control change recorded as an appended amendment."""
        edited = copy.deepcopy(CONTROL) | {'digest': 'b' * 64, 'amendments': [amendment('a' * 64, 'b' * 64)]}
        check_controls_frozen(controls(CONTROL), controls(edited))

    def test_registered_digest_cannot_change_in_place(self):
        """Keep the original control registration digest immutable."""
        edited = copy.deepcopy(CONTROL) | {'registered_digest': 'b' * 64}
        with self.assertRaisesRegex(AssertionError, 'AC-03 changed its registration digest',
                                    msg='the original registration digest must remain immutable'):
            check_controls_frozen(controls(CONTROL), controls(edited))

    def test_first_appended_amendment_must_replace_the_previous_digest(self):
        """Require the first new amendment to extend the current digest."""
        edited = copy.deepcopy(CONTROL) | {
            'digest': 'b' * 64,
            'amendments': [amendment('c' * 64, 'b' * 64)],
        }
        with self.assertRaisesRegex(AssertionError,
                                    'AC-03 changed frozen fields without an amendment replacing a{12}',
                                    msg='the first amendment must continue the registered digest chain'):
            check_controls_frozen(controls(CONTROL), controls(edited))

    def test_edited_amendment_fails(self):
        """Reject edits to an amendment already present at the base."""
        base = copy.deepcopy(CONTROL) | {'digest': 'b' * 64, 'amendments': [amendment('a' * 64, 'b' * 64)]}
        head = copy.deepcopy(base)
        head['amendments'][0]['reason'] = 'Rewritten.'
        with self.assertRaisesRegex(AssertionError, 'AC-03 edited or removed an amendment'):
            check_controls_frozen(controls(base), controls(head))

    def test_deleted_control_fails(self):
        """Reject deleting a registered control from the head register."""
        with self.assertRaisesRegex(AssertionError, 'Registered control AC-03 was deleted'):
            check_controls_frozen(controls(CONTROL), controls())

    def test_outcome_verdict_mapping_is_frozen(self):
        """Keep the registered outcome-to-verdict mapping unchanged."""
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
        """Keep the digest input field declaration unchanged."""
        base = controls(CONTROL)
        edited = controls(CONTROL)
        edited['frozen_fields'].append('analysis')
        with self.assertRaisesRegex(AssertionError, 'Registered frozen_fields list was edited in place',
                                    msg='the digest input declaration must not change in place'):
            check_controls_frozen(base, edited)

    @settings(max_examples=40, derandomize=True, deadline=None)
    @given(st.lists(st.text(alphabet='0123456789abcdef', min_size=64, max_size=64)
                    .filter(lambda digest: digest != CONTROL['registered_digest']),
                    min_size=2, max_size=6, unique=True))
    def test_generated_amendment_prefix_preserves_historical_records(self, digests: list[str]) -> None:
        """Accept generated append-only chains and reject edits or removals from their historical prefix."""
        head_control = copy.deepcopy(CONTROL)
        previous = head_control['registered_digest']
        for digest in digests:
            head_control['amendments'].append(amendment(previous, digest))
            previous = digest
        head_control['digest'] = previous

        base_control = copy.deepcopy(head_control)
        base_control['amendments'] = base_control['amendments'][:1]
        base_control['digest'] = digests[0]
        base = controls(base_control)
        head = controls(head_control)
        check_controls_frozen(base, head)

        edited_history = copy.deepcopy(head)
        edited_history['controls'][0]['amendments'][0]['reason'] = 'Rewritten.'
        with self.assertRaisesRegex(AssertionError, 'edited or removed an amendment'):
            check_controls_frozen(base, edited_history)

        removed_history = copy.deepcopy(head)
        removed_history['controls'][0]['amendments'].pop(0)
        with self.assertRaisesRegex(AssertionError, 'edited or removed an amendment'):
            check_controls_frozen(base, removed_history)


EXCEPTION = {
    'id': 'EXC-0001',
    'component': 'PF14.structural@1.1.4',
    'owner': 'leynos',
    'approved_by': 'leynos',
    'approval_reference': 'https://example.org/approval',
    'approved_on': '2026-10-12',
    'invalid_from': '2026-11-01',
    'narrowed_claim': 'The named trust boundary remains explicit.',
    'release_gate': '4.3.3',
    'reason': 'A concrete exception record for freeze tests.',
}


def exceptions(*entries: dict) -> dict:
    """Wrap exception entries in a minimal register."""
    return {'exceptions': [copy.deepcopy(entry) for entry in entries]}


class ExceptionFreeze(unittest.TestCase):
    """VO-7: approved exceptions are immutable and replaced by new identifiers."""

    def test_unchanged_exception_passes(self):
        """Preserve an approved exception without rewriting its record."""
        check_exceptions_frozen(exceptions(EXCEPTION), exceptions(EXCEPTION))

    def test_editing_an_approved_exception_fails(self):
        """Reject changing the narrowed claim on an approved exception."""
        edited = EXCEPTION | {'narrowed_claim': 'A broadened claim.'}
        with self.assertRaisesRegex(AssertionError, 'Approved exception EXC-0001 was altered or deleted'):
            check_exceptions_frozen(exceptions(EXCEPTION), exceptions(edited))

    def test_deleting_an_approved_exception_fails(self):
        """Reject deleting an approved exception rather than adding a replacement."""
        with self.assertRaisesRegex(AssertionError, 'Approved exception EXC-0001 was altered or deleted'):
            check_exceptions_frozen(exceptions(EXCEPTION), exceptions())


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
                                      ('base', 'spec/acceptance-controls.json'),
                                      ('base', 'spec/exceptions.json')],
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

    def test_head_revision_reads_the_current_commit(self) -> None:
        """Bind checker evidence to the repository's checked-out commit."""
        expected = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.root, check=True,
                                  capture_output=True, text=True).stdout.strip()
        self.assertEqual(git_head_revision(self.root), expected,
                         'the revision adapter must return the checked-out commit')

    def test_changed_committed_exception_fails_through_freeze_dispatch(self) -> None:
        """Run the registered exception freeze check against a real Git base revision."""
        register_path = self.root / 'spec/exceptions.json'
        register_path.write_text(json.dumps(exceptions(EXCEPTION)), encoding='utf-8')
        self.git('add', 'spec/exceptions.json')
        self.git('commit', '-q', '-m', 'Add approved exception')
        base_revision = git_head_revision(self.root)
        register_path.write_text(
            json.dumps(exceptions(EXCEPTION | {'reason': 'Edited in place.'})), encoding='utf-8'
        )
        context = ValidationContext(self.root)
        with self.assertRaisesRegex(AssertionError, 'Approved exception EXC-0001 was altered or deleted'):
            check_frozen(context, base_revision, partial(git_json_at_revision, self.root))

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
        with self.assertRaisesRegex(AssertionError, 'Cannot resolve base revision no-such-revision'):
            check_frozen(context, 'no-such-revision', reader)

    def write_accepted_decision_with_adr(self, adr_path: str, adr_content: bytes) -> str:
        """Commit a minimal accepted decision and its linked ADR as the freeze base."""
        adr = self.root / adr_path
        adr.parent.mkdir(parents=True, exist_ok=True)
        adr.write_bytes(adr_content)
        decisions = ACCEPTED | {'adr': adr_path}
        (self.root / 'spec/decisions.json').write_text(
            json.dumps(register(decisions)), encoding='utf-8'
        )
        self.git('add', 'spec/decisions.json', adr_path)
        self.git('commit', '-q', '-m', 'Accept a decision with an ADR')
        return git_head_revision(self.root)

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
        old_path = 'docs/adrs/adr-0002-governance-authority.md'
        new_path = 'docs/adrs/adr-0002-governance-authority-and-exceptions.md'
        content = b'# Governance authority\n\nAccepted policy.\n'
        base_revision = self.write_accepted_decision_with_adr(old_path, content)
        (self.root / old_path).rename(self.root / new_path)
        (self.root / 'spec/decisions.json').write_text(
            json.dumps(register(ACCEPTED | {'adr': new_path})), encoding='utf-8'
        )

        summary = self.check_with_file_readers(base_revision)

        self.assertIn('spec/decisions.json', summary,
                      'an unchanged accepted decision remains frozen after its ADR moves')

    def test_edited_adr_content_does_not_qualify_as_a_relocation(self) -> None:
        """Reject an ADR pointer change when the moved document also changes."""
        old_path = 'docs/adrs/adr-0002-governance-authority.md'
        new_path = 'docs/adrs/adr-0002-governance-authority-and-exceptions.md'
        base_revision = self.write_accepted_decision_with_adr(old_path, b'# Original\n')
        (self.root / old_path).rename(self.root / new_path)
        (self.root / new_path).write_bytes(b'# Rewritten\n')
        (self.root / 'spec/decisions.json').write_text(
            json.dumps(register(ACCEPTED | {'adr': new_path})), encoding='utf-8'
        )

        with self.assertRaisesRegex(AssertionError, r'Accepted decision D04 was edited \(adr\)'):
            self.check_with_file_readers(base_revision)

    def test_adr_pointer_change_does_not_qualify_while_old_path_remains(self) -> None:
        """Reject a pointer rewrite that leaves the original ADR in place."""
        old_path = 'docs/adrs/adr-0002-governance-authority.md'
        new_path = 'docs/adrs/adr-0002-governance-authority-and-exceptions.md'
        content = b'# Governance authority\n'
        base_revision = self.write_accepted_decision_with_adr(old_path, content)
        destination = self.root / new_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        (self.root / 'spec/decisions.json').write_text(
            json.dumps(register(ACCEPTED | {'adr': new_path})), encoding='utf-8'
        )

        with self.assertRaisesRegex(AssertionError, r'Accepted decision D04 was edited \(adr\)'):
            self.check_with_file_readers(base_revision)

    def test_adr_pointer_change_does_not_qualify_when_destination_already_existed(self) -> None:
        """Reject a pointer rewrite to a pre-existing duplicate rather than a moved file."""
        old_path = 'docs/adrs/adr-0002-governance-authority.md'
        new_path = 'docs/adrs/adr-0002-governance-authority-and-exceptions.md'
        content = b'# Governance authority\n'
        self.write_accepted_decision_with_adr(old_path, content)
        destination = self.root / new_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        self.git('add', new_path)
        self.git('commit', '-q', '-m', 'Add duplicate ADR')
        base_revision = git_head_revision(self.root)
        (self.root / old_path).unlink()
        (self.root / 'spec/decisions.json').write_text(
            json.dumps(register(ACCEPTED | {'adr': new_path})), encoding='utf-8'
        )

        with self.assertRaisesRegex(AssertionError, r'Accepted decision D04 was edited \(adr\)'):
            self.check_with_file_readers(base_revision)


if __name__ == '__main__':
    unittest.main()
