"""Edit committed Kani logs the way a broken producer, or a corrupt file, would.

The extractor's mutation tests all start from a real log and change one thing:
cut it short, delete a line, raise a count, splice a block into the middle of
another. They share the line vocabulary those edits are expressed in, so it
lives here rather than in either test module — one definition of "a line that
carries report structure" is what keeps the deletion sweep honest.

Nothing here decides what is correct. Each helper returns text; whether the
extractor must refuse it is the test's claim.

Examples
--------
>>> refused('not a log') is not None
True
>>> bump_first_number(' ** 3 of 4 failed')
' ** 4 of 4 failed'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kani_corpus_fixtures as corpus
from docs_validation.kani_log import KaniLogError, parse

EXPECTED = json.loads(corpus.corpus_root().joinpath('expected.json').read_text(encoding='utf-8'))
HARNESS_START = 'Checking harness '
MANUAL = 'Manual Harness Summary:'
COMPLETE = 'Complete - '
RESULTS = 'RESULTS:'
SUMMARY = 'SUMMARY:'
TIME = 'Verification Time: '
VERIFICATION = 'VERIFICATION:- '
LIST_WRITTEN = 'Wrote list results to '
# Lines that carry report structure, as opposed to the solver's own transcript
# and Cargo's build chatter. Deleting one of these must always be refused.
REPORT_PREFIXES = (
    HARNESS_START, RESULTS, SUMMARY, 'Check ', '\t - ', ' ** ', VERIFICATION, TIME,
    'Failed Checks: ', ' File: ', MANUAL, 'Verification failed for - ', COMPLETE,
)


def lines_of(name: str) -> list[str]:
    """Return one committed log as lines, which is the unit every mutation edits."""
    return corpus.log_text(name).splitlines()


def refused(text: str) -> str | None:
    """Return the structural reason a log is refused, or None when it parses."""
    try:
        parse(text)
    except KaniLogError as error:
        return error.reason
    return None


def blocks_of(name: str) -> dict[str, tuple]:
    """Return one log's blocks keyed by harness, in the table's shape."""
    parsed = corpus.parse_log(name)
    return {
        block.name: (block.verdict, block.failed_count, block.total_count, block.other_count,
                     block.other_kind, block.timed_out, block.unwinding_reported,
                     block.panics_as_expected, tuple((item.kind, item.status) for item in block.properties),
                     tuple((item.description, item.status) for item in block.covers))
        for block in parsed.blocks
    }


def table_blocks(entry: dict) -> dict[str, tuple]:
    """Return the same shape from the committed expectation for one log."""
    return {
        block['name']: (block['verdict'], block['failed'], block['total'], block['other'][0],
                        block['other'][1], block['timed_out'], block['unwinding_reported'],
                        block['panics_as_expected'],
                        tuple((kind, status) for kind, status in block['checks']),
                        tuple((description, status) for description, status in block['covers']))
        for block in entry['blocks']
    }


def harness_block(name: str) -> list[str]:
    """Return one harness's complete block, from its header to its verification time."""
    lines = lines_of(name)
    start = next(index for index, line in enumerate(lines) if line.startswith(HARNESS_START))
    end = next(index for index in range(start, len(lines)) if lines[index].startswith(TIME))
    return lines[start:end + 1]


def insert_block(lines: list[str], block: list[str], after: str) -> list[str]:
    """Splice ``block`` into ``lines`` immediately after the first line starting with ``after``."""
    index = next(position for position, line in enumerate(lines) if line.startswith(after))
    return lines[:index + 1] + block + lines[index + 1:]


def bump_first_number(line: str) -> str:
    """Raise the first number in a summary line by one, breaking its count."""
    for index, character in enumerate(line):
        if character.isdigit():
            end = index
            while end < len(line) and line[end].isdigit():
                end += 1
            return line[:index] + str(int(line[index:end]) + 1) + line[end:]
    return line
