"""Prove exception validity on the injected date and each D02 violation (VO-3, P5)."""
from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hypothesis import given, settings, strategies as st

from docs_validation.evidence_gate import Level, abstract_record, admit, exception_state
from docs_validation.exceptions import exception_problems
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
        for day, expected in ((APPROVED - DAY, 'not-yet-valid'), (APPROVED, 'active'),
                              (INVALID_FROM - DAY, 'active'), (INVALID_FROM, 'expired')):
            with self.subTest(day=day):
                self.assertEqual(state_on(day), expected, f'{day} must be {expected}')

    def test_complete_active_exception_restricts(self):
        state = next(item for item in VALID if item.exception == 'active' and item.kind == 'deductive'
                     and item.binding == 'current' and item.witness == 'all-satisfied'
                     and item.controls == 'all-required-rejected-as-intended' and item.trust == 'audited-none'
                     and item.run_mode == 'full-profile' and item.verdict_source == 'log-parser')
        self.assertEqual(admit(state).level, Level.RESTRICTED, 'an active exception yields restricted, never proof')


class Malformed(unittest.TestCase):
    """Each D02 violation has its own reason."""

    def problems(self, **changes: str) -> list[str]:
        return exception_problems(ENTRY | changes, 'leynos', frozenset())

    def test_well_formed_exception_has_no_problems(self):
        self.assertEqual(self.problems(), [], 'the reference exception satisfies D02')

    def test_each_violation_is_named(self):
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
        self.assertEqual(exception_problems(ENTRY, 'leynos', frozenset({'4.3.3'})), ['past-release-gate'],
                         'an exception cannot outlive its release gate')

    def test_ninety_days_is_allowed(self):
        self.assertEqual(self.problems(invalid_from=(APPROVED + datetime.timedelta(days=90)).isoformat()), [],
                         'exactly 90 days is within D02')


class DateSensitivity(unittest.TestCase):
    """P5: the evaluation date changes only the exception field of the abstraction."""

    @settings(max_examples=200, derandomize=True, deadline=None)
    @given(st.sampled_from(VALID), st.dates(datetime.date(2026, 1, 1), datetime.date(2027, 12, 31)))
    def test_as_of_changes_only_the_exception_state(self, state, day):
        record, exceptions = concrete(state)
        baseline = abstract_record(record, exceptions, BINDINGS, AS_OF, PARSERS)
        moved = abstract_record(record, exceptions, BINDINGS, day, PARSERS)
        self.assertEqual(moved.__class__(**{**vars(baseline), 'exception': moved.exception}), moved,
                         'only the exception field may depend on the date')


if __name__ == '__main__':
    unittest.main()
