# Evidence and decision records

This document is for anyone who produces or consumes Combobulate's governance
records: proof-evidence records, exceptions, decisions, acceptance controls,
and task-completion records. It states each record's schema, who writes it, and
what the design checks do with it.
[ADR-0009](adrs/adr-0009-proof-first-policy-and-evidence-gate.md) states the
admission rules and their rationale.

## Proof-evidence records

A record lives in `spec/evidence/` and follows
`spec/proof-evidence.schema.json`, schema version 2. Each record carries
evidence for exactly one proof-obligation component, named in `component` as
`PFnn.<method>@<task>`. The fields that decide admission are:

| Field               | Meaning                                                                                               |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| `evidence_kind`     | `deductive` (Verus), `bounded` (Kani), `test`, `trust-declaration`, or `none` (planned)               |
| `outcome`           | The verifier's or test's result; anything but `verified` blocks admission                             |
| `bounds.kind`       | `type-complete` or `partial` for bounded evidence; otherwise `not-applicable`                         |
| `success_witnesses` | At least one; each Kani `cover!` is listed; any `unsatisfied` or `not-observed` blocks admission      |
| `negative_controls` | At least one; each must be `rejected-as-intended`, and rejection for another reason blocks            |
| `trust_audit`       | Audited trusted items, each covered by a declared assumption or exception, or else blocking           |
| `binding`           | Executable and specification digests and source revision, compared with `spec/evidence-bindings.json` |
| `method.run_mode`   | `full-profile`; a `focused` run blocks admission                                                      |
| `verdict_source`    | `log-parser` (with the committed log and its digest) or `self-reported`                               |
| `exception`         | `null` or an identifier in `spec/exceptions.json`                                                     |

_Table 1: Fields that decide admission._

The schema enforces the validity predicate: an executed kind has an outcome
other than `not-run`, `none` and trust declarations have `not-run`, and only
bounded evidence has bounds. Fields such as `claim`, `outcome_detail`,
`declared_assumptions`, and `result_artefacts` inform reviewers but do not
change admission.

## Admission levels and reason codes

The gate admits a record at `proof`, `bounded`, `tested`, `restricted`, or
`rejected`. Only the first three can satisfy a component, and each component
lists which of them it accepts. Every blocking condition contributes one reason
code; the codes and their meanings are single-sourced in
`spec/evidence-reason-codes.json`. A record that cites an active exception is
`restricted`, with the informational code `exception-active`.

## Verdict sources and log parsers

A verifier verdict counts as parsed only when the tool has a registered log
parser in `spec/evidence-reason-codes.json` (`registered_log_parsers`) and the
record names its committed log with a digest. None is registered yet, so
deductive and bounded records are `verdict-self-reported` and rejected. Tasks
1.2.1 and 1.2.4 own the parsers and the trust-audit scanner, with these
obligations:

- A parser re-derives the outcome, every `cover!` result, every negative
  control's observed failure, and the run mode from the raw log, and rejects a
  log it cannot fully parse.
- The scanner lists every trusted item: for Verus, `assume`, `admit`,
  `external_body`, `external`, `external_fn_specification` (or
  `assume_specification`), and `external_type_specification`; for Kani,
  `kani::assume`, `stub`, `stub_verified`, and `should_panic`.
- Each parser is registered only together with tests over real logs,
  including a timeout, an unsatisfied cover, and a skipped harness.

## Command line

```bash
scripts/check_evidence.py --as-of 2026-10-11 spec/evidence/*.json
```

The command prints `path: level [reasons]` for each record. It exits 0 when
every record reaches `--require` (default `tested`), 1 when any falls short,
and 2 for a schema-invalid record or a usage error. Options name other binding,
parser, or exception files; the test fixtures in
`tools/tests/fixtures/evidence/` use a test-only parser registry so the
`bounded` level is reachable.

## Exceptions

`spec/exceptions.json` (schema `spec/exception.schema.json`) holds trusted
boundary exceptions under decision D02. An exception names its component,
owner, narrowed claim, reason, release gate (task 4.3.3 or 6.3.4), approval by
the sponsor, `approved_on`, and `invalid_from`. It is valid from `approved_on`
up to, but excluding, `invalid_from`, for at most 90 days. Renewal is a new
exception with a new identifier. An approved exception is never edited; the
freeze check rejects an edit or deletion.

## Decisions, controls, and completion records

- Decisions: `spec/decisions.json`, rendered into the
  [decision register](decision-register.md); see the developers' guide for the
  acceptance workflow.
- Acceptance controls: `spec/acceptance-controls.json`, registered under
  [ADR-0008](adrs/adr-0008-acceptance-control-pre-registration.md) and
  calibrated in [acceptance calibration](acceptance-calibration.md).
- Task completion: `spec/task-completion.json` names, for each ticked roadmap
  task, the decisions it relies on and the artefacts that complete it.

## Kernel-contract evidence status

Native kernel declarations (`spec/kernel-contract.schema.json`) keep their own
`evidence.status` vocabulary. It maps onto admission levels as follows:
`proposed` is evidence kind `none` (rejected as `not-run`);
`tested-with-bounds` is at most `tested` or `bounded`, depending on the record;
and `proved-with-assumptions` is at most `proof`, and only when every
assumption is a covered trusted item. The kernel contract's status is a
declaration; the evidence record and the gate decide admission.
