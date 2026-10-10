# Resolve the decisions that control acceptance (roadmap 1.1)

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: DRAFT

Implementation must not begin until the sponsor explicitly approves this plan.
Approval of the plan is not acceptance of any decision record that the plan
proposes; those acceptances are separate, recorded acts (see `EP-M2`, `EP-M3`,
and `EP-M4`).

## Purpose / big picture

Roadmap step 1.1 asks: which constraints are approved, and which remain
experiments? Today every Combobulate design document is labelled "proposed", no
decision has an accountable owner, no acceptance threshold exists, and the
repository's checker actively forbids marking any roadmap task complete. Any
later implementation could therefore have its success criteria changed after
the fact, which is precisely what the terms of reference (ToR) prohibit.

After this work, a reviewer can do four observable things that are impossible
today:

1. Run `make design-check` and see a decision register that names, for each
   governing ToR question (Q1, Q2, Q4, Q7, and Q8), the accountable authority,
   the accepted answer, the date, and the architectural decision record (ADR)
   that holds the rationale. The same run fails if any of the five governing
   documents still describes an accepted decision as open.
2. Read accepted contract records for association, empty identities, dtype
   conversion, validity, the `comb!` macro grammar, and typed-cell atomicity.
   Each record has preconditions, postconditions, empty and failure rules, and
   at least one executable example, and the documentation model rejects
   deliberately wrong semantics.
3. Read pre-registered resource, performance, build, and proof budgets with
   named workloads, controls, environments, and uncertainty rules. Editing a
   registered threshold without a recorded, authorized amendment makes
   `make design-check` fail.
4. Feed a proof-evidence record to the evidence gate and observe that a record
   with a timeout, skipped harness, vacuous result, missing success witness,
   unreported trusted assumption, or expired exception is rejected with a
   specific reason code, while a complete record is admitted.

The roadmap tasks 1.1.1 to 1.1.4 are then marked done through the same
evidence-gated mechanism, not by hand-editing a checkbox.

Term definitions used throughout:

- Sponsor: the project sponsor named in ToR §4 ("Payton"). Only the sponsor,
  or an authority the sponsor designates in an accepted record, can accept a
  decision. The implementing agent drafts; it never accepts.
- Decision record: a machine-readable entry in `spec/decisions.json` with an
  accompanying ADR in `docs/`. It is `proposed` until an authority accepts it.
- Contract record: a machine-readable entry in `spec/semantic-contracts.json`
  that states one public primitive's logical contract, independent of any
  implementation.
- Pre-registration: recording a measurement's workload, control, environment,
  statistic, and threshold before any acceptance measurement is taken, so the
  threshold cannot be tuned to the result.
- Evidence gate (merge-state gate): the pure admission function in
  `tools/docs_validation/evidence_gate.py` that decides whether a
  proof-evidence record may count towards a required obligation, and whether a
  roadmap task may be marked done.
- Negative control: a deliberately broken input that a check must reject for
  the intended reason. A check with no failing negative control is vacuous.

## Constraints

- C-EP-1. Do not invent owners, accepted thresholds, release dates, or
  deployment claims (ToR C6). Every `accepted` decision, contract, or
  pre-registration must cite a sponsor or designated-authority approval
  recorded in a durable artefact (a pull request review, a pull request
  comment, or a commit authored by that authority). The implementing agent may
  draft proposals and recommendations, labelled as such.
- C-EP-2. Approval is not verification (roadmap 1.1.1). No accepted decision
  may change a proof obligation's status, mark a bet as run, or record a
  capability as eligible.
- C-EP-3. Retain `comb!` ergonomics and names (ToR C2). Nothing in the grammar
  contract may introduce `a!`, glyph notation, or an alternate pipeline macro.
- C-EP-4. No compatibility machinery for superseded or pre-1.0 names (ToR C5,
  technical design §15). Schema revisions (for example the proof-evidence
  schema moving from revision `0.2` to `0.3`) update every consumer and fixture
  atomically; no dual-schema acceptance, alias field, or deprecated enum value.
- C-EP-5. Generated documents stay generated. `docs/roadmap.md`,
  `docs/testable-bets.md`, `docs/language-reference.md` (catalogue region), and
  the new `docs/decision-register.md` are changed only through their JSON
  masters in `spec/` and the generators in `tools/`.
- C-EP-6. The design-model validator remains a documentation-model checker.
  It must not claim Rust compilation, Kani, Verus, or Polars results
  (`tools/check_docs.py` `NOT_RUN` list stays truthful).
- C-EP-7. Python tooling follows the existing `tools/` conventions (package
  modules under `tools/docs_validation/`, `unittest` plus pinned Hypothesis in
  `tools/tests/`, dependencies in `tools/requirements.txt`). No Python file
  exceeds 400 lines. No network access in checks.
- C-EP-8. No Rust library behaviour, public API, or Rust dependency changes in
  this step. The only permitted Rust-adjacent edit is to `Cargo.toml` package
  metadata (`license`, `publish`) if the sponsor's licence and publication
  decision requires it.
- C-EP-9. Checks are deterministic. The evidence gate never reads the wall
  clock; the evaluation date is injected (`--as-of` on the command line, an
  explicit argument in code). No check reads environment variables.
- C-EP-10. Do not run gates in parallel. Gate runs go through the `scrutineer`
  agent, sequentially, with output captured under `/tmp`.

If satisfying the objective requires violating a constraint, stop, record the
conflict in `Decision log`, set the status to `BLOCKED`, and escalate.

## Tolerances (exception triggers)

- Scope: if the work needs more than 45 changed files or more than 3,500 net
  added lines (excluding generated Markdown regions and
  `docs/validation-results.json`), stop and escalate.
- Owner input: if a milestone needs a sponsor decision that has not been
  given, set the status to `BLOCKED` at that milestone and ask. Do not proceed
  to a dependent milestone on a guessed answer. Independent milestones may
  continue (see `Plan of work`).
- Interface: if any Rust public API, Rust dependency, or Make target name must
  change, stop and escalate. Adding a new Make target is not permitted without
  escalation; extend `design-check` instead.
- Dependencies: if a Python dependency beyond the existing
  `tools/requirements.txt` set is needed, stop and escalate.
- Upstream conflict: if accepting a sponsor decision contradicts an explicit
  user constraint (ToR C1 to C9), stop and present the conflict rather than
  editing the constraint.
- Iterations: if a gate still fails after three fix attempts for the same
  cause, stop and escalate with the log path.
- Ambiguity: if the "typed-cell atomicity" success criterion, or any other
  success text, admits two materially different readings that the sponsor has
  not resolved, present both with a recommendation.

## Risks

- Risk: the sponsor is unavailable, leaving decisions unaccepted.
  Severity: high. Likelihood: medium. Mitigation: `EP-M1` delivers all
  machinery with every record `proposed`, so the repository reaches a coherent
  plateau without any owner input. The decision brief in `EP-M1` presents each
  question with options and a recommendation so that one review can answer them
  all.
- Risk: the gate checks only that fields exist, which the technical design
  (§17.2) already warns is not evidence. Severity: high. Likelihood: medium.
  Mitigation: the admission function is specified as a decision table first;
  tests enumerate the entire finite abstraction against that independent table
  and assert reason codes for each seeded defect (see `Verification plan`).
- Risk: text-based consistency checks across five documents become brittle.
  Severity: medium. Likelihood: medium. Mitigation: single-source the decision
  status into one generated register and keep the cross-document check to two
  mechanical rules: each governing document links the register, and each
  accepted decision lists the exact stale sentences that must no longer appear.
- Risk: pre-registered numeric thresholds prove unattainable or meaningless
  once measured. Severity: medium. Likelihood: high. Mitigation: the amendment
  protocol permits authorized changes before measurement and treats a
  post-measurement change as a new, separately labelled registration; the bet
  decision rules (narrow scope, revise representation) absorb failure honestly.
- Risk: the grammar decision (operator precedence) interacts with how `syn`
  parses Rust expressions, which later macro work (phase 2) must honour.
  Severity: medium. Likelihood: medium. Mitigation: the recommended option
  adopts Rust's own precedence and forbids unparenthesized mixing of
  comparisons with `&` or `|`, which `syn` can enforce; the grammar corpus is
  written so phase 2 can replay it as `trybuild` fixtures.
- Risk: Python tooling diverges from `docs/scripting-standards.md` (uv script
  headers, Cyclopts, pytest). Severity: low. Likelihood: certain. Mitigation:
  follow the existing `tools/` precedent for consistency and record the reason
  in `Decision log`; scripting standards govern standalone scripts, while these
  are modules of an existing checker package.
- Risk: the evidence gate's expiry rule makes CI fail on a later date with no
  code change. Severity: low. Likelihood: medium. Mitigation: this is the
  intended revisit trigger. The failure message names the expired exception and
  its owner. The date is injected, so tests are deterministic.

## Progress

- [x] (2026-10-10) Reconnaissance with a Wyvern team: scope and authority,
  numeric and macro contracts, resource controls, proof-evidence schema, and
  repository tooling.
- [x] (2026-10-10) External research: Cargo pre-1.0 SemVer rules, the
  `jsonschema` Draft 2020-12 validator, Kani `cover` non-vacuity reporting,
  Criterion.rs bootstrap analysis, and IEEE 754-2019 `minimum`/`maximum`.
- [x] (2026-10-10) Draft ExecPlan written.
- [ ] Community-of-experts review of the draft and revision.
- [ ] Sponsor approval of the plan.
- [ ] `EP-M1` Governance machinery and decision brief.
- [ ] `EP-M2` Task 1.1.1: authority, scope, licence, and API policy accepted.
- [ ] `EP-M3` Task 1.1.2: semantic and macro contract records accepted.
- [ ] `EP-M4` Task 1.1.3: acceptance controls pre-registered.
- [ ] `EP-M5` Task 1.1.4: proof-first policy and evidence gate accepted.
- [ ] `EP-M6` Reconciliation, roadmap closure, and final gates.

## Surprises & discoveries

- Observation: the checker forbids any completed roadmap task.
  Evidence: `tools/docs_validation/ledger.py` `check_task_links` requires
  `not re.search(r'^- \[[xX]\]', text, re.M)` and fails with "Roadmap has
  fabricated completed tasks"; `tools/generate_roadmap.py` always emits
  `- [ ]`. Impact: marking 1.1.x done requires an evidence-gated status
  mechanism (`EP-M1`), not a checkbox edit.
- Observation: the proof-evidence schema cannot express the outcomes that
  1.1.4 must reject. Evidence: `spec/proof-evidence.schema.json` `status` enum
  has no timeout, skipped, unsupported, or vacuous value; `assumptions` has no
  `minItems` and no observed-versus-reported distinction; `exception` lacks
  owner, approval date, and expiry; a `proved` record may carry an exception.
  Impact: `EP-M5` revises the schema to revision `0.3`.
- Observation: the candidate ADR set differs between documents. Evidence:
  ToR §10 names four subjects; technical design §15 names eight; neither gives
  dispositions. Impact: the decision register carries all eight with an
  explicit disposition each, and ToR §10 is reconciled to it.
- Observation: ISC already appears in `Cargo.toml`, `LICENSE`, and
  `README.md`, inherited through ADR 001, yet ToR Q7 and technical design GAP5
  treat the licence as unratified. Impact: 1.1.1 ratifies or amends it.
- Observation: the bet register omits 1.1.1 and 1.1.2 from B01 and B02 task
  lists although the roadmap tags them. Evidence: `docs/testable-bets.md` B01
  tasks are 1.1.4, 1.2.4, 1.2.5, 4.3.3. Impact: reconcile in `spec/bets.json`
  during `EP-M6`.
- Observation: `make design-check` is not part of `make all` or `ci.yml`; it
  runs in `.github/workflows/design.yml`. Impact: each milestone's gate list
  names `make design-check` explicitly.

## Decision log

- Decision: implement the evidence gate and record validators in Python
  inside `tools/docs_validation/`, not as a Rust crate or Rust test. Rationale:
  the existing design-contract checker, its JSON Schema validation, its
  Hypothesis property tests, and its CI workflow already live there; the gate
  validates JSON records whatever produces them; a Rust implementation would add
  `serde_json` and a JSON Schema crate as new dependencies before task 1.2.1
  pins the toolchain profile. The roadmap's later Rust tasks emit records that
  this gate consumes. Date/Author: 2026-10-10, planning agent; subject to
  sponsor approval of this plan.
- Decision: do not use Verus or Kani in this step. Rationale: no Rust
  executable body is introduced. The one piece of contractual logic, the
  admission rule, ranges over a finite abstraction (64,512 abstract states)
  that tests enumerate exhaustively against an independently written decision
  table, which is a complete check of the abstraction. Introducing a verifier
  now would pre-empt the toolchain pinning that task 1.2.1 owns. Residual gap:
  the mapping from concrete JSON records to abstract states, covered by
  parameterized and Hypothesis tests. Date/Author: 2026-10-10, planning agent.
- Decision: follow existing `tools/` conventions rather than
  `docs/scripting-standards.md`. Rationale: the new code consists of modules in
  an existing package invoked by `tools/check_docs.py`, not standalone scripts;
  mixing pytest and `unittest` in one discovery root would split the
  `design-check` contract. Date/Author: 2026-10-10, planning agent.
- Decision: single-source decision status in `spec/decisions.json` and
  generate `docs/decision-register.md`; the five governing documents link to
  the register rather than restating status. Rationale: one source of truth
  prevents five documents drifting; the success criterion "match all five
  documents" then reduces to two mechanical checks. Date/Author: 2026-10-10,
  planning agent.

## Outcomes & retrospective

Not started. Complete at each milestone boundary and at completion, comparing
the result with `Purpose / big picture`, and reconciling every discovery with
the artefacts in `Conformance basis` before setting the status to `COMPLETE`.

## Context and orientation

Combobulate is a proposed Rust array-programming library. The repository holds
a development scaffold (`src/lib.rs` exports only a disposable `greet()` stub)
and a revision 0.2 design pack. Nothing is implemented.

The design pack has five governing documents (ToR C3; `docs/context.md` §2):

- `docs/terms-of-reference.md` (ToR): problem, goals G1 to G8, success
  criteria S1 to S11, constraints C1 to C9, and open questions Q1 to Q9 in §9.
- `docs/context.md`: vocabulary; §6 lists earlier suggestions and their
  consolidated (superseding) positions.
- `docs/technical-design.md`: requirements R1 to R11 (§2), the Core,
  Integration, and Deferred scope classes (§2), numerical and reduction
  contracts (§6), macro grammar (§7), costs (§12), verification obligations V1
  to V20 (§14), candidate decisions and gaps GAP1 to GAP9 (§15), change control
  (§16), proof-first policy (§17), and costing (§18).
- `docs/language-reference.md`: the operation catalogue, generated in part
  from `spec/vocabulary.json`.
- `docs/roadmap.md`: the GIST roadmap, generated from `spec/roadmap.json`.

Companion artefacts: `docs/testable-bets.md` (generated from `spec/bets.json`,
bets B01 to B08), `spec/proof-obligations.json` (PF01 to PF14),
`spec/traceability.json` (R and V mappings), `spec/examples.json` (semantic
examples EX01 to EX20), `spec/proof-evidence.schema.json` and its example,
`spec/kernel-contract.schema.json` (native kernel declarations, not primitive
contracts), and `spec/cost-cases.json`.

The checker is `tools/check_docs.py`. It runs the check functions in
`tools/docs_validation/` (`ledger.py` for roadmap and catalogue, `contracts.py`
for bets, obligations, and schemas, `semantics.py` for the documentation model
of examples, `costs.py` for cost cases, `markdown.py` for Markdown structure)
and then requires `docs/validation-results.json` to equal the freshly computed
report. After any deliberate change, run `python3 tools/check_docs.py --write`
and commit the regenerated report. `make design-check` runs the checker and
`python3 -m unittest discover -s tools/tests`. `.github/workflows/design.yml`
runs `make design-check` on every pull request.

The ADR format is in `docs/documentation-style-guide.md` (file name
`docs/adr-NNN-short-description.md`; title
`# Architectural decision record (ADR) NNN: <title>`; sections `Status`, `Date`,
`Context and problem statement`, then conditional sections).
`docs/adr-001-repository-bootstrap.md` is the only existing ADR.

## Conformance basis

- Terms of reference: `docs/terms-of-reference.md`, revision 0.2, 6 October
  2026. Traced items: G1, G2, G6, G7, G8; S7, S8, S10; C2, C3, C5, C6, C7,
  C9; Q1, Q2, Q4, Q7, Q8.
- Technical design: `docs/technical-design.md`, revision 0.2, 6 October 2026.
  Traced items: R7, R8, R9, R10; §2 scope classes; §§4-7 contracts; §12; §14
  V13, V14, V20; §15 candidate decisions, GAP2, GAP5, GAP9; §16; §17.1, §17.2,
  §17.8; §18.5.
- Roadmap: `docs/roadmap.md` revision 0.2, step 1.1, tasks 1.1.1 to 1.1.4.
- Bets: B01, B02, B03, B08 in `docs/testable-bets.md`.
- ADRs: `docs/adr-001-repository-bootstrap.md` (accepted, scaffold only). No
  product ADR exists.
- Governing standards: `AGENTS.md`, `docs/documentation-style-guide.md`,
  `docs/developers-guide.md` "Design contract checks", and the D-CONTRACT
  guidance recorded in `docs/references.md` (draft status retained).

Trace chains (milestone to evidence):

```plaintext
ToR Q1, Q8 -> TD GAP5, GAP9 -> D01, D02 -> EP-M2 -> ADR-002 accepted; tools/tests/test_decision_register.py
ToR Q4 -> TD §2 scope classes -> D03 -> EP-M2 -> ADR-003 accepted; register generated
ToR Q7, C5 -> TD GAP5, §15 row 10 -> D04, D05, D06 -> EP-M2 -> ADR-003; Cargo.toml metadata check
TD §15 candidate ADRs -> D07 -> EP-M2 -> docs/decision-register.md disposition table
TD §§4-7, §17.3, §17.5 -> R2 -> SC-* records -> EP-M3 -> ADR-004, ADR-005; tools/tests/test_semantic_contracts.py
ToR Q2, S7 -> TD §12, §17.8, §18.5, V13 -> AC-* controls -> EP-M4 -> ADR-006; tools/tests/test_preregistration.py
TD §17.1-17.2, V14, V20 -> R8 -> MS-* rules -> EP-M5 -> ADR-007; tools/tests/test_evidence_gate.py
Roadmap 1.1.1-1.1.4 -> EP-M6 -> spec/roadmap.json status=done; ledger closure check
```

Baseline-to-target gaps addressed: GAP2 (thresholds recorded, not met), GAP5
(scope, licence, authority ratified), GAP9 (exception authority assigned).
GAP1, GAP3, GAP4, GAP6, GAP7, and GAP8 remain open and belong to later steps.

## Decisions required from the sponsor

The plan cannot be completed without these answers (ToR C6). `EP-M1` turns this
list into `docs/decision-brief-1-1.md` with options, consequences, and a
recommendation for each; the sponsor may answer them together. The
recommendations below are proposals, not decisions.

- D01 (Q1). Who accepts architecture, scope changes, and release readiness?
  Options: the sponsor alone; the sponsor plus a named technical owner with
  delegated acceptance of contract records. Recommendation: the sponsor as sole
  accepting authority until a technical owner is named, with acceptance
  recorded by pull request review.
- D02 (Q8). Who accepts trusted-boundary exceptions and released proof-API
  changes, and what is the default exception lifetime? Recommendation: the same
  authority as D01; every exception expires at the earlier of 90 days or the
  next release-gate task (4.3.3 or 6.3.4), with explicit renewal.
- D03 (Q4). Is the Core, Integration, and Deferred split in technical design
  §2 the intended release boundary? Recommendation: accept it unchanged.
- D04 (Q7, licence). Ratify ISC or choose another licence. Recommendation:
  ratify ISC, already present in `LICENSE` and `Cargo.toml`.
- D05 (Q7, publication). Recommendation: set `publish = false` in
  `Cargo.toml` until the Core acceptance dossier (task 4.3.3) passes and the
  D01 authority approves release; publish nothing to crates.io before then.
- D06 (pre-1.0 API policy). Recommendation: ratify ToR C5 and technical design
  §15 row 10 (no compatibility shims for pre-1.0 or unreleased APIs); follow
  Cargo's 0.y.z rule, in which a change to the leftmost non-zero component is
  breaking; version the public proof interface (models, pre- and
  postconditions, lemmas) with the crate version (technical design §17.8). The
  minimum supported Rust version (MSRV) stays with ToR Q3 and task 1.2.1.
- D07 (candidate ADR dispositions). Recommendation:
  numerical and array semantics to ADR-004 (this step); macro staging and
  stable-Rust application to ADR-005 (this step); initial feature and release
  scope to ADR-003 (this step); public proof compatibility to ADR-007 (this
  step); shared semantic kernel deferred to task 1.2.1 (falsifiable by B01 in
  1.2.4); backend and cell separation deferred to task 1.2.1; resource
  certification deferred to step 2.4 (B03); backend input and output control
  scope deferred to task 1.2.6 (B06).
- D08 (`comb!` operator precedence). Technical design §7 says only
  "familiar precedence". Options: adopt Rust's expression precedence exactly
  (as parsed by `syn`) and reject unparenthesized mixing of comparisons with
  `&` or `|`; or define a bespoke precedence in which `&` and `|` bind more
  loosely than comparisons. Recommendation: Rust precedence plus the mixing
  rejection, because Rust users already know it and because in Rust
  `x > 0 & y > 0` parses as a chained comparison, which the macro can turn into
  a first-screen diagnostic.
- D09 (binary `min` and `max`). Technical design §6.1 labels its rule
  "proposed". Recommendation: accept IEEE 754-2019 `minimum` and `maximum`
  semantics (NaN propagates; negative zero is less than positive zero), as
  written.
- D10 ("typed-cell atomicity" reading). The phrase covers two distinct rules:
  cell atomicity (a typed cell such as `DVec3` is one logical element until an
  explicit component operation; technical design §4.2, §17.3) and atomic output
  commit (failure or cancellation before commit leaves the destination
  unchanged; §17.5). Recommendation: record both, under those two distinct
  names, in ADR-004.
- D11 (Q2 environments). Recommendation: GitHub-hosted `ubuntu-latest` for
  categorical gates and for proof and build ceilings with generous margins; a
  named, otherwise idle reference machine (to be specified by the sponsor) for
  runtime ratio measurements. Shared development hosts are not acceptance
  environments.
- D12 (Q2 thresholds). The sponsor supplies or amends every numeric
  threshold. `EP-M4` drafts a proposed starting table (see `EP-M4`) clearly
  marked as a proposal.

## Verification plan

This step introduces repository-governance logic, not library semantics. The
obligations below concern that logic. The semantic contracts recorded in
`EP-M3` will be discharged against Rust code by the proof obligations already in
`spec/proof-obligations.json` (for example PF07 for reduction association in
tasks 2.2.x); this step checks only that the contracts are coherent, complete,
and non-vacuous in the documentation model.

Where Verus is warranted: nowhere in this step (see `Decision log`). Each
contract record names the PF obligation and the later task where Verus or Kani
discharges it, so proof structure influences the recorded contract without
proof plumbing being written now. Where Kani is warranted: nowhere in this
step. Proptest, `rstest`, `rstest-bdd`, `insta`, `googletest`, and
`pretty_assertions` are Rust tools; no Rust code changes, so they do not apply.
Their Python counterparts are `unittest` parameterized subtests, Hypothesis
properties, and the checker's generated-document drift comparison (a
golden-file snapshot).

### Abstract model of the evidence gate

The gate is specified as a function over an abstract record before it is
implemented. An abstract record is the tuple
`(status, outcome, witness, control, assumptions, exception, binding, scope)`:

- `status` in {planned, proved, bounded-checked, tested, trusted, failed,
  inconclusive};
- `outcome` in {verified, counterexample, timeout, unsupported, skipped,
  vacuous, missing, tool-error};
- `witness` in {observed, absent, not-satisfied};
- `control` in {rejected-for-intended-reason, rejected-for-other-reason,
  accepted, absent};
- `assumptions` in {all-reported, unreported-present};
- `exception` in {none, active, expired, malformed};
- `binding` in {complete, incomplete};
- `scope` in {covers-obligation, bounded-only, does-not-cover}.

The obligation side carries `requires` in {proof, proof-or-bounded}.

Merge-state rules (to be recorded in ADR-007 and implemented exactly):

- MS-1. `admit(r, o) = proof` exactly when `status` is proved or
  bounded-checked, `outcome` is verified, `witness` is observed, `control` is
  rejected-for-intended-reason, `assumptions` is all-reported, `exception` is
  none, `binding` is complete, and `scope` is covers-obligation, or `scope` is
  bounded-only with `status` bounded-checked and `o.requires` is
  proof-or-bounded.
- MS-2. `admit(r, o) = restricted` exactly when every MS-1 condition holds
  except that `exception` is active, or `status` is trusted with an active
  exception and `outcome` is verified. A restricted admission supports only the
  exception's narrowed claim and never satisfies a proof-required obligation.
- MS-3. Otherwise `admit(r, o) = rejected`, with every applicable reason code
  reported (for example `outcome-timeout`, `witness-absent`,
  `assumption-unreported`, `exception-expired`).
- MS-4. A roadmap task may have `status: done` only when every prerequisite
  task is done, every decision record it cites is accepted, and every PF
  obligation linked to it has at least one record admitted at level `proof`.
  Tasks with no linked PF obligation (all four 1.1 tasks) need only the first
  two conditions plus their listed completion artefacts.

Proposed lemmas (hypotheses about the proof structure; implementation may
refine them):

- L1 (non-success outcomes never pass): `outcome != verified` implies
  `admit = rejected`.
- L2 (exceptions never substitute for proof): `exception != none` or
  `status = trusted` implies `admit != proof`.
- L3 (assumption monotonicity): changing `assumptions` from all-reported to
  unreported-present never raises the admission level.
- L4 (witness and control necessity): `witness != observed` or
  `control != rejected-for-intended-reason` implies `admit = rejected`.
- L5 (bounded honesty): `status = bounded-checked` and
  `o.requires = proof` imply `admit != proof` unless `scope` is
  covers-obligation, which a bounded-checked record cannot claim (schema rule:
  a bounded-checked record must carry `scope.bounds`).
- L6 (task closure): `done(t)` implies `done(p)` for every prerequisite `p`.

### Obligations

- Obligation VO-1 (evidence admission, MS-1 to MS-3, L1 to L5).
  Method: exhaustive enumeration of the finite abstraction plus a
  concrete-record abstraction test. Rationale: the domain has 7 x 8 x 3 x 4 x 2
  x 4 x 2 x 3 x 2 = 64,512 states, which `unittest` checks in well under a
  second; exhaustive enumeration over a finite domain is a complete check,
  stronger than sampling. Oracle independence: the expected result comes from a
  declarative decision table in
  `tools/tests/fixtures/evidence_gate_table.json`, written from ADR-007 before
  the implementation and not imported from it. Artefact:
  `tools/tests/test_evidence_gate.py` and
  `tools/docs_validation/evidence_gate.py`. Evidence: before implementation the
  test fails with `ModuleNotFoundError` or with mismatches; after, all states
  agree. Non-vacuity: the enumeration asserts that each admission level (proof,
  restricted, rejected) occurs, and that each reason code occurs as the sole
  reason for at least one state. Seeded mutations that must fail: treating
  `timeout` as verified; ignoring `assumptions`; letting an active exception
  yield `proof`; accepting `rejected-for-other-reason` as a valid negative
  control.
- Obligation VO-2 (concrete-to-abstract mapping). Method: parameterized
  subtests over hand-built JSON records for every reason code, plus a
  Hypothesis property that generates schema-valid records and checks that
  `abstract(record)` round-trips the fields that determine admission. Domain:
  generated records with Hypothesis classification (`hypothesis.event`) per
  status and outcome. Artefact: `tools/tests/test_evidence_records.py`.
  Non-vacuity: the test fails if any status or outcome class is never generated
  (checked via the collected events), and a seeded mapping fault (reading
  `status` where `outcome` is intended) must fail.
- Obligation VO-3 (exception validity and expiry, MS-2). Method:
  parameterized boundary tests on the injected date: one day before expiry
  (active), on the expiry date (expired, by the recorded convention that
  `expires_on` is the first invalid day), after expiry (expired); missing
  owner, missing approval reference, or missing claim restriction (malformed).
  Artefact: `tools/tests/test_evidence_gate.py`. Non-vacuity: each malformed
  variant is rejected with its own reason code; a complete active exception
  yields `restricted`, proving the path is reachable.
- Obligation VO-4 (task closure, MS-4, L6). Method: parameterized tests over
  small synthetic roadmaps (a two-task chain and a diamond) plus the real
  `spec/roadmap.json`. Artefact: `tools/tests/test_roadmap_status.py`.
  Non-vacuity: marking a task done whose prerequisite is open fails; marking
  done with a proposed (not accepted) decision fails; a fully satisfied task
  passes; the generated Markdown shows `- [x]` only for done tasks, and a
  hand-edited `[x]` without `status: done` fails as generated-content drift.
- Obligation VO-5 (decision register integrity). Invariants: every decision
  ID is unique; an accepted decision names an authority that an accepted D01 or
  D02 record designates (D01 itself is accepted by the sponsor role); an
  accepted record has a date, an approval reference, and an ADR that exists with
  `Status` `Accepted`; a proposed record has no approval fields; each ToR
  question in scope maps to exactly one decision. Method: parameterized
  negative controls, one per invariant, plus schema validation. Artefact:
  `tools/tests/test_decision_register.py`. Non-vacuity: each control is
  rejected with a distinct message; the real register passes.
- Obligation VO-6 (five-document consistency). Invariants: each of the five
  governing documents links `decision-register.md`; for each accepted decision,
  none of its listed `supersedes_statements` appears in any governing document;
  the ADR `Status` line agrees with the register. Method: parameterized tests
  that reinsert a stale statement into an in-memory copy of each document.
  Artefact: `tools/tests/test_decision_register.py`. Non-vacuity: reinserting
  the current ToR sentence "The classes remain proposed pending ToR Q4." into
  technical design §2 after D03 is accepted fails.
- Obligation VO-7 (semantic contract coherence). Invariants: every contract
  record names catalogue IDs that exist in `spec/vocabulary.json`; has
  non-empty preconditions, postconditions, empty rule, and failure rule; cites
  at least one example ID that the documentation model evaluates; and names the
  PF obligation and task that will discharge it in Rust. Method: schema plus
  cross-reference checks, and extension of the documentation model in
  `tools/docs_validation/semantics.py` with new examples for empty `product`,
  `any`, `all`, `minimum`, `maximum`, and `mean`; casts (I64 to F64 rounding
  above 2^53, F64 to I64 non-integral, out-of-range, and NaN, Bool to I64
  rejection); Kleene `and`, `or`, `xor` truth tables; binary `min` and `max`
  with NaN and signed zeros; `skip_nulls` then empty. Artefact:
  `tools/tests/test_semantic_contracts.py`. Non-vacuity: seeded wrong semantics
  must produce a different outcome than the recorded example: left association
  for `reduce`, error instead of identity for empty `sum`, a silent finite
  identity for empty `minimum`, implicit I64 to F64 promotion for `add`,
  NaN-ignoring `min`, and two-valued null logic.
- Obligation VO-8 (grammar contract). Invariants: the accept and reject
  corpus in `spec/macro-grammar.json` agrees with the precedence and
  association table in ADR-005; `&&` and `||` between array operands are
  rejected; `||` inside an explicit `host { ... }` closure is accepted;
  unparenthesized mixing of comparison with `&` or `|` is rejected (if D08 is
  accepted as recommended); `|>` is left-associative and binds most loosely.
  Method: a small reference recognizer (a precedence-climbing parser of fewer
  than 200 lines) in `tools/docs_validation/grammar.py` that parses each corpus
  entry to a parenthesized form and compares it with the expected form.
  Artefact: `tools/tests/test_macro_grammar.py`. Non-vacuity: swapping the
  precedence of `*` and `+`, or making `|>` right-associative, or accepting
  `&&`, must each fail at least one corpus entry; the corpus must contain at
  least one entry per precedence level and per rejection rule (checked
  mechanically). Residual gap: this models the grammar, not the future `comb!`
  implementation; phase 2 replays the corpus as `trybuild` pass and fail
  fixtures.
- Obligation VO-9 (no superseded-name shims). Invariant: no name listed in
  the `excluded_names` register (derived from `docs/context.md` §6 and
  `docs/language-reference.md` §9: `a!`, `cells`, `cells2`, `id` as an alias of
  `identity`, `.pipe` accepting descriptors directly, array `&&` and `||`)
  appears as a catalogue name or alias in `spec/vocabulary.json`. Method:
  register check with a negative control that adds `cells` as a catalogue entry
  in memory. Artefact: `tools/tests/test_semantic_contracts.py`.
- Obligation VO-10 (pre-registration freeze). Invariants: a registered
  control's stored `digest` equals SHA-256 of the canonical JSON (sorted keys,
  no insignificant whitespace, UTF-8) of its frozen fields; a registered
  control has workload, control, environment, metric, unit, statistic,
  threshold, uncertainty rule, sample plan, and timeout rule; amendments are
  append-only, each with authority, reason, date, and the digest it replaces;
  no measurement record exists for a control registered after that measurement.
  Method: Hypothesis property that any single-field mutation of a frozen
  control changes the digest and is rejected unless accompanied by a matching
  amendment; parameterized completeness controls. Artefact:
  `tools/tests/test_preregistration.py`. Non-vacuity: the property records
  which field was mutated and fails unless every frozen field was exercised; a
  correctly amended change passes, so the check is not reject-everything.
- Obligation VO-11 (budget outcomes cannot be relabelled). Invariant: a
  measurement or proof run whose outcome is `timeout`, `budget-exceeded`, or
  `inconclusive` maps to fail or inconclusive, never to pass or to an evidence
  `outcome` of verified. Method: exhaustive enumeration of the measurement
  outcome mapping (finite). Artefact: `tools/tests/test_preregistration.py`.
  Non-vacuity: a seeded mapping that treats `timeout` as pass must fail.

Axioms (trusted, not verified here):

- A1. The `jsonschema` package implements Draft 2020-12 validation
  correctly. Exercised by existing schema negative controls.
- A2. Python's `hashlib.sha256` is a collision-resistant identity check. A
  digest proves identity of frozen fields, not their correctness.
- A3. Git history is the durable record of when a registration or acceptance
  entered the repository; the gate checks recorded dates for internal
  consistency, not against Git metadata.
- A4. The approval reference in an accepted record was given by the named
  authority. The gate cannot verify identity; review of the pull request is the
  control. This is a social axiom and is stated in ADR-002.
- A5. Producers of future evidence records (tasks 1.2.x onward) report
  observed trusted items (Verus `assume`, `admit`, `external_body`, and
  `external_fn_specification` items; Kani stubs and `assume` calls) in
  `observed_trust_items`. The gate enforces reported-versus-observed agreement;
  the producer's audit is verified when that producer is built.

## Plan of work

The work proceeds in six milestones. `EP-M1` needs no sponsor input. `EP-M2`
needs D01 to D07. `EP-M3` needs D08 to D10 and acceptance by the D01 authority.
`EP-M4` needs D11 and D12. `EP-M5` needs the D02 authority to accept ADR-007.
`EP-M3` and `EP-M4` both require only `EP-M2` and may proceed in either order
(roadmap: 1.1.2 and 1.1.3 each require only 1.1.1). Drafting for a later
milestone may proceed while an earlier milestone waits for acceptance, but no
record may be marked accepted, and no roadmap task marked done, out of
dependency order.

Each milestone follows Red, Green, Refactor:

- Stage A (understand and propose, no code): draft the ADR and records as
  `proposed`.
- Stage B (red): add the decision table, fixtures, and tests; run
  `python3 -m unittest discover -s tools/tests` and observe the expected
  failures (missing module, or mismatched admission).
- Stage C (green): implement the validators and records; the focused tests
  pass.
- Stage D (refactor and validate): tidy, run
  `python3 tools/check_docs.py --write`, review the report diff, then run the
  full gates through `scrutineer`.

### EP-M1. Governance machinery and the decision brief

Add `spec/decision-register.schema.json` and `spec/decisions.json` holding D01
to D12 as `proposed`, each with `question` (ToR ID), `authority_role`,
`options`, `recommendation`, `adr`, `supersedes_statements`, and (once accepted)
`accepted_by`, `accepted_on`, and `approval_reference`. Add the eight
candidate ADR subjects with a `disposition` field.

Add `tools/generate_decisions.py` (mirroring `tools/generate_bets.py`) that
renders `docs/decision-register.md` between `<!-- decisions:start -->` and
`<!-- decisions:end -->` markers, and `docs/decision-brief-1-1.md` (hand
written, not generated) presenting D01 to D12 for the sponsor.

Add `tools/docs_validation/decisions.py` with `check_decision_register` (VO-5,
VO-6) and register it in `tools/check_docs.py` `collect_checks`. Add
`docs/decision-register.md` and the brief to `DESIGN_DOCUMENTS` in
`tools/docs_validation/context.py`.

Add a roadmap status mechanism. In `spec/roadmap.json`, each task gains `status`
(`open` or `done`) and `completion` (a list of artefact references: decision
IDs, ADR paths, test IDs). `tools/generate_roadmap.py` renders `- [x]` for done
tasks. Replace `check_task_links`'s blanket ban in
`tools/docs_validation/ledger.py` with `check_task_status` (MS-4 without the PF
clause, which `EP-M5` adds). All tasks stay `open` in this milestone.

Link `docs/decision-register.md` from all five governing documents and from
`docs/contents.md`. Update `docs/developers-guide.md` "Design contract checks"
with the decision-register and roadmap-status workflow.

### EP-M2. Task 1.1.1: authority, scope, licence, and API policy

With the sponsor's answers to D01 to D07, write
`docs/adr-002-decision-and-exception-authority.md` (D01, D02, axiom A4) and
`docs/adr-003-release-scope-licence-and-api-policy.md` (D03 to D06). Record the
D07 dispositions in `spec/decisions.json`. Mark D01 to D07 `accepted` with the
approval reference from the sponsor's pull request review or comment.

Reconcile the five documents: ToR §9 rows Q1, Q4, Q7, Q8 gain "Resolved by D0n"
links (the table stays hand-written; its resolution column points at the
register); ToR §10 and technical design §15 replace the candidate-ADR prose
with a link to the register's disposition table and agree on all eight
subjects; technical design §2 drops "remain proposed pending ToR Q4" for the
accepted classes; GAP5 and GAP9 are updated; `docs/context.md` §7 and the
roadmap preamble ("no accepted ADR or ExecPlan exists") are updated;
`docs/language-reference.md` prose (outside the generated region) references
the accepted scope. Each replaced sentence is listed in the decision's
`supersedes_statements`, so VO-6 enforces it.

If D05 is accepted as recommended, add `publish = false` to `Cargo.toml`, and
add a check in `tools/docs_validation/decisions.py` that reads `Cargo.toml` with
`tomllib` and compares `license` and `publish` with the accepted D04 and D05
values (negative control: an in-memory manifest with a different licence
fails). Update `README.md` "Licence" and `docs/users-guide.md` with the
stability and publication policy.

Set task 1.1.1 `status: done` with completion references D01 to D07, ADR-002,
and ADR-003.

### EP-M3. Task 1.1.2: semantic and macro contract records

Draft `docs/adr-004-numeric-validity-and-reduction-contracts.md` (dtype set and
conversions, null and Kleene logic, association of `reduce`, `fold_left`,
`scan`, `scan_left`, `.reassociate()` failure equivalence, empty identities,
`.identity(value)`, `mean` and `variance` definitions, binary `min` and `max`
per D09, cell atomicity and atomic output commit per D10) and
`docs/adr-005-comb-macro-grammar-and-staging.md` (an EBNF grammar for `comb!`,
`verb!`, `host { ... }`, `arr!`, and `array!`; the precedence and association
table per D08; the staging phases construction, preparation, and execution with
what each may evaluate; the optional static-descriptor rule from technical
design §7).

Add `spec/semantic-contract.schema.json` and `spec/semantic-contracts.json`.
Before adding the schema, record in `docs/developers-guide.md` why
`spec/kernel-contract.schema.json` does not fit (it declares a native kernel's
execution envelope, not a primitive's public logical contract) and the reuse
policy: semantic contracts are owned by the design pack and consumed by later
proof tasks; kernel contracts remain the extension interface. Each record holds
`id` (SC-NN), `catalogue_ids`, `preconditions`, `postconditions`, `empty_rule`,
`failure_rule`, `examples`, `discharged_by` (PF ID and task), and `status`.

Add the new examples to `spec/examples.json` and extend
`tools/docs_validation/semantics.py` (split into a new module if it would
exceed 400 lines). Add `spec/macro-grammar.json` and
`tools/docs_validation/grammar.py`. Add the `excluded_names` register to
`spec/vocabulary.json` with its check. Tests: VO-7, VO-8, VO-9.

When the D01 authority accepts ADR-004 and ADR-005, set D08 to D10 and the
contract records to `accepted` and task 1.1.2 to `done`. Update technical
design §§6-7 to cite the ADRs, and reconcile `docs/context.md` §6 ("Formal
acceptance remains open") for the accepted rows.

### EP-M4. Task 1.1.3: pre-registered acceptance controls

Add `spec/acceptance-controls.schema.json` and `spec/acceptance-controls.json`,
`tools/docs_validation/preregistration.py` (VO-10, VO-11), and
`docs/adr-006-acceptance-control-pre-registration.md` (policy: register before
measuring; amendments append-only and authorized; timeouts and exhausted
budgets are failures or inconclusive, never passes; a lowered target after a
disappointing result is a new registration, labelled as such; shared
development hosts are not acceptance environments).

Draft, as a proposal for the sponsor to amend, controls for these named
workloads:

- AC-01 (task 1.2.4, B01): Verus verification of the cardinality kernel.
  Metric: wall time and peak solver memory per verification run. Proposed: at
  most 120 s and 4 GiB on `ubuntu-latest`; hard timeout 600 s counts as failure.
- AC-02 (tasks 1.2.4, 1.2.5, B01, B02): each Kani harness. Proposed: at most
  300 s per harness and 30 min per job, unwinding assertions enabled, every
  `kani::cover!` satisfied.
- AC-03 (task 2.4.x, B03): compile-time cost of static admission. Control:
  the same fixture without static descriptors. Proposed: incremental rebuild
  ratio at most 1.25 at the upper bound of a 95% bootstrap confidence interval
  over at least 10 runs.
- AC-04 (task 1.2.1, S7): cold and incremental builds of the native-only,
  proof-capable, and Polars-enabled profiles. Proposed: absolute ceilings set
  by the sponsor after the first recorded baseline, registered before any
  acceptance comparison.
- AC-05 (S1, S5): row centring, neighbourhood counting, and generalized
  contraction runtime against ordinary Rust controls. Proposed: ratio at most
  1.5 at the upper bound of a 95% bootstrap confidence interval; a straddling
  interval is inconclusive, not a pass.
- AC-06 (V9, V13): peak tracked allocation against the accounted bound.
  Categorical: tracked peak never exceeds the admitted bound.
- AC-07: pull request CI wall time. Proposed: design job at most 10 min;
  full PR pipeline at most 45 min.

Statistics follow the Criterion.rs analysis model (bootstrap confidence
intervals; a change within the noise threshold is not a change), but the
registration names the statistic and decision rule explicitly so that it does
not depend on a tool default. When the sponsor accepts the controls (D11, D12),
set each control's `status` to `registered`, compute and store its digest, and
mark task 1.1.3 done. Update ToR §7 and §9 Q2 to point at the register,
technical design §12 and §17.8, GAP2, and the bet register's measurement
sentences.

### EP-M5. Task 1.1.4: proof-first policy, public proof contract, and gate

Write `docs/adr-007-proof-first-policy-and-evidence-gate.md` containing the
abstract model, MS-1 to MS-4, lemmas L1 to L6, the public proof contract (what
downstream consumers may rely on: versioned models, pre- and postconditions,
lemmas, effect policies, trust declarations; technical design §17.8), and the
trusted-boundary authority from ADR-002.

Write the decision table fixture first (red), then revise
`spec/proof-evidence.schema.json` to revision `0.3`: add `outcome`; add
`toolchain` (Rust, Verus, Kani, and solver versions); add `binding` digests for
executable and specification identity; make `success_witness` and
`negative_control` objects that record what was observed (for the control: the
mutation, the expected failure reason, the observed failure reason); split
`assumptions` into `declared_assumptions` and `observed_trust_items`; give
`exception` the fields `owner`, `approved_by`, `approved_on`,
`approval_reference`, `expires_on`, `revisit_trigger`, `claim_restriction`, and
`obligation`. Update `spec/proof-evidence.example.json`,
`check_proof_evidence_envelope`, and every reference to revision `0.2` of this
schema in one change.

Implement `tools/docs_validation/evidence_gate.py` with `abstract_record`,
`admit`, and `check_task_evidence` (the PF clause of MS-4), and a command-line
entry `python3 tools/check_evidence.py --as-of YYYY-MM-DD RECORD...` that
prints the admission level and reason codes, so later tasks can run it on real
records. Tests: VO-1 to VO-4, VO-11. Update technical design §17.1 and §17.2,
ToR Q8, GAP9, and the B08 entry.

When the D02 authority accepts ADR-007, mark task 1.1.4 done.

### EP-M6. Reconciliation, roadmap closure, and final gates

Reconcile `spec/bets.json` task lists with the roadmap's bet tags (B01 and B02
gain 1.1.x where tagged), regenerate generated documents, update
`docs/validation.md` (counts and the description of the new checks),
`docs/repository-layout.md` (new `spec/` and `tools/` files, ADRs,
`docs/execplans/`), `docs/contents.md`, and `docs/revision-0.2.md` if its
"deliberately unchanged" list is affected. Run the full gates. Complete
`Outcomes & retrospective` and set this plan's status to `COMPLETE`.

## Milestones and plateaus

### EP-M1

- Identifier and outcome: `EP-M1`. The repository has a validated decision
  register with every record `proposed`, a decision brief, and an
  evidence-gated roadmap status mechanism with every task open.
- Requirements and gaps: advances ToR Q1, Q2, Q4, Q7, Q8 (presentation
  only); C6 enforced mechanically.
- Acceptance evidence: `make design-check` passes; the register negative
  controls (VO-5, VO-6 subset for links) and VO-4 synthetic roadmaps pass;
  `docs/decision-register.md` lists D01 to D12 as proposed.
- Conformance check:
  - No ToR question is marked resolved.
  - Technical design unchanged except links.
  - No upstream assumption falsified.
  - No public Rust interface or dependency change.
  - No trust-boundary or persisted-format change (new spec files are
    design-pack inputs, not wire formats).
  - Trace links added for D01 to D12.
- Recovery: revert the milestone commits; nothing downstream depends on them.
- Remaining gaps: every decision.
- Compatibility decision: none.

### EP-M2

- Identifier and outcome: `EP-M2`. D01 to D07 accepted; ADR-002 and ADR-003
  accepted; five documents reconciled; task 1.1.1 done.
- Requirements and gaps: ToR Q1, Q4, Q7, Q8 (authority); GAP5; part of GAP9.
- Acceptance evidence: `make design-check` passes with VO-5 and VO-6 over the
  accepted records; the roadmap shows `- [x] 1.1.1.`; the `Cargo.toml` metadata
  check passes.
- Conformance check:
  - 1.1.1 success text satisfied: Q1, Q4, Q7 owner decisions recorded;
    Core/Integration boundary and candidate ADR dispositions agree in all five
    documents.
  - Design followed, or amended only by accepted decisions.
  - If D03 amends the scope classes, impact-check R1 to R11 and the roadmap
    phase gates before accepting.
  - Only `Cargo.toml` metadata may change.
  - No trust-boundary change.
  - Trace links current.
- Recovery: an accepted decision is reversed only by a new decision record
  that supersedes it; Git revert is for unaccepted drafts.
- Remaining gaps: contracts, controls, gate.
- Compatibility decision: none.

### EP-M3

- Identifier and outcome: `EP-M3`. ADR-004, ADR-005, and contract records
  accepted; task 1.1.2 done.
- Requirements and gaps: R2 contracts recorded (not implemented); V8 and V1
  inputs.
- Acceptance evidence: VO-7, VO-8, VO-9 pass, including their seeded
  mutations; `make design-check` passes.
- Conformance check:
  - Association, empty identities, dtype conversion, macro grammar, and
    typed-cell atomicity each have an accepted record.
  - No superseded name reintroduced.
  - `comb!` notation unchanged (C2).
  - No Rust change.
  - Trace links to PF obligations current.
- Recovery: revert drafts; superseding records for accepted ones.
- Remaining gaps: Rust implementation and proofs (phase 2).
- Compatibility decision: none.

### EP-M4

- Identifier and outcome: `EP-M4`. Acceptance controls registered and frozen;
  task 1.1.3 done.
- Requirements and gaps: ToR Q2; GAP2 (thresholds recorded); V13 inputs.
- Acceptance evidence: VO-10, VO-11 pass; every AC entry is `registered`
  with a matching digest.
- Conformance check:
  - Named workloads, controls, environments, budgets, uncertainty handling,
    and thresholds recorded before any acceptance measurement (none exist).
  - No benchmark claims.
  - No Rust change.
  - Trace links current.
- Recovery: amendments, not edits, once registered.
- Remaining gaps: measurements (tasks 1.2.x onward).
- Compatibility decision: none.

### EP-M5

- Identifier and outcome: `EP-M5`. ADR-007 accepted; evidence schema
  revision `0.3`; evidence gate implemented and exhaustively tested; task 1.1.4
  done.
- Requirements and gaps: R8, V14, V20; ToR Q8 mechanics; GAP9.
- Acceptance evidence: VO-1 to VO-4 and VO-11 pass;
  `python3 tools/check_evidence.py --as-of 2026-10-10 spec/proof-evidence.example.json`
  reports `rejected` with reason `status-planned` (a planned record cannot be
  admitted), and the complete fixture reports `proof`.
- Conformance check:
  - The schema binds claims to executable and specification identities,
    toolchains, scopes, assumptions, and negative controls.
  - Exceptions have owners, expiry, revisit triggers, and claim restrictions.
  - Timeout, skipped, and vacuous results cannot pass.
  - Schema change applied atomically (no revision `0.2` consumers remain).
  - No Rust change.
- Recovery: revert; the schema has no external consumers yet.
- Remaining gaps: evidence producers (task 1.2.4 onward).
- Compatibility decision: none. The schema has no deployed consumer, so
  revision `0.2` is replaced, not preserved.

### EP-M6

- Identifier and outcome: `EP-M6`. All four 1.1 tasks shown done; documents,
  bets, validation report, and layout reconciled; plan `COMPLETE`.
- Acceptance evidence: full gate run passes (see `Validation and acceptance`).
- Conformance check: every discovery in `Surprises & discoveries` reconciled
  upstream or recorded as mechanical in `Decision log`.
- Recovery: revert reconciliation commits individually.
- Remaining gaps: steps 1.2 onward.
- Compatibility decision: none.

## Concrete steps

All commands run from the repository root,
`/home/leynos/.lody/repos/github---leynos---combobulate/worktrees/99861d46-f6f5-48d6-acfb-658bee9364bf`.

Install documentation tooling once:

```bash
python3 -m pip install -r tools/requirements.txt
```

Baseline before any change (expected to pass at the plan commit):

```bash
make design-check 2>&1 | tee /tmp/design-check-combobulate-1-1-resolve-acceptance-control-decisions.out
```

Red step for each milestone (expected to fail for the named reason):

```bash
python3 -m unittest tools.tests.test_evidence_gate 2>&1 | tail -n 5
```

```plaintext
ModuleNotFoundError: No module named 'docs_validation.evidence_gate'
FAILED (errors=1)
```

Green and refactor, then regenerate the evidence report:

```bash
python3 -m unittest discover -s tools/tests
python3 tools/check_docs.py --write
git diff --stat docs/validation-results.json
```

Regenerate generated documents after changing a JSON master:

```bash
python3 tools/generate_roadmap.py
python3 tools/generate_bets.py
python3 tools/generate_reference.py
python3 tools/generate_decisions.py
```

Gate sequence, run by `scrutineer`, one at a time, each through `tee` to
`/tmp/$ACTION-combobulate-1-1-resolve-acceptance-control-decisions.out`:

```bash
make fmt
make check-fmt
make lint
make test
make design-check
make markdownlint
make nixie
```

Evidence gate demonstration (after `EP-M5`):

```bash
python3 tools/check_evidence.py --as-of 2026-10-10 spec/proof-evidence.example.json
```

```plaintext
spec/proof-evidence.example.json: rejected [status-planned]
```

## Validation and acceptance

Quality criteria:

- Tests: `make test` passes unchanged (no Rust change);
  `python3 -m unittest discover -s tools/tests` passes, including every new
  test module named in `Verification plan`; each new test module was observed
  failing before its implementation for the expected reason.
- Verification: VO-1 to VO-11 discharged as described, with their
  non-vacuity checks passing.
- Lint and format: `make check-fmt`, `make lint`, `make markdownlint` (which
  also runs `make spelling`), and `make nixie` pass.
- Design contracts: `make design-check` passes and
  `docs/validation-results.json` is regenerated and committed.
- Performance: none in this step (thresholds are registered, not measured).
- Security: no network access added to checks; no secrets.

Behavioural acceptance, observable by a reviewer:

1. `docs/decision-register.md` lists D01 to D12 as accepted with dates and
   approval references, and all eight candidate ADR subjects with a disposition.
2. `docs/roadmap.md` shows `- [x] 1.1.1.` to `- [x] 1.1.4.` and no other
   ticked task.
3. Re-inserting "The classes remain proposed pending ToR Q4." into
   `docs/technical-design.md` makes `make design-check` fail, naming D03.
4. Changing AC-03's threshold from its registered value without an amendment
   makes `make design-check` fail, naming AC-03 and the digest mismatch.
5. `python3 tools/check_evidence.py` rejects a fixture whose `outcome` is
   `timeout` with reason `outcome-timeout`, and admits the complete fixture at
   level `proof`.

## Idempotence and recovery

Generators and `check_docs.py --write` are idempotent: rerunning them on an
unchanged tree produces no diff. Tests use in-memory copies for negative
controls and never write to `spec/` or `docs/`. If a milestone fails midway,
`git restore` the uncommitted files and rerun from its red step. Each milestone
ends in one or more commits that pass every gate, so any commit is a safe
rollback point. Accepted decisions are never deleted; reverse one by adding a
superseding decision, per the ADR amendment rules in
`docs/documentation-style-guide.md`.

## Artefacts and notes

Planned new files:

- `docs/decision-register.md` (generated), `docs/decision-brief-1-1.md`.
- `docs/adr-002-decision-and-exception-authority.md`,
  `docs/adr-003-release-scope-licence-and-api-policy.md`,
  `docs/adr-004-numeric-validity-and-reduction-contracts.md`,
  `docs/adr-005-comb-macro-grammar-and-staging.md`,
  `docs/adr-006-acceptance-control-pre-registration.md`,
  `docs/adr-007-proof-first-policy-and-evidence-gate.md`.
- `spec/decision-register.schema.json`, `spec/decisions.json`,
  `spec/semantic-contract.schema.json`, `spec/semantic-contracts.json`,
  `spec/macro-grammar.json`, `spec/acceptance-controls.schema.json`,
  `spec/acceptance-controls.json`.
- `tools/generate_decisions.py`, `tools/check_evidence.py`,
  `tools/docs_validation/decisions.py`, `tools/docs_validation/grammar.py`,
  `tools/docs_validation/preregistration.py`,
  `tools/docs_validation/evidence_gate.py`.
- `tools/tests/test_decision_register.py`,
  `tools/tests/test_roadmap_status.py`,
  `tools/tests/test_semantic_contracts.py`, `tools/tests/test_macro_grammar.py`,
  `tools/tests/test_preregistration.py`, `tools/tests/test_evidence_gate.py`,
  `tools/tests/test_evidence_records.py`,
  `tools/tests/fixtures/evidence_gate_table.json`.

## Interfaces and dependencies

No new dependencies. Python modules use the standard library plus the pinned
`jsonschema`, `hypothesis`, `markdown-it-py`, and `PyYAML` from
`tools/requirements.txt`; `tomllib` is in the standard library.

In `tools/docs_validation/evidence_gate.py`, define:

```python
class Level(enum.Enum):
    PROOF = 'proof'
    RESTRICTED = 'restricted'
    REJECTED = 'rejected'

@dataclasses.dataclass(frozen=True)
class Admission:
    level: Level
    reasons: tuple[str, ...]

def abstract_record(record: Mapping[str, object], as_of: datetime.date) -> AbstractRecord: ...
def admit(record: AbstractRecord, requires: Requirement) -> Admission: ...
def check_task_evidence(context: ValidationContext, tasks: Mapping[str, dict]) -> None: ...
```

`admit` is pure and total over `AbstractRecord`; it never raises for a
well-typed abstract record. `abstract_record` raises `ValidationError` only for
records that fail the schema, which `check_evidence.py` reports as
`rejected [schema-invalid]`.

In `tools/docs_validation/decisions.py`, define
`check_decision_register(context: ValidationContext) -> None` and
`check_package_policy(context: ValidationContext) -> None`. In
`tools/docs_validation/preregistration.py`, define
`frozen_digest(control: Mapping[str, object]) -> str` and
`check_acceptance_controls(context: ValidationContext) -> None`. In
`tools/docs_validation/grammar.py`, define
`parse(source: str) -> Parsed | Rejected` for the corpus model only.

## Signposts

Documentation to read before each milestone: `docs/terms-of-reference.md` §§4,
7-10; `docs/technical-design.md` §§2, 6, 7, 12, 14-17; `docs/context.md` §§6-7;
`docs/language-reference.md` §§6, 9; `docs/testable-bets.md` B01, B02, B03, B08;
`docs/developers-guide.md` "Design contract checks";
`docs/documentation-style-guide.md` (ADR section); `docs/references.md`
§D-CONTRACT; `docs/complexity-antipatterns-and-refactoring-strategies.md` (keep
checker functions small);
`docs/reliable-testing-in-rust-via-dependency-injection.md` (the same injection
principle applies to the `as_of` date);
`docs/rust-testing-with-rstest-fixtures.md` and
`docs/rust-doctest-dry-guide.md` (for phase 2 consumers of these contracts).

Skills: `execplans` (this document), `arch-decision-records` (ADR content),
`en-gb-oxendict-style` (prose), `hypothesis` (property tests),
`rust-verification`, `verus`, and `kani` (to phrase `discharged_by` targets
correctly), `firecrawl-mcp` (external facts), `commit-message`, and
`pr-creation`. Agents: `scrutineer` runs every gate; `scribe` may make
mechanical documentation edits; `wyvern` for read-only reconnaissance.

## Revision note

Initial draft, 2026-10-10. Pending community-of-experts review and sponsor
approval.
