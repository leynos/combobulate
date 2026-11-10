"""Keep the hosted profile-measurement workflow wired to its accepted protocol.

The measurement numbers feed pre-registered acceptance controls, so a silent
edit to the trigger, the measured routes, the pinned tool versions, the
cold-run loop, the cache policy, or the artefact conditions would move the
evidence without anyone noticing. These checks read the workflow file as data
and assert each of those boundaries; they never start a runner.

Examples
--------
A route removed from the matrix fails this suite rather than shrinking the
recorded evidence::

    ROUTES  # ('rustdoc', 'clippy', 'whitaker', 'nextest', 'coverage', 'ui')
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/profile-measurements.yml'

ROUTES = ('rustdoc', 'clippy', 'whitaker', 'nextest', 'coverage', 'ui')
MEASUREMENT_JOBS = ('measure-profile', 'build-budget', 'verifier-free')
LABEL_GATE = "github.event.label.name == 'measure-profiles'"
DISPATCH_GATE = "github.event_name == 'workflow_dispatch'"


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


def _setup_rust_inputs(job: dict) -> dict[str, str]:
    """Return the ``with:`` inputs of one job's pinned ``setup-rust`` step.

    Raises
    ------
    AssertionError
        When the job has no ``setup-rust`` step.
    """
    for step in job['steps']:
        if 'shared-actions/.github/actions/setup-rust@' in step.get('uses', ''):
            return cast('dict', step.get('with', {}))
    raise AssertionError('the job has no setup-rust step')


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
        """The installer digest is not in the action manifest, so it is explicit."""
        steps = _job('measure-profile')['steps']
        installer = next(
            step for step in steps if 'install-whitaker' in step.get('uses', '')
        )

        self.assertEqual(installer['with']['installer-version'], '0.2.11', 'the installer version must stay pinned')
        self.assertEqual(
            installer['with']['installer-sha256'],
            'a32a665d01c4a2eb03a87c584d57329fc72a3aac421c8c2b15bbdb19e5410236',
            'the installer digest must stay pinned',
        )


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
        """A reused cold target measures a warm build."""
        job = _job('build-budget')
        cold = _step_run_matching(job, 'cold-target-$profile-$run')
        proof_cold = _step_run_matching(job, 'cold-target-proof-$run')

        for script, label in ((cold, 'Cargo'), (proof_cold, 'Kani')):
            self.assertIn(
                'rm -rf -- "$CARGO_TARGET_DIR"' if label == 'Cargo' else 'rm -rf -- "$proof_target"',
                script,
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
        environment = _job('build-budget')['env']

        self.assertEqual(environment['CARGO_INCREMENTAL'], '0', 'incremental state must not shorten a run')
        self.assertEqual(environment['CARGO_BUILD_JOBS'], '4', 'the measured parallelism must stay fixed')
        self.assertNotIn('SCCACHE_RECACHE', environment, 'the control measures with no sccache at all')
        self.assertIn(
            'test -z "${RUSTC_WRAPPER-}"',
            _step_run_matching(_job('build-budget'), 'RUSTC_WRAPPER'),
            'the job must reject an inherited cache wrapper',
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

    def test_the_cache_assertion_runs_after_the_tools_are_installed(self) -> None:
        """The assertion must observe the environment the timed builds inherit.

        An assertion placed before ``setup-rust`` can only observe the runner's
        own environment, so a later provisioning step that exported
        ``RUSTC_WRAPPER`` would go unnoticed while every sample was cached. The
        step that asserts and records belongs immediately before the first
        timed phase, with the tool installs between it and the top of the job.
        """
        steps = _job('build-budget')['steps']
        names = [step.get('name', '') for step in steps]
        assertion = next(index for index, step in enumerate(steps)
                         if 'RUSTC_WRAPPER' in step.get('run', ''))
        cold = names.index('Measure five cold builds per profile, alternating')

        self.assertLess(assertion, cold, 'the assertion must precede the first timed build')
        self.assertLess(cold - assertion, 2,
                        'only the fetch may sit between the assertion and the timed builds')
        for installed in ('Install the pinned build standard', 'Install the pinned Kani release'):
            self.assertLess(names.index(installed), assertion,
                            f'setup step {installed!r} must run before the assertion observes it')

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
        install = _step_run_matching(_job('build-budget'), 'install-verus')
        report = _step_run_matching(_job('build-budget'), 'build-budget/verus')

        self.assertIn('make install-verus', install,
                      'the job must install the pinned Verus release')
        self.assertNotIn('install-verus', report,
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

    def test_the_solver_is_taken_from_the_pinned_distribution(self) -> None:
        """`PATH` may hold any z3; the record must name the pinned one.

        The Verus archive omits Z3, so the probes resolve it from the
        `z3-solver` distribution. Reporting a `z3` found on `PATH` would record
        a binary the proof route never uses.
        """
        script = _step_run_matching(_job('build-budget'), 'build-budget/z3')

        self.assertIn('Z3_DISTRIBUTION', script,
                      'the solver pin must come from the repository record')
        self.assertIn('uv tool run --from "$z3_distribution"', script,
                      'the solver must be resolved through its pinned distribution')


class VerifierFreeJobTests(unittest.TestCase):
    """Keep the hosted verifier-free run free of the admission wrapper."""

    def test_the_job_refuses_a_host_compiler_wrapper(self) -> None:
        """A wrapper on the runner would compile outside the container namespace."""
        script = _step_run_matching(_job('verifier-free'), 'RUSTC_WRAPPER')

        self.assertIn('test -z "${RUSTC_WRAPPER-}"', script, 'the job must reject an inherited wrapper')

    def test_the_job_runs_the_recorded_probe_command(self) -> None:
        """The hosted route must be the same command documented for local use."""
        script = _step_run_matching(_job('verifier-free'), 'run_verifier_probes.py')

        self.assertIn(
            'uv run --script scripts/run_verifier_probes.py verifier-free',
            script,
            'the job must run the committed probe command',
        )


if __name__ == '__main__':
    unittest.main()
