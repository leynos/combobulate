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


def measurement(outcome: str, durations: list[float], failed_at: int | None = None) -> dict:
    """Build a newest-first CI window; e.g. twenty completed attempts bind p90 samples."""
    newest_start = datetime(2026, 10, 12, 12, tzinfo=UTC)
    attempts = []
    for index, duration in enumerate(durations):
        start = newest_start - timedelta(minutes=index)
        finish = start + timedelta(seconds=duration)
        attempts.append({
            'run_id': str(index + 1),
            'attempt': 1,
            'conclusion': 'timed_out' if index == failed_at else 'success',
            'wall_seconds': duration,
            'started_at': start.isoformat().replace('+00:00', 'Z'),
            'completed_at': finish.isoformat().replace('+00:00', 'Z'),
        })
    return {
        'id': 'AC-07-fixture',
        'outcome': outcome,
        'workloads': [{
            'id': 'ci-build-test',
            'samples': list(durations),
            'attempts': attempts,
        }],
    }


class CiMeasurement(unittest.TestCase):
    """Check AC-07 attempt accounting, incomplete windows, and nearest-rank p90."""

    def test_twenty_successes_pass_at_the_p90_budget_boundary(self) -> None:
        """Use rank 18 of 20 and accept an exact eight-minute p90."""
        record = measurement('pass', [420.0] * 17 + [P90_BUDGET_SECONDS] * 3)
        check_ci_measurement(CI_CONTROL, record)

    def test_twenty_successes_over_budget_must_fail(self) -> None:
        """Reject a passing label when rank 18 exceeds the registered threshold."""
        durations = [420.0] * 17 + [P90_BUDGET_SECONDS + 1] * 3
        with self.assertRaisesRegex(AssertionError, 'p90 exceeds its budget',
                                    msg='an over-budget successful window must fail AC-07'):
            check_ci_measurement(CI_CONTROL, measurement('pass', durations))
        check_ci_measurement(CI_CONTROL, measurement('fail', durations))

    def test_nineteen_successes_are_inconclusive(self) -> None:
        """Require the full registered window before reporting a successful p90."""
        durations = [60.0] * 19
        check_ci_measurement(CI_CONTROL, measurement('inconclusive', durations))
        with self.assertRaisesRegex(AssertionError, 'needs 20 build-test attempts',
                                    msg='a short successful window cannot pass AC-07'):
            check_ci_measurement(CI_CONTROL, measurement('pass', durations))

    def test_duplicate_attempt_ids_are_rejected(self) -> None:
        """Do not count a repeated workflow attempt twice in the latest window."""
        record = measurement('pass', [60.0] * 20)
        record['workloads'][0]['attempts'][1]['run_id'] = '1'
        with self.assertRaisesRegex(AssertionError, 'repeats a build-test attempt',
                                    msg='attempt identifiers must be unique'):
            check_ci_measurement(CI_CONTROL, record)

    def test_attempts_must_remain_newest_first(self) -> None:
        """Reject reordered attempts even when their sample values are reordered too."""
        record = measurement('pass', [float(value) for value in range(1, 21)])
        record['workloads'][0]['attempts'].reverse()
        record['workloads'][0]['samples'].reverse()
        with self.assertRaisesRegex(AssertionError, 'not newest first',
                                    msg='attempt order is part of the registered window'):
            check_ci_measurement(CI_CONTROL, record)

    def test_samples_and_timestamps_must_match_attempts(self) -> None:
        """Bind the reported sample vector and duration to each attempt."""
        wrong_samples = measurement('pass', [60.0] * 20)
        wrong_samples['workloads'][0]['samples'][0] += 1
        with self.assertRaisesRegex(AssertionError, 'samples must retain every',
                                    msg='samples must exactly retain attempt durations'):
            check_ci_measurement(CI_CONTROL, wrong_samples)

        wrong_duration = measurement('pass', [60.0] * 20)
        wrong_duration['workloads'][0]['attempts'][0]['wall_seconds'] += 1
        wrong_duration['workloads'][0]['samples'][0] += 1
        with self.assertRaisesRegex(AssertionError, 'duration does not match its timestamps',
                                    msg='attempt duration must match its recorded timestamps'):
            check_ci_measurement(CI_CONTROL, wrong_duration)

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(
        durations=st.lists(st.integers(min_value=0, max_value=600_000).map(lambda value: value / 1000),
                           min_size=0, max_size=20),
        failed_at=st.one_of(st.none(), st.integers(min_value=0, max_value=19)),
    )
    def test_generated_windows_follow_independent_outcome_oracle(
        self, durations: list[float], failed_at: int | None,
    ) -> None:
        """Check windows of zero to twenty attempts against failure and p90 rules."""
        failed_index = failed_at if failed_at is not None and failed_at < len(durations) else None
        if failed_index is not None:
            expected = 'fail'
        elif len(durations) < 20:
            expected = 'inconclusive'
        else:
            p90 = sorted(durations)[math.ceil(0.9 * len(durations)) - 1]
            expected = 'pass' if p90 <= P90_BUDGET_SECONDS else 'fail'

        check_ci_measurement(CI_CONTROL, measurement(expected, durations, failed_index))
        incorrect = 'pass' if expected != 'pass' else 'fail'
        with self.assertRaises(AssertionError,
                               msg=f'AC-07 must reject outcome {incorrect!r} for generated window'):
            check_ci_measurement(CI_CONTROL, measurement(incorrect, durations, failed_index))


if __name__ == '__main__':
    unittest.main()
