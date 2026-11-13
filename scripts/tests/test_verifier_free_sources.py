"""Bind the verifier-free staged source set to the repository files it names.

The source list decides which files the staging step copies and which digests
the record carries, so a misspelt path or an accidentally included evidence
record would weaken that binding. These checks read the real repository tree,
without staging or a container.

Examples
--------
The staged set is derived from the fixture tree rather than listed twice::

    [path.name for path in staged_sources() if path.name == 'Cargo.toml']
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import ModuleType

from verifier_probe_loader import load_verifier_free_probe

FIXTURES = Path(__file__).resolve().parents[2] / 'tools/verifier-fixtures'


def _module() -> ModuleType:
    """Return the verifier-free module loaded with the probe helper stubbed.

    Examples
    --------
    The module is private to the probe scripts, so it is loaded by path::

        _module().STAGING_FILES  # ('.cargo/config.toml', ...)
    """
    return load_verifier_free_probe()


class StagedSourcesTests(unittest.TestCase):
    """Bind the observation to exactly the files the build consumes."""

    def test_every_staged_file_is_a_real_repository_path(self) -> None:
        """A misspelt path would digest nothing and bind nothing."""
        module = _module()

        missing = [str(path) for path in module.staged_sources() if not path.is_file()]

        self.assertEqual(missing, [], 'every staged source must exist in the repository')

    def test_evidence_records_are_excluded_from_the_staged_set(self) -> None:
        """A record that hashed itself could never be committed."""
        module = _module()
        names = {path.name for path in module.staged_sources()}

        for ignored in ('provenance.json', 'verifier-free.json', 'verifier-free-hosted.json'):
            self.assertNotIn(ignored, names, f'{ignored} must not be staged')

    def test_build_output_is_excluded_from_the_staged_set(self) -> None:
        """A Cargo target directory is output, not a build input."""
        module = _module()

        staged = module.staged_sources()

        self.assertFalse(
            any(
                'target' in path.relative_to(FIXTURES / 'verus-wiring-probe').parts
                for path in staged
                if path.is_relative_to(FIXTURES)
            ),
            'build output must stay out of the staged set',
        )

    def test_root_toolchain_and_linker_pins_are_staged(self) -> None:
        """The container build must use the same compiler and linker as the host."""
        module = _module()
        staged = module.staged_sources()

        for name in module.STAGING_FILES:
            self.assertIn(
                Path(module.ROOT) / name,
                staged,
                f'the pinned {name} must be staged beside the fixture',
            )


if __name__ == '__main__':
    unittest.main()