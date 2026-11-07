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
    """Return every trust item in the workspace members' sources."""
    items = []
    for crate_root in _workspace_roots(root):
        for driver in _entry_points(crate_root):
            relative = driver.relative_to(root).as_posix()
            items.extend((entry['item'], str(entry['location']))
                         for entry in items_of(audit_tree(root, [relative])))
    return items


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
    completed = subprocess.run(
        ['cargo', 'metadata', '--no-deps', '--format-version', '1'],
        cwd=root, capture_output=True, text=True, check=False,
    )
    require(completed.returncode == 0,
            f'cargo metadata --no-deps failed: {completed.stderr.strip()}')
    metadata = json.loads(completed.stdout)
    return tuple(sorted({Path(package['manifest_path']).parent
                         for package in metadata['packages']}))


def _entry_points(crate_root: Path) -> Iterable[Path]:
    """Yield the Rust files that start a crate's module tree."""
    for name in CRATE_ROOTS:
        candidate = crate_root / 'src' / name
        if candidate.is_file():
            yield candidate
    for directory in COMPILED_DIRECTORIES:
        nested = crate_root / directory
        if nested.is_dir():
            yield from sorted(nested.rglob(f'*{RUST_SUFFIX}'))


__all__ = ['SEEDED_ITEMS', 'check_trust_audit']
