"""Prove acceptance controls are typed, complete and bound by their measurement records (VO-11)."""
from __future__ import annotations

import copy
import socket
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonschema import Draft202012Validator, ValidationError

from docs_validation.context import ValidationContext
from docs_validation.preregistration import (
    FROZEN_FIELDS, OUTCOME_VERDICTS, check_acceptance_controls, check_completeness, check_measurement_binding,
    check_registration_declarations,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ValidationContext(ROOT).load('spec/acceptance-controls.json')
CONTROL = REGISTER['controls'][0]
CI_CONTROL = next(item for item in REGISTER['controls'] if item['id'] == 'AC-07')
REGISTER_VALIDATOR = Draft202012Validator(
    ValidationContext(ROOT).load('spec/acceptance-controls.schema.json'),
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)
RECORD_VALIDATOR = Draft202012Validator(
    ValidationContext(ROOT).load('spec/measurement-record.schema.json'),
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)
RECORD_OUTCOMES = sorted(OUTCOME_VERDICTS)
TEST_MEASUREMENT_DATE = (date.fromisoformat(CONTROL['frozen']['registered_on']) + timedelta(days=1)).isoformat()
CI_MEASUREMENT_DATE = (date.fromisoformat(CI_CONTROL['frozen']['registered_on']) + timedelta(days=1)).isoformat()


def record(outcome: str, purpose: str = 'acceptance') -> dict:
    """Build one schema-valid measurement record for the first control."""
    entry = {'id': 'fixture', 'purpose': purpose, 'control_ids': [CONTROL['id']],
             'recorded_on': TEST_MEASUREMENT_DATE,
             'hardware': {'class': 'github-hosted-runner', 'cpu_model': 'fixture', 'cores': 4, 'threads': 4,
                          'vcpus': 4, 'memory_gib': 16, 'architecture': 'x64',
                          'os_family': 'Ubuntu 24.04', 'kernel_major': 6},
             'toolchains': {'rust': 'nightly-2026-08-27', 'codegen_backend': 'Cranelift',
                            'linker': 'mold 2.41.0', 'verus': '0.2026.09.06.8dea4a2 with Z3 4.16.0',
                            'kani': '0.67.0'},
             'workloads': [{'id': 'w', 'description': 'Fixture.', 'command': 'true',
                                              'metric': 'wall time', 'unit': 's', 'samples': [1], 'median': 1}]}
    if purpose == 'acceptance':
        entry['outcome'] = outcome
        entry['runner_image'] = 'ubuntu-24.04'
        entry['runner_metadata'] = {'image_os': 'ubuntu24', 'image_version': '20261012.1'}
    RECORD_VALIDATOR.validate(entry)
    return entry


def ci_record(outcome: str, conclusions: list[tuple[str, float]]) -> dict:
    """Build an AC-07 record in newest-first order with timestamped job attempts."""
    entry = record(outcome)
    entry['control_ids'] = [CI_CONTROL['id']]
    entry['recorded_on'] = CI_MEASUREMENT_DATE
    workload = entry['workloads'][0]
    workload['id'] = 'ci-build-test'
    attempts = []
    newest_start = datetime(2026, 10, 12, 12, tzinfo=UTC)
    for index, (conclusion, seconds) in enumerate(conclusions):
        start = newest_start - timedelta(minutes=index)
        finish = start + timedelta(seconds=seconds)
        attempts.append({'run_id': str(index + 1), 'run_number': index + 1, 'attempt': 1,
                         'conclusion': conclusion, 'wall_seconds': seconds,
                         'started_at': start.isoformat().replace('+00:00', 'Z'),
                         'completed_at': finish.isoformat().replace('+00:00', 'Z'),
                         'url': f'https://github.com/leynos/combobulate/actions/runs/{index + 1}'})
    workload['attempts'] = attempts
    workload['samples'] = [attempt['wall_seconds'] for attempt in attempts]
    RECORD_VALIDATOR.validate(entry)
    return entry


class Registration(unittest.TestCase):
    """VO-11: acceptance controls are typed, complete, and bind their measurement records."""

    def test_committed_register_passes(self):
        """Validate every registered control in the committed register."""
        # Home-path checks catch user names; a generic CI account name is ordinary text.
        check_acceptance_controls(ValidationContext(ROOT), (socket.gethostname(),))

    def test_register_lists_the_frozen_fields(self):
        """Require the register to name the fields every control must define."""
        self.assertEqual(REGISTER['frozen_fields'], list(FROZEN_FIELDS), 'the register must state its frozen fields')

    def test_register_frozen_fields_match_the_implementation(self):
        """Keep the declared field list aligned with the executable list."""
        check_registration_declarations(REGISTER)
        candidate = copy.deepcopy(REGISTER)
        candidate['frozen_fields'][-1] = 'unchecked-field'
        with self.assertRaisesRegex(AssertionError, 'must match the executable frozen-field list',
                                    msg='the declared fields must match the implementation'):
            check_registration_declarations(candidate)

    def test_missing_calibration_reference_fails(self):
        """Reject a control that omits its required calibration reference."""
        control = copy.deepcopy(CONTROL)
        del control['frozen']['calibration']
        with self.assertRaisesRegex(AssertionError, 'lacks frozen fields: calibration'):
            check_completeness(control)

    def test_an_unregistered_field_fails(self):
        """Reject a control that carries a field the register does not define."""
        control = copy.deepcopy(CONTROL)
        control['frozen']['sponsor_note'] = 'x'
        with self.assertRaisesRegex(AssertionError, 'has unregistered frozen fields: sponsor_note'):
            check_completeness(control)

    def test_register_outcome_map_matches_executable_verdicts(self):
        """Keep schema and runtime outcome mappings consistent."""
        check_registration_declarations(REGISTER)
        altered_maps = (
            dict(OUTCOME_VERDICTS) | {'new-outcome': 'fail'},
            {key: value for key, value in OUTCOME_VERDICTS.items() if key != 'missing'},
            dict(OUTCOME_VERDICTS) | {'resource-exhausted': 'pass'},
        )
        for outcome_map in altered_maps:
            with self.subTest(outcome_map=outcome_map):
                candidate = copy.deepcopy(REGISTER)
                candidate['outcome_verdicts'] = outcome_map
                with self.assertRaisesRegex(AssertionError, 'must match the executable outcome mapping',
                                            msg='runtime semantics must reject a changed outcome map'):
                    check_registration_declarations(candidate)
                with self.assertRaises(ValidationError, msg='the register schema must reject a changed outcome map'):
                    REGISTER_VALIDATOR.validate(candidate)

    def test_protocol_content_is_typed(self):
        """Validate protocol field types against the register schema."""
        for field, value in (('seeds', None), ('registered_on', 'not-a-date'), ('decision_rule', 'bad threshold')):
            with self.subTest(field=field):
                control = copy.deepcopy(CONTROL)
                if field == 'decision_rule':
                    control['frozen'][field]['thresholds']['budget'] = value
                else:
                    control['frozen'][field] = value
                candidate = copy.deepcopy(REGISTER)
                candidate['controls'] = [control if item['id'] == control['id'] else item
                                          for item in REGISTER['controls']]
                with self.assertRaises(ValidationError, msg=f'{field} must fail schema validation'):
                    REGISTER_VALIDATOR.validate(candidate)

    def test_the_register_carries_no_digest_or_approval_machinery(self):
        """Reject the retired digest, amendment and source-hash fields."""
        for field in ('digest', 'registered_digest', 'amendments'):
            with self.subTest(field=field):
                candidate = copy.deepcopy(REGISTER)
                candidate['controls'][0][field] = 'x'
                with self.assertRaises(ValidationError, msg=f'{field} is no longer part of a control'):
                    REGISTER_VALIDATOR.validate(candidate)

    def test_a_measurement_binds_to_a_control_after_its_registration(self):
        """Accept a record for the control, measured after the control was registered."""
        check_measurement_binding(CONTROL, record('pass'))

    def test_a_measurement_before_registration_is_rejected(self):
        """Reject a record dated before the control's registration."""
        early = record('pass')
        early['recorded_on'] = (date.fromisoformat(CONTROL['frozen']['registered_on']) - timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(AssertionError, 'predates registration'):
            check_measurement_binding(CONTROL, early)

    def test_a_measurement_for_another_control_is_rejected(self):
        """Reject a record that does not name the control it is bound to."""
        other = record('pass')
        other['control_ids'] = [CI_CONTROL['id']]
        with self.assertRaisesRegex(AssertionError, 'is not acceptance evidence for'):
            check_measurement_binding(CONTROL, other)


if __name__ == '__main__':
    unittest.main()
