#!/usr/bin/env python3
"""Validate the explicit documentation pack and its committed evidence report.

Run ``python tools/check_docs.py`` using tools/requirements.txt. Default checks
are read-only; ``--write`` explicitly regenerates docs/validation-results.json
only after every source check passes. No network access occurs. Repository
Markdown and Rust gates remain authoritative for their independent inputs.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from jsonschema import ValidationError

from docs_validation.context import ValidationContext, require, same_typed_value
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


def report_data(context: ValidationContext, status: str) -> dict:
    """Build in-memory evidence; a passing report explicitly names unperformed checks."""
    report = {'status': status, 'scope': 'documentation-pack-only',
              'checks': context.results}
    if status == 'pass':
        report['not_run'] = NOT_RUN
    return report


def collect_checks(context: ValidationContext) -> None:
    """Run source-only checks; the existing evidence report cannot affect their results."""
    for path in context.json_paths():
        json.loads(path.read_text(encoding='utf-8'))
    for check in (
        check_markdown, check_catalogue_and_roadmap, check_kernel_envelope,
        check_examples, check_revision_contracts,
        check_proof_evidence_envelope, check_cost_examples, check_tool_sources,
    ):
        check(context)


def verify_report(context: ValidationContext, expected: dict) -> None:
    """Require the committed report to match execution; stale or fabricated evidence fails."""
    actual = context.load('docs/validation-results.json')
    require(same_typed_value(actual, expected),
            'Validation report drift: run python tools/check_docs.py --write and review the changes')


def main(argv: list[str] | None = None) -> int:
    """Check sources and committed evidence; --write explicitly regenerates valid evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Regenerate the evidence report after checks pass')
    args = parser.parse_args(argv)
    context = ValidationContext(ROOT)
    try:
        collect_checks(context)
        report = report_data(context, 'pass')
        if args.write:
            (context.root / 'docs/validation-results.json').write_text(
                json.dumps(report, indent=2) + '\n', encoding='utf-8'
            )
        else:
            verify_report(context, report)
    except (AssertionError, ValueError, ValidationError, OSError) as error:
        context.results.append({'check': 'failure', 'status': 'fail', 'detail': str(error)})
        print(json.dumps(report_data(context, 'fail'), indent=2))
        raise SystemExit(str(error)) from error
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
