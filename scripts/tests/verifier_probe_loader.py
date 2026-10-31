"""Load verifier probe modules with their external dependencies stubbed.

Only the verifier test modules use this loader. It keeps one definition of the
Cyclopts, prover-helper, and support stubs so the suites cannot drift apart,
and it never imports the real helper or installs a verifier.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
SUPPORT_FUNCTIONS = (
    'capture',
    'digest',
    'kani_environment',
    'native_workspace',
    'require_command_statuses',
)


def _support_stub() -> SimpleNamespace:
    """Return the support attributes ``run_verifier_probes`` imports."""
    return SimpleNamespace(
        ROOT=ROOT,
        FIXTURES=ROOT / 'tools/verifier-fixtures',
        OUTPUT=ROOT,
        **dict.fromkeys(SUPPORT_FUNCTIONS),
    )


def _load(name: str, path: Path, stubs: dict[str, object]) -> ModuleType:
    """Execute one module with ``stubs`` temporarily shadowing real imports."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


def load_verifier_probes() -> ModuleType:
    """Load ``run_verifier_probes.py`` without Cyclopts or the prover helper."""
    stubs = {
        'cyclopts': SimpleNamespace(
            App=lambda: SimpleNamespace(command=lambda function: function)
        ),
        'rust_prover_tools': SimpleNamespace(),
        'rust_prover_tools.commands': SimpleNamespace(
            CommandSpec=lambda argv: argv, run_command=None
        ),
        'verifier_probe_support': _support_stub(),
    }
    return _load('verifier_probe_cli', SCRIPTS / 'run_verifier_probes.py', stubs)


def load_verifier_probe_support() -> ModuleType:
    """Load ``verifier_probe_support.py`` without the prover helper."""
    stubs = {
        'rust_prover_tools': SimpleNamespace(),
        'rust_prover_tools.commands': SimpleNamespace(
            CommandSpec=lambda argv: argv, run_command=None
        ),
        'rust_prover_tools.versions': SimpleNamespace(
            parse_tool_version=lambda *args, **kwargs: None
        ),
    }
    return _load(
        'verifier_probe_support_under_test',
        SCRIPTS / 'verifier_probe_support.py',
        stubs,
    )