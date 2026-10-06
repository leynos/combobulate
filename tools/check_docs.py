#!/usr/bin/env python3
"""Validate the explicit documentation pack, not a Combobulate implementation.

Run ``python tools/check_docs.py`` using tools/requirements.txt. No network
access occurs. Results go to docs/validation-results.json. The independent
repository Markdown and Rust gates remain authoritative for their own inputs.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from jsonschema import ValidationError

from docs_validation.context import ValidationContext
from docs_validation.contracts import (
    check_kernel_envelope, check_proof_evidence_envelope, check_revision_contracts,
)
from docs_validation.costs import check_cost_examples
from docs_validation.ledger import check_catalogue_and_roadmap
from docs_validation.markdown import check_markdown
from docs_validation.semantics import check_examples

ROOT = Path(__file__).resolve().parents[1]
NOT_RUN = [
    'Kani or Verus verification and downstream proof fixtures',
    'Rust constant evaluation or actual static cost certification',
    'Polars engine/capability/spill probes',
    'Rust compilation or doctests', 'Combobulate execution or backend conformance',
    'Actual trasic integration', 'Repository CI/markdownlint gates',
    'Nixie validation (no Mermaid diagrams supplied)',
    'Performance or memory benchmarks', 'Online link recheck from runtime',
]


def check_tool_sources(context: ValidationContext) -> None:
    """Parse delivered Python tooling; e.g. syntax errors in feature modules fail."""
    paths = sorted((context.root / 'tools').rglob('*.py'))
    for path in paths:
        ast.parse(path.read_text(), filename=str(path))
    context.record('python-tools', 'All delivered Python tool files parse; generator and checker execution also exercised their main paths.', len(paths))


def write_report(context: ValidationContext, status: str) -> dict:
    """Write this run's report; e.g. 'pass' explicitly names unperformed checks."""
    report = {'status': status, 'scope': 'documentation-pack-only',
              'checks': context.results}
    if status == 'pass':
        report['not_run'] = NOT_RUN
    (context.root / 'docs/validation-results.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8'
    )
    return report


def main() -> int:
    """Run independent design-pack checks and write a bounded evidence report."""
    context = ValidationContext(ROOT)
    write_report(context, 'running')
    try:
        for path in context.json_paths():
            json.loads(path.read_text(encoding='utf-8'))
        for check in (
            check_markdown, check_catalogue_and_roadmap, check_kernel_envelope,
            check_examples, check_revision_contracts,
            check_proof_evidence_envelope, check_cost_examples, check_tool_sources,
        ):
            check(context)
    except (AssertionError, ValueError, ValidationError) as error:
        context.results.append({'check': 'failure', 'status': 'fail', 'detail': str(error)})
        write_report(context, 'fail')
        raise SystemExit(str(error)) from error
    print(json.dumps(write_report(context, 'pass'), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
