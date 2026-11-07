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

Amended by ADR-0009 (2026-10-14): clerical fixture relocation, recorded in
[Amendments](#amendments). Amended by ADR-0009 (2026-11-07): scanner-derived
trust audits, the trust-audit matching rule, Kani partial bounds, and the Kani
parser's registration, recorded in [Amendments](#amendments).

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
  `restricted`. Record-sourced components fail closed when no record matches
  the current binding. The latest record by `recorded_on` among current-binding
  records must be admitted at an accepted level; ties fail closed. Any record
  at that source revision that reports a counterexample vetoes satisfaction,
  regardless of its admission level. A component whose evidence source is
  `checker:<check>` is satisfied when the latest result for that check passes
  in the same validation run at the current source revision, the component
  accepts `tested`, and no evidence record for it reports a counterexample at
  that revision. A checker result is `tested` evidence only and needs no
  separate verifier record. For example, `PF14.structural@1.1.4` cites the
  `evidence-gate` check.
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

A verdict counts as parsed only when a registered adapter supplies a verified
result for the tool, committed log path, and digest named by the record. The
adapter reads the log, validates its digest, and derives the outcome, bounds,
witnesses, negative controls, and run mode. The pure gate checks that this
result matches the record; registration alone is insufficient. Otherwise the
verdict is self-reported (fail closed). No parser is registered or integrated
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
owner, and a release gate, and it lasts at most 90 days. Passing that gate
expires it immediately, even when its `invalid_from` date is later.

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

## Amendments

### 2026-10-14: Fixture relocation

The Python tooling relocation on 2026-10-12 moved the evidence-gate fixture from
`tools/tests/fixtures/evidence_gate_rules.json` to
`scripts/tests/fixtures/evidence_gate_rules.json`. Use the latter path in the
current repository. The accepted rule table and policy are unchanged; the
original path above remains part of the accepted record's history.

### 2026-11-07: Scanner-derived trust audits and the Kani parser (DL-10, DL-16, DL-17)

The rule table, the ten abstract fields, the base levels, and properties P1-P6
are unchanged. Three parts of the policy are now implemented rather than
reserved, and each is stated here because it changes what a record must supply.

**Trust audits are scanner-derived (DL-16).** `AdmissionContext` carries
`verified_trust_audits` alongside `verified_log_results`. The I/O shell reads
every source file the record's harness manifest names, requires each path to be
Git-tracked and inside the repository, checks each file's digest against the
manifest, runs the scanner over it, and passes a `VerifiedTrustAudit` bound to
the same manifest. `abstract_record` then derives `trust = 'unaudited'` unless
an audit bound to the record's single `result_artefacts` manifest has an item
multiset `(item, location)` equal to the record's `trust_audit.items`. A record
that claims `audited` with no matching scan is therefore `unaudited`, which
MS-1 already blocks for deductive and bounded evidence. A record whose
`method.tool` names a registered parser must have `evidence_kind` `deductive` or
`bounded`, so a failed verifier run cannot be renamed a passing test to step
outside the parser; that rejection reuses `schema-invalid`.

**The trust-audit matching rule (DL-17).** The scanner lexes Rust, skips
comments and literals, and reports an identifier as a trusted item when it is:

1. a Kani vocabulary item reached through a path or `use` tree rooted at
   `kani`, including `kani::any_where` and `#[cfg_attr(kani, kani::stub(..))]`;
2. a Verus vocabulary item inside a `verus!` body, a `#[verifier::…]`,
   `#[verifier(…)]`, `#[verus_verify(…)]`, or `#[verus_spec(…)]` attribute, a
   `cfg_attr` carrying one of those, or a `use` tree rooted at `vstd` or
   `verus_builtin`; or
3. any unqualified vocabulary identifier in a file that imports from `kani`,
   `vstd`, or `verus_builtin` by glob or alias.

An unqualified `should_panic`, `assume`, or `external` in a file with no such
import is ordinary Rust and is not reported; without rule (iii) the vocabulary
would flag ordinary code. The Verus list also covers
`external_trait_specification`, `assume_specification[…]`, and
`exec_allows_no_decreases_clause`. The scan fails closed, never with an empty
audit, on an unterminated comment or literal, `include!`, an out-of-tree
`#[path]`, `paste!`, or `concat_idents!`.

**Kani bounds are always partial (DL-10).** The 1.2.1 Kani parser derives
`bounds = partial` for every record it decides, so no 1.2.1 record can reach
`proof` through Kani however complete its run. Deriving `type-complete` moves
to task 1.2.4 with its own mechanical rule and its own amendment, because a
manifest declaration of type-completeness would be self-reporting on the one
field that separates `proof` from `bounded`.

**Registration.** `kani` is now a registered log parser in
`spec/evidence-reason-codes.json`. The sentence above saying no parser is
registered or integrated yet is superseded: the adapter is
`scripts/docs_validation/evidence_binding.py` with the parser in
`scripts/docs_validation/kani_log/`, and `make design-check` refuses a
registration whose committed corpus does not reach every outcome class the gate
keys on, including an unsatisfied cover. Verus remains unregistered and its
parser deferred to task 1.2.4.
