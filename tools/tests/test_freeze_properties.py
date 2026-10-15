"""Generate accepted-decision mutations against the base-revision freeze rule."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

from hypothesis import given, settings, strategies as st
from hypothesis.strategies import DrawFn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.freeze import check_decisions_frozen

GENERATED = settings(max_examples=80, derandomize=True, deadline=None)
DecisionRecord = dict[str, object]
Mutation = tuple[str, DecisionRecord]
ACCEPTED: DecisionRecord = {
    'id': 'D04', 'subject': 'Package licence', 'lifecycle': 'accepted', 'decided_option': 'A',
    'supersedes': [], 'superseded_by': None, 'accepted_by': 'leynos', 'accepted_on': '2026-10-10',
    'approval_reference': {'kind': 'session', 'url': 'https://example.org/session',
                           'author_login': 'leynos', 'names_decisions': ['D04'], 'answer': 'Accepted'},
    'adr': 'docs/adrs/adr-0004-package-licence.md', 'retired_statements': [],
}
MUTABLE_FIELDS = ('id', 'subject', 'lifecycle', 'decided_option', 'supersedes', 'superseded_by',
                  'accepted_by', 'accepted_on', 'approval_reference', 'adr', 'retired_statements')


@st.composite
def forbidden_mutations(draw: DrawFn) -> st.SearchStrategy[Mutation]:
    """Generate a changed value for each frozen decision field, including its identity."""
    field = draw(st.sampled_from(MUTABLE_FIELDS))
    replacements = {
        'id': st.just('D05'),
        'subject': st.text(min_size=1, max_size=20).filter(lambda value: value != ACCEPTED['subject']),
        'lifecycle': st.sampled_from(('proposed', 'withdrawn')),
        'decided_option': st.sampled_from(('B', 'C', None)),
        'supersedes': st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=3),
        'superseded_by': st.text(min_size=1, max_size=5).filter(lambda value: value != ACCEPTED['superseded_by']),
        'accepted_by': st.text(min_size=1, max_size=12).filter(lambda value: value != ACCEPTED['accepted_by']),
        'accepted_on': st.dates().map(lambda value: value.isoformat()).filter(lambda value: value != ACCEPTED['accepted_on']),
        'approval_reference': st.just({'kind': 'session', 'url': 'https://example.org/other',
                                       'author_login': 'leynos', 'names_decisions': ['D04'],
                                       'answer': 'Accepted'}),
        'adr': st.just('docs/adrs/adr-0016-new-policy.md'),
        'retired_statements': st.just([{'document': 'docs/roadmap.md', 'text': 'Changed claim'}]),
    }
    changed = copy.deepcopy(ACCEPTED)
    changed[field] = draw(replacements[field])
    return field, changed


class DecisionFreezeProperties(unittest.TestCase):
    """Check that generated accepted-record mutations cannot bypass the freeze."""

    @GENERATED
    @given(mutation=forbidden_mutations())
    def test_every_generated_accepted_field_mutation_fails(self, mutation: Mutation) -> None:
        """Reject edits to identity and every mutable field of an accepted decision."""
        field, changed = mutation
        with self.assertRaisesRegex(
            AssertionError, 'Accepted decision D04 was (edited|deleted)',
            msg=f'mutation of {field} must violate the accepted-decision freeze',
        ):
            check_decisions_frozen(
                {'decisions': [ACCEPTED]},
                {'decisions': [changed]},
            )

    @GENERATED
    @given(replacement=st.integers(min_value=1, max_value=99))
    def test_only_a_linked_supersession_transition_may_change_acceptance(self, replacement: int) -> None:
        """Allow the explicit accepted-to-superseded transition while retaining its new link."""
        changed = ACCEPTED | {'lifecycle': 'superseded', 'superseded_by': f'D{replacement:02}'}
        check_decisions_frozen({'decisions': [ACCEPTED]}, {'decisions': [changed]})

    @GENERATED
    @given(mutation=forbidden_mutations())
    def test_generated_mutations_of_superseded_records_always_fail(self, mutation: Mutation) -> None:
        """Keep superseded records fully frozen even when a mutation resembles supersession."""
        _field, changed = mutation
        superseded = ACCEPTED | {'lifecycle': 'superseded', 'superseded_by': 'D16'}
        with self.assertRaisesRegex(AssertionError, 'Accepted decision D04 was (edited|deleted)'):
            check_decisions_frozen({'decisions': [superseded]}, {'decisions': [changed]})


if __name__ == '__main__':
    unittest.main()
