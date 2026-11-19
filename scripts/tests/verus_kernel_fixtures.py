"""Load the kernel proof driver and its siblings without a solver or a helper.

The driver imports ``cyclopts``, ``captured_command`` and its three sibling
modules by bare name at module scope, so a test that wants to call one of its
rules has to satisfy every import at once. Doing that here rather than in each
suite keeps the stubbing in one place: a new module-scope import is one edit,
not one per test file.

Nothing in this module executes a proof. ``captured_command.run_captured`` is
stubbed with a callable that raises if used, so a test that accidentally
reaches the capture boundary fails loudly rather than running a verifier.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
RECORD = ROOT / 'tools/verifier-fixtures/verus-kernel/provenance.json'

# The exact summary the pinned positive root must print. It is one line, and
# the pattern that reads it is anchored to the end of the log, so a test that
# appends anything to it is testing the suffix rule rather than the count.
SUMMARY = 'verification results:: 19 verified, 0 errors\n'


class _Namespace:
    """Minimal attribute holder for one stubbed import."""

    def __init__(self, **attributes: object) -> None:
        """Expose each keyword as an attribute, so a stub can name what it fakes."""
        self.__dict__.update(attributes)


class _Cyclopts:
    """Cyclopts stand-in whose ``App`` accepts parameters and a default."""

    def App(self, **_: object) -> _Namespace:
        """Return an app whose ``default`` decorator is the identity."""
        return _Namespace(default=lambda function: function)

    @staticmethod
    def Parameter(**attributes: object) -> _Namespace:
        """Accept the environment-first annotations the driver declares."""
        return _Namespace(**attributes)


def load_driver() -> ModuleType:
    """Load ``verus_kernel.py`` with its solver and helper imports stubbed.

    The driver imports its siblings by bare name, so every stub is installed
    at once rather than one dependency at a time. Nothing here reaches a
    solver, a helper or the network.
    """
    stubs = {
        'cyclopts': _Cyclopts(),
        'captured_command': _Namespace(run_captured=_refuse_to_run),
    }
    with patch.dict('sys.modules', stubs):
        record = load('kernel_record', SCRIPTS / 'kernel_record.py')
        stubs['kernel_record'] = record
        verdicts = load_verdicts()
        stubs['verus_kernel_verdicts'] = verdicts
        stubs['verus_kernel_identity'] = load(
            'verus_kernel_identity', SCRIPTS / 'verus_kernel_identity.py'
        )
        return load('verus_kernel', SCRIPTS / 'verus_kernel.py')


def load_verdicts() -> ModuleType:
    """Load ``verus_kernel_verdicts.py``, which imports nothing but the stdlib."""
    return load('verus_kernel_verdicts', SCRIPTS / 'verus_kernel_verdicts.py')


def load(name: str, path: Path) -> ModuleType:
    """Execute ``path`` as ``name``, resolving imports from ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _refuse_to_run(*_args: object, **_kwargs: object) -> None:
    """Fail if a test reaches the capture boundary, which would run a solver."""
    raise AssertionError('a test must not execute a captured command')
