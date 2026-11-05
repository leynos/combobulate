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
    '_capture',
    '_digest',
    '_kani_environment',
    '_native_workspace',
    'portable_argument',
    '_require_command_statuses',
)


def _support_stub() -> SimpleNamespace:
    """Return the support attributes ``run_verifier_probes`` imports."""
    return SimpleNamespace(
        ROOT=ROOT,
        FIXTURES=ROOT / 'tools/verifier-fixtures',
        OUTPUT=ROOT,
        KANI_SDK_TOOLCHAIN='nightly-2025-11-21',
        **dict.fromkeys(SUPPORT_FUNCTIONS),
    )


def _load(name: str, path: Path, stubs: dict[str, object]) -> ModuleType:
    """Execute one module with ``stubs`` temporarily shadowing real imports."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


def _probe_dependencies(stubs: dict[str, object]) -> dict[str, object]:
    """Load the probe's private modules so the CLI's imports resolve."""
    provenance = _load('probe_provenance', SCRIPTS / 'probe_provenance.py', stubs)
    return {
        **stubs,
        'kani_probe': _load('kani_probe', SCRIPTS / 'kani_probe.py', stubs),
        'probe_provenance': provenance,
        'verifier_free_probe': _load(
            'verifier_free_probe', SCRIPTS / 'verifier_free_probe.py', stubs
        ),
        'verus_probe': _load(
            'verus_probe',
            SCRIPTS / 'verus_probe.py',
            {**stubs, 'probe_provenance': provenance},
        ),
    }


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
    return _load(
        'verifier_probe_cli',
        SCRIPTS / 'run_verifier_probes.py',
        _probe_dependencies(stubs),
    )


def load_verifier_free_probe() -> ModuleType:
    """Load ``verifier_free_probe.py`` without the prover helper."""
    stubs = {
        'rust_prover_tools': SimpleNamespace(),
        'rust_prover_tools.commands': SimpleNamespace(
            CommandSpec=lambda argv: argv, run_command=None
        ),
        'verifier_probe_support': _support_stub(),
    }
    return _load(
        'verifier_free_probe_under_test',
        SCRIPTS / 'verifier_free_probe.py',
        stubs,
    )


def load_kani_probe() -> ModuleType:
    """Load ``kani_probe.py`` with the real support helpers and no prover helper.

    The CLI imports the route builders by name, so it never exposes the module
    they came from. A suite that checks the builders loads them here instead of
    reaching through the CLI's namespace, and the real support module is used
    because ``kani_prefix`` calls ``_kani_environment`` rather than merely
    forwarding it.
    """
    support = load_verifier_probe_support()
    # `_kani_environment` verifies the selected SDK against the repository pin,
    # which would otherwise spawn the installed Kani driver. The version check
    # is covered by its own suite; here the route builders need only a support
    # module whose identity probe succeeds without a verifier installation.
    support.CommandSpec = lambda argv, **kwargs: argv
    support.run_command = lambda *args, **kwargs: SimpleNamespace(
        exit_code=0, stdout='', stderr=''
    )
    support.parse_tool_version = lambda *args, **kwargs: (
        ROOT / 'tools/kani/VERSION'
    ).read_text().strip()
    return _load(
        'kani_probe_under_test',
        SCRIPTS / 'kani_probe.py',
        {'verifier_probe_support': support},
    )


def load_probe_provenance() -> ModuleType:
    """Load ``probe_provenance.py`` with the real support helpers available."""
    stubs = {'verifier_probe_support': load_verifier_probe_support()}
    return _load('probe_provenance_under_test', SCRIPTS / 'probe_provenance.py', stubs)


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
