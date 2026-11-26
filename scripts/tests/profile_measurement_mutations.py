"""Mutate the committed build-budget job to prove each contract guard works.

Every case here removes one protection from a deep copy of the workflow's
parsed `build-budget` job and requires `check_cache_assertion_order` to reject
it. Keeping the cases apart from the workflow's contract checks lets a failing
case name the protection it removes, and lets the committed job stay the single
positive control.

The job mapping is supplied by the caller, so this module parses no file and
tests cannot drift from the workflow the contract reads.

Examples
--------
Each case is a named function taking one job mapping::

    export_wrapper_in_a_cold_build(job)  # adds `export RUSTC_WRAPPER=...`
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import cast

import pytest

from profile_measurement_contract import (
    ABSENCE_CHECK,
    BUILD_STANDARD_STEP,
    CACHE_ASSERTION_STEP,
    COLD_BUILD_STEP,
    ENVIRONMENT_RECORD,
    FETCH_STEP,
    INCREMENTAL_BUILD_STEP,
    PROVER_STEP,
    SETUP_RUST_ACTION,
    STRICT_MODE,
    TOOL_IDENTITY_STEP,
    check_cache_assertion_order,
    named_step,
    step_index_named,
    step_index_using,
)

# Mutations refer to the helpers by their public names.
_named_step = named_step
_step_index_named = step_index_named
_step_index_using = step_index_using
_check_cache_assertion_order = check_cache_assertion_order


def _move_step_after(job: dict, source: int, anchor: str) -> None:
    """Move one step of ``job`` to immediately follow the step called ``anchor``."""
    step = job['steps'].pop(source)
    job['steps'].insert(_step_index_named(job, anchor) + 1, step)


def _insert_step(job: dict, index: int, name: str, script: str) -> None:
    """Insert a step into an in-memory job, leaving the parsed workflow untouched."""
    job['steps'].insert(index, {'name': name, 'run': script})


# The committed job is supplied by the caller so this module reads no file.


# Each mutation removes one protection the cache contract must keep. Every case
# is applied to a deep copy of the committed job, so the workflow file is never
# edited and the positive controls above still read the real job.
def _move_setup_rust_after_assertion(job: dict) -> None:
    """Move setup-rust between the assertion and the cold build."""
    _move_step_after(job, _step_index_using(job, SETUP_RUST_ACTION), CACHE_ASSERTION_STEP)


def _move_setup_rust_after_cold_build(job: dict) -> None:
    """Move setup-rust behind the first timed phase."""
    _move_step_after(job, _step_index_using(job, SETUP_RUST_ACTION), COLD_BUILD_STEP)


def _remove_setup_rust(job: dict) -> None:
    """Delete the sole setup-rust step."""
    job['steps'].pop(_step_index_using(job, SETUP_RUST_ACTION))


def _duplicate_setup_rust(job: dict) -> None:
    """Add a second setup-rust step with different inputs."""
    index = _step_index_using(job, SETUP_RUST_ACTION)
    extra = copy.deepcopy(job['steps'][index])
    extra['with'] = {'rustflags': '', 'use-sccache': 'true'}
    job['steps'].insert(index + 1, extra)


def _remove_assertion(job: dict) -> None:
    """Delete the cache assertion step."""
    job['steps'].pop(_step_index_named(job, CACHE_ASSERTION_STEP))


def _duplicate_assertion(job: dict) -> None:
    """Insert a copy of the assertion directly after the original."""
    index = _step_index_named(job, CACHE_ASSERTION_STEP)
    job['steps'].insert(index + 1, copy.deepcopy(job['steps'][index]))


def _insert_step_before_cold_build(job: dict) -> None:
    """Place an unrelated step between the assertion and the cold build."""
    index = _step_index_named(job, CACHE_ASSERTION_STEP)
    _insert_step(job, index + 1, 'An intervening step', 'true')


def _move_fetch_after_assertion(job: dict) -> None:
    """Move the untimed fetch between the assertion and the cold build."""
    _move_step_after(job, _step_index_named(job, FETCH_STEP), CACHE_ASSERTION_STEP)


def _guard_the_assertion(job: dict) -> None:
    """Give the assertion an ``if`` guard."""
    _named_step(job, CACHE_ASSERTION_STEP)['if'] = 'always()'


def _let_the_assertion_fail_softly(job: dict) -> None:
    """Let the assertion report success despite a failed check."""
    _named_step(job, CACHE_ASSERTION_STEP)['continue-on-error'] = 'true'


def _replace_assertion_script(job: dict, replacement: str) -> None:
    """Replace the assertion's whole script with ``replacement``."""
    _named_step(job, CACHE_ASSERTION_STEP)['run'] = replacement


def _script_from(job: dict, *, drop: str = '', insert_after: str = '', text: str = '') -> str:
    """Return the assertion script with one line dropped or one line inserted."""
    lines = cast('str', _named_step(job, CACHE_ASSERTION_STEP)['run']).splitlines()
    if drop:
        index = lines.index(drop)
        del lines[index]
    if insert_after:
        lines.insert(lines.index(insert_after) + 1, text)
    return '\n'.join(lines) + '\n'


def _mask_absence_check(job: dict) -> None:
    """Append a success fallback to the absence check."""
    _replace_assertion_script(
        job,
        _script_from(job).replace(ABSENCE_CHECK, ABSENCE_CHECK + ' || true'),
    )


def _comment_out_absence_check(job: dict) -> None:
    """Turn the absence check into a comment."""
    _replace_assertion_script(
        job,
        _script_from(job).replace(ABSENCE_CHECK, '# ' + ABSENCE_CHECK),
    )


def _wrap_absence_check_in_dead_branch(job: dict) -> None:
    """Wrap the absence check in a branch that cannot run."""
    _replace_assertion_script(
        job,
        _script_from(job).replace(
            ABSENCE_CHECK,
            f'if false; then {ABSENCE_CHECK}; fi',
        ),
    )


def _short_circuit_absence_check(job: dict) -> None:
    """Join the check to another command with `&&`."""
    _replace_assertion_script(
        job,
        _script_from(job).replace(ABSENCE_CHECK, f'{ABSENCE_CHECK} && true'),
    )


def _drop_environment_record(job: dict) -> None:
    """Remove the line that records the observed environment."""
    _replace_assertion_script(job, _script_from(job, drop=ENVIRONMENT_RECORD))


def _record_variable_names(job: dict) -> None:
    """Record the literal names instead of the observed values."""
    _replace_assertion_script(
        job,
        _script_from(job).replace(
            ENVIRONMENT_RECORD,
            "printf '%s\\n' RUSTC_WRAPPER CARGO_INCREMENTAL "
            'build-budget/build-environment',
        ),
    )


def _exit_before_the_check(job: dict) -> None:
    """Terminate the script successfully before the check runs."""
    _replace_assertion_script(
        job,
        _script_from(job, insert_after=STRICT_MODE, text='exit 0'),
    )


def _drop_strict_mode(job: dict) -> None:
    """Remove the strict-mode line from the assertion script."""
    _replace_assertion_script(job, _script_from(job, drop=STRICT_MODE))


def _set_job_level_wrapper(job: dict) -> None:
    """Configure the wrapper for the whole job."""
    job['env']['RUSTC_WRAPPER'] = 'sccache'


def _override_wrapper_on_the_step(job: dict) -> None:
    """Blank the wrapper for the assertion step alone, leaving the job unset."""
    _named_step(job, CACHE_ASSERTION_STEP)['env'] = {'RUSTC_WRAPPER': ''}


def _override_wrapper_on_a_cold_build(job: dict) -> None:
    """Give the first measured phase its own cache wrapper."""
    step = _named_step(job, COLD_BUILD_STEP)
    step.setdefault('env', {})['RUSTC_WRAPPER'] = 'sccache'


def _override_wrapper_on_an_incremental_build(job: dict) -> None:
    """Give the incremental phase its own cache wrapper."""
    step = _named_step(job, INCREMENTAL_BUILD_STEP)
    step.setdefault('env', {})['RUSTC_WRAPPER'] = 'sccache'


def _time_a_prelude(job: dict) -> None:
    """Insert a timed step ahead of the whole provisioning phase."""
    _insert_step(job, 0, 'Time a prelude', '/usr/bin/time -v true')


def _time_inside_a_provisioning_script(job: dict) -> None:
    """Time a command inside an earlier step rather than in its own step."""
    step = _named_step(job, 'Begin the build-budget measurement')
    step['run'] = step['run'] + '\n/usr/bin/time -v true\n'


def _export_wrapper_in_a_cold_build(job: dict) -> None:
    """Export a wrapper inside the first measured script, leaving env unset."""
    step = _named_step(job, COLD_BUILD_STEP)
    step['run'] = 'export RUSTC_WRAPPER=sccache\n' + step['run']


def _export_wrapper_in_an_incremental_build(job: dict) -> None:
    """Export a wrapper inside the incremental measured script."""
    step = _named_step(job, INCREMENTAL_BUILD_STEP)
    step['run'] = step['run'] + '\nexport RUSTC_WRAPPER=sccache\n'


_TIMED_CARGO = (
    '/usr/bin/time -v -o "$output.time" \\\n'
    '      cargo build --workspace'
)
_WRAPPED_TIMED_CARGO = (
    '/usr/bin/time -v -o "$output.time" \\\n'
    '      env CARGO_BUILD_JOBS=4 RUSTC_WRAPPER=sccache \\\n'
    '      cargo build --workspace'
)


def _hide_wrapper_after_env_arguments(job: dict) -> None:
    """Set a wrapper after other `env` arguments on the timed Cargo build."""
    step = _named_step(job, COLD_BUILD_STEP)
    assert _TIMED_CARGO in step['run'], 'the cold phase must run the timed Cargo build'
    step['run'] = step['run'].replace(_TIMED_CARGO, _WRAPPED_TIMED_CARGO)


def _move_tool_identity_after_the_cold_build(job: dict) -> None:
    """Move the tool-identity step behind the first timed phase."""
    _move_step_after(job, _step_index_named(job, TOOL_IDENTITY_STEP), COLD_BUILD_STEP)


def _move_linker_after_the_assertion(job: dict) -> None:
    """Move the linker installer between the assertion and the cold build."""
    source = _step_index_named(job, 'Install the linker toolchain')
    _move_step_after(job, source, CACHE_ASSERTION_STEP)


def _move_setup_uv_after_the_assertion(job: dict) -> None:
    """Move the setup-uv action between the assertion and the cold build."""
    source = _step_index_using(job, 'astral-sh/setup-uv@')
    _move_step_after(job, source, CACHE_ASSERTION_STEP)


_MUTATIONS = (
    pytest.param(_move_setup_rust_after_assertion, id='setup-rust-after-assertion'),
    pytest.param(_move_setup_rust_after_cold_build, id='setup-rust-after-cold-build'),
    pytest.param(_remove_setup_rust, id='setup-rust-removed'),
    pytest.param(_duplicate_setup_rust, id='setup-rust-duplicated'),
    pytest.param(_remove_assertion, id='assertion-removed'),
    pytest.param(_duplicate_assertion, id='assertion-duplicated'),
    pytest.param(_insert_step_before_cold_build, id='intervening-step'),
    pytest.param(_move_fetch_after_assertion, id='fetch-after-assertion'),
    pytest.param(_guard_the_assertion, id='conditional-assertion'),
    pytest.param(_let_the_assertion_fail_softly, id='continue-on-error'),
    pytest.param(_mask_absence_check, id='masked-check'),
    pytest.param(_comment_out_absence_check, id='commented-out-check'),
    pytest.param(_wrap_absence_check_in_dead_branch, id='dead-branch-check'),
    pytest.param(_short_circuit_absence_check, id='short-circuited-check'),
    pytest.param(_drop_environment_record, id='record-dropped'),
    pytest.param(_record_variable_names, id='record-names-only'),
    pytest.param(_exit_before_the_check, id='early-exit'),
    pytest.param(_drop_strict_mode, id='no-strict-mode'),
    pytest.param(_set_job_level_wrapper, id='job-level-wrapper'),
    pytest.param(_override_wrapper_on_the_step, id='assertion-step-wrapper'),
    pytest.param(_override_wrapper_on_a_cold_build, id='cold-step-wrapper'),
    pytest.param(_override_wrapper_on_an_incremental_build, id='incremental-step-wrapper'),
    pytest.param(_time_a_prelude, id='timed-prelude'),
    pytest.param(_time_inside_a_provisioning_script, id='timed-inside-script'),
    pytest.param(_export_wrapper_in_a_cold_build, id='cold-script-wrapper'),
    pytest.param(_export_wrapper_in_an_incremental_build, id='incremental-script-wrapper'),
    pytest.param(_hide_wrapper_after_env_arguments, id='env-argument-wrapper'),
    pytest.param(_move_tool_identity_after_the_cold_build, id='tool-identity-after-cold'),
    pytest.param(_move_linker_after_the_assertion, id='linker-after-assertion'),
    pytest.param(_move_setup_uv_after_the_assertion, id='setup-uv-after-assertion'),
)



def assert_rejected(committed_job: dict, mutate: Callable[[dict], None]) -> None:
    """Require ``mutate`` to change a copy of ``committed_job`` and be rejected.

    The equality guard proves the mutation changed the parsed job, so a passing
    rejection cannot come from an edit that silently did nothing.

    Raises
    ------
    AssertionError
        When the mutation changes nothing, or the checker accepts the result.
    """
    changed = copy.deepcopy(committed_job)
    mutate(changed)
    assert changed != committed_job, 'the mutation must change the parsed job'
    with pytest.raises(AssertionError):
        _check_cache_assertion_order(changed)
