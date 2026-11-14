"""Load the committed Kani log corpus, its manifests, and the commands that produced it.

Nothing in this module may invent a fact about the corpus. Every helper either
reads a committed file or derives a value from one, and the one place that
would otherwise need a guess — which manifest a log belongs to — is read from
`runs.json`, which records the command that produced each log. Reading the
`--harness` arguments from that command is what lets a test decide a
whole-crate manifest against the subset a run selected, instead of hard-coding
the pairing in a second place that could drift.

Examples
--------
>>> corpus_root().name
'kani_logs'
>>> observation('verified')['exit_code']
0
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docs_validation.kani_log import Manifest, KaniLog, KaniLogError, decide, from_error, manifest_from_document

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'scripts/tests/fixtures/kani_logs'
CRATE_MANIFEST = ROOT / 'tools/verifier-fixtures/kani-corpus/harness-manifest.json'
IN_PLACE_MANIFEST = CORPUS / 'in_place-manifest.json'
HARNESS_FLAG = '--harness'


def corpus_root() -> Path:
    """Return the directory holding the committed logs and their run commands."""
    return CORPUS


def log_names() -> tuple[str, ...]:
    """Name every committed log, in a stable order, without its extension."""
    return tuple(sorted(path.stem for path in CORPUS.glob('*.log')))


def log_text(name: str) -> str:
    """Return one committed log exactly as the parser receives it."""
    return CORPUS.joinpath(f'{name}.log').read_text(encoding='utf-8')


def observations() -> list[dict[str, Any]]:
    """Return every recorded run, one per committed log."""
    document = json.loads(CORPUS.joinpath('runs.json').read_text(encoding='utf-8'))
    return list(document['runs'])


def observation(name: str) -> dict[str, Any]:
    """Return the run whose log is ``name``; e.g. ``observation('verified')['exit_code']``."""
    for entry in observations():
        if entry['id'] == name:
            return entry
    raise KeyError(f'runs.json records no run for {name!r}')


def harness_arguments(command: list[str]) -> tuple[str, ...]:
    """Name the harnesses an observation's command selected, in order.

    Each occurrence of ``--harness`` is followed by its value; a run with no
    occurrence verifies whatever the crate defines, which is no selection at
    all rather than an empty one.
    """
    return tuple(command[index + 1] for index, token in enumerate(command)
                 if token == HARNESS_FLAG and index + 1 < len(command))


def crate_manifest() -> Manifest:
    """Return the whole-crate manifest the corpus crate commits."""
    return manifest_from_document(json.loads(CRATE_MANIFEST.read_text(encoding='utf-8')))


def in_place_manifest() -> Manifest:
    """Return the standalone manifest for the probe-generated harness."""
    return manifest_from_document(json.loads(IN_PLACE_MANIFEST.read_text(encoding='utf-8')))


def manifest_for(name: str) -> Manifest:
    """Return the manifest one log must be decided against, narrowed to its selection."""
    selected = harness_arguments(observation(name)['command'])
    if name == 'in_place':
        return in_place_manifest()
    if not selected:
        return crate_manifest()
    return crate_manifest().select(selected)


def parse_log(name: str) -> KaniLog:
    """Parse one committed log, raising the structural error it may have."""
    return parse_text(log_text(name))


def parse_text(text: str) -> KaniLog:
    """Parse arbitrary log text; imported from the package so tests share one grammar."""
    from docs_validation.kani_log import parse
    return parse(text)


def decision_for(name: str):
    """Decide one committed log against the manifest its command implies."""
    try:
        log = parse_log(name)
    except KaniLogError as error:
        return from_error(error)
    return decide(log, manifest_for(name))


def decision_table() -> dict[str, Any]:
    """Return the VO-11b decision table as data."""
    path = ROOT / 'scripts/tests/fixtures/kani_decision_table.json'
    return json.loads(path.read_text(encoding='utf-8'))


def expected() -> dict[str, Any]:
    """Return the committed record of what every log must yield and decide."""
    return json.loads(CORPUS.joinpath('expected.json').read_text(encoding='utf-8'))


def recorded(name: str) -> tuple:
    """Return one log's recorded decision, in the order the decision renders its facts."""
    entry = expected()['decisions'][name]
    return (entry['outcome'], tuple(entry['witnesses']),
            tuple((bool(required), str(observed)) for required, observed in entry['controls']),
            entry['run_mode'])
