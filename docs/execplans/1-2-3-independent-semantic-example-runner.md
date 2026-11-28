# Introduce the independent semantic-example runner and route-identifying harness

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: DRAFT (expert review applied; awaiting user approval).

Branch: `1-2-3-independent-semantic-example-runner`, cut from `main` at
`bacad37`.

Roadmap item: 1.2.3 in `docs/roadmap.md`.

Implementation must not begin until the user explicitly approves this plan.

## Purpose / big picture

Combobulate is a Rust library for inspectable array algebra. Task 1.2.2 gave it
its first runnable public path: a caller builds an I64 vector with
`Array::from_i64`, applies `identity()` or `add()`, prepares the expression with
`NativeExecutor::sequential()`, and executes it. The arithmetic body that path
runs is `add_i64_into` in the `combobulate-kernel` crate, which Verus verifies
against the SC-12 semantic contract.

The project also keeps golden examples. `spec/examples.json` holds 75
`contract_cases` (EX21 to EX95). Each is a small tagged-scalar input, an
operation, and either an expected value or an expected error. Each case belongs
to one semantic contract in `spec/semantic-contracts.json` (SC-01 to SC-12;
SC-10 has no cases because its corpus is the `comb!` grammar). Today only a
Python documentation model, `scripts/docs_validation/contract_examples.py`,
evaluates them. No Rust code reads them, so nothing shows that the Rust library
meets the expectations the documentation records.

The technical design (§14) requires "an independent scalar reference evaluator
for the core logical semantics" that "must not share optimized indexing or
accumulation implementations with the routes it checks", and a test runner that
"records selected execution routes so differential tests cannot accidentally
compare the same fallback against itself". This task delivers both in their
smallest useful form.

Terms used throughout:

- *Golden case*: one entry of `contract_cases` in `spec/examples.json`. The
  roadmap's "golden-case contract" is that list together with the tagged-scalar
  encoding described by the file's `scalar_encoding` field.
- *Reference evaluator* (the *oracle*): Rust code that computes what a golden
  case means from the semantic contracts alone. It lives in a new test-only
  crate, `combobulate-reference`, which cannot see the production crates.
- *Route*: the production path that handles an expression: which executor
  ran or refused the plan, and which kernel body each arithmetic step
  dispatches to.
- *Route identity*: the value the library reports naming its route, for
  example executor `native.sequential` with kernel
  `combobulate_kernel::elementwise_add::add_i64_into`.
- *Seeded wrong-result mutation*: a deliberately wrong implementation, such as
  an addition that wraps on overflow instead of reporting `IntegerOverflow`,
  used to prove that the harness notices wrong answers.
- *Oracle independence boundary*: the stated, machine-checked rule that the
  reference evaluator shares no execution code with any production route.

After this change, a contributor runs:

```sh
cargo nextest run --no-default-features --test semantic_examples
```

and sees 75 named replay cases, `replays_contract_case::case_01_ex21` to
`case_75_ex95` (rstest 0.27 names a described case
`case_{index}_{description}`). Every case agrees with the reference evaluator.
A route report, kept as an `insta` snapshot, says for each case what the
production library did:

- EX89 to EX93 *executed* on executor `native.sequential` through kernel
  `combobulate_kernel::elementwise_add::add_i64_into`, and agree with the
  reference;
- EX94 and EX95 were *refused at preparation* by `native.sequential` with
  `ShapeAgreement` before any kernel was selected, which is the contract's
  required outcome;
- the other 68 cases are *reference only*, because no production route for
  their operations exists yet. They never count as passing on a route.

Negative-control tests show that a route seeded with wrapping addition fails
EX92 and EX93 for the intended reason, that an always-failing route fails the
value cases, that a route misreporting itself is rejected, and that the
reference crate declares no dependency on any production crate.

A downstream caller gains one small public observation:

```rust
use combobulate::{Array, ExecutorId, NativeExecutor, add};

let xs = Array::from_i64(vec![1, 2, 3]).expr();
let plan = add().apply(&xs, &xs).prepare(&NativeExecutor::sequential())?;
let route = plan.route();
assert_eq!(route.executor(), ExecutorId::NativeSequential, "one engine today");
assert_eq!(route.executor().name(), "native.sequential", "stable label");
let symbols: Vec<&str> = route.kernels().iter().map(|k| k.symbol()).collect();
assert_eq!(
    symbols,
    ["combobulate_kernel::elementwise_add::add_i64_into"],
    "an addition step names the verified kernel it dispatches to",
);
# Ok::<(), combobulate::ExpressionError>(())
```

Existing behaviour is preserved: no operation, error, or diagnostic of the
1.2.2 path changes. The Python documentation model stays (DL-3).

This task closes roadmap item 1.2.3, including its detail "Replay the semantic
contract examples (`contract_cases` in `spec/examples.json`) as `rstest`
cases". It also absorbs the independent oracle that task 1.2.2's FACADE-1
property deliberately left in place for this task.

## Constraints

- The kernel crate `crates/combobulate-kernel` is not modified. Its Verus
  proofs, seeded Verus mutants and zero-dependency rule (VO-1 in
  `tests/workspace_boundaries.rs`) stay as they are.
- Oracle independence boundary (OIB-1 to OIB-4 in `Verification plan`): the
  new crate `crates/combobulate-reference` declares no dependency of any kind
  (normal, build or dev) for any target, has no build script, uses no
  `include!`, `include_str!`, `include_bytes!`, `env!` or `#[path]`, is
  `publish = false`, and is a dev-dependency of the root package only. No
  shipped crate may depend on it. This boundary is not negotiable within this
  plan.
- Algorithmic diversity: the reference must not call, include, or copy by
  hand any function body from `src/` or `crates/combobulate-kernel/`. Where the
  production route uses a technique, the reference uses a different one. For
  SC-12 the kernel uses `i64::checked_add` with a scan-then-write loop; the
  reference widens to `i128` and finds the least failing position with
  `Iterator::position`. Shared *type and schema* definitions are permitted
  (technical design §14); here the reference crate owns the case schema, so the
  dependency runs from the harness to the reference, never the reverse.
- The reference carries no fault-injection switches. Seeded faults live only on
  the route side of the harness (DL-9).
- Proof features must not substitute a route. No `cfg(test)`, `cfg(kani)` or
  feature flag may change which kernel the production route dispatches to
  (technical design §17.7). The route report must describe the code the plan
  executes.
- The reference crate is never cited as evidence for a proof-obligation (PF)
  component and never stands in for a proof (B01's decision rule: "do not …
  hide a duplicate checker").
- Reference lint policy: the workspace lints (`Cargo.toml` lines 68 to 151)
  apply unchanged. They deny `float_arithmetic`, `integer_division`,
  `integer_division_remainder_used`, `cast_precision_loss`,
  `cast_possible_truncation`, `indexing_slicing` and others. Integer division
  and remainder use `checked_div` and `checked_rem`, which the contracts need
  anyway. Each function that performs contract-mandated IEEE arithmetic carries
  one item-scoped
  `#[expect(clippy::float_arithmetic, reason = "SC-xx states IEEE …")]`.
  Integer-to-float conversions go through `f64::from` on a `u32` or `i32` where
  exact, or through one small helper with an item-scoped expectation whose
  reason cites the contract. No crate-level allowance.
- Public API changes are limited to the items in `Interfaces and dependencies`.
  They are additive and pre-1.0 (ADR-0005); no compatibility machinery is
  introduced.
- Ordinary consumers stay verifier-free and backend-free:
  `tests/workspace_profiles.rs` must continue to pass for `native-only` and
  `polars-enabled`.
- Repository rules apply in full (`AGENTS.md`): files under 400 lines; a `//!`
  comment on every module, including test modules; every assertion carries a
  message; no `unwrap` or `expect` outside tests; `cap_std` and `camino` for
  file access; no `std::env::var`; item-scoped `#[expect(…, reason = …)]` only;
  test submodules through `#[path]` because `self_named_module_files` is
  denied; en-GB-oxendict spelling.
- Any test binary that runs Cargo must belong to nextest's `nested-cargo`
  group and its warm-up (`.config/nextest.toml`, NC-005 and NC-010). The new
  `semantic_examples` binary runs no subprocess; dependency-graph checks live in
  `tests/workspace_boundaries.rs`, which is already in that group.
- Dependencies: no new third-party crate. `serde_json`, `rstest`,
  `rstest-bdd`, `googletest`, `pretty_assertions`, `insta`, `proptest`,
  `camino` and `cap-std` are already root dev-dependencies. `cargo-mutants`
  27.1.0 is installed on the host and is used only for recorded evidence.
- The completed ExecPlans under `docs/execplans/` are historical and are not
  edited.
- Generated files are regenerated, never hand-edited: `spec/roadmap.json`
  (`scripts/export_roadmap.py`), `docs/validation-results.json`
  (`scripts/check_docs.py --write`) and `typos.toml` (`make spelling`).
- Implementation begins only after the user approves this plan.

## Tolerances (exception triggers)

This ExecPlan file is excluded from every count. Generated or captured files
are also excluded: `Cargo.lock`, `spec/roadmap.json`,
`docs/validation-results.json`, `typos.toml`, and `insta` snapshots under
`tests/snapshots/`.

Comparison base: the merge base with `origin/main`. Net lines are additions
minus deletions. Classification is by whole file:

- Code: `*.rs`, `tests/features/*.feature` (executable specifications),
  `scripts/**/*.py`, `Makefile`.
- Configuration: every `Cargo.toml`, `.config/**`, `.github/**`,
  `.gitignore`, `spec/**/*.json` other than generated files, and
  `tests/fixtures/**/*.json`.
- Documentation: `docs/**/*.md` other than this plan, and `README.md`.

Counting command:

```sh
set -o pipefail
base="$(git merge-base origin/main HEAD)"
git diff --numstat "$base" -- . \
  ':(exclude)docs/execplans/1-2-3-independent-semantic-example-runner.md' \
  ':(exclude)Cargo.lock' ':(exclude)spec/roadmap.json' \
  ':(exclude)docs/validation-results.json' ':(exclude)typos.toml' \
  ':(exclude)tests/snapshots/**' |
awk '{ n = $1 - $2; f = $3
       if (f ~ /\.(rs|feature|py)$/ || f == "Makefile") c += n
       else if (f ~ /(Cargo\.toml|\.json)$/ || f ~ /^\.(config|github)\// || f == ".gitignore") g += n
       else d += n; files++ }
     END { printf "files %d code %d config %d docs %d\n", files, c, g, d }'
```

Survey behind the budgets. The Python documentation model this task mirrors is
366 lines (`contract_examples.py`), 91 (`elementwise_examples.py`) and 45
(`scalar_codec.py`) over 27 operations. A Rust port with module comments,
rustdoc examples, typed values, the lint policy above, and unit tests is
estimated at 1,400 to 1,800 lines across about ten modules. The harness
(decoder and codec round trip, route adapters, report, replay table, controls,
differential property, BDD steps) is estimated at 1,000 to 1,200 lines. The
route-identity API with its tests is about 300 lines, and the boundary checks,
FACADE-1 absorption and consumer fixture about 200. That is roughly 2,900 to
3,500 code lines in about 42 files.

History. Task 1.2.2 set 60 files and 4,500 net lines (code and documentation
combined) and finished at 94 files and 10,057 lines; the maintainer granted a
20,000-line expansion on 2026-11-25. Its record names one-file-per-
responsibility structure, second-round review repairs, and record
reconciliation as causes. Those causes recur here, so the budgets carry about
25% contingency over the upper estimate, and the milestones are ordered so the
roadmap's success line is met before the bulk of the port (see decision gate G1
after EP-M3).

- Files: escalate if more than 55 non-ExecPlan files change.
- Code: escalate above 4,400 net lines.
- Configuration: escalate above 150 net lines.
- Documentation: escalate above 900 net lines.
- Interface: escalate if a public item beyond those in
  `Interfaces and dependencies` is needed, or if an approved signature changes
  shape (renamed type, different return type, added type parameter). Adding
  `#[must_use]`, `const` or `#[non_exhaustive]` is not a shape change. The
  listed `Display` implementations are approved items.
- Dependencies: escalate before adding any crate to any manifest, including
  an existing workspace crate as a dependency of the reference crate.
- Architecture: escalate if any shipped crate gains an edge to
  `combobulate-reference`, or if a further workspace member is needed.
- Governance: these edits are pre-approved: a 1.2.3 entry in
  `spec/task-completion.json`; ticking task 1.2.3 in `docs/roadmap.md` and
  regenerating `spec/roadmap.json`; ADR-0013 and its `docs/contents.md` entry;
  an amendment banner and section on ADR-0010; edits to technical design §14;
  `docs/users-guide.md`; `docs/developers-guide.md` (workspace prose and table,
  Table 2 row, new replay section); `docs/repository-layout.md`; regenerating
  `docs/validation-results.json`. `spec/bets.json` and the decision register
  are not changed. Any change to `scripts/docs_validation/` needs escalation.
- Iterations: escalate if a gate still fails after three fix attempts on the
  same cause.
- Time: escalate if a milestone takes more than two working days.
- Semantics: escalate if the Rust reference and a recorded expectation in
  `spec/examples.json` disagree on any case after the reference has been
  checked against the contract text. A disagreement is a specification
  question, not a test to adjust.
- Ambiguity: escalate when two materially different readings of a contract or
  requirement appear.

## Risks

- Risk: the Rust reference reproduces a Python modelling choice that the
  contract text does not state (for example two-pass variance rounding, or a
  cast boundary), so both models agree with each other but not with the
  contract. Severity: medium. Likelihood: medium. Mitigation: write each
  reference module from `spec/semantic-contracts.json` and ADR-0006 first,
  reading the Python only to settle encoding questions; record each place the
  contract text was insufficient in `Surprises & discoveries` and escalate per
  the Semantics tolerance.
- Risk: F64 results are compared by value instead of by bit pattern, hiding a
  defect in signed zeros or NaN payloads. Severity: high. Likelihood: medium.
  Mitigation: H-1 compares F64 by `to_bits()` with no relaxation. EX60 is the
  only case whose expected result is a NaN, EX41 covers `-0.0`, and EX82 and
  EX83 cover overflow to infinity. Residual gap: every NaN input in the golden
  cases is the canonical `0x7ff8000000000000`, so payload propagation is not
  discriminated by these cases. When an F64 route lands, a NaN-class relaxation
  may apply on the route side only, and only where SC-07 permits "a NaN"; H-1
  stays bit-exact.
- Risk: a seeded fault in the kernel panics (the dev profile checks
  overflow, and the kernel's write loop uses plain `+`) instead of producing a
  wrong value, so a test fails for the wrong reason. Severity: high.
  Likelihood: high. Mitigation: route adapters run under `catch_unwind` and
  report `Observed::Panicked`; the judgement distinguishes `Panicked` from a
  wrong value, and MUT-1 classifies each caught mutant by how it was caught.
- Risk: the route-identity API grows into a premature `.explain()` (E006).
  Severity: medium. Likelihood: low. Mitigation: the API reports only the
  executor and the distinct kernels; rustdoc says E006 will add per-step
  detail; the Interface tolerance enforces the limit.
- Risk: cargo-mutants is slow under the shared compile queue, or reports
  mutants the replay cannot see. Severity: low. Likelihood: medium. Mitigation:
  the run is scoped to two files and is recorded evidence, not a gate; each
  missed or unviable mutant is triaged.
- Risk: the hand-listed case rows drift from `spec/examples.json`. Severity:
  medium. Likelihood: medium. Mitigation: H-3 compares them in both directions.
- Risk: adding a fifth workspace package (after the facade, kernel, macros
  and test macros) or changing `default-members` trips workspace-shape tests.
  Severity: low. Likelihood: low. Evidence so far: `MEMBERS` in
  `tests/support/workspace_metadata.rs` lists only the shipped crates, and no
  test asserts `default-members`. Mitigation: EP-M1 runs
  `tests/workspace_boundaries.rs`, `tests/workspace_profiles.rs` and
  `tests/build_profiles.rs` first and edits only what fails, with a reason.
- Risk: the reference crate under `crates/**` triggers the `formal.yml`
  workflow on every change. Severity: low. Likelihood: certain. Mitigation:
  accepted; the formal jobs do not build the crate. Narrowing the trigger is
  left to a later workflow change.
- Risk: another branch lands ADR-0013 first. Severity: low. Likelihood: low.
  Mitigation: EP-M6 checks `git ls-tree origin/main docs/adrs/` before merge
  and renumbers by the style guide's rule if needed, as the 1.2.2 plan did.

## Progress

- [x] (2026-11-28) Branch renamed to
  `1-2-3-independent-semantic-example-runner`; Wyvern reconnaissance over code,
  specifications, traceability and gates.
- [x] (2026-11-28) Initial draft committed (`1f59cc9`).
- [x] (2026-11-28) Expert review by three reviewers (verification and oracle
  independence; Rust API and test architecture; governance and scope) applied;
  see the revision note.
- [ ] Plan approved by the user.
- [ ] `EP-M1` Oracle independence boundary and golden-case reader.
- [ ] `EP-M2` Route identity on prepared plans and engines.
- [ ] `EP-M3` SC-12 vertical slice: reference, harness, controls, property.
- [ ] Decision gate G1 after EP-M3.
- [ ] `EP-M4` Reference port of the remaining contract families (M4a to M4c).
- [ ] `EP-M5` FACADE-1 absorption, consumer fixture, mutation evidence.
- [ ] `EP-M6` Documentation, ADR-0013, completion record, roadmap tick.

## Surprises & discoveries

- Observation: the roadmap's "golden-case contract" has no other definition in
  the repository. Evidence: no occurrence of "golden case" in `docs/` or
  `spec/`. Impact: this plan defines it in Purpose.
- Observation: no Rust code reads `spec/examples.json`. One test reads
  `spec/semantic-contracts.json` through `cap_std`
  (`tests/ordinary_application/diagnostics.rs`, around line 92). Impact: that
  test is the precedent for file access.
- Observation: of the 75 cases only the seven SC-12 cases (EX89 to EX95) are
  expressible through the public API, and two of those (EX94, EX95) are refused
  at preparation, so they never produce a `PreparedPlan`. Evidence:
  `src/plan/schedule.rs` records `Failure::ShapeAgreement` during scheduling.
  Impact: the route model has a `Refused` outcome, and `NativeExecutor::id()`
  is public so a refusal can name its engine.
- Observation: `combobulate-test-macros` is a precedent for a
  `publish = false`, test-only crate under `crates/`, but it is outside
  `default-members`, so the gates never select its targets. Impact: the
  reference crate is added to `default-members` (DL-10) so its unit tests and
  lints run in `make test` and `make lint`.
- Observation: the roadmap exporter rejects ticked detail checkboxes
  (`scripts/export_roadmap.py`, around line 130: "detail checkboxes are not
  tracked; tick the task instead"). Impact: only task 1.2.3 is ticked; the
  detail is evidenced by its completion artefacts.
- Observation: the kernel's write loop uses plain `+`, and the root manifest
  sets no `overflow-checks` override, so a seeded kernel fault panics in the
  test profile rather than returning a wrong value. Impact: the `Panicked`
  observation and MUT-1's classification.

## Decision log

Entries are dated 2026-11-28 and authored by the planning agent unless noted.
Entries marked "requires approval" are accepted, if at all, by the user's plan
approval.

- DL-1. Decision: the reference evaluator is a separate zero-dependency
  crate, `crates/combobulate-reference`, consumed only as a root
  dev-dependency. Rationale: a crate boundary makes independence a compiler
  fact (the crate cannot name `combobulate` or `combobulate_kernel`) and a
  metadata fact (OIB-1, OIB-2), rather than a review convention. The strongest
  alternative, a module under `tests/` like FACADE-1's `refinement/model.rs`,
  can import the facade at any time, and only a source scan could notice.
  Requires approval (adds a workspace member; ADR-0013 records it and amends
  ADR-0010).
- DL-2. Decision: the reference covers every operation the 75 golden cases
  use (27 operations), not only SC-12. Rationale: D15 fixed this detail in
  advance so that later criteria would not be "chosen after the fact";
  technical design §14 says the Python checks "are not that future evaluator";
  later tasks (2.1.x, 2.2.x, 2.3.5) need an oracle for their routes. The
  alternative, a SC-12-only reference with 68 unevaluated rows, would be
  filtered-away evidence, which §14 forbids. The port is ordered after the
  SC-12 vertical slice (EP-M3) and split by contract family, so the risky new
  work lands first and a budget overrun is caught at decision gate G1. Requires
  approval (sets the code budget).
- DL-3. Decision: `scripts/docs_validation/contract_examples.py` stays as the
  documentation model run by `make design-check`, and keeps the design-time
  seeded-mutation check that `semantic_contracts.py` performs through its
  `outcome` function. The Rust replay owns implementation conformance. Table 2
  of `docs/developers-guide.md` changes from "Superseded by `rstest` replay in
  task 1.2.3" to "Stays: design-time model and seeded-mutation check for
  `make design-check`; implementation conformance moved to the Rust replay
  (`tests/semantic_examples.rs`) in task 1.2.3". Rationale: `design.yml` runs
  without a Rust toolchain; the roadmap schedules no deletion for this task
  (contrast 2.3.1, which deletes `grammar.py`); the developers' guide already
  distinguishes "Superseded" from "Deleted after"; the `evidence_gate.py` row
  ("Reference model until the Rust replay in task 1.2.4") is the precedent.
  Requires approval.
- DL-4. Decision: route identity is a small public observation:
  `PreparedPlan::route()`, `NativeExecutor::id()`, and the value types `Route`,
  `ExecutorId` and `KernelId`. Rationale: the harness must take the route from
  the library rather than label it itself; a self-written label cannot catch a
  substitute executor (V15) or a fallback compared with itself (§14). A
  `#[doc(hidden)]` or `cfg(test)` seam would be a proof-only path, which §17.7
  forbids. `NativeExecutor::id()` is needed because a refused case (EX94, EX95)
  has no plan, so only the engine can name itself. The API is a strict subset
  of what E006 `.explain()` will report ("selected engine").
  `KernelId::symbol()` exposes the kernel's crate path on purpose: it is the
  identity the Verus provenance record binds (V14), and it may change before
  1.0. Requires approval (public API).
- DL-5. Decision: each golden case is a `#[case::exNN("EXNN")]` row on one
  `rstest` function, generated together with a `LISTED` constant from one
  `macro_rules!` list, plus a two-way completeness test, rather than a
  procedural macro that reads the JSON at expansion time. Rationale: rows give
  per-case names in nextest output with no build-time file reads, no
  environment access in a procedural macro and no rebuild-tracking hazard.
  rstest 0.27 accepts the case description from an `ident` metavariable:
  `macro_rules!` expansion completes before rstest parses the attribute, and
  `ident` fragments are passed transparently. The name format
  `case_{index}_{description}` comes from
  `rstest_macros-0.27.0/src/render/mod.rs`. D15 prescribes the same
  completeness pattern for 2.3.1.
- DL-6. Decision: expected outcomes have an opaque type,
  `combobulate_reference::Verdict`, with private fields and no public
  constructor; only `combobulate_reference::evaluate` produces one, and
  comparison happens through `Verdict::judge(&Observed) -> Judgement`.
  Rationale: the harness cannot build an "expected" value from a route's
  output, so a shared faulty body cannot become the oracle by accident.
- DL-7. Decision: neither Verus nor Kani is selected for this task. Technical
  design §17.1 asks each task to choose; the choice and its reasons are in
  `Verification plan`, "Where formal verification is not warranted".
- DL-8. Decision: permanent seeded-fault controls are harness-level mutant
  routes (NC-1, NC-3, NC-5) and a seeded differential property (H-4's control).
  A real mutation of the optimized body is exercised once with `cargo-mutants`
  (MUT-1) and once by hand (SEED-1), both as recorded evidence. Rationale: a
  permanent control must run in `make test` without editing production code;
  the recorded runs show that a fault *inside the optimized body* is caught by
  value, which a wrapper alone cannot show.
- DL-9. Decision: the reference has no mutation parameter; the 13 contract
  seeded mutations are not re-implemented in Rust. Rationale: threading fault
  switches through the oracle gives the independent evaluator fault paths of
  its own; the check that each contract's seeded mutation changes an example
  already exists in `semantic_contracts.py` and stays (DL-3). The reference's
  non-vacuity comes from agreeing with 75 independently recorded expectations.
  Alternative considered: `evaluate_mutated` with a mutation-tagged `Verdict`
  that routes refuse; rejected as duplicate machinery for no new evidence.
- DL-10. Decision: add `crates/combobulate-reference` to the workspace
  `default-members`. Rationale: `make test` and `make lint` run without
  `--workspace` (`Makefile`, `CARGO_FLAGS ?= --all-targets`), so a crate outside
  `default-members` would have its unit tests and lints silently skipped. The
  alternative, keeping every reference test in root integration tests, leaves
  the crate's own targets unlinted.
- DL-11. Decision: dependency-graph checks for the boundary (OIB-1, OIB-2,
  NC-4) live in `tests/workspace_boundaries.rs`, extended by generalizing its
  `kernel_dependency_names` helper into `dependency_names(metadata, package)`.
  Rationale: that binary already runs `cargo metadata`, belongs to the
  `nested-cargo` group, and holds the metadata fixtures. If it would pass 400
  lines, the checks move to a new `tests/workspace_reference_boundary.rs` added
  to both nextest filters.
- DL-12. Decision: ADR-0013 records the independence boundary, the public
  route observation and the default-member change, and ADR-0010 receives an
  amendment banner and section stating that it governs the three *shipped*
  crates and that test-only crates (`combobulate-test-macros`,
  `combobulate-reference`) sit outside that count with dev-only edges from the
  root. Rationale: ADR-0010 says "The workspace has three crates", which the
  1.2.2 test-macro crate already contradicts; an implied amendment is not
  allowed by the documentation style guide. Keeping the Python model is a Table
  2 matter, not an ADR. No decision-register entry is added; ADR-0013 is
  accepted by plan approval, as ADR-0012 was.

## Outcomes & retrospective

Not started.

## Context and orientation

Repository layout relevant to this task:

- `Cargo.toml` (root): the facade package `combobulate` and the workspace
  (`members = ["crates/*"]`, `default-members` at line 3,
  `exclude = ["tools"]`). Root dev-dependencies at lines 44 to 66; workspace
  lints at lines 68 to 151.
- `src/plan/mod.rs`: `NativeExecutor` (the only engine; `sequential()`),
  `PreparedPlan` (`execute()`, which hands its steps back to the engine's
  private `run`), the private `Step` enum (`Input`, `Add`), `sum`, and the
  private `const fn dispatch_add`, "the facade's only route to an arithmetic
  body", which calls `combobulate_kernel::elementwise_add::add_i64_into`.
  `src/plan/tests.rs::the_dispatch_route_is_the_verified_kernel` pins that
  dispatch.
- `src/plan/schedule.rs`: the scheduling walk; static shape disagreements
  become `Failure::ShapeAgreement` at `Stage::Preparation`.
- `src/expr/mod.rs`: `AExpr`, `Unary`, `Binary`, `OperationId` (`name()`,
  `catalogue_id()`, `Display`), `identity()`, `add()`.
- `src/error/mod.rs`: `ExpressionError` (`stage()`, `failures()`), `Failure`
  (`ShapeAgreement`, `IntegerOverflow { operation, position }`, `code()`),
  `Stage`.
- `crates/combobulate-kernel/src/elementwise_add.rs`: `add_i64_into`, the
  optimized, Verus-verified body: a `checked_add` scan for the least
  overflowing position, then a write loop using plain `+`.
- `tools/verifier-fixtures/verus-kernel/provenance.json`: the Verus
  provenance record, whose `"symbol"` is
  `combobulate_kernel::elementwise_add::add_i64_into`.
- `spec/examples.json`: 75 `contract_cases`. Fields: always `id`, `contract`,
  `operation`; exactly one of `expected` or `expected_error`; operands in
  `input`, `args`, `cell`, `shape`, `axis`, `count`, `destination`, `output`,
  `fail_at`; modifiers `binary`, `dtype`, `identity`, `skip_nulls`, `ddof`,
  `to`. Plain JSON integers are I64, booleans are Bool, and `null` is the
  invalid (null) cell in ADR-0006's validity vocabulary. F64 values are
  `{"f64": "<decimal>"}` or `{"f64_bits": "<hex>"}`, and wide I64 values
  `{"i64": "<decimal>"}`. `expected_error` is a registered code, optionally
  followed by `at position N` (EX92: position 1; EX93: position 0, the least of
  two overflowing positions).
- `spec/semantic-contracts.json`: SC-01 to SC-12 with `examples`,
  `seeded_mutations`, `error_codes` (17 registered) and `discharged_by`.
- `scripts/docs_validation/contract_examples.py`: the Python documentation
  model, with `elementwise_examples.py` and `scalar_codec.py`.
- `tests/ordinary_application.rs` and `tests/ordinary_application/`: the 1.2.2
  facade tests, using `#[path]` submodules; `refinement/` is FACADE-1's
  proptest refinement against an `i128` memoizing oracle.
- `tests/workspace_boundaries.rs` and `tests/support/workspace_metadata.rs`:
  `cargo::live_metadata()` (which runs `cargo metadata --no-deps`, so it
  reports declared edges), `kernel_dependency_names`, `MEMBERS`, and fixtures in
  `tests/fixtures/cargo/`.
- `tools/fixtures/native-consumer/`: an out-of-workspace consumer whose
  `src/bin/ordinary_application.rs` output is snapshotted by
  `tests/native_consumer_e2e.rs` as
  `tests/snapshots/native_consumer_e2e__ordinary_application.snap`.
- `tests/features/` with `rstest-bdd` 0.6; `tests/build_profiles.rs` shows the
  step-binding style.
- `.config/nextest.toml`: test groups, including `nested-cargo` and its
  warm-up scripts.

Gates (from `Makefile`): `make check-fmt`, `make lint` (Clippy, Whitaker and
interrogate, per profile), `make test` (nextest per profile, then doctests),
`make markdownlint` (also runs `make spelling`), `make nixie`, and
`make design-check` (`check_docs.py` and the Python tests; set `PYTHON` to a
Python 3.14 interpreter, because host `python3` is 3.12). `GATE_PROFILE`
defaults to `both` (`native-only` and `polars-enabled`).

Documents and skills to keep open while implementing:

- `docs/technical-design.md` §14 and §17 (§17.1 discipline, §17.2 success
  witnesses and negative controls, §17.7 no proof-only substitution and profile
  statement).
- `docs/adrs/adr-0006-numeric-validity-and-reduction-contracts.md`, and the
  decisions it records: D09 (F64 specials, `min` and `max`), D10 (typed-cell
  atomicity, which governs SC-09), D14 (`div` on I64).
- `docs/adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md`,
  `docs/adrs/adr-0010-workspace-crate-boundaries-and-build-profiles.md` and
  `docs/adrs/adr-0012-minimal-value-and-expression-representation.md`.
- `docs/developers-guide.md` (testing, nextest groups, workspace layout,
  governance Table 2, task completion), `docs/documentation-style-guide.md`
  (ADRs and amendments).
- `docs/rust-testing-with-rstest-fixtures.md`, `docs/rstest-bdd-users-guide.md`,
  `docs/reliable-testing-in-rust-via-dependency-injection.md`,
  `docs/rust-doctest-dry-guide.md`,
  `docs/complexity-antipatterns-and-refactoring-strategies.md`,
  `docs/references.md`.
- Skills: `rust-router`, then `rust-unit-testing` (rstest tables, googletest,
  insta), `rust-types-and-apis` (the route API), `arch-crate-design` (the new
  crate), `proptest`, `nextest`, `arch-decision-records` (ADR-0013),
  `en-gb-oxendict`, `execplans`.

## Conformance basis

- Terms of reference: `docs/terms-of-reference.md` §6.1 at `bacad37`. G2
  ("a predictable meaning across supported execution routes") and G7
  (proof-first delivery) are served directly; G6 by reusing existing tooling
  and keeping the Python model rather than rewriting governance.
- Technical design: `docs/technical-design.md` at `bacad37`. Requirements
  traced here:
  - TDD-14a: an independent scalar reference evaluator that shares no
    optimized indexing or accumulation implementation with the routes it
    checks.
  - TDD-14b: the test runner records selected execution routes.
  - TDD-14c: negative controls fail for the intended reason; skipped or
    filtered examples do not discharge an obligation.
  - TDD-17a (§17.1): logical model, permitted errors, mutation frame,
    termination claim and trust boundary are recorded before implementation.
  - TDD-17b (§17.2): an always-`Err` implementation fails a success witness.
  - TDD-17c (§17.7): no proof feature substitutes a route; a harness states
    the profile it was built under.
- Roadmap: 1.2.3 and its detail (D15).
- Bets: B01 (`docs/testable-bets.md`; `spec/bets.json` already lists 1.2.3).
- Decisions: D06 (pre-1.0 API policy, for the additive API), D09, D10, D14
  (the numeric contracts the reference implements), D15 (the replay
  obligation), D16 (crate boundaries, amended in scope by ADR-0013).
- ADRs: ADR-0005, ADR-0006, ADR-0009, ADR-0010 (amended), ADR-0012.
- Verification obligations touched: V5 (force actual routes against an
  independent model), V14 (evidence binds to actual executable identities), V15
  (wrong-denotation, always-`Err` and substitute-executor mutations fail). No
  PF component is assigned to 1.2.3 in `spec/proof-obligations.json`, and none
  is added.

Gaps closed: GAP-1, no Rust code reads the golden cases; GAP-2, no independent
reference evaluator exists beyond FACADE-1's private one; GAP-3, no route
identity is observable.

```plaintext
TOR G2 -> TDD-14a -> OIB-1..OIB-4, H-1, H-5 -> EP-M1, EP-M3, EP-M4
    -> workspace_boundaries::reference_*, semantic_examples::replays_contract_case
TOR G2 -> TDD-14b -> RI-1..RI-3 -> EP-M2, EP-M3
    -> plan::tests::route_*, semantic_examples::report::*
TOR G7 -> TDD-14c, TDD-17b -> NC-1, NC-3, NC-4, NC-5, H-4 -> EP-M3, EP-M5
    -> semantic_examples::controls::*, semantic_examples::differential::*
TOR G7 -> TDD-14c -> MUT-1, SEED-1 -> EP-M3, EP-M5 -> Artefacts and notes
D15 -> roadmap 1.2.3 detail -> H-1, H-3 -> EP-M3, EP-M4
```

## Verification plan

### Abstract model, stated first

A golden case `c` has an operation `op(c)`, operands `in(c)`, and a recorded
expectation `exp(c)`, which is `Value(v)` or `Error(code, pos?)`. Scalars are
`Null | Bool(b) | I64(n) | F64(bits)`. Equality of F64 is equality of bits.

The reference denotation `ref(c)` is the meaning the semantic contracts assign
to `op(c)` on `in(c)`. A route `r` maps a case to an observation:

```plaintext
obs(r, c) ∈ { Unsupported,
              Refused(executor, outcome),        -- rejected before a plan exists
              Ran(route_id, outcome),            -- a plan was prepared and executed
              Panicked(executor) }
```

The harness verdict for a case is:

```plaintext
ref_ok(c)       iff ref(c) = exp(c)                         (bit-exact)
route_ok(r, c)  iff obs(r, c) = Unsupported
                 or obs(r, c) = Refused(e, o),  e = declared_executor(r),
                                                judge(ref(c), o) = Agrees
                 or obs(r, c) = Ran(id, o),     id = declared_route(r),
                                                judge(ref(c), o) = Agrees
passes(c)       iff ref_ok(c) and route_ok(production, c)
```

`Panicked` never agrees. `Unsupported` is never reported as a pass on a route:
the report marks it "reference only". The suite passes iff every listed case
passes, the listed set equals the file's set, the executed set is {EX89, …,
EX93}, and the refused set is {EX94, EX95}.

An observed error agrees only if it carries exactly one failure whose code and
position equal the expectation's; a route reporting two failures cannot pass on
its first one.

Mutation frame and termination (TDD-17a): `evaluate`, `judge`,
`PreparedPlan::route` and `NativeExecutor::id` are pure; they read their
arguments and allocate only their results. Each terminates in time linear in
its input: the reference makes one or two passes over finite operand sequences,
and `route()` makes one pass over the plan's steps. Permitted errors: decoding
fails with the case identifier on malformed input; the reference returns
contract errors as `Verdict` values, never by panicking.

### Oracle independence boundary (stated before any evaluator code)

- OIB-1. The reference crate declares no dependency of any kind (normal,
  build, dev) for any target, and has no build script.
- OIB-2. Every dependency edge that names the reference crate comes from the
  root package with kind `dev`. No shipped package reaches it.
- OIB-3. The reference crate's sources contain no `include!`,
  `include_str!`, `include_bytes!`, `#[path]` or `env!`, so no file outside the
  crate can enter it at compile time.
- OIB-4. A `Verdict` (the expected side of every comparison) can only be
  produced by `combobulate_reference::evaluate`: private fields, no public
  constructor, no `From` conversion, no `Default`.

Together, OIB-1 to OIB-4 establish that a fault in the optimized body
(`add_i64_into`, the facade's schedule and error mapping, or any later route)
cannot also appear in the expected value: the code computing it cannot reach
that body by call or by inclusion, and the expected value cannot be built from
a route's output. They do not establish that the reference is *correct*; that
is H-1, checked against independently recorded expectations, with the Python
documentation model as corroboration over the same expectations, not as
separate evidence. Nor do they forbid a hand-copied algorithm; the
algorithmic-diversity constraint and review cover that, with a source scan for
`checked_add` in the reference's SC-12 module as a weak backstop.

### Obligations

- OIB-1, OIB-2 checks. Method: tests in `tests/workspace_boundaries.rs`
  (`reference_declares_no_dependency`,
  `only_the_root_dev_depends_on_reference`) over live `cargo metadata`, plus a
  manifest read asserting no `build` key and no `build.rs`. Command:
  `cargo nextest run --test workspace_boundaries`. Non-vacuity (NC-4): the same
  predicates run on a new fixture
  `tests/fixtures/cargo/reference-depends-on-kernel.json` and must report the
  edge; a second fixture where the facade normal-depends on the reference must
  report that edge.
- OIB-3 check. Method: a test walks `crates/combobulate-reference/src` with
  `cap_std::fs_utf8` and rejects the listed tokens. Non-vacuity: the scan
  function is also run on an in-memory source string containing
  `include!("../x.rs")` and must reject it.
- OIB-4. Discharged by Rust privacy (AXIOM-2); the rustdoc of `Verdict`
  states it. No compile-fail fixture: it would test the compiler.
- H-1 (reference agrees with the golden cases). For all 75 cases,
  `ref(c) = exp(c)`, bit-exact. Method: one `rstest` case per golden case
  (`replays_contract_case`). Artefacts: `tests/semantic_examples.rs`,
  `tests/semantic_examples/replay.rs`. Command:
  `cargo nextest run --no-default-features --test semantic_examples`. Evidence:
  75 passing named cases in both gate profiles. Non-vacuity: each case asserts
  it decoded exactly one expectation kind; H-5 protects decoding; NC-1 and NC-5
  show judgements reject wrong values. Discharge: all 75 pass under `make test`.
- H-3 (completeness). The listed identifiers plus those of
  `PENDING_CONTRACTS` equal the file's identifiers, the two sets are disjoint,
  and there are no duplicates. `PENDING_CONTRACTS` lists contract families not
  yet ported during EP-M4 and is asserted empty at the end of EP-M4; pending
  cases are never counted as passing. Method: one `#[test]` over the `LISTED`
  constant. Non-vacuity: `completeness_reports_missing_and_extra` runs the
  comparison on a fixture list with one extra and one missing identifier and
  requires both diagnostics.
- H-4 (differential property: independence doing work). For generated pairs
  of I64 vectors, the production route's observation agrees with the reference,
  and every executed observation reports executor `native.sequential` and the
  SC-12 kernel. Method: `proptest` in
  `tests/semantic_examples/differential.rs`; generators biased to `i64::MIN`,
  `i64::MAX`, zero and small lengths, including unequal lengths. Non-vacuity: a
  classification tally asserts that success, shape refusal, overflow at
  position 0, at an interior position, at the last position, and a case with
  several overflowing positions are each reached at least once per run. The
  seeded control runs the same property against the wrapping mutant route with
  a fixed-seed `TestRunner` and requires a failure.
- H-5 (decoding is lossless). Every decoded case re-encodes to a value
  structurally equal to its source JSON, with tagged strings equal exactly.
  Error expectations parse with the strict grammar
  `^([A-Za-z]+)( at position ([0-9]+))?$`, and the code must be registered in
  `spec/semantic-contracts.json`. Non-vacuity: altering one digit of a wide I64
  in a fixture copy breaks the round trip, and an unregistered code or
  malformed position is rejected with the case identifier.
- RI-1 (route identity derived from the executed schedule). For every
  prepared plan, `route().executor()` equals the `id()` of the engine stored in
  the plan, and `route().kernels()` lists, in first-use order without
  duplicates, the kernel of each step. Method: unit tests in
  `src/plan/tests.rs`. Structure: `dispatch_add` stays a `const fn` calling the
  kernel function item directly; a `pub(super) const ADD_KERNEL: KernelId` sits
  beside it; one exhaustive
  `const fn kernel_of(step: &Step) -> Option<KernelId>` sits beside `run`'s
  match, so a new `Step` variant must update both. Non-vacuity: an input-only
  plan reports no kernels; a plan with two additions reports one kernel;
  `ADD_KERNEL.symbol()` must equal the `"symbol"` in
  `tools/verifier-fixtures/verus-kernel/provenance.json`, so the route report
  and the Verus record name the same body.
- RI-2 (the harness records the route the library reports). For every
  executed case the report entry's route is the value `plan.route()` returned
  for the plan that produced the observation; for every refused case the
  report's executor is `engine.id()` for the engine passed to `prepare`, and no
  kernel is listed. Method: the production adapter returns the route from the
  same `plan` value it executes.
- RI-3 (no self-comparison). The expected side of every comparison is a
  `Verdict` (OIB-4), so no comparison has a route on both sides.
- NC-1 (seeded wrong result fails for the intended reason). A mutant route
  that runs the real facade but, where the facade reports `IntegerOverflow`,
  returns the wrapping sums instead, fails exactly EX92 and EX93, each with
  `Judgement::ValueWhereErrorExpected` naming the expected position (1 and 0).
  A second mutant that adds one to the last element fails EX89 and EX91 with
  `Judgement::ValueMismatch` at the last position and passes EX90 (empty) and
  the error cases, which witnesses that the perturbation applies only where it
  can.
- NC-3 (route mismatch). A control adapter whose declared route differs from
  what its plan reports produces `Judgement::RouteMismatch` for every executed
  case, never a pass.
- NC-5 (always-`Err`). A route that returns
  `IntegerOverflow at position 0` for every case fails EX89, EX90 and EX91 with
  `Judgement::ErrorWhereValueExpected` (TDD-17b, V15).
- MUT-1 (a fault in the optimized body is caught by value). cargo-mutants
  mutates `crates/combobulate-kernel/src/elementwise_add.rs` and
  `src/plan/mod.rs` (`sum`, `dispatch_add`, `run`) and runs only the replay.
  Each caught mutant is classified as caught by judgement, by panic, or by
  timeout; only the first counts as "detected wrong result". Evidence: the
  cargo-mutants version, command, timeout, and classification table in
  `Artefacts and notes`. Each missed or unviable mutant is triaged with a
  reason. Recorded evidence, not a gate.
- SEED-1 (hand-seeded body fault). In a local, uncommitted edit, change the
  kernel to compute wrapping sums: the scan treats no position as overflowing,
  and the write loop uses `wrapping_add`. The replay must fail `case_72_ex92`
  and `case_73_ex93` with `ValueWhereErrorExpected`, not with a panic. Revert
  and confirm `git diff --exit-code crates/combobulate-kernel`. Recorded once
  as a `plaintext` transcript.
- FACADE-1' (absorbed oracle). FACADE-1's model computes pointwise sums with
  `combobulate_reference::elementwise_add`, whose failure type carries
  `lhs_len` and `rhs_len` so `Outcome::Shape` evidence is unchanged; the private
  `i128` helper is deleted. Non-vacuity: FACADE-1's existing classification
  counts still hold.
- PROFILE-1 (TDD-17c). The route report is profile-independent: it is
  rendered without profile data, and the same snapshot is asserted under both
  `native-only` and `polars-enabled` by `make test`, which is itself the
  evidence that enabling Polars does not change the route.

### Axioms (trusted, not verified here)

- AXIOM-1. `cargo metadata --format-version 1 --no-deps` reports every
  dependency declared by workspace manifests (Cargo documentation). OIB-1 and
  OIB-2 depend on it.
- AXIOM-2. Rust privacy: a struct with private fields and no public
  constructor cannot be built outside its crate (Rust Reference, "Visibility
  and privacy"). OIB-4 depends on it.
- AXIOM-3. `f64::to_bits` and `f64::from_bits` round-trip IEEE binary64 bit
  patterns, including NaN payloads, on the pinned toolchain and targets (`core`
  documentation). H-1 depends on it.
- AXIOM-4. `str::parse::<f64>` rounds decimals correctly, and `serde_json`
  delivers the tagged strings unchanged. H-5 checks the round trip
  independently.
- AXIOM-5. `std::panic::catch_unwind` observes panics in the facade and kernel
  in the test profile (`panic = "unwind"`, the default). The `Panicked`
  classification depends on it.
- AXIOM-6. `PreparedPlan::execute` reaches arithmetic only through `run`'s
  match, and `route()` iterates the same `steps`. RI-1's structure makes this
  reviewable and MUT-1 exercises it, but no machine check proves that `run` and
  `kernel_of` agree.

### Where formal verification is not warranted

Technical design §17.1 applies its machine-checked-evidence requirement when a
task changes "a semantic primitive, builder, rewrite, admission rule, or public
verification interface". This task changes none: it adds a test oracle, a
harness and a read-only route observation. Neither Verus nor Kani is selected.
The reference evaluator *is* the executable statement of the contracts for
testing; proving it would prove the specification against a second copy of
itself. Its correctness evidence is agreement with independently recorded
expectations (H-1). The independence boundary is a structural property of the
dependency graph and of Rust privacy, discharged by metadata checks and the
type system, not by a theorem. The route-identity API is plumbing over one
dispatch site. Kani has nothing to explore: no machine-width arithmetic or
bounded state space belongs to the harness. The kernel's arithmetic is already
verified by Verus under task 1.2.2 and is not modified; `make verus-kernel` is
run once at EP-M2 as a regression check, because the dispatch site gains a
neighbouring constant, but it is not a milestone gate.

### Relationship between tests and proofs

Verus establishes that `add_i64_into` meets SC-12 for all inputs. The replay
and the differential property establish that the *public route* reaching that
body, through the facade's schedule and error mapping, produces the contract's
outcomes, and that the route reported is the one the schedule uses. Neither
substitutes for the other: the proof does not cover the facade's plumbing, and
the tests cover only listed and generated cases.

## Plan of work

Six milestones. Each ends in a coherent state with all gates green. The
roadmap's success line is met at the end of EP-M3; EP-M4 completes the detail's
75-case replay.

### EP-M1: oracle independence boundary and golden-case reader

Assigned: OIB-1 to OIB-4, NC-4, H-5.

1. Red. In `tests/workspace_boundaries.rs`, add
   `reference_declares_no_dependency`,
   `only_the_root_dev_depends_on_reference`, the build-script check and the two
   fixture controls. Run `cargo nextest run --test workspace_boundaries`; they
   fail because the crate does not exist.
2. Green. Create `crates/combobulate-reference/` (`Cargo.toml` with
   `publish = false`, `[lints] workspace = true`, no dependency tables, no
   `build`; `src/lib.rs` with a `//!` statement of the boundary and the case
   schema types `Scalar`, `Operand`, `Operation`, `Case`, `Observed`, `Verdict`
   and `Judgement`). `evaluate` arrives in EP-M3. Add the crate to
   `default-members` and as a root dev-dependency by path. Generalize
   `kernel_dependency_names` into `dependency_names(metadata, package)`. Add
   the OIB-3 source scan and its control.
3. Add the decoder `tests/semantic_examples/decode.rs` and the round-trip
   encoder: read `spec/examples.json` with `cap_std` from
   `env!("CARGO_MANIFEST_DIR")`; decode tagged scalars; map each case to
   `combobulate_reference::Case`; reject unknown fields, unknown operations,
   both-or-neither expectations, and malformed error strings, naming the case.
   Add H-5's round trip and controls, and a test that all 75 cases decode.
4. Run `tests/workspace_profiles.rs` and `tests/build_profiles.rs`; edit only
   what fails, citing ADR-0013.

End state: the crate exists, is provably independent, and all 75 cases decode
losslessly. No replay rows yet: ignored or expected-failure rows are not
evidence and are not committed.

### EP-M2: route identity on prepared plans and engines

Assigned: RI-1.

1. Red. In `src/plan/tests.rs` add `route_names_the_sequential_engine`,
   `input_only_plan_reports_no_kernel`,
   `repeated_additions_report_one_distinct_kernel`, and
   `kernel_symbol_matches_the_verus_provenance_record`; add doctests on
   `PreparedPlan::route`, `NativeExecutor::id` and `ExecutorId::name`. They
   fail to compile.
2. Green. Add `src/plan/route.rs` with `ExecutorId`, `KernelId`, `Route` and
   their `Display` implementations (matching `OperationId`). Add `ADD_KERNEL`
   beside `dispatch_add` and `kernel_of` beside `run`. Re-export from
   `src/lib.rs`. Extend `tests/ordinary_application/surface.rs` with the new
   types (`Send`, `Sync`, non-generic names).
3. Run `make verus-kernel` once as a regression check.

### EP-M3: SC-12 vertical slice

Assigned: H-1 and H-3 for SC-12, RI-2, RI-3, NC-1, NC-3, NC-5, H-4, PROFILE-1,
SEED-1. This milestone meets the roadmap success line.

1. Red. Add `tests/semantic_examples.rs` (with `#[path]` submodules
   `decode`, `replay`, `route`, `report`, `controls`, `differential`, `bdd`)
   and write the controls first: NC-1, NC-3 and NC-5 assert specific case
   identifiers and judgement kinds, and fail because no harness exists.
2. Implement the reference's `evaluate` for SC-12 (`elementwise.rs`: `i128`
   widening, least failing position by `Iterator::position`, `RefFailure`
   carrying `lhs_len` and `rhs_len`, or `position`). For any other contract,
   `evaluate` returns a `Verdict` the replay treats as a test failure, never a
   pass; the replay does not list those cases yet.
3. Add `replay.rs` with the `macro_rules!` case list holding the SC-12 rows,
   `LISTED`, `PENDING_CONTRACTS` (every other family), and H-3.
4. Add `route.rs`: the `RouteUnderTest` trait (`declared() -> Declared`,
   `observe(&Case) -> Observation`), the `NativeSequential` adapter (maps
   `elementwise_add` onto `Array::from_i64`, `add().apply`, `prepare`, `route`,
   `execute`; maps `ExpressionError` to `Observed` by `code()` and fields, never
   `Display`; wraps the call in `catch_unwind`), and the mutant adapters used
   by the controls.
5. Add `report.rs`: one entry per case, sorted by identifier (`id`,
   `contract`, observation kind, executor, kernels, judgement), rendered as
   plain text and snapshotted (`insta` names it from the module path, for
   example `semantic_examples__report__route_report.snap`). Semantic assertions
   accompany it: the executed set is EX89 to EX93, the refused set is EX94 and
   EX95, and every executed entry names `native.sequential` and the SC-12
   kernel.
6. Add `differential.rs` (H-4) and the BDD feature and steps.
7. Record SEED-1.

#### Decision gate G1

After EP-M3, measure the tolerances. If code is above 1,800 net lines, or any
SC-12 obligation needed a design change, stop and report before EP-M4 with the
measurements and a revised estimate for the port.

### EP-M4: reference port of the remaining contract families

Assigned: H-1 and H-3 for SC-01 to SC-09 and SC-11. Three sub-milestones, each
a commit that removes its families from `PENDING_CONTRACTS` and adds their rows:

- M4a: `scalar.rs`, `arith.rs` (SC-03 `idiv`, `rem`; SC-04 `add`, `sub`,
  `mul`, `cast`; SC-05 `div`), `cast.rs`.
- M4b: `logic.rs` (SC-06 Kleene `and`, `or`, `xor`), `extremum.rs` (SC-07
  `min`, `max`, `minimum`, `maximum`, D09's NaN and signed-zero rules).
- M4c: `reduce.rs` (SC-01 right-associated `reduce`, `fold_left`; SC-02
  `sum`, `product`, `any`, `all`, empty and identity rules, null policy),
  `statistics.rs` (SC-11 `mean`, `mean_count`, `variance`, `stddev`, `ddof`),
  `structure.rs` (SC-08 `batch_axis`, SC-09 `atomic_commit` per D10). The last
  commit asserts `PENDING_CONTRACTS` is empty.

Red-Green per family: add the rows and watch them fail because `evaluate` does
not yet implement the family; implement from the contract text; watch them
pass. The production adapter returns `Unsupported` for these operations, so the
report gains "reference only" entries.

### EP-M5: FACADE-1 absorption, consumer fixture, mutation evidence

Assigned: FACADE-1', MUT-1, and public-consumer evidence for RI-1.

1. Change `tests/ordinary_application/refinement/model.rs` to use
   `combobulate_reference::elementwise_add` and delete its private helper.
2. Extend `tools/fixtures/native-consumer/src/bin/ordinary_application.rs` to
   print
   `route: native.sequential [combobulate_kernel::elementwise_add::add_i64_into]`
   through the public API and its `Display` implementations, and accept the
   updated `native_consumer_e2e__ordinary_application.snap`.
3. Run cargo-mutants (command in `Concrete steps`) and record MUT-1.

### EP-M6: documentation, ADR-0013, completion record, roadmap tick

1. Confirm the ADR number is free on `origin/main`. Write
   `docs/adrs/adr-0013-independent-reference-oracle-and-route-identity.md`
   (boundary, diversity rule, opaque verdict, public route observation,
   default-member change), add it to `docs/contents.md`, and add the ADR-0010
   amendment banner and section (DL-12).
2. Technical design §14: cite ADR-0013 for the evaluator and the route
   recording, and reword "The Python checks … are not that future evaluator"
   now that the evaluator exists.
3. `docs/users-guide.md`: a "Seeing which route ran" subsection with the
   `route()` example; update "Current limits".
4. `docs/developers-guide.md`: a `## Semantic-example replay` section (adding a
   golden case; how coverage grows when a route lands; the independence rules
   and the reuse policy for `combobulate-reference`: test-only, never a
   dependency of a shipped crate, extended by contract text and never by
   importing production code, never PF evidence; how to run MUT-1); the
   workspace prose ("holds four crates … None of the three") and table row; the
   Table 2 row (DL-3).
5. `docs/repository-layout.md`: the new crate and test binary.
6. `spec/task-completion.json`: a 1.2.3 entry with decisions
   `D06, D09, D10, D14, D15, D16` and artefacts
   `docs/adrs/adr-0013-independent-reference-oracle-and-route-identity.md`,
   `crates/combobulate-reference/Cargo.toml`,
   `crates/combobulate-reference/src/lib.rs`, `src/plan/route.rs`,
   `tests/semantic_examples.rs`, `tests/features/semantic_examples.feature`,
   `docs/developers-guide.md#semantic-example-replay`. Every path must resolve.
7. Tick task 1.2.3 only in `docs/roadmap.md`; its detail bullet stays `[ ]`
   because the exporter rejects ticked details. Regenerate and check:
   `uv run scripts/export_roadmap.py`, then
   `uv run scripts/export_roadmap.py --check`, then
   `uv run --python 3.14 scripts/check_docs.py --write --as-of "$(git log -1 --format=%cs)"`
   on the final tree.

## Milestones and plateaus

Every milestone is pre-1.0 and additive (ADR-0005); none needs compatibility
machinery. Each ends with `make check-fmt`, `make lint` and `make test`
passing, run in that order with `tee` logs, plus `make markdownlint` and
`make nixie` when Markdown changed and `make design-check` when `spec/` or
`docs/` changed.

- EP-M1. Requirements: TDD-14a (boundary half). End state: crate present,
  independent, cases decode losslessly. Acceptance: the boundary tests and
  their controls pass; `cargo nextest list --no-default-features` lists the
  `combobulate-reference` unit tests (evidence for DL-10). Conformance check:
  no shipped crate depends on the reference; no public API changed. Recovery:
  revert the milestone's commits; nothing else depends on them. Remaining gaps:
  no replay, no route.
- EP-M2. Requirements: TDD-14b (library half). End state: plans and engines
  report routes. Acceptance: the four unit tests and three doctests pass;
  `make verus-kernel` passes unchanged. Conformance check: only the approved
  public items were added; `dispatch_add` is still the single dispatch site.
  Recovery: revert; EP-M1 is unaffected. Remaining gaps: nothing consumes the
  route yet.
- EP-M3. Requirements: TDD-14a, TDD-14b, TDD-14c, TDD-17b and TDD-17c for
  SC-12. End state: the success line holds. Acceptance: SC-12 rows, NC-1, NC-3,
  NC-5, H-3 (with pending families), H-4 with its tally and seeded control, the
  BDD scenarios and the snapshot pass in both profiles; SEED-1 recorded.
  Conformance check: the reference SC-12 module uses no `checked_add`; the
  harness constructs no `Verdict`. Recovery: revert to EP-M2. Remaining gaps:
  68 cases pending; decision gate G1.
- EP-M4 (M4a, M4b, M4c). Requirements: D15's detail. End state after M4c: 75
  rows, `PENDING_CONTRACTS` empty. Acceptance per sub-milestone: its rows pass
  in both profiles. Conformance check: no reference module imports anything
  outside the crate; every float operation has an item-scoped expectation
  citing its contract. Recovery: each sub-milestone reverts independently.
  Remaining gaps: FACADE-1 still has its own oracle.
- EP-M5. Requirements: GAP-2 closure, V15 evidence. Acceptance: FACADE-1'
  classification unchanged; consumer snapshot updated; MUT-1 recorded.
  Recovery: revert; the replay is unaffected.
- EP-M6. Requirements: documentation and closure. Acceptance: all gates,
  including `make design-check` with `PYTHON` set to Python 3.14 and
  `export_roadmap.py --check`. Recovery: revert the documentation commit.

## Behavioural specification (BDD)

Path: `tests/features/semantic_examples.feature`, bound in
`tests/semantic_examples/bdd.rs`. Trace: RI-2, H-1; EP-M3. The harness's
negative controls stay as `rstest` tests; the scenarios describe the behaviour
a reader of the report relies on. Steps assert judgement and observation kinds,
not rendered text.

```gherkin
Feature: Replaying golden cases through an independent reference

  Scenario: An executed case reports the route that ran
    Given the golden case "EX89"
    When the case is replayed on the native sequential route
    Then the reference accepts the route's outcome
    And the report records an executed observation on executor "native.sequential"
    And the report names kernel "combobulate_kernel::elementwise_add::add_i64_into"

  Scenario: A shape disagreement is refused before any kernel is chosen
    Given the golden case "EX94"
    When the case is replayed on the native sequential route
    Then the reference accepts the route's outcome
    And the report records a refused observation on executor "native.sequential"
    And the report names no kernel

  Scenario: A case without a production route is reference only
    Given the golden case "EX21"
    When the case is replayed on the native sequential route
    Then the reference accepts the recorded expectation
    And the report records an unsupported observation
```

## Concrete steps

All commands run from the worktree root. Gate logs use `tee` with `pipefail` so
a failure is not masked:

```sh
set -o pipefail
B=1-2-3-independent-semantic-example-runner
make check-fmt 2>&1 | tee /tmp/check-fmt-combobulate-$B.out
make lint 2>&1 | tee /tmp/lint-combobulate-$B.out
make test 2>&1 | tee /tmp/test-combobulate-$B.out
```

Focused loop while developing:

```sh
cargo nextest run --no-default-features --test semantic_examples
cargo nextest run --no-default-features -p combobulate-reference
cargo nextest run --no-default-features --test workspace_boundaries
```

Mutation evidence (EP-M5), using cargo-mutants 27.1.0 options confirmed with
`cargo mutants --help`. Arguments after `--` go to the test tool:

```sh
set -o pipefail
cargo mutants --test-tool nextest --no-default-features \
  --file crates/combobulate-kernel/src/elementwise_add.rs \
  --file src/plan/mod.rs --test-package combobulate \
  -- --test semantic_examples \
  2>&1 | tee /tmp/mutants-combobulate-1-2-3-independent-semantic-example-runner.out
```

Expect a cold scratch build under the shared compile queue. Delete
`mutants.out*` afterwards; it is not committed.

## Validation and acceptance

Quality criteria:

- `make test` shows, in both profiles, 75 passing
  `replays_contract_case::case_NN_exNN` cases, the completeness test, the
  decoder round trip and its controls, NC-1, NC-3, NC-5, the differential
  property with its tally and seeded control, and the three BDD scenarios.
- `tests/workspace_boundaries.rs` shows the boundary checks and their fixture
  controls passing.
- The route-report snapshot lists EX89 to EX93 as executed on
  `native.sequential` with the SC-12 kernel, EX94 and EX95 as refused on
  `native.sequential` with no kernel, and the other 68 as reference only.
- The consumer fixture prints the route line.
- SEED-1 and MUT-1 are recorded in `Artefacts and notes`.
- `make check-fmt`, `make lint`, `make test`, `make markdownlint`,
  `make nixie` and `make design-check` pass; `export_roadmap.py --check` passes.

Quality method: the gates above in order, with `tee` logs; the snapshot is
reviewed once and accepted with `cargo insta review`; recorded runs are kept as
`plaintext` transcripts below.

## Idempotence and recovery

Every step is additive or rewrites a file this plan owns, and is safe to rerun.
If a milestone fails part-way, reset to the previous milestone's commit.
cargo-mutants works in a scratch copy and leaves the tree unchanged; if
interrupted, delete `mutants.out*`. SEED-1 is made and reverted within one
shell session and never committed;
`git diff --exit-code crates/combobulate-kernel` must succeed afterwards.

## Artefacts and notes

None yet. Red and Green transcripts, SEED-1 and the MUT-1 classification table
are recorded here as `plaintext` blocks as they are produced.

## Interfaces and dependencies

New public items in the facade (`src/plan/route.rs`, re-exported from
`src/lib.rs`). Every getter is `#[must_use]`:

```rust
/// Which engine prepared, refused or ran a plan.
#[non_exhaustive]
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ExecutorId { NativeSequential }
impl ExecutorId { pub const fn name(self) -> &'static str }  // "native.sequential"
impl Display for ExecutorId                                    // writes name()

/// One kernel body a plan's steps dispatch to.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct KernelId { /* operation: OperationId, symbol: &'static str */ }
impl KernelId {
    pub const fn operation(self) -> OperationId;
    pub const fn symbol(self) -> &'static str;
}
impl Display for KernelId                                      // writes symbol()

/// The route a prepared plan takes. E006 `.explain()` will add per-step detail.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Route { /* executor: ExecutorId, kernels: Box<[KernelId]> */ }
impl Route {
    pub const fn executor(&self) -> ExecutorId;
    pub fn kernels(&self) -> &[KernelId];
}
impl Display for Route                                         // "native.sequential [k1, …]"

impl NativeExecutor { pub const fn id(&self) -> ExecutorId }
impl PreparedPlan { pub fn route(&self) -> Route }
```

New test-only crate `combobulate-reference` (not shipped):

```rust
pub enum Scalar { Null, Bool(bool), I64(i64), F64(u64 /* bits */) }
pub enum Operand { /* scalar, vector, shape, cell, commit destination */ }
pub enum Operation { /* the 27 golden-case operations */ }
pub struct Case { /* id, contract, operation, operands, modifiers */ }
pub enum Observed { Value(Operand), Error { code: String, position: Option<usize> }, Panicked }
pub struct Verdict { /* private */ }
pub enum Judgement {
    Agrees, ValueMismatch { .. }, ErrorWhereValueExpected { .. },
    ValueWhereErrorExpected { .. }, ErrorMismatch { .. }, Panicked, RouteMismatch { .. },
}
pub fn evaluate(case: &Case) -> Verdict;
impl Verdict { pub fn judge(&self, observed: &Observed) -> Judgement; }
pub enum RefFailure { Shape { lhs_len: usize, rhs_len: usize }, Overflow { position: usize } }
pub fn elementwise_add(lhs: &[i64], rhs: &[i64]) -> Result<Vec<i64>, RefFailure>;
```

`Judgement::RouteMismatch` is produced by the harness's route comparison, not by
`judge`; it lives in the shared type so the report has one vocabulary.

Dependencies: none added. The root gains a path dev-dependency on
`crates/combobulate-reference`, which also joins `default-members`.

## Revision note

- 2026-11-28: initial draft from Wyvern reconnaissance.
- 2026-11-28: expert review applied (three reviewers). Changes: EX94 and EX95
  are modelled as refusals, with `NativeExecutor::id()` kept public to name
  their engine; corrected EX93's position, NC-1's failing set and the NaN
  witnesses; added panic classification (the test profile checks overflow);
  added the decoder round trip (H-5), the differential property (H-4), the
  always-`Err` control (NC-5) and the single-failure rule; tightened OIB-1 and
  OIB-3 and added the diversity rule; moved boundary checks into
  `tests/workspace_boundaries.rs` (nested-Cargo controls); added the reference
  crate to `default-members`; added the reference lint policy; corrected rstest
  case names; dropped the reference-side mutation table (formerly H-2) and the
  shared-body control (formerly NC-2); reordered milestones so the SC-12 slice
  meets the success line before the port, with decision gate G1 and
  `PENDING_CONTRACTS`; derived route identity from the schedule with an
  exhaustive `kernel_of` and the Verus provenance symbol; corrected decision
  citations and completion mechanics (task tick only, generated
  `spec/roadmap.json`, Python 3.14); added the ADR-0010 amendment, the
  Milestones and plateaus section, per-category counting, and Architecture and
  Time tolerances; raised the code budget to 4,400 and files to 55. Remaining
  work is unchanged in purpose; implementation awaits approval.
