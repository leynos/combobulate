"""Bind a record's cited Kani artefacts to the facts a parser can re-derive (VO-12).

ADR-0009 makes a verdict parsed only when a registered adapter re-derives it
from the exact log the record names. This module is that adapter's shell half:
it reads a record's Git-tracked log, harness manifest, and source files, checks
the digests the record binds, parses the log, decides it against the manifest,
and hands the result to the gate as a :class:`VerifiedLogResult`.

The split from :mod:`docs_validation.kani_log` is the architecture's: the
package is pure and never touches a filesystem, so the parser and the decision
can be enumerated over constructed inputs, while every path this module opens
is opened here and nowhere else.

Three policies live here because they need the repository and Git:

- Only Git-tracked paths are read. An untracked log can be created between
  reviews, so binding it would let a record cite evidence no commit contains.
- Only paths inside the repository are read, checked on the resolved path so a
  ``..`` component cannot borrow the root's prefix to escape it.
- A digest the record names must match the bytes on disk. The gate compares the
  parsed facts with the record; without this check a record could cite a log
  that says something else entirely and still match, because the parser would
  decide the file rather than the record.

The shell returns no result for a log it cannot bind. That is a refusal rather
than an error: the record then falls back to ``self-reported`` and the gate
rejects it, which is the documented fail-closed direction (C-EP-10).

Examples
--------
>>> callable(bind_verdict)
True
>>> 'not tracked' in MissingEvidence('log', 'x.log', 'it is not tracked').reason
True
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..evidence_gate import VerifiedLogResult
from . import KaniLogError, decide, from_error, manifest_from_document, parse

KANI = 'kani'
TOOL_ALIASES = {KANI: KANI}
# Two callers refuse a record that does not bind exactly one artefact: the
# verdict adapter, and the scanner that runs before it. They are reached
# independently, so both must state the rule; sharing the sentence keeps a
# change to it from drifting between the two refusals.
#
# Three places name a record whose author gave no id. A refusal must still
# identify what it refused, so the fallback is a named constant rather than a
# literal retyped at each site.
ONE_ARTEFACT = 'the record must bind exactly one result artefact: its harness manifest'
UNNAMED_RECORD = 'record'


@dataclass(frozen=True, slots=True)
class MissingEvidence:
    """Why one cited artefact could not be bound to a verdict; e.g. an untracked log."""

    what: str
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class GitUnavailable:
    """Why Git could not answer what a root tracks; e.g. the root is not a repository.

    A separate value from an empty result, because the two answer different
    questions. "Nothing here is tracked" is evidence about the paths a record
    cites; "Git could not answer" is evidence about the checkout, and reporting
    it as the former made a broken invocation read as a specific, wrong
    verdict about each cited path. Both stay fail-closed: neither admits.
    """

    detail: str


@dataclass(frozen=True, slots=True)
class KaniBinding:
    """The inputs one record's Kani claim is decided from."""

    log_path: str
    log_sha256: str
    manifest_path: str
    manifest_sha256: str
    sources: tuple[str, ...]
    source_digests: Mapping[str, str]


def tracked_paths(root: Path, paths: Sequence[str]) -> frozenset[str] | GitUnavailable:
    """Return the subset of ``paths`` Git tracks under ``root``.

    One ``git ls-files`` call answers for all of them, so a record citing many
    sources costs one subprocess rather than one per file.

    Examples
    --------
    ``tracked_paths(root, ['spec/roadmap.json', 'scratch/none.log'])`` returns
    only the tracked path when the second is untracked. A root Git cannot
    answer for returns ``GitUnavailable`` rather than an empty set, so the
    caller can say that instead of blaming each cited path.

    ``check=False`` is deliberate: a non-zero exit is ordinary here, because a
    directory that is not a repository is exactly what this function is asked
    about, and ``CalledProcessError`` would escape as an exception.
    """
    wanted = sorted(set(paths))
    if not wanted:
        return frozenset()
    completed = subprocess.run(
        ['git', '-C', str(root), 'ls-files', '--', *wanted],
        capture_output=True, check=False, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f'git ls-files exited {completed.returncode}'
        return GitUnavailable(detail)
    return frozenset(completed.stdout.splitlines())


def read_tracked(root: Path, relative: str) -> bytes | MissingEvidence:
    """Read one Git-tracked file inside ``root``, or say why it could not be read.

    The containment check runs on the resolved path, so ``a/../../b`` cannot
    borrow the root's prefix to escape it, and it runs before the existence
    check so an escaping path is refused for what it is rather than reported
    absent.
    """
    purl = PurePosixPath(relative)
    if purl.is_absolute() or '..' in purl.parts:
        return MissingEvidence('path', relative, 'it is not a repository-relative path')
    resolved = (root / relative).resolve()
    root_resolved = root.resolve()
    if root_resolved not in resolved.parents:
        return MissingEvidence('path', relative, 'it resolves outside the repository')
    tracked = tracked_paths(root, [relative])
    if isinstance(tracked, GitUnavailable):
        return MissingEvidence('path', relative, f'Git could not report what it tracks: {tracked.detail}')
    if relative not in tracked:
        return MissingEvidence('path', relative, 'it is not tracked by Git')
    try:
        return resolved.read_bytes()
    except OSError as error:
        return MissingEvidence('path', relative, f'it cannot be read: {error}')


def digest(data: bytes) -> str:
    """Return the SHA-256 digest of one artefact's bytes."""
    return hashlib.sha256(data).hexdigest()


def read_artefact(root: Path, path: str, sha256: str, what: str) -> bytes | MissingEvidence:
    """Read one bound artefact and require the digest the record names.

    The digest is checked here rather than left to the gate because the gate
    never sees the file: a mismatch would otherwise be invisible, and the
    parsed facts would describe whatever the file happens to say.
    """
    data = read_tracked(root, path)
    if isinstance(data, MissingEvidence):
        return MissingEvidence(what, path, data.reason)
    if digest(data) != sha256:
        return MissingEvidence(what, path, 'its digest differs from the one the record binds')
    return data


def _manifest_document(data: bytes, path: str):
    """Parse a manifest document, returning why it could not be read instead of raising."""
    try:
        document = json.loads(data)
    except ValueError as error:
        return MissingEvidence('manifest', path, f'it is not valid JSON: {error}')
    if not isinstance(document, Mapping):
        return MissingEvidence('manifest', path, 'it is not a JSON object')
    return document


def _first_mismatch(record: Mapping[str, object]) -> str | None:
    """Name the first field whose shape this adapter cannot bind, or None when it can."""
    source = record['verdict_source']
    log = source['log'] if isinstance(source, Mapping) else None
    method = record['method']
    if not isinstance(source, Mapping) or source.get('kind') != 'log-parser':
        return 'the record does not claim a parsed verdict'
    if str(method['tool']) not in TOOL_ALIASES:
        return f'the record names tool {method["tool"]!r}, which this adapter does not read'
    if not isinstance(log, Mapping) or not all(isinstance(log.get(key), str) for key in ('path', 'sha256')):
        return 'the record names no log path and digest'
    artefacts = record.get('result_artefacts') or ()
    if not isinstance(artefacts, Sequence) or len(artefacts) != 1:
        return ONE_ARTEFACT
    only = artefacts[0]
    if not isinstance(only, Mapping) or not all(isinstance(only.get(key), str) for key in ('path', 'sha256')):
        return 'the bound result artefact names no path and digest'
    return None


def _manifest_sources(document: Mapping[str, object]) -> tuple[tuple[str, str], ...] | None:
    """Return the ``(path, sha256)`` pairs one manifest binds, or None if it cannot.

    The list is all-or-nothing. A manifest that names a source without a digest
    cannot be bound to the file the audit reads, and keeping the other entries
    would audit exactly the sources the author remembered to bind while the
    unbound one went unread. The audit would then describe a proof whose scope
    the record never established, which is the failure DL-16 exists to prevent.
    So one malformed entry rejects the whole list rather than shrinking it.

    ``None`` distinguishes "this list is unusable" from ``()``, "this manifest
    declares no source at all", because the two refusals call the author to
    different repairs.

    Examples
    --------
    >>> _manifest_sources({'sources': [{'path': 'a.rs', 'sha256': '00'}]})
    (('a.rs', '00'),)
    >>> _manifest_sources({'sources': ['a.rs']}) is None
    True
    >>> _manifest_sources({'sources': []})
    ()
    """
    sources = document.get('sources', ())
    if not isinstance(sources, Sequence) or isinstance(sources, str):
        return None
    bound = []
    for item in sources:
        if not isinstance(item, Mapping):
            return None
        path, sha256 = item.get('path'), item.get('sha256')
        if not isinstance(path, str) or not isinstance(sha256, str) or not sha256:
            return None
        bound.append((path, sha256))
    return tuple(bound)


def _verified_result(decision, log_path: str, log_sha256: str,
                     manifest_path: str, manifest_sha256: str) -> VerifiedLogResult:
    """Render one decision in the shape the gate compares with the record.

    Both artefact identities travel with the facts. The decision was taken
    against one manifest's harness list, so a result that named only the log
    could stand in for a record bound to a different — or unparseable —
    manifest that happened to cite the same capture.
    """
    return VerifiedLogResult(
        tool=KANI, log_path=log_path, log_sha256=log_sha256,
        manifest_path=manifest_path, manifest_sha256=manifest_sha256,
        outcome=decision.outcome, bounds=decision.bounds,
        witness_statuses=decision.witness_statuses,
        negative_controls=decision.negative_controls, run_mode=decision.run_mode)


def bind_verdict(root: Path, record: Mapping[str, object]) -> VerifiedLogResult | MissingEvidence:
    """Re-derive one record's Kani verdict from its cited log and manifest.

    Parameters
    ----------
    root
        Repository root; every artefact must resolve inside it and be tracked.
    record
        A schema-valid evidence record whose ``method.tool`` this adapter reads.

    Returns
    -------
    VerifiedLogResult | MissingEvidence
        The parsed facts, or the first artefact or field that could not be
        bound. A structural log refusal is not missing evidence: it becomes a
        ``tool-error`` decision, which the gate then rejects on its outcome.

    Examples
    --------
    A record naming an untracked log yields ``MissingEvidence('path', ...,
    'it is not tracked by Git')`` rather than a verdict.
    """
    problem = _first_mismatch(record)
    if problem is not None:
        return MissingEvidence('field', str(record.get('id', UNNAMED_RECORD)), problem)
    source = record['verdict_source']
    log_path, log_sha256 = str(source['log']['path']), str(source['log']['sha256'])
    artefact = record['result_artefacts'][0]
    manifest_path, manifest_sha256 = str(artefact['path']), str(artefact['sha256'])
    if not manifest_sha256:
        return MissingEvidence('manifest', manifest_path, 'the record binds no digest for it')
    log_data = read_artefact(root, log_path, log_sha256, 'log')
    if isinstance(log_data, MissingEvidence):
        return log_data
    manifest_data = read_artefact(root, manifest_path, manifest_sha256, 'manifest')
    if isinstance(manifest_data, MissingEvidence):
        return manifest_data
    document = _manifest_document(manifest_data, manifest_path)
    if isinstance(document, MissingEvidence):
        return document
    try:
        manifest = manifest_from_document(document)
    except ValueError as error:
        return MissingEvidence('manifest', manifest_path, str(error))
    try:
        log = parse(log_data.decode('utf-8', errors='replace'))
    except KaniLogError as error:
        return _verified_result(from_error(error), log_path, log_sha256,
                                manifest_path, manifest_sha256)
    return _verified_result(decide(log, manifest), log_path, log_sha256,
                            manifest_path, manifest_sha256)


def bound_sources(root: Path, record: Mapping[str, object]) -> Mapping[str, bytes] | MissingEvidence:
    """Return the manifest-declared sources of one record's claim, once they are readable.

    The scanner audits these files and the gate compares the result with the
    record's ``trust_audit``; returning them here keeps the scanner's input and
    the record's claim bound to the same list. The *bytes* are returned rather
    than the paths so the scanner audits exactly the text whose digest this
    function checked. A path alone would let the scanner re-open the file and
    read whatever it holds by then, and the digest check would have vouched for
    an earlier version of it.

    A record citing no manifest — or several — has nothing this scanner can
    audit, so it is refused rather than raising. The schema permits an empty
    ``result_artefacts`` for a record whose claim needs no artefact, and a
    refusal leaves that record ``unaudited``, which is the fail-closed direction
    DL-16 takes. The count is checked here as well as in the verdict adapter
    because the scanner runs first and independently of it.

    A manifest whose source list is unusable is refused whole. Auditing only
    the entries that happened to be well formed would leave sources the record
    claims to have covered silently unread, so the audit would certify a scope
    the record never established.

    Each source's digest is checked against the file as it exists now, so a
    manifest cannot outlive the source it was written for (DL-16). The check is
    :func:`read_artefact`'s rather than a bare read, so a drift is reported for
    what it is instead of letting the audit describe a file the record never
    named.
    """
    artefacts = record.get('result_artefacts') or ()
    if not isinstance(artefacts, Sequence) or len(artefacts) != 1:
        return MissingEvidence('manifest', str(record.get('id', UNNAMED_RECORD)), ONE_ARTEFACT)
    artefact = artefacts[0]
    manifest_data = read_artefact(root, str(artefact['path']), str(artefact['sha256']), 'manifest')
    if isinstance(manifest_data, MissingEvidence):
        return manifest_data
    document = _manifest_document(manifest_data, str(artefact['path']))
    if isinstance(document, MissingEvidence):
        return document
    sources = _manifest_sources(document)
    if sources is None:
        return MissingEvidence('manifest', str(artefact['path']),
                               'it binds a source that names no path and digest')
    if not sources:
        return MissingEvidence('manifest', str(artefact['path']), 'it names no source files to audit')
    verified: dict[str, bytes] = {}
    for relative, sha256 in sources:
        data = read_artefact(root, relative, sha256, 'source')
        if isinstance(data, MissingEvidence):
            return data
        verified[relative] = data
    return verified
