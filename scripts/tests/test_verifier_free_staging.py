"""Check the verifier-free workspace lifecycle and its staged-input binding.

These cases exercise the staging helpers directly with real filesystem
operations and no container, so a stale destination file, a refused removal,
or a mismatched staged tree is caught without podman.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verifier_probe_loader import load_verifier_free_probe


def _module():
    """Return the verifier-free module loaded with the probe helper stubbed.

    Examples
    --------
    The module is private to the probe scripts, so it is loaded by path::

        _module().STAGING_FILES  # ('.cargo/config.toml', ...)
    """
    return load_verifier_free_probe()


class WorkspaceGuardTests(unittest.TestCase):
    """Refuse to remove anything outside the directory the probe owns."""

    def test_a_symlinked_workspace_is_refused_and_its_target_survives(self) -> None:
        """Following the link would delete a directory the probe does not own."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory) / 'target'
            boundary.mkdir()
            target = boundary / 'real-workspace'
            target.mkdir()
            marker = target / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')
            link = boundary / 'workspace'
            link.symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, 'must not be a symbolic link'):
                module._recreate_workspace(link, boundary)

            self.assertTrue(marker.is_file(), 'the symlink target must remain untouched')
            self.assertTrue(link.is_symlink(), 'the refused link must remain in place')

    def test_a_workspace_outside_the_boundary_is_refused(self) -> None:
        """A mistaken path must not remove or create a sibling tree."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory) / 'target'
            boundary.mkdir()
            outside = Path(directory) / 'outside'

            with self.assertRaisesRegex(ValueError, 'must be strictly inside'):
                module._recreate_workspace(outside, boundary)

            self.assertFalse(outside.exists(), 'a refused workspace must not be created')

    def test_the_boundary_itself_is_refused(self) -> None:
        """Removing the boundary would take the whole owned tree with it."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory) / 'target'
            boundary.mkdir()
            marker = boundary / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'must be strictly inside'):
                module._recreate_workspace(boundary, boundary)

            self.assertTrue(marker.is_file(), 'the boundary must not be removed')

    def test_a_regular_file_at_the_workspace_path_is_refused(self) -> None:
        """A file where the workspace belongs is not a stale directory."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory) / 'target'
            boundary.mkdir()
            workspace = boundary / 'workspace'
            workspace.write_text('not a directory', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'must be a real directory'):
                module._recreate_workspace(workspace, boundary)

            self.assertTrue(workspace.is_file(), 'the refused file must remain')


class StagedInputsTests(unittest.TestCase):
    """Map, check, and digest the staged copies the record actually binds."""

    def test_fixture_and_pin_sources_map_to_their_staged_copies(self) -> None:
        """Keys stay repository-relative while values name the staged copy."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            workspace = boundary / 'workspace'
            module._stage_verifier_free_workspace(workspace, boundary=boundary)

            inputs = module.staged_inputs(workspace)

            self.assertEqual(
                inputs['tools/verifier-fixtures/verus-wiring-probe/Cargo.toml'],
                workspace / 'probe/Cargo.toml',
                'a fixture input must map under `probe/`',
            )
            self.assertEqual(
                inputs['rust-toolchain.toml'],
                workspace / 'rust-toolchain.toml',
                'a pinned repository input must keep its repository-relative path',
            )
            for key, staged in inputs.items():
                self.assertTrue(staged.is_file(), f'the staged copy of {key} must exist')
            module._verify_staged_workspace(workspace, inputs)

    def test_an_unknown_fixture_file_is_reported(self) -> None:
        """A staged file the record does not bind is a different build input."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            workspace = boundary / 'workspace'
            module._stage_verifier_free_workspace(workspace, boundary=boundary)
            inputs = module.staged_inputs(workspace)
            unknown = workspace / 'probe/unknown.toml'
            unknown.write_text('unknown = true', encoding='utf-8')

            with self.assertRaisesRegex(RuntimeError, r'extra=\[.*unknown\.toml'):
                module._verify_staged_workspace(workspace, inputs)

    def test_a_missing_staged_file_is_reported(self) -> None:
        """A digest for an absent file would bind nothing the build read."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            workspace = boundary / 'workspace'
            module._stage_verifier_free_workspace(workspace, boundary=boundary)
            inputs = module.staged_inputs(workspace)
            (workspace / 'probe/Cargo.toml').unlink()

            with self.assertRaisesRegex(RuntimeError, r'missing=\[.*Cargo\.toml'):
                module._verify_staged_workspace(workspace, inputs)


if __name__ == '__main__':
    unittest.main()