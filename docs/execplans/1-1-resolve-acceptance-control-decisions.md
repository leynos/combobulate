# Resolve the decisions that control acceptance (roadmap 1.1)

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: COMPLETE (implementation of `EP-M0` to `EP-M6` on 2026-10-11, in the
stacked pull requests #11 to #18; local CodeRabbit CLI reviews of `EP-M2`
onward and the sponsor's review and merge of each pull request remain)

Approval of the plan is distinct from acceptance of a decision; acceptances are
recorded per decision identifier (see `Sponsor decisions`).

## Purpose / big picture

Roadmap step 1.1 asks: which constraints are approved, and which remain
experiments? Before this work, every Combobulate design document was labelled
"proposed", no decision had an accountable owner, no acceptance threshold
existed, and the repository's checker forbade marking any roadmap task
complete. Any later implementation could therefore have had its success
criteria changed after the fact, which the terms of reference (ToR) prohibit.

After this work, a reviewer can do five observable things that were impossible
before:

1. Run `make design-check` and read `docs/decision-register.md`, a generated
   register naming, for each governing ToR question (Q1, Q2, Q4, Q7, Q8), the
   accountable authority, the option chosen, the date, the approval reference,
   and the architectural decision record (ADR) holding the rationale. The same
   run fails if any of the five governing documents still describes an accepted
   decision as open.
2. Read accepted contract records for association, empty identities, dtype
   conversion, validity, the `comb!` macro grammar, and typed-cell atomicity.
   Each record states preconditions, postconditions, empty and failure rules, a
   proof sketch for the later Verus or Kani work, and executable examples; the
   documentation model rejects deliberately wrong semantics.
3. Read pre-registered resource, performance, build, and proof controls whose
   thresholds are calibrated from recorded measurements and extrapolated to the
   pinned GitHub runner class. A pull request that changes a registered
   threshold without an authorized amendment fails the `Design contracts`
   workflow, even if it also recomputes the stored digest.
4. Run `python3 scripts/check_evidence.py` on a proof-evidence record and see a
   timeout, skipped harness, unsatisfied `cover`, negative control that failed
   for the wrong reason, unaudited or uncovered trusted assumption, stale
   binding, focused run, self-reported verdict, or expired exception rejected
   with a specific reason code, while a complete record is admitted at the
   level it has earned (`proof`, `bounded`, or `tested`).
5. See roadmap tasks 1.1.1 to 1.1.4 ticked in the canonical `docs/roadmap.md`,
   with the checker confirming that each tick is backed by evidence.

Term definitions used throughout:

- Sponsor: the project sponsor named in ToR §4. Per D01, the sponsor and the
  technical owner are both the GitHub login `leynos`. Only that authority can
  accept a decision. The implementing agent drafts and recommends; it never
  accepts.
- Decision record: an entry in `spec/decisions.json`, rendered into
  `docs/decision-register.md`, usually with an ADR in `docs/adrs/`. Its
  lifecycle is `proposed`, `accepted`, `superseded`, or `withdrawn`.
- Contract record: an entry in `spec/semantic-contracts.json` stating one
  public primitive's logical contract, independent of any implementation. It
  takes its acceptance from a decision record.
- Pre-registration: recording a measurement's workload, control,
  environment, estimand, and decision rule before any acceptance measurement,
  so the threshold cannot be tuned to the result.
- Calibration run: an exploratory measurement used only to choose a
  pre-registered threshold. It never counts as acceptance evidence.
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
  deployment claims (ToR C6). An `accepted` record carries a structured
  approval reference: `kind` (`session`, `pr-review`, `pr-comment`, or
  `commit`), `url`, `author_login`, `names_decisions`, and, for `session`, the
  verbatim answer. `author_login` must be `leynos` (D01). Ambiguous approval
  ("looks good") accepts nothing; the agent asks again. The sponsor's merge of
  the pull request that records an acceptance is the durable confirmation.
- C-EP-2. Approval is not verification (roadmap 1.1.1). No accepted decision
  may change a proof obligation's status, mark a bet as run, or record a
  capability as eligible.
- C-EP-3. Retain `comb!` ergonomics and names (ToR C2). The grammar contract
  must not introduce `a!`, glyph notation, or an alternate pipeline macro.
- C-EP-4. No compatibility machinery (ToR C5, technical design §15). The
  proof-evidence schema change (to `schema_version` 2) and the ADR relocation
  update every consumer and link atomically; no dual-schema acceptance, alias
  field, redirect file, or deprecated enum value.
- C-EP-5. Canonical sources stay canonical. `docs/roadmap.md` is canonical;
  `spec/roadmap.json` is a derived export checked for drift (D15).
  `docs/testable-bets.md`, `docs/language-reference.md` (catalogue region), and
  `docs/decision-register.md` remain generated from their JSON masters.
- C-EP-6. The design-model checker remains a documentation-model checker. It
  must not claim Rust compilation, Kani, Verus, or Polars results; the
  `NOT_RUN` list in `tools/check_docs.py` stays truthful.
- C-EP-7. Checker logic lives in `tools/docs_validation/` and follows the
  existing `tools/` conventions (`unittest` plus pinned Hypothesis with
  `derandomize=True`, dependencies pinned in `tools/requirements.txt`).
  Runnable helper scripts live in `scripts/` and follow
  `docs/scripting-standards.md` (`uv` shebang, PEP 723 block, Python 3.14,
  Cyclopts with `INPUT_*` environment support, pytest suites in
  `scripts/tests/` named after the script); when the checker needs a helper's
  logic it loads the script by path rather than duplicating it. No Python file
  exceeds 400 lines. Checks perform no network access.
- C-EP-8. No Rust library behaviour, public API, or Rust dependency changes.
  The only Rust-adjacent edit is `publish = false` in `Cargo.toml` (D05).
  Calibration probes live outside the repository's Cargo package (see `EP-M4`).
- C-EP-9. Checks are deterministic for a given commit. The evidence gate
  never reads the wall clock; `make design-check` injects the HEAD commit date
  as `--as-of`, and the base revision for freeze checks as `--base-rev`. No
  check reads environment variables.
- C-EP-10. Fail closed. Until a log parser registered for a verifier
  re-derives a record's verdict from a committed raw log (task 1.2.4 onward),
  no record from that verifier can be admitted at `proof` or `bounded`. Until
  `EP-M5` lands, no task with a linked proof-obligation component can be ticked.
- C-EP-11. Gates run sequentially through the `scrutineer` agent, with
  output captured under `/tmp`. `make fmt` (which writes files) runs before,
  never inside, a scrutineer gate run.
- C-EP-12. No hostnames, usernames, or absolute home paths in repository
  documents or records (D11). Measurement records describe hardware by class
  only: CPU model, core and thread counts, memory, operating-system family, and
  kernel major version.
- C-EP-13. No `.github/CODEOWNERS` (D13). Governance relies on the
  base-revision freeze check and the sponsor's pull request review and merge.

If satisfying the objective requires violating a constraint, stop, record the
conflict in `Decision log`, set the status to `BLOCKED`, and escalate.

## Tolerances (exception triggers)

- Scope per milestone: more than 25 changed files or more than 1,500 net
  added lines (excluding generated Markdown regions, derived exports,
  `docs/validation-results.json`, calibration transcripts, and the gate rule
  fixture) triggers escalation. The whole step is estimated at about 80 changed
  files across eight milestones; if the estimate grows past 100, escalate.
- Owner input: if a milestone needs a sponsor decision not yet given, set the
  status to `BLOCKED` at that milestone and ask, naming the decision
  identifiers. If no answer arrives within 10 working days, report the block.
- Upstream conflict: if implementation shows that an accepted decision
  contradicts an explicit user constraint (ToR C1 to C9), present the conflict
  and the required upstream edit before continuing.
- Interface: if a Rust public API, Rust dependency, or Make target name must
  change, stop and escalate. New Make variables (`AS_OF`, `BASE_REV`) on the
  existing `design-check` target are in scope. If a Rust contract test in
  `tests/` pins edited Makefile or workflow text, update that test in the same
  commit; if the change would alter a tested contract's meaning, escalate.
- Dependencies: Wenmode 0.15.2 is sponsor-directed (D15). Any other Python
  dependency beyond `tools/requirements.txt` triggers escalation.
- Calibration: if a calibration workload cannot run locally (for example a
  Verus release incompatible with the pinned nightly), record the gap, use the
  nearest runnable proxy with its limitation stated, and report it; do not
  invent a number.
- Iterations: a gate still failing after three fix attempts for the same
  cause triggers escalation with the log path.

## Risks

- Risk: the gate tests its inputs' self-description, so a fabricated record
  passes. Severity: high. Likelihood: high without mitigation. Mitigation:
  C-EP-10; provenance and log digests in the schema; the complete
  admit-at-`proof` fixture lives only under `tools/tests/fixtures/`.
- Risk: a threshold and its digest are edited together in one commit.
  Severity: high. Likelihood: medium. Mitigation: the base-revision freeze
  check (VO-7) compares against the merge base in CI. Without CODEOWNERS (D13),
  the sponsor's review and merge is the human control; the freeze check makes
  the change visible as a named failure rather than relying on the reviewer to
  notice.
- Risk: calibration on a shared, contended development machine misstates
  runner performance. Severity: medium. Likelihood: high. Mitigation: pin
  parallelism to the runner's 4 vCPUs, repeat runs and take the median, record
  compile-admission queue time separately from compile time, prefer
  deterministic resource limits (Verus `rlimit`) as primary budgets, and set
  thresholds at the extrapolated median times a stated safety margin.
- Risk: an exception expires and breaks CI for an unrelated contributor.
  Severity: medium. Likelihood: medium. Mitigation: a 14-day warning printed
  (not recorded in the report); a weekly scheduled `Design contracts` run so
  expiry surfaces on `main` first; a renewal runbook in
  `docs/developers-guide.md`.
- Risk: the decision table and the implementation share an error. Severity:
  medium. Likelihood: medium. Mitigation: the compact rule table is part of
  ADR-0009, accepted by the sponsor; substantive admission properties are
  checked against the table itself; an upstream scenario corpus derived from
  the bet register and proof ledger checks both.
- Risk: text-based cross-document checks are evaded by rewording or broken by
  rewrapping. Severity: medium. Likelihood: medium. Mitigation: positive
  anchors, whitespace- and inline-Markdown-normalized matching for retired
  statements, and a per-question open-status pattern check.
- Risk: the Wenmode-based roadmap exporter misreads Markdown structure and
  silently drops content. Severity: medium. Likelihood: medium. Mitigation:
  `EP-M0` proves the export reproduces the current `spec/roadmap.json` exactly
  before the old generator is removed, rejects unknown structure with a source
  line, and round-trips generated roadmaps through an independent renderer.
  Upstream issue leynos/mapsplice#144 tracks the replacement.
- Risk: governance Python grows beyond what one maintainer will sustain.
  Severity: medium. Likelihood: medium. Mitigation: per-module owners in
  `docs/developers-guide.md`; the grammar recognizer is retired when task 2.3.1
  replays the corpus; the roadmap exporter is retired when mapsplice ships an
  export.
- Risk: `docs/validation-results.json` conflicts between stacked branches.
  Severity: low. Likelihood: high. Mitigation: milestones land sequentially;
  the documented conflict rule is "take either side, rerun the generators and
  `check_docs.py --write`".

## Progress

- [x] (2026-10-10) Reconnaissance with a Wyvern team.
- [x] (2026-10-10) External research: Cargo pre-1.0 SemVer rules, the
  `jsonschema` Draft 2020-12 validator, Kani `cover` reporting, Criterion.rs
  bootstrap analysis, IEEE 754-2019 `minimum` and `maximum`, GitHub-hosted
  runner specifications, Wenmode.
- [x] (2026-10-10) First draft written and committed.
- [x] (2026-10-10) Community-of-experts review (six lenses). Verdict: revise.
  See `Design review record`.
- [x] (2026-10-10) Plan revised to address every blocking finding.
- [x] (2026-10-10) Base pull request #8 (`typos.toml` regeneration) merged by
  the sponsor; this branch rebased onto `main`.
- [x] (2026-10-10) Sponsor decisions D01 to D15 received in the Lody session
  and folded into this revision.
- [x] (2026-10-10) Upstream request leynos/mapsplice#144 filed for a JSON
  export and export validator.
- [x] (2026-10-10) `EP-M0` Make `docs/roadmap.md` canonical with a Wenmode
  exporter and drift validator (separate stacked pull request,
  sponsor-directed). Evidence: the fresh export equals the previous
  `spec/roadmap.json` exactly apart from the new per-task `status` field. On
  2026-10-11 the exporter moved to `scripts/export_roadmap.py` (Cyclopts, PEP
  723) per the sponsor. 18 pytest cases in
       `scripts/tests/test_export_roadmap.py`
  pass, including the command line, `INPUT_CHECK`, and a 60-example
  derandomized round-trip property that observed every required structural
  class; 2 checker-gate cases pass in
  `tools/tests/test_roadmap_export_gate.py`; seeded faults (dropped details,
  ignored ticks) each fail the suite; the script runs through its own `uv`
  shebang; `make design-check` passes.
- [x] (2026-10-11) Sponsor approval of this revision (implementation workflow
  invoked for this plan).
- [x] (2026-10-11) `EP-M1a` ADR relocation, decision register, generator, and
  anchors (branch `1-1-decision-register`, stacked on `EP-M0`). Evidence: ADR
  001 moved to `docs/adrs/adr-0001-repository-bootstrap.md` with every link
  updated and the style guide amended (D07); `spec/decisions.json` holds D01 to
  D15 (all `proposed`) and the eight candidate ADR subjects; 11 pytest cases in
  `scripts/tests/test_generate_decisions.py` (red first: module missing) and 33
  `unittest` cases in `tools/tests/test_decision_register.py` pass; seeded
  mutations (open-status pattern disabled, supersession check removed) each
  fail their control; a hand edit of `docs/decision-register.md` fails the
  drift check (VO-14).
- [x] (2026-10-11) `EP-M1b` Roadmap status, obligation components, and freeze
  check (branch `1-1-roadmap-closure`, stacked on `EP-M1a`). Evidence: 27
  `unittest` cases in `tools/tests/test_roadmap_status.py` and
  `tools/tests/test_freeze.py` (red first: modules missing) pass, covering a
  chain and a diamond, every MS-4 failure reason, fail-closed record
  components, a checker-sourced component, and a temporary Git repository for
  the base-revision comparison; every obligation has one component per linked
  task, with `PF14.structural@1.1.4` accepting `tested` from
  `checker:evidence-gate`; `make design-check BASE_REV=...` passes.
- [x] (2026-10-11) `EP-M2` Task 1.1.1: authority, scope, licence, and API
  policy recorded (branch `1-1-governance-decisions`, stacked on `EP-M1b`).
  Evidence: ADR-0002 to ADR-0005 accepted; D01 to D07 and D13 accepted in
  `spec/decisions.json` with `kind: session` references quoting the sponsor's
  answers, D01 and D13 on option B; the five governing documents reconciled,
  with 12 replaced sentences listed in `retired_statements`; ToR §9 rows Q1,
  Q4, Q7, and Q8 link their register anchors; `Cargo.toml` sets
  `publish = false` and `cargo publish --dry-run` refuses; 4 cases in
  `tools/tests/test_package_policy.py` (red first) and 5 real-document VO-6
  controls pass (reinserting the Q4 sentence, rewrapped or not, writing "Q4
  remains open", or deleting the Q4 anchor each fails naming D03); task 1.1.1
  ticked with its completion record, and the checker reports it backed.
- [x] (2026-10-11) `EP-M3` Task 1.1.2: semantic and macro contract records
  (branch `1-1-semantic-contracts`, stacked on `EP-M2`). Evidence: ADR-0006 and
  ADR-0007 accepted; D08, D09, D10, and D14 accepted with session references
  (D08 and D09 share one answer); `spec/semantic-contracts.json` holds `SC-01`
  to `SC-10` with 51 handwritten tagged-scalar examples (`EX21` to `EX71`) and
  a 28-entry `comb!` corpus (`G01` to `G28`); 29 catalogue contracts cite their
  records; seven superseded names are excluded; 211 `unittest` cases pass,
  including 26 new ones (VO-8 to VO-10 negative controls, four Hypothesis
  properties, and the ADR-0007 table agreement); every seeded mutation changes
  at least one outcome; the recognizer is 198 lines; task 1.1.2 ticked and
  backed.
- [x] (2026-10-11) `EP-M4` Task 1.1.3: calibrated acceptance controls
  pre-registered (branch `1-1-acceptance-controls`, stacked on `EP-M3`).
  Evidence: ADR-0008 accepted; D11 and D12 accepted (both option B) with
  session references; `AC-01` to `AC-07` registered with every frozen field and
  SHA-256 digests, four calibrated from records in `spec/calibration/` and
  three labelled not calibrated with reasons; the probe in
  `tools/calibration/cardinality-probe/` verifies in Verus (8 functions, a
  seeded mutant rejected) and its structural Kani harnesses satisfy every
  `cover!`; 29 cases in `tools/tests/test_preregistration.py` and
  `tools/tests/test_freeze.py` pass, including the exhaustive outcome mapping,
  a Hypothesis property that exercised every frozen field, a
  threshold-plus-digest edit rejected without an amendment, and host-identity
  scans with the local host name supplied at test time; the CI `build-test` job
  has `timeout-minutes: 8` (`AC-07`); task 1.1.3 ticked and backed.
- [x] (2026-10-11) `EP-M5` Task 1.1.4: proof-first policy and evidence gate
  (branch `1-1-evidence-gate`, stacked on `EP-M4`). Evidence: ADR-0009 accepted
  under D02 and D06; the rule-table fixture and gate tests written first (red:
  module missing); the gate agrees with an independent interpreter of the
  fixture on all 345,600 states (86,400 valid), every level and reason occurs
  alone, P1 to P4 hold over the enumeration, the upstream scenario corpus (B01,
  B02, B08, PF14, §17) passes, and five seeded rule-table faults are each
  caught; VO-2 round-trips every valid state through a concrete schema version
  2 record, and the schema agrees with the validity predicate on all 120 kind,
  outcome, and bounds combinations; VO-3 checks the exception window
  boundaries, each D02 violation, and P5; P6 and record-sourced closure pass;
  `scripts/check_evidence.py` rejects the planned example (exit 1), admits the
  complete test fixture at `tested`, reports partial bounds at `bounded` (never
  `proof`), and rejects resource-exhausted and self-reported fixtures with
  their reasons; `PF14.structural@1.1.4` is satisfied by the passing
  `evidence-gate` check and task 1.1.4 is ticked.
- [x] (2026-10-11) `EP-M6` Reconciliation, roadmap closure, and final gates
  (branch `1-1-reconciliation`, stacked on `EP-M5`). Evidence: D15 accepted and
  its four details added to tasks 1.2.1, 1.2.3, 1.2.4, and 2.3.1 in the
  canonical roadmap and re-exported; every decision D01 to D15 is accepted; 73
  one-way task-to-bet links and one bet-to-task link reconciled, with a two-way
  check and negative controls (VO-15); repository layout, contents, validation,
  and developers' guide updated (module ownership, exception renewal, control
  amendment, report conflicts); full gates pass.

## Surprises & discoveries

- Observation: the hand-edit drift controls edited "Decision: pending.",
  which vanished once every decision was accepted, so the edit became a no-op
  and the control passed vacuously. Evidence: `make design-check` on `EP-M6`
  failed with "AssertionError not raised". Impact: the controls now edit text
  that is always generated and assert that the edit changed something.
- Observation: a synchronize run on #16 received `github.base_ref` = `main`
  although the pull request's base is `1-1-semantic-contracts`, so its freeze
  check compared against `main` and found no frozen registers. Evidence: Design
  contracts run 38098734956 ("Freeze check against 2f856b0 passed for no frozen
  registers"); earlier runs on #13 to #16 used their stacked bases. Impact: from
  `EP-M5` the workflow takes the merge base with the event's
  `pull_request.base.sha` and prints the selected base.
- Observation: the hosted design check failed on #16 because the
  host-identity test also supplied the user name, which is `runner` on GitHub
  runners and is an ordinary word in the CI calibration record. Evidence:
  Design contracts run 38098132965, "spec/calibration/ci-history.json contains
  host identity 'runner'". Impact: the test supplies only the host name; user
  names are still caught through the home-path patterns (D11 concerns host
  names).
- Observation: symbolic 64-bit multiplication is out of reach for Kani on
  this host. Evidence: a harness asserting the exact product of three full-width
  `usize` extents was stopped after 900 s, and one bounded below 2^16 after 18
  min 46 s (18 min 27 s of CPU), both without a verdict
  (`spec/calibration/verifier-probe.json`); Verus proved the unbounded
  specification in under 2 s. Impact: `AC-02` scopes Kani to structural
  harnesses, and multiplication-heavy properties go to Verus under `AC-01`;
  task 1.2.4 should plan its proofs accordingly.
- Observation: a usable Verus release already existed at user level
  (`0.2026.09.06.8dea4a2`, Rust 1.98.0), but it requires exactly Z3 4.16.0; the
  locally available Z3 4.12.1 crashed its response parser. Impact: Z3 4.16.0
  was installed from the upstream release into a user-level directory
  (`sha256 7288c49a...`), and no repository file names the location.
- Observation: the shared host was heavily contended during calibration (load
  average 20 to 41 on 24 threads; four of four compile-admission slots held by
  other agents). Impact: the factor uses medians of a workload run on both
  machines, and thresholds round up generously; noisy local wall times inflate
  thresholds rather than tighten them.
- Observation: tests written while nothing was accepted or ticked assumed
  that state (the exporter's all-open assertion and its 1.1.1 checkbox
  controls; register tests seeded from the committed register). Evidence: they
  failed once 1.1.1 was ticked and D01 to D07 accepted. Impact: checkbox
  controls now target task 2.1.1, the all-open assertion derives the expected
  ticks from the Markdown, and synthetic register tests start from a
  `proposed_register()` baseline, so later milestones do not break them.
- Observation: the hosted `build-test` job failed `make check-fmt` on the
  plan itself for #9, #11, and #12. Evidence: CI pins mdtablefix 0.6.0, whose
  `--renumber` treats a wrapped line beginning "2026." as an ordered-list item;
  the local 0.6.1 does not. Impact: the line was reworded in the plan branch
  and the stack rebased (range-diff showed identical patches); local formatting
  checks now also run mdtablefix 0.6.0 before publication.
- Observation: generated register text containing `Batch<DVec3>` failed
  `make fmt` (markdownlint MD033, inline HTML). Evidence: `make fmt` exit 2
  naming `docs/decision-register.md`. Impact: register master text puts code
  identifiers in backticks.
- Observation: `tools/tests/test_docs_validation.py` pinned the checked
  Markdown count at 10. Impact: it now derives the count from
  `DESIGN_DOCUMENTS`, so adding a design document needs no test edit.
- Observation: the checker forbids any completed roadmap task.
  Evidence: `tools/docs_validation/ledger.py` `check_task_links` fails with
  "Roadmap has fabricated completed tasks"; `tools/generate_roadmap.py` always
  emits `- [ ]`. Impact: `EP-M1b` replaces the ban with an evidence check.
- Observation: PF14 already links task 1.1.4, with methods Verus, Kani, and
  "structural validation". Impact: obligations gain per-task components; 1.1.4
  discharges only `PF14.structural@1.1.4`, at level `tested`.
- Observation: the proof-evidence schema's `status` mixes evidence kind with
  result, so contradictory records are schema-valid. Impact: `EP-M5` splits
  `status` into `evidence_kind` and `outcome`.
- Observation: the catalogue permits Bool-to-I64 and Bool-to-F64 casts and
  forbids numeric-to-Bool (`spec/vocabulary.json` V031). Impact: VO-8 encodes
  this correctly.
- Observation: `syn` rejects chained comparisons with "comparison operators
  cannot be chained", while single mixes such as `a & b > c` parse silently.
  Impact: the D08 rule is a syntax-tree check plus a translated parse error.
- Observation: the system Python lacks `markdown-it-py`, so `make design-check`
  fails without a prepared environment. Impact: concrete steps use
  `uv run --python 3.14 --with-requirements tools/requirements.txt`.
- Observation: `make spelling` checks only tracked files, and the gate
  rejects the existing schema field spelling `result_art...` (American
  spelling). Impact: commit before relying on the gate; schema version 2
  renames the field to `result_artefacts`.
- Observation: after the sponsor merged #8, GitHub's stacked pull request
  handling rebased this branch onto `main` server-side. Impact: fetch and
  compare before any force push; never overwrite a remote head unseen.
- Observation: the development machine is larger than local agent notes
  state (12 cores, 24 threads, about 125 GiB memory), and Rust compilation
  passes through a shared admission queue. Impact: calibration pins parallelism
  and separates queue time (`EP-M4`).
- Observation: Verus is not installed on the development machine; Kani is.
  Impact: `EP-M4` installs a pinned Verus release in a user-level tool
  directory for calibration only.
- Observation: the repository is public, so standard hosted Linux runners
  provide 4 vCPUs, 16 GB of memory, and 14 GB of SSD storage on x64 (GitHub
  documentation, 2026-10-10). Impact: calibration extrapolates to that class.
- Observation: ISC already appears in `Cargo.toml`, `LICENSE`, and
  `README.md` through ADR 001; D04 ratifies it.

## Decision log

- Decision: `EP-M2` milestone review dispositions (CodeRabbit CLI, three
  minor findings, all fixed). The terms-of-reference handoff now names the ADRs
  each candidate subject is assigned rather than claiming ADR-0006 and ADR-0007
  existed before `EP-M3` (fixed in the `EP-M2` layer and the stack restacked;
  range-diff showed identical patches above it); the register renders session
  answers as verbatim blockquotes that keep paragraph breaks; the
  package-policy result names only the rules it enforced. Fixes to rendering
  and reporting landed in `EP-M6`. Date/Author: 2026-10-11, implementing agent.
- Decision: `EP-M5` milestone review disposition (CodeRabbit CLI):
  `scripts/check_evidence.py` stopped at the first schema-invalid record and
  raised on an unreadable file; it now reports every record, names unreadable
  and invalid files, and exits 2 after the loop. Date/Author: 2026-10-11,
  implementing agent.
- Decision: `EP-M5` exceeded both per-milestone tolerances: 39 changed files
  against 25, and about 1,900 net added lines against 1,500, excluding the
  regenerated regions, the export, and the report. The evidence fixtures (six
  JSON files under `tools/tests/fixtures/evidence/` plus the rule-table
  fixture), the version 2 schema, and the five test suites the plan requires
  (VO-1 to VO-4 and the command) account for most of it. Escalated to the
  sponsor in the milestone pull request. Date/Author: 2026-10-11, implementing
  agent.
- Decision: in `EP-M5`, P1's order for the exception field depends on the
  kind: for a trust declaration an active exception is better than none,
  because a declaration exists only to carry one (the enumeration found this).
  `outcome-not-run` is not a reason code, because an executed kind that did not
  run fails the validity predicate first. Without an evaluation date the gate
  treats every exception as malformed (fail closed). The parser registry under
  `tools/tests/fixtures/evidence/` is test-only; the repository registry
  registers no parser, so verifier evidence stays self-reported until tasks
  1.2.1 and 1.2.4 (C-EP-10). Date/Author: 2026-10-11, implementing agent.
- Decision: `EP-M4` milestone review dispositions (CodeRabbit CLI). Fixed in
  this layer before any merge or acceptance measurement: `verdict` read a
  `control_id` field that the measurement-record schema names `control_ids`
  (the test fixture is now schema-validated); registered workload sources are
  now checked against their SHA-256 digests, which exposed that `AC-02`'s
  digest predated `rustfmt` on the probe, so its source digest and control
  digests were recomputed. The wording findings inside frozen derivations
  ("rounded up to 64 MiB", the ten-harness job budget) are clarified in the
  calibration report rather than by editing registered fields. Date/Author:
  2026-10-11, implementing agent.
- Decision: `EP-M4` exceeded both per-milestone tolerances: 29 changed files
  against 25, and about 1,990 net added lines against 1,500, excluding the
  regenerated register and bet regions, the export, the report, and the probe's
  generated `Cargo.lock` (1,899 lines, committed so the Polars dependency tree
  behind the calibration is reproducible). Most of the remainder is calibration
  evidence and the control register (`spec/` calibration records, about 520
  lines; `spec/acceptance-controls.json`, 511). Escalated to the sponsor in the
  milestone pull request. Date/Author: 2026-10-11, implementing agent.
- Decision: the runner extrapolation factor comes from one workload run on
  both machines (the design checks' unittest and pytest suites at commit
  398d2f6, hosted run 38095157811) rather than a published processor benchmark,
  because the hosted runner's CPU model is not recorded and the shared workload
  removes that uncertainty. Ratios of hosted to local medians were 0.92 and
  1.17; the factor is the larger, rounded up to 1.2. Builds use the same factor
  with parallelism pinned to 4 jobs. Calibration reused the existing user-level
  Verus build rather than installing a second copy. Date/Author: 2026-10-11,
  implementing agent.
- Decision: `EP-M3` exceeded the per-milestone line tolerance (about 2,800
  net added lines against 1,500, excluding the regenerated reference table, the
  register region, the export, and the report; 24 files, within the file
  tolerance). About 1,480 lines are the three JSON data files the milestone
  exists to create (`spec/examples.json` additions, 562;
  `spec/semantic-contracts.json`, 534; `spec/macro-grammar.json`, 385), written
  with the repository's indented JSON style. Escalated to the sponsor in the
  milestone pull request; splitting the contracts from their examples would
  have left either half unverifiable. Date/Author: 2026-10-11, implementing
  agent.
- Decision: in `EP-M3`, contract records whose rules come from technical
  design §6 rather than from D08 to D14 (association, empty identities,
  conversion, integer division, Kleene logic) cite D07, the accepted decision
  that assigned numerical and array semantics to ADR-0006. Error relations name
  registered codes only; `Propagated` marks an operation's own failure passing
  through unchanged, and `MacroSyntax` a grammar rejection. The examples were
  written by hand from the contracts, not generated from the model, so the
  model is checked against them. Deviation: the two models
  (`contract_examples.py`, `grammar.py`) were written before their test suites
  rather than after a red run; non-vacuity rests on the handwritten
  expectations, the seeded mutations each changing an outcome, and the
  in-memory negative controls. Date/Author: 2026-10-11, implementing agent.
- Decision: `EP-M1b` milestone review dispositions. Fixed: completion
  artefacts must resolve inside the repository; the real-roadmap closure test
  runs the full check sequence so a tick that relies on a checker-sourced
  component is judged with that check's result; the scheduled workflow passes
  its run date as `AS_OF` so expiry surfaces while `main` is idle; the two
  public checker functions gained parameter documentation. Declined: annotating
  every `unittest` method's return type, because the existing `tools/tests/`
  suites do not, and the one untyped helper parameter was annotated instead.
  The re-review's request to require at least one decision in every completion
  record was declined: MS-4 requires each cited decision to be accepted, and
  many later tasks (for example 2.1.1) are governed by no register decision, so
  a mandatory citation would invite invented ones. The second re-review noted
  that the freeze check covers only decisions; that is the intended `EP-M1b`
  scope, because the control and exception registers do not exist yet. `EP-M4`
  and `EP-M5` now state that each register joins `freeze.FROZEN_DOCUMENTS` in
  the commit that creates it, and the module docstring says so. Date/Author:
  2026-10-11, implementing agent.
- Decision: the freeze check's result is printed, not recorded in
  `docs/validation-results.json`, so the committed report is identical with and
  without `BASE_REV`. Obligation components default to `PFnn.proof@<task>`
  accepting only `proof` with `evidence_source: record`; the owning task may
  refine a component before any evidence exists. `spec/task-completion.json`
  starts empty; each closing milestone adds its task's record. Date/Author:
  2026-10-11, implementing agent.
- Decision: `EP-M1a` exceeded the per-milestone line tolerance (about 1,600
  net added lines against 1,500, excluding the generated register region and
  the validation report). The overrun is the register master itself
  (`spec/decisions.json`, 522 lines of indented JSON for 15 decisions and 8
  candidate subjects), not added scope; file count (24) is within tolerance.
  Escalated to the sponsor in the milestone pull request rather than
  compressing the master's formatting to fit. Date/Author: 2026-10-11,
  implementing agent.
- Decision: in `EP-M1a`, VO-5's question coverage is checked over live
  records (`proposed` or `accepted`), because acceptances arrive in `EP-M2` to
  `EP-M4`. Coverage by accepted records then follows from closure: tasks 1.1.1
  to 1.1.4 cite the decisions for Q1, Q2, Q4, Q7, and Q8, and MS-4 forbids a
  tick while a cited decision is not accepted. The register's `authorities` map
  is optional in the schema and required by the checker once any record is
  accepted, and it must cite an accepted D01. Options include the alternatives
  the sponsor chose where they differ from the recommendation (D12 option B,
  D13 option B). Date/Author: 2026-10-11, implementing agent.
- Decision: record the sponsor's answers to D01 to D15 as given in the Lody
  session on 2026-10-10 (see `Sponsor decisions`). Approval references use
  `kind: session` with the verbatim answers; the sponsor's merge of the
  recording pull request confirms them. Rationale: the answers were given in
  the session, not on GitHub; C-EP-1 now admits that kind explicitly rather
  than pretending a GitHub artefact exists. Date/Author: 2026-10-10, planning
  agent, following sponsor answers.
- Decision: no CODEOWNERS (D13, rejected by the sponsor). The base-revision
  freeze check remains; the sponsor's review and merge is the human control.
  Revisit if a second developer joins. Date/Author: 2026-10-10, sponsor.
- Decision: `docs/roadmap.md` is canonical (D15, sponsor). `spec/roadmap.json`
  becomes a derived export produced by a Wenmode-based exporter with a drift
  validator, delivered as `EP-M0` in a separate stacked pull request; the
  JSON-to-Markdown generator is removed. Upstream request leynos/mapsplice#144
  tracks a native export; when it lands, the Python exporter is retired.
  Date/Author: 2026-10-10, sponsor.
- Decision: ADRs live in `docs/adrs/` as `adr-nnnn-title-slug.md` (four-digit
  index) and RFCs in `docs/rfcs/` as `rfc-nnnn-title-slug.md` (D07, sponsor).
  This deliberately diverges from the current df12 central style guide; if it
  works well, the sponsor will update the central guide in
  `agent-helper-scripts`. The existing ADR 001 moves to
  `docs/adrs/adr-0001-repository-bootstrap.md` with every link updated in the
  same commit. Date/Author: 2026-10-10, sponsor.
- Decision: the sponsor delegated threshold selection (D12) to the agent, on
  condition that thresholds rest on recorded local measurements extrapolated to
  the pinned runner class. The calibration method, transcripts, and
  extrapolation factors are recorded in `docs/acceptance-calibration.md`; the
  registered values cite them. Date/Author: 2026-10-10, sponsor.
- Decision: implement validators and the evidence gate in Python inside
  `tools/docs_validation/`. Rationale: the design-contract checker, its JSON
  Schema validation, its Hypothesis tests, and its CI workflow live there. Rust
  contract tests over repository files exist (`tests/markdown_wiring.rs`), so
  Rust was credible, but JSON Schema validation would stay in Python, splitting
  the gate before task 1.2.1 pins the toolchain. The gate rule table is a
  language-neutral fixture that task 1.2.4 replays from Rust (D15).
  Date/Author: 2026-10-10, planning agent.
- Decision: no Verus or Kani proofs in this step, a named, justified
  deviation from the general Verus requirement in `AGENTS.md`. Rationale: no
  Rust executable body is introduced; the admission rule ranges over a finite
  abstract domain that tests enumerate exhaustively. Verus and Kani run in
  `EP-M4` only as calibration workloads, not as evidence. Each contract record
  carries a proof sketch. Date/Author: 2026-10-10, planning agent.
- Decision: evidence is tracked per obligation component; closure checks the
  latest record per component and binding; a counterexample at the current
  source revision always blocks. Date/Author: 2026-10-10.
- Decision: admission levels are `proof`, `bounded`, `tested`, `restricted`,
  and `rejected`; `restricted` never satisfies a component. Date/Author:
  2026-10-10.
- Decision: one decision per ADR, ADR-0002 to ADR-0009. Date/Author:
  2026-10-10.
- Decision: the proof-evidence schema gains `schema_version` (value 2) rather
  than changing the pack-wide `revision` (`0.2`). Date/Author: 2026-10-10.
- Decision: exceptions live in `spec/exceptions.json`, referenced by
  identifier. Date/Author: 2026-10-10.
- Decision: keep `scripts/check_evidence.py` with documented exit codes.
  Date/Author: 2026-10-10.
- Decision: runnable helper scripts go in `scripts/` under
  `docs/scripting-standards.md`, with pytest suites in `scripts/tests/`;
  checker modules stay in `tools/docs_validation/` under `unittest`. The
  roadmap exporter is `scripts/export_roadmap.py`;
  `scripts/generate_decisions.py` and `scripts/check_evidence.py` follow the
  same rule. Existing `tools/generate_*.py` generators are not moved in this
  step. Rationale: the sponsor named `scripts/` as the expected home for helper
  scripts (2026-10-11), replacing the planning agent's earlier choice to follow
  `tools/` conventions. Date/Author: 2026-10-11, sponsor.
- Decision: milestones land sequentially on stacked branches. Date/Author:
  2026-10-10.
- Decision: the kernel-contract `evidence.status` vocabulary is unchanged;
  the component document records its mapping. Date/Author: 2026-10-10.

## Design review record

The first draft was reviewed through six lenses; the verdict was "revise".
Blocking findings and dispositions: the PF14 deadlock (obligation components);
MS-1 contradicting L5 (validity predicate, `bounds`, `bounded` level); `status`
and `outcome` overlap (`evidence_kind`); self-reported trust items and verdicts
(`trust_audit`, `verdict_source`, C-EP-10); a digest freeze defeated by one
edit (base-revision check and amendment chain; the CODEOWNERS part was later
rejected by the sponsor, D13); unregistrable AC-04, unbound environment,
underspecified statistics, unfrozen controls (`EP-M4`); expiry contradicting
C-EP-9 (HEAD commit date); file tolerance tripping by design (per-milestone
tolerances); VO-5 false on the plan's own data (`questions` lists,
`decided_option`); a wrong Bool-cast example and unencodable F64 specials
(corrected example, tagged scalars).

Improvements adopted: a single `roadmap_status.py` owner of closure; drift
checking for every generator and export; ADRs in the checker's document list;
computed roadmap status strings; contracts deriving acceptance from decisions;
vocabulary entries citing contract identifiers; proof sketches; substantive
admission properties and an upstream scenario corpus; a `syn`-aware grammar
corpus; two-way bet-to-task links; a separate `package_policy.py`; a component
document; per-module owners. Not adopted: a full Rust gate now; deferring all
executable grammar checks to phase 2.

## Outcomes & retrospective

Outcome against `Purpose / big picture`, item by item:

1. `docs/decision-register.md` is generated from `spec/decisions.json` and
   lists D01 to D15 as accepted, each with its chosen option, date, quoted
   session answer, and ADR, plus the eight candidate ADR subjects with their
   dispositions. Reinserting a retired sentence, writing "Q4 remains open", or
   deleting a ToR §9 anchor fails `make design-check` and names the decision.
2. `spec/semantic-contracts.json` holds `SC-01` to `SC-10` with
   preconditions, success and error relations, empty rules, 51 executable
   examples, a 28-entry grammar corpus, seeded mutations that each change an
   outcome, and proof sketches.
3. `spec/acceptance-controls.json` registers `AC-01` to `AC-07`, four
   calibrated from recorded measurements extrapolated to the hosted runner
   class and three labelled not calibrated; a threshold changed together with
   its digest fails the freeze check without an amendment.
4. `scripts/check_evidence.py` rejects timeouts, unsatisfied witnesses,
   misfiring controls, uncovered or unaudited trust, stale bindings, focused
   runs, self-reported verifier verdicts, and bad exceptions with specific
   reason codes, and admits complete records at the level they earn.
5. Tasks 1.1.1 to 1.1.4 are ticked in `docs/roadmap.md`, and the checker
   confirms each tick is backed by prerequisites, a completion record, accepted
   decisions, and satisfied obligation components.

Acceptance criteria (`Validation and acceptance`): 1 to 6 are met; criterion 4
is demonstrated by `tools/tests/test_freeze.py` (control and decision freezes,
including a temporary Git repository) and by the hosted `Design contracts`
runs; criterion 6 by `cargo publish --dry-run` refusing to publish.

Deviations and lessons:

- Tolerances. `EP-M1a`, `EP-M3`, `EP-M4`, and `EP-M5` exceeded the
  per-milestone line or file tolerance, mostly through indented JSON data and
  required test suites; each overrun is in the decision log and its pull
  request. The 80-file estimate held only per milestone; the whole step changed
  well over 100 files across eight pull requests.
- Red-first order slipped once (`EP-M3` models before tests); its
  non-vacuity rests on handwritten expectations and seeded mutations.
- Calibration found that Kani cannot discharge symbolic 64-bit multiplication
  on the shared host within 900 s; task 1.2.4 should plan Verus for arithmetic
  and Kani for structure.
- Hosted CI exposed two environment assumptions the local gates could not:
  mdtablefix 0.6.0's renumbering of a wrapped "2026." line, and the CI user name
  `runner`. A stacked synchronize run also reported `main` as its base branch,
  which led to choosing the freeze base by commit.
- Remaining: local CodeRabbit CLI reviews of `EP-M2` to `EP-M6`, hosted
  reviews, and the sponsor's review and merge of #9 to #18 in stack order.

## Context and orientation

Combobulate is a proposed Rust array-programming library. The repository holds
a development scaffold (`src/lib.rs` exports only a disposable `greet()` stub)
and a revision 0.2 design pack. Nothing is implemented.

The five governing documents (ToR C3; `docs/context.md` §2) are
`docs/terms-of-reference.md` (goals, success criteria S1 to S11, constraints C1
to C9, open questions Q1 to Q9 in §9, candidate ADR subjects in §10),
`docs/context.md` (vocabulary; §6 lists superseded suggestions),
`docs/technical-design.md` (requirements R1 to R11 and scope classes in §2,
contracts in §§4-7, costs in §12, V1 to V20 in §14, candidate decisions and
GAP1 to GAP9 in §15, proof-first policy in §17, costing in §18),
`docs/language-reference.md` (the catalogue, partly generated from
`spec/vocabulary.json`), and `docs/roadmap.md` (the GIST roadmap, canonical from
`EP-M0` onward).

Companion artefacts: `docs/testable-bets.md` (generated from `spec/bets.json`),
`spec/proof-obligations.json` (PF01 to PF14), `spec/traceability.json`,
`spec/examples.json` (EX01 to EX20), `spec/proof-evidence.schema.json` and its
example, `spec/kernel-contract.schema.json` (native kernel declarations), and
`spec/cost-cases.json`.

The checker is `tools/check_docs.py`. It runs the checks in
`tools/docs_validation/` and requires `docs/validation-results.json` to equal
the freshly computed report; after a deliberate change, run
`check_docs.py --write` and commit the report. `make design-check` runs the
checker and `python3 -m unittest discover -s tools/tests`;
`.github/workflows/design.yml` runs it on every pull request. Markdown checks
cover the files listed in `DESIGN_DOCUMENTS` in
`tools/docs_validation/context.py`.

ADR format (after `EP-M1a`): `docs/adrs/adr-nnnn-title-slug.md`, title
`# Architectural decision record (ADR) nnnn: <title>`, sections `Status`,
`Date`, `Context and problem statement`, then conditional sections, per
`docs/documentation-style-guide.md`.

## Conformance basis

- Terms of reference: `docs/terms-of-reference.md`, revision 0.2 of 6 October
  2026, tracing G1, G2, G6, G7, G8; S7, S8, S10; C2, C3, C5, C6, C7, C9; Q1,
  Q2, Q4, Q7, Q8.
- Technical design: `docs/technical-design.md`, revision 0.2, 6 October 2026.
  Traced items: R7, R8, R9, R10; §2 scope classes; §§4-7; §12; §14 V13, V14,
  V20; §15 candidate decisions, GAP2, GAP5, GAP9; §16; §17.1, §17.2, §17.7,
  §17.8; §18.2, §18.5.
- Roadmap: `docs/roadmap.md` revision 0.2, step 1.1, tasks 1.1.1 to 1.1.4.
- Bets: B01, B02, B03, B08. Proof obligations: PF14 (structural component).
- ADRs: ADR 001 (accepted, scaffold only; relocated in `EP-M1a`).
- Sponsor decisions: D01 to D15 (2026-10-10, Lody session
  `99861d46-f6f5-48d6-acfb-658bee9364bf`).
- Governing standards: `AGENTS.md`, `docs/documentation-style-guide.md` (as
  amended by D07), `docs/developers-guide.md`, and D-CONTRACT in
  `docs/references.md` (draft status retained).

Trace chains:

```plaintext
ToR Q1, Q8 -> TD GAP5, GAP9 -> D01, D02, D13 -> EP-M2 -> ADR-0002 -> tools/tests/test_decision_register.py
ToR Q4 -> TD §2 scope classes -> D03 -> EP-M2 -> ADR-0003 -> register anchors in five documents
ToR Q7 -> TD GAP5 -> D04, D05 -> EP-M2 -> ADR-0004 -> tools/tests/test_package_policy.py
ToR C5 -> TD §15 row 10, §17.8 -> D06 -> EP-M2 -> ADR-0005
TD §15 candidate ADRs -> D07 -> EP-M1a, EP-M2 -> docs/decision-register.md disposition table; docs/adrs/
TD §§4-7, §17.3, §17.5 -> R2 -> D08-D10, D14 -> SC-* -> EP-M3 -> ADR-0006, ADR-0007 -> tools/tests/test_semantic_contracts.py
ToR Q2, S7 -> TD §12, §14 V13, §17.8, §18.5 -> D11, D12 -> AC-* -> EP-M4 -> ADR-0008 -> tools/tests/test_preregistration.py
TD §17.1-17.2, V14, V20 -> R8 -> PF14.structural@1.1.4 -> EP-M5 -> ADR-0009 -> tools/tests/test_evidence_gate.py
D15 -> EP-M0 -> docs/roadmap.md canonical -> scripts/tests/test_export_roadmap.py
Roadmap 1.1.1-1.1.4 -> EP-M6 -> ticked in docs/roadmap.md -> tools/tests/test_roadmap_status.py
```

Gaps addressed: GAP2 (thresholds recorded, not met), GAP5 (scope, licence,
authority ratified), GAP9 (exception authority assigned). GAP1, GAP3, GAP4,
GAP6, GAP7, and GAP8 remain open.

## Sponsor decisions

The sponsor answered every decision in the Lody session on 2026-10-10. These
answers are binding inputs to this plan; `EP-M2` onward records them in
`spec/decisions.json` with `kind: session` approval references and the verbatim
text. Recommendations were the planning agent's; the outcome column is the
sponsor's.

- D01 (Q1, Q8 authority). Outcome: sponsor and technical owner, both
  `leynos`. Consistent with ToR §9's "Sponsor and technical owner" wording, so
  no ToR authority amendment is needed.
- D02 (exception policy). Outcome: accepted as recommended. An exception is
  valid from its approval date until its `invalid_from` date, at most 90 days
  and never past the next release-gate task (4.3.3 or 6.3.4); renewal is a new
  approval; an exception names a narrowed claim and never satisfies a
  proof-required component.
- D03 (Q4 scope). Outcome: accepted. The Core, Integration, and Deferred split
  in technical design §2 stands unchanged.
- D04 (Q7 licence). Outcome: accepted. ISC is ratified.
- D05 (Q7 publication). Outcome: accepted, with the instruction that the
  policy be clearly documented in `docs/developers-guide.md`. `Cargo.toml` gains
  `publish = false` until the Core acceptance dossier (task 4.3.3) passes and
  `leynos` approves release.
- D06 (pre-1.0 API policy). Outcome: accepted as recommended (no shims for
  pre-1.0 or unreleased APIs; Cargo's 0.y.z rule; the public proof interface
  versioned with the crate, with strengthened preconditions and weakened
  postconditions treated as breaking; MSRV stays with ToR Q3 and task 1.2.1).
- D07 (candidate ADR dispositions). Outcome: accepted as recommended, plus a
  sponsor-directed change to documentation conventions: ADRs in `docs/adrs/`
  named `adr-nnnn-title-slug.md`, and RFCs in `docs/rfcs/` named
  `rfc-nnnn-title-slug.md`, with a four-digit index. Dispositions: numerical
  and array semantics to ADR-0006; macro staging and stable-Rust application to
  ADR-0007; initial release scope to ADR-0003; public proof compatibility to
  ADR-0005 and ADR-0009; shared semantic kernel and backend and cell separation
  deferred to task 1.2.1; resource certification deferred to step 2.4; backend
  input and output control scope deferred to task 1.2.6.
- D08 (`comb!` operator precedence). Outcome: accepted as recommended (Rust
  precedence via `syn`; `|>` split first, lowest, left-associative; reject
  unparenthesized comparison mixed with `&`, `|`, or `^`; translate `syn`'s
  chained-comparison error).
- D09 (F64 special values). Outcome: accepted as recommended (IEEE 754-2019
  `minimum` and `maximum`; null before NaN; empty F64 `sum` is positive zero,
  `sum([-0.0])` is negative zero; a `mean` count of exactly 2^53 admitted).
- D10 (typed-cell atomicity). Outcome: accepted. Two rules under two names:
  cell atomicity and atomic output commit.
- D11 (Q2 environments). Outcome: accepted: paired, interleaved runs on a
  pinned `ubuntu-24.04` hosted runner class, instruction counts primary and
  wall time secondary; proof and build ceilings on the same class. The sponsor
  added that local development machines are whatever is available, and that
  hostnames must not appear in source documentation (C-EP-12).
- D12 (Q2 thresholds and statistics). Outcome: delegated to the agent. The
  agent measures realistic workloads on the current development machine,
  extrapolates to the hosted runner class (4 vCPUs, 16 GB, x64), and brings the
  evidence (`EP-M4`).
- D13 (governance enforcement). Outcome: rejected. No `.github/CODEOWNERS`;
  revisit if another developer joins (C-EP-13).
- D14 (`div` on I64 operands). Outcome: accepted as recommended (convert each
  operand to F64 with ties-to-even rounding, then IEEE division).
- D15 (prospective details for later tasks). Outcome: accepted, with the
  instruction that `docs/roadmap.md` is canonical. The details (1.2.1 and 1.2.4
  build the trust-audit scanner and log parsers and replay the gate rule table
  from Rust; 1.2.3 replays the semantic examples as `rstest` cases; 2.3.1
  replays the grammar corpus as `trybuild` fixtures with a completeness check)
  are added to `docs/roadmap.md` directly. A JSON view comes from a Wenmode
  exporter with a drift validator in a separate stacked pull request (`EP-M0`),
  pending leynos/mapsplice#144.

## Verification plan

This step introduces repository-governance logic, not library semantics. The
semantic contracts recorded in `EP-M3` are discharged against Rust code later
by the existing proof obligations (for example PF07 in tasks 2.2.x). This step
checks that those contracts are coherent, complete, and non-vacuous in the
documentation model, and that the governance logic is correct.

### Method selection

Verus and Kani produce no evidence in this step (see `Decision log`); they run
in `EP-M4` only as calibration workloads. Each contract record's `proof_sketch`
states the Verus lemma statements and Kani harness intent that its discharging
task must prove.

The project's Rust test tools apply when the contracts gain Rust
implementations, and this step's artefacts are designed to be replayed by them:
the grammar corpus becomes `trybuild` fixtures in 2.3.1; the semantic examples
become `rstest` cases with `googletest` matchers and `pretty_assertions` diffs
in 1.2.3 and phase 2; `insta` diagnostic snapshots start with the first
rendered errors in 2.3.3; the gate rule table is replayed by Rust tooling in
1.2.4; `proptest` covers shape and cardinality invariants in 2.1.1.
`rstest-bdd` does not apply here because no user-visible Rust behaviour
changes. In this step, Python `unittest` subtests play the role of
parameterized cases, Hypothesis properties the role of property tests, and the
checker's drift comparisons the role of golden snapshots.

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
exactly when `kind` is not bounded. The JSON Schema enforces the same
predicate, and VO-2 checks that the two agree.

Admission (recorded in ADR-0009 as a compact, ordered rule table and
implemented exactly):

- MS-0. If `Valid` fails, the level is `rejected` with `schema-invalid`.
- MS-1 (blocking reasons). Each failed condition contributes one reason code:
  `outcome != verified` gives `outcome-<value>` (except for trust-declarations);
  `witness != all-satisfied` gives `witness-<value>`;
  `controls != all-required-rejected-as-intended` gives `control-<value>`; for
  deductive and bounded kinds, `trust = unaudited` gives `trust-unaudited` and
  `audited-uncovered` gives `trust-uncovered`; `binding != current` gives
  `binding-<value>`; `run_mode = focused` gives `run-focused`; an expired,
  not-yet-valid, or malformed exception gives `exception-<value>`; for
  deductive and bounded kinds, `verdict_source = self-reported` gives
  `verdict-self-reported`; `kind = none` gives `not-run`; a trust-declaration
  without an active exception gives `trust-without-exception`.
- MS-2 (level). With no blocking reason, the base level is `proof` for
  deductive, or bounded with `type-complete` bounds; `bounded` for bounded with
  `partial` bounds; `tested` for test; `restricted` for a trust-declaration. If
  `exception = active`, the level becomes `restricted` with the informational
  reason `exception-active`. Any blocking reason makes the level `rejected`.
- MS-3 (component satisfaction). A component lists the levels it accepts (a
  subset of {proof, bounded, tested}; never `restricted`). It is satisfied when
  the latest record for it at the current binding is admitted at an accepted
  level and no record at the same source revision reports
  `outcome = counterexample`. A component whose `evidence_source` is
  `checker:<check-id>` is satisfied when that check passes in the same run.
- MS-4 (task closure). A task may be ticked in `docs/roadmap.md` only when
  every prerequisite task is ticked, every decision it cites is accepted and
  not superseded, every completion artefact it lists (in
  `spec/task-completion.json`) resolves, and every obligation component linked
  to it is satisfied. A task whose conditions hold but which is not ticked is
  reported without failing, so a tick remains an explicit claim.

Substantive admission properties, checked against both the rule table and the
implementation:

- P1 (degradation monotonicity): replacing any field value with a worse one
  never raises the level (proof > bounded > tested > restricted > rejected).
- P2 (diagnostic soundness and completeness): a level is `rejected` exactly
  when a blocking reason exists, and moving any single contributing field to
  its best value removes exactly that reason.
- P3 (exceptions never substitute): no state with `exception != none`
  satisfies any component.
- P4 (bounded honesty): no state with `bounds = partial` reaches `proof`.
- P5 (date sensitivity): for concrete records, `as_of` affects the result only
  through the exception state.
- P6 (closure soundness): a ticked task implies ticked prerequisites; adding a
  counterexample record at the current revision un-closes every dependent task.

Upstream scenario corpus (derived from the bet register, proof ledger, and
technical design, not from ADR-0009): B01 "suppress a failed harness" maps to
`outcome-skipped` or `verdict-self-reported`; B02 "always-Err executor" to
`witness-some-unsatisfied`; B02 "assumed executor postcondition" to
`trust-uncovered`; B08 "import verification metadata from a different
executable revision" to `binding-stale`; B08 "use focus/skip mode as release
evidence" to `run-focused` or `outcome-skipped`; B08 "label bounded Kani
evidence as unbounded" to level `bounded`, failing a proof-only component; PF14
"swap a compiled body" to `binding-stale`; §17.1 timeout to
`outcome-resource-exhausted`; unsupported feature to `outcome-unsupported`;
failed unwinding assertion to `outcome-counterexample`; empty generator to
`witness-absent`; §17.7 negative control failing on an unrelated parse error to
`control-some-rejected-otherwise`.

### Obligations

- VO-0 (roadmap export fidelity, `EP-M0`). Invariants: exporting the current
  `docs/roadmap.md` reproduces the current `spec/roadmap.json` exactly before
  the generator is removed; export is deterministic and independent of Markdown
  wrapping; unknown or malformed structure fails with a source line; the drift
  validator fails when the committed export differs from a fresh export.
  Method: an exact-equality test on the real roadmap; a Hypothesis round-trip
  property that renders generated roadmap structures with an independent
  test-only renderer (the former generator's layout) and exports them back;
  parameterized malformed-input cases; command-line exit codes. Artefacts:
  `scripts/tests/test_export_roadmap.py` (pytest) and
  `tools/tests/test_roadmap_export_gate.py` (the checker rejects a stale
  export). Non-vacuity: a changed task title, a changed `Requires` reference,
  and a changed checkbox in an in-memory roadmap each make the drift check fail
  and name the item; a heading at the wrong level is rejected rather than
  dropped; the property records generated phase, step, task, and detail counts
  and fails if any class is absent.
- VO-1 (admission correctness, MS-0 to MS-2, P1 to P4). Method: exhaustive
  enumeration of all 345,600 abstract states against an independent interpreter
  of the ADR-0009 rule table in
  `tools/tests/fixtures/evidence_gate_rules.json`; P1 to P4 over the full
  enumeration against both; the scenario corpus against both. Artefacts:
  `tools/tests/test_evidence_gate.py`,
  `tools/docs_validation/evidence_gate.py`. Evidence: red is
  `ModuleNotFoundError`; green is full agreement. Non-vacuity: every level and
  reason occurs, each reason as the sole reason for some state; the valid-state
  count is asserted. Seeded mutations that must fail: `resource-exhausted`
  treated as verified; `trust` ignored; `active` keeping the base level;
  `partial` mapped to `proof`; `some-rejected-otherwise` accepted.
- VO-2 (concrete-to-abstract mapping and schema agreement). Method: for each
  valid abstract state a generated concrete record must be schema-valid and
  abstract back to that state; for each invalid state the record must be
  schema-invalid; a Hypothesis property checks that abstraction depends only on
  documented fields. Artefact: `tools/tests/test_evidence_records.py`.
  Non-vacuity: fails if any kind or outcome class is never generated; a seeded
  mapping fault must fail.
- VO-3 (exception register validity, P5). Method: boundary tests on the
  injected date (day before approval: not-yet-valid; approval day: active; day
  before `invalid_from`: active; `invalid_from`: expired); malformed cases
  (lifetime beyond D02's maximum, approver other than `leynos`, missing
  narrowed claim, missing owner); a Hypothesis property that `as_of` changes
  only the exception state. Artefact: `tools/tests/test_exceptions.py`.
  Non-vacuity: each malformed variant has its own reason; a complete active
  exception yields `restricted`.
- VO-4 (components and closure, MS-3, MS-4, P6). Method: parameterized tests
  over synthetic roadmaps (a chain and a diamond) and the real roadmap.
  Artefact: `tools/tests/test_roadmap_status.py`. Non-vacuity: a tick with an
  open prerequisite fails; a tick citing a proposed or superseded decision
  fails; a tick with an unsatisfied component or unresolvable completion
  artefact fails; a counterexample at the current revision reopens a component;
  a fully satisfied task passes. Before `EP-M5`, a task with a linked component
  cannot be ticked.
- VO-5 (decision register integrity). Invariants: unique identifiers; unique
  subjects among accepted, non-superseded records; every in-scope ToR question
  covered by an accepted record; accepted records carry `decided_option`,
  `accepted_on`, and a structured approval reference whose `author_login` is
  `leynos` and whose `names_decisions` includes the record; proposed records
  carry no approval fields; two-way, acyclic supersession links; each cited ADR
  exists under `docs/adrs/` with an agreeing `Status` line; dates validated
  with the `jsonschema` format checker. Artefact:
  `tools/tests/test_decision_register.py`. Non-vacuity: one in-memory negative
  control per invariant, each with a distinct message; the real register passes.
- VO-6 (five-document consistency). Invariants: each governing document links
  `decision-register.md`; each accepted question's ToR §9 row links its
  register anchor; after whitespace and inline-Markdown normalization, no
  `retired_statements` text of an accepted decision appears; no governing
  document matches `(pending|open|unresolved|remains? proposed)` within 60
  characters of an accepted question's identifier. Artefact:
  `tools/tests/test_decision_register.py`. Non-vacuity: after D03's acceptance,
  reinserting "The classes remain proposed pending ToR Q4." (also rewrapped
  across two lines), writing "Q4 remains open", or deleting the ToR §9 anchor
  each fails.
- VO-7 (base-revision freeze). Invariant: compared with `--base-rev`, the
  check rejects a frozen-field change to a registered control without a new
  amendment whose `replaces` equals the previous digest; an edited or removed
  amendment; an accepted decision deleted or edited other than by supersession;
  an accepted exception altered rather than replaced. Method: in-memory base
  and head documents, plus one integration test against a temporary Git
  repository in the test's temporary directory. Artefact:
  `tools/tests/test_freeze.py`. Non-vacuity: changing a threshold and its
  digest together is rejected; a correct amendment passes.
- VO-8 (semantic contract coherence and examples). Invariants: every contract
  record names existing catalogue identifiers; has preconditions, success
  conditions, success relation, error relation with registered error codes,
  mutation frame, termination, and empty rule; cites at least one evaluated
  example and one seeded mutation; has `discharged_by` (a PF component, or a
  test task where no PF obligation applies, such as 2.3.1 for the grammar) and a
  `proof_sketch`; every catalogue entry's `contract` cites its contract
  identifier. New examples use tagged scalars (`{"f64": "-0.0"}`,
  `{"f64_bits": "0x7ff8000000000000"}`, `{"i64": "9223372036854775807"}`) and
  cover: empty `product`, `any`, `all`, `minimum`, `maximum`, and `mean`;
  `minimum([5]).identity(0)` returning 5 and a wrong-dtype identity failing;
  `idiv(-7, 2) = -3` and `rem(-7, 2) = -1`; I64 to F64 ties-to-even (2^53 + 1
  to 2^53); `div` on large I64 operands per D14; F64 to I64 boundaries (2^63
  fails, -2^63 succeeds, -0.0 gives 0, NaN and non-integral fail); Bool to I64
  giving 0 or 1 and numeric to Bool rejected; Kleene `and`, `or`, `xor`;
  `any([true, null])` null under the default policy; binary `min` and `max`
  with NaN, signed zeros, and null; empty F64 `sum` positive zero and
  `sum([-0.0])` negative zero; `skip_nulls` then empty; `Batch<DVec3>` of shape
  `[2,3]` with cardinality 6 rejecting `.axis(2)`; an injected failure leaving
  the destination unchanged. Artefact:
  `tools/tests/test_semantic_contracts.py`. Non-vacuity: each seeded mutation
  must change at least one outcome (left association for `reduce`; floor
  division for `idiv`; error instead of identity for empty `sum`; identity as a
  seed; implicit promotion in `add`; NaN-ignoring `min`; two-valued null logic;
  exact-quotient rounding for `div`; partial output on failure).
- VO-9 (grammar corpus adequacy). Invariant: `spec/macro-grammar.json` agrees
  with the ADR-0007 precedence table, transcribed from the Rust Reference with
  a citation. Corpus coverage: `|>` lowest and left-associative, and inside
  parentheses; `a|>b` and `a | > b`; unary `-` and `!`; comparison chains
  rejected; unparenthesized comparison mixed with `&`, `|`, or `^` rejected;
  `&&` and `||` between arrays rejected; closures inside `host { ... }`
  accepted and outside rejected; `rows(&centre)` as host construction; `as`,
  `..`, `=`, `+=` rejected; token-level entries tagged `phase2-only`. Method: a
  precedence-climbing recognizer under 200 lines in
  `tools/docs_validation/grammar.py`. Artefact:
  `tools/tests/test_macro_grammar.py`. Non-vacuity: swapping `*` and `+`,
  right-associative `|>`, accepting `&&`, or allowing comparison mixing each
  fail an entry; a mechanical check requires an entry per precedence level and
  rejection rule. Residual gap: the recognizer models the corpus, not the
  macro; 2.3.1 replays every entry through `trybuild`, after which the
  recognizer is deleted.
- VO-10 (no superseded-name shims). Invariant: no name in the
  `excluded_names` register (`a!`, `cells`, `cells2`, `id` aliasing `identity`,
  `.pipe` accepting descriptors, array `&&` and `||`) appears as a catalogue
  name or alias. Artefact: `tools/tests/test_semantic_contracts.py`.
  Non-vacuity: adding `cells` in memory fails.
- VO-11 (pre-registration completeness and amendment chain). Invariants: a
  registered control has every frozen field listed in `EP-M4`, including its
  calibration reference; its digest is SHA-256 of canonical JSON over those
  fields; amendments form a chain (`replaces` equals the previous digest; the
  current digest equals the last `new_digest`); a measurement record cites a
  current or historical digest. Method: a Hypothesis property mutating each
  frozen field in turn; parameterized completeness controls. Artefact:
  `tools/tests/test_preregistration.py`. Non-vacuity: fails unless every frozen
  field was exercised; a correct amendment passes.
- VO-12 (measurement outcomes cannot be relabelled). Invariant:
  `resource-exhausted`, `budget-exceeded`, `inconclusive`, and a missing record
  from a killed job map to fail or inconclusive, never pass; retries are all
  recorded and all count; calibration records can never satisfy an acceptance
  control. Method: exhaustive enumeration of the outcome mapping. Artefact:
  `tools/tests/test_preregistration.py`. Non-vacuity: a seeded mapping treating
  `resource-exhausted` as pass, or admitting a calibration record, must fail.
- VO-13 (package policy). Invariant: `Cargo.toml` `license` is `ISC` and
  `publish` is `false`, per accepted D04 and D05. Artefact:
  `tools/tests/test_package_policy.py`. Non-vacuity: an in-memory manifest
  without `publish = false` fails.
- VO-14 (drift and idempotence for every generator and export). Invariant:
  every generator and the roadmap exporter are covered by the checker; rerun on
  a clean tree, they yield no diff. Artefact:
  `tools/tests/test_roadmap_status.py` and the idempotence step. Non-vacuity: a
  hand edit to `docs/decision-register.md` or `spec/roadmap.json` fails.
- VO-15 (bet and task links are two-way). Artefact:
  `tools/tests/test_metadata_ids.py`. Non-vacuity: removing 1.1.4 from B08 in
  memory fails.
- VO-16 (no host identity leaks). Invariant: committed calibration and
  measurement records contain no hostname, username, or absolute home path.
  Method: a check over `docs/acceptance-calibration.md` and measurement records
  using the hardware-class schema (no free-form host fields) plus a pattern
  scan for `/home/`, `/Users/`, and the local hostname supplied at test time
  only. Artefact: `tools/tests/test_preregistration.py`. Non-vacuity: an
  in-memory record containing a home path fails.

### Axioms

Trusted, not verified here:

- A1. The `jsonschema` package implements Draft 2020-12 and its format
  checker correctly.
- A2. SHA-256 is a collision-resistant identity check.
- A3. Git history and the merge base supplied by CI are authentic.
- A4. Session answers are attributed to the sponsor by the Lody session, and
  pull request reviews and merges by GitHub. Without CODEOWNERS (D13), the
  sponsor's merge is the human control; ADR-0002 states this.
- A5. Verifier log parsers and the trust-audit scanner (tasks 1.2.1 and
  1.2.4) correctly read verifier output. C-EP-10 means this axiom is never
  exercised before those parsers exist and are tested. The scanner's item
  vocabulary is fixed in ADR-0009: for Verus, `assume`, `admit`,
  `external_body`, `external`, `external_fn_specification` or
  `assume_specification`, and `external_type_specification`; for Kani,
  `kani::assume`, `stub`, `stub_verified`, and `should_panic`.
- A6. Wenmode parses CommonMark and GitHub-flavoured task lists as
  documented. VO-0's exact-equality test exercises it on the real roadmap.

## Plan of work

Milestones run in order on stacked branches. `EP-M0` is sponsor-directed and
proceeds now. `EP-M1a` onward awaits approval of this revision; all decisions
they need have been answered. Each milestone follows Red, Green, Refactor:
draft as `proposed` (Stage A); add rule tables, fixtures, and tests and observe
the expected failure (Stage B); implement until the focused tests pass (Stage
C); tidy, run the generators and exporter and `check_docs.py --write`, review
the report diff, and have `scrutineer` run the full gates (Stage D).

### EP-M0. Make `docs/roadmap.md` canonical (separate stacked pull request)

- Add `wenmode==0.15.2`, `cyclopts==5.2.0`, and `pytest==9.1.1` to
  `tools/requirements.txt`, and run `pytest -q scripts/tests` from
  `make design-check`.
- Add `scripts/export_roadmap.py` (a `uv` script with a PEP 723 block and a
  Cyclopts command line) whose parser parses the region between
  `<!-- roadmap:start -->` and `<!-- roadmap:end -->` with Wenmode's
  GitHub-flavoured preset into the existing structure (phases with `number`,
  `title`, `idea`, `goals`, `context`, `gate`; steps with `number`, `title`,
  `question`, `sections`; tasks with `id`, `title`, `requires`, `sections`,
  `success`, `details`, `proof_first`, `bets`), plus each task's checkbox
  state. Top-level `revision` comes from the preamble's "Revision" line;
  `status` is computed from checkbox states. Unknown structure raises an error
  naming the source line.
- The script writes `spec/roadmap.json` from the Markdown, or with `--check`
  (or `INPUT_CHECK=true`) exits 1 and prints a unified diff when the committed
  export has drifted. The checker loads it by path through
  `ValidationContext.load_script`.
- In `tools/docs_validation/ledger.py`, replace the JSON-to-Markdown drift
  comparison for the roadmap with the export drift comparison. Remove
  `tools/generate_roadmap.py`. Move its rendering layout into
  `scripts/tests/roadmap_render.py` as the independent test-only renderer used
  by VO-0. The checker's Python-source check also parses `scripts/`.
- Update `docs/validation.md` (reproduction steps),
  `docs/developers-guide.md` (roadmap workflow: edit `docs/roadmap.md`,
  preferably with `mapsplice` for structural edits, then run the exporter),
  `docs/repository-layout.md`, and the roadmap preamble sentence saying the
  roadmap is generated.
- Tests: VO-0. Regenerate `docs/validation-results.json`.

### EP-M1a. ADR relocation, decision register, generator, and anchors

- Amend `docs/documentation-style-guide.md`: ADRs in `docs/adrs/` named
  `adr-nnnn-title-slug.md`; RFCs in `docs/rfcs/` named
  `rfc-nnnn-title-slug.md`; four-digit indices; note the deliberate divergence
  from the central df12 guide. Move ADR 001 to
  `docs/adrs/adr-0001-repository-bootstrap.md` and update every link,
  `DESIGN_DOCUMENTS`, `docs/contents.md`, and `docs/repository-layout.md` in
  the same commit.
- Add `spec/decision-register.schema.json` and `spec/decisions.json` with D01
  to D15 (still `proposed` in this milestone; acceptance is recorded in `EP-M2`
  onward). Each decision carries `subject`, `questions`, `authority_roles`,
  `options`, `recommendation`, `decided_option`, `lifecycle`, `supersedes`,
  `superseded_by`, `accepted_by`, `accepted_on`, `approval_reference`, `adr`,
  and `retired_statements`. Add the eight candidate ADR subjects with
  dispositions.
- Add `scripts/generate_decisions.py`, rendering `docs/decision-register.md`
  between `<!-- decisions:start -->` and `<!-- decisions:end -->` with one
  anchored heading per decision.
- Turn the generator list in `ledger.check_generated_documents` into a table
  including the decisions generator. Add `tools/docs_validation/decisions.py`
  (VO-5, VO-6) and register it. Add the register and all ADRs to
  `DESIGN_DOCUMENTS`.
- Link the register from the five governing documents and `docs/contents.md`.
  Update `docs/developers-guide.md` with the register workflow and the `uv`
  invocation for `make design-check`.

### EP-M1b. Roadmap status, obligation components, and freeze check

- Add `spec/task-completion.json` (task identifier to completion artefact
  references) and `tools/docs_validation/roadmap_status.py` as the single owner
  of MS-3 and MS-4, reading tick state from the roadmap export. Replace the
  blanket ban in `ledger.py` with a call to it. Compute the export's `status`
  string and the checker's roadmap detail from tick state.
- In `spec/proof-obligations.json`, add `components` to every obligation (for
  PF14, `PF14.structural@1.1.4` accepts `tested`, evidence source
  `checker:evidence-gate`). Relax `check_obligations` so components may cite
  evidence while obligation-level status stays `planned-not-run` until every
  component is satisfied. Until `EP-M5`, a task with a component cannot be
  ticked.
- Add `tools/docs_validation/freeze.py` (VO-7) and `--base-rev` to
  `check_docs.py`. In the `Makefile`, add
  `AS_OF ?= $(shell git log -1 --format=%cs)` and an optional `BASE_REV` to
  `design-check`. In `.github/workflows/design.yml`, set `fetch-depth: 0`, pass
  the merge base, and add a weekly `schedule:` trigger.

### EP-M2. Task 1.1.1: authority, scope, licence, and API policy

- Write `docs/adrs/adr-0002-governance-authority.md` (D01, D02, D13, axiom
  A4), `docs/adrs/adr-0003-initial-release-scope.md` (D03),
  `docs/adrs/adr-0004-licence-and-publication.md` (D04, D05), and
  `docs/adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md` (D06), each
  `Accepted` on 2026-10-10 citing the session answer.
- Record D01 to D07 and D13 as accepted (D13 with `decided_option`
  "no CODEOWNERS") with `kind: session` approval references and verbatim
  answers. Record the D07 dispositions.
- Reconcile the five documents: ToR §9 rows Q1, Q4, Q7, Q8 link their
  register anchors; ToR §10 and technical design §15 point at the disposition
  table; technical design §2, GAP5, and GAP9 drop open-status language;
  `docs/context.md` §7 and the roadmap preamble are updated;
  `docs/language-reference.md` prose outside the generated region is updated.
  Record each replaced sentence in `retired_statements`.
- Add `publish = false` to `Cargo.toml`; add
  `tools/docs_validation/package_policy.py` (VO-13). Add a "Licence and
  publication" section to `docs/developers-guide.md` stating plainly that the
  crate is ISC-licensed, that `publish = false` blocks crates.io publication
  until the Core acceptance dossier (task 4.3.3) passes and `leynos` approves
  release, and how that approval is recorded. Update `README.md` "Licence" and
  `docs/users-guide.md` (project status, licence, publication, and pre-1.0
  stability policy).
- Tick task 1.1.1 in `docs/roadmap.md` with completion references D01 to D07,
  D13, and ADR-0002 to ADR-0005.

### EP-M3. Task 1.1.2: semantic and macro contract records

- Write `docs/adrs/adr-0006-numeric-validity-and-reduction-contracts.md`
  (dtype set and conversions including V031 and D14; null and Kleene logic;
  association of `reduce`, `fold_left`, `scan`, `scan_left`; `.reassociate()`
  failure equivalence; empty identities and `.identity(value)`; `mean` and
  `variance`; D09; D10) and
  `docs/adrs/adr-0007-comb-macro-grammar-and-staging.md` (an EBNF for `comb!`,
  `verb!`, `host { ... }`, `arr!`, `array!`; the D08 precedence table with a
  Rust Reference citation; the token-level `|>` split; staging phases and what
  each may evaluate; the optional static-descriptor rule). Both are `Accepted`
  on 2026-10-10 citing the D08 to D10 and D14 answers; the contract details
  they contain are new drafting, so the sponsor reviews them in the milestone
  pull request before merge, and any requested change is made before merge.
- Record in `docs/developers-guide.md` why `spec/kernel-contract.schema.json`
  does not fit primitive contracts and how the two relate (shared `outcomes`
  field names; kernel contracts cite contract identifiers).
- Add `spec/semantic-contract.schema.json` and `spec/semantic-contracts.json`
  (SC-01 onward), each record with `decision`, `catalogue_ids`, `preconditions`,
  `success_relation`, `success_conditions`, `error_relation`, `mutation_frame`,
  `termination`, `empty_rule`, `examples`, `seeded_mutations`,
  `discharged_by`, and `proof_sketch`.
- Make affected `spec/vocabulary.json` contracts cite their identifiers;
  regenerate the reference; add the `excluded_names` register.
- Add tagged-scalar examples to `spec/examples.json`; extend the
  documentation model in a new `tools/docs_validation/contract_examples.py`. Add
  `spec/macro-grammar.json` and `tools/docs_validation/grammar.py`.
- Tests: VO-8, VO-9, VO-10. Update technical design §§6-7 and §17.3 to cite
  the ADRs and record the proof-influenced choices; reconcile accepted rows of
  `docs/context.md` §6. Tick task 1.1.2.

### EP-M4. Task 1.1.3: calibrated, pre-registered acceptance controls

- Write `docs/adrs/adr-0008-acceptance-control-pre-registration.md`
  (register before measuring; amendments are an authorized chain; a
  post-measurement change is a new control identifier with the original result
  retained; calibration runs never count as acceptance evidence; shared
  development hosts are not acceptance environments; hardware is recorded by
  class only).
- Add `spec/acceptance-controls.schema.json`, `spec/acceptance-controls.json`,
  `spec/measurement-record.schema.json` (binding `control_id` and
  `control_digest`; a `purpose` of `calibration` or `acceptance`), and
  `tools/docs_validation/preregistration.py` (VO-11, VO-12, VO-16). Register
  `spec/acceptance-controls.json` in `freeze.FROZEN_DOCUMENTS` with its
  amendment-chain rule, so VO-7 covers controls from the commit that creates
  them.

Calibration (D12), recorded in `docs/acceptance-calibration.md` and machine
records under `spec/calibration/`:

1. Toolchains. Use the installed Kani (record its version). Install a pinned
   Verus release in a user-level tool directory outside the repository and
   `/tmp`, recording the release identifier and its required Rust toolchain. If
   no Verus release supports a usable toolchain, apply the calibration
   tolerance.
2. Probe workloads, in a standalone probe crate under
   `tools/calibration/cardinality-probe/` (its own `Cargo.toml`, not a
   workspace member, `target/` ignored), clearly labelled as a calibration
   probe and not the shipped kernel (task 1.2.4 owns that): a checked
   cardinality function (zero extent first, then checked multiplication), a
   Verus proof of its specification, and Kani harnesses over symbolic extents
   with `cover` statements. Measure Verus wall time, `rlimit` consumption, and
   peak process-tree memory (cgroup v2 `memory.peak` via
   `systemd-run --user --scope`), and per-harness Kani wall time and memory.
3. Build workloads: cold and incremental builds of the current package
   (native-only profile) and of a Polars-enabled probe (the probe crate with an
   optional `polars` dependency at the version task 1.2.1 is expected to pin,
   recorded as provisional), each with `-j4` to match the runner's vCPUs, five
   runs, median reported. Compile-admission queue time (the `[build-limits]`
   waiting lines) is recorded separately and excluded.
4. CI workload: the last 20 `Design contracts` and `CI` workflow runs on
   `main` and pull requests via `gh run list` and `gh run view`, critical-path
   wall time excluding queue time.
5. Runtime workloads (AC-05) cannot be calibrated yet because no executor
   exists; their thresholds are set from the design target with the protocol
   frozen, and labelled as not calibrated.

Extrapolation to the hosted runner class (4 vCPUs, 16 GB, x64): for
single-threaded solver work, a factor derived from a single-thread CPU
benchmark run locally and on the runner class's published processor family,
stated with its source; for parallel builds, the measured `-j4` local time
times that factor. Thresholds are the extrapolated median times a safety margin
of 2, rounded up to a stated granularity; memory ceilings are the measured peak
times 1.5, capped below 16 GB minus a stated system reserve. Every number in
the register cites its calibration record. Calibration records carry hardware
class only (C-EP-12).

Controls to register, with the protocol from the review retained:

- AC-01 (task 1.2.4, B01): Verus verification of the cardinality kernel;
  primary budget `rlimit` per function, secondary wall time and process-tree
  memory; above the threshold is `budget-exceeded`, above the hard timeout is
  `resource-exhausted`, both failures; no retries.
- AC-02 (tasks 1.2.4, 1.2.5): each Kani harness; per-harness and per-job
  budgets; registered solver; unwinding assertions on; every declared
  `kani::cover!` satisfied; a per-harness wrapper writes a record even when
  killed.
- AC-03 (step 2.4, B03): compile-time cost of static admission; geometric
  mean of paired, interleaved incremental-rebuild ratios; at least 10 pairs and
  3 warm-up runs per arm; percentile bootstrap with at least 10,000 resamples
  on the log scale; a one-sided 95% upper bound at most 1.25 passes; a
  straddling interval is inconclusive with one pre-declared doubling.
- AC-04 (task 1.2.1, S7): cold and incremental builds of the native-only,
  proof-capable, and Polars-enabled profiles, with calibrated ceilings.
- AC-05 (S1, S5): runtime ratios against ordinary Rust controls, two sizes
  per workload, at least 30 pairs, upper bound at most 1.5, all six members
  must pass, each reported; labelled not calibrated.
- AC-06 (V9, V13): tracked peak never exceeds the admitted bound; a counting
  `GlobalAlloc` reports untracked allocation.
- AC-07: pull request CI critical-path wall time, p90 over the last 20 runs,
  calibrated; `timeout-minutes` equals the budget.

Frozen fields per control: workload and control source paths and digests,
sizes, seeds, timed region; metric, unit, estimand, statistic, decision rule
including the inconclusive and extension policy; warm-up, interleaving, sample
counts, outlier policy; environment (image family `ubuntu-24.04`, runner class,
toolchains with codegen backend and linker); cache policy; proof scope
parameters; measurement tool and version; analysis script digest; calibration
reference; `registered_on` and authority. Observed runner metadata (`ImageOS`,
`ImageVersion`) is recorded per measurement, not frozen.

Register the controls under the D12 delegation, store digests, tick task 1.1.3,
and update ToR §7 and §9 Q2, technical design §12, §14 V13, §17.8, and GAP2,
and the bet register's measurement sentences.

### EP-M5. Task 1.1.4: proof-first policy, public proof contract, and gate

- Write `docs/adrs/adr-0009-proof-first-policy-and-evidence-gate.md` (the
  abstract model and validity predicate; the compact ordered rule table;
  properties P1 to P6; the trust-audit vocabulary; the public proof contract
  per technical design §17.8 and D06; the `check_evidence.py` exit codes). It
  is drafted under the accepted D02 and D06 policies and reviewed by the
  sponsor in the milestone pull request before merge.
- Red: write `tools/tests/fixtures/evidence_gate_rules.json`, the scenario
  corpus, and the tests first.
- Revise `spec/proof-evidence.schema.json` to `schema_version` 2: `id` and
  `component`; `evidence_kind` and `outcome` with `outcome_detail`; structured
  `bounds`; `binding` with executable and specification digests, source
  revision, target, features, semantic policy, backend profile, and
  `implementation_relation`; `method` with tool, version, solver, solver
  version, command, and `run_mode`; `declared_assumptions`; `trust_audit`;
  `success_witnesses` (minimum one; every Kani `cover` listed);
  `negative_controls` (minimum one; structured expected and observed failures);
  `verdict_source`; `exception` (identifier into `spec/exceptions.json`); and
  `result_artefacts` (the existing result-list field renamed to the en-GB
  spelling the gate enforces).
- Add `spec/exceptions.json` with its schema, update the example and
  `check_proof_evidence_envelope`, and single-source reason codes in
  `spec/evidence-reason-codes.json`, in one change. Register
  `spec/exceptions.json` in `freeze.FROZEN_DOCUMENTS` (an accepted exception is
  replaced, never altered).
- Implement the pure `tools/docs_validation/evidence_gate.py`
  (`abstract_record`, `admit`), have `roadmap_status.py` consume it, and add
  `scripts/check_evidence.py`. Tests: VO-1 to VO-4.
- Add `docs/evidence-and-decision-records.md` (the component document for
  producers: schema, reason codes, exit codes, log-parser and trust-scanner
  obligations, kernel-contract status mapping). Update technical design §17.1
  and §17.2, ToR Q8, GAP9, the B08 entry, and `docs/users-guide.md` (public
  proof contract summary).
- `PF14.structural@1.1.4` is satisfied by the passing `evidence-gate` check;
  tick task 1.1.4.

### EP-M6. Reconciliation, roadmap closure, and final gates

- Add the D15 details to tasks 1.2.1, 1.2.3, 1.2.4, and 2.3.1 in
  `docs/roadmap.md` and re-export. Reconcile bet task lists and add the two-way
  check (VO-15).
- Update `docs/validation.md`, `docs/repository-layout.md` (new `spec/` and
  `tools/` files, `docs/adrs/`, `docs/execplans/`, the calibration probe),
  `docs/contents.md`, `docs/developers-guide.md` (per-module owners, the
  exception renewal runbook, the pre-registration amendment procedure, the
  report conflict rule), and `docs/revision-0.2.md` if affected.
- Run the full gates. Complete `Outcomes & retrospective` and set this plan
  to `COMPLETE`.

## Milestones and plateaus

- `EP-M0`. Outcome: `docs/roadmap.md` canonical; `spec/roadmap.json` an
  exported, drift-checked artefact; the old generator removed. Evidence: VO-0;
  `make design-check` passes with an unchanged `spec/roadmap.json`.
  Conformance: no roadmap content change; Wenmode is the only new dependency.
  Recovery: revert the stacked pull request. Compatibility: none.
- `EP-M1a`. Outcome: ADRs relocated under the new convention; a validated
  register with every record proposed; links from all five documents. Evidence:
  VO-5, VO-14; no broken local links. Recovery: revert. Gaps: every acceptance.
  Compatibility: none (no redirect for the old ADR path).
- `EP-M1b`. Outcome: evidence-gated ticks, obligation components, and the
  freeze check, with every task unticked. Evidence: VO-4 (synthetic), VO-7;
  `Design contracts` runs with full history. Recovery: revert while nothing is
  ticked; afterwards fix forward. Compatibility: none.
- `EP-M2`. Outcome: D01 to D07 and D13 recorded as accepted; ADR-0002 to
  ADR-0005; five documents reconciled; `publish = false`; task 1.1.1 ticked.
  Evidence: VO-5, VO-6, VO-13. Conformance: the 1.1.1 success text is
  satisfied; only `Cargo.toml` metadata changes on the Rust side. Recovery:
  superseding records only. Compatibility: none.
- `EP-M3`. Outcome: ADR-0006 and ADR-0007; contract records, examples,
  grammar corpus, excluded names; task 1.1.2 ticked. Evidence: VO-8, VO-9,
  VO-10 with seeded mutations. Conformance: all five success topics covered;
  `comb!` unchanged; no Rust change. Recovery: superseding records.
  Compatibility: none.
- `EP-M4`. Outcome: calibrated controls registered and frozen; task 1.1.3
  ticked. Evidence: VO-11, VO-12, VO-16; every control cites a calibration
  record or is labelled not calibrated; VO-7 rejects a threshold-plus-digest
  edit. Conformance: no acceptance measurement predates registration. Recovery:
  amendments only. Compatibility: none.
- `EP-M5`. Outcome: ADR-0009; schema version 2; exception register; pure gate
  with exhaustive tests; task 1.1.4 ticked via `PF14.structural@1.1.4`.
  Evidence: VO-1 to VO-4; `check_evidence.py` rejects the planned example with
  `not-run` (exit 1), admits the complete test fixture at `tested` (exit 0),
  and reports its partial-bounds variant at `bounded`. Conformance: the 1.1.4
  success text is satisfied; no version-1 consumer remains. Compatibility: none
  (no deployed consumer).
- `EP-M6`. Outcome: all four 1.1 tasks ticked; documents reconciled; plan
  `COMPLETE`. Evidence: full gates and the idempotence step pass.

## Concrete steps

Run all commands from the repository root.

```bash
export PY="uv run --python 3.14 --with-requirements tools/requirements.txt python3"
make design-check PYTHON="$PY" 2>&1 | tee /tmp/design-check-combobulate-1-1-resolve-acceptance-control-decisions.out
```

Red step, for example in `EP-M5`:

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
$PY scripts/export_roadmap.py
for g in reference bets; do $PY tools/generate_$g.py; done
$PY scripts/generate_decisions.py
$PY tools/check_docs.py --write --as-of "$(git log -1 --format=%cs)"
$PY scripts/export_roadmap.py --check
for g in reference bets; do $PY tools/generate_$g.py; done
$PY scripts/generate_decisions.py
git diff --exit-code -- docs/ spec/ && echo idempotent
```

Format, then have `scrutineer` run the gates one at a time, each through `tee`
to `/tmp/$ACTION-combobulate-<branch>.out`:

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
$PY scripts/check_evidence.py --as-of 2026-10-10 --require proof spec/proof-evidence.example.json; echo "exit=$?"
```

```plaintext
spec/proof-evidence.example.json: rejected [not-run]
exit=1
```

## Validation and acceptance

Quality criteria: `make test` passes unchanged;
`$PY -m unittest discover -s tools/tests` passes, including every new module,
each observed failing for the expected reason first; VO-0 to VO-16 discharged
with non-vacuity checks passing; `make check-fmt`, `make lint`,
`make markdownlint` (with spelling), and `make nixie` pass; `make design-check`
passes with `BASE_REV` set and the regenerated report committed. No benchmark
claims; thresholds are registered, not met. No network access in checks, no
secrets, no host identity in committed records.

Behavioural acceptance:

1. `docs/decision-register.md` lists D01 to D15 as accepted (D13 accepted as
   "no CODEOWNERS", D12 as delegated), each with its chosen option, date, and
   approval reference, plus all eight candidate ADR subjects.
2. `docs/roadmap.md` shows 1.1.1 to 1.1.4 ticked and no other ticked task;
   `scripts/export_roadmap.py --check` passes.
3. Reinserting "The classes remain proposed pending ToR Q4." into
   `docs/technical-design.md`, or writing "Q4 remains open", makes
   `make design-check` fail and name D03.
4. Changing AC-03's threshold and its digest in one commit makes
   `make design-check BASE_REV=origin/main` fail and name AC-03.
5. `check_evidence.py` rejects a `resource-exhausted` fixture, reports a
   partial-bounds Kani fixture at `bounded`, never `proof`, and rejects a
   self-reported Verus record with `verdict-self-reported`.
6. `docs/developers-guide.md` states the ISC licence and the `publish = false`
   policy, and `cargo publish --dry-run` refuses to publish.

## Idempotence and recovery

Generators, the exporter, and `check_docs.py --write` are idempotent for a fixed
`--as-of`. Tests use in-memory copies or temporary directories. If a milestone
fails midway, `git restore` the uncommitted files and rerun from its red step.
Git revert is safe only for milestones with no accepted records and no ticked
tasks; afterwards, reverse an accepted item with a superseding record. Before
any force push, fetch and compare the remote head (GitHub may rebase stacked
branches server-side). Resolve `docs/validation-results.json` conflicts by
taking either side and rerunning the generators, exporter, and
`check_docs.py --write`. Calibration probes build under their own ignored
`target/`, never `/tmp`, and can be rebuilt at any time.

## Artefacts and notes

New documents: `docs/decision-register.md` (generated),
`docs/evidence-and-decision-records.md`, `docs/acceptance-calibration.md`, and
`docs/adrs/adr-0002-governance-authority.md`,
`adr-0003-initial-release-scope.md`, `adr-0004-licence-and-publication.md`,
`adr-0005-pre-1-0-api-and-proof-interface-policy.md`,
`adr-0006-numeric-validity-and-reduction-contracts.md`,
`adr-0007-comb-macro-grammar-and-staging.md`,
`adr-0008-acceptance-control-pre-registration.md`,
`adr-0009-proof-first-policy-and-evidence-gate.md`. Moved:
`docs/adrs/adr-0001-repository-bootstrap.md`.

New specification files: `spec/decision-register.schema.json`,
`spec/decisions.json`, `spec/task-completion.json`,
`spec/semantic-contract.schema.json`, `spec/semantic-contracts.json`,
`spec/macro-grammar.json`, `spec/acceptance-controls.schema.json`,
`spec/acceptance-controls.json`, `spec/measurement-record.schema.json`,
`spec/calibration/`, `spec/exceptions.json`, `spec/exception.schema.json`,
`spec/evidence-reason-codes.json`. `spec/roadmap.json` becomes a derived export.

New tooling: helper scripts `scripts/export_roadmap.py`,
`scripts/generate_decisions.py`, and `scripts/check_evidence.py`; the probe
`tools/calibration/cardinality-probe/`; and `tools/docs_validation/` modules
`decisions.py`, `roadmap_status.py`, `freeze.py`, `package_policy.py`,
`contract_examples.py`, `grammar.py`, `preregistration.py`, `evidence_gate.py`.
Removed: `tools/generate_roadmap.py`.

New pytest suites in `scripts/tests/`: `test_export_roadmap.py` (with
`conftest.py` and the test-only `roadmap_render.py`),
`test_generate_decisions.py`, and `test_check_evidence.py`. New `unittest`
modules in `tools/tests/`: `test_roadmap_export_gate.py`,
`test_decision_register.py`, `test_roadmap_status.py`, `test_freeze.py`,
`test_package_policy.py`, `test_semantic_contracts.py`, `test_macro_grammar.py`,
`test_preregistration.py`, `test_exceptions.py`, `test_evidence_gate.py`,
`test_evidence_records.py`, and fixtures `evidence_gate_rules.json` and
`evidence/`.

## Interfaces and dependencies

New dependency: `wenmode==0.15.2` (sponsor-directed). Otherwise the standard
library (`tomllib`, `hashlib`, `subprocess` only in `freeze.py` for `git show`)
plus the pinned `jsonschema`, `hypothesis`, `markdown-it-py`, and `PyYAML`.

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

`admit` is pure and total over `AbstractRecord`; `abstract_record` raises
`ValidationError` only for schema-invalid records.

`scripts/check_evidence.py --as-of DATE [--require LEVEL] [--bindings FILE]
RECORD…`
prints `path: level [reasons]` per record and exits 0 when every record meets
`--require` (default `tested`), 1 when any falls short, and 2 for
schema-invalid input or usage errors.

`scripts/export_roadmap.py [--check] [--roadmap PATH] [--export PATH]` (or
`INPUT_CHECK=true`) exits 0 when the export is written or matches, 1 on drift
(printing a unified diff), and 2 on malformed roadmap structure (printing the
source line). The script exposes `parse_roadmap(text: str) -> dict` and
`RoadmapStructureError` for the checker.

`roadmap_status.py` exposes
`check_task_status(context, roadmap, decisions, components) -> None`;
`freeze.py` exposes `check_frozen(context, base_rev: str | None) -> None`;
`decisions.py` exposes `check_decision_register(context) -> None`;
`package_policy.py` exposes `check_package_policy(context) -> None`;
`preregistration.py` exposes `frozen_digest(control) -> str` and
`check_acceptance_controls(context) -> None`; `grammar.py` exposes
`parse(source: str) -> Parsed | Rejected` for the corpus model only.

## Signposts

Documentation: `docs/terms-of-reference.md` §§4, 7-10;
`docs/technical-design.md` §§2, 6, 7, 12, 14-18; `docs/context.md` §§6-7;
`docs/language-reference.md` §§6, 9; `docs/testable-bets.md` B01, B02, B03, B08;
`spec/proof-obligations.json` PF14; `docs/developers-guide.md`;
`docs/documentation-style-guide.md`; `docs/references.md` §D-CONTRACT;
`docs/complexity-antipatterns-and-refactoring-strategies.md`;
`docs/reliable-testing-in-rust-via-dependency-injection.md` (the injection
principle behind `--as-of` and `--base-rev`);
`docs/rust-testing-with-rstest-fixtures.md`, `docs/rust-doctest-dry-guide.md`,
and `docs/rstest-bdd-users-guide.md` (for later tasks that replay these
artefacts). External: Wenmode documentation (<https://wenmode.lepture.com/>),
leynos/mapsplice#144, GitHub-hosted runner reference.

Skills: `execplans`, `arch-decision-records`, `en-gb-oxendict-style`,
`hypothesis`, `rust-verification`, `verus`, `kani`, `mapsplice`,
`github-stacks`, `firecrawl-mcp`, `logisphere-design-review`, `commit-message`,
and `pr-creation`. Agents: `scrutineer` runs every gate; `scribe` makes
mechanical documentation edits; `wyvern` does read-only reconnaissance.

## Revision note

- 2026-10-10, initial draft.
- 2026-10-10, revised after the community-of-experts review (verdict
  "revise"): per-component evidence, `evidence_kind` split from `outcome`, new
  admission levels and substantive properties, fail-closed parsing and trust
  audits, a base-revision freeze, one decision per ADR, rigorous measurement
  protocols, corrected examples, per-milestone tolerances.
- 2026-10-10, revised for the sponsor's answers to D01 to D15: `leynos` as
  sponsor and technical owner; CODEOWNERS dropped (D13 rejected); ADRs and RFCs
  relocated under a four-digit naming convention (D07); `docs/roadmap.md` made
  canonical with a Wenmode exporter in a new `EP-M0` stacked pull request and
  upstream request leynos/mapsplice#144 (D15); threshold selection delegated to
  evidence-backed local calibration extrapolated to the 4-vCPU public runner
  class (D12); no host identity in records (D11); the publication policy
  documented in the developers' guide (D05); approval references admit session
  answers. Remaining work: deliver `EP-M0` now, then obtain approval of this
  revision before `EP-M1a`.
- 2026-10-11, helper scripts relocated per the sponsor: the roadmap exporter is
  `scripts/export_roadmap.py` under the scripting standards (Cyclopts, PEP 723,
  pytest suites in `scripts/tests/`), and the planned decision generator and
  evidence checker follow the same rule. Checker modules stay in
  `tools/docs_validation/`. Remaining work is unchanged.
