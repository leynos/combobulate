"""Prove exception validity on the injected date and each D02 violation (VO-3, P5)."""
from __future__ import annotations

import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hypothesis import given, settings, strategies as st

from docs_validation.context import ValidationContext
from docs_validation.evidence_gate import (
    AbstractRecord, AdmissionContext, Level, abstract_record, admit, exception_state,
)
from docs_validation.exceptions import check_exceptions, exception_problems
from evidence_fixtures import AS_OF, BINDINGS, PARSERS, VALID, concrete

APPROVED, INVALID_FROM = datetime.date(2026, 10, 1), datetime.date(2026, 11, 1)
ENTRY = {'id': 'EXC-0001', 'component': 'PF09.proof@2.4.1', 'owner': 'leynos', 'approved_by': 'leynos',
         'approval_reference': 'https://example.org/approval', 'approved_on': APPROVED.isoformat(),
         'invalid_from': INVALID_FROM.isoformat(), 'narrowed_claim': 'Holds for extents below 2^16.',
         'release_gate': '4.3.3', 'reason': 'Solver timeout pending a lemma.'}
DAY = datetime.timedelta(days=1)


def state_on(day: datetime.date) -> str:
    """Classify the well-formed exception on one day."""
    return exception_state(ENTRY | {'problems': []}, day)


class ValidityWindow(unittest.TestCase):
    """The window is [approved_on, invalid_from): boundaries on both sides."""

    def test_boundaries(self):
        """Check the approval date is inclusive and the expiry date exclusive."""
        for day, expected in ((APPROVED - DAY, 'not-yet-valid'), (APPROVED, 'active'),
                              (INVALID_FROM - DAY, 'active'), (INVALID_FROM, 'expired')):
            with self.subTest(day=day):
                self.assertEqual(state_on(day), expected, f'{day} must be {expected}')

    def test_complete_active_exception_restricts(self):
        """An active exception must restrict an otherwise verified abstract record."""
        state = AbstractRecord(
            kind='deductive', outcome='verified', bounds='not-applicable', witness='all-satisfied',
            controls='all-required-rejected-as-intended', trust='audited-none', exception='active',
            binding='current', run_mode='full-profile', verdict_source='log-parser',
        )
        self.assertEqual(admit(state).level, Level.RESTRICTED, 'an active exception yields restricted, never proof')

    def test_release_gate_expires_an_exception_before_its_date(self):
        """A completed release gate expires an exception immediately."""
        exception = ENTRY | {'problems': ['past-release-gate']}
        self.assertEqual(exception_state(exception, APPROVED), 'expired',
                         'a completed release gate ends an exception immediately')

    def test_other_d02_problems_remain_malformed_after_release_gate(self):
        """Release-gate expiry does not excuse another malformed exception field."""
        exception = ENTRY | {'problems': ['past-release-gate', 'approver-not-sponsor']}
        self.assertEqual(exception_state(exception, APPROVED), 'malformed',
                         'release-gate expiry does not excuse another D02 violation')


class Malformed(unittest.TestCase):
    """Each D02 violation has its own reason."""

    def problems(self, **changes: str) -> list[str]:
        """Return D02 violations after applying fields to the valid fixture."""
        return exception_problems(ENTRY | changes, 'leynos', frozenset())

    def test_well_formed_exception_has_no_problems(self):
        """A complete reference exception satisfies every D02 check."""
        self.assertEqual(self.problems(), [], 'the reference exception satisfies D02')

    def test_each_violation_is_named(self):
        """Report each tested lifetime, authority, claim, and owner defect alone."""
        cases = {
            'lifetime-over-90-days': {'invalid_from': (APPROVED + datetime.timedelta(days=91)).isoformat()},
            'empty-lifetime': {'invalid_from': APPROVED.isoformat()},
            'approver-not-sponsor': {'approved_by': 'someone-else'},
            'missing-narrowed-claim': {'narrowed_claim': ' '},
            'missing-owner': {'owner': ''},
        }
        for problem, changes in cases.items():
            with self.subTest(problem=problem):
                self.assertEqual(self.problems(**changes), [problem], f'{problem} must be reported alone')

    def test_passed_release_gate_is_named(self):
        """Identify a passed release gate as an exception violation."""
        self.assertEqual(exception_problems(ENTRY, 'leynos', frozenset({'4.3.3'})), ['past-release-gate'],
                         'an exception cannot outlive its release gate')

    def test_ninety_days_is_allowed(self):
        """Allow an exception whose lifetime reaches the 90-day limit."""
        self.assertEqual(self.problems(invalid_from=(APPROVED + datetime.timedelta(days=90)).isoformat()), [],
                         'exactly 90 days is within D02')


class RegisterCheck(unittest.TestCase):
    """A released exception remains valid history and cannot be used again."""

    def test_passed_release_gate_is_valid_expired_history(self):
        """Keep a D02-compliant exception as expired history after its release gate."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = root / 'spec'
            spec.mkdir()
            project_root = Path(__file__).resolve().parents[2]
            (spec / 'exception.schema.json').write_text(
                (project_root / 'spec/exception.schema.json').read_text(encoding='utf-8'), encoding='utf-8')
            (spec / 'exceptions.json').write_text(
                json.dumps({'revision': '0.2', 'exceptions': [ENTRY]}), encoding='utf-8')
            (spec / 'decisions.json').write_text(
                json.dumps({'authorities': {'roles': {'sponsor': 'leynos'}}}), encoding='utf-8')
            (spec / 'roadmap.json').write_text(
                json.dumps({'phases': [{'steps': [{'tasks': [{'id': '4.3.3', 'status': 'done'}]}]}]}),
                encoding='utf-8')

            context = ValidationContext(root)
            check_exceptions(context)

        self.assertEqual(context.results[-1]['count'], 1, 'the expired exception remains in the register')
        self.assertEqual(context.results[-1]['detail'],
                         'D02-compliant exception records: 1; expired at release gate: 1.',
                         'the check reports release-gate expiry as history rather than failure')


class DateSensitivity(unittest.TestCase):
    """P5: the evaluation date changes only the exception field of the abstraction."""

    @settings(max_examples=200, derandomize=True, deadline=None)
    @given(st.sampled_from(VALID), st.dates(datetime.date(2026, 1, 1), datetime.date(2027, 12, 31)))
    def test_as_of_changes_only_the_exception_state(self, state, day):
        """Changing the evaluation date alters only the abstract exception status."""
        record, exceptions = concrete(state)
        baseline_context = AdmissionContext(exceptions, BINDINGS, AS_OF, PARSERS)
        moved_context = AdmissionContext(exceptions, BINDINGS, day, PARSERS)
        baseline = abstract_record(record, baseline_context)
        moved = abstract_record(record, moved_context)
        self.assertEqual(moved.__class__(**{**vars(baseline), 'exception': moved.exception}), moved,
                         'only the exception field may depend on the date')


if __name__ == '__main__':
    unittest.main()
