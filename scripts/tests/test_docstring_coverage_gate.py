"""Exercise repository-wide Python source discovery for the docstring gate."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPOSITORY_ROOT / 'Makefile'
SOURCE_PATHS = (
    '.github/workflows/check.py',
    '.github/actions/validate/action.py',
    'scripts/check.py',
    'tests/check.py',
    'tools/check.py',
    'benchmarks/check.py',
    'scripts/types.pyi',
)


class DocstringCoverageGateTests(unittest.TestCase):
    """Verify Interrogate receives every repository Python source category."""

    def test_gate_passes_tracked_and_untracked_hidden_and_regular_sources(self) -> None:
        """Include workflow, action, tool, benchmark, and stub files in discovery."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._initialize_repository(root)
            invocation_log = root / 'uv-arguments.txt'
            uv = self._write_uv_stub(root)
            environment = os.environ | {'UV_INVOCATION_LOG': str(invocation_log)}

            result = subprocess.run(
                [
                    'make',
                    '-f',
                    str(MAKEFILE),
                    'docstring-coverage',
                    f'UV={uv}',
                ],
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            arguments = invocation_log.read_text().splitlines()
            self.assertEqual(arguments[:7], [
                'tool', 'run', '--python', '3.14', '--from',
                'interrogate==1.7.0', 'interrogate',
            ])
            self.assertIn('--fail-under', arguments)
            self.assertIn('100', arguments)
            discovered_paths = set(arguments[arguments.index('100') + 1:])
            self.assertEqual(
                discovered_paths,
                set(SOURCE_PATHS),
                'the gate must pass every tracked and untracked Python source',
            )

    def test_gate_fails_when_git_source_discovery_fails(self) -> None:
        """Reject a source-list failure instead of running with an empty list."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                ['make', '-f', str(MAKEFILE), 'check-python-sources'],
                cwd=temporary_directory,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(
                result.returncode,
                0,
                'source discovery outside a Git repository must fail closed',
            )
            self.assertIn(
                'failed while discovering Python sources',
                result.stderr,
            )

    def _initialize_repository(self, root: Path) -> None:
        """Create a temporary repository with tracked and untracked sources."""
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        for source_path in SOURCE_PATHS[:-1]:
            path = root / source_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('"""A fixture source for path discovery."""\n')
        stub_path = root / SOURCE_PATHS[-1]
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        stub_path.write_text('"""A fixture typing stub."""\n')
        subprocess.run(['git', 'add', *SOURCE_PATHS[:-1]], cwd=root, check=True)

    def _write_uv_stub(self, root: Path) -> Path:
        """Return a fake uv executable that records Interrogate's arguments."""
        executable = root / 'uv'
        executable.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$@" > "$UV_INVOCATION_LOG"\n'
        )
        executable.chmod(0o755)
        return executable


if __name__ == '__main__':
    unittest.main()
