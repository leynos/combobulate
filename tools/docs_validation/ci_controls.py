"""Validate AC-07 CI attempt outcomes and their calibration history."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import ceil, isclose
from statistics import median

from .context import require

OUTCOME_VERDICTS = {
    'pass': 'pass', 'fail': 'fail', 'budget-exceeded': 'fail', 'resource-exhausted': 'fail',
    'inconclusive': 'inconclusive', 'missing': 'fail',
}


@dataclass(frozen=True)
class _CiAttemptSummary:
    """Carry one validated AC-07 window; for example, retain timed and incomplete attempts together."""

    attempts: tuple[Mapping[str, object], ...]
    durations: tuple[float, ...]
    has_incomplete_attempt: bool


@dataclass(frozen=True)
class AcceptanceWorkflowSettings:
    """Carry the workflow values used by AC-07; e.g. `ubuntu-24.04` and eight minutes."""

    runner_image: object
    timeout_minutes: object


def check_ci_measurement(control: Mapping[str, object], record: Mapping[str, object]) -> None:
    """Validate AC-07 retry samples and apply failure-first outcome rules.

    Parameters
    ----------
    control : Mapping[str, object]
        Registered control; non-AC-07 controls need no CI-specific checks.
    record : Mapping[str, object]
        Acceptance record containing the build-test attempts and samples.

    Returns
    -------
    None
        Returns without a CI-specific check for any control except AC-07.

    Raises
    ------
    AssertionError
        If attempts, durations, sample retention, or the recorded outcome disagree.
    KeyError
        If a required control or record field is absent.
    ValueError
        If a started or completed timestamp is malformed.

    Examples
    --------
    check_ci_measurement(control, record) rejects an AC-07 timeout marked as passing.
    """
    if control['id'] != 'AC-07':
        return
    workload = _ci_build_test_workload(record)
    attempts = workload.get('attempts', [])
    _check_ci_attempt_window(attempts, record['id'])
    summary = _ci_attempt_durations(attempts, record['id'])
    require(workload['samples'] == list(summary.durations),
            f"{record['id']} samples must retain every started build-test attempt duration")
    _check_ci_measurement_outcome(control, record, summary)


def _ci_build_test_workload(record: Mapping[str, object]) -> Mapping[str, object]:
    """Select the single CI workload; for example, reject a missing build-test job."""
    jobs = [workload for workload in record['workloads'] if workload['id'] == 'ci-build-test']
    require(len(jobs) == 1, f"{record['id']} must contain exactly one ci-build-test workload")
    return jobs[0]


def _check_ci_attempt_window(attempts: list[Mapping[str, object]], record_id: str) -> None:
    """Validate the newest-first retry window; for example, reject duplicate attempts."""
    require(len(attempts) <= 20, f"{record_id} must contain only the latest 20 build-test attempts")
    attempt_ids = [(attempt['run_id'], attempt['attempt']) for attempt in attempts]
    require(len(attempt_ids) == len(set(attempt_ids)), f"{record_id} repeats a build-test attempt")
    starts = [attempt['started_at'] for attempt in attempts if attempt['started_at'] is not None]
    require(starts == sorted(starts, reverse=True), f"{record_id} attempts are not newest first")


def _ci_attempt_durations(
    attempts: list[Mapping[str, object]], record_id: str,
) -> _CiAttemptSummary:
    """Summarize attempt timing; for example, missing timestamps yield no duration."""
    durations = []
    has_incomplete_attempt = False
    for attempt in attempts:
        duration = _ci_attempt_duration(attempt, record_id)
        if duration is None:
            has_incomplete_attempt = True
        else:
            durations.append(duration)
    return _CiAttemptSummary(tuple(attempts), tuple(durations), has_incomplete_attempt)


def _ci_attempt_duration(attempt: Mapping[str, object], record_id: str) -> float | None:
    """Check one elapsed time; for example, an attempt without completion is incomplete."""
    start, finish, duration = (attempt['started_at'], attempt['completed_at'], attempt['wall_seconds'])
    if any(value is None for value in (start, finish, duration)):
        return None
    elapsed = (datetime.fromisoformat(finish.replace('Z', '+00:00'))
               - datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds()
    require(isclose(duration, elapsed, abs_tol=0.001),
            f"{record_id} run {attempt['run_id']} duration does not match its timestamps")
    return duration


def _check_ci_measurement_outcome(
    control: Mapping[str, object], record: Mapping[str, object], summary: _CiAttemptSummary,
) -> None:
    """Enforce failure, sample-count, and p90 rules; failures take precedence."""
    has_failed_attempt = any(attempt['conclusion'] != 'success' for attempt in summary.attempts)
    if has_failed_attempt:
        require(OUTCOME_VERDICTS[record['outcome']] == 'fail',
                f"{record['id']} must fail when a build-test attempt fails, times out, or has no duration")
        return
    if summary.has_incomplete_attempt:
        require(OUTCOME_VERDICTS[record['outcome']] == 'fail',
                f"{record['id']} must fail when a build-test attempt fails, times out, or has no duration")
        return
    if len(summary.attempts) < 20:
        require(record['outcome'] == 'inconclusive',
                f"{record['id']} needs 20 build-test attempts for a conclusive result")
        return
    _check_ci_p90_outcome(control, record, list(summary.durations))


def _check_ci_p90_outcome(
    control: Mapping[str, object], record: Mapping[str, object], durations: list[float],
) -> None:
    """Apply the registered p90 budget; for example, an over-budget run must fail."""
    p90_seconds = nearest_rank(durations, 0.9)
    budget_seconds = control['frozen']['decision_rule']['thresholds']['p90_minutes'] * 60
    if p90_seconds > budget_seconds:
        require(OUTCOME_VERDICTS[record['outcome']] == 'fail',
                f"{record['id']} must fail when build-test p90 exceeds its budget")
    else:
        require(record['outcome'] == 'pass',
                f"{record['id']} must pass when 20 successful attempts meet the p90 budget")


def nearest_rank(values: list[float], quantile: float) -> float:
    """Return a sample quantile using the nearest-rank definition.

    Parameters
    ----------
    values : list[float]
        Non-empty sample values.
    quantile : float
        Quantile fraction; for example, 0.9 selects rank 18 from 20 samples.

    Returns
    -------
    float
        Sample at rank ceil(quantile * len(values)) in sorted order.

    Raises
    ------
    AssertionError
        If values is empty.
    IndexError
        If the quantile selects a rank above the available sample count.

    Examples
    --------
    nearest_rank(list(range(1, 21)), 0.9) returns 18.
    """
    require(bool(values), 'A percentile requires at least one sample')
    return sorted(values)[ceil(quantile * len(values)) - 1]


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
    _check_ci_calibration_p90(control, calibration, build_test, build_durations)


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
    control: Mapping[str, object], calibration: Mapping[str, object], workload: Mapping[str, object],
    durations: list[float],
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


def check_acceptance_workflow(settings: AcceptanceWorkflowSettings, control: Mapping[str, object]) -> None:
    """Require the hosted build-test workflow to use the registered runner and timeout.

    Parameters
    ----------
    settings : AcceptanceWorkflowSettings
        Parsed runner image and timeout from the build-test job.
    control : Mapping[str, object]
        Registered AC-07 control supplying the expected image and timeout.

    Returns
    -------
    None
        Returns only when both workflow settings match the registration.

    Raises
    ------
    AssertionError
        If the workflow runner image or timeout differs from the control.
    KeyError
        If the control omits a required environment or threshold field.

    Examples
    --------
    check_acceptance_workflow(settings, control) accepts ubuntu-24.04 with an eight-minute timeout.
    """
    image = control['frozen']['environment']['image']
    timeout = control['frozen']['decision_rule']['thresholds']['timeout_minutes']
    require(settings.runner_image == image,
            f"build-test runner {settings.runner_image!r} does not match AC-07 image {image}")
    require(settings.timeout_minutes == timeout,
            f"build-test timeout {settings.timeout_minutes!r} does not match AC-07 budget {timeout}")
