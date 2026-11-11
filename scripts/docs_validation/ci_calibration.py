"""Validate AC-07's pre-DL-14 calibration history and its recorded p90.

The calibration series is the single `ci-build-test` workload measured before
DL-14 widened AC-07 to every required pull-request job. It is deliberately not
the acceptance workload: it fixes the registered threshold, so it is checked
for the shape it actually had (one timed job per attempt) rather than for the
per-job conclusion map a current acceptance record must carry.

This module is split from `ci_controls.py` so each module states one contract.
`ci_controls` owns what a current record must say; this one owns the sample
window the threshold was derived from. It depends on `ci_controls` for the
shared nearest-rank definition, never the reverse.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from math import isclose
from statistics import median

from .ci_controls import nearest_rank
from .context import require


def check_ci_calibration(control: Mapping[str, object], records: Mapping[str, dict]) -> None:
    """Validate the AC-07 calibration history and its recorded p90 derivation.

    Parameters
    ----------
    control : Mapping[str, object]
        Registered AC-07 control containing calibration metadata and thresholds.
    records : Mapping[str, dict]
        Calibration records indexed by repository-relative path.

    Returns
    -------
    None
        Returns when the calibration is not required or all retained samples agree.

    Raises
    ------
    AssertionError
        If a required record, attempt window, median, timestamp, or p90 is inconsistent.
    KeyError
        If a required control, record, or workload field is absent.
    ValueError
        If a retained attempt timestamp is malformed.

    Examples
    --------
    check_ci_calibration(control, records) accepts a history whose p90 matches its samples.
    """
    calibration = control['frozen']['calibration']
    if calibration['status'] != 'calibrated':
        return
    record = records.get(calibration['record'])
    require(record is not None, f"{control['id']} cites missing calibration record {calibration['record']}")
    workloads = {workload['id']: workload for workload in record['workloads']}
    build_test = _required_ci_calibration_workload(workloads, 'ci-build-test', calibration['record'])
    design_check = _required_ci_calibration_workload(workloads, 'design-check', calibration['record'])
    build_durations = _validate_ci_calibration_workload(build_test, 'ci-build-test', calibration['record'])
    _validate_ci_calibration_workload(design_check, 'design-check', calibration['record'])
    _check_ci_calibration_timestamps(build_test['attempts'], calibration['record'])
    _check_ci_calibration_p90(control, calibration, build_durations)


def _required_ci_calibration_workload(
    workloads: Mapping[str, Mapping[str, object]], workload_id: str, record_id: str,
) -> Mapping[str, object]:
    """Select one calibration history; for example, reject a missing job history."""
    workload = workloads.get(workload_id)
    require(workload is not None, f"{record_id} lacks {workload_id} history")
    return workload


def _validate_ci_calibration_workload(
    workload: Mapping[str, object], workload_id: str, record_id: str,
) -> list[float]:
    """Validate a 20-attempt sample window; for example, reject a missing duration."""
    attempts = workload.get('attempts', [])
    require(len(attempts) == 20, f"{record_id} must retain 20 {workload_id} attempts")
    attempt_ids = [(attempt['run_id'], attempt['attempt']) for attempt in attempts]
    require(len(attempt_ids) == len(set(attempt_ids)), f"{record_id} repeats a {workload_id} attempt")
    starts = [attempt['started_at'] for attempt in attempts]
    require(all(start is not None for start in starts),
            f"{record_id} must retain start times for every {workload_id} attempt")
    require(starts == sorted(starts, reverse=True),
            f"{record_id} {workload_id} attempts are not newest first")
    durations = [attempt['wall_seconds'] for attempt in attempts if attempt['wall_seconds'] is not None]
    require(bool(durations), f"{record_id} has no timed {workload_id} attempts")
    require(workload['samples'] == durations,
            f"{record_id} samples must include every timed {workload_id} attempt")
    require(len(durations) == len(attempts), f"{record_id} must time every {workload_id} attempt")
    require(workload['median'] == median(durations),
            f"{record_id} median does not match its {workload_id} attempts")
    return durations


def _check_ci_calibration_timestamps(attempts: list[Mapping[str, object]], record_id: str) -> None:
    """Bind build durations to timestamps; for example, reject edited wall times."""
    for attempt in attempts:
        require(attempt['completed_at'] is not None,
                f"{record_id} must retain completion times for every ci-build-test attempt")
        elapsed = (datetime.fromisoformat(attempt['completed_at'].replace('Z', '+00:00'))
                   - datetime.fromisoformat(attempt['started_at'].replace('Z', '+00:00'))).total_seconds()
        require(isclose(attempt['wall_seconds'], elapsed, abs_tol=0.001),
                f"{record_id} ci-build-test duration does not match its timestamps")


def _check_ci_calibration_p90(
    control: Mapping[str, object], calibration: Mapping[str, object], durations: list[float],
) -> None:
    """Bind AC-07's percentile to its samples; for example, reject a stale derivation."""
    p90_seconds = nearest_rank(durations, 0.9)
    p90_budget = control['frozen']['decision_rule']['thresholds']['p90_minutes'] * 60
    require(p90_seconds <= p90_budget,
            f"{control['id']} calibration p90 {p90_seconds} s exceeds its {p90_budget} s budget")
    match = re.search(
        r'nearest-rank p90 ([0-9.]+) s', calibration['derivation'], re.IGNORECASE)
    require(match is not None and float(match[1]) == p90_seconds,
            f"{control['id']} calibration derivation does not match its recorded attempt p90")
