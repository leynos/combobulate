"""Exercise supersession lifecycle chains in the decision register."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.decisions import check_register_records, validate_register
from test_decision_register import SCHEMA, accept, accepted_register, record


DecisionRecord = dict[str, object]
DecisionRegister = dict[str, list[DecisionRecord]]


def free_identifier(register: DecisionRegister, first: int) -> str:
    """Return the first ``D<n>`` at or after ``first`` the register does not already use.

    The suite builds replacement records on top of the committed register, so a
    hard-coded identifier starts colliding the moment the register grows to it.
    Allocating one keeps these cases about supersession rather than about which
    numbers the repository happens to have taken.

    Examples
    --------
    With D15 and D16 committed, asking from 16 names the next free record::

        free_identifier(accepted_register(), 16)
        # 'D17'
    """
    used = {str(entry['id']) for entry in register['decisions']}
    candidate = first
    while f'D{candidate}' in used:
        candidate += 1
    return f'D{candidate}'


def supersede_decision(register: DecisionRegister, replacement_id: str, lifecycle: str) -> DecisionRecord:
    """Replace accepted D03 with a new record in the requested lifecycle."""
    older = record(register, 'D03')
    replacement = copy.deepcopy(older)
    replacement.update({
        'id': replacement_id, 'subject': f'Replacement for {older["subject"]}',
        'lifecycle': lifecycle, 'decided_option': None, 'accepted_by': None,
        'accepted_on': None, 'approval_reference': None, 'adr': None,
        'supersedes': ['D03'], 'superseded_by': None, 'retired_statements': [],
    })
    older.update({'lifecycle': 'superseded', 'superseded_by': replacement_id})
    register['decisions'].append(replacement)
    return replacement


class SupersessionLifecycle(unittest.TestCase):
    """Every supersession chain preserves an accepted terminal decision."""

    def test_withdrawn_replacement_cannot_retire_an_accepted_decision(self) -> None:
        """Reject a withdrawn record as the replacement for an accepted decision."""
        register = accepted_register()
        withdrawn = free_identifier(register, 16)
        replacement = supersede_decision(register, withdrawn, 'withdrawn')
        live_proposal = copy.deepcopy(replacement)
        live_proposal.update({
            'id': free_identifier(register, 17), 'subject': 'Open alternative for Q4',
            'lifecycle': 'proposed', 'supersedes': [], 'superseded_by': None,
        })
        register['decisions'].append(live_proposal)
        validate_register(register, SCHEMA)
        with self.assertRaisesRegex(
                AssertionError, f'{withdrawn} must be accepted before superseding D03'):
            check_register_records(register)

    def test_accepted_replacement_can_supersede_an_accepted_decision(self) -> None:
        """Accept a valid D01-authorized replacement of an accepted decision."""
        register = accepted_register()
        replacement = free_identifier(register, 16)
        supersede_decision(register, replacement, 'proposed')
        accept(register, replacement)
        validate_register(register, SCHEMA)
        check_register_records(register)

    def test_supersession_chain_may_end_at_accepted_replacement(self) -> None:
        """Accept an acyclic supersession chain whose newest record is accepted."""
        register = accepted_register()
        intermediate_id = free_identifier(register, 16)
        intermediate = supersede_decision(register, intermediate_id, 'proposed')
        accept(register, intermediate_id)
        final_id = free_identifier(register, 17)
        final = copy.deepcopy(intermediate)
        final.update({
            'id': final_id, 'subject': 'Final replacement for Q4', 'lifecycle': 'proposed',
            'decided_option': None, 'accepted_by': None, 'accepted_on': None,
            'approval_reference': None, 'supersedes': [intermediate_id], 'superseded_by': None,
        })
        intermediate.update({'lifecycle': 'superseded', 'superseded_by': final_id})
        register['decisions'].append(final)
        accept(register, final_id)
        validate_register(register, SCHEMA)
        check_register_records(register)


if __name__ == '__main__':
    unittest.main()
