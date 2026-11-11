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

A refusal is returned rather than printed. The gate can name only the reason
code it produced, and every refusal collapses to the same one, so the artefact,
the path, and the reason an adapter refused would otherwise be lost. Returning
them keeps the queries queries: nothing here writes to a stream, so a caller
that only wants admissions is not made to launder a diagnostic it never asked
for, and a caller that does want one — the CLI, or a validation gate — renders
:class:`Refusal` through :func:`report`. The refusals travel with the checked
values because they describe the same pass over the same records.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .evidence_gate import VerifiedLogResult, VerifiedTrustAudit
from .kani_log.shell import KANI, MissingEvidence, bind_verdict, bound_sources
from .trust_audit import TrustAuditError, audit_bound_tree, items_of

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


@dataclass(frozen=True, slots=True)
class Refusal:
    """Why one record's claim was refused, in the words its author can act on.

    The gate can only say ``verdict-self-reported`` or ``trust-unaudited``,
    which are the same two words whether a log was tampered with, untracked, or
    simply named at the wrong path. A record's author has no other channel, so
    the artefact, the path, and the reason are carried here until a boundary
    renders them.

    A value rather than a printed line, because binding runs inside queries
    whose callers may and may not want a diagnostic. Printing chose for them:
    a checker that admits records as one step among many had its standard error
    filled by a seam it never called for, and a caller that needed the detail as
    data had to capture a stream to get it back.
    """

    record: str
    what: str
    path: str
    reason: str

    def __str__(self) -> str:
        """
        Render the line a reader scans for the id, the class, the path, and the reason.

        Examples
        --------
        >>> str(Refusal('EV-1', 'log', 'a.log', 'it is not tracked'))
        "EV-1: log 'a.log' was refused: it is not tracked"
        """
        return f'{self.record}: {self.what} {self.path!r} was refused: {self.reason}'


def refusal_for(record: Mapping[str, object], missing: MissingEvidence) -> Refusal:
    """Return the refusal one failed binding produces for ``record``.

    A record with no id is labelled rather than left blank: the fallback is the
    only name a reader gets for a record that cannot name itself.
    """
    return Refusal(str(record.get('id', 'record')), missing.what, missing.path, missing.reason)


def report(refusals: Iterable[Refusal]) -> None:
    """Write each refusal on its own line of standard error.

    This is the boundary's job rather than the query's. :func:`checked_inputs`
    returns what it could not bind, and the caller that owns a human audience —
    the CLI, or a validation gate — is the one that decides the detail belongs
    on standard error, beside the other diagnostics the gate writes there.

    Examples
    --------
    >>> report([])
    """
    for refusal in refusals:
        print(refusal, file=sys.stderr)


def log_result(root: Path, record: Mapping[str, object],
               parsers: frozenset[str]) -> VerifiedLogResult | Refusal | None:
    """Re-derive one record's verdict, or say why no adapter could.

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
    VerifiedLogResult | Refusal | None
        The parser's facts; a :class:`Refusal` when an adapter ran and could
        not bind its artefacts; or None when no adapter had anything to do —
        the record claims no parsed verdict, or names an unregistered tool.
        The third case is not a refusal: nothing was attempted, so there is no
        artefact to name. The gate judges both non-results as self-reported.

    Examples
    --------
    A record whose ``method.tool`` is ``"Verus"`` returns None even though it
    cites a log, because no Verus adapter exists yet. A record citing a log
    whose bytes changed returns a refusal naming the log.
    """
    if not _claims_parsed_verdict(record):
        return None
    adapter = _adapter_for(record, parsers, ADAPTERS)
    if adapter is None:
        return None
    result = adapter(root, record)
    if isinstance(result, MissingEvidence):
        return refusal_for(record, result)
    return result


def trust_audit(root: Path, record: Mapping[str, object],
                parsers: frozenset[str]) -> VerifiedTrustAudit | Refusal | None:
    """Scan the sources one record's manifest names, or say why it could not.

    The audit is bound to the record's single result artefact, which is the
    harness manifest: the gate compares that identity with the record's, so an
    audit of some other manifest cannot stand in for this one. The verdict
    adapter binds the same artefact for the same reason, so the two results of
    one record describe one manifest rather than two records' worth of them.

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
    VerifiedTrustAudit | Refusal | None
        What the scanner found in the manifest's sources; a :class:`Refusal`
        when the scanner ran and could not read what the record cites; or None
        when the record claims no audit to perform. Every non-result demotes
        the record's trust claim to ``unaudited`` (DL-16), which blocks
        verifier evidence.

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
        return refusal_for(record, sources)
    try:
        # The bound walk, not the working-tree one: `bound_sources` has already
        # checked each source's digest, and re-reading the files here would
        # audit bytes nobody vouched for. It also refuses a module the bound
        # set does not name, which is the same DL-16 escape one level down.
        files = audit_bound_tree(root, sources)
    except TrustAuditError as error:
        return Refusal(str(record.get('id', 'record')), 'trust audit',
                       str(record['result_artefacts'][0]['path']), str(error))
    artefact = record['result_artefacts'][0]
    items = tuple((str(item['item']), str(item['location'])) for item in items_of(files))
    return VerifiedTrustAudit(manifest_path=str(artefact['path']),
                              manifest_sha256=str(artefact['sha256']), items=items)


@dataclass(frozen=True, slots=True)
class CheckedInputs:
    """Everything one admission pass derived from the records it was given.

    The refusals travel with the values because they describe the same pass
    over the same records: a caller that wanted only the two de-duplicated value
    lists would have to bind every record a second time to learn why the rest
    contributed nothing. A refusal is not an error — the gate already treats an
    unbound record as self-reported, and that verdict is unchanged — so it is
    returned here rather than raised.
    """

    logs: tuple[VerifiedLogResult, ...]
    audits: tuple[VerifiedTrustAudit, ...]
    refusals: tuple[Refusal, ...]

    def pair(self) -> tuple[tuple[VerifiedLogResult, ...], tuple[VerifiedTrustAudit, ...]]:
        """Return the two value lists in the shape :func:`admit_record` accepts.

        The gate reads only these two, so the admission call sites take them as
        a pair rather than the whole value: which is also why the refusals are
        not silently iterable alongside them. A caller that discarded a refusal
        by unpacking should have to say so.

        Examples
        --------
        >>> CheckedInputs((), (), ()).pair()
        ((), ())
        """
        return self.logs, self.audits


def checked_inputs(root: Path, records: list[Mapping[str, object]],
                   parsers: frozenset[str]) -> CheckedInputs:
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
    CheckedInputs
        The parser results and scanner audits, each in record order and each
        distinct value exactly once, plus the refusals that kept the other
        records from contributing anything. Only the values are de-duplicated:
        two records may cite the same broken log, and each author needs the
        refusal that names their own record.

    Examples
    --------
    The same record admitted twice contributes one result, not two. The gate
    asks that exactly one candidate match a record's tool, log and manifest
    identity, so a duplicated result would make a sound record look ambiguous
    and demote it to ``verdict-self-reported``. Equal values came from the same
    bytes decided against the same manifest, so they are one fact. Two records
    citing one log but binding different manifests are *not* equal: each
    verdict was decided against a different claim set, and collapsing them
    would let one record answer for the other.
    """
    logs, audits, refusals = [], [], []
    for record in records:
        result = log_result(root, record, parsers)
        audit = trust_audit(root, record, parsers)
        refusals.extend(item for item in (result, audit) if isinstance(item, Refusal))
        logs.extend(item for item in (result,) if isinstance(item, VerifiedLogResult))
        audits.extend(item for item in (audit,) if isinstance(item, VerifiedTrustAudit))
    # Both value types are frozen dataclasses over hashable fields, so
    # `dict.fromkeys` is an ordered de-duplication that preserves record order.
    return CheckedInputs(tuple(dict.fromkeys(logs)), tuple(dict.fromkeys(audits)),
                         tuple(refusals))
