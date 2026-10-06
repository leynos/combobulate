"""Validate costs claims in the design pack without claiming Rust evidence."""
from __future__ import annotations

import math
from .context import ValidationContext, require


def classify_admission(case: dict) -> str:
    """Classify budget intervals; unknown cost always needs a runtime obligation."""
    kind = case['classification']
    if kind in {'estimate', 'unknown'}:
        return 'runtime-obligation-or-strict-refusal'
    lo, hi, limit = case['lower'], case['upper'], case['budget']
    require(isinstance(lo, int) and isinstance(hi, int) and 0 <= lo <= hi,
            'Malformed cost interval')
    if lo > limit:
        return 'certain-excess'
    if hi <= limit:
        return 'certified-within-model'
    return 'uncertifiable-domain'


def shape_product(case: dict) -> int | str:
    """Bound a shape product by target usize width; [65536, 65536] overflows 32 bits."""
    shape = case['shape']
    require(all(isinstance(dimension, int) and dimension >= 0 for dimension in shape),
            'Invalid shape model')
    value = math.prod(shape)
    return value if value <= (1 << case['target_bits']) - 1 else 'overflow'


def right_prefix_work(case: dict) -> int:
    """Count reductions over all prefixes; length 3 needs 3 operations."""
    length = case['length']
    require(length >= 0, 'Negative prefix length')
    return length * (length - 1) // 2


def tracked_peak(case: dict) -> int:
    """Count distinct live allocations plus scratch; repeated alias IDs count once."""
    return max(sum(case['capacities'][key] for key in set(stage['live']))
               + stage['scratch'] for stage in case['stages'])


COST_MODELS = {
    'admission': classify_admission, 'product': shape_product,
    'right-prefix-work': right_prefix_work, 'tracked-peak': tracked_peak,
}


def check_cost_examples(context: ValidationContext) -> None:
    """Validate worked costs and controls; this does not execute Rust const evaluation."""
    cases = context.load('spec/cost-cases.json')['cases']
    require(len({case['id'] for case in cases}) == len(cases), 'Duplicate cost example ID')
    for case in cases:
        kind = case['kind']
        require(kind in COST_MODELS, f'Unknown cost example kind {kind}')
        result = COST_MODELS[kind](case)
        require(result == case['expected'], f'Wrong cost result {case["id"]}: {result}')
    by_id = {c['id']: c for c in cases}
    require(classify_admission(by_id['K01']) != classify_admission(by_id['K02']),
            'Exact/bounded distinction is vacuous')
    require(classify_admission(by_id['K04']) != 'certified-within-model',
            'Unknown-as-zero negative control failed')
    alias = by_id['K12']
    wrong_peak = max(sum(alias['capacities'][key] for key in stage['live'])
                     + stage['scratch'] for stage in alias['stages'])
    require(wrong_peak != alias['expected'], 'Alias-count negative control is vacuous')
    require(by_id['K08']['expected'] != by_id['K09']['expected'],
            'Target-width distinction is vacuous')
    context.record('cost-documentation-examples', 'Python checks exact/interval/unknown admission, target-width/zero arithmetic, prefix work and distinct-allocation accounting, with wrong-bound and alias controls. No Rust const or verifier execution occurred.', len(cases))
