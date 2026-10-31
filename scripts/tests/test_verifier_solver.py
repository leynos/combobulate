"""Guard pinned default solver selection without installing verifier tools."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


class SolverSelectionTests(unittest.TestCase):
    """Exercise the CLI's solver boundary with incompatible system discovery."""

    def test_default_uses_pin_while_explicit_selection_is_checked(self) -> None:
        """A stale PATH solver must not displace the default pinned distribution."""
        support = SimpleNamespace(
            ROOT=ROOT, FIXTURES=ROOT / 'tools/verifier-fixtures', OUTPUT=ROOT,
            **dict.fromkeys('capture digest kani_environment native_workspace require_command_statuses'.split()),
        )
        modules = {
            'cyclopts': SimpleNamespace(App=lambda: SimpleNamespace(command=lambda function: function)),
            'rust_prover_tools': SimpleNamespace(),
            'rust_prover_tools.commands': SimpleNamespace(CommandSpec=lambda argv: argv, run_command=None),
            'verifier_probe_support': support,
        }
        spec = importlib.util.spec_from_file_location('solver_probe', ROOT / 'scripts/run_verifier_probes.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', modules):
            spec.loader.exec_module(module)
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
