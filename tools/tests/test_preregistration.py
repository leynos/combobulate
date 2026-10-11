"""Prove pre-registration freezes every field and outcomes cannot be relabelled (VO-11, VO-12, VO-16)."""
from __future__ import annotations

import copy
import itertools
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import given, settings, strategies as st
from jsonschema import Draft202012Validator

from docs_validation.context import ValidationContext
from docs_validation.preregistration import (
    FROZEN_FIELDS, OUTCOME_VERDICTS, check_acceptance_controls, check_amendment_chain, check_completeness, check_sources,
    check_host_identity, frozen_digest, verdict,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ValidationContext(ROOT).load('spec/acceptance-controls.json')
CONTROL = REGISTER['controls'][0]
SPONSOR = 'leynos'


def amended(control: dict, field: str, value: object) -> dict:
    """Return a copy with one frozen field changed through an approved amendment."""
    edited = copy.deepcopy(control)
    edited['frozen'][field] = value
    new_digest = frozen_digest(edited)
    edited['amendments'].append({'date': '2026-10-12', 'approved_by': SPONSOR,
                                 'approval_reference': 'https://example.org/approval',
                                 'replaces': edited['digest'], 'new_digest': new_digest, 'reason': 'Test.'})
    edited['digest'] = new_digest
    return edited


class Registration(unittest.TestCase):
    """VO-11: every frozen field is digested, and changes need an approved amendment chain."""

    def test_committed_register_passes(self):
        # Only the host name is supplied: user names leak through home paths, which the
        # check always rejects, and a generic CI user such as `runner` is an ordinary word.
        check_acceptance_controls(ValidationContext(ROOT), (socket.gethostname(),))

    def test_register_lists_the_frozen_fields(self):
        self.assertEqual(REGISTER['frozen_fields'], list(FROZEN_FIELDS), 'the register must state its frozen fields')

    def test_missing_calibration_reference_fails(self):
        control = copy.deepcopy(CONTROL)
        del control['frozen']['calibration']
        with self.assertRaisesRegex(AssertionError, 'lacks frozen fields: calibration'):
            check_completeness(control)

    def test_threshold_and_digest_edited_together_fail(self):
        control = copy.deepcopy(CONTROL)
        control['frozen']['decision_rule']['thresholds'] = {'anything': 1}
        control['digest'] = frozen_digest(control)
        with self.assertRaisesRegex(AssertionError, 'digest is not the end of its amendment chain'):
            check_amendment_chain(control, SPONSOR)

    def test_correct_amendment_passes(self):
        check_amendment_chain(amended(CONTROL, 'seeds', [7]), SPONSOR)

    def test_amendment_needs_the_sponsor(self):
        control = amended(CONTROL, 'seeds', [7])
        control['amendments'][-1]['approved_by'] = 'someone-else'
        with self.assertRaisesRegex(AssertionError, 'not approved by the sponsor'):
            check_amendment_chain(control, SPONSOR)

    def test_changed_source_needs_an_amendment(self):
        control = next(item for item in REGISTER['controls'] if item['id'] == 'AC-07')
        check_sources(control, ROOT)
        stale = copy.deepcopy(control)
        stale['frozen']['workload']['sources'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(AssertionError, r'AC-07 source \.github/workflows/ci\.yml changed since registration'):
            check_sources(stale, ROOT)

    def test_source_outside_the_repository_fails(self):
        control = copy.deepcopy(next(item for item in REGISTER['controls'] if item['id'] == 'AC-07'))
        for path in ('../outside.yml', '/etc/hostname'):
            control['frozen']['workload']['sources'][0]['path'] = path
            with self.subTest(path=path), self.assertRaisesRegex(AssertionError, 'escapes the repository'):
                check_sources(control, ROOT)

    def test_every_frozen_field_changes_the_digest(self):
        exercised: set[str] = set()

        @settings(max_examples=200, derandomize=True, deadline=None)
        @given(st.sampled_from(FROZEN_FIELDS), st.integers())
        def mutate(field: str, value: int) -> None:
            exercised.add(field)
            control = copy.deepcopy(CONTROL)
            control['frozen'][field] = {'mutated': value}
            self.assertNotEqual(frozen_digest(control), CONTROL['digest'], f'{field} must be covered by the digest')
            with self.assertRaises(AssertionError):
                check_amendment_chain(control, SPONSOR)

        mutate()
        self.assertEqual(exercised, set(FROZEN_FIELDS), 'every frozen field must be exercised')


RECORD_OUTCOMES = sorted(OUTCOME_VERDICTS)


RECORD_VALIDATOR = Draft202012Validator(ValidationContext(ROOT).load('spec/measurement-record.schema.json'),
                                        format_checker=Draft202012Validator.FORMAT_CHECKER)


def record(outcome: str, purpose: str = 'acceptance', digest: str | None = None) -> dict:
    """Build one schema-valid measurement record for the first control."""
    entry = {'id': 'fixture', 'purpose': purpose, 'control_ids': [CONTROL['id']],
             'control_digest': digest or CONTROL['digest'], 'recorded_on': '2026-10-12',
             'hardware': {'class': 'github-hosted-runner', 'cpu_model': 'fixture', 'cores': 4, 'threads': 4,
                          'memory_gib': 16, 'os_family': 'Ubuntu 24.04', 'kernel_major': 6},
             'toolchains': {}, 'workloads': [{'id': 'w', 'description': 'Fixture.', 'command': 'true',
                                              'metric': 'wall time', 'unit': 's', 'samples': [1], 'median': 1}]}
    if purpose == 'acceptance':
        entry['outcome'] = outcome
    RECORD_VALIDATOR.validate(entry)
    return entry


class Outcomes(unittest.TestCase):
    """VO-12: exhaustive enumeration of outcome sequences; nothing but passes can pass."""

    def test_failure_like_outcomes_never_pass(self):
        for outcome in ('budget-exceeded', 'resource-exhausted', 'missing', 'inconclusive'):
            with self.subTest(outcome=outcome):
                self.assertNotEqual(OUTCOME_VERDICTS[outcome], 'pass', f'{outcome} must not map to pass')

    def test_every_retry_counts(self):
        for length in range(1, 4):
            for outcomes in itertools.product(RECORD_OUTCOMES, repeat=length):
                result = verdict(CONTROL, [record(outcome) for outcome in outcomes])
                expected_pass = all(outcome == 'pass' for outcome in outcomes)
                self.assertEqual(result == 'pass', expected_pass, f'{outcomes} gave {result}')

    def test_calibration_records_never_count(self):
        for outcome in RECORD_OUTCOMES:
            records = [record(outcome, purpose='calibration')]
            self.assertEqual(verdict(CONTROL, records), 'not-run', 'calibration never satisfies a control')

    def test_records_for_a_superseded_digest_do_not_count(self):
        self.assertEqual(verdict(CONTROL, [record('pass', digest='0' * 64)]), 'not-run',
                         'evidence must bind the current digest')

    def test_seeded_mapping_fault_is_detected(self):
        faulty = dict(OUTCOME_VERDICTS, **{'resource-exhausted': 'pass'})
        outcomes = [faulty[name] for name in ('pass', 'resource-exhausted')]
        self.assertEqual(set(outcomes), {'pass'}, 'the seeded fault would pass an exhausted run')
        self.assertEqual(verdict(CONTROL, [record('pass'), record('resource-exhausted')]), 'fail',
                         'the real mapping fails it')


class HostIdentity(unittest.TestCase):
    """VO-16: committed records carry hardware class only."""

    def test_home_path_fails(self):
        with self.assertRaisesRegex(AssertionError, 'contains a home path'):
            check_host_identity('record.json', '{"command": "/home/someone/bin/verus"}')

    def test_supplied_host_name_fails(self):
        with self.assertRaisesRegex(AssertionError, "contains host identity 'build-box-7'"):
            check_host_identity('record.json', '{"notes": "measured on build-box-7"}', ('build-box-7',))

    def test_clean_record_passes(self):
        check_host_identity('record.json', '{"hardware": {"cpu_model": "AMD Ryzen 9 3900"}}', ('build-box-7',))


if __name__ == '__main__':
    unittest.main()
