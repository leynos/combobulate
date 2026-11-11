"""Validate AC-07 CI attempt outcomes and their calibration history."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import ceil, isclose

from .context import require

# DL-14 renamed AC-07's workload when it stopped measuring one job. The
# calibration record keeps `ci-build-test`, which is the series it actually
# measured before the job split; only acceptance records use this id.
REQUIRED_JOB_WORKLOAD = 'ci-required-jobs'

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
class RequiredJob:
    """One required pull-request job; e.g. `build-test` on `ubuntu-24.04` for eight minutes."""

    name: str
    runner_image: object
    timeout_minutes: object


@dataclass(frozen=True)
class AcceptanceWorkflowSettings:
    """Carry AC-07's required jobs; e.g. `build-test` plus the two Polars jobs."""

    jobs: tuple[RequiredJob, ...]

    @property
    def job_names(self) -> frozenset[str]:
        """Return the registered required-job names; e.g. `{'build-test', 'polars-lint'}`.

        The record check compares each attempt's per-job map with this set, so it
        must be derived from the same workflow the runner and timeout checks use.
        Deriving it here rather than at each call site keeps one definition of
        "required job" for both checks.

        Examples
        --------
        AcceptanceWorkflowSettings((RequiredJob('build-test', 'ubuntu-24.04', 8),)).job_names
        is frozenset({'build-test'}).
        """
        return frozenset(job.name for job in self.jobs)


def check_ci_measurement(
    control: Mapping[str, object], record: Mapping[str, object], required_jobs: frozenset[str],
) -> None:
    """Validate AC-07 retry samples and apply failure-first outcome rules.

    Parameters
    ----------
    control : Mapping[str, object]
        Registered control; non-AC-07 controls need no CI-specific checks.
    record : Mapping[str, object]
        Acceptance record containing one attempt per workflow run, each carrying
        that run's longest required job.
    required_jobs : frozenset[str]
        The required-job names the workflow declares, normally
        :attr:`AcceptanceWorkflowSettings.job_names`. Every attempt's
        ``required_job_conclusions`` must name exactly these jobs, so a record
        cannot omit a job that failed by leaving it out of the map. This is a
        required argument rather than an optional one because an omitted set
        would silently skip the completeness rule: the caller that forgot it
        would be the one whose record passes unchecked.

    Returns
    -------
    None
        Returns without a CI-specific check for any control except AC-07.

    Raises
    ------
    AssertionError
        If attempts, durations, sample retention, the recorded outcome, or the
        per-job map's job names disagree with the workflow and the record.
    KeyError
        If a required control or record field is absent.
    ValueError
        If a started or completed timestamp is malformed.

    Examples
    --------
    check_ci_measurement(control, record, frozenset({'build-test'})) rejects an
    AC-07 timeout marked as passing, and a record that omits a required job.
    """
    if control['id'] != 'AC-07':
        return
    workload = _ci_required_jobs_workload(record)
    attempts = workload.get('attempts', [])
    _check_ci_attempt_window(attempts, record['id'])
    summary = _ci_attempt_durations(attempts, record['id'])
    require(workload['samples'] == list(summary.durations),
            f"{record['id']} samples must retain every started required-job attempt duration")
    _check_recorded_job_names(workload, required_jobs, record['id'])
    _check_ci_measurement_outcome(control, record, summary)


def _check_recorded_job_names(
    workload: Mapping[str, object], required_jobs: frozenset[str], record_id: str,
) -> None:
    """Require every attempt to record exactly the workflow's required jobs.

    The outcome rule treats a job missing from an attempt's map as successful:
    it can only see the conclusions written there. A record that names two of
    the three required jobs but omits the one that failed would therefore pass
    on the strength of the jobs it did record. Comparing the map's keys with the
    workflow's own set closes that gap from the other side — an extra key is a
    job the workflow does not declare, and a missing key is a job whose result
    the record withholds.

    Parameters
    ----------
    workload : Mapping[str, object]
        The record's single ``ci-required-jobs`` workload.
    required_jobs : frozenset[str]
        Names from the workflow, via :attr:`AcceptanceWorkflowSettings.job_names`.
    record_id : str
        Record identifier used in any diagnostic.

    Returns
    -------
    None
        Returns only when every attempt records each required job and no other.

    Raises
    ------
    AssertionError
        If an attempt's job names differ from the workflow's required set.

    Examples
    --------
    A workflow declaring ``build-test`` and ``polars-lint`` is satisfied by an
    attempt recording both, and refused when the attempt records only
    ``build-test``.
    """
    for attempt in workload['attempts']:
        recorded = set(attempt.get('required_job_conclusions') or {})
        missing = sorted(required_jobs - recorded)
        unexpected = sorted(recorded - required_jobs)
        require(not missing and not unexpected,
                f"{record_id} run {attempt['run_id']} attempt {attempt['attempt']} must record every "
                f"required job's conclusion; missing {missing}, unexpected {unexpected}")


def _ci_required_jobs_workload(record: Mapping[str, object]) -> Mapping[str, object]:
    """Select the single CI workload; for example, reject a missing required-jobs series."""
    jobs = [workload for workload in record['workloads']
            if workload['id'] == REQUIRED_JOB_WORKLOAD]
    require(len(jobs) == 1,
            f"{record['id']} must contain exactly one {REQUIRED_JOB_WORKLOAD} workload")
    return jobs[0]


def _check_ci_attempt_window(attempts: list[Mapping[str, object]], record_id: str) -> None:
    """Validate the newest-first retry window; for example, reject duplicate attempts."""
    require(len(attempts) <= 20,
            f"{record_id} must contain only the latest 20 required-job attempts")
    attempt_ids = [(attempt['run_id'], attempt['attempt']) for attempt in attempts]
    require(len(attempt_ids) == len(set(attempt_ids)),
            f"{record_id} repeats a required-job attempt")
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
    failed = f"{record['id']} must fail when a required-job attempt fails, times out, or has no duration"
    if any(attempt['conclusion'] != 'success' for attempt in summary.attempts):
        require(OUTCOME_VERDICTS[record['outcome']] == 'fail', failed)
        return
    if any(_unsuccessful_required_job(attempt) for attempt in summary.attempts):
        # AC-07 requires *every* required job to succeed, and the per-attempt
        # `conclusion` covers only the run's longest job. Without this the
        # record could name a passing longest job while `polars-lint` failed.
        require(OUTCOME_VERDICTS[record['outcome']] == 'fail',
                f"{record['id']} must fail when any required job in an attempt does not succeed")
        return
    if summary.has_incomplete_attempt:
        require(OUTCOME_VERDICTS[record['outcome']] == 'fail', failed)
        return
    if len(summary.attempts) < 20:
        require(record['outcome'] == 'inconclusive',
                f"{record['id']} needs 20 required-job attempts for a conclusive result")
        return
    _check_ci_p90_outcome(control, record, list(summary.durations))


def _unsuccessful_required_job(attempt: Mapping[str, object]) -> bool:
    """Report whether any required job in one attempt did not succeed.

    An attempt that records no per-job map contributes nothing here: the
    pre-DL-14 `ci-build-test` workload measured one job, and the record's
    single ``conclusion`` already states it. The schema requires the map for
    ``ci-required-jobs``, so a current record cannot omit it.
    """
    conclusions = attempt.get('required_job_conclusions') or {}
    return any(conclusion != 'success' for conclusion in conclusions.values())


def _check_ci_p90_outcome(
    control: Mapping[str, object], record: Mapping[str, object], durations: list[float],
) -> None:
    """Apply the registered p90 budget; for example, an over-budget run must fail."""
    p90_seconds = nearest_rank(durations, 0.9)
    budget_seconds = control['frozen']['decision_rule']['thresholds']['p90_minutes'] * 60
    if p90_seconds > budget_seconds:
        require(OUTCOME_VERDICTS[record['outcome']] == 'fail',
                f"{record['id']} must fail when required-job p90 exceeds its budget")
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


def check_acceptance_workflow(settings: AcceptanceWorkflowSettings, control: Mapping[str, object]) -> None:
    """Require every required pull-request job to use AC-07's runner and timeout.

    The workload is every required job (DL-14), so a job with a different
    runner or budget would change what the statistic measures: the per-run
    figure is the longest required job, and a job outside the registered
    runner class would time itself on unknown hardware.

    Parameters
    ----------
    settings : AcceptanceWorkflowSettings
        Parsed required jobs, each with its runner image and timeout.
    control : Mapping[str, object]
        Registered AC-07 control supplying the expected image and timeout.

    Returns
    -------
    None
        Returns only when every required job matches the registration.

    Raises
    ------
    AssertionError
        If a job's runner image or timeout differs from the control, or no job
        is declared.
    KeyError
        If the control omits a required environment or threshold field.

    Examples
    --------
    check_acceptance_workflow(settings, control) accepts two jobs on
    `ubuntu-24.04` with eight-minute timeouts.
    """
    image = control['frozen']['environment']['image']
    timeout = control['frozen']['decision_rule']['thresholds']['timeout_minutes']
    require(bool(settings.jobs), 'the workflow must declare at least one required pull-request job')
    for job in settings.jobs:
        require(job.runner_image == image,
                f"{job.name} runner {job.runner_image!r} does not match AC-07 image {image}")
        require(job.timeout_minutes == timeout,
                f"{job.name} timeout {job.timeout_minutes!r} does not match AC-07 budget {timeout}")
