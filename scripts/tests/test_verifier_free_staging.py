"""Check the verifier-free workspace lifecycle and its staged-input binding.

These cases exercise the staging helpers with real filesystem operations and
no container, so a stale destination file, a refused removal, a planted
symbolic link, or a mismatched staged tree is caught without podman.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
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

    Unittest discovery never passes pytest fixtures, so this shared setup is a
    context manager: the documented exception to the fixture rule.

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


@dataclass(frozen=True)
class _GuardCase:
    """One workspace path the guard must refuse and what it must leave behind.

    Examples
    --------
    A linked workspace keeps both the link and its target::

        _GuardCase('must not be a symbolic link', link, boundary, present=(marker, link))
    """

    pattern: str
    path: Path
    boundary: Path
    present: tuple[Path, ...] = ()
    absent: tuple[Path, ...] = ()


class WorkspaceGuardTests(unittest.TestCase):
    """Refuse to remove anything outside the directory the probe owns."""

    def _assert_workspace_refused(self, case: _GuardCase) -> None:
        """Assert the case is refused and its evidence is left as it was.

        Examples
        --------
        A refused link keeps both its target and itself::

            self._assert_workspace_refused(
                _GuardCase(PATTERN, link, boundary, present=(link,))
            )
        """
        with self.assertRaisesRegex(ValueError, case.pattern):
            _module()._recreate_workspace(case.path, case.boundary)
        for survivor in case.present:
            self.assertTrue(survivor.exists(), f'{survivor} must remain untouched')
        for missing in case.absent:
            self.assertFalse(missing.exists(), f'{missing} must not be created')

    def test_a_symlinked_workspace_is_refused_and_its_target_survives(self) -> None:
        """Following the link would delete a directory the probe does not own."""
        with _boundary() as boundary:
            target = boundary / 'real-workspace'
            target.mkdir()
            marker = target / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')
            link = boundary / 'workspace'
            link.symlink_to(target, target_is_directory=True)

            self._assert_workspace_refused(
                _GuardCase('must not be a symbolic link', link, boundary, present=(marker, link))
            )

    def test_a_symlinked_boundary_is_refused_and_its_target_survives(self) -> None:
        """A linked boundary would resolve outside the repository."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'real-target'
            target.mkdir()
            marker = target / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')
            boundary = Path(directory) / 'target'
            boundary.symlink_to(target, target_is_directory=True)

            self._assert_workspace_refused(
                _GuardCase(
                    r'staging boundary .* must not be a symbolic link',
                    boundary / 'workspace',
                    boundary,
                    present=(marker, boundary),
                )
            )

    def test_a_linked_intermediate_directory_is_refused_and_its_target_survives(self) -> None:
        """Resolving the path would remove the directory behind the link."""
        with _boundary() as boundary:
            real = boundary / 'real'
            real.mkdir()
            marker = real / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')
            alias = boundary / 'alias'
            alias.symlink_to(real, target_is_directory=True)

            self._assert_workspace_refused(
                _GuardCase(
                    'must not be reached through symbolic links',
                    alias / 'workspace',
                    boundary,
                    present=(marker,),
                    absent=(real / 'workspace',),
                )
            )

    def test_a_parent_path_at_the_boundary_is_refused(self) -> None:
        """A ``..`` component must not resolve removal to the boundary parent."""
        with _boundary() as boundary:
            marker = boundary.parent / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')

            self._assert_workspace_refused(
                _GuardCase(
                    'must be strictly inside',
                    boundary / '..',
                    boundary,
                    present=(marker,),
                )
            )

    def test_a_workspace_outside_the_boundary_is_refused(self) -> None:
        """A mistaken path must not remove or create a sibling tree."""
        with _boundary() as boundary:
            outside = boundary.parent / 'outside'

            self._assert_workspace_refused(
                _GuardCase(
                    'must be strictly inside', outside, boundary, absent=(outside,)
                )
            )

    def test_the_boundary_itself_is_refused(self) -> None:
        """Removing the boundary would take the whole owned tree with it."""
        with _boundary() as boundary:
            marker = boundary / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')

            self._assert_workspace_refused(
                _GuardCase(
                    'must be strictly inside', boundary, boundary, present=(marker,)
                )
            )

    def test_a_regular_file_at_the_workspace_path_is_refused(self) -> None:
        """A file where the workspace belongs is not a stale directory."""
        with _boundary() as boundary:
            workspace = boundary / 'workspace'
            workspace.write_text('not a directory', encoding='utf-8')

            self._assert_workspace_refused(
                _GuardCase(
                    'must be a real directory',
                    workspace,
                    boundary,
                    present=(workspace,),
                )
            )


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

    def _assert_staging_refused(
        self,
        pattern: str,
        plant_link: Callable[[ModuleType, Path], None],
    ) -> None:
        """Plant a link, then assert staging is refused before it starts.

        Examples
        --------
        The callback receives the relocated module and its fixture::

            self._assert_staging_refused('must not be symbolic links', _link_cargo)
        """
        with _boundary() as boundary:
            module, fixture = self._relocated_module(boundary)
            plant_link(module, fixture)
            workspace = boundary / 'workspace'

            with self.assertRaisesRegex(ValueError, pattern):
                module._stage_verifier_free_workspace(workspace, boundary=boundary)

            self.assertFalse(workspace.exists(), 'a refused source set must not be staged')

    def test_a_symbolic_link_among_the_sources_is_refused_before_staging(self) -> None:
        """copytree would turn the link into a regular staged file."""

        def link_a_source(module: ModuleType, fixture: Path) -> None:
            """Point the fixture manifest at a file outside the repository."""
            outside = module.ROOT.parent / 'outside.toml'
            outside.write_text('outside = true\n', encoding='utf-8')
            (fixture / 'Cargo.toml').symlink_to(outside)

        self._assert_staging_refused('must not be symbolic links', link_a_source)

    def test_a_symbolic_link_in_a_source_directory_is_refused(self) -> None:
        """A linked directory hides the link behind a regular leaf path."""

        def link_the_cargo_directory(module: ModuleType, _: Path) -> None:
            """Replace the pinned `.cargo` directory with a link outside it."""
            real_cargo = module.ROOT.parent / 'real-cargo'
            real_cargo.mkdir()
            (real_cargo / 'config.toml').write_text('outside = true\n', encoding='utf-8')
            cargo = module.ROOT / '.cargo'
            shutil.rmtree(cargo)
            cargo.symlink_to(real_cargo, target_is_directory=True)

        self._assert_staging_refused(r'symbolic links: \[.*\.cargo', link_the_cargo_directory)

    def test_a_linked_directory_inside_the_fixture_is_refused(self) -> None:
        """copytree would copy the linked directory's external contents."""

        def link_a_fixture_directory(module: ModuleType, fixture: Path) -> None:
            """Nest a link to outside content inside the fixture."""
            external = module.ROOT.parent / 'external'
            external.mkdir()
            (external / 'payload.toml').write_text('outside = true\n', encoding='utf-8')
            nested = fixture / 'nested'
            nested.mkdir()
            (nested / 'linked').symlink_to(external, target_is_directory=True)

        self._assert_staging_refused(r'symbolic links: \[.*linked', link_a_fixture_directory)


def _staged(boundary: Path) -> tuple[ModuleType, Path, dict[str, Path]]:
    """Stage the fixture into ``boundary`` and return module, tree, and inputs.

    Examples
    --------
    The caller tampers with the returned workspace::

        module, workspace, inputs = _staged(boundary)
    """
    module = _module()
    workspace = boundary / 'workspace'
    module._stage_verifier_free_workspace(workspace, boundary=boundary)
    return module, workspace, module.staged_inputs(workspace)


class StagedInputsTests(unittest.TestCase):
    """Map, check, and digest the staged copies the record actually binds."""

    def _assert_drift(
        self, pattern: str, tamper: Callable[[Path, Path], None]
    ) -> None:
        """Tamper with a staged tree and assert the drift is named.

        Examples
        --------
        The callback receives the workspace and its boundary::

            self._assert_drift(r'extra=\\[.*unknown', add_unknown_file)
        """
        with _boundary() as boundary:
            module, workspace, inputs = _staged(boundary)
            tamper(workspace, boundary)

            with self.assertRaisesRegex(RuntimeError, pattern):
                module._verify_staged_workspace(workspace, inputs)

    def test_fixture_and_pin_sources_map_to_their_staged_copies(self) -> None:
        """Keys stay repository-relative while values name the staged copy."""
        with _boundary() as boundary:
            module, workspace, inputs = _staged(boundary)

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

        def add_unknown_file(workspace: Path, _: Path) -> None:
            """Add a staged file the record does not bind."""
            unknown = workspace / 'probe/unknown.toml'
            unknown.write_text('unknown = true', encoding='utf-8')

        self._assert_drift(r'extra=\[.*unknown\.toml', add_unknown_file)

    def test_a_missing_staged_file_is_reported(self) -> None:
        """A digest for an absent file would bind nothing the build read."""
        self._assert_drift(
            r'missing=\[.*Cargo\.toml',
            lambda workspace, _: (workspace / 'probe/Cargo.toml').unlink(),
        )

    def test_a_symbolic_link_in_the_staged_tree_is_refused(self) -> None:
        """A link at an expected path would digest content from outside."""

        def link_a_staged_file(workspace: Path, boundary: Path) -> None:
            """Replace a staged input with a link to outside content."""
            outside = boundary / 'outside.toml'
            outside.write_text('outside = true\n', encoding='utf-8')
            staged = workspace / 'probe/Cargo.toml'
            staged.unlink()
            staged.symlink_to(outside)

        self._assert_drift(r'symbolic links=\[.*Cargo\.toml', link_a_staged_file)

    def test_a_special_file_in_the_staged_tree_is_refused(self) -> None:
        """A pipe is neither a link nor a regular file, so no set would name it."""
        self._assert_drift(
            r'irregular entries=\[.*fifo',
            lambda workspace, _: os.mkfifo(workspace / 'probe/fifo'),
        )

    def test_a_symlinked_workspace_root_is_refused(self) -> None:
        """``rglob`` would enumerate a replacement link's target silently."""

        def link_the_workspace_root(workspace: Path, boundary: Path) -> None:
            """Replace the staged workspace root with a directory link."""
            real = boundary / 'real-workspace'
            workspace.rename(real)
            workspace.symlink_to(real, target_is_directory=True)

        self._assert_drift(
            r'staged workspace .* must not be a symbolic link',
            link_the_workspace_root,
        )


if __name__ == '__main__':
    unittest.main()