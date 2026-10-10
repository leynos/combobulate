# Resolve the decisions that control acceptance (roadmap 1.1)

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: DRAFT (revised after community-of-experts review; awaiting sponsor
approval)

Implementation must not begin until the sponsor explicitly approves this plan.
Approval of the plan is not acceptance of any decision record that the plan
proposes. Each acceptance is a separate, recorded act that names the decision
identifiers it accepts (see `Decisions required from the sponsor`).

## Purpose / big picture

Roadmap step 1.1 asks: which constraints are approved, and which remain
experiments? Today every Combobulate design document is labelled "proposed", no
decision has an accountable owner, no acceptance threshold exists, and the
repository's checker forbids marking any roadmap task complete. Any later
implementation could therefore have its success criteria changed after the
fact, which the terms of reference (ToR) prohibit.

After this work, a reviewer can do five observable things that are impossible
today:

1. Run `make design-check` and read `docs/decision-register.md`, a generated
   register that names, for each governing ToR question (Q1, Q2, Q4, Q7, Q8),
   the accountable authority, the option chosen, the date, the approval
   reference, and the architectural decision record (ADR) holding the
   rationale. The same run fails if any of the five governing documents still
   describes an accepted decision as open.
2. Read accepted contract records for association, empty identities, dtype
   conversion, validity, the `comb!` macro grammar, and typed-cell atomicity.
   Each record states preconditions, postconditions, empty and failure rules, a
   proof sketch for the later Verus or Kani work, and executable examples; the
   documentation model rejects deliberately wrong semantics.
3. Read pre-registered resource, performance, build, and proof controls with
   named workloads, frozen control implementations, pinned environments,
   estimands, and decision rules. A pull request that changes a registered
   threshold without an authorized amendment fails the `Design contracts`
   workflow, even if it also recomputes the stored digest.
4. Run `python3 tools/check_evidence.py` on a proof-evidence record and see a
   timeout, skipped harness, unsatisfied `cover`, negative control that failed
   for the wrong reason, unaudited or uncovered trusted assumption, stale
   binding, focused run, self-reported verdict, or expired exception rejected
   with a specific reason code, while a complete record is admitted at the
   level it has actually earned (`proof`, `bounded`, or `tested`).
5. See roadmap tasks 1.1.1 to 1.1.4 marked done through the same
   evidence-gated mechanism, not by hand-editing a checkbox.

Term definitions used throughout:

- Sponsor: the project sponsor named in ToR §4. Only the sponsor, or an
  authority the sponsor designates in an accepted record, can accept a
  decision. The implementing agent drafts and recommends; it never accepts.
- Decision record: an entry in `spec/decisions.json`, rendered into
  `docs/decision-register.md`, usually with an ADR in `docs/`. Its lifecycle is
  `proposed`, `accepted`, `superseded`, or `withdrawn`.
- Contract record: an entry in `spec/semantic-contracts.json` stating one
  public primitive's logical contract, independent of any implementation. It
  takes its acceptance from a decision record.
- Pre-registration: recording a measurement's workload, control,
  environment, estimand, and decision rule before any acceptance measurement,
  so the threshold cannot be tuned to the result.
- Obligation component: one independently dischargeable part of a proof
  obligation in `spec/proof-obligations.json`, identified as
  `PFnn.<method>@<task>` (for example `PF14.structural@1.1.4`). A component
  states which admission levels satisfy it.
- Evidence gate: the pure admission function in
  `tools/docs_validation/evidence_gate.py` that maps one evidence record to an
  admission level and a set of reason codes.
- Negative control: a deliberately broken input that a check must reject for
  the intended reason. A check with no failing negative control is vacuous.

## Constraints

- C-EP-1. Do not invent owners, accepted thresholds, release dates, or
  deployment claims (ToR C6). An `accepted` record must carry a structured
  approval reference to a durable GitHub artefact (a pull request review or
  comment, or a commit) whose author login matches an authority designated by
  an accepted D01 record (D01 itself by the sponsor), and whose text names the
  decision identifiers it accepts. Ambiguous approval ("looks good") accepts
  nothing; the agent asks again.
- C-EP-2. Approval is not verification (roadmap 1.1.1). No accepted decision
  may change a proof obligation's status, mark a bet as run, or record a
  capability as eligible.
- C-EP-3. Retain `comb!` ergonomics and names (ToR C2). The grammar contract
  must not introduce `a!`, glyph notation, or an alternate pipeline macro.
- C-EP-4. No compatibility machinery (ToR C5, technical design §15). The
  proof-evidence schema change (to `schema_version` 2) updates every consumer
  and fixture atomically; no dual-schema acceptance, alias field, or deprecated
  enum value.
- C-EP-5. Generated documents stay generated. `docs/roadmap.md`,
  `docs/testable-bets.md`, `docs/language-reference.md` (catalogue region), and
  `docs/decision-register.md` change only through their JSON masters and
  generators.
- C-EP-6. The design-model checker remains a documentation-model checker. It
  must not claim Rust compilation, Kani, Verus, or Polars results; the
  `NOT_RUN` list in `tools/check_docs.py` stays truthful.
- C-EP-7. Python tooling follows the existing `tools/` conventions (modules
  in `tools/docs_validation/`, `unittest` plus pinned Hypothesis with
  `derandomize=True`, dependencies in `tools/requirements.txt`). No Python file
  exceeds 400 lines. Checks perform no network access.
- C-EP-8. No Rust library behaviour, public API, or Rust dependency changes.
  The only permitted Rust-adjacent edit is `Cargo.toml` package metadata
  (`license`, `publish`) if D04 or D05 requires it.
- C-EP-9. Checks are deterministic for a given commit. The evidence gate
  never reads the wall clock; `make design-check` injects the HEAD commit date
  as `--as-of`, and the base revision for freeze checks as `--base-rev`. No
  check reads environment variables.
- C-EP-10. Fail closed. Until a log parser registered for a verifier
  re-derives a record's verdict from a committed raw log (task 1.2.4 onward),
  no record from that verifier can be admitted at `proof` or `bounded`. Until
  `EP-M5` lands, no task with a linked proof-obligation component can be marked
  done.
- C-EP-11. Gates run sequentially through the `scrutineer` agent, with
  output captured under `/tmp`. `make fmt` (which writes files) runs before,
  never inside, a scrutineer gate run.

If satisfying the objective requires violating a constraint, stop, record the
conflict in `Decision log`, set the status to `BLOCKED`, and escalate.

## Tolerances (exception triggers)

- Scope per milestone: more than 25 changed files or more than 1,500 net
  added lines (excluding generated Markdown regions,
  `docs/validation-results.json`, and the gate rule fixture) triggers
  escalation. The whole step is estimated at about 75 changed files across
  seven milestones; if the estimate grows past 95, escalate.
- Owner input: if a milestone needs a sponsor decision not yet given, set the
  status to `BLOCKED` at that milestone and ask, naming the decision
  identifiers. If no answer arrives within 10 working days, report the block
  rather than waiting silently. Do not proceed to a dependent milestone on a
  guessed answer.
- Upstream conflict: if a sponsor decision contradicts an explicit user
  constraint (ToR C1 to C9) or changes an authority listed in ToR §9 (for
  example D01 choosing a sole authority where ToR §9 names "Sponsor and
  technical owner" for Q2 and Q4), present the conflict and the required
  upstream edit before accepting.
- Interface: if a Rust public API, Rust dependency, or Make target name must
  change, stop and escalate. New Make variables (`AS_OF`, `BASE_REV`) on the
  existing `design-check` target are in scope. If a Rust contract test in
  `tests/` pins the edited Makefile or workflow text, update that test in the
  same commit; if the change would alter a tested contract's meaning, escalate.
- Dependencies: a Python dependency beyond `tools/requirements.txt` triggers
  escalation.
- Iterations: a gate still failing after three fix attempts for the same
  cause triggers escalation with the log path.
- Ambiguity: success text with two materially different readings that the
  sponsor has not resolved triggers a presentation of both readings with a
  recommendation.

## Risks

- Risk: the sponsor is unavailable, leaving decisions unaccepted.
  Severity: high. Likelihood: medium. Mitigation: `EP-M1a` and `EP-M1b` deliver
  all machinery with every record `proposed`, a coherent plateau needing no
  owner input. The generated register presents every question with options and
  a recommendation, so one review can answer them all. D01 is requested first
  because every other acceptance depends on it.
- Risk: the gate tests its own inputs' self-description, so a fabricated
  record passes. Severity: high. Likelihood: high without mitigation.
  Mitigation: C-EP-10 (verdicts for `proof` and `bounded` must be re-derived
  from committed logs by a registered parser); provenance and log digests in
  the schema; the complete admit-at-`proof` fixture lives only under
  `tools/tests/fixtures/`, never in `spec/`.
- Risk: a threshold and its digest are edited together in one commit.
  Severity: high. Likelihood: medium. Mitigation: the base-revision freeze
  check (VO-7) compares against the merge base in CI; `.github/CODEOWNERS`
  names the sponsor for governance files; D13 asks the sponsor to enable
  code-owner review and require the `Design contracts` check on `main`.
- Risk: an exception expires and breaks CI for an unrelated contributor.
  Severity: medium. Likelihood: medium. Mitigation: a 14-day warning printed
  (not recorded in the report); a weekly scheduled `Design contracts` run so
  expiry surfaces on `main` first; a renewal runbook in
  `docs/developers-guide.md` naming the exception owner as responder.
- Risk: the decision table and the implementation share an error because one
  author wrote both from the same prose. Severity: medium. Likelihood: medium.
  Mitigation: the compact rule table is part of ADR-009, so sponsor acceptance
  makes it the specification; substantive admission properties are checked
  against the table itself; an upstream scenario corpus derived from the bet
  register and proof ledger (not from ADR-009) checks both.
- Risk: text-based cross-document checks are evaded by rewording or broken by
  rewrapping. Severity: medium. Likelihood: medium. Mitigation: positive
  anchors (each accepted question's ToR §9 row links its register entry),
  whitespace- and inline-Markdown-normalized matching for retired statements,
  and a per-question open-status pattern check.
- Risk: pre-registered thresholds prove unattainable. Severity: medium.
  Likelihood: high. Mitigation: authorized pre-measurement amendments; a
  post-measurement change becomes a new control identifier with the original
  result retained; the bet decision rules absorb failure honestly.
- Risk: governance Python grows beyond what one maintainer will sustain.
  Severity: medium. Likelihood: medium. Mitigation: per-module owners in
  `docs/developers-guide.md`; the grammar recognizer is retired when task 2.3.1
  replays the corpus through `trybuild`; `semantics.py` stays a capped
  documentation model, not a reference evaluator.
- Risk: `docs/validation-results.json` conflicts between stacked branches.
  Severity: low. Likelihood: high. Mitigation: milestones land sequentially;
  the documented conflict rule is "take either side, rerun the generators and
  `check_docs.py --write`".

## Progress

- [x] (2026-10-10) Reconnaissance with a Wyvern team: scope and authority,
  numeric and macro contracts, resource controls, proof-evidence schema, and
  repository tooling.
- [x] (2026-10-10) External research: Cargo pre-1.0 SemVer rules, the
  `jsonschema` Draft 2020-12 validator, Kani `cover` reporting, Criterion.rs
  bootstrap analysis, IEEE 754-2019 `minimum` and `maximum`.
- [x] (2026-10-10) First draft written and committed.
- [x] (2026-10-10) Community-of-experts review (six lenses: structure,
  alternatives, measurement cost, contracts, failure modes, long-term viability
  and assurance). Verdict: revise. See `Design review record`.
- [x] (2026-10-10) Plan revised to address every blocking finding.
- [ ] Sponsor approval of the plan.
- [ ] `EP-M1a` Decision register, generator, anchors, and CODEOWNERS draft.
- [ ] `EP-M1b` Roadmap status, obligation components, and freeze check.
- [ ] `EP-M2` Task 1.1.1: authority, scope, licence, and API policy accepted.
- [ ] `EP-M3` Task 1.1.2: semantic and macro contract records accepted.
- [ ] `EP-M4` Task 1.1.3: acceptance controls pre-registered.
- [ ] `EP-M5` Task 1.1.4: proof-first policy and evidence gate accepted.
- [ ] `EP-M6` Reconciliation, roadmap closure, and final gates.

## Surprises & discoveries

- Observation: the checker forbids any completed roadmap task.
  Evidence: `tools/docs_validation/ledger.py` `check_task_links` fails with
  "Roadmap has fabricated completed tasks"; `tools/generate_roadmap.py` always
  emits `- [ ]`. Impact: `EP-M1b` adds an evidence-gated status mechanism.
- Observation: PF14 already links task 1.1.4, with methods Verus, Kani, and
  "structural validation". Evidence: `spec/proof-obligations.json` PF14 `tasks`
  and `tools`. Impact: the first draft's claim that no 1.1 task has a proof
  obligation was false and would have deadlocked 1.1.4. Obligations gain
  per-task components; 1.1.4 discharges only `PF14.structural@1.1.4`, at level
  `tested`.
- Observation: the proof-evidence schema cannot express the outcomes 1.1.4
  must reject, and its `status` mixes evidence kind with result, so
  contradictory records (proved with timeout) are schema-valid. Evidence:
  `spec/proof-evidence.schema.json` `status` enum and conditionals. Impact:
  `EP-M5` splits `status` into `evidence_kind` and `outcome`.
- Observation: the catalogue permits Bool-to-I64 and Bool-to-F64 casts (0 or
  1) and forbids numeric-to-Bool. Evidence: `spec/vocabulary.json` V031. The
  first draft wrongly planned a "Bool to I64 rejection" example. Impact:
  corrected in VO-8.
- Observation: `syn` rejects chained comparisons with "comparison operators
  cannot be chained", so `x > 0 & y > 0` yields a parse error rather than a
  tree, while single mixes such as `a & b > c` parse silently. Impact: the D08
  rule is a syntax-tree check plus a translated parse error.
- Observation: `make design-check` fails locally because the system Python
  lacks `markdown-it-py`. Evidence:
  `ModuleNotFoundError: No module named 'markdown_it'`. Impact: concrete steps
  use
  `PYTHON="uv run --python 3.14 --with-requirements tools/requirements.txt
  python3"`,
  verified to import `markdown_it`, `jsonschema` 4.26.0, and `hypothesis`.
- Observation: `make spelling` checks only tracked files, so an untracked
  document passes until committed. Impact: commit before relying on the
  spelling gate.
- Observation: the candidate ADR set differs between documents (ToR §10
  names four subjects; technical design §15 names eight), and the bet register
  omits 1.1.1 and 1.1.2 from B01 and B02 although the roadmap tags them.
  Impact: the register carries all eight subjects with dispositions; `EP-M6`
  adds a two-way bet-to-task check.
- Observation: ISC already appears in `Cargo.toml`, `LICENSE`, and
  `README.md` through ADR 001, yet ToR Q7 and technical design GAP5 treat the
  licence as unratified. Impact: D04 ratifies or amends it.
- Observation: `make design-check` is not part of `make all` or `ci.yml`; it
  runs in `.github/workflows/design.yml` with a shallow checkout. Impact: the
  freeze check needs `fetch-depth: 0` there.

## Decision log

- Decision: implement validators and the evidence gate in Python inside
  `tools/docs_validation/`. Rationale: the design-contract checker, its JSON
  Schema validation, its Hypothesis tests, and its CI workflow live there. The
  repository also has Rust contract tests over its own files
  (`tests/markdown_wiring.rs`), so Rust was a credible alternative; it was not
  chosen because JSON Schema validation would stay in Python, splitting the
  gate across two languages before task 1.2.1 pins the toolchain. To keep the
  door open, the gate rule table is a language-neutral fixture, and D15
  proposes that task 1.2.4 replay it from Rust. Date/Author: 2026-10-10,
  planning agent, revised after review.
- Decision: no Verus or Kani in this step, a named, justified deviation from
  the general Verus requirement in `AGENTS.md`. Rationale: no Rust executable
  body is introduced. The one piece of contractual logic, the admission rule,
  ranges over a finite abstract domain that tests enumerate exhaustively, a
  complete check of that abstraction. A verifier now would pre-empt task
  1.2.1's toolchain pinning. Each contract record carries a proof sketch, so
  proof structure still shapes the accepted contracts. Residual gap: the
  mapping from JSON records to abstract states (VO-2). Date/Author: 2026-10-10,
  planning agent.
- Decision: evidence is tracked per obligation component, and closure checks
  the latest record per component and binding; a counterexample at the current
  source revision always blocks. Rationale: PF14 links 1.1.4 for its structural
  part only; "at least one admitted record" allowed cherry-picking.
  Date/Author: 2026-10-10, after Pandalump, Dinolump, and Telefono findings.
- Decision: admission levels are `proof`, `bounded`, `tested`, `restricted`,
  and `rejected`. `restricted` (an active exception) is report-only and never
  satisfies a component. Rationale: a Kani run over a partial domain must never
  be reported as proof (technical design §17.8 rejects a single `verified`
  flag; B08 negative control "label bounded as unbounded"). Date/Author:
  2026-10-10.
- Decision: the freeze and acceptance controls are the base-revision diff
  check plus CODEOWNERS; stored digests remain identity references for binding
  evidence to controls. Rationale: a digest in the same file as the value it
  protects is defeated by editing both. Date/Author: 2026-10-10, after
  Wafflecat and Doggylump findings.
- Decision: one decision per ADR, numbered ADR-002 to ADR-009 (see
  `Artefacts and notes`). Rationale: `docs/documentation-style-guide.md` states
  that an ADR captures one accepted decision; bundling licence with scope would
  force superseding both when one changes. Date/Author: 2026-10-10.
- Decision: the proof-evidence schema gains a `schema_version` field (value
  2) rather than changing the pack-wide `revision` (`0.2`). Rationale: every
  `spec/` file uses `revision` for the design-pack revision. Date/Author:
  2026-10-10.
- Decision: exceptions live in their own register, `spec/exceptions.json`,
  referenced by identifier from evidence records. Rationale: renewing an
  exception must not require rewriting digest-bound evidence. Date/Author:
  2026-10-10.
- Decision: keep a small command-line entry, `tools/check_evidence.py`, with
  documented exit codes. Rationale: it is the reviewer's way to observe the
  gate, and task 1.2.4's producers will call it; its interface is documented in
  the new component document. Date/Author: 2026-10-10.
- Decision: follow existing `tools/` conventions rather than
  `docs/scripting-standards.md`. Rationale: the new code is modules in an
  existing package plus thin entry scripts matching `tools/check_docs.py`;
  mixing pytest and `unittest` would split the `design-check` contract.
  Date/Author: 2026-10-10.
- Decision: milestones land sequentially (`EP-M3` before `EP-M4`) on stacked
  branches. Rationale: both touch the report, registers, and generated
  documents; parallel work guarantees conflicts. Date/Author: 2026-10-10.
- Decision: the kernel-contract `evidence.status` vocabulary is left
  unchanged in this step; the component document records its mapping to
  evidence kinds. Rationale: kernel contracts are an extension interface owned
  by phase 3, outside 1.1's success text. Date/Author: 2026-10-10.

## Design review record

The draft of 2026-10-10 was reviewed through six lenses. The consolidated
verdict was "revise". Blocking findings and their dispositions:

- PF14 deadlock for 1.1.4 (Pandalump, Dinolump): resolved by obligation
  components.
- MS-1 contradicted L5 (Telefono, Dinolump, Wafflecat): resolved by an
  explicit validity predicate, a `bounds` field, and the `bounded` level.
- `status` and `outcome` overlap (Telefono): resolved by `evidence_kind`.
- Self-reported trust items and verdicts (Dinolump, Doggylump, Telefono):
  resolved by `trust_audit` with auditor identity, `verdict_source` with log
  digests, and C-EP-10.
- Digest freeze defeated by a single edit (Wafflecat, Doggylump, Buzzy Bee):
  resolved by the base-revision check, CODEOWNERS, and an amendment chain.
- Unregistrable AC-04, unbound measurement environment, underspecified ratio
  statistic, unfrozen control implementations (Buzzy Bee): resolved in `EP-M4`.
- Expiry rule contradicting C-EP-9 (Doggylump): resolved by injecting the HEAD
  commit date.
- File tolerance tripping by design (Doggylump): resolved by per-milestone
  tolerances.
- VO-5 "exactly one decision per question" false on the plan's own data, no
  field for the chosen option (Telefono): resolved by `questions` lists and
  `decided_option`.
- Wrong Bool-cast example and unencodable F64 specials in JSON (Telefono):
  resolved by correcting VO-8 and a tagged scalar encoding.

Improvements adopted: a `roadmap_status.py` single owner of closure
(Pandalump); drift checking for the decisions generator; ADRs added to the
checker's document list; computed roadmap status strings; contract records
deriving acceptance from decisions; vocabulary entries citing contract
identifiers; proof sketches in contract records (Dinolump); lemmas reframed as
substantive admission properties plus an upstream scenario corpus; `syn`-aware
grammar corpus (Telefono, Wafflecat); two-way bet-to-task links;
`package_policy.py` separated; a component document for producers; per-module
owners. Considered and not adopted: a full Rust gate now (see `Decision log`);
deferring all executable grammar checks to phase 2 (it would lose the 1.1.2
red-green evidence).

## Outcomes & retrospective

Not started. Complete at each milestone boundary and at completion, comparing
the result with `Purpose / big picture`, and reconciling every discovery with
the artefacts in `Conformance basis` before setting the status to `COMPLETE`.

## Context and orientation

Combobulate is a proposed Rust array-programming library. The repository holds
a development scaffold (`src/lib.rs` exports only a disposable `greet()` stub)
and a revision 0.2 design pack. Nothing is implemented.

The five governing documents (ToR C3; `docs/context.md` §2):

- `docs/terms-of-reference.md` (ToR): goals G1 to G8, success criteria S1 to
  S11, constraints C1 to C9, open questions Q1 to Q9 (§9), candidate ADR
  subjects (§10).
- `docs/context.md`: vocabulary; §6 lists earlier suggestions and their
  superseding positions.
- `docs/technical-design.md`: requirements R1 to R11 and the Core,
  Integration, and Deferred scope classes (§2); numerical and reduction
  contracts (§6); macro grammar (§7); costs (§12); verification obligations V1
  to V20 (§14); candidate decisions and gaps GAP1 to GAP9 (§15); change control
  (§16); proof-first policy (§17); costing (§18).
- `docs/language-reference.md`: the operation catalogue, partly generated
  from `spec/vocabulary.json`.
- `docs/roadmap.md`: the GIST roadmap, generated from `spec/roadmap.json`.

Companion artefacts: `docs/testable-bets.md` (generated from `spec/bets.json`),
`spec/proof-obligations.json` (PF01 to PF14), `spec/traceability.json`,
`spec/examples.json` (EX01 to EX20), `spec/proof-evidence.schema.json` and its
example, `spec/kernel-contract.schema.json` (native kernel declarations, not
primitive contracts), and `spec/cost-cases.json`.

The checker is `tools/check_docs.py`. It runs the checks in
`tools/docs_validation/` (`ledger.py` for roadmap and catalogue, `contracts.py`
for bets, obligations, and schemas, `semantics.py` for the example
documentation model, `costs.py`, `markdown.py`) and requires
`docs/validation-results.json` to equal the freshly computed report. After a
deliberate change, run `check_docs.py --write` and commit the report.
`make design-check` runs the checker and
`python3 -m unittest discover -s tools/tests`; `.github/workflows/design.yml`
runs it on every pull request. The checker's Markdown checks cover only the
files listed in `DESIGN_DOCUMENTS` in `tools/docs_validation/context.py`.

ADR format: `docs/documentation-style-guide.md` (file
`docs/adr-NNN-short-description.md`; title
`# Architectural decision record (ADR) NNN: <title>`; sections `Status`, `Date`,
`Context and problem statement`, then conditional sections).
`docs/adr-001-repository-bootstrap.md` is the only existing ADR and predates
that template.

## Conformance basis

- Terms of reference: `docs/terms-of-reference.md`, revision 0.2, 6 October
  2026. Traced items: G1, G2, G6, G7, G8; S7, S8, S10; C2, C3, C5, C6, C7,
  C9; Q1, Q2, Q4, Q7, Q8.
- Technical design: `docs/technical-design.md`, revision 0.2, 6 October 2026.
  Traced items: R7, R8, R9, R10; §2 scope classes; §§4-7; §12; §14 V13, V14,
  V20; §15 candidate decisions, GAP2, GAP5, GAP9; §16; §17.1, §17.2, §17.7,
  §17.8; §18.2, §18.5.
- Roadmap: `docs/roadmap.md` revision 0.2, step 1.1, tasks 1.1.1 to 1.1.4.
- Bets: B01, B02, B03, B08. Proof obligations: PF14 (structural component).
- ADRs: `docs/adr-001-repository-bootstrap.md` (accepted, scaffold only).
- Governing standards: `AGENTS.md`, `docs/documentation-style-guide.md`,
  `docs/developers-guide.md` "Design contract checks", and D-CONTRACT in
  `docs/references.md` (draft status retained).

Trace chains:

```plaintext
ToR Q1, Q8 -> TD GAP5, GAP9 -> D01, D02, D13 -> EP-M2 -> ADR-002 -> tools/tests/test_decision_register.py
ToR Q4 -> TD §2 scope classes -> D03 -> EP-M2 -> ADR-003 -> register anchors in five documents
ToR Q7 -> TD GAP5 -> D04, D05 -> EP-M2 -> ADR-004 -> tools/tests/test_package_policy.py
ToR C5 -> TD §15 row 10, §17.8 -> D06 -> EP-M2 -> ADR-005
TD §15 candidate ADRs -> D07 -> EP-M2 -> docs/decision-register.md disposition table
TD §§4-7, §17.3, §17.5 -> R2 -> D08-D10, D14 -> SC-* -> EP-M3 -> ADR-006, ADR-007 -> tools/tests/test_semantic_contracts.py
ToR Q2, S7 -> TD §12, §14 V13, §17.8, §18.5 -> D11, D12 -> AC-* -> EP-M4 -> ADR-008 -> tools/tests/test_preregistration.py
TD §17.1-17.2, V14, V20 -> R8 -> PF14.structural@1.1.4 -> EP-M5 -> ADR-009 -> tools/tests/test_evidence_gate.py
Roadmap 1.1.1-1.1.4 -> EP-M6 -> spec/roadmap.json status=done -> tools/tests/test_roadmap_status.py
```

Gaps addressed: GAP2 (thresholds recorded, not met), GAP5 (scope, licence,
authority ratified), GAP9 (exception authority assigned). GAP1, GAP3, GAP4,
GAP6, GAP7, and GAP8 remain open for later steps.

## Decisions required from the sponsor

The plan cannot complete without these answers (ToR C6). `EP-M1a` publishes
them in `docs/decision-register.md` with options, consequences, and a
recommendation each. An approval must name the identifiers it accepts, for
example "Accept D01, D03 to D05 as recommended; amend D02 as follows: …".
Partial answers are accepted per identifier. D01 is needed first.

- D01 (Q1, Q8 authority). Who accepts architecture, scope changes, release
  readiness, trusted-boundary exceptions, and released proof-API changes, by
  GitHub login? Options: the sponsor alone; the sponsor plus a named technical
  owner with delegated acceptance of contract records and pre-registrations.
  Recommendation: the sponsor plus a named technical owner (who may be the same
  person), because ToR §9 names "Sponsor and technical owner" for Q2 and Q4;
  choosing the sponsor alone requires amending that column.
- D02 (exception policy). Recommendation: an exception is valid from its
  approval date until its `invalid_from` date, at most 90 days and never past
  the next release-gate task (4.3.3 or 6.3.4); renewal is a new approval; an
  exception names a narrowed claim and can never satisfy a proof-required
  component.
- D03 (Q4 scope). Recommendation: accept the Core, Integration, and Deferred
  split in technical design §2 unchanged.
- D04 (Q7 licence). Recommendation: ratify ISC.
- D05 (Q7 publication). Recommendation: set `publish = false` in
  `Cargo.toml` until the Core acceptance dossier (task 4.3.3) passes and the
  D01 authority approves release.
- D06 (pre-1.0 API policy). Recommendation: ratify ToR C5 and technical design
  §15 row 10 (no shims for pre-1.0 or unreleased APIs); follow Cargo's 0.y.z
  rule (a change to the leftmost non-zero component is breaking); version the
  public proof interface (models, pre- and postconditions, lemmas, trust
  declarations) with the crate version, treating a strengthened precondition or
  weakened postcondition as breaking (technical design §17.8). MSRV stays with
  ToR Q3 and task 1.2.1.
- D07 (candidate ADR dispositions). Recommendation: numerical and array
  semantics to ADR-006; macro staging and stable-Rust application to ADR-007;
  initial release scope to ADR-003; public proof compatibility to ADR-005 and
  ADR-009; shared semantic kernel and backend and cell separation deferred to
  task 1.2.1 (B01 can falsify the kernel in 1.2.4); resource certification
  deferred to step 2.4 (B03); backend input and output control scope deferred
  to task 1.2.6 (B06).
- D08 (`comb!` operator precedence). Recommendation: Rust's expression
  precedence as parsed by `syn`, with `|>` split from the token stream first
  (lowest precedence, left-associative); reject, with a first-screen
  diagnostic, any comparison that is the unparenthesized operand of `&`, `|`, or
  `^` and vice versa; translate `syn`'s chained-comparison error into the same
  diagnostic.
- D09 (F64 special values). Recommendation: binary `min` and `max` follow
  IEEE 754-2019 `minimum` and `maximum` (NaN propagates; negative zero is less
  than positive zero); null propagation takes precedence over NaN; an empty F64
  `sum` returns positive zero (the registered typed zero) while `sum([-0.0])`
  returns negative zero (a singleton passes through); a `mean` count of exactly
  2^53 is admitted.
- D10 ("typed-cell atomicity"). Recommendation: record two distinct rules
  under distinct names: cell atomicity (a typed cell such as `DVec3` is one
  logical element until an explicit component operation; `Batch<DVec3>` of shape
  `[2,3]` has cardinality 6) and atomic output commit (failure or cancellation
  before commit leaves the destination unchanged).
- D11 (Q2 environments). Options for runtime ratios: a named, otherwise idle
  reference machine (CPU model, cores, memory, governor, SMT, kernel,
  isolation); or paired, interleaved runs within one hosted job, with
  instruction counts as the primary metric and wall time secondary.
  Recommendation: the hosted paired design on a pinned `ubuntu-24.04` runner
  class, because it needs no dedicated hardware. Proof and build ceilings use
  the same pinned runner class. Shared development hosts are never acceptance
  environments.
- D12 (Q2 thresholds and statistics). The sponsor supplies or amends every
  value in the `EP-M4` proposal table.
- D13 (governance enforcement). Recommendation: commit `.github/CODEOWNERS`
  naming the D01 logins for `spec/decisions.json`, `spec/exceptions.json`,
  `spec/acceptance-controls.json`, `spec/semantic-contracts.json`, and
  `docs/adr-*.md`; the sponsor enables "require review from code owners" and
  makes `Design contracts` a required check on `main` (a repository setting the
  agent will not change).
- D14 (`div` on I64 operands). Technical design §6.1 says only "true division
  to F64". Recommendation: convert each operand to F64 (round to nearest, ties
  to even), then apply IEEE division, matching Rust `as f64` and common
  backends; document that this can differ from rounding the exact quotient once.
- D15 (prospective details for later tasks). Recommendation: add these
  `details` to `spec/roadmap.json` now, before those tasks start, so their
  criteria are fixed in advance: 1.2.1 and 1.2.4 build the trust-audit scanner
  and verifier log parsers and replay the gate rule table from Rust; 1.2.3
  replays the semantic examples as `rstest` cases; 2.3.1 replays every grammar
  corpus entry as a `trybuild` pass or fail fixture, with a completeness check.

## Verification plan

This step introduces repository-governance logic, not library semantics. The
semantic contracts recorded in `EP-M3` will be discharged against Rust code by
the existing proof obligations (for example PF07 for reduction association in
tasks 2.2.x). This step checks that those contracts are coherent, complete, and
non-vacuous in the documentation model, and that the governance logic is
correct.

### Method selection

Verus and Kani are not used in this step (see `Decision log`). Each contract
record's `proof_sketch` states the Verus lemma statements and Kani harness
intent that its discharging task must prove, so proof structure shapes the
accepted contracts now without speculative proof plumbing.

The Rust test tools named in the project's testing guidance apply when the
contracts gain Rust implementations. This step's artefacts are designed to be
replayed by them:

- the grammar corpus becomes `trybuild` pass and fail fixtures in 2.3.1;
- the semantic examples become `rstest` cases with `googletest` matchers and
  `pretty_assertions` diffs in 1.2.3 and phase 2;
- diagnostic snapshots with `insta` start with the first rendered errors in
  2.3.3;
- the gate rule table is replayed by Rust tooling in 1.2.4, where Kani
  harnesses over its enums become cheap;
- `proptest` covers the Rust shape and cardinality invariants in 2.1.1.

`rstest-bdd` does not apply here: no user-visible Rust behaviour changes. In
this step, Python `unittest` subtests play the role of parameterized cases,
Hypothesis properties the role of property tests, and the checker's
generated-document drift comparison the role of golden snapshots.

### Abstract model of the evidence gate

An abstract record is a tuple of ten fields:

- `kind` in {deductive, bounded, test, trust-declaration, none};
- `outcome` in {verified, counterexample, resource-exhausted,
  solver-unknown, unsupported, skipped, not-run, tool-error};
- `bounds` in {not-applicable, type-complete, partial};
- `witness` in {all-satisfied, some-unsatisfied, absent};
- `controls` in {all-required-rejected-as-intended, some-rejected-otherwise,
  some-accepted, required-missing};
- `trust` in {audited-none, audited-all-covered, audited-uncovered,
  unaudited};
- `exception` in {none, active, expired, not-yet-valid, malformed};
- `binding` in {current, stale, incomplete};
- `run_mode` in {full-profile, focused};
- `verdict_source` in {log-parser, self-reported}.

The product domain has 345,600 states. A validity predicate `Valid` excludes
contradictory combinations: `kind = none` exactly when `outcome = not-run`;
`trust-declaration` requires `outcome = not-run`; `bounds = not-applicable`
exactly when `kind` is not bounded; a bounded record has `type-complete` or
`partial` bounds. The JSON Schema enforces the same predicate, and VO-2 checks
that the two agree.

Admission (to be recorded in ADR-009 as a compact, ordered rule table that the
sponsor accepts, and implemented exactly):

- MS-0. If `Valid` fails, the level is `rejected` with `schema-invalid`.
- MS-1 (blocking reasons). Each failed condition contributes one reason
  code:
  - `outcome != verified` gives `outcome-<value>`, except for
    trust-declarations;
  - `witness != all-satisfied` gives `witness-<value>`;
  - `controls != all-required-rejected-as-intended` gives `control-<value>`;
  - for deductive and bounded kinds, `trust = unaudited` gives
    `trust-unaudited` and `audited-uncovered` gives `trust-uncovered`;
  - `binding != current` gives `binding-<value>`;
  - `run_mode = focused` gives `run-focused`;
  - an expired, not-yet-valid, or malformed exception gives
    `exception-<value>`;
  - for deductive and bounded kinds, `verdict_source = self-reported` gives
    `verdict-self-reported`;
  - `kind = none` gives `not-run`;
  - a trust-declaration without an active exception gives
    `trust-without-exception`.
- MS-2 (level). With no blocking reason, the base level is:
  - `proof` for deductive, or for bounded with `type-complete` bounds;
  - `bounded` for bounded with `partial` bounds;
  - `tested` for test;
  - `restricted` for a trust-declaration.

  If `exception = active`, the level becomes `restricted`, with the
  informational reason `exception-active`. Any blocking reason makes the level
  `rejected`.
- MS-3 (component satisfaction). A component lists the levels it accepts, a
  subset of {proof, bounded, tested}; `restricted` is never accepted. A
  component is satisfied when the latest record for it at the current binding
  is admitted at an accepted level and no record at the same source revision
  reports `outcome = counterexample`. A component whose `evidence_source` is
  `checker:<check-id>` is satisfied when that checker check passes in the same
  run (the checker produces that evidence itself).
- MS-4 (task closure). A task may claim `status: done` only when:
  - every prerequisite task is done;
  - every decision it cites is accepted and not superseded;
  - every completion artefact it lists resolves;
  - every obligation component linked to it is satisfied.

  The checker also rejects support that is not claimed: a task whose conditions
  hold but whose status is `open` is reported, without failing, so that status
  remains an explicit claim.

Substantive admission properties, checked against both the rule table and the
implementation. These are hypotheses about the structure of a later Rust proof;
restatements of single rules are deliberately excluded:

- P1 (degradation monotonicity). Order each field from best to worst and
  levels as proof > bounded > tested > restricted > rejected. Replacing any
  field value with a worse one never raises the level.
- P2 (diagnostic soundness and completeness). A level is `rejected` exactly
  when the reason set contains a blocking reason. Moving any single field that
  contributed a reason to its best value removes exactly that reason.
- P3 (exceptions never substitute). No state with `exception != none`
  satisfies any component.
- P4 (bounded honesty). No state with `bounds = partial` reaches `proof`.
- P5 (date sensitivity). For concrete records, `as_of` affects the result
  only through the exception state.
- P6 (closure soundness). For synthetic roadmaps, `done(t)` implies
  `done(p)` for every prerequisite `p`; adding a counterexample record at the
  current revision un-closes every task depending on that component.

Upstream scenario corpus (derived from the bet register, proof ledger, and
technical design, not from ADR-009), each mapped to its expected level and
reason:

- B01 "suppress a failed harness" maps to `outcome-skipped` or
  `verdict-self-reported`.
- B02 "always-Err executor" maps to `witness-some-unsatisfied`.
- B02 "assumed executor postcondition" maps to `trust-uncovered`.
- B08 "import verification metadata from a different executable revision"
  maps to `binding-stale`.
- B08 "use focus/skip mode as release evidence" maps to `run-focused` or
  `outcome-skipped`.
- B08 "label bounded Kani evidence as unbounded" maps to level `bounded`,
  failing a proof-only component.
- PF14 "swap a compiled body" maps to `binding-stale`.
- §17.1 timeout maps to `outcome-resource-exhausted`.
- §17.1 unsupported feature maps to `outcome-unsupported`.
- §17.1 failed unwinding assertion maps to `outcome-counterexample`.
- §17.1 empty generator maps to `witness-absent`.
- §17.7 negative control failing on an unrelated parse error maps to
  `control-some-rejected-otherwise`.

### Obligations

- Obligation VO-1 (admission correctness, MS-0 to MS-2, P1 to P4).
  - Method: exhaustive enumeration of all 345,600 abstract states, comparing
    the implementation with an independent interpreter of the ADR-009 rule
    table stored as `tools/tests/fixtures/evidence_gate_rules.json`; P1 to P4
    are checked over the full enumeration, against both the table and the
    implementation; the scenario corpus is checked against both.
  - Rationale: the domain is finite and small, so enumeration is complete;
    the properties and the upstream corpus give independence that
    table-versus-code agreement alone cannot.
  - Artefacts: `tools/tests/test_evidence_gate.py`,
    `tools/docs_validation/evidence_gate.py`.
  - Evidence: red is `ModuleNotFoundError` for `evidence_gate`; green is full
    agreement.
  - Non-vacuity: every level and every reason code occurs, and each reason
    occurs as the sole reason for at least one state; the count of valid
    states is asserted.
  - Seeded mutations that must fail:
    - treating `resource-exhausted` as verified;
    - ignoring `trust`;
    - letting `active` keep the base level;
    - mapping `partial` bounds to `proof`;
    - accepting `some-rejected-otherwise`.
- Obligation VO-2 (concrete-to-abstract mapping and schema agreement).
  - Method:
    - for each valid abstract state, a generator builds a concrete record
      that must be schema-valid and must abstract back to that state;
    - for each invalid state, the built record must be schema-invalid;
    - a Hypothesis property over generated concrete records checks that
      abstraction depends only on the documented fields.
  - Domain: all abstract states, and generated records classified with
    `hypothesis.event` by kind and outcome.
  - Artefact: `tools/tests/test_evidence_records.py`.
  - Non-vacuity: the test fails if any kind or outcome class is never
    generated. A seeded mapping fault (reading `kind` where `outcome` is
    intended) must fail.
- Obligation VO-3 (exception register validity, P5).
  - Method: parameterized boundary tests on the injected date:
    - the day before `approved_on` is not-yet-valid;
    - `approved_on` is active;
    - the day before `invalid_from` is active;
    - `invalid_from` is expired.

    Malformed cases are:
    - a lifetime beyond D02's maximum;
    - an approver not designated by D01;
    - a missing narrowed-claim identifier;
    - a missing owner.

    A Hypothesis property checks that varying `as_of` changes only the
    exception state.
  - Artefact: `tools/tests/test_exceptions.py`.
  - Non-vacuity: each malformed variant yields its own reason; a complete
    active exception yields `restricted`.
- Obligation VO-4 (components and closure, MS-3, MS-4, P6).
  - Method: parameterized tests over synthetic roadmaps (a chain and a
    diamond) and the real `spec/roadmap.json`.
  - Artefact: `tools/tests/test_roadmap_status.py`.
  - Non-vacuity, where each case must behave as stated:
    - `done` with an open prerequisite fails;
    - `done` citing a proposed or superseded decision fails;
    - `done` with an unsatisfied component fails;
    - `done` with an unresolvable completion artefact fails;
    - a counterexample at the current revision reopens a component;
    - a fully satisfied task passes;
    - `- [x]` appears only for done tasks;
    - a hand-edited `[x]` fails as drift.

    Before `EP-M5`, any task with a linked component cannot be done (C-EP-10).
- Obligation VO-5 (decision register integrity).
  - Invariants:
    - identifiers are unique;
    - accepted, non-superseded records have unique subjects;
    - every in-scope ToR question is covered by an accepted record;
    - an accepted record has `decided_option`, `accepted_on`, and a
      structured `approval_reference` (`kind`, `url`, `author_login`,
      `names_decisions`) whose `author_login` is a D01-designated login and
      whose `names_decisions` includes the record;
    - D01 itself is accepted by the sponsor login it records;
    - a proposed record has no approval fields;
    - `supersedes` and `superseded_by` links agree in both directions and
      are acyclic;
    - each cited ADR exists and its `Status` line agrees with the lifecycle;
    - dates are validated with the `jsonschema` format checker.
  - Artefact: `tools/tests/test_decision_register.py`.
  - Non-vacuity: one in-memory negative control per invariant, each
    rejected with a distinct message; the real register passes.
- Obligation VO-6 (five-document consistency).
  - Invariants:
    - each governing document links `decision-register.md`;
    - each accepted question's ToR §9 row links its register anchor
      (`decision-register.md#d03`);
    - after whitespace and inline-Markdown normalization, no
      `retired_statements` text of an accepted decision appears in its
      document;
    - for each accepted question, no governing document matches the
      open-status pattern `(pending|open|unresolved|remains? proposed)` within
      60 characters of that question's identifier.
  - Artefact: `tools/tests/test_decision_register.py`.
  - Non-vacuity, each of which must fail after D03's acceptance:
    - reinserting "The classes remain proposed pending ToR Q4." into
      technical design §2, rewrapped across two lines;
    - rewording it to "Q4 remains open";
    - deleting the ToR §9 anchor link.
- Obligation VO-7 (base-revision freeze).
  - Invariant: compared with `--base-rev`, the change is rejected when:
    - a registered control's frozen field changes without a new amendment
      whose `replaces` equals the previous digest;
    - an amendment chain entry is edited or removed;
    - an accepted decision is deleted or edited other than by supersession;
    - an accepted exception is altered rather than replaced.
  - Method: parameterized tests with in-memory base and head documents, and
    one integration test against a temporary Git repository created inside
    the test's temporary directory.
  - Artefact: `tools/tests/test_freeze.py`.
  - Non-vacuity: changing a threshold and its digest together is rejected; a
    correctly amended change passes.
- Obligation VO-8 (semantic contract coherence and examples).
  - Invariants: every contract record
    - names catalogue identifiers that exist;
    - has preconditions, success conditions, a success relation, an error
      relation using registered error codes, a mutation frame, termination,
      and an empty rule;
    - cites at least one evaluated example and at least one seeded mutation;
    - has a `discharged_by` list (a PF component, or a test task where no PF
      obligation applies, such as the grammar's 2.3.1);
    - has a `proof_sketch`.

    Every catalogue entry's `contract` text cites its contract identifier.
  - New examples use a tagged scalar encoding (`{"f64": "-0.0"}`,
    `{"f64_bits": "0x7ff8000000000000"}`, `{"i64": "9223372036854775807"}`)
    and cover:
    - empty `product`, `any`, `all`, `minimum`, `maximum`, and `mean`;
    - `minimum([5]).identity(0)` returning 5, and a wrong-dtype identity
      failing;
    - `idiv(-7, 2) = -3` and `rem(-7, 2) = -1`;
    - I64 to F64 ties-to-even (2^53 + 1 to 2^53);
    - F64 to I64 boundaries (2^63 fails, -2^63 succeeds, -0.0 gives 0, NaN
      and non-integral fail);
    - Bool to I64 giving 0 or 1, and numeric to Bool rejected;
    - Kleene `and`, `or`, `xor`;
    - `any([true, null])` null under the default policy;
    - binary `min` and `max` with NaN, signed zeros, and null;
    - empty F64 `sum` returning positive zero, and `sum([-0.0])` returning
      negative zero;
    - `skip_nulls` then empty;
    - `Batch<DVec3>` of shape `[2,3]` having cardinality 6 and rejecting
      `.axis(2)`;
    - an injected failure leaving the output destination unchanged.
  - Artefact: `tools/tests/test_semantic_contracts.py`.
  - Non-vacuity: each seeded mutation must change at least one example's
    outcome:
    - left association for `reduce`;
    - floor division for `idiv`;
    - error instead of identity for empty `sum`;
    - the identity used as a seed;
    - implicit I64 to F64 promotion in `add`;
    - NaN-ignoring `min`;
    - two-valued null logic;
    - partial output on failure.
- Obligation VO-9 (grammar corpus adequacy).
  - Invariant: `spec/macro-grammar.json` agrees with the ADR-007 precedence
    table, which is transcribed from the Rust Reference's expression
    precedence with a citation.
  - Corpus coverage:
    - `|>` lowest and left-associative, and inside parentheses;
    - `a|>b` and `a | > b`;
    - unary `-` and `!` (`!a == b`, `-a * b`, `-x.abs()`);
    - comparison chains rejected;
    - unparenthesized comparison mixed with `&`, `|`, or `^` rejected;
    - `&&` and `||` between arrays rejected;
    - `||` and `|v|` closures inside `host { ... }` accepted, and outside it
      rejected;
    - `rows(&centre)` as host construction;
    - `as`, `..`, `=`, and `+=` rejected.

    Entries that only a token-level implementation can exercise are tagged
    `phase2-only`.
  - Method: a precedence-climbing recognizer of under 200 lines in
    `tools/docs_validation/grammar.py` checks corpus adequacy.
  - Artefact: `tools/tests/test_macro_grammar.py`.
  - Non-vacuity: each of these must fail at least one entry:
    - swapping `*` and `+`;
    - making `|>` right-associative;
    - accepting `&&`;
    - allowing comparison mixing.

    A mechanical check requires an entry for every precedence level and
    every rejection rule.
  - Residual gap: this models the corpus, not the macro. Task 2.3.1 replays
    every entry through `trybuild` (D15), after which the recognizer is
    deleted.
- Obligation VO-10 (no superseded-name shims).
  - Invariant: no name in the `excluded_names` register appears as a
    catalogue name or alias. The register is derived from `docs/context.md`
    §6 and `docs/language-reference.md` §9: `a!`, `cells`, `cells2`, `id` as
    an alias of `identity`, `.pipe` accepting descriptors directly, and array
    `&&` and `||`.
  - Artefact: `tools/tests/test_semantic_contracts.py`.
  - Non-vacuity: adding `cells` in memory fails.
- Obligation VO-11 (pre-registration completeness and amendment chain).
  - Invariants: a registered control has every frozen field listed in
    `EP-M4`. Its digest is SHA-256 of canonical JSON (sorted keys, compact
    separators, UTF-8) over those fields. Amendments are a chain:
    - each `replaces` equals the previous digest;
    - the current digest equals the last amendment's `new_digest`;
    - a measurement record must cite a current or historical digest of its
      control.
  - Method: a Hypothesis property mutates each frozen field in turn,
    recording which field was mutated, and requires rejection unless a
    matching amendment is present; parameterized completeness controls.
  - Artefact: `tools/tests/test_preregistration.py`.
  - Non-vacuity: the property fails unless every frozen field was exercised;
    a correct amendment passes.
- Obligation VO-12 (measurement outcomes cannot be relabelled).
  - Invariant: `resource-exhausted`, `budget-exceeded`, `inconclusive`, and a
    missing record from a killed job map to fail or inconclusive, never pass.
    Retried attempts are all recorded and all count.
  - Method: exhaustive enumeration of the measurement outcome mapping.
  - Artefact: `tools/tests/test_preregistration.py`.
  - Non-vacuity: a seeded mapping treating `resource-exhausted` as pass
    must fail.
- Obligation VO-13 (package policy).
  - Invariant: `Cargo.toml` `license` and `publish` agree with accepted D04
    and D05.
  - Artefact: `tools/tests/test_package_policy.py`.
  - Non-vacuity: an in-memory manifest with another licence fails.
- Obligation VO-14 (generator drift and idempotence).
  - Invariant: every generator, including `tools/generate_decisions.py`, is
    covered by the checker's drift comparison; rerunning all generators on a
    clean tree yields no diff.
  - Artefact: `tools/tests/test_roadmap_status.py` and the concrete
    idempotence step.
  - Non-vacuity: a hand edit to `docs/decision-register.md` fails.
- Obligation VO-15 (bet and task links are two-way).
  - Invariant: each task's `bets` and each bet's `tasks` list each other.
  - Artefact: `tools/tests/test_metadata_ids.py`.
  - Non-vacuity: removing 1.1.4 from B08 in memory fails.

### Axioms

These are trusted, not verified here:

- A1. The `jsonschema` package implements Draft 2020-12 and its format
  checker correctly. The existing schema negative controls exercise it.
- A2. SHA-256 is a collision-resistant identity check. A digest proves the
  identity of frozen fields, not their correctness.
- A3. Git history and the merge base supplied by CI are authentic. The
  freeze check trusts them.
- A4. GitHub attributes reviews and comments to the logged-in author.
  CODEOWNERS and branch protection (D13) make A4 an enforced control rather
  than an assumption; until the sponsor enables them, the axiom is stated in
  ADR-002.
- A5. Verifier log parsers and the trust-audit scanner (tasks 1.2.1 and
  1.2.4, D15) correctly read verifier output. C-EP-10 means this axiom is never
  exercised before those parsers exist and are themselves tested. The scanner's
  item vocabulary is fixed in ADR-009:
  - for Verus: `assume`, `admit`, `external_body`, `external`,
    `external_fn_specification` or `assume_specification`, and
    `external_type_specification`;
  - for Kani: `kani::assume`, `stub`, `stub_verified`, and `should_panic`.

## Plan of work

Milestones run in order. `EP-M1a` and `EP-M1b` need no sponsor input. `EP-M2`
needs D01 to D07 and D13. `EP-M3` needs D08 to D10 and D14. `EP-M4` needs D11
and D12. `EP-M5` needs acceptance of ADR-009. `EP-M6` needs D15. Drafting for a
later milestone may proceed while an earlier one awaits acceptance, but no
record is accepted and no task marked done out of dependency order.

Each milestone follows Red, Green, Refactor:

- Stage A (understand and propose; no code): draft ADRs and records as
  `proposed`.
- Stage B (red): add the rule table, fixtures, and tests. Run the focused
  test module and observe the expected failure (a missing module, a
  disagreement, or an unrejected negative control).
- Stage C (green): implement validators and records until the focused tests
  pass.
- Stage D (refactor and validate): tidy the code, then run the generators
  and `check_docs.py --write` and review the report diff. Finally have
  `scrutineer` run the full gates.

### EP-M1a. Decision register, generator, and anchors

- Records:
  - Add `spec/decision-register.schema.json` and `spec/decisions.json` with
    D01 to D15 as `proposed`. Each decision carries:
    - `subject`, `questions`, and `authority_roles` (a set);
    - `options`, `recommendation`, and `decided_option`;
    - `lifecycle`, `supersedes`, and `superseded_by`;
    - `accepted_by`, `accepted_on`, and `approval_reference`;
    - `adr` and `retired_statements` (pairs of document and text).
  - Add the eight candidate ADR subjects with a `disposition` each.
- Generator: add `tools/generate_decisions.py`, mirroring
  `tools/generate_bets.py`. It renders `docs/decision-register.md` between
  `<!-- decisions:start -->` and `<!-- decisions:end -->`, with one anchored
  heading per decision.
- Checks:
  - Turn the generator list in `ledger.check_generated_documents` into a
    table that includes the decisions generator.
  - Add `tools/docs_validation/decisions.py` (VO-5, VO-6) and register it in
    `collect_checks`.
  - Add the register and all ADRs to `DESIGN_DOCUMENTS`.
- Documents and CODEOWNERS:
  - Link the register from the five governing documents and from
    `docs/contents.md`.
  - Draft `.github/CODEOWNERS`, inactive until D13 names the logins.
  - Update `docs/developers-guide.md` "Design contract checks" with the
    register workflow and the `uv` invocation for `make design-check`.

### EP-M1b. Roadmap status, obligation components, and freeze check

- Roadmap status:
  - In `spec/roadmap.json`, give each task a `status` (`open` or `done`) and
    a `completion` list of artefact references.
  - Compute the top-level status string and the checker's roadmap detail
    from the data, rather than hard-coding "All tasks remain open".
  - Make `tools/generate_roadmap.py` render `- [x]` for done tasks.
- Closure owner: add `tools/docs_validation/roadmap_status.py` as the single
  owner of MS-3 and MS-4, and replace the blanket ban in `ledger.py` with a
  call to it.
- Obligation components:
  - In `spec/proof-obligations.json`, add `components` to every obligation
    (for PF14, `PF14.structural@1.1.4` accepts `tested`, with evidence source
    `checker:evidence-gate`).
  - Relax `check_obligations` so components may cite evidence, while
    obligation-level status stays `planned-not-run` until every component is
    satisfied.
  - Until `EP-M5`, a task with any component cannot be done (C-EP-10).
- Freeze check:
  - Add `tools/docs_validation/freeze.py` (VO-7) and a `--base-rev` option
    to `check_docs.py`.
  - In the `Makefile`, add `AS_OF ?= $(shell git log -1 --format=%cs)` and
    an optional `BASE_REV` to `design-check`.
  - In `.github/workflows/design.yml`, set `fetch-depth: 0`, pass the merge
    base, and add a weekly `schedule:` trigger.

### EP-M2. Task 1.1.1: authority, scope, licence, and API policy

- ADRs: with the sponsor's named acceptance of D01 to D07 and D13, write:
  - `docs/adr-002-governance-authority.md` (D01, D02, D13, axiom A4);
  - `docs/adr-003-initial-release-scope.md` (D03);
  - `docs/adr-004-licence-and-publication.md` (D04, D05);
  - `docs/adr-005-pre-1-0-api-and-proof-interface-policy.md` (D06).
- Register: record the D07 dispositions and set the records' lifecycle to
  `accepted` with structured approval references. Acceptance lands in a small
  dedicated commit that the sponsor reviews.
- Reconcile the five documents:
  - In ToR §9, rows Q1, Q4, Q7, and Q8 link their register anchors.
  - ToR §10 and technical design §15 point at the register's disposition
    table.
  - Technical design §2, GAP5, and GAP9 drop their open-status language.
  - Update the `docs/context.md` §7 sentence and the roadmap preamble ("no
    accepted ADR or ExecPlan exists", already false because ADR 001 is
    accepted).
  - Update `docs/language-reference.md` prose outside the generated region.
  - Record each replaced sentence in `retired_statements`.
- Package policy:
  - If D05 is accepted as recommended, add `publish = false` to
    `Cargo.toml`.
  - Add `tools/docs_validation/package_policy.py` (VO-13).
  - Update `README.md` "Licence" and `docs/users-guide.md` (project status,
    licence, publication, and stability policy).
- If D01 changes an authority in ToR §9, amend that column under the
  upstream-conflict tolerance.
- Close: set task 1.1.1 to `done` with completion references D01 to D07,
  D13, and ADR-002 to ADR-005.

### EP-M3. Task 1.1.2: semantic and macro contract records

- ADRs: draft
  `docs/adr-006-numeric-validity-and-reduction-contracts.md` and
  `docs/adr-007-comb-macro-grammar-and-staging.md`.
  - ADR-006 covers:
    - the dtype set and conversions (V031, D14);
    - null and Kleene logic;
    - association of `reduce`, `fold_left`, `scan`, and `scan_left`;
    - `.reassociate()` failure equivalence;
    - empty identities and `.identity(value)`;
    - `mean` and `variance`;
    - D09 and D10.
  - ADR-007 covers:
    - an EBNF for `comb!`, `verb!`, `host { ... }`, `arr!`, and `array!`;
    - the D08 precedence and association table with its Rust Reference
      citation;
    - the token-level `|>` split;
    - the staging phases (construction, preparation, execution) and what
      each may evaluate;
    - the optional static-descriptor rule.
- Reuse policy: before adding the new schema, record in
  `docs/developers-guide.md` why `spec/kernel-contract.schema.json` does not
  fit and how the two relate.
  - The kernel schema declares a native kernel's execution envelope; it is
    not a primitive's public logical contract.
  - Semantic contracts reuse the kernel `outcomes` field names
    (`success_conditions`, `error_relation`, `mutation_frame`,
    `termination`).
  - Kernel contracts will cite contract identifiers through their
    `operation_id`.
- Contract records: add `spec/semantic-contract.schema.json` and
  `spec/semantic-contracts.json` (records SC-01 onward). Each record carries:
  - `decision` (for acceptance) and `catalogue_ids`;
  - `preconditions`, `success_relation`, `success_conditions`,
    `error_relation` (registered error codes), `mutation_frame`,
    `termination`, and `empty_rule`;
  - `examples` and `seeded_mutations`;
  - `discharged_by` and `proof_sketch` (Verus lemma statements, Kani
    harness intent, witness, and control).
- Vocabulary: make each affected `spec/vocabulary.json` `contract` cite its
  contract identifier, then regenerate the reference. Add the `excluded_names`
  register.
- Examples: add the tagged-scalar examples to `spec/examples.json`. Extend
  the documentation model in a new `tools/docs_validation/contract_examples.py`
  rather than growing `semantics.py` past 400 lines; the model remains a
  documentation model, not the reference evaluator of technical design §14.
- Grammar: add `spec/macro-grammar.json` and
  `tools/docs_validation/grammar.py`.
- Tests: VO-8, VO-9, and VO-10.
- Close: when the D01 authority accepts ADR-006 and ADR-007 (D08 to D10,
  D14), set task 1.1.2 to `done`. Update technical design §§6-7 and §17.3 to
  cite the ADRs and record the proof-influenced choices: the two atomicity
  rules, and the D08 rule being enforceable through `syn`. Reconcile the
  accepted rows of `docs/context.md` §6.

### EP-M4. Task 1.1.3: pre-registered acceptance controls

- Records and policy:
  - Add `spec/acceptance-controls.schema.json`,
    `spec/acceptance-controls.json`, a measurement-record schema
    (`spec/measurement-record.schema.json`, binding `control_id` and
    `control_digest`), and `tools/docs_validation/preregistration.py`
    (VO-11, VO-12).
  - Write `docs/adr-008-acceptance-control-pre-registration.md`, setting the
    policy:
    - register before measuring;
    - amendments are an authorized chain;
    - a post-measurement change is a new control identifier (`AC-03r2`), and
      the original result is retained and reported;
    - exploratory baseline runs never count as acceptance evidence;
    - shared development hosts are not acceptance environments.

Frozen fields for every control:

- workload and control source paths and digests, input sizes (at least two
  per runtime workload, so planning cost is visible), seeds, and timed region
  (whether planning or preparation is inside it);
- metric and unit, estimand, statistic, and decision rule, including the
  inconclusive and single pre-declared extension policy;
- warm-up, interleaving, sample counts, and outlier policy;
- environment: image family, runner class with vCPU and memory, and Rust,
  Verus, Kani, solver, and Polars versions with codegen backend and linker;
- cache policy, and for proofs the scope parameters (harness list, unwind
  bounds, Verus `rlimit`, solver);
- measurement tool and version, and analysis script digest;
- `registered_on` and authority.

Observed runner metadata (`ImageOS`, `ImageVersion`) is recorded per
measurement, not frozen. A toolchain bump requires re-measuring the control
under an amendment.

Proposed starting controls for the sponsor to amend (D12):

- AC-01 (task 1.2.4, B01): Verus verification of the cardinality kernel.
  - Primary budget: a deterministic `rlimit` per function.
  - Secondary budget: wall time at most 120 s and peak process-tree memory at
    most 4 GiB, measured by cgroup v2 `memory.peak` over a transient scope.
  - Outcomes: up to 120 s passes; from 120 s to 600 s is `budget-exceeded`
    (fail); beyond 600 s is `resource-exhausted` (fail).
  - Retries are forbidden.
- AC-02 (tasks 1.2.4, 1.2.5; B01, B02): each Kani harness.
  - Budget: at most 300 s per harness and 30 min per job.
  - Frozen scope: the solver is registered, unwinding assertions are on, and
    every declared `kani::cover!` must be satisfied.
  - A per-harness wrapper writes a record even when killed; a missing record
    is a failure.
- AC-03 (step 2.4, B03): compile-time cost of static admission.
  - Control: the same fixture without static descriptors.
  - Estimand: the geometric mean of paired, interleaved candidate/control
    incremental-rebuild ratios, with each process-level run as one sample.
  - Statistics: at least 10 pairs and 3 discarded warm-up runs per arm; a
    percentile bootstrap with at least 10,000 resamples on the log scale.
  - Decision rule: a one-sided 95% upper bound of at most 1.25 passes; an
    interval straddling 1.25 is inconclusive, with one pre-declared doubling
    of the sample allowed.
- AC-04 (task 1.2.1, S7): cold and incremental builds of the native-only,
  proof-capable, and Polars-enabled profiles.
  - Build conditions: cold means an empty `target/` with dependencies
    pre-fetched and no `sccache` or Rust cache; incremental means a
    registered single-file edit; `-j`, `CARGO_INCREMENTAL`, and the profile
    are fixed.
  - Registered now: the ceiling formula (1.5 times the median of five
    exploratory baseline runs, rounded up to the minute), so the control is
    complete before any acceptance measurement.
- AC-05 (S1, S5): row centring, neighbourhood counting, and generalized
  contraction against ordinary Rust controls.
  - Workloads: each at two sizes.
  - Statistics: the AC-03 estimand and statistics with at least 30 pairs.
  - Decision rule: an upper bound of at most 1.5 passes. All six members
    must pass (an intersection-union test, so no alpha correction), and each
    member's result is reported.
- AC-06 (V9, V13): peak tracked allocation against the accounted bound.
  - Categorical: the tracked peak never exceeds the admitted bound.
  - A counting `GlobalAlloc` reports untracked allocation alongside it.
- AC-07: pull request CI wall time.
  - Measured as the critical path from first job start to last job end,
    excluding queue time.
  - Budget: the p90 over the last 20 runs, with warm and cold caches stated
    separately; the design job at most 10 min and the whole pipeline at most
    45 min.
  - `timeout-minutes` equals the budget, so the budget is enforced.

Criterion.rs's default change-detection noise threshold is not used as an
acceptance rule; the registration states its own rule. Whether verifier
installation time counts towards a budget is stated per control (proposed:
excluded, measured separately).

When the sponsor accepts D11 and D12 (naming the controls), set each control to
`registered`, store its digest, mark task 1.1.3 done, and update:

- ToR §7 and §9 Q2 (anchor links);
- technical design §12, §14 V13, §17.8, and GAP2;
- the bet register's measurement sentences.

### EP-M5. Task 1.1.4: proof-first policy, public proof contract, and gate

- ADR: write `docs/adr-009-proof-first-policy-and-evidence-gate.md`
  containing:
  - the abstract model and validity predicate;
  - the compact ordered rule table (about 20 rows);
  - properties P1 to P6;
  - the trust-audit item vocabulary;
  - the public proof contract (what consumers may rely on: versioned models,
    pre- and postconditions, lemmas, effect policies, and trust
    declarations, per technical design §17.8 and D06);
  - the exit codes of `check_evidence.py`.
- Red: write `tools/tests/fixtures/evidence_gate_rules.json`, the scenario
  corpus, and the tests first.
- Schema: revise `spec/proof-evidence.schema.json` to `schema_version` 2:
  - `id` and `component` (separate fields);
  - `evidence_kind` and `outcome` (with `outcome_detail`);
  - structured `bounds`;
  - `binding` with executable and specification digests, source revision,
    target, features, semantic policy, backend profile, and
    `implementation_relation` (same-body, refinement-proved, or
    refinement-gap);
  - `method` with tool, version, solver, solver version, command, and
    `run_mode`;
  - `declared_assumptions` (a fixed baseline plus extensions, each citing an
    exception);
  - `trust_audit` (auditor tool, version, and digest, plus items with tool,
    kind, symbol, location, and `covered_by`);
  - `success_witnesses` (minimum one; kind `kani-cover`,
    `verus-witness-fn`, or `test`, with expected and observed results; every
    Kani `cover` listed);
  - `negative_controls` (minimum one; each with a required control
    identifier from the component, a mutation digest, and expected and
    observed failures as tool, error kind, and property identifier);
  - `verdict_source` (kind, parser, log path, log digest);
  - `exception` (an identifier into `spec/exceptions.json`);
  - `result_artefacts` (the existing result-list field, renamed to the en-GB
    spelling that the spelling gate enforces, as part of the atomic change).
- Exception register: add `spec/exceptions.json` with its schema (owner,
  approver, `approved_on`, `invalid_from`, revisit trigger, narrowed claim
  identifier, component).
- Atomic update: update `spec/proof-evidence.example.json` (still a planned
  record) and `check_proof_evidence_envelope`, and single-source the reason
  codes in `spec/evidence-reason-codes.json`, all in the same change.
- Implementation:
  - `tools/docs_validation/evidence_gate.py` is pure, with no
    `ValidationContext`, and exposes `abstract_record` and `admit`.
  - `roadmap_status.py` consumes it for MS-3.
  - Add `tools/check_evidence.py`.
- Tests: VO-1 to VO-4.
- Documents:
  - Add `docs/evidence-and-decision-records.md`, the component document for
    producers (schema, reason codes, exit codes, the log-parser and
    trust-scanner obligations, and the mapping from the kernel-contract
    status vocabulary).
  - Update technical design §17.1 and §17.2 (citing ADR-009), ToR Q8,
    GAP9, the B08 entry, and `docs/users-guide.md` (a summary of the public
    proof contract).
- Close: when the D01 authority accepts ADR-009, `PF14.structural@1.1.4` is
  satisfied by the passing `evidence-gate` check, and task 1.1.4 is marked done.

### EP-M6. Reconciliation, roadmap closure, and final gates

- Roadmap and bets:
  - With D15 accepted, add the prospective `details` to tasks 1.2.1, 1.2.3,
    1.2.4, and 2.3.1.
  - Reconcile the bet task lists and add the two-way check (VO-15).
- Documents: regenerate generated documents and update:
  - `docs/validation.md` (counts and the new checks);
  - `docs/repository-layout.md` (new `spec/` and `tools/` files, ADRs,
    `docs/execplans/`, `.github/CODEOWNERS`);
  - `docs/contents.md`;
  - `docs/developers-guide.md` (per-module owners; the exception renewal
    runbook; the pre-registration amendment procedure; the
    `validation-results.json` conflict rule);
  - `docs/revision-0.2.md`, if its "deliberately unchanged" list is
    affected.
- Finish: run the full gates. Complete `Outcomes & retrospective` and set
  this plan's status to `COMPLETE`.

## Milestones and plateaus

### EP-M1a

- Identifier and outcome: `EP-M1a`. A validated decision register with
  every record `proposed`, drift-checked generation, links from all five
  documents, and an inactive CODEOWNERS draft.
- Requirements and gaps: ToR Q1, Q2, Q4, Q7, Q8 presented, not resolved; C6
  enforced mechanically.
- Acceptance evidence: `make design-check` passes; VO-5 and VO-14 pass;
  `docs/decision-register.md` lists D01 to D15 as proposed.
- Conformance check:
  - No ToR question is marked resolved.
  - The technical design is unchanged except for links.
  - No public Rust interface or dependency change.
  - New `spec/` files are design-pack inputs, not wire formats.
  - Trace links have been added.
- Recovery: revert; nothing is accepted yet.
- Remaining gaps: every decision.
- Compatibility decision: none.

### EP-M1b

- Identifier and outcome: `EP-M1b`. Evidence-gated roadmap status, obligation
  components, and the base-revision freeze check, with every task open.
- Requirements and gaps: prepares MS-3 and MS-4; C-EP-10 enforced.
- Acceptance evidence: VO-4 (synthetic roadmaps) and VO-7 pass. The
  `Design contracts` workflow runs with full history and a merge base.
- Conformance check:
  - The Makefile and workflow changes stay within the tolerances.
  - Any Rust contract test pinning them is updated in the same commit.
- Recovery: revert while no task is done; after that, fix forward, because
  reverting would restore the blanket ban and break `main`.
- Compatibility decision: none.

### EP-M2

- Identifier and outcome: `EP-M2`. D01 to D07 and D13 accepted; ADR-002 to
  ADR-005 accepted; five documents reconciled; task 1.1.1 done.
- Requirements and gaps: ToR Q1, Q4, Q7, and Q8 (authority); GAP5; part of
  GAP9.
- Acceptance evidence: VO-5, VO-6, and VO-13 pass over accepted records;
  `- [x] 1.1.1.` is generated.
- Conformance check:
  - The 1.1.1 success text is satisfied.
  - If D03 amends the scope classes, R1 to R11 and the phase gates are
    impact-checked first.
  - Only `Cargo.toml` metadata changes on the Rust side.
- Recovery: accepted records are reversed only by superseding records.
- Compatibility decision: none.

### EP-M3

- Identifier and outcome: `EP-M3`. ADR-006 and ADR-007 accepted; contract
  records, examples, grammar corpus, and excluded names in place; task 1.1.2
  done.
- Requirements and gaps: R2 contracts recorded, not implemented.
- Acceptance evidence: VO-8, VO-9, and VO-10 pass with their seeded
  mutations.
- Conformance check:
  - Each of the five success topics has an accepted record.
  - `comb!` is unchanged (C2).
  - No superseded name has returned.
  - No Rust change.
- Recovery: superseding records for accepted contracts.
- Remaining gaps: Rust implementation and proofs (phase 2).
- Compatibility decision: none.

### EP-M4

- Identifier and outcome: `EP-M4`. Acceptance controls registered and
  frozen; task 1.1.3 done.
- Requirements and gaps: ToR Q2; GAP2 (recorded, not met); V13 inputs.
- Acceptance evidence: VO-11 and VO-12 pass; every AC entry is
  `registered`; VO-7 rejects a threshold-plus-digest edit.
- Conformance check:
  - No acceptance measurement predates its registration (none exist).
  - No benchmark claims.
- Recovery: amendments only, once registered.
- Remaining gaps: measurements (tasks 1.2.x onward).
- Compatibility decision: none.

### EP-M5

- Identifier and outcome: `EP-M5`. ADR-009 accepted; evidence schema version
  2; exception register; pure gate with exhaustive tests; task 1.1.4 done
  through `PF14.structural@1.1.4` at level `tested`.
- Requirements and gaps: R8, V14, V20, ToR Q8 mechanics, GAP9.
- Acceptance evidence:
  - VO-1 to VO-4 pass.
  - `check_evidence.py` rejects the planned example with `not-run` and
    exits 1.
  - It admits the complete test fixture at `tested`, exits 0, and reports
    the fixture's bounded variant at `bounded`.
- Conformance check:
  - Claims are bound to executable and specification identities,
    toolchains, scopes, assumptions, and negative controls.
  - Exceptions have owners, expiry, revisit triggers, and claim
    restrictions.
  - Timeout, skipped, and vacuous results cannot pass.
  - No `schema_version` 1 consumer remains.
- Recovery: revert before any producer exists.
- Remaining gaps: producers and parsers (task 1.2.4).
- Compatibility decision: none. The schema has no deployed consumer, so the
  old version is replaced, not preserved.

### EP-M6

- Identifier and outcome: `EP-M6`. All four 1.1 tasks shown done; documents,
  bets, report, and layout reconciled; plan `COMPLETE`.
- Acceptance evidence: the full gate run and the generator idempotence step
  both pass.
- Conformance check: every discovery is reconciled upstream or recorded as
  mechanical in `Decision log`.
- Recovery: revert reconciliation commits individually.
- Compatibility decision: none.

## Concrete steps

Run all commands from the repository root.

Use a Python environment with the documentation dependencies (the system Python
lacks `markdown-it-py`):

```bash
export PY="uv run --python 3.14 --with-requirements tools/requirements.txt python3"
```

Baseline before any change:

```bash
make design-check PYTHON="$PY" 2>&1 | tee /tmp/design-check-combobulate-1-1-resolve-acceptance-control-decisions.out
```

Red step, for example in `EP-M5` (expected to fail for the named reason):

```bash
$PY -m unittest discover -s tools/tests -p 'test_evidence_gate.py' 2>&1 | tail -n 3
```

```plaintext
ModuleNotFoundError: No module named 'docs_validation.evidence_gate'
FAILED (errors=1)
```

Green and refactor, then regenerate and check idempotence:

```bash
$PY -m unittest discover -s tools/tests
for g in reference roadmap bets decisions; do $PY tools/generate_$g.py; done
$PY tools/check_docs.py --write --as-of "$(git log -1 --format=%cs)"
for g in reference roadmap bets decisions; do $PY tools/generate_$g.py; done
git diff --exit-code -- docs/ && echo idempotent
```

Format, then have `scrutineer` run the gates one at a time, each through `tee`
to `/tmp/$ACTION-combobulate-1-1-resolve-acceptance-control-decisions.out`:

```bash
make fmt
make check-fmt
make lint
make test
make design-check PYTHON="$PY" BASE_REV=origin/main
make markdownlint
make nixie
```

Evidence gate demonstration (after `EP-M5`):

```bash
$PY tools/check_evidence.py --as-of 2026-10-10 --require proof spec/proof-evidence.example.json; echo "exit=$?"
```

```plaintext
spec/proof-evidence.example.json: rejected [not-run]
exit=1
```

## Validation and acceptance

Quality criteria:

- Tests:
  - `make test` passes unchanged.
  - `$PY -m unittest discover -s tools/tests` passes, including every new
    module named in `Verification plan`.
  - Each new module was observed failing for the expected reason before its
    implementation.
- Verification: VO-1 to VO-15 are discharged with their non-vacuity checks
  passing.
- Lint and format: `make check-fmt`, `make lint`, `make markdownlint` (which
  includes `make spelling`), and `make nixie` pass.
- Design contracts: `make design-check` passes with `BASE_REV` set, and the
  regenerated `docs/validation-results.json` is committed.
- Performance: none in this step; thresholds are registered, not measured.
- Security: no network access in checks and no secrets. CODEOWNERS covers
  the governance files.

Behavioural acceptance, observable by a reviewer:

1. `docs/decision-register.md` lists D01 to D15 as accepted, each with its
   chosen option, date, and approval link, plus all eight candidate ADR
   subjects with dispositions.
2. `docs/roadmap.md` shows `- [x] 1.1.1.` to `- [x] 1.1.4.` and no other
   ticked task.
3. Reinserting "The classes remain proposed pending ToR Q4." into
   `docs/technical-design.md`, or writing "Q4 remains open", makes
   `make design-check` fail and name D03.
4. Changing AC-03's threshold and its digest in one commit makes
   `make design-check BASE_REV=origin/main` fail and name AC-03.
5. `check_evidence.py` rejects a fixture with `outcome` `resource-exhausted`
   (reason `outcome-resource-exhausted`). It reports a partial-bounds Kani
   fixture at `bounded`, never `proof`, and rejects a self-reported Verus
   record with `verdict-self-reported`.

## Idempotence and recovery

Generators and `check_docs.py --write` are idempotent for a fixed `--as-of`;
the idempotence step proves it. Tests use in-memory copies or temporary
directories and never write to `spec/` or `docs/`. If a milestone fails midway,
`git restore` the uncommitted files and rerun from its red step. Git revert is
safe only for milestones with no accepted records and no done tasks. After
that, an accepted decision, contract, control, or exception is reversed by a
superseding record, per the ADR amendment rules in
`docs/documentation-style-guide.md`. Conflicts in
`docs/validation-results.json` are resolved by taking either side, rerunning
the generators, and running `check_docs.py --write`.

## Artefacts and notes

New documents:

- `docs/decision-register.md` (generated);
- `docs/evidence-and-decision-records.md` (component document);
- `docs/adr-002-governance-authority.md`;
- `docs/adr-003-initial-release-scope.md`;
- `docs/adr-004-licence-and-publication.md`;
- `docs/adr-005-pre-1-0-api-and-proof-interface-policy.md`;
- `docs/adr-006-numeric-validity-and-reduction-contracts.md`;
- `docs/adr-007-comb-macro-grammar-and-staging.md`;
- `docs/adr-008-acceptance-control-pre-registration.md`;
- `docs/adr-009-proof-first-policy-and-evidence-gate.md`.

New specification files:

- `spec/decision-register.schema.json` and `spec/decisions.json`;
- `spec/semantic-contract.schema.json` and `spec/semantic-contracts.json`;
- `spec/macro-grammar.json`;
- `spec/acceptance-controls.schema.json` and
  `spec/acceptance-controls.json`;
- `spec/measurement-record.schema.json`;
- `spec/exceptions.json` with `spec/exception.schema.json`;
- `spec/evidence-reason-codes.json`.

New tooling:

- `tools/generate_decisions.py` and `tools/check_evidence.py`;
- `tools/docs_validation/decisions.py`, `roadmap_status.py`, `freeze.py`,
  `package_policy.py`, `contract_examples.py`, `grammar.py`,
  `preregistration.py`, and `evidence_gate.py`.

New tests in `tools/tests/`:

- `test_decision_register.py`, `test_roadmap_status.py`, `test_freeze.py`,
  `test_package_policy.py`, `test_semantic_contracts.py`,
  `test_macro_grammar.py`, `test_preregistration.py`, `test_exceptions.py`,
  `test_evidence_gate.py`, and `test_evidence_records.py`;
- `fixtures/evidence_gate_rules.json`, plus evidence fixtures under
  `fixtures/evidence/`.

Repository configuration: `.github/CODEOWNERS`.

## Interfaces and dependencies

No new dependencies. Python modules use the standard library (`tomllib`,
`hashlib`, `subprocess` only in `freeze.py` for `git show`) plus the pinned
`jsonschema`, `hypothesis`, `markdown-it-py`, and `PyYAML`.

In `tools/docs_validation/evidence_gate.py`:

```python
class Level(enum.Enum):
    PROOF = 'proof'
    BOUNDED = 'bounded'
    TESTED = 'tested'
    RESTRICTED = 'restricted'
    REJECTED = 'rejected'

@dataclasses.dataclass(frozen=True)
class Admission:
    level: Level
    reasons: tuple[str, ...]

def abstract_record(record: Mapping[str, object], exceptions: Mapping[str, Mapping[str, object]],
                    bindings: Mapping[str, str], as_of: datetime.date) -> AbstractRecord: ...
def admit(record: AbstractRecord) -> Admission: ...
```

`admit` is pure and total over `AbstractRecord`. `abstract_record` raises
`ValidationError` only for schema-invalid records.

`tools/check_evidence.py --as-of DATE [--require LEVEL] [--bindings FILE]
RECORD…`
prints one line per record (`path: level [reasons]`). It exits 0 when every
record meets `--require` (default `tested`), 1 when any falls short, and 2 for
schema-invalid input or usage errors.

`tools/docs_validation/roadmap_status.py` exposes
`check_task_status(context, tasks, decisions, components) -> None`, and
`freeze.py` exposes `check_frozen(context, base_rev: str | None) -> None`.
`decisions.py` exposes `check_decision_register(context) -> None`,
`package_policy.py` exposes `check_package_policy(context) -> None`, and
`preregistration.py` exposes `frozen_digest(control) -> str` and
`check_acceptance_controls(context) -> None`. `grammar.py` exposes
`parse(source: str) -> Parsed | Rejected` for the corpus model only.

## Signposts

Documentation to read before each milestone:

- `docs/terms-of-reference.md` §§4, 7-10;
- `docs/technical-design.md` §§2, 6, 7, 12, 14-18;
- `docs/context.md` §§6-7;
- `docs/language-reference.md` §§6, 9;
- `docs/testable-bets.md` B01, B02, B03, B08;
- `spec/proof-obligations.json` PF14;
- `docs/developers-guide.md` "Design contract checks";
- `docs/documentation-style-guide.md` (the ADR section);
- `docs/references.md` §D-CONTRACT;
- `docs/complexity-antipatterns-and-refactoring-strategies.md` (keep checker
  functions small);
- `docs/reliable-testing-in-rust-via-dependency-injection.md` (the injection
  principle behind `--as-of` and `--base-rev`);
- `docs/rust-testing-with-rstest-fixtures.md`, `docs/rust-doctest-dry-guide.md`,
  and `docs/rstest-bdd-users-guide.md` (for the later tasks that replay these
  artefacts).

Skills and agents:

- Skills: `execplans`, `arch-decision-records`, `en-gb-oxendict-style`,
  `hypothesis`, `rust-verification`, `verus`, `kani`, `firecrawl-mcp`,
  `logisphere-design-review`, `commit-message`, and `pr-creation`.
- Agents: `scrutineer` runs every gate; `scribe` makes mechanical
  documentation edits; `wyvern` does read-only reconnaissance.

## Revision note

- 2026-10-10, initial draft.
- 2026-10-10, revised after the community-of-experts review (six lenses,
  verdict "revise"). Changes:
  - per-component obligation evidence (fixing the PF14 deadlock);
  - `evidence_kind` split from `outcome`;
  - `bounded` and `tested` admission levels, a validity predicate, and
    substantive properties in place of restated lemmas;
  - fail-closed log-parser and trust-audit rules;
  - a base-revision freeze with CODEOWNERS;
  - one decision per ADR (now ADR-002 to ADR-009);
  - D13 to D15 added; the D08, D09, and D11 recommendations refined;
  - rigorous measurement protocols in `EP-M4`;
  - the corrected V031 cast example and tagged F64 encoding;
  - per-milestone tolerances and sequential milestones.

  Remaining work is unchanged in purpose: obtain sponsor approval, then execute
  `EP-M1a` onward.
