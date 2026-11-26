"""Hold the AC-04 cache contract for the profile-measurement workflow.

The `build-budget` job's numbers feed a pre-registered acceptance control, and
that control requires the measured environment to carry no compiler cache. The
rule is expressed here, apart from the workflow's other contract tests, so one
module owns the ordering, conditional, and script-text guarantees and the test
module only exercises them.

Every check raises `AssertionError` with a message that names the missing
guarantee, because these functions are called from assertions in the test
suite and from the mutation cases that prove each guard is load-bearing. None
of them read a file: the caller parses the workflow and passes the job mapping
in, which keeps the rules testable against an in-memory job.

Examples
--------
The committed job satisfies every rule::

    import yaml

    document = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    check_cache_assertion_order(document['jobs']['build-budget'])  # no error
"""

from __future__ import annotations

from typing import cast

SETUP_RUST_ACTION = 'leynos/shared-actions/.github/actions/setup-rust@'
CACHE_ASSERTION_STEP = 'Confirm the measured environment carries no cache'
COLD_BUILD_STEP = 'Measure five cold builds per profile, alternating'
INCREMENTAL_BUILD_STEP = 'Measure five incremental builds per profile, alternating'
FETCH_STEP = 'Fetch dependencies once, untimed'
BUILD_STANDARD_STEP = 'Install the pinned build standard'
PROVER_STEP = 'Install the pinned Kani and Verus releases'

ABSENCE_CHECK = 'test -z "${RUSTC_WRAPPER-}"'
ENVIRONMENT_RECORD = (
    "printf '%s\\n' \"${RUSTC_WRAPPER-}\" \"$CARGO_INCREMENTAL\" "
    '> build-budget/build-environment'
)
STRICT_MODE = 'set -euo pipefail'
TIMED_INVOCATION = '/usr/bin/time'

# Keys that let a step be skipped or let a failed step still report success.
CONDITIONAL_STEP_KEYS = ('if', 'continue-on-error')


def step_index_using(job: dict, prefix: str) -> int:
    """Return the index of the job's sole step whose ``uses`` starts ``prefix``.

    Binding an ordering assertion to the step that really carries the action
    keeps a same-named or comment-only mention from satisfying it.

    Raises
    ------
    AssertionError
        When no step uses ``prefix`` or more than one does.

    Examples
    --------
    The measuring job declares one pinned ``setup-rust`` step::

        step_index_using(job, SETUP_RUST_ACTION)
    """
    matches = [
        index
        for index, step in enumerate(job['steps'])
        if step.get('uses', '').startswith(prefix)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f'the job must declare exactly one {prefix} step, found {len(matches)}'
        )
    return matches[0]


def step_index_named(job: dict, name: str) -> int:
    """Return the index of the job's sole step called ``name``.

    Raises
    ------
    AssertionError
        When the job has no such step or more than one.

    Examples
    --------
    The cache assertion is located by its exact name::

        step_index_named(job, CACHE_ASSERTION_STEP)
    """
    matches = [
        index
        for index, step in enumerate(job['steps'])
        if step.get('name') == name
    ]
    if len(matches) != 1:
        raise AssertionError(
            f'the job must declare exactly one step named {name!r}, '
            f'found {len(matches)}'
        )
    return matches[0]


def named_step(job: dict, name: str) -> dict:
    """Return the job's sole step called ``name``."""
    return cast('dict', job['steps'][step_index_named(job, name)])


def executable_lines(script: str) -> list[str]:
    """Return the stripped, non-blank, non-comment lines of a shell script.

    A commented-out check is not executable, so it cannot satisfy a contract
    that requires the check to run.

    Examples
    --------
    Comments and blank lines disappear from the result::

        executable_lines('set -e\\n# note\\ntrue\\n')  # ['set -e', 'true']
    """
    stripped = (line.strip() for line in script.splitlines())
    return [line for line in stripped if line and not line.startswith('#')]


def check_cache_assertion_order(job: dict) -> None:
    """Require the cache assertion immediately before the first timed build.

    The assertion must observe the environment the samples inherit, so every
    provisioning step and the untimed fetch run before it, and the first timed
    phase runs immediately after it. The assertion must also be
    unconditional: a skipped step, a soft failure, a masked command, or a
    check inside a branch that never runs would leave the measurement
    cache-free only by assumption.

    Raises
    ------
    AssertionError
        When an ordering, timing, or failure-propagation guarantee is missing.

    Examples
    --------
    The committed job satisfies the contract::

        check_cache_assertion_order(job)
    """
    assertion = step_index_named(job, CACHE_ASSERTION_STEP)
    check_cold_build_follows(job, assertion)
    check_prerequisites_precede(job, assertion)
    check_no_earlier_timed_step(job, assertion)
    assertion_step = named_step(job, CACHE_ASSERTION_STEP)
    check_assertion_step(job, assertion_step)
    check_assertion_script(assertion_step)
    check_no_step_wrapper(job)


def check_cold_build_follows(job: dict, assertion: int) -> None:
    """Require the first timed phase immediately after the assertion.

    Raises
    ------
    AssertionError
        When any step, including the untimed fetch, sits between them.
    """
    if step_index_named(job, COLD_BUILD_STEP) != assertion + 1:
        raise AssertionError(
            'the first timed phase must immediately follow the cache assertion'
        )


def check_prerequisites_precede(job: dict, assertion: int) -> None:
    """Require setup-rust, both installers and the fetch before the assertion.

    Raises
    ------
    AssertionError
        When any provisioning step or the fetch follows the assertion.
    """
    prerequisites = (
        ('setup-rust', step_index_using(job, SETUP_RUST_ACTION)),
        (BUILD_STANDARD_STEP, step_index_named(job, BUILD_STANDARD_STEP)),
        (PROVER_STEP, step_index_named(job, PROVER_STEP)),
        (FETCH_STEP, step_index_named(job, FETCH_STEP)),
    )
    for label, index in prerequisites:
        if index >= assertion:
            raise AssertionError(
                f'{label!r} must run before the cache assertion observes '
                'the environment'
            )


def check_no_earlier_timed_step(job: dict, assertion: int) -> None:
    """Reject a sample taken before the environment is observed.

    Raises
    ------
    AssertionError
        When a step ahead of the assertion runs the timing command.
    """
    for step in job['steps'][:assertion]:
        if is_timed(step):
            raise AssertionError(
                f'step {step_label(step)!r} is timed before the cache assertion'
            )


def is_timed(step: dict) -> bool:
    """Whether any executable line of ``step`` invokes the timing command.

    Comment lines are ignored: a comment naming the timing command does not run
    it, and rejecting one would make the contract test fail on documentation.
    """
    return any(
        TIMED_INVOCATION in line
        for line in executable_lines(cast('str', step.get('run', '')))
    )


def step_label(step: dict) -> str:
    """Return the name a step is reported under, falling back to its action."""
    return cast('str', step.get('name', step.get('uses', '')))


def check_assertion_step(job: dict, step: dict) -> None:
    """Require the assertion step itself to run and to fail the job.

    A job-level ``RUSTC_WRAPPER`` contaminates every sample, so it is rejected
    outright; a step-level value is caught by :func:`check_no_step_wrapper`.

    Raises
    ------
    AssertionError
        When the step carries an ``if`` guard or ``continue-on-error``, or when
        the job sets ``RUSTC_WRAPPER``.
    """
    for key in CONDITIONAL_STEP_KEYS:
        if key in step:
            raise AssertionError(
                f'the cache assertion must not carry {key!r}; it must always '
                'run and must fail the job'
            )
    check_no_job_wrapper(job)


def check_no_job_wrapper(job: dict) -> None:
    """Reject a job-level ``RUSTC_WRAPPER``, which reaches every sample.

    Raises
    ------
    AssertionError
        When the job's ``env`` mapping sets ``RUSTC_WRAPPER``.
    """
    if 'RUSTC_WRAPPER' in job.get('env', {}):
        raise AssertionError(
            'the job must not configure RUSTC_WRAPPER; the control requires '
            'it unset'
        )


def check_no_step_wrapper(job: dict) -> None:
    """Reject a step-level ``RUSTC_WRAPPER`` anywhere in the job.

    A step-level value applies to that step alone, so an assertion that
    observed an empty wrapper would say nothing about a timed, warm-up, or
    proof step that configured its own cache.

    Raises
    ------
    AssertionError
        When any step's ``env`` mapping sets ``RUSTC_WRAPPER``.
    """
    for step in job['steps']:
        if 'RUSTC_WRAPPER' in step.get('env', {}):
            raise AssertionError(
                f'step {step_label(step)!r} must not configure RUSTC_WRAPPER; '
                'the control requires it unset'
            )


def check_assertion_script(step: dict) -> None:
    """Require the exact fail-fast script that checks and records.

    Only three commands are permitted, in this order: strict mode, the exact
    absence check, and the environment record. A fourth line could exit
    successfully before the check, and a condition could skip it, while both
    required lines remained in the text. This also rejects masking forms such
    as ``|| true`` and ``set +e`` by construction.

    Raises
    ------
    AssertionError
        When the executable lines are not exactly the permitted sequence.
    """
    lines = executable_lines(cast('str', step.get('run', '')))
    if lines != permitted_assertion_sequence():
        raise AssertionError(
            'the cache assertion must be exactly the strict-mode line, the '
            'RUSTC_WRAPPER absence check and the environment record, in that '
            f'order; got {lines!r}'
        )


def permitted_assertion_sequence() -> list[str]:
    """Return the only script the assertion may run.

    The record line is compared exactly. A looser match accepts a line that
    prints the names of the two variables rather than their values, which
    creates no evidence for the acceptance record.

    Examples
    --------
    The committed script is the permitted sequence::

        permitted_assertion_sequence()  # [STRICT_MODE, ABSENCE_CHECK, ...]
    """
    return [STRICT_MODE, ABSENCE_CHECK, ENVIRONMENT_RECORD]


def setup_rust_inputs(job: dict) -> dict[str, str]:
    """Return the ``with:`` inputs of the job's sole pinned ``setup-rust`` step.

    Raises
    ------
    AssertionError
        When the job has no ``setup-rust`` step or more than one.
    """
    step = job['steps'][step_index_using(job, SETUP_RUST_ACTION)]
    return cast('dict', step.get('with', {}))
