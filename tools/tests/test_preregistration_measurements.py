"""Validate measurement outcomes, CI bindings, tool versions, and host identity."""
from __future__ import annotations

import copy
import itertools
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.ci_controls import AcceptanceWorkflowSettings
from docs_validation.context import ValidationContext
from docs_validation.preregistration import (
    OUTCOME_VERDICTS, check_acceptance_workflow, check_calibration_record, check_ci_calibration,
    check_ci_measurement, check_control_bindings, check_host_identity, check_measurement_binding,
    check_sources, verdict,
)
from test_preregistration import (
    CI_CONTROL, CONTROL, RECORD_OUTCOMES, RECORD_VALIDATOR, REGISTER, ROOT, amended, ci_record, record,
)


class Outcomes(unittest.TestCase):
    """VO-12: retries count, and only current-digest records decide the current verdict."""

    def test_failure_like_outcomes_have_exact_verdicts(self):
        expected_verdicts = {
            'budget-exceeded': 'fail',
            'resource-exhausted': 'fail',
            'missing': 'fail',
            'inconclusive': 'inconclusive',
        }
        for outcome, expected_verdict in expected_verdicts.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(
                    OUTCOME_VERDICTS[outcome],
                    expected_verdict,
                    f'{outcome} must map to {expected_verdict}',
                )

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
        historical['recorded_on'] = control['amendments'][-2]['date']
        self.assertFalse(check_measurement_binding(control, historical),
                         'known earlier digests remain valid historical bindings')
        self.assertEqual(verdict(control, [historical]), 'not-run',
                         'a historical result cannot satisfy the amended current digest')

    def test_historical_digest_is_rejected_on_or_after_its_supersession_date(self):
        control = amended(CONTROL, 'seeds', [7])
        superseded_on = control['amendments'][-1]['date']
        recorded_dates = (
            superseded_on,
            (datetime.fromisoformat(superseded_on) + timedelta(days=1)).date().isoformat(),
        )

        for recorded_on in recorded_dates:
            with self.subTest(recorded_on=recorded_on):
                historical = record('pass', digest=CONTROL['digest'])
                historical['recorded_on'] = recorded_on
                with self.assertRaisesRegex(AssertionError, 'superseded'):
                    check_measurement_binding(control, historical)

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

    def test_acceptance_runner_profile_must_match_registration(self):
        for field, value in (('threads', 1), ('vcpus', 1), ('memory_gib', 1), ('architecture', 'arm64')):
            with self.subTest(field=field):
                wrong_profile = record('pass')
                wrong_profile['hardware'][field] = value
                with self.assertRaises(ValidationError,
                                       msg=f'acceptance schema must reject an incorrect {field}'):
                    RECORD_VALIDATOR.validate(wrong_profile)
                with self.assertRaisesRegex(AssertionError, 'registered 4-vCPU'):
                    check_measurement_binding(CONTROL, wrong_profile)

        missing_vcpu_count = record('pass')
        del missing_vcpu_count['hardware']['vcpus']
        with self.assertRaises(ValidationError,
                               msg='acceptance schema must require the registered virtual CPU count'):
            RECORD_VALIDATOR.validate(missing_vcpu_count)

    def test_acceptance_runner_metadata_and_toolchain_versions_are_required(self):
        missing_metadata = record('pass')
        del missing_metadata['runner_metadata']
        with self.assertRaises(ValidationError, msg='acceptance records require observed runner metadata'):
            RECORD_VALIDATOR.validate(missing_metadata)
        with self.assertRaisesRegex(AssertionError, 'lacks observed GitHub ImageOS'):
            check_measurement_binding(CONTROL, missing_metadata)

        missing_toolchain = record('pass')
        missing_toolchain['toolchains'] = {}
        with self.assertRaisesRegex(AssertionError, 'lacks measured versions for registered toolchains'):
            check_measurement_binding(CONTROL, missing_toolchain)

        wrong_version = record('pass')
        wrong_version['toolchains']['kani'] = '0.68.0'
        with self.assertRaisesRegex(AssertionError, 'does not report frozen toolchain versions'):
            check_measurement_binding(CONTROL, wrong_version)

        embedded_wrong_version = record('pass')
        embedded_wrong_version['toolchains']['kani'] = '10.67.0'
        with self.assertRaisesRegex(AssertionError, 'kani 0.67.0',
                                    msg='a larger version must not satisfy a pinned Kani version'):
            check_measurement_binding(CONTROL, embedded_wrong_version)

        misplaced_secondary_version = record('pass')
        misplaced_secondary_version['toolchains']['kani'] += ' with Z3 4.16.0'
        misplaced_secondary_version['toolchains']['verus'] = '0.2026.09.06.8dea4a2 with Z3 4.17.0'
        with self.assertRaisesRegex(AssertionError, 'verus 4.16.0',
                                    msg='a secondary version must belong to its registered tool'):
            check_measurement_binding(CONTROL, misplaced_secondary_version)

    def test_analysis_script_must_be_a_hashed_workload_source(self):
        control = copy.deepcopy(CONTROL)
        control['frozen']['analysis_script'] = {
            'path': 'tools/analyse.py', 'requirement': 'Use the registered analysis.',
        }
        control['frozen']['workload']['sources'] = []
        with self.assertRaisesRegex(AssertionError, 'analysis script .* has no matching hashed workload source',
                                    msg='analysis script bytes must be frozen with a source digest'):
            check_sources(control, {})

        script_digest = 'a' * 64
        control['frozen']['workload']['sources'] = [{'path': 'tools/analyse.py', 'sha256': script_digest}]
        check_sources(control, {'tools/analyse.py': script_digest})

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
