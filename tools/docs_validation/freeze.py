"""Reject edits to frozen governance records relative to a base revision.

Accepted decisions, registered acceptance controls, and accepted exceptions
are append-only: a later change must arrive as a new record (a superseding
decision, an authorized amendment, or a replacement exception) rather than as
an edit. Recomputing a stored digest in the same commit cannot hide an edit,
because this check compares with the base revision's committed content, not
with the head's own claims. CI passes the merge base; without a base revision
the check does not run and says so.

`FROZEN_DOCUMENTS` lists the registers compared. Each governance register
joins it in the commit that creates the register: decisions and acceptance
controls (with their amendment chain) now; exceptions when they are added.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping

from .context import ValidationContext, require

SUPERSESSION_FIELDS = frozenset({'lifecycle', 'superseded_by'})


def committed_json(context: ValidationContext, revision: str, path: str) -> dict | None:
    """Read JSON from a revision; a path absent at that revision returns None."""
    result = subprocess.run(['git', 'show', f'{revision}:{path}'], cwd=context.root, capture_output=True,
                            text=True, check=False)
    if result.returncode != 0:
        require('does not exist' in result.stderr or 'exists on disk, but not in' in result.stderr,
                f'Cannot read {path} at base revision {revision}: {result.stderr.strip()}')
        return None
    return json.loads(result.stdout)


def check_decisions_frozen(base: dict, head: dict) -> None:
    """Allow an accepted decision to change only by becoming superseded; deletion and edits fail."""
    head_records = {record['id']: record for record in head['decisions']}
    for record in base['decisions']:
        if record['lifecycle'] not in {'accepted', 'superseded'}:
            continue
        current = head_records.get(record['id'])
        require(current is not None, f"Accepted decision {record['id']} was deleted; supersede it instead")
        changed = {key for key in record.keys() | current.keys() if record.get(key) != current.get(key)}
        if record['lifecycle'] == 'accepted' and current['lifecycle'] == 'superseded':
            changed -= SUPERSESSION_FIELDS
        require(not changed, f"Accepted decision {record['id']} was edited ({', '.join(sorted(changed))}); "
                             'supersede it instead')


def check_controls_frozen(base: dict, head: dict) -> None:
    """Allow a registered control to change only by appending an amendment that replaces the base digest."""
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


FROZEN_DOCUMENTS: Mapping[str, Callable[[dict, dict], None]] = {
    'spec/decisions.json': check_decisions_frozen,
    'spec/acceptance-controls.json': check_controls_frozen,
}


def check_frozen(context: ValidationContext, base_rev: str | None) -> str:
    """Compare each frozen register with the base revision; return a summary for the caller to print.

    Parameters
    ----------
    context
        The validation context whose root is a Git work tree.
    base_rev
        The revision to compare with, or None to skip the check.

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
        base = committed_json(context, base_rev, path)
        if base is None:
            continue
        check(base, context.load(path))
        compared.append(path)
    return f"Freeze check against {base_rev} passed for {', '.join(compared) or 'no frozen registers'}."
