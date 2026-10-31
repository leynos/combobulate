"""Guard the verifier-free image recipe against a missing mold runtime library."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class VerifierFreeContainerTests(unittest.TestCase):
    """Check the container recipe can run the pinned mold linker."""

    def test_containerfile_installs_the_pinned_mold_runtime_library(self) -> None:
        """Clang pulls in no libatomic, so the recipe must name it explicitly."""
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
        spec = importlib.util.spec_from_file_location('container_probe', ROOT / 'scripts/run_verifier_probes.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', modules):
            spec.loader.exec_module(module)

        recipe = module.verifier_free_containerfile()

        self.assertTrue(recipe.startswith('FROM quay.io/rockylinux/'), 'the recipe must start from the pinned base image')
        self.assertIn('clang gcc-c++ make libatomic', recipe, 'the recipe must install mold\'s runtime library')