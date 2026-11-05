"""Guard pinned default solver selection without installing verifier tools.

Solver resolution has two injection points so this suite never runs ``uv`` and
never executes a solver: the pinned-distribution resolver, which is the one
command-side effect in the route, and the process execution that reads the
version banner. An explicit selection is resolved by name instead, and ``PATH``
is never consulted for the default.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from verifier_probe_loader import load_verifier_probes

PIN_FAILURE = 'the pinned z3-solver distribution could not be resolved'


def banner_response(module, exit_code: int = 0, stdout: str | None = None):
    """Return a prover-helper result reporting a solver banner.

    The helper returns a small result object rather than a completed process,
    so the stubs mirror that shape instead of imitating ``subprocess``.
    """
    return SimpleNamespace(
        exit_code=exit_code,
        stdout=module.Z3_VERSION_BANNER if stdout is None else stdout,
        stderr='',
    )


class SolverSelectionTests(unittest.TestCase):
    """Exercise the solver boundary with injected discovery and execution."""

    def test_failed_pin_resolution_does_not_fall_back_to_path(self) -> None:
        """A system solver must not be recorded as the calibrated distribution."""
        module = load_verifier_probes().verus_probe
        resolver = Mock(side_effect=RuntimeError(PIN_FAILURE))
        discover = Mock(return_value='/system/z3')
        execute = Mock(return_value=banner_response(module))

        with self.assertRaisesRegex(RuntimeError, 'could not be resolved'):
            module.resolve_z3(
                'z3', resolver=resolver, discovery=discover, execute=execute
            )

        discover.assert_not_called()
        execute.assert_not_called()

    def test_default_resolves_the_pin_and_explicit_selection_its_name(self) -> None:
        """A stale PATH solver must not displace the default pinned distribution."""
        module = load_verifier_probes().verus_probe
        cases = [
            ('z3', '/pinned/z3', 'resolver'),
            ('/explicit/z3', '/system/z3', 'discovery'),
        ]
        for selection, expected, route in cases:
            with self.subTest(selection=selection):
                resolver = Mock(return_value='/pinned/z3')
                discover = Mock(return_value='/system/z3')
                execute = Mock(return_value=banner_response(module, 1, 'incompatible'))

                with self.assertRaisesRegex(RuntimeError, 'calibrated Z3'):
                    module.resolve_z3(
                        selection,
                        resolver=resolver,
                        discovery=discover,
                        execute=execute,
                    )

                self.assertEqual(
                    (resolver if route == 'resolver' else discover).call_count,
                    1,
                    f'the {route} boundary must resolve {selection}',
                )
                self.assertEqual(
                    execute.call_args.args[0][0],
                    expected,
                    'the version check must run the path that route resolved',
                )

    def test_the_cli_route_selects_the_solver_it_was_given(self) -> None:
        """The CLI must hand its selection to the injected resolver boundary."""
        cli = load_verifier_probes()
        module = cli.verus_probe
        for selection in ('z3', '/explicit/z3'):
            with self.subTest(selection=selection):
                resolved = Mock(return_value=('/pinned/z3', module.Z3_VERSION_BANNER, None))
                with (
                    patch.object(module, 'resolve_z3', resolved),
                    patch.object(module, '_verus_environment', return_value={}),
                    patch.object(module, '_refresh_candidate_fingerprint'),
                    patch.object(module, '_verus_command', return_value=[]),
                    patch.object(module, '_qualified_candidates', return_value=[]),
                    patch.object(cli, '_capture', return_value={}),
                    patch.object(cli, '_write_verus_provenance'),
                ):
                    with self.assertRaisesRegex(RuntimeError, 'no Verus candidate'):
                        cli.verus(prover_tools='unused', z3=selection)
                resolved.assert_called_once_with(selection)

    def test_pinned_distribution_is_attributed_only_to_the_default_route(self) -> None:
        """The provenance must name the pin only when its resolver supplied it."""
        module = load_verifier_probes().verus_probe
        cases = [
            ('z3', module.Z3_DISTRIBUTION, '/pinned/z3'),
            ('/explicit/z3', None, '/system/z3'),
        ]
        for selection, expected_distribution, expected_path in cases:
            with self.subTest(selection=selection):
                path, checked_banner, distribution = module.resolve_z3(
                    selection,
                    resolver=Mock(return_value='/pinned/z3'),
                    discovery=Mock(return_value='/system/z3'),
                    execute=Mock(return_value=banner_response(module)),
                )

                self.assertEqual(
                    str(path),
                    expected_path,
                    'the selected executable must be the one the route resolved',
                )
                self.assertEqual(
                    checked_banner,
                    module.Z3_VERSION_BANNER,
                    'the checked banner must be returned to the record',
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

        module.resolve_z3(
            '/explicit/z3',
            resolver=resolver,
            discovery=Mock(return_value='/system/z3'),
            execute=Mock(return_value=banner_response(module)),
        )

        resolver.assert_not_called()

    def test_the_pinned_resolver_explains_its_own_failure(self) -> None:
        """The resolver's error names the distribution it could not select."""
        module = load_verifier_probes().verus_probe
        module.run_command = Mock(
            return_value=SimpleNamespace(
                exit_code=1, stdout='', stderr='no matching distribution'
            )
        )

        with patch.object(module.shutil, 'which', return_value='/system/z3') as discovered:
            with self.assertRaisesRegex(RuntimeError, 'no matching distribution'):
                module._pinned_solver_executable()

        discovered.assert_not_called()


if __name__ == '__main__':
    unittest.main()
