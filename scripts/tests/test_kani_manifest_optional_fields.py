"""Hold the manifest's optional fields to the values they default to (VO-11b).

A manifest is the half of a decision the log cannot supply: which harnesses are
claims, which properties controls must fail, and which claims panic on purpose.
Every one of those is an optional key in the JSON a record binds, so a default
that inverted would still parse, still decide, and still disagree with what the
manifest's author wrote — the record would be refused or accepted for a reason
that has nothing to do with the proof.

Each case reads one optional key through ``manifest_from_document``, which is the
reader a bound record actually uses, and asserts the value the decision then
consumes. The constructed-fact suite in ``test_kani_log_decide.py`` enumerates
what the decision does with those values; this module pins how they are read.

Examples
--------
>>> reading({}).should_panic
False
>>> reading({'should_panic': True}).should_panic
True
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.kani_log import manifest_from_document

NAME = 'harnesses::verified'
CLAIM = 'claim'


def reading(entry: dict) -> object:
    """Read one claim entry, with the fields every entry needs supplied."""
    document = {'name': NAME, 'role': CLAIM}
    document.update(entry)
    return manifest_from_document({'harnesses': [document]}).claims[0]


class ShouldPanicDefault(unittest.TestCase):
    """Read the flag that excuses a failed assertion, in both directions."""

    def test_an_entry_without_the_key_is_not_a_panic_harness(self):
        """Require the absence of the key to mean "ordinary claim".

        Almost every claim in the corpus omits the key, so a default of ``True``
        would make every failed assertion look like the outcome it asked for.
        """
        self.assertFalse(reading({}).should_panic,
                         'a claim with no should_panic key must not read as a panic harness')

    def test_an_entry_stating_the_flag_keeps_it(self):
        """Require the flag to survive the reader, since a claim may carry it."""
        self.assertTrue(reading({'should_panic': True}).should_panic,
                        'a should_panic claim must keep its flag through the document reader')


class AbsentOptionalFields(unittest.TestCase):
    """Read the two remaining optional keys, whose defaults narrow the claim."""

    def test_an_entry_without_covers_declares_no_witnesses(self):
        """Require no declared covers, which makes the record's witness list empty.

        A cover is a success witness, so inventing one would let a run report a
        satisfied witness it never declared and never printed.
        """
        self.assertEqual(reading({}).covers, (),
                         'a claim with no covers key must declare no witnesses')

    def test_an_entry_without_an_expected_failure_names_none(self):
        """Require the claim default, which is what admits a claim that fails nothing.

        The field is a control's declaration; ``None`` is how a claim records
        that it has nothing to fail on purpose.
        """
        self.assertIsNone(reading({}).expected_failure,
                          'a claim with no expected_failure key must name no property')


if __name__ == '__main__':
    unittest.main()
