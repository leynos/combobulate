"""Scan the committed verifier records without teaching each test their schema.

The Verus, Kani, and verifier-free generators write JSON documents of different
shapes into two fixture roots. Three suites read them: one checks that no
published path names an account home, one binds each record's sources by
digest, and one requires the hosted observation to bind both. The scanning and
path-walking rules are the same for all three, so they live here rather than
being copied into a suite that would then drift from its siblings.

For example::

    for path, record in committed_record_documents():
        print(path.name, sorted(record.get('source_digests', {})))
"""

from __future__ import annotations

import json
from pathlib import Path

from verifier_probe_loader import ROOT

# The two roots match the two generators: the Kani corpus writes its provenance
# under the test fixtures, and the Verus probes under their own fixture tree.
_RECORD_ROOTS = ('tools/verifier-fixtures', 'scripts/tests/fixtures/kani_logs')


def recorded_paths(node: object) -> list[str]:
    """Return every path a decoded record publishes.

    Command arrays carry the invocation, and the Verus provenance also records
    the resolved solver path; the same portability rule governs both, so the
    walk collects both. Records differ in shape — the Verus probe nests its
    observations, while the verifier-free record is flat — and walking the
    decoded JSON finds either without teaching each test its schema.

    Examples
    --------
    A solver path and a nested observation are both reached::

        recorded_paths({'z3': '~/z3', 'observations': [{'command': ['kani']}]})
        # ['~/z3', 'kani']
    """
    match node:
        case dict():
            paths: list[str] = []
            for key, value in node.items():
                match (key, value):
                    case ('command', list()):
                        paths.extend(item for item in value if isinstance(item, str))
                    case ('z3', str()):
                        paths.append(value)
                    case _:
                        paths.extend(recorded_paths(value))
            return paths
        case list():
            return [item for child in node for item in recorded_paths(child)]
        case _:
            return []


def record_documents(root: Path) -> list[tuple[Path, dict]]:
    """Return each record document below ``root``, skipping build output.

    The fixture crates sit outside the repository workspace, so Cargo builds
    them in place and leaves a ``target`` directory inside the scanned tree.
    Those files are build metadata, not records: the walked documents must be
    JSON objects, while a build artefact may be an array, so parsing one would
    fail a suite for a reason unrelated to provenance.
    """
    return [
        (path, json.loads(path.read_text(encoding='utf-8')))
        for path in sorted(root.rglob('*.json'))
        if 'target' not in path.relative_to(root).parts
    ]


def committed_record_documents() -> list[tuple[Path, dict]]:
    """Return each committed verifier record with its decoded document."""
    return [
        document
        for root in _RECORD_ROOTS
        for document in record_documents(ROOT / root)
    ]


def committed_records() -> list[tuple[Path, list[str]]]:
    """Return each committed verifier record with the paths it publishes.

    Synthetic evidence fixtures are not observation records and stay out of
    scope; only the two generator roots are scanned.
    """
    return [
        (path, recorded_paths(record))
        for path, record in committed_record_documents()
    ]


def publishes_host_detail(argument: str) -> bool:
    """Report whether an argument names this worktree or an account home.

    Account homes are detected by their POSIX and macOS roots. Container paths
    such as ``/usr/local/bin`` remain legitimate, so the check is limited to
    roots that encode who and where the probe ran.
    """
    roots = ('/home/', '/Users/')
    return str(ROOT) in argument or any(root in argument for root in roots)
