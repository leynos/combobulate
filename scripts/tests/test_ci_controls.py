"""Exercise AC-07 attempt windows against an independent nearest-rank oracle."""
from __future__ import annotations

import math
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import given, settings, strategies as st

from docs_validation.ci_controls import check_ci_measurement
from docs_validation.context import ValidationContext

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ValidationContext(ROOT).load('spec/acceptance-controls.json')
CI_CONTROL = next(control for control in REGISTER['controls'] if control['id'] == 'AC-07')
P90_BUDGET_SECONDS = CI_CONTROL['frozen']['decision_rule']['thresholds']['p90_minutes'] * 60
# The three jobs the workflow declares unconditionally; the completeness rule
# compares every attempt's per-job map with this set.
REQUIRED_JOBS = frozenset({'build-test', 'polars-lint', 'polars-test'})


def measurement(
    outcome: str, durations: list[float], failed_at: int | None = None,
    incomplete_at: int | None = None,
) -> dict:
    """Build a newest-first CI window; e.g. twenty completed attempts bind p90 samples.

    Every attempt records a conclusion for each job in :data:`REQUIRED_JOBS`, all
    successful unless that attempt is the timed-out one, so the completeness rule
    and the outcome rule agree about what the window says. ``failed_at`` and
    ``incomplete_at`` mark a run whose longest job is the one that failed.
    """
    newest_start = datetime(2026, 10, 12, 12, tzinfo=UTC)
    attempts = []
    samples = []
    for index, duration in enumerate(durations):
        start = newest_start - timedelta(minutes=index)
        finish = start + timedelta(seconds=duration)
        is_incomplete = index == incomplete_at
        conclusion = 'timed_out' if index == failed_at else 'success'
        attempts.append({
            'run_id': str(index + 1),
            'attempt': 1,
            'conclusion': conclusion,
            'required_job_conclusions': {
                job: 'timed_out' if index == failed_at and job == 'build-test' else 'success'
                for job in REQUIRED_JOBS
            },
            'wall_seconds': None if is_incomplete else duration,
            'started_at': start.isoformat().replace('+00:00', 'Z'),
            'completed_at': None if is_incomplete else finish.isoformat().replace('+00:00', 'Z'),
        })
        if not is_incomplete:
            samples.append(duration)
    return {
        'id': 'AC-07-fixture',
        'outcome': outcome,
        'workloads': [{
            'id': 'ci-required-jobs',
            'samples': samples,
            'attempts': attempts,
        }],
    }


@st.composite
def generated_windows(draw: st.DrawFn) -> tuple[list[float], int | None, int | None, int | None, list[int]]:
    """Generate attempt windows and malformed variants; e.g. a duplicate retry ID."""
    durations = draw(st.lists(st.integers(min_value=0, max_value=600_000).map(lambda value: value / 1000),
                              min_size=0, max_size=20))
    last_index = len(durations) - 1
    failed_at = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=last_index))) if durations else None
    incomplete_at = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=last_index))) if durations else None
    duplicate_at = (draw(st.one_of(st.none(), st.integers(min_value=1, max_value=last_index)))
                    if len(durations) > 1 else None)
    order = draw(st.permutations(tuple(range(len(durations)))))
    return durations, failed_at, incomplete_at, duplicate_at, order


class CiMeasurement(unittest.TestCase):
    """Check AC-07 attempt accounting, incomplete windows, and nearest-rank p90."""

    def test_twenty_successes_pass_at_the_p90_budget_boundary(self) -> None:
        """Use rank 18 of 20 and accept an exact eight-minute p90."""
        record = measurement('pass', [420.0] * 17 + [P90_BUDGET_SECONDS] * 3)
        check_ci_measurement(CI_CONTROL, record, REQUIRED_JOBS)

    def test_twenty_successes_over_budget_must_fail(self) -> None:
        """Reject a passing label when rank 18 exceeds the registered threshold."""
        durations = [420.0] * 17 + [P90_BUDGET_SECONDS + 1] * 3
        with self.assertRaisesRegex(AssertionError, 'p90 exceeds its budget',
                                    msg='an over-budget successful window must fail AC-07'):
            check_ci_measurement(CI_CONTROL, measurement('pass', durations), REQUIRED_JOBS)
        check_ci_measurement(CI_CONTROL, measurement('fail', durations), REQUIRED_JOBS)

    def test_nineteen_successes_are_inconclusive(self) -> None:
        """Require the full registered window before reporting a successful p90."""
        durations = [60.0] * 19
        check_ci_measurement(CI_CONTROL, measurement('inconclusive', durations), REQUIRED_JOBS)
        with self.assertRaisesRegex(AssertionError, 'needs 20 required-job attempts',
                                    msg='a short successful window cannot pass AC-07'):
            check_ci_measurement(CI_CONTROL, measurement('pass', durations), REQUIRED_JOBS)

    def test_a_failed_non_longest_job_fails_the_attempt(self) -> None:
        """Fail the record when any required job other than the longest did not succeed.

        The per-attempt ``conclusion`` describes the run's longest required job,
        which is the run's duration sample. AC-07 requires every required job to
        succeed, so a shorter job's failure is invisible in that one field:
        ``build-test`` succeeded, ``polars-lint`` failed, and the record would
        otherwise pass on the strength of the longest job alone.
        """
        record = measurement('pass', [60.0] * 20)
        record['workloads'][0]['attempts'][0]['required_job_conclusions']['polars-lint'] = 'failure'
        with self.assertRaisesRegex(AssertionError, 'any required job in an attempt',
                                    msg='a failed shorter required job must fail AC-07'):
            check_ci_measurement(CI_CONTROL, record, REQUIRED_JOBS)
        record['outcome'] = 'fail'
        check_ci_measurement(CI_CONTROL, record, REQUIRED_JOBS)

    def test_an_omitted_required_job_is_rejected(self) -> None:
        """Refuse a per-job map that leaves a required job out of every attempt.

        The schema requires the map to be non-empty, not complete, so a map
        naming only ``build-test`` validates. The outcome rule then reads just
        the conclusions written there, and a ``polars-lint`` failure that the
        record simply does not mention would pass AC-07. Comparing the map with
        the workflow's required set rejects the omission itself, which is the
        only place the absence of evidence can be told apart from success.
        """
        record = measurement('pass', [60.0] * 20)
        for attempt in record['workloads'][0]['attempts']:
            del attempt['required_job_conclusions']['polars-lint']
        with self.assertRaisesRegex(AssertionError, "missing \\['polars-lint'\\]",
                                    msg='a per-job map must name every required job'):
            check_ci_measurement(CI_CONTROL, record, REQUIRED_JOBS)

    def test_an_undeclared_job_is_rejected(self) -> None:
        """Refuse a per-job map naming a job the workflow does not declare.

        An extra key is the mirror of an omission: it would let a record claim a
        required job exists when the workflow changed, and the runner and
        timeout checks would not see it because they read only declared jobs.
        """
        record = measurement('pass', [60.0] * 20)
        for attempt in record['workloads'][0]['attempts']:
            attempt['required_job_conclusions']['a-removed-job'] = 'success'
        with self.assertRaisesRegex(AssertionError, "unexpected \\['a-removed-job'\\]",
                                    msg='a per-job map must name only the declared jobs'):
            check_ci_measurement(CI_CONTROL, record, REQUIRED_JOBS)

    def test_duplicate_attempt_ids_are_rejected(self) -> None:
        """Do not count a repeated workflow attempt twice in the latest window."""
        record = measurement('pass', [60.0] * 20)
        record['workloads'][0]['attempts'][1]['run_id'] = '1'
        with self.assertRaisesRegex(AssertionError, 'repeats a required-job attempt',
                                    msg='attempt identifiers must be unique'):
            check_ci_measurement(CI_CONTROL, record, REQUIRED_JOBS)

    def test_attempts_must_remain_newest_first(self) -> None:
        """Reject reordered attempts even when their sample values are reordered too."""
        record = measurement('pass', [float(value) for value in range(1, 21)])
        record['workloads'][0]['attempts'].reverse()
        record['workloads'][0]['samples'].reverse()
        with self.assertRaisesRegex(AssertionError, 'not newest first',
                                    msg='attempt order is part of the registered window'):
            check_ci_measurement(CI_CONTROL, record, REQUIRED_JOBS)

    def test_samples_and_timestamps_must_match_attempts(self) -> None:
        """Bind the reported sample vector and duration to each attempt."""
        wrong_samples = measurement('pass', [60.0] * 20)
        wrong_samples['workloads'][0]['samples'][0] += 1
        with self.assertRaisesRegex(AssertionError, 'samples must retain every',
                                    msg='samples must exactly retain attempt durations'):
            check_ci_measurement(CI_CONTROL, wrong_samples, REQUIRED_JOBS)

        wrong_duration = measurement('pass', [60.0] * 20)
        wrong_duration['workloads'][0]['attempts'][0]['wall_seconds'] += 1
        wrong_duration['workloads'][0]['samples'][0] += 1
        with self.assertRaisesRegex(AssertionError, 'duration does not match its timestamps',
                                    msg='attempt duration must match its recorded timestamps'):
            check_ci_measurement(CI_CONTROL, wrong_duration, REQUIRED_JOBS)

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(window=generated_windows())
    def test_generated_windows_follow_independent_outcome_oracle(
        self, window: tuple[list[float], int | None, int | None, int | None, list[int]],
    ) -> None:
        """Check outcome, incomplete timing, duplicate IDs, and ordering against an oracle."""
        durations, failed_index, incomplete_index, duplicate_index, order = window
        if failed_index is not None or incomplete_index is not None:
            expected = 'fail'
        elif len(durations) < 20:
            expected = 'inconclusive'
        else:
            p90 = sorted(durations)[math.ceil(0.9 * len(durations)) - 1]
            expected = 'pass' if p90 <= P90_BUDGET_SECONDS else 'fail'

        check_ci_measurement(CI_CONTROL, measurement(expected, durations, failed_index, incomplete_index), REQUIRED_JOBS)
        incorrect = 'pass' if expected != 'pass' else 'fail'
        with self.assertRaises(AssertionError,
                               msg=f'AC-07 must reject outcome {incorrect!r} for generated window'):
            check_ci_measurement(CI_CONTROL, measurement(incorrect, durations, failed_index, incomplete_index), REQUIRED_JOBS)

        if duplicate_index is not None:
            duplicate_record = measurement(expected, durations, failed_index, incomplete_index)
            attempts = duplicate_record['workloads'][0]['attempts']
            attempts[duplicate_index]['run_id'] = attempts[duplicate_index - 1]['run_id']
            with self.assertRaisesRegex(AssertionError, 'repeats a required-job attempt',
                                        msg='generated duplicate attempt IDs must be rejected'):
                check_ci_measurement(CI_CONTROL, duplicate_record, REQUIRED_JOBS)

        if order != list(range(len(durations))):
            reordered_record = measurement(expected, durations, failed_index, incomplete_index)
            attempts = reordered_record['workloads'][0]['attempts']
            reordered_record['workloads'][0]['attempts'] = [attempts[index] for index in order]
            with self.assertRaisesRegex(AssertionError, 'not newest first',
                                        msg='generated attempt permutations must preserve newest-first order'):
                check_ci_measurement(CI_CONTROL, reordered_record, REQUIRED_JOBS)


if __name__ == '__main__':
    unittest.main()
