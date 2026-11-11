"""Require shipped crates to be trust-free and the fixtures to stay seeded (VO-10).

A scan that reports nothing is only meaningful if it *could* have reported
something. This check therefore does two things in one pass: it audits every
workspace member enumerated from ``cargo metadata`` and requires an empty
result, and it audits ``tools/verifier-fixtures/`` and requires the items the
corpus deliberately seeds. The second half is the non-vacuity control — if the
scanner regressed to reporting nothing anywhere, the fixtures would fail and
the shipped-crate result would stop being evidence of anything.

Members come from ``cargo metadata`` rather than a manifest glob because the
metadata is the workspace Cargo actually builds. A member that a future
workspace edit adds but a glob would miss is exactly the crate whose proofs
would go unaudited.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path

from .context import ValidationContext, require
from .trust_audit import audit_tree, items_of
from .trust_audit.command import RUST_SUFFIX

FIXTURE_ROOT = 'tools/verifier-fixtures'
# The corpus files that must report items, and one item each must contain.
# Naming a file per item keeps the control from passing on a single stray hit.
SEEDED_ITEMS = {
    'tools/verifier-fixtures/kani-corpus/src/harnesses.rs':
        {'assume', 'should_panic'},
}
CRATE_ROOTS = ('lib.rs', 'main.rs')
COMPILED_DIRECTORIES = ('tests', 'benches', 'examples')


def check_trust_audit(context: ValidationContext) -> None:
    """Audit shipped crates and the seeded fixtures in one check.

    Parameters
    ----------
    context
        Repository inputs owned by the documentation checker.

    Returns
    -------
    None
        Records one result for the trust audit.

    Raises
    ------
    AssertionError
        If a shipped crate reports an item, or the fixture corpus no longer
        reports its seeded items.
    TrustAuditError
        If any audited source cannot be scanned; the check fails closed rather
        than reporting an empty audit.

    Examples
    --------
    check_trust_audit(context) passes when the workspace sources contain no
    trust vocabulary and ``tools/verifier-fixtures/`` still does.
    """
    shipped = _shipped_items(context.root)
    require(not shipped,
            'shipped crates must contain no trust items; found '
            + ', '.join(f'{location} ({item})' for item, location in shipped))
    _require_seeded_fixtures(context.root)
    context.record('trust-audit',
                   'No trust item appears in any workspace member; the fixture corpus still '
                   'reports its seeded items.', len(_workspace_roots(context.root)))


def _shipped_items(root: Path) -> list[tuple[str, str]]:
    """Return every trust item in the workspace members' sources.

    Each member's target sources come from ``cargo metadata``, so a target
    Cargo builds is audited even when no crate root reaches it.
    """
    items = []
    metadata = _metadata(root)
    for crate_root, targets in _workspace_members(root, metadata):
        for driver in _entry_points(root, crate_root, targets):
            relative = driver.relative_to(root).as_posix()
            items.extend((entry['item'], str(entry['location']))
                         for entry in items_of(audit_tree(root, [relative])))
    return items


def _workspace_members(root: Path, metadata: dict) -> tuple[tuple[Path, tuple[str, ...]], ...]:
    """Pair each workspace member's directory with its target source paths.

    ``targets[].src_path`` is absolute, and is made relative to the repository
    root here, because that is the form :func:`_entry_points` resolves against
    and the form the rest of the audit speaks. An absolute path outside the
    root would be a dependency's source, which this audit does not own, so it
    is skipped rather than audited.

    Both sides are resolved before they are compared. Cargo reports canonical
    paths, while ``root`` may be reached through a symlink — a macOS temporary
    directory is the usual case, where ``/var/...`` is canonically
    ``/private/var/...``. Comparing the unresolved forms would find no target
    inside the root and silently drop every crate's sources, leaving only the
    directory fallback in :func:`_entry_points` and the gap this function
    exists to close open again. A resolved comparison is also path-aware, so a
    sibling such as ``/repo-other`` no longer matches a root of ``/repo`` and
    reach a ``relative_to`` that would raise outside the documented failures.

    ``crate_root`` is resolved to match, because :func:`_entry_points` joins
    paths from it and a member directory under a symlinked root would otherwise
    disagree with the sources beside it.
    """
    canonical = root.resolve()
    members = []
    for package in metadata['packages']:
        crate_root = Path(package['manifest_path']).parent.resolve()
        sources = tuple(
            Path(target['src_path']).resolve().relative_to(canonical).as_posix()
            for target in package.get('targets', ())
            if Path(target['src_path']).resolve().is_relative_to(canonical)
        )
        members.append((crate_root, sources))
    return tuple(sorted(members, key=lambda member: str(member[0])))


def _require_seeded_fixtures(root: Path) -> None:
    """Require each seeded fixture file to report the items it seeds.

    The whole fixture tree is audited rather than only the named files, so an
    item that moves between files still fails until :data:`SEEDED_ITEMS` is
    updated. That is deliberate: the map states where the corpus intends its
    trust to live.
    """
    reported = _fixture_items(root)
    for relative, expected in SEEDED_ITEMS.items():
        found = reported.get(relative, set())
        require(expected <= found,
                f'{relative} must report {sorted(expected)}; the audit found {sorted(found)}')


def _fixture_items(root: Path) -> dict[str, set[str]]:
    """Map each fixture source to the item names the audit reports there.

    Every ``.rs`` file in the fixture tree is audited as its own driver. The
    tree is a corpus of standalone probes rather than one crate: the Verus
    wiring probe keeps its variants in sibling directories with no ``mod``
    declaration joining them, so a walk from a single root would never reach
    them. Duplicated items cannot result, because :func:`audit_tree` reports
    each file's items once and they are collected into a set.
    """
    reported: dict[str, set[str]] = {}
    for driver in sorted((root / FIXTURE_ROOT).rglob(f'*{RUST_SUFFIX}')):
        relative = driver.relative_to(root).as_posix()
        for audited in audit_tree(root, [relative]):
            reported.setdefault(audited.path, set()).update(item.item for item in audited.items)
    return reported


def _workspace_roots(root: Path) -> tuple[Path, ...]:
    """Return each workspace member's directory, from ``cargo metadata``.

    Metadata is read with ``--no-deps`` because dependency sources are not this
    repository's code and are not shipped from it.
    """
    return tuple(sorted({Path(package['manifest_path']).parent
                         for package in _metadata(root)['packages']}))


def _metadata(root: Path) -> dict:
    """Read the workspace metadata once, refusing rather than raising.

    Every caller needs the same document, so it is parsed here once and the
    parsed form is what the target and member walks iterate.
    """
    completed = subprocess.run(
        ['cargo', 'metadata', '--no-deps', '--format-version', '1'],
        cwd=root, capture_output=True, text=True, check=False,
    )
    require(completed.returncode == 0,
            f'cargo metadata --no-deps failed: {completed.stderr.strip()}')
    return json.loads(completed.stdout)


def _entry_points(root: Path, crate_root: Path, targets: Iterable[str] = ()) -> Iterable[Path]:
    """Yield the Rust files that start a crate's module tree.

    ``targets`` is Cargo's own list of that member's target source paths,
    written repository-relative by :func:`_workspace_members`, so each is
    resolved against ``root``. Joining it to ``crate_root`` instead would
    repeat the member's own directory for a nested member — ``crates/foo`` plus
    ``crates/foo/src/lib.rs`` — and the path would not exist. The conventional
    root fallback below would then still find ``src/lib.rs``, which is exactly
    what made the bug invisible: only the targets no fallback covers, such as
    ``build.rs`` and ``src/bin/*``, would go unaudited.

    Using Cargo's list rather than a filename convention is what keeps those
    targets in scope: none is reachable from a crate root by following ``mod``,
    yet all are compiled and can carry trust vocabulary.

    The conventional roots are still yielded, because metadata names a crate
    root as a target anyway and a second visit is harmless: the audit reports
    each file's items once and they are collected into a set.
    """
    seen = set()
    for source in targets:
        candidate = root / source
        if candidate.is_file() and candidate not in seen:
            seen.add(candidate)
            yield candidate
    for name in CRATE_ROOTS:
        candidate = crate_root / 'src' / name
        if candidate.is_file() and candidate not in seen:
            seen.add(candidate)
            yield candidate
    for directory in COMPILED_DIRECTORIES:
        nested = crate_root / directory
        if nested.is_dir():
            for candidate in sorted(nested.rglob(f'*{RUST_SUFFIX}')):
                if candidate not in seen:
                    seen.add(candidate)
                    yield candidate


__all__ = ['SEEDED_ITEMS', 'check_trust_audit']
