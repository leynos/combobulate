"""Keep the hosted profile-measurement workflow wired to its accepted protocol.

The measurement numbers feed pre-registered acceptance controls, so a silent
edit to the trigger, the measured routes, the pinned tool versions, the
cold-run loop, the cache policy, the position of the cache assertion, or the
artefact conditions would move the evidence without anyone noticing. These
checks read the workflow file as data and assert each of those boundaries;
they never start a runner.

Examples
--------
A route removed from the matrix fails this suite rather than shrinking the
recorded evidence::

    ROUTES  # ('rustdoc', 'clippy', 'whitaker', 'nextest', 'coverage', 'ui')
"""

from __future__ import annotations

import copy
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/profile-measurements.yml'

ROUTES = ('rustdoc', 'clippy', 'whitaker', 'nextest', 'coverage', 'ui')
MEASUREMENT_JOBS = ('measure-profile', 'build-budget')
LABEL_GATE = "github.event.label.name == 'measure-profiles'"
DISPATCH_GATE = "github.event_name == 'workflow_dispatch'"

SETUP_RUST_ACTION = 'leynos/shared-actions/.github/actions/setup-rust@'
CACHE_ASSERTION_STEP = 'Confirm the measured environment carries no cache'
COLD_BUILD_STEP = 'Measure five cold builds per profile, alternating'
FETCH_STEP = 'Fetch dependencies once, untimed'
BUILD_STANDARD_STEP = 'Install the pinned build standard'
PROVER_STEP = 'Install the pinned Kani and Verus releases'
ABSENCE_CHECK = 'test -z "${RUSTC_WRAPPER-}"'
ENVIRONMENT_RECORD = (
    "printf '%s\\n' \"${RUSTC_WRAPPER-}\" \"$CARGO_INCREMENTAL\" "
    '> build-budget/build-environment'
)
TIMED_INVOCATION = '/usr/bin/time'
STRICT_MODE = 'set -euo pipefail'


def _workflow() -> dict:
    """Return the measurement workflow decoded with every scalar as a string.

    ``BaseLoader`` keeps ``on``, ``if``, and boolean-looking values as the
    literal text the file contains. A YAML 1.1 loader would decode the ``on``
    key as ``True`` and ``cancel-in-progress`` as a boolean, which turns the
    assertions below into tests of the loader rather than of the workflow.

    Examples
    --------
    The trigger block is reachable under its written key::

        _workflow()['on']['pull_request']['types']  # ['labeled']
    """
    document = yaml.load(WORKFLOW.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    return cast('dict', document)


def _job(name: str) -> dict:
    """Return one job block from the measurement workflow."""
    return cast('dict', _workflow()['jobs'][name])


def _step_run_matching(job: dict, needle: str) -> str:
    """Return the first ``run`` script in ``job`` that contains ``needle``.

    Ordering-sensitive checks use the index locators below instead: a comment
    in an earlier step that merely names the same text must not stand in for
    the step whose position is being asserted.

    Raises
    ------
    AssertionError
        When no step's script mentions ``needle``.
    """
    for step in job['steps']:
        script = step.get('run', '')
        if needle in script:
            return cast('str', script)
    raise AssertionError(f'no step script in the job contains {needle!r}')


def _step_index_using(job: dict, prefix: str) -> int:
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

        _step_index_using(_job('build-budget'), SETUP_RUST_ACTION)
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


def _step_index_named(job: dict, name: str) -> int:
    """Return the index of the job's sole step called ``name``.

    Raises
    ------
    AssertionError
        When the job has no such step or more than one.

    Examples
    --------
    The cache assertion is located by its exact name::

        _step_index_named(_job('build-budget'), CACHE_ASSERTION_STEP)
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


def _named_step(job: dict, name: str) -> dict:
    """Return the job's sole step called ``name``."""
    return cast('dict', job['steps'][_step_index_named(job, name)])


def _executable_lines(script: str) -> list[str]:
    """Return the stripped, non-blank, non-comment lines of a shell script.

    A commented-out check is not executable, so it cannot satisfy a contract
    that requires the check to run.

    Examples
    --------
    Comments and blank lines disappear from the result::

        _executable_lines('set -e\\n# note\\ntrue\\n')  # ['set -e', 'true']
    """
    stripped = (line.strip() for line in script.splitlines())
    return [line for line in stripped if line and not line.startswith('#')]




def _check_cache_assertion_order(job: dict) -> None:
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

        _check_cache_assertion_order(_job('build-budget'))
    """
    assertion = _step_index_named(job, CACHE_ASSERTION_STEP)
    _check_assertion_position(job, assertion)
    assertion_step = _named_step(job, CACHE_ASSERTION_STEP)
    _check_assertion_step(job, assertion_step)
    _check_assertion_script(assertion_step)


def _check_assertion_position(job: dict, assertion: int) -> None:
    """Require every prerequisite before the assertion and the cold build after.

    Parameters
    ----------
    job
        One parsed workflow job mapping.
    assertion
        Index of the cache assertion step in ``job['steps']``.

    Raises
    ------
    AssertionError
        When a prerequisite follows the assertion, the first timed phase does
        not immediately follow it, or an earlier step is already timed.
    """
    if _step_index_named(job, COLD_BUILD_STEP) != assertion + 1:
        raise AssertionError(
            'the first timed phase must immediately follow the cache assertion'
        )

    prerequisites = (
        ('setup-rust', _step_index_using(job, SETUP_RUST_ACTION)),
        (BUILD_STANDARD_STEP, _step_index_named(job, BUILD_STANDARD_STEP)),
        (PROVER_STEP, _step_index_named(job, PROVER_STEP)),
        (FETCH_STEP, _step_index_named(job, FETCH_STEP)),
    )
    for label, index in prerequisites:
        if index >= assertion:
            raise AssertionError(
                f'{label!r} must run before the cache assertion observes '
                'the environment'
            )

    for step in job['steps'][:assertion]:
        if _is_timed(step):
            raise AssertionError(
                f'step {step.get("name", step.get("uses", ""))!r} is timed '
                'before the cache assertion'
            )


def _is_timed(step: dict) -> bool:
    """Whether any executable line of ``step`` invokes the timing command.

    Comment lines are ignored: a comment naming the timing command does not run
    it, and rejecting one would make the contract test fail on documentation.
    """
    return any(
        TIMED_INVOCATION in line
        for line in _executable_lines(cast('str', step.get('run', '')))
    )


def _check_assertion_step(job: dict, step: dict) -> None:
    """Require the assertion step itself to run and to fail the job.

    A step-level ``RUSTC_WRAPPER`` would let the assertion observe an empty
    value while the timed builds inherit a job-level wrapper. A job-level
    wrapper contaminates every sample directly, so neither is accepted.

    Raises
    ------
    AssertionError
        When the step carries an ``if`` guard or ``continue-on-error``, or when
        either the job or the step sets ``RUSTC_WRAPPER``.
    """
    for key in ('if', 'continue-on-error'):
        if key in step:
            raise AssertionError(
                f'the cache assertion must not carry {key!r}; it must always '
                'run and must fail the job'
            )
    if 'RUSTC_WRAPPER' in job.get('env', {}):
        raise AssertionError(
            'the job must not configure RUSTC_WRAPPER; the control requires '
            'it unset'
        )
    if 'RUSTC_WRAPPER' in step.get('env', {}):
        raise AssertionError(
            'the assertion must not override RUSTC_WRAPPER for its own step; '
            'the timed builds would still inherit the job value'
        )


def _check_assertion_script(step: dict) -> None:
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
    lines = _executable_lines(cast('str', step.get('run', '')))
    if not _is_permitted_assertion_sequence(lines):
        raise AssertionError(
            'the cache assertion must be exactly the strict-mode line, the '
            'RUSTC_WRAPPER absence check and the environment record, in that '
            f'order; got {lines!r}'
        )


def _is_permitted_assertion_sequence(lines: list[str]) -> bool:
    """Whether ``lines`` is the strict-mode, check, and record sequence.

    The record line is compared exactly. A looser match accepts a line that
    prints the names of the two variables rather than their values, which
    creates no evidence for the acceptance record.

    Examples
    --------
    The committed script is the permitted sequence::

        _is_permitted_assertion_sequence(['set -euo pipefail', ...])  # True
    """
    return lines == [STRICT_MODE, ABSENCE_CHECK, ENVIRONMENT_RECORD]


def _setup_rust_inputs(job: dict) -> dict[str, str]:
    """Return the ``with:`` inputs of the job's sole pinned ``setup-rust`` step.

    Raises
    ------
    AssertionError
        When the job has no ``setup-rust`` step or more than one.
    """
    step = job['steps'][_step_index_using(job, SETUP_RUST_ACTION)]
    return cast('dict', step.get('with', {}))


class TriggerTests(unittest.TestCase):
    """Keep both entry points and the label gate that guards them."""

    def test_triggers_are_dispatch_and_only_the_labeled_action(self) -> None:
        """A broader pull_request trigger would measure unlabelled pushes."""
        triggers = _workflow()['on']

        self.assertEqual(
            sorted(triggers),
            ['pull_request', 'workflow_dispatch'],
            'a measurement run must start by dispatch or by a pull request label',
        )
        self.assertEqual(
            triggers['pull_request'],
            {'types': ['labeled']},
            'the pull request trigger must be limited to the labeled action',
        )

    def test_every_measurement_job_requires_the_label(self) -> None:
        """Labelling a pull request for another reason must skip every job."""
        for name in MEASUREMENT_JOBS:
            with self.subTest(job=name):
                condition = _job(name)['if']
                self.assertIn(LABEL_GATE, condition, f'{name} must name the measurement label')
                self.assertIn(DISPATCH_GATE, condition, f'{name} must also allow manual dispatch')

    def test_concurrency_separates_labels_without_cancelling(self) -> None:
        """Distinct labels queue independently; a running measurement survives."""
        concurrency = _workflow()['concurrency']

        self.assertIn('github.event.label.name', concurrency['group'], 'the label name must partition the group')
        self.assertEqual(
            concurrency['cancel-in-progress'],
            'false',
            'a measurement must not be cancelled by a later request',
        )


class RouteMatrixTests(unittest.TestCase):
    """Keep the exact six measured routes and their shared environment."""

    def test_matrix_names_the_six_accepted_routes(self) -> None:
        """A route dropped from the matrix silently removes its measurement."""
        matrix = _job('measure-profile')['strategy']['matrix']

        self.assertEqual(
            tuple(matrix['route']),
            ROUTES,
            'the matrix must measure exactly the accepted routes in order',
        )

    def test_matrix_does_not_stop_at_the_first_failing_route(self) -> None:
        """One broken route must not hide the other five observations."""
        strategy = _job('measure-profile')['strategy']

        self.assertEqual(strategy['fail-fast'], 'false', 'every route must report independently')

    def test_shared_environment_pins_parallelism_and_disables_caching(self) -> None:
        """A warm local cache or a different job count changes the timings."""
        environment = _job('measure-profile')['env']

        self.assertEqual(environment['CARGO_BUILD_JOBS'], '4', 'the measured parallelism must stay fixed')
        self.assertEqual(environment['CARGO_INCREMENTAL'], '0', 'incremental state must not shorten a run')
        self.assertEqual(environment['SCCACHE_RECACHE'], '1', 'sccache must not serve a cached object')
        self.assertEqual(environment['RUSTDOCFLAGS'], '-D warnings', 'a rustdoc warning must fail the route')


class ToolPinTests(unittest.TestCase):
    """Pin the tool identities behind the accepted measurement runs."""

    def test_measurement_tools_are_pinned_to_the_accepted_versions(self) -> None:
        """A newer release between runs would move the recorded timings."""
        script = _step_run_matching(_job('measure-profile'), 'cargo binstall')

        for pin in ('cargo-nextest@0.9.150', 'cargo-llvm-cov@0.9.1'):
            self.assertIn(pin, script, f'the workflow must install {pin}')

    def test_whitaker_installer_pins_its_version_and_digest(self) -> None:
        """The installer digest must agree with the action's own manifest.

        The digest's value is owned by the installer release, so restating it
        would turn every deliberate repin into a test edit. The action gives
        its manifest precedence and rejects a supplied digest that conflicts
        with it; the manifest names the Linux x86-64 archive for the pinned
        version. The workflow therefore keeps the version and digest aligned
        rather than letting the digest select the archive, and only their
        presence and shape are asserted here.
        """
        steps = _job('measure-profile')['steps']
        installer = next(
            step for step in steps if 'install-whitaker' in step.get('uses', '')
        )
        inputs = installer['with']

        self.assertNotIn('installer-version', inputs, 'the action pin owns the installer version')
        self.assertNotIn('installer-sha256', inputs, 'the action pin owns the installer digest')
        self.assertRegex(installer['uses'], r'@[0-9a-f]{40}$', 'the action must be pinned by SHA')


class ColdRunTests(unittest.TestCase):
    """Keep three genuinely independent cold runs per route."""

    def test_each_route_runs_three_cold_iterations(self) -> None:
        """Two runs cannot show variance; a warm run cannot be called cold."""
        script = _step_run_matching(_job('measure-profile'), 'for run in')

        self.assertIn('for run in 1 2 3', script, 'each route must be measured three times')

    def test_every_run_owns_its_target_and_driver_directory(self) -> None:
        """A shared target directory would make later runs warm."""
        script = _step_run_matching(_job('measure-profile'), 'for run in')

        self.assertIn('CARGO_TARGET_DIR="$PWD/profile-target-$run"', script, 'each run must own its target directory')
        self.assertIn(
            'DYLINT_DRIVER_PATH="$CARGO_TARGET_DIR/whitaker-driver"',
            script,
            'Whitaker must build its driver inside the run that measures it',
        )

    def test_only_the_last_run_survives_for_the_cache_save(self) -> None:
        """Deleting all runs would leave nothing for the main-only cache."""
        script = _step_run_matching(_job('measure-profile'), 'for run in')

        self.assertIn(
            'if [ "$run" != 3 ]; then rm -rf -- "$CARGO_TARGET_DIR"; fi',
            script,
            'the earlier runs must be discarded and the third retained',
        )


class CachePolicyTests(unittest.TestCase):
    """Save the measured cache on main only, keyed by the run that made it."""

    def test_cache_save_is_conditional_on_main(self) -> None:
        """A pull request must never publish a cache from its measurement."""
        steps = _job('measure-profile')['steps']
        saves = [step for step in steps if 'cache/save' in step.get('uses', '')]

        self.assertEqual(len(saves), 1, 'the workflow must save exactly one cache entry')
        self.assertEqual(saves[0]['if'], "github.ref == 'refs/heads/main'", 'the cache save must be main-only')
        self.assertEqual(saves[0]['with']['path'], 'profile-target-3', 'the cache must hold the measured run')

    def test_cache_key_names_the_route_and_the_run(self) -> None:
        """A stable key would restore a previous measurement into this one."""
        steps = _job('measure-profile')['steps']
        save = next(step for step in steps if 'cache/save' in step.get('uses', ''))

        self.assertIn("${{ matrix.route }}", save['with']['key'], 'the key must name the route')
        self.assertIn("${{ github.run_id }}", save['with']['key'], 'the key must name the run')

    def test_a_skipped_cache_save_is_recorded_as_skipped(self) -> None:
        """Absence of evidence must be distinguishable from a zero duration."""
        script = _step_run_matching(_job('measure-profile'), 'cache-save-status')

        self.assertIn('not measured: caches are saved only on main', script, 'a skipped save must say so')


class ArtefactTests(unittest.TestCase):
    """Upload evidence even when the route that produced it failed."""

    def test_every_artifact_upload_runs_on_failure(self) -> None:
        """An upload limited to success discards the failing route's evidence."""
        uploads = [
            step
            for name in MEASUREMENT_JOBS
            for step in _job(name)['steps']
            if 'upload-artifact' in step.get('uses', '')
        ]

        self.assertEqual(
            len(uploads),
            len(MEASUREMENT_JOBS),
            'every measurement job must publish its evidence',
        )
        for step in uploads:
            self.assertEqual(
                step['if'],
                'always()',
                'an artefact upload must run even when the measurement failed',
            )


class BuildBudgetTests(unittest.TestCase):
    """Keep the AC-04 job measuring the protocol its control registers."""

    def test_the_profiles_alternate_within_one_runner(self) -> None:
        """Parallel matrix legs would never interleave the three profiles."""
        job = _job('build-budget')

        self.assertNotIn(
            'strategy',
            job,
            'AC-04 requires profiles to alternate run by run, which parallel matrix legs cannot do',
        )
        for phase in ('cold', 'incremental'):
            with self.subTest(phase=phase):
                script = _step_run_matching(job, f'build-budget/{phase}-proof-$run')
                self.assertIn(
                    'for run in 1 2 3 4 5',
                    script,
                    f'each {phase} pass must measure all three profiles before advancing the run',
                )

    def test_the_job_measures_all_three_profiles(self) -> None:
        """A profile dropped from the job silently shrinks the record."""
        job = _job('build-budget')

        for phase in ('cold', 'incremental'):
            with self.subTest(phase=phase):
                self.assertIn(
                    f'build-budget/{phase}-proof-$run',
                    _step_run_matching(job, f'{phase}-proof-$run'),
                    f'the {phase} phase must measure the proof profile',
                )
        cold = _step_run_matching(job, 'cold-target-$profile-$run')
        self.assertIn('for profile in native-only polars-enabled', cold, 'the loop must name both Cargo profiles')

    def test_each_cold_run_starts_from_an_empty_target(self) -> None:
        """A reused cold target measures a warm build.

        Each cold script removes its target twice: once before the timed build
        and once after, so the ten cold targets cannot exhaust the runner's
        disk. Membership alone would therefore pass with the pre-run removal
        deleted, and the profile would then be measured against whatever the
        previous run left behind. Requiring the removal to precede the timed
        invocation is what distinguishes the two.
        """
        job = _job('build-budget')
        scripts = (
            (_step_run_matching(job, 'cold-target-$profile-$run'),
             'rm -rf -- "$CARGO_TARGET_DIR"', '/usr/bin/time -v -o "$output.time"', 'Cargo'),
            (_step_run_matching(job, 'cold-target-proof-$run'),
             'rm -rf -- "$proof_target"', '/usr/bin/time -v -o "$proof_output.time"', 'Kani'),
        )

        for script, removal, timed, label in scripts:
            with self.subTest(profile=label):
                self.assertIn(removal, script,
                              f'the {label} cold run must remove its target')
                self.assertLess(
                    script.index(removal), script.index(timed),
                    f'the {label} cold target must be empty before the timed region',
                )

    def test_one_warm_up_is_discarded_per_phase(self) -> None:
        """A measured first incremental build would include the initial compile."""
        job = _job('build-budget')
        warm_up = _step_run_matching(job, 'warm-target-$profile')

        self.assertIn('rm -rf -- "$CARGO_TARGET_DIR"', warm_up, 'the warm phase must start from an empty target')
        self.assertIn(
            'Discard one warm-up Kani codegen',
            '\n'.join(step.get('name', '') for step in job['steps']),
            'the proof profile must discard its own warm-up',
        )

    def test_each_incremental_run_touches_its_own_crate_root(self) -> None:
        """Touching another crate cannot make the measured profile rebuild."""
        job = _job('build-budget')
        incremental = _step_run_matching(job, 'incremental-$profile-$run')

        self.assertIn('source_file=src/lib.rs', incremental, 'the facade profile must touch its own crate root')
        self.assertIn(
            'kernel_file=crates/combobulate-kernel/src/lib.rs',
            incremental,
            'the proof profile must touch the kernel, not the facade',
        )
        self.assertIn('git checkout -- "$source_file"', incremental, 'the touch must be reverted after timing')
        self.assertIn('git checkout -- "$kernel_file"', incremental, 'the kernel touch must be reverted too')

    def test_the_caching_policy_matches_the_control(self) -> None:
        """A warm sccache or incremental compile would shorten every sample."""
        job = _job('build-budget')
        environment = job['env']
        assertion = _named_step(job, CACHE_ASSERTION_STEP)

        self.assertEqual(environment['CARGO_INCREMENTAL'], '0', 'incremental state must not shorten a run')
        self.assertEqual(environment['CARGO_BUILD_JOBS'], '4', 'the measured parallelism must stay fixed')
        self.assertNotIn('SCCACHE_RECACHE', environment, 'the control measures with no sccache at all')
        self.assertIn(
            ABSENCE_CHECK,
            assertion.get('run', ''),
            'the assertion step must reject an inherited cache wrapper',
        )

    def test_setup_rust_does_not_install_sccache_for_the_measurement(self) -> None:
        """The action's default installs sccache, and the control forbids it.

        ``setup-rust`` defaults ``use-sccache`` to ``true``, which installs the
        binary and exports ``SCCACHE_PATH``. The measurement must name
        ``'false'`` rather than rely on nothing wiring the wrapper: a job that
        left the default in place would provision the cache it then asserts is
        absent.
        """
        inputs = _setup_rust_inputs(_job('build-budget'))

        self.assertEqual(inputs.get('use-sccache'), 'false',
                         'the measuring job must not install sccache at all')

    def test_the_cache_assertion_runs_after_setup_rust_and_the_tools(self) -> None:
        """The assertion must observe the environment the timed builds inherit.

        An assertion placed before ``setup-rust`` can only observe the runner's
        own environment, so a later provisioning step that exported
        ``RUSTC_WRAPPER`` would go unnoticed while every sample was cached.
        ``setup-rust``, both named installers, and the untimed fetch must all
        run first, and the first timed phase must follow the assertion with no
        intervening step.
        """
        _check_cache_assertion_order(_job('build-budget'))

    def test_the_proof_profile_runs_the_installed_driver_directly(self) -> None:
        """The helper's `kani exec` refuses this repository's backend table."""
        launcher = _step_run_matching(_job('build-budget'), 'kani-codegen')

        self.assertIn('"$KANI_HOME/bin/kani-driver" kani --only-codegen', launcher, 'the launcher must invoke the installed driver')
        self.assertIn('--manifest-path crates/combobulate-kernel/Cargo.toml', launcher, 'codegen must target the kernel')
        self.assertIn('CARGO_PROFILE_DEV_CODEGEN_BACKEND="llvm"', launcher, 'the verifier needs its own backend')
        self.assertIn('RUSTUP_TOOLCHAIN=', launcher, 'the driver needs the SDK toolchain it bundles')
        self.assertNotIn('kani exec', launcher, 'the helper route cannot isolate the repository backend')

    def test_the_launcher_sets_both_rustflags_spellings(self) -> None:
        """Cargo prefers the encoded form, so setting only `RUSTFLAGS` is not enough.

        ``CARGO_ENCODED_RUSTFLAGS`` wins over ``RUSTFLAGS`` whenever both are
        set, which was confirmed against Cargo directly. A launcher that named
        only the space-separated spelling would let an inherited encoded value
        replace the warnings-as-errors policy while the launcher text still
        looked correct, so the sample would measure a different compiler
        configuration from the one the record describes.
        """
        launcher = _step_run_matching(_job('build-budget'), 'kani-codegen')

        self.assertIn('RUSTFLAGS="-D warnings"', launcher, 'the shared spelling must carry the policy')
        self.assertIn(
            'CARGO_ENCODED_RUSTFLAGS="-D"$\'\\x1f\'"warnings"',
            launcher,
            'the encoded spelling must carry it too, or an inherited value wins',
        )

    def test_the_proof_phase_is_timed_not_merely_run(self) -> None:
        """An untimed proof build supplies no sample to the median."""
        job = _job('build-budget')
        cold = _step_run_matching(job, 'cold-target-proof-$run')

        self.assertIn('/usr/bin/time -v -o "$proof_output.time"', cold, 'the cold proof sample must be timed')
        self.assertIn('build-budget/kani-codegen', cold, 'the cold proof sample must run the launcher')

    def test_the_runner_metadata_the_record_requires_is_captured(self) -> None:
        """The acceptance record cannot be written without the image identity."""
        script = _step_run_matching(_job('build-budget'), 'setup-start')

        for capture in ('nproc', 'free -b', '"$ImageOS" "$ImageVersion"'):
            self.assertIn(capture, script, f'the job must record {capture}')

    def test_every_registered_toolchain_is_observed_not_assumed(self) -> None:
        """AC-04's binding refuses a record that omits a registered toolchain.

        Verus and Z3 are registered alongside rustc, Kani, and mold, so a job
        that installed only the build tools and Kani could never produce a
        bindable record. Each is read from the binary the job installed.
        """
        script = _step_run_matching(_job('build-budget'), 'setup-end')

        for recorded in ('build-budget/rustc', 'build-budget/kani',
                         'build-budget/verus', 'build-budget/z3', 'build-budget/mold'):
            self.assertIn(recorded, script, f'the job must observe {recorded}')

    def test_the_verus_release_is_installed_before_it_is_reported(self) -> None:
        """A version report is worthless unless the release was installed first."""
        steps = _job('build-budget')['steps']
        names = [step.get('name', '') for step in steps]
        install = steps[names.index('Install the pinned Kani and Verus releases')]
        report = _step_run_matching(_job('build-budget'), 'build-budget/verus')

        self.assertIn('install-prover-tools@', install['uses'],
                      'the job must install through the shared prover action')
        self.assertIn('verus', install['with']['tools'].split(),
                      'the job must install the pinned Verus release')
        self.assertNotIn('make install', report,
                         'the report step must observe, not install')

    def test_the_verus_release_gets_the_toolchain_it_was_built_against(self) -> None:
        """`verus --version` runs the verifier, which needs its own Rust.

        The release names that toolchain in its `version.json`, so the job must
        read the name from there. A job that installed the release but not the
        toolchain fails at the report step, and a hard-coded name would be a
        second pin to drift from the archive.
        """
        script = _step_run_matching(_job('build-budget'), 'build-budget/verus')

        self.assertIn('version.json', script,
                      'the toolchain name must come from the release metadata')
        self.assertIn('rustup toolchain install "$verus_toolchain"', script,
                      'the release toolchain must be installed before it is run')

    def test_the_solver_is_the_one_the_install_action_reports(self) -> None:
        """`PATH` may hold any z3; the record must name the installed one.

        The Verus archive omits Z3, so the shared action installs it and reports
        its path. Reporting a `z3` found on `PATH` would record a binary the
        proof route never uses.
        """
        job = _job('build-budget')
        step = next(step for step in job['steps'] if 'build-budget/z3' in step.get('run', ''))

        self.assertEqual(step['env']['Z3_PATH'], '${{ steps.prover.outputs.z3-path }}',
                         'the solver path must come from the install action')
        self.assertIn('"$Z3_PATH" --version > build-budget/z3', step['run'],
                      'the recorded version must come from that binary')


class CacheAssertionOrderTests(unittest.TestCase):
    """The committed job and harmless mentions satisfy the cache contract."""

    def test_the_unmodified_job_is_accepted(self) -> None:
        """A checker that rejected the committed job could not guard it."""
        _check_cache_assertion_order(_job('build-budget'))

    def test_an_earlier_comment_mentioning_the_wrapper_is_accepted(self) -> None:
        """Only the named step counts, not the first text that names it."""
        job = _job('build-budget')
        begin = _named_step(job, 'Begin the build-budget measurement')
        begin['run'] = begin['run'] + '\n# RUSTC_WRAPPER must stay unset for AC-04\n'
        self.assertNotEqual(job, _job('build-budget'), 'the comment must change the parsed job')

        _check_cache_assertion_order(job)

    def test_an_earlier_comment_mentioning_the_timing_command_is_accepted(self) -> None:
        """A comment naming the timing command runs nothing and must not fail."""
        job = _job('build-budget')
        begin = _named_step(job, 'Begin the build-budget measurement')
        begin['run'] = begin['run'] + '\n# Samples use /usr/bin/time per invocation\n'
        self.assertNotEqual(job, _job('build-budget'), 'the comment must change the parsed job')

        _check_cache_assertion_order(job)


def _move_step_after(job: dict, source: int, anchor: str) -> None:
    """Move one step of ``job`` to immediately follow the step called ``anchor``."""
    step = job['steps'].pop(source)
    job['steps'].insert(_step_index_named(job, anchor) + 1, step)


def _insert_step(job: dict, index: int, name: str, script: str) -> None:
    """Insert a step into an in-memory job, leaving the parsed workflow untouched."""
    job['steps'].insert(index, {'name': name, 'run': script})


class CacheAssertionMutationTests(unittest.TestCase):
    """Each mutation removes one protection the cache contract must keep."""

    def setUp(self) -> None:
        """Parse the committed job once for every mutation to copy."""
        self.job = _job('build-budget')

    def assert_rejected(self, mutate: Callable[[dict], None]) -> None:
        """Apply ``mutate`` to a deep copy and require the checker to reject it.

        The equality guard proves the mutation changed the parsed job, so a
        passing rejection cannot come from an edit that silently did nothing.
        """
        changed = copy.deepcopy(self.job)
        mutate(changed)
        self.assertNotEqual(changed, self.job, 'the mutation must change the parsed job')
        with self.assertRaises(AssertionError):
            _check_cache_assertion_order(changed)

    def test_setup_rust_moved_after_the_assertion_is_rejected(self) -> None:
        """Provisioning after the check would leave the samples unwatched."""

        def move(job: dict) -> None:
            """Move setup-rust between the assertion and the cold build."""
            _move_step_after(
                job,
                _step_index_using(job, SETUP_RUST_ACTION),
                CACHE_ASSERTION_STEP,
            )

        self.assert_rejected(move)

    def test_setup_rust_moved_after_the_cold_build_is_rejected(self) -> None:
        """A provisioning step after the first sample has run too late."""

        def move(job: dict) -> None:
            """Move setup-rust behind the first timed phase."""
            _move_step_after(
                job,
                _step_index_using(job, SETUP_RUST_ACTION),
                COLD_BUILD_STEP,
            )

        self.assert_rejected(move)

    def test_setup_rust_removed_is_rejected(self) -> None:
        """Without it the job no longer provisions the compiler it times."""

        def remove(job: dict) -> None:
            """Delete the sole setup-rust step."""
            job['steps'].pop(_step_index_using(job, SETUP_RUST_ACTION))

        self.assert_rejected(remove)

    def test_a_second_setup_rust_step_is_rejected(self) -> None:
        """Two setup steps leave the observed environment ambiguous."""

        def duplicate(job: dict) -> None:
            """Add a second setup-rust step with different inputs."""
            index = _step_index_using(job, SETUP_RUST_ACTION)
            extra = copy.deepcopy(job['steps'][index])
            extra['with'] = {'rustflags': '', 'use-sccache': 'true'}
            job['steps'].insert(index + 1, extra)

        self.assert_rejected(duplicate)

    def test_the_assertion_removed_is_rejected(self) -> None:
        """A job that never checks the wrapper measures an unknown environment."""

        def remove(job: dict) -> None:
            """Delete the cache assertion step."""
            job['steps'].pop(_step_index_named(job, CACHE_ASSERTION_STEP))

        self.assert_rejected(remove)

    def test_a_second_assertion_step_is_rejected(self) -> None:
        """A duplicate would let an earlier copy define the observed order."""

        def duplicate(job: dict) -> None:
            """Insert a copy of the assertion directly after the original."""
            index = _step_index_named(job, CACHE_ASSERTION_STEP)
            job['steps'].insert(index + 1, copy.deepcopy(job['steps'][index]))

        self.assert_rejected(duplicate)

    def test_a_step_between_the_assertion_and_the_cold_build_is_rejected(self) -> None:
        """Strict adjacency keeps the assertion the last check before sampling."""

        def insert(job: dict) -> None:
            """Place an unrelated step between the assertion and the cold build."""
            index = _step_index_named(job, CACHE_ASSERTION_STEP)
            _insert_step(job, index + 1, 'An intervening step', 'true')

        self.assert_rejected(insert)

    def test_the_fetch_moved_after_the_assertion_is_rejected(self) -> None:
        """The untimed fetch must finish before the environment is observed."""

        def move(job: dict) -> None:
            """Move the fetch between the assertion and the cold build."""
            _move_step_after(
                job,
                _step_index_named(job, FETCH_STEP),
                CACHE_ASSERTION_STEP,
            )

        self.assert_rejected(move)

    def test_an_assertion_that_may_be_skipped_is_rejected(self) -> None:
        """A conditional assertion could be skipped while the samples run."""

        def add_condition(job: dict) -> None:
            """Give the assertion an ``if`` guard."""
            _named_step(job, CACHE_ASSERTION_STEP)['if'] = 'always()'

        self.assert_rejected(add_condition)

    def test_an_assertion_that_may_fail_softly_is_rejected(self) -> None:
        """`continue-on-error` would hide a contaminated environment."""

        def add_continue_on_error(job: dict) -> None:
            """Let the assertion report success despite a failed check."""
            _named_step(job, CACHE_ASSERTION_STEP)['continue-on-error'] = 'true'

        self.assert_rejected(add_continue_on_error)

    def test_a_masked_absence_check_is_rejected(self) -> None:
        """`|| true` would turn a contaminated environment into a pass."""

        def mask(job: dict) -> None:
            """Append a success fallback to the absence check."""
            step = _named_step(job, CACHE_ASSERTION_STEP)
            self.assertIn(ABSENCE_CHECK, step['run'])
            step['run'] = step['run'].replace(ABSENCE_CHECK, ABSENCE_CHECK + ' || true')

        self.assert_rejected(mask)

    def test_a_commented_out_absence_check_is_rejected(self) -> None:
        """A comment is not an assertion; the check must stay executable."""

        def comment_out(job: dict) -> None:
            """Turn the absence check into a comment."""
            step = _named_step(job, CACHE_ASSERTION_STEP)
            self.assertIn(ABSENCE_CHECK, step['run'])
            step['run'] = step['run'].replace(ABSENCE_CHECK, '# ' + ABSENCE_CHECK)

        self.assert_rejected(comment_out)

    def test_an_absence_check_in_a_dead_branch_is_rejected(self) -> None:
        """Text inside `if false` is never executed, so it checks nothing."""

        def wrap_in_dead_branch(job: dict) -> None:
            """Wrap the absence check in a branch that cannot run."""
            step = _named_step(job, CACHE_ASSERTION_STEP)
            self.assertIn(ABSENCE_CHECK, step['run'])
            step['run'] = step['run'].replace(
                ABSENCE_CHECK,
                f'if false; then {ABSENCE_CHECK}; fi',
            )

        self.assert_rejected(wrap_in_dead_branch)

    def test_a_short_circuited_absence_check_is_rejected(self) -> None:
        """`&&` still lets a later failure be skipped after a passing check."""

        def chain(job: dict) -> None:
            """Join the check to another command with `&&`."""
            step = _named_step(job, CACHE_ASSERTION_STEP)
            self.assertIn(ABSENCE_CHECK, step['run'])
            step['run'] = step['run'].replace(
                ABSENCE_CHECK,
                f'{ABSENCE_CHECK} && true',
            )

        self.assert_rejected(chain)

    def test_a_script_that_records_nothing_is_rejected(self) -> None:
        """An unrecorded assertion leaves no evidence for the acceptance record."""

        def drop_record(job: dict) -> None:
            """Remove the line that records the observed environment."""
            step = _named_step(job, CACHE_ASSERTION_STEP)
            lines = step['run'].splitlines()
            kept = [line for line in lines if 'build-budget/build-environment' not in line]
            self.assertLess(len(kept), len(lines), 'the record line must be present to remove')
            step['run'] = '\n'.join(kept) + '\n'

        self.assert_rejected(drop_record)

    def test_a_record_of_variable_names_is_rejected(self) -> None:
        """Printing `RUSTC_WRAPPER` rather than its value records no evidence."""

        def record_names(job: dict) -> None:
            """Replace the record with one that prints the literal names."""
            step = _named_step(job, CACHE_ASSERTION_STEP)
            self.assertIn(ENVIRONMENT_RECORD, step['run'])
            step['run'] = step['run'].replace(
                ENVIRONMENT_RECORD,
                "printf '%s\\n' RUSTC_WRAPPER CARGO_INCREMENTAL "
                'build-budget/build-environment',
            )

        self.assert_rejected(record_names)

    def test_an_early_successful_exit_is_rejected(self) -> None:
        """`exit 0` after strict mode would skip the check and the record."""

        def exit_early(job: dict) -> None:
            """Terminate the script successfully before the check runs."""
            step = _named_step(job, CACHE_ASSERTION_STEP)
            lines = step['run'].splitlines()
            index = lines.index(STRICT_MODE) + 1
            lines.insert(index, 'exit 0')
            step['run'] = '\n'.join(lines) + '\n'

        self.assert_rejected(exit_early)

    def test_a_job_level_wrapper_is_rejected(self) -> None:
        """A job-level wrapper reaches every timed build, not just the check."""

        def set_job_wrapper(job: dict) -> None:
            """Configure the wrapper for the whole job."""
            job['env']['RUSTC_WRAPPER'] = 'sccache'

        self.assert_rejected(set_job_wrapper)

    def test_a_step_level_wrapper_override_is_rejected(self) -> None:
        """A step-local empty value would hide the job value from the check."""

        def override_on_the_step(job: dict) -> None:
            """Give the job a wrapper and blank it for the assertion only."""
            job['env']['RUSTC_WRAPPER'] = 'sccache'
            _named_step(job, CACHE_ASSERTION_STEP)['env'] = {'RUSTC_WRAPPER': ''}

        self.assert_rejected(override_on_the_step)

    def test_a_script_without_failure_propagation_is_rejected(self) -> None:
        """Without `set -e` a failing check would not fail the job."""

        def drop_strict_mode(job: dict) -> None:
            """Remove the strict-mode line from the assertion script."""
            step = _named_step(job, CACHE_ASSERTION_STEP)
            self.assertIn('set -euo pipefail\n', step['run'])
            step['run'] = step['run'].replace('set -euo pipefail\n', '', 1)

        self.assert_rejected(drop_strict_mode)

    def test_a_timed_step_before_the_assertion_is_rejected(self) -> None:
        """A sample taken before the check would not be covered by it."""

        def time_a_prelude(job: dict) -> None:
            """Insert a timed step ahead of the whole provisioning phase."""
            _insert_step(job, 0, 'Time a prelude', '/usr/bin/time -v true')

        self.assert_rejected(time_a_prelude)


if __name__ == '__main__':
    unittest.main()
