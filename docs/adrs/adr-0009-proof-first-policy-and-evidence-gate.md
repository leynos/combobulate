# Architectural decision record (ADR) 0009: Proof-first policy and evidence gate

## Status

Accepted on 2026-10-10: proof evidence is admitted by a pure gate over a
ten-field abstract model, using the ordered rule table below. A record reaches
`proof`, `bounded`, or `tested` only when nothing blocks it. Exceptions only
ever restrict a record. Self-reported verifier verdicts are never `proof` or
`bounded`. This ADR implements the exception policy (D02) and the proof
interface policy (D06) recorded in the
[decision register](../decision-register.md), and the public proof
compatibility subject assigned here by D07.

## Date

2026-10-10.

## Context and problem statement

Technical design §17 requires machine-checked evidence before a semantic claim
is complete. It also says that a timeout, a skipped harness, an empty
generator, or a vacuous witness is never success. The version 1 proof-evidence
schema mixed evidence kind with result in one `status` field, so contradictory
records were schema-valid. It also trusted each record's own description of its
verdict, assumptions, and binding. A check that only reads a record's
self-description admits a fabricated record. Roadmap task 1.1.4 asks for the
gate rules to be specified before the gate is implemented.

## Decision drivers

- Every failure mode named in technical design §17 and bets B01, B02, and
  B08 must be rejected, each with its own reason.
- The rules must be small enough to state as a table, check exhaustively, and
  replay from Rust (task 1.2.4).
- Admission must not depend on the wall clock, the environment, or the
  network.
- An exception must never stand in for proof.

## Abstract model

A record is abstracted to ten fields:

- `kind`: deductive, bounded, test, trust-declaration, or none.
- `outcome`: verified, counterexample, resource-exhausted, solver-unknown,
  unsupported, skipped, not-run, or tool-error.
- `bounds`: not-applicable, type-complete, or partial.
- `witness`: all-satisfied, some-unsatisfied, or absent.
- `controls`: all-required-rejected-as-intended, some-rejected-otherwise,
  some-accepted, or required-missing.
- `trust`: audited-none, audited-all-covered, audited-uncovered, or unaudited.
- `exception`: none, active, expired, not-yet-valid, or malformed.
- `binding`: current, stale, or incomplete.
- `run_mode`: full-profile or focused.
- `verdict_source`: log-parser or self-reported.

The product has 345,600 states. The validity predicate admits 86,400 of them:
nothing ran exactly when the kind is `none` or `trust-declaration`, and only
`bounded` evidence has bounds. Schema version 2 enforces the same predicate.

## Rule table

Screen reader description: the table lists the gate's ordered rules, one per
row. Each row gives the rule's condition and its effect on the reasons and the
level.

| Rule | Condition                                                         | Effect                                         |
| ---- | ----------------------------------------------------------------- | ---------------------------------------------- |
| MS-0 | The validity predicate fails                                      | `rejected`, reason `schema-invalid`            |
| MS-1 | An executed kind has an outcome other than `verified`             | Blocking reason `outcome-<value>`              |
| MS-1 | `witness` is not `all-satisfied`                                  | Blocking reason `witness-<value>`              |
| MS-1 | `controls` is not `all-required-rejected-as-intended`             | Blocking reason `control-<value>`              |
| MS-1 | Deductive or bounded evidence with `trust` uncovered or unaudited | `trust-uncovered` or `trust-unaudited`         |
| MS-1 | `exception` is expired, not yet valid, or malformed               | Blocking reason `exception-<value>`            |
| MS-1 | `binding` is not `current`                                        | Blocking reason `binding-<value>`              |
| MS-1 | `run_mode` is `focused`                                           | Blocking reason `run-focused`                  |
| MS-1 | Deductive or bounded evidence with a self-reported verdict        | Blocking reason `verdict-self-reported`        |
| MS-1 | `kind` is `none`                                                  | Blocking reason `not-run`                      |
| MS-1 | A trust declaration without an active exception                   | Blocking reason `trust-without-exception`      |
| MS-2 | Any blocking reason                                               | `rejected`                                     |
| MS-2 | No blocking reason and an active exception                        | `restricted`, informational `exception-active` |
| MS-2 | Otherwise                                                         | Base level, below                              |

_Table 1: Admission rules, applied in order._

The base level is `proof` for deductive evidence and for bounded evidence with
type-complete bounds. It is `bounded` for bounded evidence with partial bounds,
`tested` for tests, and `restricted` for trust declarations.
`tools/tests/fixtures/evidence_gate_rules.json` states the same table as data;
reason codes are single-sourced in `spec/evidence-reason-codes.json`.

## Components and closure

- MS-3. A proof-obligation component (`PFnn.<method>@<task>`) lists the
  levels it accepts, a subset of `proof`, `bounded`, and `tested`; never
  `restricted`. It is satisfied when its latest record is admitted at an
  accepted level and no record at that source revision reports a
  counterexample. A component whose evidence source is `checker:<check>` is
  satisfied when that design check passes in the same run. For example,
  `PF14.structural@1.1.4` cites the `evidence-gate` check.
- MS-4. A roadmap task may be ticked only when its prerequisites are ticked,
  its completion record cites accepted decisions and resolvable artefacts, and
  every component linked to it is satisfied.

## Properties

The tests check these over the full enumeration, against both the
implementation and the rule table:

- P1, degradation monotonicity: making a field worse never raises the level.
  For a trust declaration, an active exception is better than none.
- P2, diagnostic soundness: a record is rejected exactly when a blocking
  reason exists, and remedying one field removes exactly its reason.
- P3: no state with an exception satisfies a component.
- P4: partial bounds never reach `proof`.
- P5: the evaluation date affects only the exception state.
- P6: a counterexample at the current source revision reopens every
  dependent task.

## Trust audit and verdicts

A verdict counts as parsed only when a log parser is registered for the tool in
`spec/evidence-reason-codes.json` and the record names its committed log with a
digest. Otherwise it is self-reported (fail closed). No parser is registered
yet; tasks 1.2.1 and 1.2.4 build the parsers and the trust-audit scanner, whose
item vocabulary is fixed here:

- Verus: `assume`, `admit`, `external_body`, `external`,
  `external_fn_specification` (or `assume_specification`), and
  `external_type_specification`.
- Kani: `kani::assume`, `stub`, `stub_verified`, and `should_panic`.

## Public proof contract

The public proof interface consists of the logical models, preconditions,
postconditions, lemmas, and trust declarations. It is versioned with the crate
under ADR-0005 (D06): a strengthened precondition or a weakened postcondition
is breaking even without a Rust signature change. Released proof-interface
changes and exceptions are accepted by the D01 authority. Exceptions follow D02
and live in `spec/exceptions.json`. An exception names a narrowed claim, an
owner, and a release gate, and it lasts at most 90 days.

## Command line

`scripts/check_evidence.py --as-of DATE [--require LEVEL] RECORD...` prints
`path: level [reasons]` for each record. It exits 0 when every record reaches
the required level (default `tested`), 1 when any falls short, and 2 for a
schema-invalid record or a usage error.

## Consequences

- Version 1 records are not accepted; no dual-schema reading exists (terms of
  reference C5).
- Until log parsers exist, verifier evidence cannot satisfy a proof-only
  component. This is deliberate.
- Rust tooling replays the rule table in task 1.2.4. The Python gate remains
  the documentation-model reference until then.
