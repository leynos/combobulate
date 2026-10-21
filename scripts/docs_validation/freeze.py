"""Reject edits to frozen governance records relative to a base revision.

Accepted decisions, registered acceptance controls, and accepted exceptions
are append-only: a later change must arrive as a new record (a superseding
decision, an authorized amendment, or a replacement exception) rather than as
an edit. Recomputing a stored digest in the same commit cannot hide an edit,
because this check compares with the base revision's committed content, not
with the head's own claims. CI passes the merge base; without a base revision
the check does not run and says so.

`FROZEN_DOCUMENTS` lists the registers compared. Each governance register
joins it in the commit that creates the register: decisions, acceptance
controls (with their amendment chain), and exceptions.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TypeAlias

from .adr_naming import ADR_NAME, canonical_adr_path
from .context import ValidationContext, require

SUPERSESSION_FIELDS = frozenset({'lifecycle', 'superseded_by'})
RevisionJsonReader: TypeAlias = Callable[[str, str], dict | None]
RevisionBytesReader: TypeAlias = Callable[[str, str], bytes | None]
CurrentBytesReader: TypeAlias = Callable[[str], bytes | None]


def check_decisions_frozen(base: dict, head: dict,
                           relocated_adr_ids: frozenset[str] = frozenset()) -> None:
    """Allow supersession and verified ADR moves; reject other frozen decision edits."""
    head_records = {record['id']: record for record in head['decisions']}
    for record in base['decisions']:
        if record['lifecycle'] not in {'accepted', 'superseded'}:
            continue
        current = head_records.get(record['id'])
        require(current is not None, f"Accepted decision {record['id']} was deleted; supersede it instead")
        changed = {key for key in record.keys() | current.keys() if record.get(key) != current.get(key)}
        if record['lifecycle'] == 'accepted' and current['lifecycle'] == 'superseded':
            changed -= SUPERSESSION_FIELDS
        if changed == {'adr'} and record['id'] in relocated_adr_ids:
            changed.clear()
        require(not changed, f"Accepted decision {record['id']} was edited ({', '.join(sorted(changed))}); "
                             'supersede it instead')


def unchanged_adr_relocations(base: dict, head: dict, base_rev: str,
                              read_bytes_at_revision: RevisionBytesReader,
                              read_current_bytes: CurrentBytesReader) -> frozenset[str]:
    """Identify accepted ADR links whose files moved without any content change.

    The move qualifies only when the destination name is the canonical name
    its own title implies. A byte-identical copy parked at an unrelated slug
    therefore stays a frozen-record edit.
    """
    head_records = {record['id']: record for record in head['decisions']}
    relocated = set()
    for record in base['decisions']:
        if record['lifecycle'] != 'accepted':
            continue
        current = head_records.get(record['id'])
        if current is None:
            continue
        changed = {key for key in record.keys() | current.keys() if record.get(key) != current.get(key)}
        if current['lifecycle'] == 'superseded':
            changed -= SUPERSESSION_FIELDS
        if changed != {'adr'}:
            continue
        old_path, new_path = record.get('adr'), current.get('adr')
        if not isinstance(old_path, str) or not isinstance(new_path, str):
            continue
        if ADR_NAME.fullmatch(old_path) is None or ADR_NAME.fullmatch(new_path) is None:
            continue
        if old_path == new_path:
            continue
        original = read_bytes_at_revision(base_rev, old_path)
        if original is None or read_bytes_at_revision(base_rev, new_path) is not None:
            continue
        if read_current_bytes(old_path) is not None:
            continue
        replacement = read_current_bytes(new_path)
        if replacement is None:
            continue
        if canonical_adr_path(replacement.decode('utf-8', errors='replace')) != new_path:
            continue
        if replacement == original:
            relocated.add(record['id'])
    return frozenset(relocated)


def check_controls_frozen(base: dict, head: dict) -> None:
    """Freeze register metadata; permit control changes only through appended amendments."""
    require(head.get('frozen_fields') == base.get('frozen_fields'),
            'Registered frozen_fields list was edited in place')
    require(head.get('outcome_verdicts') == base.get('outcome_verdicts'),
            'Registered outcome_verdicts mapping was edited in place')
    head_controls = {control['id']: control for control in head['controls']}
    for control in base['controls']:
        current = head_controls.get(control['id'])
        require(current is not None, f"Registered control {control['id']} was deleted")
        require(current['registered_digest'] == control['registered_digest'],
                f"Registered control {control['id']} changed its registration digest")
        prefix = current['amendments'][:len(control['amendments'])]
        require(prefix == control['amendments'], f"Registered control {control['id']} edited or removed an amendment")
        if current['digest'] != control['digest']:
            added = current['amendments'][len(control['amendments']):]
            require(bool(added) and added[0]['replaces'] == control['digest'],
                    f"Registered control {control['id']} changed frozen fields without an amendment replacing "
                    f"{control['digest'][:12]}")


def check_exceptions_frozen(base: dict, head: dict) -> None:
    """Forbid altering or deleting an approved exception; a change is a new exception."""
    head_entries = {entry['id']: entry for entry in head['exceptions']}
    for entry in base['exceptions']:
        require(head_entries.get(entry['id']) == entry,
                f"Approved exception {entry['id']} was altered or deleted; add a replacement instead")


FROZEN_DOCUMENTS: Mapping[str, Callable[[dict, dict], None]] = {
    'spec/decisions.json': check_decisions_frozen,
    'spec/acceptance-controls.json': check_controls_frozen,
    'spec/exceptions.json': check_exceptions_frozen,
}


def check_frozen(context: ValidationContext, base_rev: str | None,
                 read_json_at_revision: RevisionJsonReader,
                 read_bytes_at_revision: RevisionBytesReader | None = None,
                 read_current_bytes: CurrentBytesReader | None = None) -> str:
    """Compare each frozen register with the base revision; return a summary for the caller to print.

    For example, a test can supply a fixed base register without invoking Git::

        check_frozen(context, 'base', lambda revision, path: base_register)

    Parameters
    ----------
    context
        The validation context containing the current register files.
    base_rev
        The revision to compare with, or None to skip the check.
    read_json_at_revision
        A repository reader that returns the committed JSON value, or None
        only when the register did not exist at that revision. The CLI supplies
        the Git adapter; unit tests can supply a deterministic reader.
    read_bytes_at_revision
        Optional reader for committed files, used to verify an unchanged ADR
        relocation. Omitting it leaves ADR pointers fully frozen.
    read_current_bytes
        Optional reader for current files, paired with the revision reader to
        verify that the old path was removed and the new path is unchanged.

    Returns
    -------
    str
        A one-line summary naming the registers compared, or why none were.

    Raises
    ------
    AssertionError
        When a frozen record was deleted or edited, or the base revision cannot be read.
    """
    if base_rev is None:
        return 'Freeze check not run: no --base-rev supplied.'
    compared = []
    for path, check in FROZEN_DOCUMENTS.items():
        base = read_json_at_revision(base_rev, path)
        if base is None:
            continue
        current = context.load(path)
        relocation_readers = (read_bytes_at_revision, read_current_bytes)
        if path == 'spec/decisions.json' and all(relocation_readers):
            relocated = unchanged_adr_relocations(base, current, base_rev, *relocation_readers)
            check(base, current, relocated)
        else:
            check(base, current)
        compared.append(path)
    return f"Freeze check against {base_rev} passed for {', '.join(compared) or 'no frozen registers'}."
