"""Share the scratch checkout and record builders binding refusals are asserted on.

A binding refusal names the artefact that caused it, so every case has to drive
a real record against a real Git checkout. These builders are the same for the
verdict adapter and for the scanner, and the two are tested in separate modules
so each stays within the repository's module-length limit. Putting the builders
here is what keeps the two modules asserting against one definition of "a record
that would otherwise bind".

Nothing here decides what is correct. Each builder returns a record or a
checkout; whether the adapter must refuse it is the calling module's claim.

Examples
--------
>>> record()['method']['tool']
'kani'
>>> report({'id': 'EV-1'}, MissingEvidence('log', 'a.log', 'bad'))
"EV-1: log 'a.log' was refused: bad"
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.evidence_binding import _refusal
from docs_validation.kani_log.shell import MissingEvidence, bind_verdict
from git_fixtures import run_git

ROOT = Path(__file__).resolve().parents[2]
KANI = frozenset({'kani'})
# The tool name a bound verdict reports; the gate matches on it with the log identity.
TOOL = 'kani'
LOG = 'scripts/tests/fixtures/kani_logs/verified.log'
MANIFEST = 'scripts/tests/fixtures/evidence/default-unwind-manifest.json'


def report(record: dict, missing: MissingEvidence) -> str:
    """Return the line ``_refusal`` prints, without its trailing newline."""
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        _refusal(record, missing)
    return captured.getvalue().rstrip('\n')


def file_digest(relative: str) -> str:
    """Return the digest of one repository file, so a record can bind real bytes."""
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def digest(data: bytes) -> str:
    """Return the digest of arbitrary bytes, for an artefact that is not committed."""
    return hashlib.sha256(data).hexdigest()


def record(**overrides) -> dict:
    """Return a minimal record whose every binding would succeed, before overrides."""
    document = {
        'id': 'EV-TEST',
        'method': {'tool': 'kani'},
        'verdict_source': {'kind': 'log-parser',
                           'log': {'path': LOG, 'sha256': file_digest(LOG)}},
        'result_artefacts': [{'path': MANIFEST, 'sha256': file_digest(MANIFEST)}],
        'trust_audit': {'status': 'audited', 'items': []},
    }
    document.update(overrides)
    return document


def captured_against(root: Path, adapter, document: dict) -> str:
    """Return the refusal report for one record against one root."""
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        adapter(root, document, KANI)
    return captured.getvalue().strip()


def refused_by(adapter, document: dict) -> str | None:
    """Return the refusal an adapter reports for one record, or None when it binds."""
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        result = adapter(ROOT, document, KANI)
    if result is not None:
        return None
    return captured.getvalue().strip()


def refused_directly(document: dict) -> str:
    """Return the line ``bind_verdict``'s own refusal prints, without the seam's filters.

    ``evidence_binding.log_result`` returns before dispatch for a tool it has no
    adapter for, so the adapter's own shape checks are reachable only by calling
    it. They are not dead: the seam calls the adapter on every record whose tool
    *is* registered, and a malformed record must still refuse there.
    """
    return report(document, bind_verdict(ROOT, document))



class ScratchCheckout:
    """A Git repository holding one log and one manifest, both tracked.

    A refusal that names a path can only be pinned against a repository whose
    contents the test controls, so the log and manifest here are real files
    with real digests rather than paths into the project.
    """

    def __init__(self, manifest: str | None = None, log: str | None = None) -> None:
        """Create the checkout, with the files the caller asked to override."""
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        log_text = log or (ROOT / LOG).read_text(encoding='utf-8')
        self.root.joinpath('run.log').write_text(log_text, encoding='utf-8')
        text = manifest if manifest is not None else (ROOT / MANIFEST).read_text(encoding='utf-8')
        self.root.joinpath('manifest.json').write_text(text, encoding='utf-8')
        run_git(self.root, 'init', '-q')
        run_git(self.root, 'add', '-A')
        run_git(self.root, 'commit', '-q', '-m', 'Create binding fixture')

    def close(self) -> None:
        """Remove the checkout."""
        self._directory.cleanup()

    def record(self, **overrides) -> dict:
        """Return a record binding this checkout's files, with any field overridden."""
        defaults = {
            'verdict_source': {
                'kind': 'log-parser',
                'log': {'path': 'run.log',
                        'sha256': digest(self.root.joinpath('run.log').read_bytes())}},
            'result_artefacts': [
                {'path': 'manifest.json',
                 'sha256': digest(self.root.joinpath('manifest.json').read_bytes())}],
        }
        defaults.update(overrides)
        return record(**defaults)


class CheckoutFixture(unittest.TestCase):
    """Give each case a scratch checkout that is cleaned up afterwards."""

    def checkout(self, **options) -> ScratchCheckout:
        """Create one checkout and register its removal."""
        checkout = ScratchCheckout(**options)
        self.addCleanup(checkout.close)
        return checkout
