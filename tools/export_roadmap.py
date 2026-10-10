#!/usr/bin/env python3
"""Export the canonical `docs/roadmap.md` to its derived `spec/roadmap.json` view.

Run ``python tools/export_roadmap.py`` after editing the roadmap to rewrite the
export, or ``--check`` to fail when the committed export has drifted. Exit
codes: 0 when the export is written or matches, 1 on drift (a unified diff is
printed), and 2 when the roadmap structure is malformed (the source line is
printed). Upstream request leynos/mapsplice#144 tracks a native replacement.
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from docs_validation.roadmap_markdown import RoadmapStructureError, export_text

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / 'docs/roadmap.md'
EXPORT = ROOT / 'spec/roadmap.json'


def drift(committed: str, fresh: str) -> str:
    """Render the difference between the committed and fresh exports."""
    return ''.join(difflib.unified_diff(committed.splitlines(keepends=True), fresh.splitlines(keepends=True),
                                        'spec/roadmap.json (committed)', 'spec/roadmap.json (fresh export)'))


def main(argv: list[str] | None = None) -> int:
    """Write or check the export; e.g. main(['--check']) returns 1 after an unexported edit."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail if the committed export has drifted')
    args = parser.parse_args(argv)
    try:
        fresh = export_text(ROADMAP.read_text(encoding='utf-8'))
    except RoadmapStructureError as error:
        print(error, file=sys.stderr)
        return 2
    committed = EXPORT.read_text(encoding='utf-8') if EXPORT.exists() else ''
    if not args.check:
        EXPORT.write_text(fresh, encoding='utf-8')
        return 0
    if committed == fresh:
        print('spec/roadmap.json matches docs/roadmap.md.')
        return 0
    print(drift(committed, fresh), end='')
    print('spec/roadmap.json is stale: run python tools/export_roadmap.py', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
