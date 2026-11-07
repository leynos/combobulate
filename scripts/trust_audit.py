#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
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
from pathlib import Path
from typing import Annotated

import cyclopts
from cyclopts import Parameter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from docs_validation.trust_audit import (  # noqa: E402  (import after sys.path)
    TrustAuditError, audit_tree, items_of,
)
from docs_validation.trust_audit.command import RUST_SUFFIX  # noqa: E402

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
    """Return each entry point under ``path`` as ``(relative driver, root)``.

    A file is its own driver, resolved from its parent. A directory
    contributes the crate roots it contains, or every file directly in one of
    the compiled directories beneath it, because each of those is a crate root
    in its own right. Drivers stay relative because the walk refuses an
    absolute path: it audited the whole repository, and accepting an absolute
    one would let a caller point the audit outside it.
    """
    resolved = path.resolve()
    if resolved.is_file():
        return [(resolved.name, resolved.parent)]
    if not resolved.is_dir():
        raise TrustAuditError(f'{path} does not exist')
    drivers = [(candidate.name, resolved) for candidate in sorted(resolved.iterdir())
               if candidate.is_file() and candidate.name in CRATE_ROOTS]
    for directory in COMPILED_DIRECTORIES:
        nested = resolved / directory
        if nested.is_dir():
            drivers.extend((f'{directory}/{candidate.name}', resolved)
                           for candidate in sorted(nested.glob(f'*{RUST_SUFFIX}')))
    if not drivers:
        raise TrustAuditError(f'{path} contains no Rust entry point to audit')
    return drivers


if __name__ == '__main__':
    app()
