"""Guard pinned default solver selection without installing verifier tools."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from verifier_probe_loader import load_verifier_probes


class SolverSelectionTests(unittest.TestCase):
    """Exercise the CLI's solver boundary with incompatible system discovery."""

    def test_failed_pin_resolution_does_not_fall_back_to_path(self) -> None:
        """A system solver must not be recorded as the calibrated distribution."""
        module = load_verifier_probes()
        module.run_command = Mock(side_effect=[
            SimpleNamespace(
                exit_code=1, stdout='', stderr='no matching distribution'
            ),
            SimpleNamespace(exit_code=0, stdout=module.Z3_VERSION_BANNER, stderr=''),
        ])

        with patch.object(module.shutil, 'which', return_value='/system/z3'):
            with self.assertRaisesRegex(RuntimeError, 'could not be resolved'):
                module.resolve_z3('z3')

        self.assertEqual(
            module.run_command.call_count,
            1,
            'a failed resolver must not go on to check the PATH solver',
        )

    def test_default_uses_pin_while_explicit_selection_is_checked(self) -> None:
        """A stale PATH solver must not displace the default pinned distribution."""
        module = load_verifier_probes()
        for selection, expected in [('z3', 'uv'), ('/explicit/z3', '/system/z3')]:
            with self.subTest(selection=selection):
                module.run_command = Mock(side_effect=[
                    SimpleNamespace(exit_code=0, stdout='/pinned/z3'),
                    SimpleNamespace(exit_code=1, stdout='incompatible solver'),
                ])
                with patch.object(module.shutil, 'which', return_value='/system/z3') as discovered:
                    with self.assertRaisesRegex(RuntimeError, 'calibrated Z3'):
                        module.verus(prover_tools='unused', z3=selection)
                discovered.assert_called_once_with(selection)
                arguments = module.run_command.call_args_list[0].args[0]
                self.assertEqual(arguments[0], expected, 'default selection must resolve the pinned tool first')
                if selection == 'z3':
                    self.assertIn('z3-solver==4.16.0.0', arguments, 'the resolver must select the calibrated package')