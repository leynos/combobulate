"""Prove pre-registration freezes every field and outcomes cannot be relabelled (VO-11, VO-12, VO-16)."""
from __future__ import annotations

import copy
import itertools
import socket
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import given, settings, strategies as st
from jsonschema import Draft202012Validator, ValidationError

from docs_validation.ci_controls import AcceptanceWorkflowSettings
from docs_validation.context import ValidationContext
from docs_validation.preregistration import (
    FROZEN_FIELDS, OUTCOME_VERDICTS, check_acceptance_controls, check_acceptance_workflow,
    check_amendment_chain, check_calibration_record, check_ci_calibration, check_ci_measurement, check_completeness,
    check_control_bindings, check_host_identity, check_measurement_binding, check_registration_declarations,
    check_sources, frozen_digest, verdict,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ValidationContext(ROOT).load('spec/acceptance-controls.json')
CONTROL = REGISTER['controls'][0]
CI_CONTROL = next(item for item in REGISTER['controls'] if item['id'] == 'AC-07')
SPONSOR = 'leynos'
REGISTER_VALIDATOR = Draft202012Validator(
    ValidationContext(ROOT).load('spec/acceptance-controls.schema.json'),
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)
RECORD_VALIDATOR = Draft202012Validator(
    ValidationContext(ROOT).load('spec/measurement-record.schema.json'),
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)
RECORD_OUTCOMES = sorted(OUTCOME_VERDICTS)
LATEST_CONTROL_AMENDMENT_DATE = CONTROL['amendments'][-1]['date']
TEST_MEASUREMENT_DATE = (date.fromisoformat(LATEST_CONTROL_AMENDMENT_DATE) + timedelta(days=1)).isoformat()


def amended(control: dict, field: str, value: object) -> dict:
    """Return a copy with one frozen field changed through an approved amendment."""
    edited = copy.deepcopy(control)
    edited['frozen'][field] = value
    new_digest = frozen_digest(edited)
    previous_date = edited['amendments'][-1]['date'] if edited['amendments'] else edited['frozen']['registered_on']
    amendment_date = (date.fromisoformat(previous_date) + timedelta(days=1)).isoformat()
    edited['amendments'].append({'date': amendment_date, 'approved_by': SPONSOR,
                                 'approval_reference': 'https://example.org/approval',
                                 'replaces': edited['digest'], 'new_digest': new_digest, 'reason': 'Test.'})
    edited['digest'] = new_digest
    return edited


def record(outcome: str, purpose: str = 'acceptance', digest: str | None = None) -> dict:
    """Build one schema-valid measurement record for the first control."""
    entry = {'id': 'fixture', 'purpose': purpose, 'control_ids': [CONTROL['id']],
             'control_digest': None if purpose == 'calibration' else (digest or CONTROL['digest']),
             'recorded_on': TEST_MEASUREMENT_DATE,
             'hardware': {'class': 'github-hosted-runner', 'cpu_model': 'fixture', 'cores': 4, 'threads': 4,
                          'memory_gib': 16, 'os_family': 'Ubuntu 24.04', 'kernel_major': 6},
             'toolchains': {}, 'workloads': [{'id': 'w', 'description': 'Fixture.', 'command': 'true',
                                              'metric': 'wall time', 'unit': 's', 'samples': [1], 'median': 1}]}
    if purpose == 'acceptance':
        entry['outcome'] = outcome
        entry['runner_image'] = 'ubuntu-24.04'
    RECORD_VALIDATOR.validate(entry)
    return entry


def ci_record(outcome: str, conclusions: list[tuple[str, float]]) -> dict:
    """Build an AC-07 record in newest-first order with timestamped job attempts."""
    entry = record(outcome, digest=CI_CONTROL['digest'])
    entry['control_ids'] = [CI_CONTROL['id']]
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
    """VO-11: frozen protocols are typed, digested, and governed by an approved chain."""

    def test_committed_register_passes(self):
        # Home-path checks catch user names; a generic CI account name is ordinary text.
        check_acceptance_controls(ValidationContext(ROOT), (socket.gethostname(),))

    def test_register_lists_the_frozen_fields(self):
        self.assertEqual(REGISTER['frozen_fields'], list(FROZEN_FIELDS), 'the register must state its frozen fields')

    def test_register_frozen_fields_match_digest_implementation(self):
        check_registration_declarations(REGISTER)
        candidate = copy.deepcopy(REGISTER)
        candidate['frozen_fields'][-1] = 'unhashed-field'
        with self.assertRaisesRegex(AssertionError, 'must match the executable digest fields',
                                    msg='the declared frozen fields must match the digest implementation'):
            check_registration_declarations(candidate)

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

    def test_amendment_before_first_measurement_remains_authorized(self):
        control = amended(CONTROL, 'seeds', [7])
        measurement = record('pass', digest=control['digest'])
        measurement['recorded_on'] = (
            date.fromisoformat(control['amendments'][-1]['date']) + timedelta(days=1)
        ).isoformat()
        check_amendment_chain(control, SPONSOR, [measurement])
        self.assertTrue(check_measurement_binding(control, measurement),
                        'a measurement after an approved amendment binds the amended digest')

    def test_amendment_cannot_backdate_measurement_authority(self):
        control = amended(CONTROL, 'seeds', [7])
        control['amendments'][0]['date'] = '2026-10-10'
        between_registration_and_record = record('pass', digest=control['digest'])
        between_registration_and_record['recorded_on'] = '2026-10-11'
        with self.assertRaisesRegex(AssertionError, 'amendment date cannot predate its previous effective date'):
            check_amendment_chain(control, SPONSOR, [between_registration_and_record])

    def test_amendment_date_must_follow_the_previous_amendment(self):
        control = amended(amended(CONTROL, 'seeds', [7]), 'seeds', [8])
        control['amendments'][-1]['date'] = '2026-10-11'
        with self.assertRaisesRegex(AssertionError, 'amendment date cannot predate its previous effective date'):
            check_amendment_chain(control, SPONSOR)

    def test_register_outcome_map_matches_executable_verdicts(self):
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

    def test_amendment_needs_the_sponsor(self):
        control = amended(CONTROL, 'seeds', [7])
        control['amendments'][-1]['approved_by'] = 'someone-else'
        with self.assertRaisesRegex(AssertionError, 'not approved by the sponsor'):
            check_amendment_chain(control, SPONSOR)

    def test_amendment_on_measurement_date_requires_a_new_control_identifier(self):
        control = amended(CONTROL, 'seeds', [7])
        with self.assertRaisesRegex(AssertionError, 'must predate the earliest acceptance measurement'):
            check_amendment_chain(control, SPONSOR, [record('pass')])

    def test_protocol_content_is_typed_after_digest_recalculation(self):
        for field, value in (('seeds', None), ('registered_on', 'not-a-date'), ('decision_rule', 'bad threshold')):
            with self.subTest(field=field):
                control = copy.deepcopy(CONTROL)
                if field == 'decision_rule':
                    control['frozen'][field]['thresholds']['budget'] = value
                else:
                    control['frozen'][field] = value
                digest = frozen_digest(control)
                control['registered_digest'] = digest
                control['digest'] = digest
                candidate = copy.deepcopy(REGISTER)
                candidate['controls'] = [control if item['id'] == control['id'] else item
                                          for item in REGISTER['controls']]
                with self.assertRaises(ValidationError,
                                       msg=f'{field} must fail schema validation with a recomputed digest'):
                    REGISTER_VALIDATOR.validate(candidate)

    def test_changed_source_needs_an_amendment(self):
        control = copy.deepcopy(CI_CONTROL)
        sources = {source['path']: source['sha256'] for source in control['frozen']['workload']['sources']}
        check_sources(control, sources)
        sources['.github/workflows/ci.yml'] = '0' * 64
        with self.assertRaisesRegex(AssertionError, 'AC-07 source .github/workflows/ci.yml changed since registration',
                                    msg='changed source bytes must require a registered amendment'):
            check_sources(control, sources)
        with self.assertRaisesRegex(AssertionError, 'AC-07 source .github/workflows/ci.yml is missing',
                                    msg='every registered source must be supplied to the pure rule'):
            check_sources(control, {})

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


class Outcomes(unittest.TestCase):
    """VO-12: retries count, and only current-digest records decide the current verdict."""

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

    def test_unknown_digest_is_rejected_before_aggregation(self):
        with self.assertRaisesRegex(AssertionError, 'cites unknown digest'):
            verdict(CONTROL, [record('pass', digest='0' * 64)])

    def test_unknown_control_id_is_rejected(self):
        unknown = record('pass')
        unknown['control_ids'] = ['AC-99']
        controls = {item['id']: item for item in REGISTER['controls']}
        with self.assertRaisesRegex(AssertionError, 'cites unknown control AC-99'):
            check_control_bindings(controls, unknown)

    def test_historical_digest_is_valid_but_does_not_count_for_current_digest(self):
        control = amended(CONTROL, 'seeds', [7])
        historical = record('pass', digest=CONTROL['digest'])
        self.assertFalse(check_measurement_binding(control, historical),
                         'known earlier digests remain valid historical bindings')
        self.assertEqual(verdict(control, [historical]), 'not-run',
                         'a historical result cannot satisfy the amended current digest')

    def test_record_before_registration_is_rejected(self):
        earlier = record('pass')
        earlier['recorded_on'] = '2026-10-10'
        with self.assertRaisesRegex(AssertionError, 'predates registration'):
            check_measurement_binding(CONTROL, earlier)

    def test_shared_development_host_cannot_supply_acceptance_evidence(self):
        shared_host = record('pass')
        shared_host['hardware']['class'] = 'shared-development-host'
        with self.assertRaises(ValidationError, msg='acceptance records must use the hosted runner class'):
            RECORD_VALIDATOR.validate(shared_host)
        with self.assertRaisesRegex(AssertionError, 'not measured on the registered'):
            check_measurement_binding(CONTROL, shared_host)

    def test_acceptance_runner_image_must_match_registration(self):
        wrong_image = record('pass')
        wrong_image['runner_image'] = 'ubuntu-latest'
        with self.assertRaises(ValidationError, msg='schema must reject an unpinned acceptance image'):
            RECORD_VALIDATOR.validate(wrong_image)
        with self.assertRaisesRegex(AssertionError, 'does not use AC-01'):
            check_measurement_binding(CONTROL, wrong_image)

    def test_calibration_directory_rejects_acceptance_record_directly(self):
        with self.assertRaisesRegex(AssertionError, 'acceptance evidence belongs in spec/measurements'):
            check_calibration_record('spec/calibration/fixture.json', record('pass'))

    def test_seeded_mapping_fault_is_detected(self):
        faulty = dict(OUTCOME_VERDICTS, **{'resource-exhausted': 'pass'})
        outcomes = [faulty[name] for name in ('pass', 'resource-exhausted')]
        self.assertEqual(set(outcomes), {'pass'}, 'the seeded fault would pass an exhausted run')
        self.assertEqual(verdict(CONTROL, [record('pass'), record('resource-exhausted')]), 'fail',
                         'the real mapping fails it')


class WorkflowAndCi(unittest.TestCase):
    """Pin the hosted CI control and prevent failures hiding in the p90 tail."""

    def test_workflow_runner_and_timeout_match_ac07(self):
        check_acceptance_workflow(AcceptanceWorkflowSettings('ubuntu-24.04', 8), CI_CONTROL)
        with self.assertRaisesRegex(AssertionError, 'runner.*does not match AC-07'):
            check_acceptance_workflow(AcceptanceWorkflowSettings('ubuntu-latest', 8), CI_CONTROL)
        with self.assertRaisesRegex(AssertionError, 'timeout.*does not match AC-07'):
            check_acceptance_workflow(AcceptanceWorkflowSettings('ubuntu-24.04', 9), CI_CONTROL)

    def test_two_timeouts_fail_even_when_fast_successes_keep_p90_low(self):
        attempts = [('success', 1.0)] * 18 + [('timed_out', 480.0)] * 2
        with self.assertRaisesRegex(AssertionError, 'must fail when a build-test attempt fails'):
            check_ci_measurement(CI_CONTROL, ci_record('pass', attempts))
        failed = ci_record('fail', attempts)
        check_ci_measurement(CI_CONTROL, failed)
        self.assertEqual(verdict(CI_CONTROL, [failed]), 'fail',
                         'timeouts fail AC-07 even when nearest-rank p90 is within budget')

    def test_untimed_failed_attempt_is_a_valid_failed_measurement(self):
        failed = record('fail', digest=CI_CONTROL['digest'])
        failed['control_ids'] = [CI_CONTROL['id']]
        workload = failed['workloads'][0]
        workload['id'] = 'ci-build-test'
        workload['samples'] = []
        workload['median'] = 'not available'
        workload['attempts'] = [{
            'run_id': '21',
            'run_number': 21,
            'attempt': 1,
            'conclusion': 'timed_out',
            'wall_seconds': None,
            'started_at': '2026-10-12T12:00:00Z',
            'completed_at': None,
            'url': 'https://github.com/leynos/combobulate/actions/runs/21',
        }]

        RECORD_VALIDATOR.validate(failed)
        check_ci_measurement(CI_CONTROL, failed)
        self.assertEqual(verdict(CI_CONTROL, [failed]), 'fail',
                         'an untimed failed AC-07 attempt must remain a failed measurement')
        passing = copy.deepcopy(failed)
        passing['outcome'] = 'pass'
        with self.assertRaisesRegex(AssertionError, 'must fail when a build-test attempt fails',
                                    msg='an untimed failed attempt must never be recorded as a pass'):
            check_ci_measurement(CI_CONTROL, passing)

    def test_other_controls_still_require_a_sample(self):
        no_samples = record('pass')
        no_samples['workloads'][0]['samples'] = []
        no_samples['workloads'][0]['median'] = 'not available'
        with self.assertRaises(ValidationError, msg='non-AC-07 records still require measured samples'):
            RECORD_VALIDATOR.validate(no_samples)

    def test_calibration_p90_must_fit_registered_budget(self):
        calibration = ValidationContext(ROOT).load('spec/calibration/ci-history.json')
        control = copy.deepcopy(CI_CONTROL)
        workload = next(item for item in calibration['workloads'] if item['id'] == 'ci-build-test')
        workload['samples'] = [500.0] * 20
        workload['median'] = 500.0
        for attempt in workload['attempts']:
            attempt['wall_seconds'] = 500.0
            started_at = datetime.fromisoformat(attempt['started_at'].replace('Z', '+00:00'))
            attempt['completed_at'] = (started_at + timedelta(seconds=500)).isoformat().replace('+00:00', 'Z')
        control['frozen']['calibration']['derivation'] = 'nearest-rank p90 500 s.'
        with self.assertRaisesRegex(AssertionError, 'calibration p90 500.0 s exceeds its 480 s budget'):
            check_ci_calibration(control, {'spec/calibration/ci-history.json': calibration})

    def test_calibration_derivation_must_match_the_recorded_attempt_p90(self):
        calibration = ValidationContext(ROOT).load('spec/calibration/ci-history.json')
        control = copy.deepcopy(CI_CONTROL)
        control['frozen']['calibration']['derivation'] = (
            'Nearest-rank p90 212.0 s of 20 eligible attempts x 2, rounded up to whole minutes.'
        )
        with self.assertRaisesRegex(AssertionError, 'derivation does not match its recorded attempt p90'):
            check_ci_calibration(control, {'spec/calibration/ci-history.json': calibration})


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
