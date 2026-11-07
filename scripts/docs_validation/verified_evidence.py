"""Carry what an adapter re-derived, so the gate can compare it with a record's claim.

The gate is pure: it decides admission from the submitted record plus a small
set of caller-owned inputs. Those inputs are the values a verifier adapter
produced by reading the exact artefacts a record cites, and the gate compares
them with the record rather than trusting the record's own fields.

Both values here follow the same shape. An adapter constructs one only after
reading bytes and verifying their digest; the value names the artefact it was
derived from, so a result from one log can never be mistaken for a result from
another. :meth:`VerifiedLogResult.matches_record` and
:meth:`VerifiedTrustAudit.matches_record` then hold the record to what was
actually found, which is what keeps a claim a claim rather than evidence.

They live in their own module so :mod:`docs_validation.evidence_gate` stays
about the rule table, and so a caller that only carries these values (the
binding adapters, for instance) need not import the admission rules at all.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerifiedLogResult:
    """Facts re-derived by a parser from the exact log named by one record.

    An adapter creates this value only after reading the log, verifying its
    digest, and deriving every admission-relevant result from its contents.
    The pure gate also checks that these facts match the submitted record.
    """

    tool: str
    log_path: str
    log_sha256: str
    outcome: str
    bounds: str
    witness_statuses: tuple[str, ...]
    negative_controls: tuple[tuple[bool, str], ...]
    run_mode: str

    def matches_record(self, record: Mapping[str, object]) -> bool:
        """Confirm the parser-derived admission facts agree with the record."""
        method = record['method']
        bounds = record['bounds']
        witnesses = tuple(str(item['status']) for item in record['success_witnesses'])
        controls = tuple((bool(item['required']), str(item['observed'])) for item in record['negative_controls'])
        return (self.outcome == record['outcome'] and self.bounds == bounds['kind']
                and self.witness_statuses == witnesses and self.negative_controls == controls
                and self.run_mode == method['run_mode'])


@dataclass(frozen=True, slots=True)
class VerifiedTrustAudit:
    """Items a scanner found in the sources one record's manifest names (DL-16).

    The scanner reports ``(item, location)`` pairs and nothing else: which
    assumption covers an item is the record author's claim, so ``covered_by``
    stays out of the multiset the gate compares. The manifest identity binds
    the audit to the record, because a record's ``result_artefacts`` names the
    manifest whose ``sources`` were scanned.
    """

    manifest_path: str
    manifest_sha256: str
    items: tuple[tuple[str, str], ...]

    def matches_record(self, record: Mapping[str, object]) -> bool:
        """Confirm the audit is bound to the record and found exactly what it claims.

        Both halves matter. An audit of some other manifest says nothing about
        this record, and an audit that found fewer items than the record lists
        is the fabricated-empty case DL-16 exists to reject.
        """
        artefact = manifest_artefact(record)
        if artefact is None:
            return False
        if (self.manifest_path, self.manifest_sha256) != artefact:
            return False
        claimed = tuple(sorted((str(item['item']), str(item['location']))
                               for item in record['trust_audit']['items']))
        return claimed == tuple(sorted(self.items))


def manifest_artefact(record: Mapping[str, object]) -> tuple[str, str] | None:
    """Return the one result artefact a parsed claim is decided from, or None.

    A rule that reads exactly one artefact is a rule a record cannot satisfy by
    listing several, so more than one is as unusable as none.
    """
    artefacts = record.get('result_artefacts') or ()
    if not isinstance(artefacts, Sequence) or len(artefacts) != 1:
        return None
    only = artefacts[0]
    if not isinstance(only, Mapping) or not isinstance(only.get('path'), str) \
            or not isinstance(only.get('sha256'), str):
        return None
    return str(only['path']), str(only['sha256'])
