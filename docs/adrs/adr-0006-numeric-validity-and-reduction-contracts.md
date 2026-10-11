# Architectural decision record (ADR) 0006: Numeric, validity, and reduction contracts

## Status

Accepted on 2026-10-10: the numeric, validity, reduction, typed-cell, and
commit contracts below are Combobulate's semantic baseline, recorded as `SC-01`
to `SC-09` in `spec/semantic-contracts.json`. Records D09, D10, and D14, and
the numerical and array semantics subject assigned here by D07, in the
[decision register](../decision-register.md).

## Date

2026-10-10.

## Context and problem statement

Technical design §6 proposed Combobulate's numeric and reduction semantics, but
left several choices open: how binary `min` and `max` treat NaN and signed
zeros, what an empty F64 `sum` returns, how large `mean` counts are bounded, how
`div` rounds large I64 operands, and what "typed-cell atomicity" meant.
Without fixed answers, an implementation could pass its tests while differing
from the proofs that later tasks must discharge (PF07, PF01, PF05), and a
backend could substitute a cheaper but different aggregation.

## Decision drivers

- One logical contract per primitive, independent of any backend, so a
  backend aggregation is eligible only when it matches exactly.
- Failure equivalence: a regrouped or fused computation must fail exactly
  when the specified one fails.
- Every rule must be executable as an example and falsifiable by a seeded
  mutation before any Rust exists.

## Decision outcome

- Dtypes and conversion (`SC-04`). Core dtypes are Bool, I64, and F64; Bool is
  not an integer subtype. Mixed-dtype arithmetic requires an explicit `cast`.
  Bool converts to 0 or 1; I64 converts to F64 rounding to nearest, ties to
  even; F64 converts to I64 only when finite, integral, and in `[-2^63, 2^63)`,
  with `-0.0` giving zero. No numeric value converts to Bool.
- Integer division (`SC-03`). `idiv` truncates towards zero and `rem` takes
  the dividend's sign; a zero divisor and `MIN / -1` fail.
- True division (`SC-05`, D14). `div` converts each operand to F64 first,
  then applies IEEE 754 division. This matches Rust's `as f64` and common
  backends; it can differ from rounding the exact quotient once, as
  `div(2^53 + 1, 3)` shows.
- Validity and logic (`SC-06`). Null is validity metadata, never NaN.
  Arithmetic propagates null; `and`, `or`, and `not` follow Kleene three-valued
  logic; `xor` is unknown when either operand is unknown. Aggregates apply the
  null policy first: propagate by default, or `.skip_nulls()` removes invalid
  values in order and then the empty rule applies.
- Association (`SC-01`). `reduce` is exact right association without
  permutation, `fold_left` is left association, and `scan` and `scan_left`
  return those values for each nonempty prefix. A singleton passes through.
  `.reassociate()` permits another grouping only with a safe-domain proof, an
  equivalent algorithm, or a separately accepted numeric policy.
- Empty lanes (`SC-02`). The registered identities are typed zero for `sum`,
  one for `product`, false for `any`, and true for `all`. `minimum`, `maximum`,
  and `mean` have none: empty input fails unless `.identity(value)` supplies a
  result of the output dtype. An identity is used only for an empty lane and is
  never a seed.
- F64 special values (`SC-07`, D09). Binary `min` and `max` follow IEEE
  754-2019 `minimum` and `maximum`: null takes precedence over NaN, NaN
  propagates, and `-0.0` is less than `+0.0`. An empty F64 `sum` is `+0.0`,
  while `sum([-0.0])` is `-0.0` because a singleton passes through. `mean`
  converts to F64, right-sums, and divides by a count of at most 2^53.
- Cell atomicity (`SC-08`, D10). A typed cell such as `DVec3` is one logical
  element until an explicit component operation: `Batch<DVec3>` of shape
  `[2,3]` has cardinality 6, and its axes index the frame only.
- Atomic output commit (`SC-09`, D10). Failure or cancellation before commit
  leaves the destination unchanged; no partial output is observable.

## Consequences

- `spec/examples.json` holds tagged-scalar examples (`EX21` to `EX71`) for
  every rule, and each contract names seeded mutations (left association, floor
  division, an erroring empty sum, an identity used as a seed, implicit
  promotion, NaN-ignoring `min`, two-valued logic, exact-quotient `div`, cell
  flattening, partial output) that the documentation model shows change an
  outcome.
- Each contract carries a proof sketch for the Verus lemmas and Kani harnesses
  that its discharging obligation component must provide; task 1.2.3 replays
  the examples as `rstest` cases.
- Native Polars aggregations that differ, such as NaN-ignoring minima or
  reassociated sums, are ineligible unless a later decision accepts a named
  numeric policy.
