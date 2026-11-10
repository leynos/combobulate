"""Bind the artefacts one evidence record cites to what a parser and a scanner derive (VO-12).

The evidence gate is pure and cannot read a file, but a record's verdict and its
trust audit are both claims about files: a log the tool wrote and the sources
the manifest names. This module is the seam that turns those claims into the two
checked values ``AdmissionContext`` accepts — :class:`VerifiedLogResult` and
:class:`VerifiedTrustAudit` — so the gate can compare them with the record
instead of believing it.

Two policies decide what this seam reads, and both are about authority rather
than convenience:

- Only Git-tracked paths are read. A log created after the last review is not
  evidence any commit contains, so binding it would let a record cite an
  artefact that disappears with the working tree.
- Only paths inside the repository are read, checked on the resolved path so a
  ``..`` component cannot borrow the root's prefix to escape it.

Registration decides *whether* a tool's adapter runs; this module decides only
what it is handed. A record naming a tool no adapter reads yields no result at
all, which leaves the record ``self-reported`` — the fail-closed direction
ADR-0009 states, because tool registration alone must never admit a verdict
(C-EP-10).

A refusal is reported rather than swallowed. The gate can name only the reason
code it produced, and every refusal collapses to the same one, so the artefact,
the path, and the reason an adapter refused are printed on standard error where
the record's author can act on them.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from .evidence_gate import VerifiedLogResult, VerifiedTrustAudit
from .kani_log.shell import KANI, MissingEvidence, bind_verdict, bound_sources
from .trust_audit import TrustAuditError, audit_tree, items_of

# Adapters are keyed by the tool name a record writes, which is the name the
# registry lists. Keeping the map here means a record for an unregistered tool
# is distinguishable from one no adapter implements, without the gate knowing
# either name.
ADAPTERS = {KANI: bind_verdict}
# The files each adapter's scanner starts from. A manifest names *sources*, and
# a source is scanned with its own module tree, so the driver list is the source
# list rather than the manifest itself.
SCANNERS = {KANI: bound_sources}


def _claims_parsed_verdict(record: Mapping[str, object]) -> bool:
    """Report whether a record claims a verdict a parser could re-derive.

    A record claiming ``self-reported`` needs no binding: it already makes the
    weaker statement, and the gate treats it as such. Checking first keeps the
    seam from reading files on behalf of a claim the record never made.
    """
    source = record['verdict_source']
    return isinstance(source, Mapping) and source.get('kind') == 'log-parser'


def _adapter_for(record: Mapping[str, object], parsers: frozenset[str], table: Mapping):
    """Return the adapter a record's tool selects, if it is registered and known."""
    tool = str(record['method']['tool'])
    if tool not in parsers:
        return None
    return table.get(tool)


def _refusal(record: Mapping[str, object], missing: MissingEvidence) -> None:
    """Report one refused claim on standard error, naming the artefact that failed.

    The gate can only say ``verdict-self-reported`` or ``trust-unaudited``,
    which are the same two words whether a log was tampered with, untracked, or
    simply named at the wrong path. A record's author has no other channel, so
    the refusal detail is reported here rather than discarded; the trust audit
    already reports its scanner failures the same way.
    """
    print(f'{record.get("id", "record")}: {missing.what} {missing.path!r} was refused: '
          f'{missing.reason}', file=sys.stderr)


def log_result(root: Path, record: Mapping[str, object],
               parsers: frozenset[str]) -> VerifiedLogResult | None:
    """Re-derive one record's verdict, or return None when no adapter may.

    Parameters
    ----------
    root
        Repository root; every artefact must resolve inside it and be tracked.
    record
        A schema-valid evidence record.
    parsers
        The registered parser names from ``spec/evidence-reason-codes.json``.

    Returns
    -------
    VerifiedLogResult | None
        The parser's facts, or None when the record claims no parsed verdict,
        names an unregistered tool, or names a tool this seam has no adapter
        for. An adapter that *is* run and cannot bind its artefacts also
        returns None, after reporting the refusal on standard error: the gate
        then judges the record as self-reported.

    Examples
    --------
    A record whose ``method.tool`` is ``"Verus"`` returns None even though it
    cites a log, because no Verus adapter exists yet.
    """
    if not _claims_parsed_verdict(record):
        return None
    adapter = _adapter_for(record, parsers, ADAPTERS)
    if adapter is None:
        return None
    result = adapter(root, record)
    if isinstance(result, MissingEvidence):
        _refusal(record, result)
        return None
    return result


def trust_audit(root: Path, record: Mapping[str, object],
                parsers: frozenset[str]) -> VerifiedTrustAudit | None:
    """Scan the sources one record's manifest names, or return None.

    The audit is bound to the record's single result artefact, which is the
    harness manifest: the gate compares that identity with the record's, so an
    audit of some other manifest cannot stand in for this one.

    Parameters
    ----------
    root
        Repository root; the manifest and every source must be tracked.
    record
        A schema-valid evidence record.
    parsers
        The registered parser names.

    Returns
    -------
    VerifiedTrustAudit | None
        What the scanner found in the manifest's sources, or None when the
        record is not claiming a parsed verdict, claims no audit, names no
        adapter, or cites a source the scanner cannot read. None demotes the
        record's trust claim to ``unaudited`` (DL-16), which blocks verifier
        evidence, and a refusal is reported on standard error.

    Examples
    --------
    A record whose ``trust_audit.status`` is ``"unaudited"`` returns None: it
    claims nothing a scan could confirm.
    """
    if not _claims_parsed_verdict(record) or record['trust_audit']['status'] != 'audited':
        return None
    scanner = _adapter_for(record, parsers, SCANNERS)
    if scanner is None:
        return None
    sources = scanner(root, record)
    if isinstance(sources, MissingEvidence):
        _refusal(record, sources)
        return None
    try:
        files = audit_tree(root, sources)
    except TrustAuditError as error:
        print(f'{record.get("id", "record")}: trust audit refused: {error}', file=sys.stderr)
        return None
    artefact = record['result_artefacts'][0]
    items = tuple((str(item['item']), str(item['location'])) for item in items_of(files))
    return VerifiedTrustAudit(manifest_path=str(artefact['path']),
                              manifest_sha256=str(artefact['sha256']), items=items)


def checked_inputs(root: Path, records: list[Mapping[str, object]],
                   parsers: frozenset[str]) -> tuple[tuple[VerifiedLogResult, ...],
                                                      tuple[VerifiedTrustAudit, ...]]:
    """Bind every record's cited artefacts once, for one admission pass.

    Parameters
    ----------
    root
        Repository root.
    records
        Every record about to be admitted.
    parsers
        The registered parser names.

    Returns
    -------
    tuple[tuple[VerifiedLogResult, ...], tuple[VerifiedTrustAudit, ...]]
        The parser results and scanner audits, each in record order and each
        distinct value exactly once. A record no adapter could bind contributes
        nothing.

    Examples
    --------
    Two records citing the same log contribute one result, not two. The gate
    asks that exactly one candidate match a record's ``(tool, path, digest)``,
    so a duplicated identity would make a sound record look ambiguous and
    demote it to ``verdict-self-reported``. Equal values came from the same
    bytes, so they are one fact.
    """
    logs, audits = [], []
    for record in records:
        result = log_result(root, record, parsers)
        audit = trust_audit(root, record, parsers)
        if result is not None:
            logs.append(result)
        if audit is not None:
            audits.append(audit)
    # Both value types are frozen dataclasses over hashable fields, so
    # `dict.fromkeys` is an ordered de-duplication that preserves record order.
    return tuple(dict.fromkeys(logs)), tuple(dict.fromkeys(audits))
