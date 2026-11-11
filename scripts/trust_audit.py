#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts==5.2.0"]
# ///
"""Report trusted items in Rust sources, in the evidence schema's audit shape.

Each argument is a Rust file or a directory. A directory is expanded to the
entry points Rust would compile from it: ``lib.rs``, ``main.rs``, ``mod.rs``,
and every file in ``tests/``, ``benches/``, and ``examples/``. The walk then
follows ``mod`` declarations, so a submodule is audited when — and only when —
the crate compiles it.

Output is one JSON object per argument on stdout, matching
``spec/proof-evidence.schema.json``'s ``trust_audit.items`` entries, so the
result can be pasted into a record or compared with one. Exit codes: 0 when
every source was audited, 1 when any source could not be audited, and 2 for a
usage error. An unreadable source fails the run rather than reporting an empty
audit, because an empty audit is a claim of purity.

Examples
--------
    scripts/trust_audit.py src/lib.rs
    scripts/trust_audit.py crates/ tools/verifier-fixtures/
"""
from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

import cyclopts
from cyclopts import Parameter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from docs_validation.trust_audit import (  # noqa: E402  (import after sys.path)
    TrustAuditError, audit_tree, items_of,
)
from docs_validation.trust_audit.command import RUST_SUFFIX  # noqa: E402  (import after sys.path)

# The files a directory contributes as entry points. A file in tests/benches/
# examples is its own crate root, so it is a driver wherever it sits; inside a
# source tree only the module roots are.
CRATE_ROOTS = ('lib.rs', 'main.rs', 'mod.rs')
COMPILED_DIRECTORIES = ('tests', 'benches', 'examples')

app = cyclopts.App(
    help='Report the trust ADR-0009 vocabulary introduces, in the evidence schema shape.',
)


@app.default
def main(
    paths: Annotated[list[Path], Parameter(help='Rust file or directory to audit.')],
) -> None:
    """Audit every named path and print one JSON object per path.

    Raises
    ------
    SystemExit
        With status 1 when a path cannot be audited, naming the reason.
    """
    audited = []
    for path in paths:
        try:
            driver_paths = _drivers(path)
        except TrustAuditError as error:
            print(f'{path}: {error}', file=sys.stderr)
            raise SystemExit(1) from error
        for driver, root in driver_paths:
            try:
                audited.append((driver, items_of(audit_tree(root, [driver]))))
            except TrustAuditError as error:
                print(f'{path}: {error}', file=sys.stderr)
                raise SystemExit(1) from error
    json.dump([{'source': source, 'items': list(items)} for source, items in audited],
              sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write('\n')


def _drivers(path: Path) -> list[tuple[str, Path]]:
    """Return each entry point under ``path`` as ``(repository-relative driver, ROOT)``.

    A file is its own driver. A directory contributes the entry points of every
    crate it contains — the manifest's own ``src/lib.rs``, ``src/main.rs``, and
    the compiled directories — found by walking for ``Cargo.toml`` rather than
    by looking only at the directory itself. A crate directory such as
    ``crates/combobulate-kernel`` keeps its sources in ``src/``, so a reader
    that looked only at the directory's immediate files found nothing and
    refused an argument Rust compiles happily.

    Every driver is resolved against :data:`ROOT` and named relative to it,
    because that is the root the walk is given. Naming a driver relative to the
    argument instead would make the locations in the output depend on how the
    caller spelled the path, and would break a ``mod`` declaration that reaches
    a sibling of the argument.

    Examples
    --------
    ``_drivers(ROOT / 'crates')`` yields ``('crates/combobulate-kernel/src/lib.rs', ROOT)``.
    """
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as error:
        raise TrustAuditError(f'{path} is outside the repository at {ROOT}') from error
    if resolved.is_file():
        return [(resolved.relative_to(ROOT).as_posix(), ROOT)]
    if not resolved.is_dir():
        raise TrustAuditError(f'{path} does not exist')
    drivers = {}
    for crate_root in _crate_roots(resolved):
        for candidate in _entry_points(ROOT, crate_root):
            drivers[candidate.relative_to(ROOT).as_posix()] = ROOT
    if not drivers:
        raise TrustAuditError(
            f'{path} contains no Rust entry point to audit')
    return sorted(drivers.items())


def _crate_roots(resolved: Path) -> list[Path]:
    """Return every crate directory under ``resolved``, including itself.

    A crate is a directory with a ``Cargo.toml``. The argument is included as
    well so that a bare module directory — ``src/``, which has no manifest —
    still contributes the entry points it holds directly. Directories are
    returned in a stable order so an audit's output is reproducible.
    """
    manifests = {candidate.parent for candidate in resolved.rglob('Cargo.toml')}
    return sorted(manifests | {resolved})


def _entry_points(root: Path, crate_root: Path) -> Iterable[Path]:
    """Yield the files that start a crate's module tree, as absolute paths.

    ``crate_root`` may itself be the repository root, which is a crate in this
    workspace, so the caller cannot assume the entry points sit one level down.
    """
    for name in CRATE_ROOTS:
        candidate = crate_root / name
        if candidate.is_file():
            yield candidate
        candidate = crate_root / 'src' / name
        if candidate.is_file():
            yield candidate
    for directory in COMPILED_DIRECTORIES:
        nested = crate_root / directory
        if nested.is_dir():
            yield from sorted(nested.rglob(f'*{RUST_SUFFIX}'))


if __name__ == '__main__':
    app()
