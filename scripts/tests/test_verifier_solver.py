"""Guard pinned default solver selection without installing verifier tools.

Solver resolution is split so its side effects sit at the command boundary:
``select_solver`` chooses an executable from the selection policy and never
runs one, and ``qualify_solver`` validates a version invocation whose status
and output the caller observed. ``_pinned_solver_executable`` is the one
resolver that may consult a package index and write to uv's cache, so it is a
required parameter rather than a default, and an explicit selection never
reaches it.
"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from verifier_probe_loader import load_verifier_probes

PIN_FAILURE = 'the pinned z3-solver distribution could not be resolved'


def solver_result(module, exit_code: int = 0, stdout: str = '', stderr: str = ''):
    """Return a prover-helper result reporting a solver invocation.

    The helper returns a small result object rather than a completed process,
    so the stubs mirror that shape instead of imitating ``subprocess``. A
    module supplies the calibrated banner as the reported stdout by default.
    """
    return SimpleNamespace(
        exit_code=exit_code,
        stdout=module.Z3_VERSION_BANNER if not stdout else stdout,
        stderr=stderr,
    )


class SolverSelectionTests(unittest.TestCase):
    """Exercise the selection policy without running a resolver or a solver."""

    def test_failed_pin_resolution_does_not_fall_back_to_path(self) -> None:
        """A system solver must not be recorded as the calibrated distribution."""
        module = load_verifier_probes().verus_probe
        resolver = Mock(side_effect=RuntimeError(PIN_FAILURE))
        discover = Mock(return_value='/system/z3')

        with self.assertRaisesRegex(RuntimeError, 'could not be resolved'):
            module.select_solver('z3', pinned=resolver, discovery=discover)

        discover.assert_not_called()

    def test_the_route_chooses_the_resolver_the_selection_names(self) -> None:
        """A stale PATH solver must not displace the default pinned distribution."""
        module = load_verifier_probes().verus_probe
        cases = [
            ('z3', '/pinned/z3', 'pinned'),
            ('/explicit/z3', '/system/z3', 'discovery'),
        ]
        for selection, expected, route in cases:
            with self.subTest(selection=selection):
                resolver = Mock(return_value='/pinned/z3')
                discover = Mock(return_value='/system/z3')

                path, _ = module.select_solver(
                    selection, pinned=resolver, discovery=discover
                )

                self.assertEqual(
                    (resolver if route == 'pinned' else discover).call_count,
                    1,
                    f'the {route} boundary must resolve {selection}',
                )
                self.assertEqual(
                    str(path),
                    expected,
                    'the selected executable must be the one that route resolved',
                )

    def test_pinned_distribution_is_attributed_only_to_the_default_route(self) -> None:
        """The provenance must name the pin only when its resolver supplied it."""
        module = load_verifier_probes().verus_probe
        cases = [
            ('z3', module.Z3_DISTRIBUTION, '/pinned/z3'),
            ('/explicit/z3', None, '/system/z3'),
        ]
        for selection, expected_distribution, expected_path in cases:
            with self.subTest(selection=selection):
                path, distribution = module.select_solver(
                    selection,
                    pinned=Mock(return_value='/pinned/z3'),
                    discovery=Mock(return_value='/system/z3'),
                )

                self.assertEqual(
                    str(path),
                    expected_path,
                    'the selected executable must be the one the route resolved',
                )
                self.assertEqual(
                    distribution,
                    expected_distribution,
                    'only the pinned resolver may be attributed to the distribution',
                )

    def test_an_explicit_selection_never_runs_the_pinned_resolver(self) -> None:
        """The package-unpacking route is a side effect only the default may use."""
        module = load_verifier_probes().verus_probe
        resolver = Mock(return_value='/pinned/z3')

        module.select_solver(
            '/explicit/z3',
            pinned=resolver,
            discovery=Mock(return_value='/system/z3'),
        )

        resolver.assert_not_called()

    def test_an_unresolved_selection_is_a_named_failure(self) -> None:
        """A selection that finds nothing must fail, not fall through."""
        module = load_verifier_probes().verus_probe

        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            module.select_solver(
                'z3', pinned=Mock(return_value=None), discovery=Mock(return_value=None)
            )

    def test_the_pinned_resolver_explains_its_own_failure(self) -> None:
        """The resolver's error names the distribution it could not select."""
        module = load_verifier_probes().verus_probe
        module.run_command = Mock(
            return_value=solver_result(module, exit_code=1, stderr='no matching distribution')
        )

        with patch.object(module.shutil, 'which', return_value='/system/z3') as discovered:
            with self.assertRaisesRegex(RuntimeError, 'no matching distribution'):
                module._pinned_solver_executable()

        discovered.assert_not_called()


class SolverQualificationTests(unittest.TestCase):
    """Exercise banner validation over an already-observed invocation."""

    def test_a_calibrated_banner_is_returned_with_its_source(self) -> None:
        """Qualification must pass the observed banner and attribution through."""
        module = load_verifier_probes().verus_probe

        path, banner, distribution = module.qualify_solver(
            Path('/pinned/z3'),
            exit_code=0,
            reported=module.Z3_VERSION_BANNER,
            distribution=module.Z3_DISTRIBUTION,
        )

        self.assertEqual(
            (str(path), banner, distribution),
            ('/pinned/z3', module.Z3_VERSION_BANNER, module.Z3_DISTRIBUTION),
            'the record must name the checked banner and the pin that supplied it',
        )

    def test_an_uncalibrated_solver_is_rejected(self) -> None:
        """A solver that does not report the calibrated release must not pass."""
        module = load_verifier_probes().verus_probe
        cases = [
            (1, module.Z3_VERSION_BANNER, 'a failed version check'),
            (0, 'Z3 version 4.15.0 - 64 bit', 'a different release'),
        ]
        for exit_code, reported, description in cases:
            with self.subTest(description):
                with self.assertRaisesRegex(RuntimeError, 'calibrated Z3'):
                    module.qualify_solver(
                        Path('/pinned/z3'),
                        exit_code=exit_code,
                        reported=reported,
                        distribution=None,
                    )

    def test_qualification_starts_no_process(self) -> None:
        """The command boundary observes; this step must not reach for a runner."""
        module = load_verifier_probes().verus_probe
        module.run_command = Mock(side_effect=AssertionError('must not execute'))

        module.qualify_solver(
            Path('/pinned/z3'),
            exit_code=0,
            reported=module.Z3_VERSION_BANNER,
            distribution=None,
        )


class CliSolverBoundaryTests(unittest.TestCase):
    """Require the CLI to observe the solver it selected."""

    def test_the_cli_selects_and_observes_the_solver_it_was_given(self) -> None:
        """The CLI must hand its selection to the policy and run what it chose."""
        cli = load_verifier_probes()
        module = cli.verus_probe
        cases = ('z3', '/explicit/z3')
        for selection in cases:
            with self.subTest(selection=selection):
                selected = Mock(
                    return_value=(Path('/pinned/z3'), module.Z3_DISTRIBUTION)
                )
                observed = Mock(return_value=solver_result(module))
                with (
                    patch.object(module, 'select_solver', selected),
                    patch.object(cli, 'run_command', observed),
                    patch.object(module, '_verus_environment', return_value={}),
                    patch.object(module, '_refresh_candidate_fingerprint'),
                    patch.object(module, '_verus_command', return_value=[]),
                    patch.object(module, '_qualified_candidates', return_value=[]),
                    patch.object(cli, '_capture', return_value={}),
                    patch.object(cli, '_write_verus_provenance'),
                ):
                    with self.assertRaisesRegex(RuntimeError, 'no Verus candidate'):
                        cli.verus(prover_tools='unused', z3=selection)

                self.assertEqual(
                    selected.call_args.args,
                    (selection,),
                    'the CLI must pass its selection to the policy',
                )
                self.assertEqual(
                    observed.call_args.args[0][0],
                    '/pinned/z3',
                    'the CLI must run the executable the policy selected',
                )


if __name__ == '__main__':
    unittest.main()
