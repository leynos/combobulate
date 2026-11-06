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

    def test_both_jobs_require_the_measurement_label(self) -> None:
        """Labelling a pull request for another reason must skip both jobs."""
        for name in ('measure-profile', 'verifier-free'):
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
            for name in ('measure-profile', 'verifier-free')
            for step in _job(name)['steps']
            if 'upload-artifact' in step.get('uses', '')
        ]

        self.assertEqual(len(uploads), 2, 'both jobs must publish their evidence')
        for step in uploads:
            self.assertEqual(
                step['if'],
                'always()',
                'an artefact upload must run even when the measurement failed',
            )


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
