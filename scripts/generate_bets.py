#!/usr/bin/env python3
"""Render the planned GIST experiment register from its JSON master."""
from __future__ import annotations
import argparse
import json
import textwrap
from pathlib import Path

from docs_validation.markdown import generated_matches
ROOT = Path(__file__).resolve().parents[1]
START = '<!-- bets:start -->'
END = '<!-- bets:end -->'

def paragraph(text: str) -> str:
    """Wrap a bet field as an 80-column Markdown paragraph.

    For example, ``paragraph('short field')`` returns ``'short field\\n\\n'``.
    """
    return textwrap.fill(text, 80, break_long_words=False, break_on_hyphens=False) + '\n\n'

def render(bets: list[dict]) -> str:
    """Render bet records as the generated section body, preserving field order.

    For example, passing a valid record with ID ``B01`` and title
    ``Bounded cost`` yields output beginning ``## B01. Bounded cost``.
    """
    output = []
    for bet in bets:
        output.append(f"## {bet['id']}. {bet['title']}\n\n")
        for label, key in [('Hypothesis', 'hypothesis'), ('Success witness', 'success_witness'),
                           ('Negative control', 'negative_control'), ('Falsifier', 'falsifier'),
                           ('Decision rule', 'decision_rule'), ('Measurement', 'measurement')]:
            output.append(paragraph(label + ': ' + bet[key]))
        output.append(paragraph('Requirements: ' + ', '.join(bet['requirements']) +
                                '. Tasks: ' + ', '.join(bet['tasks']) + '.'))
        output.append(paragraph('Status: ' + bet['status'] + '.'))
    return ''.join(output).rstrip()

def main() -> int:
    """Check or update the generated bet section from the JSON register.

    For example, ``python scripts/generate_bets.py --check`` reports whether
    the generated section matches and returns zero when it does.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT/'docs/testable-bets.md'
    text = path.read_text(encoding='utf-8')
    if text.count(START) != 1 or text.count(END) != 1:
        raise SystemExit('Exactly one bet marker pair is required.')
    before, rest = text.split(START)
    _, after = rest.split(END)
    bets = json.loads((ROOT/'spec/bets.json').read_text())['bets']
    expected = before + START + '\n\n' + render(bets) + '\n\n' + END + after
    if args.check:
        if not generated_matches(text, render(bets), START, END):
            raise SystemExit('Bet register differs from spec/bets.json.')
        print('Bet register matches the hypothesis ledger.')
    else:
        path.write_text(expected, encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
