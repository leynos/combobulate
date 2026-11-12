"""Check the verifier-free workspace lifecycle and its staged-input binding.

These cases exercise the staging helpers directly with real filesystem
operations and no container, so a stale destination file, a refused removal,
a planted symbolic link, or a mismatched staged tree is caught without podman.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from verifier_probe_loader import load_verifier_free_probe


def _module() -> ModuleType:
    """Return the verifier-free module loaded with the probe helper stubbed.

    Examples
    --------
    The module is private to the probe scripts, so it is loaded by path::

        _module().STAGING_FILES  # ('.cargo/config.toml', ...)
    """
    return load_verifier_free_probe()


@contextmanager
def _boundary() -> Iterator[Path]:
    """Yield a temporary staging boundary with a nested workspace path.

    Both test runners collect these cases. Unittest discovery never passes
    pytest fixtures, so this shared setup is deliberately a context manager
    rather than a fixture: the documented exception to the fixture rule for
    unittest-compatible cases.

    Examples
    --------
    The caller adds the state each case needs::

        with _boundary() as boundary:
            workspace = boundary / 'workspace'
    """
    with tempfile.TemporaryDirectory() as directory:
        boundary = Path(directory) / 'target'
        boundary.mkdir()
        yield boundary


class WorkspaceGuardTests(unittest.TestCase):
    """Refuse to remove anything outside the directory the probe owns."""

    def test_a_symlinked_workspace_is_refused_and_its_target_survives(self) -> None:
        """Following the link would delete a directory the probe does not own."""
        module = _module()
        with _boundary() as boundary:
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

    def test_a_symlinked_boundary_is_refused_and_its_target_survives(self) -> None:
        """A linked boundary would resolve outside the repository."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'real-target'
            target.mkdir()
            marker = target / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')
            boundary = Path(directory) / 'target'
            boundary.symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, r'staging boundary .* must not be a symbolic link'):
                module._recreate_workspace(boundary / 'workspace', boundary)

            self.assertTrue(marker.is_file(), 'the symlink target must remain untouched')
            self.assertTrue(boundary.is_symlink(), 'the refused link must remain in place')

    def test_a_linked_intermediate_directory_is_refused_and_its_target_survives(self) -> None:
        """Resolving the path would remove the directory behind the link."""
        module = _module()
        with _boundary() as boundary:
            real = boundary / 'real'
            real.mkdir()
            marker = real / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')
            alias = boundary / 'alias'
            alias.symlink_to(real, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, 'must not be reached through symbolic links'):
                module._recreate_workspace(alias / 'workspace', boundary)

            self.assertTrue(marker.is_file(), 'the link target must remain untouched')
            self.assertFalse((real / 'workspace').exists(), 'no workspace may be created through a link')

    def test_a_parent_path_at_the_boundary_is_refused(self) -> None:
        """A ``..`` component must not resolve removal to the boundary parent."""
        module = _module()
        with _boundary() as boundary:
            marker = boundary.parent / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'must be strictly inside'):
                module._recreate_workspace(boundary / '..', boundary)

            self.assertTrue(marker.is_file(), 'the boundary parent must not be removed')

    def test_a_workspace_outside_the_boundary_is_refused(self) -> None:
        """A mistaken path must not remove or create a sibling tree."""
        module = _module()
        with _boundary() as boundary:
            outside = boundary.parent / 'outside'

            with self.assertRaisesRegex(ValueError, 'must be strictly inside'):
                module._recreate_workspace(outside, boundary)

            self.assertFalse(outside.exists(), 'a refused workspace must not be created')

    def test_the_boundary_itself_is_refused(self) -> None:
        """Removing the boundary would take the whole owned tree with it."""
        module = _module()
        with _boundary() as boundary:
            marker = boundary / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'must be strictly inside'):
                module._recreate_workspace(boundary, boundary)

            self.assertTrue(marker.is_file(), 'the boundary must not be removed')

    def test_a_regular_file_at_the_workspace_path_is_refused(self) -> None:
        """A file where the workspace belongs is not a stale directory."""
        module = _module()
        with _boundary() as boundary:
            workspace = boundary / 'workspace'
            workspace.write_text('not a directory', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'must be a real directory'):
                module._recreate_workspace(workspace, boundary)

            self.assertTrue(workspace.is_file(), 'the refused file must remain')


class SourceLinkTests(unittest.TestCase):
    """Refuse a repository source that copying would dereference."""

    def _relocated_module(self, boundary: Path) -> tuple[ModuleType, Path]:
        """Point the module at a temporary repository and return its fixture.

        The pins are created as empty files; only their paths matter here.

        Examples
        --------
        The caller adds the link under test::

            module, fixture = self._relocated_module(boundary)
        """
        module = _module()
        root = boundary.parent / 'repo'
        fixture = root / 'fixtures/verus-wiring-probe'
        fixture.mkdir(parents=True)
        for name in module.STAGING_FILES:
            pin = root / name
            pin.parent.mkdir(parents=True, exist_ok=True)
            pin.write_text('', encoding='utf-8')
        for name, value in (('ROOT', root), ('FIXTURES', root / 'fixtures')):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        return module, fixture

    def test_a_symbolic_link_among_the_sources_is_refused_before_staging(self) -> None:
        """copytree would turn the link into a regular staged file."""
        with _boundary() as boundary:
            module, fixture = self._relocated_module(boundary)
            outside = boundary.parent / 'outside.toml'
            outside.write_text('outside = true\n', encoding='utf-8')
            (fixture / 'Cargo.toml').symlink_to(outside)
            workspace = boundary / 'workspace'

            with self.assertRaisesRegex(ValueError, 'must not be symbolic links'):
                module._stage_verifier_free_workspace(workspace, boundary=boundary)

            self.assertFalse(workspace.exists(), 'a refused source set must not be staged')

    def test_a_symbolic_link_in_a_source_directory_is_refused(self) -> None:
        """A linked directory hides the link behind a regular leaf path."""
        with _boundary() as boundary:
            module, _ = self._relocated_module(boundary)
            real_cargo = boundary.parent / 'real-cargo'
            real_cargo.mkdir()
            (real_cargo / 'config.toml').write_text('outside = true\n', encoding='utf-8')
            cargo = module.ROOT / '.cargo'
            shutil.rmtree(cargo)
            cargo.symlink_to(real_cargo, target_is_directory=True)
            workspace = boundary / 'workspace'

            with self.assertRaisesRegex(ValueError, r'symbolic links: \[.*\.cargo'):
                module._stage_verifier_free_workspace(workspace, boundary=boundary)

            self.assertFalse(workspace.exists(), 'a refused source set must not be staged')

    def test_a_linked_directory_inside_the_fixture_is_refused(self) -> None:
        """copytree would copy the linked directory's external contents."""
        with _boundary() as boundary:
            module, fixture = self._relocated_module(boundary)
            external = boundary.parent / 'external'
            external.mkdir()
            (external / 'payload.toml').write_text('outside = true\n', encoding='utf-8')
            (fixture / 'nested').mkdir()
            (fixture / 'nested/linked').symlink_to(external, target_is_directory=True)
            workspace = boundary / 'workspace'

            with self.assertRaisesRegex(ValueError, r'symbolic links: \[.*linked'):
                module._stage_verifier_free_workspace(workspace, boundary=boundary)

            self.assertFalse(workspace.exists(), 'a refused source set must not be staged')


class StagedInputsTests(unittest.TestCase):
    """Map, check, and digest the staged copies the record actually binds."""

    def test_fixture_and_pin_sources_map_to_their_staged_copies(self) -> None:
        """Keys stay repository-relative while values name the staged copy."""
        module = _module()
        with _boundary() as boundary:
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
        with _boundary() as boundary:
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
        with _boundary() as boundary:
            workspace = boundary / 'workspace'
            module._stage_verifier_free_workspace(workspace, boundary=boundary)
            inputs = module.staged_inputs(workspace)
            (workspace / 'probe/Cargo.toml').unlink()

            with self.assertRaisesRegex(RuntimeError, r'missing=\[.*Cargo\.toml'):
                module._verify_staged_workspace(workspace, inputs)

    def test_a_symbolic_link_in_the_staged_tree_is_refused(self) -> None:
        """A link at an expected path would digest content from outside."""
        module = _module()
        with _boundary() as boundary:
            workspace = boundary / 'workspace'
            module._stage_verifier_free_workspace(workspace, boundary=boundary)
            inputs = module.staged_inputs(workspace)
            outside = boundary / 'outside.toml'
            outside.write_text('outside = true\n', encoding='utf-8')
            staged = workspace / 'probe/Cargo.toml'
            staged.unlink()
            staged.symlink_to(outside)

            with self.assertRaisesRegex(RuntimeError, r'symbolic links=\[.*Cargo\.toml'):
                module._verify_staged_workspace(workspace, inputs)

    def test_a_special_file_in_the_staged_tree_is_refused(self) -> None:
        """A pipe is neither a link nor a regular file, so no set would name it."""
        module = _module()
        with _boundary() as boundary:
            workspace = boundary / 'workspace'
            module._stage_verifier_free_workspace(workspace, boundary=boundary)
            inputs = module.staged_inputs(workspace)
            os.mkfifo(workspace / 'probe/fifo')

            with self.assertRaisesRegex(RuntimeError, r'irregular entries=\[.*fifo'):
                module._verify_staged_workspace(workspace, inputs)

    def test_a_symlinked_workspace_root_is_refused(self) -> None:
        """``rglob`` would enumerate a replacement link's target silently."""
        module = _module()
        with _boundary() as boundary:
            workspace = boundary / 'workspace'
            module._stage_verifier_free_workspace(workspace, boundary=boundary)
            inputs = module.staged_inputs(workspace)
            real = boundary / 'real-workspace'
            workspace.rename(real)
            workspace.symlink_to(real, target_is_directory=True)

            with self.assertRaisesRegex(RuntimeError, r'staged workspace .* must not be a symbolic link'):
                module._verify_staged_workspace(workspace, inputs)


if __name__ == '__main__':
    unittest.main()