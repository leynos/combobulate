# Introduce the independent semantic-example runner and route-identifying harness

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: DRAFT (awaiting expert review and user approval).

Roadmap task: 1.2.3 in `docs/roadmap.md`. Branch:
`1-2-3-independent-semantic-example-runner`, cut from `main` at `bacad37`.

Implementation must not begin until the user explicitly approves this plan.

## Purpose / big picture

Combobulate is a Rust library for inspectable array algebra. Task 1.2.2 gave it
its first runnable public path: a caller builds an I64 vector with
`Array::from_i64`, applies `identity()` or `add()`, prepares the expression with
`NativeExecutor::sequential()`, and executes it. The arithmetic body that path
runs is `add_i64_into` in the `combobulate-kernel` crate, verified by Verus
against the SC-12 semantic contract.

The project also keeps a set of golden examples. `spec/examples.json` holds 75
`contract_cases` (EX21 to EX95), each a small tagged-scalar input, an
operation, and either an expected value or an expected error code. Each case
belongs to one semantic contract (SC-01 to SC-12, except SC-10) in
`spec/semantic-contracts.json`. Today only a Python documentation model,
`scripts/docs_validation/contract_examples.py`, evaluates these cases. No Rust
code reads them, so nothing shows that the Rust library meets the expectations
the documentation records.

The technical design (§14) requires "an independent scalar reference evaluator
for the core logical semantics" that "must not share optimized indexing or
accumulation implementations with the routes it checks", and a test runner that
"records selected execution routes so differential tests cannot accidentally
compare the same fallback against itself". This task delivers both, in their
smallest useful form.

Terms used throughout:

- *Golden case*: one entry of `contract_cases` in `spec/examples.json`. The
  roadmap's "golden-case contract" is that list together with the tagged-scalar
  encoding its `scalar_encoding` field describes.
- *Reference evaluator* (or *oracle*): a Rust function that computes what a
  golden case means from the semantic contracts alone. It lives in a new
  test-only crate, `combobulate-reference`, that cannot see the production
  crates.
- *Route*: the production path that executes an expression: which executor
  ran the plan and which kernel body each arithmetic step dispatched to.
- *Route identity*: the value a prepared plan reports naming its route, for
  example executor `native.sequential` with kernel
  `combobulate_kernel::elementwise_add::add_i64_into`.
- *Seeded wrong-result mutation*: a deliberately wrong implementation, such as
  an addition that wraps on overflow instead of reporting `IntegerOverflow`,
  used to prove the harness notices wrong answers.
- *Oracle independence boundary*: the stated, machine-checked rule that the
  reference evaluator shares no execution code with any production route.

After this change, a contributor runs:

```sh
cargo nextest run --test semantic_examples --no-default-features
```

and sees 75 named replay cases (`replays_contract_case::case_ex21` through
`case_ex95`), each passing against the reference evaluator, and a route report
naming, for each case, either the production route that also executed it or the
fact that no production route exists yet. The seven SC-12 cases (EX89 to EX95)
run through the public facade, report executor `native.sequential` and kernel
`combobulate_kernel::elementwise_add::add_i64_into`, and agree with the
reference. Negative-control tests show that a route seeded with wrapping
addition fails replay on EX92 and EX93 for the intended reason, and that the
reference crate's dependency closure contains no production crate.

A downstream caller gains one small public observation:

```rust
use combobulate::{Array, ExecutorId, NativeExecutor, add};

let xs = Array::from_i64(vec![1, 2, 3]).expr();
let plan = add().apply(&xs, &xs).prepare(&NativeExecutor::sequential())?;
let route = plan.route();
assert_eq!(route.executor(), ExecutorId::NativeSequential, "one engine today");
assert_eq!(route.executor().name(), "native.sequential", "stable label");
assert_eq!(
    route.kernels().iter().map(|k| k.symbol()).collect::<Vec<_>>(),
    ["combobulate_kernel::elementwise_add::add_i64_into"],
    "an addition step names the verified kernel it dispatches to",
);
# Ok::<(), combobulate::ExpressionError>(())
```

Existing behaviour is preserved: no operation, error, or diagnostic of the
1.2.2 path changes. The Python documentation model stays (see DL-3).

This task closes roadmap item 1.2.3 and its sub-item "Replay the semantic
contract examples (`contract_cases` in `spec/examples.json`) as `rstest`
cases". It absorbs the independent oracle that task 1.2.2's FACADE-1 property
deliberately left in place for this task (1.2.2 plan, "Facade obligations").

## Constraints

- The kernel crate `crates/combobulate-kernel` is not modified. Its Verus
  proofs, seeded Verus mutants, and zero-dependency rule (VO-1 in
  `tests/workspace_boundaries.rs`) stay as they are.
- The new crate `crates/combobulate-reference` has no dependencies of any kind
  (normal, build, or dev), is `publish = false`, and is a dev-dependency of the
  root package only. No shipped crate may depend on it. This is the oracle
  independence boundary (OIB-1, OIB-2); it is not negotiable within this plan.
- The reference evaluator must not call, include (`#[path]`, `include!`), copy
  by macro, or otherwise reuse any function body from `src/` or
  `crates/combobulate-kernel/`. Shared *type and schema* definitions are
  permitted (technical design §14); in this plan the reference crate owns the
  shared case schema, so the dependency direction runs from the harness to the
  reference, never the reverse.
- Proof features must not substitute a route. No `cfg(test)`, `cfg(kani)`, or
  feature flag may change which kernel the production route dispatches to
  (technical design §17.7). The route report must describe the code that
  actually ran.
- Public API changes are limited to the items listed in
  `Interfaces and dependencies` (`ExecutorId`, `KernelId`, `Route`,
  `PreparedPlan::route`, `NativeExecutor::id`). They are additive and pre-1.0
  (ADR-0005); no compatibility machinery is introduced.
- Ordinary consumers stay verifier-free and backend-free:
  `tests/workspace_profiles.rs` must continue to pass for `native-only` and
  `polars-enabled`.
- Repository rules apply in full (`AGENTS.md`): files under 400 lines; `//!`
  module comments on every module including tests; every assertion carries a
  message; no `unwrap`/`expect` outside tests; `cap_std`/`camino` for file
  access; no `std::env::var`; item-scoped `#[expect(..., reason = ...)]` only;
  en-GB-oxendict spelling.
- Dependencies: no new third-party crate. `serde_json`, `rstest`,
  `rstest-bdd`, `googletest`, `pretty_assertions`, `insta`, `proptest`,
  `camino` and `cap-std` are already root dev-dependencies. `cargo-mutants`
  27.1.0 is already installed on the host and is used only as an out-of-gate
  evidence tool.
- The completed ExecPlans under `docs/execplans/` (1.1, 1.2.1, 1.2.2) are
  historical and are not edited.
- `docs/validation-results.json` and `typos.toml` are regenerated, never
  hand-edited.
- Implementation begins only after the user approves this plan.

## Tolerances (exception triggers)

This ExecPlan file is excluded from every count. Generated or captured files
are also excluded: `Cargo.lock`, `docs/validation-results.json`, `typos.toml`,
and `insta` snapshot files under `tests/snapshots/`.

Comparison base: `origin/main` at the merge base of this branch. Counting
command (net lines = additions minus deletions, per category):

```sh
git diff --numstat "$(git merge-base origin/main HEAD)" -- . \
  ':(exclude)docs/execplans/1-2-3-independent-semantic-example-runner.md' \
  ':(exclude)Cargo.lock' ':(exclude)docs/validation-results.json' \
  ':(exclude)typos.toml' ':(exclude)tests/snapshots/**'
```

Classification, by whole file:

- Code: `*.rs` anywhere, `scripts/**/*.py`, `Makefile`.
- Configuration: `Cargo.toml` files, `.config/**`, `.github/**`,
  `spec/**/*.json` other than the generated report.
- Documentation: `docs/**/*.md` (except this plan), `README.md`,
  `tests/features/*.feature`.

Survey behind the budgets. The Python documentation model this task mirrors is
366 lines (`contract_examples.py`) plus 91 (`elementwise_examples.py`) and 45
(`scalar_codec.py`) over 27 operations. A Rust port with module comments,
rustdoc examples, typed values and unit tests is estimated at 1,300 to 1,600
lines across about ten modules of the reference crate. The harness (decoder,
route adapter, report, replay table, controls, BDD steps) is estimated at 900
to 1,100 lines. The route-identity API with its tests is about 250 lines.
Absorbing FACADE-1's oracle and extending the consumer fixture is about 100.
That is roughly 2,600 to 3,050 code lines.

History. Task 1.2.2 set 60 files and 4,500 net lines (code and documentation
combined) and finished at 94 files and 10,057 lines; the maintainer granted a
20,000-line expansion on 2026-11-25. The 1.2.2 record attributes the overrun to
one-file-per-responsibility toolchain structure, second-round review repairs (a
diagnostic reader, its tests, a compile-contract fixture), and record
reconciliation. Those causes recur here (review rounds, file granularity), so
the budgets below carry a 30% contingency over the upper estimate and the
milestones are smaller.

- Files: escalate if more than 45 non-ExecPlan files change.
- Code: escalate above 4,000 net lines.
- Configuration: escalate above 150 net lines.
- Documentation: escalate above 900 net lines.
- Interface: escalate if a public item beyond those in
  `Interfaces and dependencies` is needed, or if an approved signature must
  change shape (renamed type, different return type, added type parameter).
  Adding `#[must_use]`, `const`, or `#[non_exhaustive]` is not a shape change.
- Dependencies: escalate before adding any crate to any manifest, including
  adding an existing workspace crate as a dependency of the reference crate.
- Governance: these validator-facing edits are pre-approved: a 1.2.3 entry in
  `spec/task-completion.json`; the `docs/developers-guide.md` Table 2 row for
  `contract_examples.py`; the ADR-0013 entry in `docs/contents.md`; ticking
  1.2.3 in `docs/roadmap.md` and `spec/roadmap.json`. Any change to
  `scripts/docs_validation/` needs escalation.
- Iterations: escalate if a gate still fails after three fix attempts on the
  same cause.
- Semantics: escalate if the Rust reference and the recorded expectation in
  `spec/examples.json` disagree on any case after the reference has been
  checked against the contract text. A disagreement is a specification
  question, not a test to adjust.
- Ambiguity: escalate when two materially different readings of a contract or
  requirement appear.

## Risks

- Risk: the Rust reference reproduces a Python modelling choice that the
  contract text does not actually state (for example two-pass variance
  rounding, or cast boundary handling), so both models agree with each other
  but not with the contract. Severity: medium. Likelihood: medium. Mitigation:
  write each reference module from `spec/semantic-contracts.json` and ADR-0006
  first, reading the Python only to resolve encoding questions; record each
  place the contract text was insufficient in `Surprises & discoveries` and
  escalate per the Semantics tolerance.
- Risk: F64 semantics (signed zero, NaN payloads, `-0.0` casts, overflow to
  infinity) are compared by value instead of by bit pattern, hiding a defect.
  Severity: high. Likelihood: medium. Mitigation: the comparison compares F64 by
  `to_bits()`, with an explicit NaN-class rule only where a contract says any
  NaN is acceptable; EX42, EX60 and EX63 are the witnesses.
- Risk: the `scalar_encoding` prose says "null is invalid", yet cases use JSON
  `null` as a valid nullable value (EX11, EX51 to EX58, EX63, EX78). Severity:
  low. Likelihood: high. Mitigation: decode `null` as the invalid (null) cell
  of a nullable value, which is what the cases mean; record the wording issue
  as a discovery and propose a prose fix in the developers' guide rather than
  editing `spec/examples.json`.
- Risk: the route-identity API grows into a premature `.explain()` (E006).
  Severity: medium. Likelihood: low. Mitigation: the API reports only the
  executor and the kernel bindings of the steps; anything else waits for 2.3.3
  and 4.3.1. The Interface tolerance enforces the limit.
- Risk: cargo-mutants spends a long time or reports mutants the replay cannot
  see (for example in `const` evaluation paths). Severity: low. Likelihood:
  medium. Mitigation: the run is scoped to one file and is evidence, not a
  gate; any surviving mutant is triaged in `Surprises & discoveries`, and
  equivalent mutants are named with a reason.
- Risk: 75 hand-listed `#[case]` rows drift from `spec/examples.json`.
  Severity: medium. Likelihood: medium. Mitigation: a completeness test (H-3)
  compares the listed identifiers with the file in both directions.
- Risk: adding a fourth workspace crate trips workspace-shape tests
  (`tests/workspace_boundaries.rs`, `tests/workspace_profiles.rs`,
  `tests/build_profiles.rs`). Severity: medium. Likelihood: medium. Mitigation:
  EP-M1 runs those suites first and updates the expected crate sets with a
  reason; ADR-0013 records the crate.

## Progress

- [x] (2026-11-28) Branch renamed to
  `1-2-3-independent-semantic-example-runner`; reconnaissance by a Wyvern team
  over code, specifications, traceability, and gates.
- [x] (2026-11-28) Initial draft written.
- [ ] Expert review applied.
- [ ] Plan approved by the user.
- [ ] `EP-M1` Oracle independence boundary and golden-case reader.
- [ ] `EP-M2` Reference evaluator replays all 75 golden cases.
- [ ] `EP-M3` Route identity on prepared plans.
- [ ] `EP-M4` Route-identifying harness, production replay, negative controls.
- [ ] `EP-M5` FACADE-1 absorption, consumer fixture, mutation evidence.
- [ ] `EP-M6` Documentation, ADR-0013, completion record, roadmap tick.

## Surprises & discoveries

- Observation: the roadmap's "golden-case contract" has no other definition in
  the repository. Evidence: no occurrence of "golden case" in `docs/` or
  `spec/`. Impact: this plan defines it as `contract_cases` plus
  `scalar_encoding` (Purpose).
- Observation: no Rust code reads `spec/examples.json`; one test reads
  `spec/semantic-contracts.json` (`tests/ordinary_application/diagnostics.rs`
  around line 92, via `cap_std`). Impact: that test is the precedent for file
  access.
- Observation: of 75 golden cases, only the seven SC-12 cases (EX89 to EX95)
  are expressible through the public API. EX47 (`add`) mixes I64 and F64, and
  F64 does not exist yet. Impact: the remaining 68 cases replay against the
  reference only and are reported as having no production route.
- Observation: `scalar_encoding` says "null is invalid" while cases use `null`
  as a valid nullable cell. Impact: see Risks.
- Observation: `combobulate-test-macros` is a precedent for a
  `publish = false`, test-only crate under `crates/`
  (`docs/developers-guide.md` around line 650). Impact: the reference crate
  follows that precedent.

## Decision log

- DL-1. Decision: the reference evaluator is a separate zero-dependency crate,
  `crates/combobulate-reference`, consumed only as a root dev-dependency.
  Rationale: a crate boundary makes the independence rule a compiler fact (the
  crate cannot name `combobulate` or `combobulate_kernel`) and a checkable
  metadata fact (OIB-2), rather than a review convention. The strongest
  alternative, a module under `tests/` like FACADE-1's `refinement/model.rs`,
  can import the facade at any time and only a source scan could notice.
  Status: proposed; requires approval because it adds a workspace member
  (ADR-0013 records it).
- DL-2. Decision: the reference covers every operation the 75 golden cases
  use (27 operations), not only the one with a production route. Rationale: the
  roadmap sub-item asks for the `contract_cases` to be replayed as `rstest`
  cases; the technical design asks for a reference evaluator of the core
  logical semantics; and later tasks (2.1.x, 2.2.x, 2.3.5) need an oracle to
  differentially test their routes against. Alternative B, a reference for
  SC-12 only with the other 68 cases listed as "unreplayed", would satisfy the
  success line but leave the sub-item mostly undone. Status: proposed; requires
  approval because it sets the code budget.
- DL-3. Decision: `scripts/docs_validation/contract_examples.py` stays as the
  documentation model run by `make design-check`. The Rust replay becomes the
  implementation-conformance check. Table 2 of `docs/developers-guide.md` is
  reworded from "Superseded by `rstest` replay in task 1.2.3" to say the Rust
  replay owns implementation conformance while the Python model keeps the
  design-time mutation check. Rationale: `semantic_contracts.py` imports
  `outcome` from it to prove each contract's seeded mutation changes an example,
  `design.yml` runs without a Rust toolchain, and the roadmap schedules no
  deletion for this task (contrast 2.3.1, which deletes `grammar.py`).
  Alternative: port the mutation check into Rust and delete the Python model;
  that changes the governance validators and is out of this task's scope.
  Status: proposed; requires approval.
- DL-4. Decision: route identity becomes a small public observation,
  `PreparedPlan::route()`, rather than a test-only hook. Rationale: the harness
  must *observe* the route from the code that ran; a label the harness writes
  itself cannot catch a substitute executor (V15) or a fallback compared with
  itself (§14). A `#[doc(hidden)]` or `cfg(test)` seam would be a proof-only
  path, which §17.7 forbids. The API is a strict subset of what E006
  `.explain()` will later report ("selected engine"). Status: proposed;
  requires approval as a public API addition.
- DL-5. Decision: each golden case is an explicit
  `#[case::exNN("EXNN")]` row on one `rstest` function, plus a two-way
  completeness test, instead of a procedural macro that reads the JSON at
  expansion time. Rationale: explicit rows give per-case names in nextest
  output with no build-time file reads, no environment access in a procedural
  macro, and no rebuild-tracking hazard; the completeness test catches drift
  either way, the same pattern D15 prescribes for 2.3.1.
- DL-6. Decision: expected outcomes have an opaque type,
  `combobulate_reference::Verdict`, with no public constructor; only
  `combobulate_reference::evaluate` produces one. Rationale: the harness then
  cannot build an "expected" value from a route's own output, so a shared
  faulty body cannot become the oracle by accident. Comparison happens through
  `Verdict::judge(&Observed) -> Judgement`.
- DL-7. Decision: Verus and Kani are not used in this task. See
  `Verification plan`, "Where formal verification is not warranted".
- DL-8. Decision: the permanent seeded-fault controls are harness-level
  mutant routes; a real mutation of the shipped kernel body is exercised with
  `cargo-mutants` once, as recorded evidence. Rationale: a permanent control
  must run in `make test` without editing production code; the cargo-mutants
  run shows the replay detects a fault *inside the optimized body*, which a
  wrapper alone cannot show.

## Outcomes & retrospective

Not started.

## Context and orientation

Repository layout relevant to this task:

- `Cargo.toml` (root): the facade package `combobulate` and the workspace
  (`members = ["crates/*"]`, `exclude = ["tools"]`). Root dev-dependencies at
  lines 44 to 66. Workspace lints at lines 68 to 151 deny `missing_docs`,
  `missing_docs_in_private_items`, `unwrap_used`, `expect_used`,
  `indexing_slicing`, `allow_attributes`, `missing_assert_message`, and
  printing to stdout or stderr.
- `src/plan/mod.rs`: `NativeExecutor` (the only engine; `sequential()`),
  `PreparedPlan` (`execute()`), the private `Step` enum (`Input`, `Add`), and
  the private `dispatch_add`, "the facade's only route to an arithmetic body
  (DL-14 of 1.2.2)", which calls
  `combobulate_kernel::elementwise_add::add_i64_into`.
  `src/plan/tests.rs::the_dispatch_route_is_the_verified_kernel` already pins
  that dispatch.
- `src/expr/mod.rs`: `AExpr`, `Unary`, `Binary`, `OperationId` (`name()`,
  `catalogue_id()`), `identity()`, `add()`.
- `src/error/mod.rs`: `ExpressionError` (`stage()`, `failures()`), `Failure`
  (`ShapeAgreement`, `IntegerOverflow { operation, position }`, `code()`),
  `Stage`.
- `crates/combobulate-kernel/src/elementwise_add.rs`: `add_i64_into`, the
  optimized and Verus-verified body.
- `crates/combobulate-test-macros/`: precedent for a test-only workspace crate.
- `spec/examples.json`: `contract_cases` (75 entries, EX21 to EX95) and
  `scalar_encoding`. Fields per case: always `id`, `contract`, `operation`;
  exactly one of `expected` or `expected_error`; operands in `input`, `args`,
  `cell`, `shape`, `axis`, `count`, `destination`, `output`, `fail_at`;
  modifiers `binary`, `dtype`, `identity`, `skip_nulls`, `ddof`, `to`.
  `expected_error` is usually a code (`"IntegerOverflow"`) but EX92 and EX93
  carry a position (`"IntegerOverflow at position 1"`).
- `spec/semantic-contracts.json`: SC-01 to SC-12 with `examples`,
  `seeded_mutations`, `error_codes` (17 registered), and `discharged_by` (SC-12
  is `task:1.2.2` and `PF05.proof@2.3.5`).
- `scripts/docs_validation/contract_examples.py`: the Python documentation
  model; `elementwise_examples.py` and `scalar_codec.py` beside it.
- `tests/ordinary_application.rs` and `tests/ordinary_application/`: the 1.2.2
  facade tests; `refinement/` is FACADE-1's proptest refinement against an
  `i128` memoizing oracle.
- `tests/workspace_boundaries.rs` with `tests/support/` cargo helpers
  (`cargo::live_metadata()`, `cargo::metadata::*`, fixtures under
  `tests/fixtures/cargo/`): the precedent for dependency-graph assertions.
- `tools/fixtures/native-consumer/`: an out-of-workspace consumer whose
  `src/bin/ordinary_application.rs` output is snapshotted by
  `tests/native_consumer_e2e.rs`.
- `tests/features/` and `rstest-bdd` 0.6: BDD scenarios; see
  `tests/build_profiles.rs` for the step-binding style.

Gates (from `Makefile`): `make check-fmt`, `make lint` (Clippy, Whitaker,
interrogate, per profile), `make test` (nextest per profile then doctests),
`make markdownlint` (also runs `make spelling`), `make nixie`, and
`make design-check` (`check_docs.py`, Python unit tests). `GATE_PROFILE`
defaults to `both` (`native-only` and `polars-enabled`).

Documents and skills to keep open while implementing:

- `docs/technical-design.md` §14 (independent evaluator, route recording) and
  §17 (proof-first, §17.7 no proof-only substitution).
- `docs/adrs/adr-0006-numeric-validity-and-reduction-contracts.md` (the
  numeric rules the reference implements).
- `docs/adrs/adr-0010-workspace-crate-boundaries-and-build-profiles.md` and
  `docs/adrs/adr-0012-minimal-value-and-expression-representation.md`.
- `docs/developers-guide.md` (testing, nextest warm-up, governance Table 2,
  task completion).
- `docs/rust-testing-with-rstest-fixtures.md`, `docs/rstest-bdd-users-guide.md`,
  `docs/reliable-testing-in-rust-via-dependency-injection.md`,
  `docs/rust-doctest-dry-guide.md`,
  `docs/complexity-antipatterns-and-refactoring-strategies.md`.
- Skills: `rust-router` then `rust-unit-testing` (rstest tables, googletest,
  insta), `rust-types-and-apis` (the route API), `arch-crate-design` (the new
  crate), `proptest`, `nextest`, `arch-decision-records` (ADR-0013),
  `en-gb-oxendict`.

## Conformance basis

- Terms of reference: `docs/terms-of-reference.md` §6.1 goals G1, G2, G6, G7,
  G8 (revision as of `bacad37`). This task serves G2 ("a predictable meaning
  across supported execution routes") and G7 (proof-first delivery) directly,
  and G6 by reusing existing tooling.
- Technical design: `docs/technical-design.md` at `bacad37`, §14 (independent
  scalar reference evaluator; route recording; negative controls must fail for
  the intended reason) and §17 (§17.1 discipline, §17.2 success witnesses,
  §17.7 no proof-only route substitution).
- Bets: B01 (`docs/testable-bets.md`; `spec/bets.json` lists task 1.2.3).
- Decisions: D15 (replay the semantic examples as `rstest` cases in 1.2.3),
  D06, D07 (numeric and validity contracts), D16 (as used by 1.2.2).
- ADRs: ADR-0005 (pre-1.0 API policy), ADR-0006, ADR-0009 (evidence gate),
  ADR-0010 (crate boundaries; amended in effect by ADR-0013), ADR-0012.
- Verification obligations touched: V5 (force actual routes against an
  independent model), V14 (evidence binds to actual executable identities), V15
  (substitute-executor mutations fail). No PF component is assigned to 1.2.3 in
  `spec/proof-obligations.json`, and none is added.

Trace links:

```plaintext
TOR G2 -> TDD §14 independent evaluator -> OIB-1..OIB-3 -> EP-M1, EP-M2
    -> tests::semantic_examples::replays_contract_case, independence::*
TOR G2 -> TDD §14 route recording -> RI-1..RI-3 -> EP-M3, EP-M4
    -> plan::tests::route_names_*, semantic_examples::routes::*
TOR G7 -> TDD §17.2 negative controls -> NC-1..NC-4 -> EP-M4, EP-M5
    -> semantic_examples::controls::*, cargo-mutants record
D15 -> roadmap 1.2.3 sub-item -> H-1..H-3 -> EP-M2, EP-M4
```

## Verification plan

### Abstract model, stated first

A golden case `c` has an operation `op(c)`, operands `in(c)`, and a recorded
expectation `exp(c)`, which is either `Value(v)` or `Error(code, pos?)`.
Scalars are `Null | Bool(b) | I64(n) | F64(bits)`; F64 equality is bit equality.

The reference denotation `ref(c, M)` is the meaning the semantic contracts
assign to `op(c)` on `in(c)` under a set `M` of seeded mutations, with
`ref(c, ∅)` the unmutated meaning. A route `r` is a function from a case to an
observation `obs(r, c)`, which is `Unsupported` or `Ran(id, outcome)` where
`id` is the route identity reported by the production plan.

The harness verdict for a case is:

```plaintext
ref_ok(c)        iff ref(c, ∅) = exp(c)
route_ok(r, c)   iff obs(r, c) = Unsupported
                     or (obs(r, c) = Ran(id, o) and id = declared(r) and o = exp(c))
passes(c)        iff ref_ok(c) and route_ok(production, c)
covered(c)       iff obs(production, c) = Ran(_, _)
```

`Unsupported` is never reported as a pass on a route; the report lists it as
"reference only". The suite passes iff every listed case passes, the listed set
equals the file's set, and the covered set equals the declared coverage set
(today the SC-12 examples).

### Oracle independence boundary (stated before any evaluator code)

- OIB-1. The reference crate's dependency closure, over normal, build and dev
  edges and every target, contains no workspace package other than itself.
- OIB-2. No shipped package (facade, kernel, macros) has the reference crate
  in its normal or build closure; it is a dev-dependency of the root only.
- OIB-3. The reference crate's sources contain no `#[path]`, `include!`,
  `include_str!` or `include_bytes!` that names a file outside the crate
  directory.
- OIB-4. An expected outcome (`Verdict`) can only be produced by
  `combobulate_reference::evaluate`; the type has private fields and no public
  constructor or `From` conversion.

What OIB-1 to OIB-4 establish together: a fault in the optimized body
(`add_i64_into`, the facade schedule, or any later route) cannot also appear in
the expected value, because the code computing the expected value cannot reach
that body by call, by inclusion, or by construction of the expected value from
a route's output. What they do not establish: that the reference is *correct*.
Correctness of the reference against the contract is H-1, checked against the
independently recorded expectations in `spec/examples.json`, and cross-checked
by a second independent model (the Python documentation model, DL-3).

### Obligations

- H-1 (reference agrees with the golden cases). For all 75 cases,
  `ref(c, ∅) = exp(c)`. Method: one `rstest` case per golden case
  (`replays_contract_case`). Artefact: `tests/semantic_examples.rs`,
  `tests/semantic_examples/replay.rs`. Command:
  `cargo nextest run --test semantic_examples`. Evidence: 75 passing named
  cases. Non-vacuity: H-2 below; the decoded case count is asserted to be 75,
  and each case asserts it decoded a non-empty operation and exactly one
  expectation kind. Discharge: all 75 pass under both gate profiles.
- H-2 (each contract's seeded mutation is visible). For every contract `k`
  with cases and every seeded mutation `m` in `spec/semantic-contracts.json` for
  `k`, some case `c` of `k` has `ref(c, {m}) ≠ exp(c)`. Method: `rstest` table
  over the 13 seeded mutation identifiers (SC-10's `right-associative-pipe`
  excluded with a stated reason: SC-10 has no `contract_cases`; its corpus is
  `spec/macro-grammar.json`, owned by 2.3.1). Artefact:
  `tests/semantic_examples/mutations.rs`; the reference crate's `mutation`
  module. Non-vacuity: each row names the case identifier expected to change,
  so a mutation that changes an unrelated case still fails the row; and an
  unknown mutation identifier is a decoding error, not a silent no-op.
  Discharge: every row passes and the table's identifier set equals the file's.
- H-3 (completeness). The `#[case]` identifiers equal the `contract_cases`
  identifiers, in both directions, with no duplicates. Method: one
  `macro_rules!` list in `replay.rs` expands to both the `rstest` rows
  (`#[case::$name($id)]`) and a `LISTED: &[&str]` constant, so the rows and the
  constant cannot differ; one `#[test]` compares `LISTED` with the file's
  identifiers. Whether `rstest` 0.27 accepts a case name supplied through a
  macro metavariable is checked first in EP-M2; if it does not, the rows are
  written out and a second test compares the rows' generated test names, read
  from `LISTED`, by count. Non-vacuity: the comparison function is also run on
  a fixture list with one extra and one missing identifier and must report both
  (`completeness_reports_missing_and_extra`).
- RI-1 (route identity is observed, not asserted). For every prepared plan,
  `route().executor()` equals the `ExecutorId` of the engine the plan was
  prepared with and stores, and `route().kernels()` lists, in schedule order
  and without duplicates, the `KernelId` of each distinct kernel the plan's
  steps dispatch to. Method: unit tests in `src/plan/tests.rs`; the `KernelId`
  for addition is defined beside `dispatch_add` in the same `const` dispatch
  entry whose function pointer `run` calls, so the label and the call cannot
  name different functions. Non-vacuity: an input-only plan reports no kernels;
  a plan with two additions reports one kernel (distinct), and a test asserts
  `core::any::type_name_of_val(&add_i64_into)` ends with the reported symbol
  path, so renaming the kernel without updating the label fails.
- RI-2 (the harness records the route that ran). For every covered case, the
  report entry's route identity is the value `plan.route()` returned for the
  plan that produced the observation. Method: the production adapter returns
  the route from the same `plan` value it executes. A control route whose plan
  reports executor `native.sequential` but whose adapter declares a different
  expected route produces `RouteMismatch` (NC-3).
- RI-3 (no self-comparison). The expected side of every comparison is a
  `Verdict` (OIB-4), so no comparison has a route on both sides.
- NC-1 (seeded wrong result fails, intended reason). A mutant route that
  executes the real facade but substitutes wrapping addition for overflow
  failures fails exactly EX92 and EX93, each with `ValueWhereErrorExpected`
  naming the expected `IntegerOverflow` position; a second mutant that perturbs
  the last element by one fails EX89, EX91 and EX95 with `ValueMismatch` at the
  last position, and passes the empty case EX90 (the witness that the
  perturbation is applied only where it can be).
- NC-2 (shared body is blind). A deliberately dependent "oracle" built from the
  mutant route's own output accepts every SC-12 case, while the reference
  rejects EX92 and EX93. This shows why OIB is needed; it is a witness, not the
  enforcement (OIB-1 to OIB-4 are the enforcement).
- NC-3 (route mismatch). A control adapter that declares a route identity
  different from what its plan reports produces `RouteMismatch` for every
  covered case, never a pass.
- NC-4 (independence metadata). The OIB-1 check reports a violation for a
  metadata fixture in which the reference crate depends on
  `combobulate-kernel`, and none for the live workspace.
- MUT-1 (real optimized-body fault). Running
  `cargo-mutants` on `crates/combobulate-kernel/src/elementwise_add.rs` with
  the replay as the test command reports every viable mutant that changes an
  SC-12 outcome as caught. Evidence recorded in `Artefacts and notes`, with
  each missed or unviable mutant triaged.
- FACADE-1' (absorbed oracle). FACADE-1's proptest refinement computes
  pointwise sums with the reference crate's `elementwise_add` instead of its
  private `i128` helper, and keeps its generator-classification evidence.
  Non-vacuity: the existing classification counts (success, shape, overflow
  outcomes all reached) still hold.

### Axioms (trusted, not verified here)

- AXIOM-1. Cargo's resolved metadata (`cargo metadata --format-version 1`)
  faithfully reports every dependency edge Cargo will compile.
- AXIOM-2. Rust privacy: a struct with private fields and no public constructor
  cannot be built outside its crate (OIB-4).
- AXIOM-3. `f64::to_bits` and `f64::from_bits` round-trip IEEE binary64 bit
  patterns, including NaN payloads, on the pinned toolchain and targets.
- AXIOM-4. `serde_json` parses the decimal strings used by the tagged scalars
  without loss; decoding F64 from `{"f64": "<decimal>"}` uses Rust's
  correctly-rounded `str::parse::<f64>`, and `{"f64_bits": "<hex>"}` is parsed
  as a `u64`.
- AXIOM-5. `core::any::type_name_of_val` names a function item by its path on
  the pinned nightly (used only in a drift test, never in a route decision).

### Where formal verification is not warranted

The reference evaluator *is* the executable statement of the contract for
testing. Proving it with Verus would prove the specification against a second
copy of itself, which adds no assurance; its correctness evidence is agreement
with independently recorded expectations (H-1), a second independent model (the
Python documentation model), and mutation sensitivity (H-2). The independence
boundary is a structural property of the dependency graph and of Rust privacy,
discharged by metadata checks and the type system, not by a theorem. The
route-identity API is plumbing over one dispatch entry. The kernel's arithmetic
is already verified by Verus under task 1.2.2 and is not modified, so
`make verus-kernel` is not a milestone gate; it is run once at EP-M3 as a
regression check because the dispatch site changes shape. Kani adds nothing
here: there is no machine-width arithmetic or bounded state space of the
harness's own to explore.

### Relationship between tests and proofs

Verus establishes that `add_i64_into` meets SC-12 for all inputs. The replay
establishes that the *public route* reaching that body, through the facade's
schedule and error mapping, produces the golden outcomes, and that the route
reported is the one that ran. Neither substitutes for the other: the proof does
not cover the facade's plumbing, and the replay covers only listed cases.

## Plan of work

The work proceeds in six milestones. Each ends in a coherent state with all
gates green.

### EP-M1: oracle independence boundary and golden-case reader

Assigned: OIB-1 to OIB-4, H-3, NC-4.

1. Red. Add `tests/semantic_examples.rs` with an `independence` module whose
   tests call a new helper `cargo::metadata::reference_closure_violations`
   against the live workspace and against a new fixture
   `tests/fixtures/cargo/reference-depends-on-kernel.json`. Run
   `cargo nextest run --test semantic_examples`; it fails to compile because
   the crate and helper do not exist.
2. Green. Create `crates/combobulate-reference/` (`Cargo.toml` with
   `publish = false`, `[lints] workspace = true`, no dependency tables;
   `src/lib.rs` with the `//!` statement of the boundary, `Scalar`, `Value`,
   `Case`, `Operation`, `Verdict` and a stub `evaluate` that returns a
   `Verdict` of `Unimplemented`). Add it as a root dev-dependency by path. Add
   the metadata helper and the OIB-3 source scan (walk the crate's `src/` with
   `cap_std::fs_utf8`, reject `#[path` and `include` macros naming `..`).
3. Add the decoder `tests/semantic_examples/decode.rs`: read
   `spec/examples.json` with `cap_std` from `env!("CARGO_MANIFEST_DIR")`,
   decode tagged scalars per `scalar_encoding`, map each case to
   `combobulate_reference::Case`, and fail with the case id on any unknown
   field, unknown operation, or both-or-neither expectation fields. Add H-3's
   completeness test with its fixture-based negative control.
4. Update the workspace-shape tests' expected crate sets
   (`tests/workspace_boundaries.rs`, `tests/workspace_profiles.rs`,
   `tests/build_profiles.rs`) only where they enumerate members, each with a
   comment citing ADR-0013.

End state: the reference crate exists, is provably independent, and all 75
golden cases decode. The replay table is introduced in EP-M2, not here, because
ignored or expected-failure rows are not evidence (§14) and must not be
committed.

Acceptance: `make check-fmt`, `make lint`, `make test` pass;
`cargo nextest run --test semantic_examples` shows the independence tests and
the decode test passing, including the fixture violation control.

### EP-M2: the reference evaluator replays all 75 golden cases

Assigned: H-1, H-2.

Write each reference module from the contract text in
`spec/semantic-contracts.json` and ADR-0006, one module per contract family,
each under 400 lines: `scalar.rs` (values, dtype, bit equality), `arith.rs`
(SC-03, SC-04, SC-05: `add`, `sub`, `mul`, `div`, `idiv`, `rem`, checked I64 via
`i128`), `logic.rs` (SC-06 Kleene `and`, `or`, `xor`), `extremum.rs` (SC-07
`min`, `max`, `minimum`, `maximum`, NaN and signed-zero rules), `cast.rs`
(SC-04 casts and their range and `-0.0` rules), `reduce.rs` (SC-01
right-associated `reduce`, `fold_left`; SC-02 `sum`, `product`, `any`, `all`,
empty and identity rules, null policy), `statistics.rs` (SC-11 `mean`,
`mean_count`, `variance`, `stddev`, `ddof`), `structure.rs` (SC-08
`batch_axis`, SC-09 `atomic_commit`), `elementwise.rs` (SC-12 `elementwise_add`
with least-position overflow), and `mutation.rs` (the 13 seeded mutations as an
enum, each consulted only at the point its contract describes).

Red-Green per module: add the module's golden-case rows to the replay table
(through the shared `macro_rules!` list), run them, watch them fail with
`Unimplemented`, implement, watch them pass. Then add that contract's H-2
mutation rows and watch each fail before the mutation hook exists.

Acceptance: 75 replay cases and 13 mutation rows pass; gates pass.

### EP-M3: route identity on prepared plans

Assigned: RI-1.

1. Red. Add unit tests in `src/plan/tests.rs`:
   `route_names_the_sequential_engine`, `input_only_plan_reports_no_kernel`,
   `repeated_additions_report_one_distinct_kernel`,
   `kernel_label_names_the_dispatched_function`; add a doctest on
   `PreparedPlan::route`. They fail to compile.
2. Green. Add `src/plan/route.rs` with `ExecutorId`, `KernelId`, `Route`.
   Replace `dispatch_add` with a `const ADD_KERNEL: KernelEntry` holding the
   `KernelId` and the function pointer; `run` calls `ADD_KERNEL.body`, and
   `route()` collects `ADD_KERNEL.id` for each `Step::Add`. Re-export from
   `src/lib.rs`. Extend `tests/ordinary_application/surface.rs` with the new
   types (Send, Sync, non-generic names).
3. Run `make verus-kernel` once as a regression check (kernel unchanged).

Acceptance: gates pass; `cargo test --doc` shows the new doctest; the existing
`the_dispatch_route_is_the_verified_kernel` still passes, adapted to
`ADD_KERNEL`.

### EP-M4: route-identifying harness, production replay, negative controls

Assigned: RI-2, RI-3, NC-1, NC-2, NC-3, and H-1's route half.

1. Add `tests/semantic_examples/route.rs`: the `RouteUnderTest` trait
   (`declared() -> Route`, `observe(&Case) -> Observation`), the
   `NativeSequential` adapter mapping `elementwise_add` cases onto
   `Array::from_i64`, `add().apply`, `prepare`, `route`, `execute`, and
   `Observed` conversion from `ExpressionError` (code, position) without using
   `Display` text.
2. Add `tests/semantic_examples/report.rs`: a report entry per case
   (`id`, `contract`, `route` or `reference only`, `judgement`), rendered as
   plain text and snapshotted with `insta` as
   `semantic_examples__route_report.snap`. Semantic assertions accompany the
   snapshot: the covered set equals SC-12's `examples` list, and every covered
   entry names `native.sequential` and `add_i64_into`.
3. Extend `replays_contract_case` so each case is judged against the
   reference and then, if the production adapter supports it, against the route;
   `Unsupported` is recorded, not passed.
4. Add `tests/semantic_examples/controls.rs` with NC-1, NC-2 and NC-3, each
   asserting the specific failing case identifiers and judgement kinds.
5. Add `tests/features/semantic_examples.feature` and its step bindings
   (scenarios below).

Red-Green: the controls are written first and fail because the harness reports
nothing; the harness is then built until each control fails *its mutant* for
the stated reason and the production route passes.

Acceptance: gates pass; the snapshot is reviewed and accepted once.

### EP-M5: FACADE-1 absorption, consumer fixture, mutation evidence

Assigned: FACADE-1', MUT-1, and the public-consumer evidence for RI-1.

1. Change `tests/ordinary_application/refinement/model.rs` to compute
   pointwise sums with `combobulate_reference::elementwise_add` and delete the
   private helper; keep classification evidence.
2. Extend `tools/fixtures/native-consumer/src/bin/ordinary_application.rs` to
   print
   `route: native.sequential [combobulate_kernel::elementwise_add::add_i64_into]`
   through the public API, and accept the updated
   `native_consumer_e2e__ordinary_application.snap`.
3. Run cargo-mutants (command in `Concrete steps`) and record the result.

Acceptance: gates pass; MUT-1 evidence recorded.

### EP-M6: documentation, ADR-0013, completion record, roadmap tick

1. Write `docs/adrs/adr-0013-independent-reference-oracle-and-route-identity.md`
   (Y-statement: the crate boundary, the opaque verdict, the public route
   observation, the retained Python model), add it to `docs/contents.md`, and
   reference it from technical design §14.
2. `docs/users-guide.md`: a "Seeing which route ran" subsection with the
   `route()` example; update "Current limits".
3. `docs/developers-guide.md`: a "Semantic-example replay" section (how to add
   a golden case, how coverage grows when a route lands, how to add a seeded
   mutation, the independence rules and reuse policy for
   `combobulate-reference`: test-only; never a dependency of a shipped crate;
   later tasks extend it by contract, not by importing production code); the
   crate table row; the Table 2 row for `contract_examples.py` (DL-3); the
   `null` wording note.
4. `docs/repository-layout.md`: the new crate and test binary.
5. `spec/task-completion.json`: a 1.2.3 entry (decisions D15, D06, D07;
   artefacts: ADR-0013, the reference crate's `src/lib.rs`,
   `tests/semantic_examples.rs`, `src/plan/route.rs`,
   `tests/features/semantic_examples.feature`). Tick 1.2.3 and its sub-item in
   `docs/roadmap.md` and set `spec/roadmap.json` status to `done`. Regenerate
   `docs/validation-results.json` with `python scripts/check_docs.py --write`
   on the final tree.

Acceptance: `make check-fmt`, `make lint`, `make test`, `make markdownlint`,
`make nixie`, `make design-check` pass.

## Behavioural specification (BDD)

Path: `tests/features/semantic_examples.feature`, bound in
`tests/semantic_examples/bdd.rs`. Trace: H-1, RI-2, NC-1, NC-3; EP-M4.

```gherkin
Feature: Replaying the golden cases through an independent reference

  Scenario: A covered case reports the route that ran
    Given the golden case "EX89"
    When the case is replayed on the native sequential route
    Then the reference accepts the route's outcome
    And the report names executor "native.sequential"
    And the report names kernel "combobulate_kernel::elementwise_add::add_i64_into"

  Scenario: A case without a production route is reference-only
    Given the golden case "EX21"
    When the case is replayed on the native sequential route
    Then the report marks the case as reference only
    And the case is not counted as passing on any route

  Scenario: A seeded wrong result fails for the intended reason
    Given the golden case "EX92"
    When the case is replayed on a route that wraps on overflow
    Then the replay fails with "value where IntegerOverflow at position 1 was expected"

  Scenario: A route that misreports itself is rejected
    Given the golden case "EX89"
    When the case is replayed on a route whose declared executor differs from its plan
    Then the replay fails with a route mismatch
```

## Concrete steps

All commands run from the worktree root. Use `tee` logs as `AGENTS.md` and the
user's instructions require, for example:

```sh
make check-fmt 2>&1 | tee /tmp/check-fmt-combobulate-1-2-3-independent-semantic-example-runner.out
make lint 2>&1 | tee /tmp/lint-combobulate-1-2-3-independent-semantic-example-runner.out
make test 2>&1 | tee /tmp/test-combobulate-1-2-3-independent-semantic-example-runner.out
```

Focused loop while developing:

```sh
cargo nextest run --no-default-features --test semantic_examples
cargo nextest run --no-default-features -p combobulate-reference
```

Mutation evidence (EP-M5). Confirm the flags with `cargo mutants --help` on
27.1.0 first; the intent is "mutate only this file, run only the replay":

```sh
cargo mutants --file crates/combobulate-kernel/src/elementwise_add.rs \
  --test-workspace=true -- --no-default-features --test semantic_examples \
  2>&1 | tee /tmp/mutants-combobulate-1-2-3-independent-semantic-example-runner.out
```

Expected: a summary with zero `MISSED` mutants that change SC-12 outcomes; any
`MISSED` mutant is triaged in `Surprises & discoveries`.

## Validation and acceptance

The task is complete when:

- `cargo nextest run --test semantic_examples` (both profiles, through
  `make test`) shows 75 passing `replays_contract_case::case_exNN` cases, 13
  passing mutation rows, the completeness test, the independence tests, the
  four controls and the four BDD scenarios.
- The snapshot `semantic_examples__route_report.snap` lists EX89 to EX95 on
  `native.sequential` / `add_i64_into` and the other 68 cases as reference only.
- Seeding wrapping addition into the kernel body by hand (local experiment,
  reverted) makes `replays_contract_case::case_ex92` and `case_ex93` fail with
  the intended judgement; cargo-mutants confirms the same mechanically.
- The consumer fixture prints the route line, and `make test` passes.
- `make check-fmt`, `make lint`, `make test`, `make markdownlint`,
  `make nixie`, and `make design-check` pass.

## Idempotence and recovery

Every step is additive or a rewrite of a file this plan owns, and is safe to
rerun. If a milestone fails part-way, reset to the previous milestone's commit.
cargo-mutants works in a scratch copy and does not edit the tree; if it is
interrupted, delete `mutants.out*` (ignored or removed before commit). The
hand-seeded kernel mutation is made and reverted within one shell session and
never committed; `git diff --exit-code crates/combobulate-kernel` must succeed
afterwards.

## Artefacts and notes

None yet.

## Interfaces and dependencies

New public items in the facade (`src/plan/route.rs`, re-exported from
`src/lib.rs`):

```rust
/// Which engine runs a prepared plan.
#[non_exhaustive]
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ExecutorId { NativeSequential }
impl ExecutorId { pub const fn name(self) -> &'static str }  // "native.sequential"

/// One kernel body a plan's steps dispatch to.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct KernelId { /* operation: OperationId, symbol: &'static str */ }
impl KernelId {
    pub const fn operation(self) -> OperationId;
    pub const fn symbol(self) -> &'static str;  // "combobulate_kernel::elementwise_add::add_i64_into"
}

/// The route a prepared plan will take.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Route { /* executor: ExecutorId, kernels: Box<[KernelId]> */ }
impl Route {
    pub const fn executor(&self) -> ExecutorId;
    pub fn kernels(&self) -> &[KernelId];
}

impl NativeExecutor { pub const fn id(&self) -> ExecutorId }
impl PreparedPlan { pub fn route(&self) -> Route }
```

New test-only crate `combobulate-reference` (not shipped):

```rust
pub enum Scalar { Null, Bool(bool), I64(i64), F64(u64 /* bits */) }
pub enum Operand { Scalar(Scalar), Vector(Vec<Scalar>), /* shapes, cells */ }
pub enum Operation { /* the 27 golden-case operations */ }
pub struct Case { /* id, contract, operation, operands, modifiers */ }
pub enum Mutation { LeftReduce, EmptySumError, /* … 13 … */ }
pub struct Verdict { /* private */ }
pub enum Judgement { Agrees, ValueMismatch { .. }, ErrorWhereValueExpected { .. },
                     ValueWhereErrorExpected { .. }, ErrorMismatch { .. } }
pub fn evaluate(case: &Case, mutations: &[Mutation]) -> Verdict;
impl Verdict { pub fn judge(&self, observed: &Observed) -> Judgement; }
pub fn elementwise_add(lhs: &[i64], rhs: &[i64]) -> Result<Vec<i64>, Failure>;
```

Dependencies: none added. The root gains one path dev-dependency on
`crates/combobulate-reference`.

## Revision note

- 2026-11-28: initial draft from Wyvern reconnaissance.
