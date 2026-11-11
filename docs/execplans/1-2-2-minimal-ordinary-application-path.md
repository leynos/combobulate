# Implement the minimal values, expression handles, and ordinary application path

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: DRAFT

Roadmap task: 1.2.2 in `docs/roadmap.md`. Branch:
`1-2-2-minimal-ordinary-application-path`, cut from `main` at `b873322`.

Implementation must not begin until the user explicitly approves this plan.

## Purpose / big picture

Combobulate is a Rust library for inspectable array algebra. After task 1.2.1
the repository builds a facade crate (`combobulate`), a `#![no_std]` semantic
kernel (`combobulate-kernel`), and an empty procedural-macro crate, but no
array value or operation exists. The users' guide still says "array algebra is
not yet implemented".

This task delivers the first runnable public path. After it lands, a downstream
Rust program that depends on `combobulate` with `default-features = false` (no
Polars, no verifier) can write:

```rust
use combobulate::{add, identity, Array, ExpressionError, NativeExecutor};

let xs = Array::from_i64(vec![1, 2, 3]);
let ys = Array::from_i64(vec![10, 20, 30]);

let expression = add().apply(&xs.expr().then(&identity()), &ys.expr());
let plan = expression.prepare(&NativeExecutor::sequential())?;
let sum = plan.execute()?;
assert_eq!(sum.as_i64_slice(), Some(&[11, 22, 33][..]), "add is pointwise");

let same = xs.expr().then(&identity()).collect()?;
assert_eq!(
    same.as_i64_slice().map(<[i64]>::as_ptr),
    xs.as_i64_slice().map(<[i64]>::as_ptr),
    "identity shares the input buffer"
);
# Ok::<(), ExpressionError>(())
```

The program constructs an `I64` vector without copying the `Vec` it was given.
It builds a deferred expression with `identity` and `add`, prepares it against
an explicit executor, and executes it. It also collects in one step with the
default executor. No public type has a generic parameter, and `identity`
returns the very buffer it was given. The arithmetic of `add` runs in one
`core`-only kernel function. Verus checks that function's specification locally
against the shipped body.

The Verus result is not yet admitted evidence in the ADR-0009 sense. The Verus
log parser arrives in task 1.2.4, and the semantic contract assigns admission to
`PF05.proof@2.3.5`, as DL-1 explains.

Observable success is:

1. A standalone fixture binary under `tools/fixtures/native-consumer/` builds
   with `default-features = false` and runs, printing the identity and add
   results. `tests/native_consumer_e2e.rs` builds it, runs it, and compares its
   output.
2. `make verus-kernel` fully verifies the kernel proof root, including the
   shipped body. Every seeded mutant is rejected at the clause it targets.
3. `make check-fmt`, `make lint`, `make test`, `make markdownlint`,
   `make nixie`, `make spelling` and `make design-check` all pass.

The task also answers roadmap step 1.2's question: can a small public Rust
program create and execute an array without Polars or custom `Fn`
implementations? The answer, and what it means for feature selection and the
baseline dependency lock, is recorded under `Outcomes & retrospective` and
cited by the completion record.

## Constraints

These are hard invariants. Violating one requires escalation, not a workaround.

- The kernel crate stays `#![no_std]` without `alloc` and declares no
  dependency of any kind, including dev-dependencies
  (`tests/workspace_boundaries.rs` VO-1 reads every dependency kind). Kernel
  code uses `core` only.
- Verus vocabulary enters kernel source only as ADR-0010's single-root
  pattern:
  - a `#[cfg(verus_keep_ghost)] use vstd::prelude::*;`;
  - `cfg_attr(verus_keep_ghost, …)` attributes.
  Both are inert in ordinary builds. vstd is already on ADR-0010's
  proof-dependency allowlist and comes from Verus's own `--extern`, so no
  manifest edge is added.
- No Polars or glam path appears outside `src/polars_backend.rs` (the 1.2.1
  plan's DL-19, checked by `scripts/docs_validation/polars_confinement.py`).
  New facade modules must compile and pass gates under both `native-only`
  (`--no-default-features`) and `polars-enabled` profiles.
- No public type exposes an internal graph generic (technical design R3).
  Every new public type is non-generic. No public signature carries a kernel
  type: `Failure` does not wrap `AddFailure`.
- Consumers never need to name `combobulate_kernel`. The kernel's functions
  are `pub` only because the facade must call them.
- `unsafe_code` stays forbidden workspace-wide.
- One executable body. The facade executes exactly the kernel function that
  Verus verifies. No `cfg(kani)`, `cfg(verus_keep_ghost)`,
  `cfg(not(verus_keep_ghost))` or feature flag may gate a `fn` item in kernel
  source. No proof root may define a function named like a shipped kernel
  function (technical design §17.7, B01 falsifier). The widened VO-6 scan and
  `scripts/verus_kernel.py` enforce both rules mechanically.
- Trust audit:
  - zero trusted items in workspace sources and in each product proof root;
  - no `assume`, `admit`, `external_body`, `external`, `assume_specification`
    or `external_fn_specification` in kernel source or any proof root;
  - no `#[verifier::…]` attribute (for example `external_derive`, `rlimit`,
    `loop_isolation`) without a decision-log entry, and any
    `external_derive` declared as an axiom.
- Kernel source contains no `crate::` or `super::` path, because the proof
  root compiles it as a nested module through `#[path]`.
- I64 addition is checked. Overflow is the `IntegerOverflow` failure, never
  wrapping or saturation (V001, technical design §6.1, SC-12).
- Graph construction and preparation never invoke an arithmetic kernel. Only
  `PreparedPlan::execute` and `AExpr::collect` execute (ADR-0007 staging, E002,
  E004, E005).
- Names follow `spec/vocabulary.json` and the existing specification model:
  - `identity`, never the excluded alias `id` (D06);
  - the shape failure is `ShapeAgreement`, the name `spec/examples.json` EX08
    and `scripts/docs_validation/semantics.py` already use;
  - no aliases, deprecated entry points or compatibility shims (ADR-0005).
- Each code file stays at or under 400 lines (`AGENTS.md`). This includes
  `scripts/docs_validation/contract_examples.py`, which is at 390 lines now.
- Lint and suppressions:
  - Clippy pedantic, the workspace restriction lints, the `clippy.toml`
    thresholds (cognitive complexity 9, four arguments, 70 lines, nesting 4)
    and Whitaker must pass.
  - The only new suppressions are those in DL-8. A function-scoped
    `#[expect(clippy::missing_const_for_fn)]` on `add_i64_into` is
    pre-approved only if Verus rejects a `const fn` body.
- Tests must not mutate the process environment. The fixture build uses
  `Command::env`/`env_remove`, the permitted subprocess exemption.
- `scripts/run_verifier_probes.py`, `scripts/verus_probe.py`,
  `scripts/probe_provenance.py` and `scripts/verifier_probe_support.py` must
  not be edited. Their structural digests are bound into the 1.2.1 Verus
  records, and `scripts/tests/test_verifier_record_digests.py` fails on any
  change to them.
- Completed ExecPlans for other tasks are historical. Do not edit them.

## Tolerances (exception triggers)

The ExecPlan file itself is excluded from every count below. So are generated
and captured files:

- `Cargo.lock` and `spec/roadmap.json`;
- `docs/validation-results.json`;
- `typos.toml`;
- the regenerated language-reference tables;
- `insta` snapshots;
- Verus logs and `provenance.json`.

The thresholds are:

- Scope: stop and escalate if the change touches more than 60 other files or
  exceeds 4,500 net added lines of code and other documentation.
- Interface: stop and escalate if a public signature in
  `Interfaces and dependencies` must change shape after approval, such as a
  renamed type, an added type parameter, a different return type or a removed
  item. Adding or removing `const`, `#[must_use]` or `#[non_exhaustive]`, or
  adding a private helper, is not an interface change.
- Dependencies: `proptest` as a root-package dev-dependency is pre-approved
  (DL-6). Any other new dependency requires escalation.
- Verus feasibility: if EP-M2 cannot fully verify the kernel through the
  single-root `cfg_attr` route after three distinct attempts, stop and escalate
  with the logs. This includes `verus_spec` on `while` loops inside a
  `const fn`, the `matches` patterns, and `final`/`old` spellings. Do not fall
  back to `verus!` macro source for the executable body, a mirror body,
  `external_body`, or recursion.
- Proof cost: no acceptance control covers this kernel. As a plan-local
  escalation trigger, use AC-01's frozen thresholds: 10 s wall time, 320 MiB
  resident memory, a per-function rlimit of 300,000, and a 30 s hard timeout
  for the positive root. Record each measurement. Exceeding a threshold is an
  escalation, not an acceptance claim, and a timeout is never relabelled as
  success.
- Iterations: if a gate still fails after three fix attempts on the same
  cause, stop and escalate.
- Governance: the following validator edits are pre-approved:
  - registering `ShapeAgreement` and adding SC-12 with its examples;
  - an `elementwise_add` handler for the Python contract model;
  - adding product proof roots to `trust_audit_check.py` as zero-trust
    subjects;
  - adding `verus-kernel` subjects to `spec/toolchain-profiles.json`'s
    `proof-verus` record.
  Any other validator change needed to make `make design-check` pass requires
  escalation.
- Ambiguity: if review or implementation finds two materially different
  readings of a requirement, stop and present the options.

## Risks

- Risk: Verus may reject one of the attribute-syntax constructs the kernel
  needs. The wiring probe verified only a straight-line `fn` on `u8`. The
  constructs are:
  - `cfg_attr(verus_keep_ghost, verus_spec(invariant …, decreases …))` on a
    `while` statement;
  - the `final(out)@`/`old(out)@` spellings;
  - `matches` patterns over a verified enum with derives;
  - a `const fn` body.
  Severity: high. Likelihood: medium. Mitigation:
  - EP-M2 is a prototyping milestone. It settles each construct before any
    facade code, under the Verus tolerance.
  - The Verus attribute syntax documents loop specifications by
    `#[verus_spec(invariant …)]` on `while` statements.
  - With the `cfg` false, an attribute on a statement is stable Rust.
  - Each confirmed spelling is recorded in `Surprises & discoveries`.
- Risk: workspace Clippy denies `indexing_slicing`. A Verus-friendly loop
  indexes slices directly. Severity: medium. Likelihood: certain. Mitigation:
  DL-8's scoped expectation. Its reason names the Verus obligation that
  discharges each bound. The alternative, `get`/`get_mut`, would leave
  unreachable `None` arms as untestable lines that the coverage ratchet counts.
- Risk: vstd specifications are themselves `assume_specification` items and
  widen the trusted basis. Severity: low. Likelihood: certain. Mitigation:
  AXIOM-2 lists each vstd item used. They live in vstd, not in workspace
  sources.
- Risk: Verus compiles the kernel with Rust 1.98.0 while ordinary builds use
  nightly-2026-11-06 (1.101). Severity: medium. Likelihood: certain. Mitigation:
  - The same source is verified and shipped.
  - The Verus run passes `--edition=2024` explicitly.
  - Compiler agreement on this `core`-only subset is AXIOM-3.
  - The ordinary unit, const-evaluation and property tests exercise the
    shipped object code.
- Risk: a naive walk over a shared directed acyclic graph (DAG) is
  exponential, and recursive traversal, recursive `Drop` or derived `Debug`
  overflow the stack on deep chains. Severity: high. Likelihood: high if
  unplanned. Mitigation:
  - Lengths are cached per node at construction.
  - Preparation emits a linear schedule over a visited set.
  - `Node` has an iterative `Drop`.
  - `Debug` is handwritten and non-recursive.
  - FACADE-4 and FACADE-5 are the negative controls.
- Risk: governance drift. `docs/validation-results.json` records counts that
  this work changes, such as the Python tool count, facade source file count,
  links and roadmap text. `make design-check` fails until it is regenerated.
  Severity: medium. Likelihood: certain. Mitigation: regenerate and commit the
  report after every green milestone (see `Concrete steps`).
- Risk: committed Verus logs contain pinned version strings, which the VO-7
  pin sweep rejects outside exempt directories. Severity: medium. Likelihood:
  certain. Mitigation: commit observations under
  `tools/verifier-fixtures/verus-kernel/`, which the sweep already exempts. The
  existing record tests there may assume the wiring-probe schema. Run them
  first, and treat any schema mismatch under the governance tolerance.
- Risk: the hosted `build-test` job has an eight-minute budget, and new test
  binaries and `proptest` add build time. Severity: medium. Likelihood: medium.
  Mitigation:
  - Add at most two new integration-test binaries.
  - Reuse the existing fixture build.
  - Keep property cases at proptest's default 256.
  - Measure the job time on the draft PR and record it.

## Progress

- [x] (2026-11-11) Branch renamed to `1-2-2-minimal-ordinary-application-path`.
- [x] (2026-11-11) Wyvern reconnaissance of the design, ADR, specification and
  tooling surfaces.
- [x] (2026-11-11) Draft ExecPlan written and committed.
- [x] (2026-11-11) Community-of-experts review. Four reviewers covered Verus
  proof design, Rust API and ownership, tests and governance tooling, and
  design conformance. Their findings are folded into this revision (see
  `Revision note`).
- [ ] Draft PR opened for plan review.
- [ ] User approval of the plan (status becomes `APPROVED`).
- [ ] EP-M1: specify. SC-12, the `ShapeAgreement` registration, examples and
  the Python model, the ADR-0006 amendment, and the denotation in technical
  design §8.
- [ ] EP-M2 (prototype): kernel `elementwise_add::add_i64_into`, Verus roots,
  mutants, `scripts/verus_kernel.py` and `make verus-kernel`.
- [ ] EP-M3: facade values and expression handles.
- [ ] EP-M4: preparation, execution and errors.
- [ ] EP-M5: the public consumer fixture, boundary and workflow wiring.
- [ ] EP-M6: documentation, ADR-0011, the completion record and the roadmap
  tick.

## Surprises & discoveries

- Observation: no proof-obligation component in `spec/proof-obligations.json`
  names task 1.2.2. The Verus log parser is not registered until 1.2.4, so any
  Verus record made now is `verdict-self-reported` and the gate rejects it.
  Evidence: ADR-0009 lines 132-144 and 183-243;
  `scripts/docs_validation/evidence_gate.py:121`. Impact: DL-1.
- Observation: `tests/workspace_kernel_boundary.rs` (VO-6) scans only
  `crates/combobulate-kernel/src/lib.rs`, so an `extern crate alloc` in a new
  kernel submodule would pass it. Evidence:
  `tests/support/workspace_source.rs`. Impact: EP-M5 widens it.
- Observation: the specification model already names the shape failure
  `ShapeAgreement`, yet the closed `error_codes` set in
  `spec/semantic-contracts.json` omits it. No existing contract record covers
  checked elementwise I64 addition. SC-04 is "Explicit dtype conversion" and
  links to `add` only through `DtypeMismatch`. Evidence:
  `spec/examples.json:105`, `scripts/docs_validation/semantics.py:67,80`,
  `spec/semantic-contracts.json:3-20`. Impact: DL-4 adds SC-12.
- Observation: running `--verify-root` checks only the proof root module, not
  the module it includes. The wiring probe needed a separate
  `--verify-only-module=production` run to check the included body. Evidence:
  `tools/verifier-fixtures/verus-wiring-probe/observations/`
  `single-root-capability.log` (`1 verified`) versus `single-root-helper.log`.
  Impact: the positive Verus root runs with no `--verify-*` flag (DL-13).
- Observation: on this host `make design-check` fails eight
  `test_verifier_record_digests` subtests on an unmodified tree, but the hosted
  design job passes on `main` at `b873322`. The structural digest of `.py`
  sources hashes `ast.dump`, whose output differs between the host's `python3`
  (3.12.15) and `design.yml`'s Python 3.14. Under Python 3.14 the same tests
  pass (7 passed, 43 subtests). Evidence: the local design-check log under
  `/tmp`, and the focused run in `Artefacts and notes`. Impact: every local
  `make design-check` in this plan sets `PYTHON` to a Python 3.14 interpreter
  (see `Concrete steps`), matching the hosted job. It also matters for the
  digests `scripts/verus_kernel.py` records in EP-M2, which must be produced
  under Python 3.14.
- Observation: `clippy::error_impl_error` is denied, so a public type named
  `Error` that implements the error trait fails `make lint`. Evidence:
  `Cargo.toml:125`; the existing `BackendProbeError`. Impact: DL-11.

## Decision log

Each entry below is proposed. It takes effect on plan approval unless it says
otherwise.

- DL-1. Evidence admission.
  Decision: this task links no gate component in `spec/proof-obligations.json`.
  SC-12 records `discharged_by: ["task:1.2.2", "PF05.proof@2.3.5"]`, so the
  admission hand-off lives in the specification rather than in this plan. The
  existing PF05 component is outcome and frame of the sequential native route.
  Verus runs in `make verus-kernel` as an EP-M2 acceptance criterion. The logs
  are committed under `tools/verifier-fixtures/verus-kernel/` as development
  artefacts. They are not evidence records, and 2.3.5 re-runs rather than
  admits them. User-facing text says "checked locally with Verus; not admitted
  evidence (ADR-0009 MS-1)". No scope is added to task 1.2.4. Rationale:
  - ADR-0009 MS-4 gates only on linked components, and the ledger assigns PF04
    and PF05 to 2.3.x. Linking none is conformant.
  - A `proof`-accepting component on 1.2.2 could never be satisfied before the
    1.2.4 parser exists, which would make 1.2.2 untickable.
  - Roadmap 1.2.2's proof-first clause asks for denotation, witnesses and
    executable identities. EP-M1 and EP-M2 deliver all three.
  Approval needed: yes. Date/Author: 2026-11-11, planning agent.
- DL-2. Storage.
  Decision: values hold storage as a private `Storage::I64(Arc<Vec<i64>>)`.
  `Array::from_i64(values: Vec<i64>)` moves the `Vec` into the `Arc` with no
  element copy. Rationale:
  - The success criterion forbids unnecessary input copies.
  - `Arc<[i64]>` would force a copy from every `Vec`, because the slice needs
    a header in front of its data.
  - The extra indirection is paid once per kernel call, when `&[i64]` is
    borrowed, not per element.
  - A constructor from `Arc<[i64]>` is not added until a consumer needs one.
  Date/Author: 2026-11-11, planning agent.
- DL-3. Identity folding.
  Decision: `Unary::apply` with the identity descriptor returns a clone of the
  operand handle and adds no node. `AExpr::then(op)` is defined as
  `op.apply(self)`, so the two spellings cannot diverge. `AExpr` has no public
  pointer-identity or structural-equality API, so a later identity node, for
  provenance (2.3.3) or explain output, is unobservable and non-breaking.
  Rationale: V032 says identity "Shares the input handle; no evaluation or
  copy". Folding preserves ⟦identity(e)⟧ = ⟦e⟧ exactly and makes buffer sharing
  structural. Date/Author: 2026-11-11, planning agent.
- DL-4. Contract record.
  Decision: amend ADR-0006 (D07; D01 option B delegates this to the technical
  owner) to add the following to `spec/semantic-contracts.json`.
  - Contract SC-12, "Elementwise checked I64 addition and equal-shape
    agreement", citing D07 with `catalogue_ids: ["V001"]`. It records:
    - preconditions;
    - the success relation `addv`;
    - success conditions;
    - error relation: `ShapeAgreement` at preparation and
      `IntegerOverflow` at the least overflowing position during
      execution;
    - frame: inputs unchanged, failed execution publishes nothing;
    - termination, the empty rule, and examples;
    - seeded mutation `wrapping-add`;
    - `discharged_by` per DL-1;
    - a proof sketch.
  - `ShapeAgreement` in the closed `error_codes` set.
  - New `contract_cases` (EX89 onward) evaluated by a new
    `scripts/docs_validation/elementwise_examples.py`, which
    `contract_examples.py` dispatches to through one handler entry.
  V001's contract text gains "SC-12" and the reference tables are regenerated.
  Every earlier "SC-04 (checked add)" citation is replaced by "technical design
  §6.1, V001, SC-12". Rationale:
  - Technical design §17.5 makes error categories public semantic values.
  - A completed ExecPlan is historical, so the denotation must live in a
    durable contract that 1.2.3 (contract-case replay), 1.2.5 (logical view)
    and 2.3.5 (PF05) can refine.
  - Reusing `ShapeAgreement` avoids an alias (D06).
  Approval needed: yes. Date/Author: 2026-11-11, planning agent.
- DL-5. Minimal executor.
  Decision: introduce `NativeExecutor` with one `const fn sequential()`
  constructor. It is the only engine and the default for `collect`. Mark it
  `#[non_exhaustive]` and not `Copy`: E017 will add resources and scratch, and
  removing `Copy` later would break callers. E017's `roadmap_tasks` stays
  unchanged, because its contract (caller-owned output, policies) is not met.
  The users' guide calls this a "minimal preview". Rationale:
  `.prepare(&engine)` needs an engine type, and E017's name avoids a
  placeholder that 2.3.5 would have to delete. Date/Author: 2026-11-11,
  planning agent.
- DL-6. `proptest`.
  Decision: add `proptest` (caret `1.12.0`, confirmed against the shared cache
  at implementation) as a root-package dev-dependency. Use
  `default-features = false, features = ["std"]` if that feature set compiles;
  otherwise use the defaults, and record which. Rationale: the refinement claim
  FACADE-1 quantifies over generated expression DAGs and values, which a finite
  table cannot cover. Kani is not used for the facade, which allocates and
  traverses heap-shaped graphs. Date/Author: 2026-11-11, planning agent.
- DL-7. Kernel shape.
  Decision: the kernel is two-pass with caller-provided output:
  `add_i64_into(lhs, rhs, out) -> Result<(), AddFailure>`.
  - Pass 1 checks lengths, then finds the least overflowing position without
    writing.
  - Pass 2 writes every sum.
  - Every `Err` leaves `out` unchanged.
  The facade allocates `vec![0; n]`, runs the kernel, and wraps the `Vec` in an
  `Arc` only on `Ok`. Rationale:
  - The kernel has no `alloc`.
  - A one-pass kernel would leave `out[..p]` written on overflow. That is the
    "partial-output" and "early-write" mutation SC-09 and PF05 require to
    fail, so it could never serve 2.3.5's caller-owned destination.
  - Two passes give the frame "Err ⇒ out unchanged". The kernel is then
    directly reusable by 2.3.5, which still discharges SC-09 itself.
  Date/Author: 2026-11-11, planning agent.
- DL-8. Scoped suppressions. Decision: exactly two
  `#[expect(clippy::indexing_slicing, reason = …)]` attributes, each on one
  function.
  - On `add_i64_into`, the reason states that the loop guards bound every
    index and Verus discharges each in-bounds obligation. Clippy expectations
    are inert when Clippy is not running.
  - On the facade's one-line `fn operand(results: &[Vec<i64>], slot: Slot) ->
    &[i64]`, the reason states that the post-order schedule places every
    operand slot before its consumer. FACADE-1 and FACADE-4 are the evidence.
  Rationale: the alternatives leave unreachable `None` arms. Date/Author:
  2026-11-11, planning agent.
- DL-9. Static failure rule. Decision: the static length model is partial.
  - `len(add(l, r))` is undefined when either operand's length is undefined or
    when the two differ.
  - A mismatch is reported only at the root-cause node, the add whose operands
    both have defined, unequal lengths. Ancestors of an undefined length report
    nothing.
  - Preparation reports every root-cause mismatch once, in first-completion,
    left-first post-order.
  - Execution fails fast with the first failing add in the same order.
  Lengths and a `mismatch_below` flag are computed in O(1) per node in
  `Binary::apply` from the operands' cached facts, without running a kernel.
  Rationale: technical design §8 asks preparation to collect "independent
  static errors". The rule makes that precise and deterministic. Date/Author:
  2026-11-11, planning agent.
- DL-10. Records.
  Decision:
  - `docs/adrs/adr-0011-minimal-value-and-expression-representation.md`
    records DL-2, DL-3, DL-7, DL-9, DL-12 and DL-14. Its initial status is
    `Accepted`, citing this plan's approval and the PR as the approval
    reference.
  - Technical design §§4.1 and 8 reference it.
  - DL-4's semantic content goes through the ADR-0006 amendment.
  - No decision-register entry is added, because representation choices do not
    control acceptance. ADR-0001 and ADR-0009 are precedents for ADRs without a
    D link.
  Date/Author: 2026-11-11, planning agent.
- DL-11. Error type name.
  Decision: the public error type is `ExpressionError`. Rationale:
  `clippy::error_impl_error` is denied, and the name matches the repository's
  `BackendProbeError` precedent. Date/Author: 2026-11-11, planning agent.
- DL-12. Execution schedule.
  Decision: preparation emits a linear `Box<[Step]>`:
  `Step::Input(Arc<Vec<i64>>)` or `Step::Add { lhs: Slot, rhs: Slot }`.
  - The traversal uses an explicit stack (`Finish(n)`, `Expand(r)`,
    `Expand(l)`) and a visited set keyed by `Arc::as_ptr`.
  - The set lives only for the duration of `prepare`. The borrowed root keeps
    every node alive, so addresses cannot be reused mid-walk. `PreparedPlan`
    never stores raw pointers.
  - Execution is a plain loop over the steps with no hashing.
  - Intermediate buffers live until execution ends. Freeing after last use is a
    recorded gap for 2.3.5.
  Rationale: memoized, iterative and simple, within the Clippy thresholds.
  Date/Author: 2026-11-11, planning agent.
- DL-13. Verus layout.
  Decision:
  - Production source is `crates/combobulate-kernel/src/elementwise_add.rs`.
  - `crates/combobulate-kernel/verus/elementwise_add_contract.rs` defines open
    spec functions `k1` to `k5` and the lemma `lemma_contract_determinate`.
  - The positive root, `verus/elementwise_add.rs`, includes the contract and the
    production file by `#[path]`. It runs with no `--verify-*` flag and must
    report `N verified, 0 errors` with no "partial verification" suffix; `N`
    is pinned in the script after EP-M2.
  - The mutant root, `verus/elementwise_add_mutants.rs`, includes the same
    files. Each mutant runs with
    `--verify-root --verify-function=<exact name>`, and mutant names share no
    substrings.
  - The new `scripts/verus_kernel.py` runs both passes and imports
    `verus_probe` helpers without editing them. It passes `--edition=2024`.
    Its tests live in `scripts/tests/test_verus_kernel.py`.
  Rationale: a positive run limited to the root module never checks the shipped
  body (`Surprises`). Shared spec functions stop mutant contracts drifting from
  the shipped one. Date/Author: 2026-11-11, planning agent.
- DL-14. Executable identity.
  Decision: the identity of `add` over I64 is a tuple of:
  - catalogue id `V001`;
  - `OperationId::add()` with `name() == "add"` and
    `catalogue_id() == "V001"`;
  - dtype `I64`;
  - symbol `combobulate_kernel::elementwise_add::add_i64_into`;
  - the structural executable digest of `src/elementwise_add.rs`;
  - the specification digest of `verus/elementwise_add_contract.rs`;
  - semantic policy `checked-i64`.
  The tuple is recorded in the Verus observations' `provenance.json`. The
  facade routes every `OperationId` to its kernel through one crate-private
  dispatch function, and a unit test enforces that mapping. Verified kernels
  live one per file, so a later `sub` or `mul` (2.2.1) cannot stale the `add`
  digest. Rationale: technical design §17.2 asks for typed symbol and
  specification bindings plus revision fingerprints. B01 asks for matched
  executable and specification identity. Date/Author: 2026-11-11, planning
  agent.

## Outcomes & retrospective

Not started. Record at each milestone boundary and at completion. At
completion, add a "Step 1.2 finding" that the completion record cites, stating:

- the fixture's `cargo tree` closure (expected: `combobulate` and
  `combobulate-kernel` only);
- that the ordinary path needs neither the `macros` nor the `polars` feature;
- that no `Fn` trait is implemented and the fixture uses no closures;
- the `Cargo.lock` change (`proptest`, dev-only);
- that AC-04 needs no re-measurement, because no shipped dependency changed.

## Context and orientation

The repository root is the facade package `combobulate` (`src/`):

- `src/lib.rs` (50 lines) forbids `unsafe`, declares `mod profile`, and
  declares `pub(crate) mod polars_backend` under `cfg(feature = "polars")`. It
  exports `BuildProfile`, `BackendProbeError` and a hidden
  `polars_backend_probe`.
- `src/profile.rs` defines `BuildProfile`, a report of compiled features.
- `src/polars_backend.rs` is the crate-private Polars wiring probe. Its
  `fold_collected` and `from_polars` show the house pattern for keeping error
  arms testable.

`crates/combobulate-kernel/src/lib.rs` is the `#![no_std]` kernel. Its only
item is `TargetFacts`, and it declares `#[cfg(kani)] extern crate kani;`.
`crates/combobulate-macros` exports nothing.

Terms:

- Value (materialized value): an `Array` holding an actual buffer.
- Expression handle: an `AExpr`, a cheap cloneable reference to an immutable
  graph node that denotes a deferred result. It holds no result.
- Descriptor: a reusable operation, `identity()` (a `Unary`) or `add()` (a
  `Binary`). Applying a descriptor builds a graph node and never executes a
  kernel.
- Preparation: `AExpr::prepare(&NativeExecutor)` validates static facts (here,
  equal vector lengths) and returns a `PreparedPlan` or a preparation-stage
  `ExpressionError`.
- Execution: `PreparedPlan::execute()` evaluates the plan, returning a new
  `Array` or an execution-stage `ExpressionError`. `AExpr::collect()` is
  preparation plus execution with the default executor.
- Denotation: the mathematical meaning of an expression, defined in
  `Verification plan` and recorded durably as SC-12 and technical design §8.
- Single-root Verus wiring: production source carries
  `#[cfg_attr(verus_keep_ghost, verus_spec(...))]` attributes that ordinary
  builds ignore. A proof root imports the production module with
  `#[path = ...]`, and `prover-tools verus run --proof-file` verifies it
  (ADR-0010). The worked example is
  `tools/verifier-fixtures/verus-wiring-probe/`.
- Seeded mutant: a deliberately wrong function under the shipped
  specification. It must be rejected at the clause it targets, and only there.
  It is the negative control showing the specification can reject a wrong body.

Gates (see `AGENTS.md` and the `Makefile`):

- `make check-fmt` runs rustfmt and `mdtablefix --check`.
- `make lint` runs rustdoc, Clippy for each gate profile, Whitaker and the
  Python lint.
- `make test` runs nextest and doctests for each profile.
- `make markdownlint`, `make nixie`, `make spelling` and `make design-check`
  are the documentation and governance gates.

Verus tooling: `make install-verus` installs Verus 0.2026.09.06.8dea4a2 (Rust
1.98.0, Z3 4.16.0, vstd `=0.0.0-2026-09-06-0133`). `$(PROVER_TOOLS)` is
`uv tool run --from git+…rust-prover-tools.git@<REF> prover-tools`.

Test patterns to copy:

- `src/profile.rs`: `rstest` cases with messages.
- `tests/build_profiles.rs` with `tests/features/build_profiles.feature`:
  `rstest-bdd` 0.6, `#[scenario(path, name)]` bindings, `insta` snapshots in
  `tests/snapshots/`.
- `tests/native_consumer_e2e.rs` with `tools/fixtures/native-consumer/`: a
  standalone consumer built with `--locked --offline`.
- `tests/workspace_kernel_boundary.rs`: `googletest` matchers.
- `tests/prover_tools_contract.rs`: the contract for verifier Make targets,
  using fake helpers.

Documentation and skills:

- `docs/technical-design.md` §§4, 5.1, 6.1, 7, 8 and 17.
- `docs/language-reference.md` rows V001, V032, E002, E004, E005, E014 and
  E017.
- ADR-0005, ADR-0006, ADR-0007, ADR-0009 and ADR-0010.
- `docs/testable-bets.md` (B01, B02).
- `docs/evidence-and-decision-records.md`.
- `docs/developers-guide.md`: "Test timeouts", "Workspace layout and module
  ownership", and "Verifier capability probes".
- `docs/rust-testing-with-rstest-fixtures.md`,
  `docs/rstest-bdd-users-guide.md` and `docs/rust-doctest-dry-guide.md`.
- `docs/reliable-testing-in-rust-via-dependency-injection.md`.
- `docs/complexity-antipatterns-and-refactoring-strategies.md`.
- Skills: start with `rust-router`, then:
  - `rust-types-and-apis` and `rust-memory-and-state` for `Arc` sharing and
    the iterative `Drop`;
  - `verus` and `proptest`;
  - `rust-unit-testing` and `nextest`;
  - `execplans` and `en-gb-oxendict-style`.

## Conformance basis

Upstream artefacts at commit `b873322`:

- Terms of reference revision 0.2 (6 October 2026): phase-1 goals G1, G2, G6,
  G7 and G8 (§6), and G3 and G4, which R3 and R4 trace to.
- Technical design revision 0.2 (6 October 2026), as amended through 1.2.1:
  - requirements R2, R3, R4, R8 and R9;
  - §4.1 (conceptual types and ownership), §5.1 (agreement), §6.1 (checked
    I64), §7 (ordinary application spelling) and §8 (lifecycle);
  - §17.1, §17.2, §17.3, §17.5 and §17.7.
  - verification items V2, V14 and V20 (§14).
- Language reference revision 0.2 rows:
  - V001 `add` and V032 `identity`;
  - E002 `.apply`/`.then`, E004 `.prepare` and E005 `.collect`/`.execute`;
  - E014 (logical view, for later binding);
  - E017 `NativeExecutor::sequential()` (minimal preview only).
- ADR-0005, ADR-0006 (SC-01 to SC-11, amended here with SC-12), ADR-0007,
  ADR-0009 (MS-1, MS-4) and ADR-0010 (Verus wiring, proof allowlist).
- Decisions D06, D07 and D16.
- Bets B01 and B02.
- Proof obligations PF04 and PF05, traced through SC-12's `discharged_by`.

Trace links:

```plaintext
G2 -> R2 -> §5.1, §6.1 -> SC-12 -> EP-M1 -> contract_cases EX89+ (Python model, wrapping-add mutation)
G2 -> R2 -> §6.1 -> SC-12 -> EP-M2 -> verus: k1..k5 on add_i64_into (+ mutants rejected)
G2 -> R2 -> §8 -> SC-12 -> EP-M4 -> FACADE-1 refinement property; FACADE-2 static failures; FACADE-6 staging
G3 -> R3 -> §4.1 -> EP-M3/EP-M5 -> fixture native-consumer/ordinary_application (non-generic public names)
G4 -> R4 -> §4.1, V032 -> EP-M3/EP-M4 -> FACADE-3 no unnecessary copies
G7 -> R8 -> §17.1, §17.7 -> B01 -> EP-M2 -> make verus-kernel; widened VO-6 (no substitute body)
G7 -> R9 -> §17.2 -> DL-14 -> EP-M2/EP-M6 -> provenance.json identity tuple; dispatch unit test
B02 -> R9 -> EP-M5 -> public-only consumer fixture (ahead of 1.2.5)
```

## Verification plan

### Abstract model (specified first, recorded as SC-12 and technical design §8)

Values. An `Array` denotes `(I64, s)` with `s` a finite sequence of integers,
each in `[i64::MIN, i64::MAX]`, and visible shape `[|s|]`. Every element is
valid. Nullability, scalars (shape `[]`) and scalar extension belong to 2.1.1.
This task's values are rank-one vectors only, including the empty vector `[0]`.

Expressions, with the partial static length model `len : Expr -> Option<usize>`
and the dynamic denotation `⟦·⟧`:

```plaintext
len(input a)        = Some(|a.s|)
len(identity(e))    = len(e)
len(add(l, r))      = Some(m)   if len(l) = Some(m) = len(r)
                    = None      otherwise
mismatch(n)        iff n = add(l, r), len(l) = Some(a), len(r) = Some(b), a ≠ b
static(e)           = mismatch nodes of e, each once, in first-completion
                      left-first post-order

⟦input a⟧           = Ok(a.s)
⟦identity(e)⟧       = ⟦e⟧
⟦add(l, r)⟧         = ⟦l⟧ >>= λx. ⟦r⟧ >>= λy. addv(x, y)
addv(x, y)          = Err(IntegerOverflow{p}), p the least i with
                      x[i] + y[i] ∉ [i64::MIN, i64::MAX], if such i exists
                    = Ok([x[0]+y[0], …, x[n-1]+y[n-1]])   otherwise
```

`>>=` propagates the first `Err`, so the left operand's failure wins. A shared
node has one denotation however often it is referenced.

Lifecycle contract:

- `prepare(e)` is `Err(Preparation, static(e))` when `static(e)` is
  non-empty, otherwise `Ok(plan_e)`. Preparation never evaluates `⟦·⟧`.
- `execute(plan_e)` is `⟦e⟧`. `⟦e⟧ = Err(f)` becomes `Err(Execution, [f])`.
- `collect(e)` is `prepare(e, sequential)` followed by `execute`.
- Frame: no operation mutates an input `Array`, and a failed execution
  publishes no output.
- Sharing: when `e` is `input a` under any number of identities, the result's
  buffer is `a`'s buffer.
- Termination: handles are immutable and acyclic by construction. Preparation
  visits each distinct node once, and execution runs one step per distinct node.

Success witnesses:

- `[1,2,3] + [10,20,30] = [11,22,33]`;
- `[] + [] = []`;
- `[i64::MAX] + [0] = [i64::MAX]`;
- `[i64::MIN] + [0] = [i64::MIN]`;
- identity of `[7]` shares its buffer.

### Kernel obligations (Verus, unbounded)

The function is
`combobulate_kernel::elementwise_add::add_i64_into(lhs: &[i64],
rhs: &[i64], out: &mut [i64]) -> Result<(), AddFailure>`,
with `AddFailure = LengthMismatch | Overflow { position: usize }`. Let
`same_len := lhs@.len() == rhs@.len() && rhs@.len() == old(out)@.len()`, let
`in_range(i) := i64::MIN <= lhs@[i] + rhs@[i] <= i64::MAX` over `int`, and let
`all_in_range := forall|i| 0 <= i < lhs@.len() ==> in_range(i)`. Each clause is
its own `ensures` line, so a failure can be attributed to it:

- K0. Length preserved: `final(out)@.len() == old(out)@.len()`.
- K1. Success relation (`plaintext` below).
- K2. Success condition: `same_len && all_in_range ==> r is Ok`. With K1,
  `Ok` holds exactly when the premise holds, which rules out an always-`Err`
  body.
- K3. Length failure: `r matches Err(LengthMismatch) <==> !same_len`.
- K4. First overflow (`plaintext` below).
- K5. Frame: `r is Err ==> final(out)@ == old(out)@`.
- K6. Safety and termination: every index is in bounds, the counters never
  overflow, and both loops terminate with `decreases n - i`. These are
  obligations Verus checks while verifying the body, and they make DL-8 sound.

```plaintext
K1: r is Ok ==> same_len && all_in_range
      && forall|i| 0 <= i < lhs@.len() ==> final(out)@[i] == lhs@[i] + rhs@[i]
K4: r matches Err(Overflow { position }) ==> same_len && position < lhs@.len()
      && !in_range(position) && forall|i| 0 <= i < position ==> in_range(i)
```

Expected loop shapes are below. Exact `old`/`final` spellings and any
quantifier triggers are settled in attempt 1 and recorded in
`Surprises & discoveries`. Pass 1 has the invariant `i <= n`, the length
equalities, `forall|j| 0 <= j < i ==> in_range(j)` and `out@ == old(out)@`, and
returns `Overflow { position: i }` at the first `None` from `checked_add`. Pass
2 has the invariant `all_in_range`, the length equalities,
`forall|j| 0 <= j < i ==> out@[j] == lhs@[j] + rhs@[j]`, and writes
`lhs[i] + rhs[i]`, whose freedom from overflow follows from `all_in_range`.

The proof files are:

- `verus/elementwise_add_contract.rs`: open spec functions `k1` to `k5` over
  `(lhs, rhs, pre, post, r)`, and `lemma_contract_determinate`. That lemma
  states that two outcomes `(r, post)` both satisfying `k0` to `k5` for the same
  `(lhs, rhs, pre)` are equal. It proves the contract is complete, so the
  mutants below are a sanity sample rather than the only discrimination
  evidence.
- `verus/elementwise_add.rs` (positive root): includes the contract and the
  production file. It holds:
  - `add_i64_into_contract`, a wrapper that ensures `k0` to `k5` and calls the
    shipped function, showing that the production contract implies the
    exported specification;
  - proof-function witnesses that inhabit the premises of K1 (`[1,2,3]` plus
    `[10,20,30]`), K3 (lengths 2 and 1) and K4 (`[0, i64::MAX]` plus `[0, 1]`
    gives position 1);
  - the determinacy lemma.
- `verus/elementwise_add_mutants.rs`: wrappers around, or guarded edits of,
  the shipped call, each ensuring `k0` to `k5`.

| Mutant           | Wrong behaviour                                     | Clause that must reject it |
| ---------------- | --------------------------------------------------- | -------------------------- |
| M-err            | Always returns `Err(LengthMismatch)`                | K2 and K3                  |
| M-late           | Maps `Overflow{p}` to `Overflow{p+1}`               | K4                         |
| M-ok-on-overflow | Maps `Overflow` to `Ok(())`                         | K1                         |
| M-mismatch-write | Writes `out[0]` on the mismatch path when non-empty | K5                         |
| M-early-write    | Writes the wrapped sum at `out[p]`, then `Err`      | K5                         |

_Table 1: Seeded Verus mutants and their target clauses._

A body-tier mutant, M-wrap, copies `src/elementwise_add.rs` into a scratch
directory under `target/`, replaces `checked_add` with `wrapping_add`, and
verifies it under the positive root. It must fail at a loop invariant or K1.

Red step (EP-M2): `elementwise_add.rs` with the full contract and body
`Err(AddFailure::LengthMismatch)`. The positive run exits 1 with located
failures at the K2 and K3 lines of `add_i64_into`. That always-`Err` log is
kept as a negative control on the shipped item. The witnesses, lemma and mutant
verdicts already hold at this point, because they depend only on the
specification. Green: the real two-pass body fully verifies, and the mutant
verdicts are unchanged.

Rejection rule (`scripts/verus_kernel.py`). A mutant counts as rejected only
when all of the following hold:

- the exit status is 1;
- at least one error was reported;
- every error is a postcondition (or, for M-wrap, a loop-invariant) failure
  inside that mutant's own source region;
- the intended K line is among the failures.

Any type, syntax, precondition, arithmetic-overflow or unsupported-feature
error disqualifies the run. The positive pass requires exactly the pinned
`N verified, 0 errors`, with no partial-verification suffix.

Method rationale: Verus suits arbitrary-length sequence relations, loop
invariants and frame conditions (technical design §17.1). §17.1 also prefers
Kani for finite-width arithmetic. Here the finite-width behaviour reduces to
`checked_add`, whose vstd specification is exact (AXIOM-2). Kani could
cross-check AXIOM-2 against real `core` code, but only at `partial` level and
on a third compiler. That cross-check is deferred to 1.2.4, which owns product
Kani wiring. Runtime `rstest`, const-evaluation and `proptest` cases at
`i64::MIN`, `i64::MAX` and 0 exercise the shipped object code.

Non-vacuity:

- The witnesses inhabit the success, overflow and length-failure premises.
- The always-`Err` stub is rejected, as is every mutant at its own clause.
- The determinacy lemma shows no second outcome satisfies the contract.
- `scripts/trust_audit.py crates/combobulate-kernel/src/elementwise_add.rs`
  and each `crates/combobulate-kernel/verus/*.rs` file must report zero items.
  `trust_audit_check.py` enforces this through a product-proof-root list.

### Facade obligations (tests and properties)

The facade-obligation identifiers are FACADE-1 to FACADE-8. They are distinct
from the terms-of-reference goals G1 to G8.

- FACADE-1. Refinement to the denotation. Method: `proptest` in the
  `tests/ordinary_application.rs` binary.
  - Expressions are generated as `Vec<NodeSpec>` in which each node refers only
    to earlier indices. This gives sharing and shrinks well.
  - Each case draws up to four inputs with one common length (0-8). It injects
    a mismatched length at a set rate, and draws elements mostly from a small
    range, with boundary values (`i64::MIN`, `i64::MAX`, 0, ±1) as a minority.
  - DAGs have up to 12 nodes.
  - `collect(e)` must equal an independent test-side reference evaluator,
    which uses `i128` and memoizes by node index. It never calls the kernel.
    Task 1.2.3's independent runner later absorbs this oracle, so no reusable
    harness is built here.
  - Persistence: `failure_persistence: None`. A shrunk counterexample becomes a
    named `rstest` case.
  - Non-vacuity: a companion test runs the same strategy through
    `TestRunner::deterministic()` for 512 draws. It asserts minimum counts of:
    - `Ok` with length 2 or more;
    - `IntegerOverflow` with a position above 0;
    - two independent `ShapeAgreement` failures;
    - an `Ok` result through a shared subterm.
    Minimum counts are used because the random stream may change on a
    proptest upgrade.
  - Negative control: temporarily replacing the kernel call with a
    `wrapping_add` loop makes FACADE-1 fail. This is recorded once in `Artefacts`
    and not committed.
- FACADE-2. Static failure completeness (DL-9). Method: named `rstest` cases
  plus FACADE-1's generator. Cases:
  - one mismatch;
  - `add(add(a3, b2), c1)`, which reports one failure;
  - `add(add(a3, b2), add(c3, d2))`, which reports two failures in left-first
    order;
  - a mismatch below a shared node, which is reported once.
  Assertions use googletest `elements_are!` and `matches_pattern!`, with `..`
  for the `#[non_exhaustive]` variants.
- FACADE-3. No unnecessary copies. Method: `rstest` cases. Each compares
  `as_i64_slice().map(<[i64]>::as_ptr)`:
  - `Array::from_i64(vec)` has the `Vec`'s original data pointer, captured
    before the move.
  - Identity through `then`, through `apply`, through `collect`, and through
    `prepare` then `execute` returns the input's pointer.
  - After `add`, both inputs keep their pointers and contents, and the output
    pointer differs from each input.
  - Non-vacuity: the `add` case asserts inequality, so the comparison can
    fail.
- FACADE-4. Shared DAG evaluated once. `x0 = [1]` and
  `x(k+1) = add(x(k), x(k))`. At 62 levels `collect` returns `[2^62]`, and the
  63rd level returns `IntegerOverflow { position: 0 }`, both within nextest's
  default 60 s period. Without memoization the walk visits 2^62 nodes and never
  finishes. That is the negative control, recorded once by temporary mutation.
- FACADE-5. Deep chains. A left-leaning chain of 100,000 `add` nodes over `[1]`
  builds, formats with `{:?}`, prepares, executes to `[100_001]`, and drops. It
  runs on a thread with a 2 MiB stack (`std::thread::Builder::stack_size`).
  Recursive traversal, recursive `Debug` or the default `Arc` drop would
  overflow that stack, which is the negative control.
- FACADE-6. Staging. An expression whose execution overflows still prepares, and
  the failure appears only from `execute` with `stage() == Stage::Execution`. A
  length mismatch fails at `prepare` with `stage() == Stage::Preparation`.
  Method: `rstest` and the behaviour-driven development (BDD) scenarios below.
- FACADE-7. Public surface.
  - The extended `tests/native_consumer_e2e.rs` checks that the consumer
    fixture's `cargo tree` reaches no `polars`, `glam`, `kani`, `verus` or
    `vstd` package.
  - A unit test asserts `AExpr`, `Array`, `PreparedPlan` and
    `ExpressionError` are `Send + Sync`.
  - A unit test asserts no public type's `core::any::type_name` contains `<`.
  - Residual gap: there is no mechanical public-API snapshot. Generating
    rustdoc JSON in a test would compile the repository from a test body,
    which the developers' guide forbids. Reviewers inspect `cargo doc` output,
    and the gap is recorded.
- FACADE-8. Diagnostics and codes.
  - `insta` snapshots `Display` for every failure kind and both stages, in
    `tests/snapshots/ordinary_application__*.snap`.
  - Each snapshot test pairs a semantic assertion on `Failure::code()`.
  - A test reads `spec/semantic-contracts.json` and asserts every
    `Failure::code()` value is a registered error code.
  - `pretty_assertions::assert_eq` is used for slice comparisons throughout.

### Python contract model (EP-M1)

The Python model gains:

- new `contract_cases` EX89 onward, covering:
  - success;
  - empty;
  - both boundaries;
  - the first-overflow position, including a case where a later position also
    overflows;
  - `ShapeAgreement`;
- a `wrapping-add` seeded mutation in `elementwise_examples.py` that changes at
  least one recorded outcome.

`make design-check` evaluates them. This is the documentation model's evidence,
not the Rust implementation's.

### Axioms (trusted, not verified here)

- AXIOM-1. The pinned Verus (0.2026.09.06.8dea4a2) and Z3 4.16.0 are sound for
  the features used.
- AXIOM-2. The vstd specifications used match Rust semantics:
  - slice `len`;
  - slice index read and mutable index write;
  - `i64::checked_add`;
  - the `Option` and `Result` type specifications;
  - `i64::MIN` and `i64::MAX`.
  These are vstd `assume_specification` items outside workspace sources.
- AXIOM-3. Rust 1.98.0 (Verus, run with `--edition=2024`) and
  nightly-2026-11-06 (ordinary) give the same semantics to the kernel's
  `core`-only source. The kernel source compiles as a crate-root module in one
  build and as a `#[path]` submodule in the other, so it contains no `crate::`
  or `super::` path.
- AXIOM-4. `Arc::new(vec)` moves the `Vec` header without copying elements.
  FACADE-3 observes this directly by pointer equality, so nothing relies on the
  axiom unobserved.

### Where Verus is not used, and why

The graph handles, schedule construction and storage are facade plumbing over
`alloc`. They sit outside the kernel's `core`-only boundary, which is the only
boundary ADR-0010 wires for Verus. Their meaning is the abstract model above,
recorded as SC-12 and checked by FACADE-1 and FACADE-2 against an independent
oracle. PF04 (graph meaning and preparation refinement) machine-checks this
layer at 2.3.2, 2.3.5 and 4.2.3, once public logical models exist (E014,
1.2.5). Diagnostic formatting (FACADE-8) and fixture wiring (FACADE-7) carry no
proof obligation.

## Plan of work

- Stage A, understand and propose: this document. It passes through
  community-of-experts review and user approval.
- Stage B, red: each milestone begins with its failing tests, feature file,
  contract cases or Verus stub. Each red run is recorded with its expected
  failure reason.
- Stage C, green: the smallest implementation that turns each red artefact
  green, in milestone order.
- Stage D, refactor and document: separate refactoring commits once behaviour
  is green. EP-M6 holds the documentation work.

## Milestones and plateaus

### EP-M1: specify the denotation and contract

Outcome:

- `spec/semantic-contracts.json` gains `ShapeAgreement` and SC-12 (DL-4).
- `spec/examples.json` gains EX89 onward.
- `scripts/docs_validation/elementwise_examples.py` evaluates them, with the
  `wrapping-add` mutation.
- `scripts/tests/` cases cover the new handler.
- ADR-0006 carries a dated amendment.
- Technical design §8 gains a normative "Denotation of values and graphs"
  paragraph pointing at SC-12, and §6.1 cites SC-12 for checked add.
- V001's text cites SC-12, and the tables are regenerated.
- `docs/validation-results.json` is regenerated.

Requirements: R2, §8, B01/B02 proof-first clause ("specify denotation and
success witnesses first").

Acceptance evidence:

- Red: the new cases fail as "Unknown contract operation elementwise_add".
- Green: `make design-check` passes.
- The `wrapping-add` mutation changes an outcome and is caught.
- `make markdownlint` and `make spelling` pass.

Conformance check:

- No Rust code changes.
- `ShapeAgreement` is reused, not aliased.
- The closed error-code set changes only by that registration.

Recovery: the edits revert as a unit.

Remaining gaps: Rust implementation.

Compatibility decision: none.

### EP-M2 (prototyping): the verified kernel elementwise add

Outcome:

- `crates/combobulate-kernel/src/elementwise_add.rs` with `AddFailure` (with
  `#[cfg_attr(verus_keep_ghost, verus_verify)]`) and
  `pub const fn add_i64_into` (DL-7). It carries the K0-K5 contract and both
  loop invariants through `cfg_attr`.
- The kernel root declares `pub mod elementwise_add;`.
- The three Verus files from DL-13.
- `scripts/verus_kernel.py` with `scripts/tests/test_verus_kernel.py`.
- A `verus-kernel` Make target beside `verus-probe`, recorded in
  `tests/prover_tools_contract.rs`'s target list. Fake-helper cases there cover:
  - the positive argv and each mutant's argv;
  - an inflated verified count, which must fail;
  - an unlocated mutant diagnostic, which must fail.
- `trust_audit_check.py` lists the product proof roots as zero-trust subjects.
- `spec/toolchain-profiles.json`'s `proof-verus` record gains the new
  subjects.
- Kernel in-crate tests are plain `#[test]` functions using only `core`, plus a
  `const` evaluation of `add_i64_into` (B01's const-evaluation clause).
- A new root test binary `tests/kernel_elementwise_add.rs` holds the
  parameterized `rstest` boundary cases, because the kernel may not take
  dev-dependencies.

Requirements: R2, R8; B01 (one body, runtime, const and Verus agreement on the
same source).

Go/no-go: the Verus tolerance applies. Possible revisions are a different loop
shape, a different specification phrasing, or narrowing the claim. Each needs
approval.

Acceptance evidence:

- `make verus-kernel` exits 0. It prints the pinned verified count, each
  mutant rejected at its located clause, and M-wrap rejected.
- The proof-cost measurement is recorded against the AC-01-derived trigger.
- The trust audit of each file reports zero items.
- `make check-fmt`, `make lint` and `make test` pass.
- `make design-check` passes after regenerating the validation report.

Conformance check:

- The kernel stays `no_std` without `alloc` and has no dependency (VO-1,
  VO-6).
- The proof roots import the shipped file by `#[path]`.
- The only new suppression is DL-8's kernel entry, plus the pre-approved
  `missing_const_for_fn` fallback if it is needed.

Recovery: the milestone is additive and reverts as a unit.

Remaining gaps: facade use (EP-M4), the formal workflow step and the widened
VO-6 (EP-M5).

Compatibility decision: none.

### EP-M3: values and expression handles

Outcome:

- `src/array.rs` defines `Array`, `Dtype` and the private `Storage`.
- `src/expr.rs` defines `AExpr`, `Unary`, `Binary`, `OperationId`,
  `identity`, `add`, and the crate-private `Node`. `Node` has:
  - its kind enum;
  - cached length and `mismatch_below`;
  - the iterative `Drop` built on `Arc::into_inner`;
  - a handwritten non-recursive `Debug`.
- The root re-exports them.

The `Drop` design is a private `NodeKind` without `Drop`, which can therefore
be destructured. `Node::drop` moves operand handles into a `Vec` work list and
repeatedly takes `Arc::into_inner` of each, detaching that node's children in
turn. A node is detached by `mem::replace` with an inert leaf, using
`Arc::default()`, which allocates nothing.

Requirements: R3, R4; V032, E002.

Acceptance evidence: unit `rstest` cases for construction, `len`, `is_empty`,
`dtype`, identity folding, FACADE-3 for construction and identity, and
FACADE-5's build, format and drop parts. Doctests pass in both profiles, and
the gates pass.

Conformance check:

- Every public type is non-generic.
- No kernel is invoked during construction.
- No Polars path appears.

Recovery: additive; revert the two modules and their re-exports together.

Remaining gaps: `prepare`, `execute` and `collect`.

Compatibility decision: none.

### EP-M4: preparation, execution, and errors

Outcome:

- `src/error.rs` defines `ExpressionError`, `Failure` and `Stage`, and a
  `const fn failure_from_kernel(AddFailure, lhs_len, rhs_len) -> Failure`
  unit-tested for both arms.
- `src/plan.rs` defines `NativeExecutor`, `PreparedPlan`, `Step`, `Slot`, the
  iterative schedule builder (DL-12), and the execution loop calling
  `add_i64_into` through the dispatch function (DL-14).
- `AExpr::prepare`, `AExpr::collect` and `PreparedPlan::execute`.
- `tests/ordinary_application.rs` is the second and last new test binary. It
  holds:
  - FACADE-1 and its classification companion;
  - FACADE-2, FACADE-3, FACADE-4, FACADE-5 and FACADE-6;
  - the FACADE-8 snapshots and the code-registration test;
  - the BDD bindings for `tests/features/ordinary_application.feature`.
  Its submodules sit under `tests/ordinary_application/` and are loaded by
  `#[path]`.
- `proptest` is added (DL-6).

Requirements: R2, R4, R9; E004, E005, E017 (minimal); SC-12.

Acceptance evidence:

- Every new test passes in both profiles.
- Each test was observed red first: missing items fail compilation, and
  behaviour assertions fail against a skeleton whose `execute` returns `Err`.
- The gates pass, including the regenerated validation report.

Conformance check:

- Preparation runs no kernel (FACADE-6).
- Execution uses only the dispatch path.
- Codes are registered (FACADE-8).

Recovery: additive over EP-M3; revert the modules and tests together.

Remaining gaps: the fixture, wiring and documentation.

Compatibility decision: none.

### EP-M5: public consumer fixture, boundaries, and workflow wiring

Outcome:

- `tools/fixtures/native-consumer/src/bin/ordinary_application.rs` runs the
  `Purpose` program and prints three lines (see `Artefacts`). The fixture's
  `main.rs`, `Cargo.toml`, `Cargo.lock`, `nested-cargo-allow:` header and
  Dependabot entry are unchanged.
- `tests/native_consumer_e2e.rs`:
  - one `built()` helper returns both binaries' outputs from the single nested
    build, with binaries selected by target name from the JSON build messages;
  - the JSON helpers move to `tests/support/` to stay under 400 lines;
  - a lookup unit case covers two `bin` artefacts in either order;
  - the new output is compared with
    `tests/snapshots/native_consumer_e2e__ordinary_application.snap`.
- VO-6 is widened:
  - `#![no_std]` and the deny rules still apply to `lib.rs` only;
  - every kernel `.rs` file must not contain `extern crate alloc`,
    `extern crate std`, an `allow`, `warn` or `expect` of the two lints,
    `cfg(not(verus_keep_ghost))`, or `cfg(verus_keep_ghost)` or `cfg(kani)` on
    a `fn` item;
  - seeded fixtures under `tests/fixtures/` (not named `main.rs`) are
    rejected.
- `.github/workflows/formal.yml` runs `make verus-kernel` after
  `make install-verus` and uploads the logs. Its header comment is updated, and
  `tests/formal_workflow_contract.rs` gains a check of that step order.
- `docs/developers-guide.md` "Test timeouts" records `native_consumer_e2e` as
  an existing, bounded exception to the no-compiling-test-bodies rule.

Requirements: B02 (public-only consumer, ahead of 1.2.5); the roadmap success
criterion.

Acceptance evidence:

- `cargo nextest run --test native_consumer_e2e`,
  `--test workspace_kernel_boundary` and `--test formal_workflow_contract` pass.
- The gates pass.
- The hosted `build-test` time on the draft PR is recorded against its
  eight-minute budget.

Conformance check:

- The fixture names every public type without type arguments.
- No proof package enters either ordinary profile (VO-3).
- The formal workflow still gates no merge.

Recovery: the fixture binary and e2e changes revert together, and so do the
workflow edit and its contract.

Remaining gaps: documentation and completion.

Compatibility decision: none.

### EP-M6: documentation, completion, and roadmap tick

Outcome:

- `docs/adrs/adr-0011-minimal-value-and-expression-representation.md`
  (DL-10).
- Technical design §3 and §4.1 name the facade's public items and the
  `elementwise_add` kernel module, and reference ADR-0011.
- `docs/users-guide.md` gains a "Build and run an array expression" section.
  It covers:
  - the `Purpose` example;
  - error stages and codes;
  - copy and sharing rules;
  - current limits: I64 vectors only, no nulls, no scalars, and a "minimal
    preview" executor;
  - the Verus wording from DL-1.
  The section also corrects the "not yet implemented" status lines.
- `docs/developers-guide.md` gains:
  - ownership-table rows and a re-use policy for `elementwise_add`: only the
    facade's dispatch function calls it, and each new kernel gets its own file,
    `verus_spec`, contract file, mutants and `verus_kernel.py` entry;
  - a "Product Verus proofs" subsection on `make verus-kernel`, the proof
    roots, the rejection rule and observations.
- `docs/repository-layout.md` gains rows for the new paths.
- `docs/contents.md` lists this plan and ADR-0011.
- The captured observations and `provenance.json` under
  `tools/verifier-fixtures/verus-kernel/` hold the DL-14 identity tuple.
- `spec/task-completion.json` gains a 1.2.2 entry. It cites D06, D07 and D16,
  and lists file artefacts, never directories.
- `docs/roadmap.md` ticks 1.2.2, and `scripts/export_roadmap.py` refreshes
  `spec/roadmap.json`.
- `docs/validation-results.json` is regenerated.
- The `Outcomes` Step 1.2 finding.

Acceptance evidence: `make design-check`, `make markdownlint`, `make nixie`,
`make spelling`, `make check-fmt`, `make lint`, `make test` and
`make verus-kernel` pass on the final head.

Conformance check:

- Every DL item appears in ADR-0011, the ADR-0006 amendment or the design.
- No upstream assumption is silently changed.
- Trace links resolve to real tests and files.

Recovery: documentation edits revert freely. The roadmap tick is the last
commit and reverts alone.

Remaining gaps:

- Verus evidence admission at PF05.proof@2.3.5 (DL-1).
- Nulls, scalars and other dtypes (2.1.x).
- Freeing intermediates after last use (2.3.5).

Compatibility decision: none.

## Concrete steps

Run every command from the worktree root, sequentially and never in parallel.
Tee long output to
`/tmp/$ACTION-combobulate-1-2-2-minimal-ordinary-application-path.out`.

```sh
make install-verus      # once per machine; checksum-verified and idempotent
make verus-kernel 2>&1 | tee /tmp/verus-combobulate-1-2-2-minimal-ordinary-application-path.out
for f in crates/combobulate-kernel/src/elementwise_add.rs crates/combobulate-kernel/verus/*.rs; do
  uv run --script scripts/trust_audit.py "$f"
done
```

Expected `make verus-kernel` tail. `N` is pinned after the first green run; it
is recorded, not predicted:

```plaintext
positive: verification results:: N verified, 0 errors
mutant m_err: rejected at K2, K3 (elementwise_add_mutants.rs:<line>)
mutant m_late: rejected at K4 (elementwise_add_mutants.rs:<line>)
mutant m_ok_on_overflow: rejected at K1 (elementwise_add_mutants.rs:<line>)
mutant m_mismatch_write: rejected at K5 (elementwise_add_mutants.rs:<line>)
mutant m_early_write: rejected at K5 (elementwise_add_mutants.rs:<line>)
body mutant wrap: rejected at loop invariant (elementwise_add.rs:<line>)
```

Every milestone runs these, in this order:

```sh
make check-fmt 2>&1 | tee /tmp/check-fmt-combobulate-1-2-2-minimal-ordinary-application-path.out
make lint 2>&1 | tee /tmp/lint-combobulate-1-2-2-minimal-ordinary-application-path.out
make test 2>&1 | tee /tmp/test-combobulate-1-2-2-minimal-ordinary-application-path.out
```

Every milestone also runs the documentation and governance gates and
regenerates the validation report:

```sh
make fmt
make markdownlint 2>&1 | tee /tmp/markdownlint-combobulate-1-2-2-minimal-ordinary-application-path.out
make nixie
make spelling
uv run python scripts/generate_reference.py          # when vocabulary.json changed
python scripts/check_docs.py --as-of "$(git log -1 --format=%cs)" --write
make design-check PYTHON="uv run --no-project --python 3.14 --with-requirements scripts/requirements.txt python" \
  2>&1 | tee /tmp/design-check-combobulate-1-2-2-minimal-ordinary-application-path.out
```

The exact interpreter invocation for the two Python scripts follows their
existing Make recipes; check the `Makefile` before running them. After each
green step, commit with an imperative subject naming the milestone, for example
`Specify elementwise checked addition as SC-12 (1.2.2, EP-M1)`.

## Validation and acceptance

Red, green and refactor evidence for each milestone:

- EP-M1. Red: the contract cases fail with "Unknown contract operation".
  Green: `make design-check` passes, and the mutation changes an outcome.
- EP-M2. Red: the always-`Err` stub fails Verus at K2 and K3, and the
  `rstest` success cases fail on assertions. Green: full verification, all
  mutants rejected, and the tests pass.
- EP-M3. Red: unit tests and doctests naming `Array`, `AExpr`, `identity` and
  `add` fail to compile. Green: they pass.
- EP-M4. Red: every BDD scenario fails, and FACADE-1 fails with a counterexample
  against a skeleton whose `execute` returns `Err`. Green: all pass.
- EP-M5. Red: the e2e test reports that the `ordinary_application` binary
  was not found, and the seeded VO-6 submodule fixture passes the old scanner,
  which the new test rejects as a vacuous scan. Green: both pass.

BDD feature (`tests/features/ordinary_application.feature`, bound with
`#[scenario(path, name)]`, without `cfg` gating; vector placeholders parse
through a `FromStr` newtype into `ScenarioState` slots):

```gherkin
Feature: Ordinary application of identity and add to I64 vectors

  Scenario: Identity shares the input buffer
    Given an I64 vector [1, 2, 3]
    When identity is applied and the expression is collected
    Then the result is [1, 2, 3]
    And the result shares the input buffer

  Scenario: Adding two vectors after explicit preparation
    Given an I64 vector [1, 2, 3]
    And another I64 vector [10, 20, 30]
    When add is applied, the expression is prepared, and the plan is executed
    Then the result is [11, 22, 33]
    And both inputs are unchanged

  Scenario: Adding empty vectors
    Given an I64 vector []
    And another I64 vector []
    When add is applied and the expression is collected
    Then the result is []

  Scenario: Mismatched lengths fail at preparation
    Given an I64 vector [1, 2, 3]
    And another I64 vector [1, 2]
    When add is applied and the expression is prepared
    Then preparation fails with ShapeAgreement between lengths 3 and 2

  Scenario: Overflow fails at execution, not preparation
    Given an I64 vector [0, 9223372036854775807]
    And another I64 vector [0, 1]
    When add is applied and the expression is prepared
    Then preparation succeeds
    And executing the plan fails with IntegerOverflow at position 1
```

Quality criteria:

- Tests: `make test` passes in both profiles.
- Verification: `make verus-kernel` verifies K0-K6, the wrapper, the
  witnesses and the determinacy lemma, and rejects every mutant at its clause.
  FACADE-1 to FACADE-8 pass.
- Lint and format: `make lint` and `make check-fmt` pass, with no
  suppressions beyond DL-8 and the pre-approved `missing_const_for_fn` fallback.
- Documentation: `make markdownlint`, `make nixie` and `make spelling` pass.
- Governance: `make design-check` passes.
- Performance: no benchmark gate. FACADE-4 and FACADE-5 complete within
  nextest's default period. The hosted `build-test` time is recorded.

## Idempotence and recovery

Every step can be repeated. `make install-verus` checks checksums and skips a
present installation. Generated files are regenerated, never hand-edited:
`spec/roadmap.json`, the language-reference tables, `typos.toml` and
`docs/validation-results.json`.

If a milestone fails midway, reset to its last green commit with
`git reset --hard <sha>` on this branch only, after confirming the working tree
holds nothing worth keeping. Never use a bare `git stash`, because the stash
stack is shared across worktrees. Scratch copies for M-wrap live under
`target/`, which is ignored, and are recreated on every run.

## Artefacts and notes

Expected fixture output from the `ordinary_application` binary:

```plaintext
identity: [1, 2, 3] (shared buffer: true)
add: [11, 22, 33]
collect: [11, 22, 33]
```

Focused confirmation that the record-digest failures are interpreter-specific
(run under Python 3.14, matching `design.yml`):

```sh
uv run --no-project --python 3.14 --with-requirements scripts/requirements.txt \
  python -m pytest -q scripts/tests/test_verifier_record_digests.py
# 7 passed, 1 warning, 43 subtests passed
```

Negative-control transcripts are added here as each is observed:

- FACADE-1 with `wrapping_add`;
- FACADE-4 without memoization;
- FACADE-5 with derived `Debug`;
- the Verus always-`Err` stub;
- each Verus mutant.

## Interfaces and dependencies

Kernel, `crates/combobulate-kernel/src/elementwise_add.rs` (`core` only):

```rust
#[cfg(verus_keep_ghost)]
use vstd::prelude::*;

/// Why an elementwise I64 addition did not complete. `out` is unchanged in
/// every case.
#[cfg_attr(verus_keep_ghost, verus_verify)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AddFailure {
    /// The operand and output lengths differ.
    LengthMismatch,
    /// `lhs[position] + rhs[position]` is outside I64, and every earlier
    /// position is in range.
    Overflow { position: usize },
}

/// Add `lhs` and `rhs` element-wise into `out` with checked I64 arithmetic.
#[cfg_attr(verus_keep_ghost, verus_verify, verus_spec(r => ensures /* K0-K5, one line each */))]
#[expect(clippy::indexing_slicing, reason = "…")]
pub const fn add_i64_into(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> Result<(), AddFailure>;
```

Facade, re-exported from `src/lib.rs`. Every type is non-generic, every
non-`Result` public function is `#[must_use]`, and every `Result` returner has
an `# Errors` section:

```rust
// src/array.rs
#[non_exhaustive] #[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Dtype { I64 }

#[derive(Clone, Debug)]
pub struct Array { /* storage: Storage — private enum Storage { I64(Arc<Vec<i64>>) } */ }
impl Array {
    pub fn from_i64(values: Vec<i64>) -> Self;
    pub const fn dtype(&self) -> Dtype;
    pub fn len(&self) -> usize;
    pub fn is_empty(&self) -> bool;
    pub fn as_i64_slice(&self) -> Option<&[i64]>;
    pub fn expr(&self) -> AExpr;
}

// src/expr.rs
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct OperationId { /* name: &'static str, catalogue_id: &'static str */ }
impl OperationId {
    pub const fn name(self) -> &'static str;          // "identity", "add"
    pub const fn catalogue_id(self) -> &'static str;  // "V032", "V001"
}

#[derive(Clone)] pub struct AExpr { /* Arc<Node> */ }     // handwritten, non-recursive Debug
#[derive(Clone, Debug)] pub struct Unary { /* private kind */ }
#[derive(Clone, Debug)] pub struct Binary { /* private kind */ }

pub const fn identity() -> Unary;
pub const fn add() -> Binary;
impl Unary  { pub fn apply(&self, operand: &AExpr) -> AExpr; pub const fn operation_id(&self) -> OperationId; }
impl Binary { pub fn apply(&self, lhs: &AExpr, rhs: &AExpr) -> AExpr; pub const fn operation_id(&self) -> OperationId; }
impl AExpr {
    pub fn then(&self, operation: &Unary) -> AExpr;   // = operation.apply(self)
    pub fn prepare(&self, engine: &NativeExecutor) -> Result<PreparedPlan, ExpressionError>;
    pub fn collect(&self) -> Result<Array, ExpressionError>;
}

// src/plan.rs
#[non_exhaustive] #[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct NativeExecutor {}
impl NativeExecutor { pub const fn sequential() -> Self; }

#[derive(Clone)] pub struct PreparedPlan { /* steps: Box<[Step]> */ }   // handwritten Debug
impl PreparedPlan { pub fn execute(&self) -> Result<Array, ExpressionError>; }

// src/error.rs
#[non_exhaustive] #[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stage { Preparation, Execution }

#[non_exhaustive] #[derive(Clone, Debug, PartialEq, Eq)]
pub enum Failure {
    #[non_exhaustive] ShapeAgreement { operation: OperationId, lhs_len: usize, rhs_len: usize },
    #[non_exhaustive] IntegerOverflow { operation: OperationId, position: usize },
}
impl Failure { pub const fn code(&self) -> &'static str; }  // registered error code

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExpressionError { /* stage: Stage, failures: Box<[Failure]>; non-empty; Execution => one */ }
impl ExpressionError { pub const fn stage(&self) -> Stage; pub fn failures(&self) -> &[Failure]; }
impl core::fmt::Display for ExpressionError {}
impl core::error::Error for ExpressionError {}
```

The existing items `BuildProfile`, `BackendProbeError` and
`polars_backend_probe` are unchanged.

Dependencies:

- New dev-dependency `proptest = "1.12.0"` on the root package (DL-6).
- No new runtime dependency.
- No kernel dependency of any kind.
- Verus and vstd stay outside every Cargo manifest (ADR-0010).

Make: a new `verus-kernel` target beside `verus-probe` in `.PHONY`. It runs
`uv run --script scripts/verus_kernel.py --prover-tools '$(PROVER_TOOLS)'`. It
builds no Cargo target, so it stays outside the gate-order and build-standard
contracts. Its own contract lives in `tests/prover_tools_contract.rs`.

## Revision note

- 2026-11-11, initial draft from Wyvern reconnaissance.
- 2026-11-11, revision 2 after community-of-experts review:
  - Verus proof: separate positive and mutant roots, so the shipped body is
    actually verified; one `ensures` line per clause; shared `k0` to `k5`
    spec functions with a determinacy lemma; a sharper mutant set, adding
    M-early-write and a body-tier M-wrap; a coherent red step; a trust audit
    of the proof roots; `const fn`, `--edition=2024` and no `crate::` paths.
  - Rust API: the error is renamed `ExpressionError` (`error_impl_error`).
    `Arc<Vec<i64>>` storage gives zero-copy `from_i64(Vec)`. Additions are a
    handwritten non-recursive `Debug`, an iterative `Drop` via
    `Arc::into_inner`, a linear schedule (DL-12), a partial length model
    (DL-9), a `#[non_exhaustive]`, non-`Copy` executor, and
    `failure_from_kernel`.
  - Tests and governance:
    - no kernel dev-dependencies (VO-1); at most two new test binaries;
    - `docs/validation-results.json` regenerated per milestone;
    - a new `scripts/verus_kernel.py` instead of editing digest-bound scripts;
    - observations under `tools/verifier-fixtures/verus-kernel/`;
    - `ShapeAgreement` instead of a new alias;
    - `prover_tools_contract.rs` as the Make contract;
    - FACADE-1 generator and classification redesign; BDD binding details;
    - realistic size tolerances.
  - Design conformance: SC-12 makes the denotation durable (EP-M1 is now the
    proof-first specification milestone). The incorrect SC-04 citation is
    corrected. The proof-cost trigger now uses AC-01's frozen thresholds. A
    two-pass kernel removes the SC-09 and PF05 partial-write conflict.
    Admission is handed to PF05.proof@2.3.5 instead of 1.2.4. The executable
    identity tuple (DL-14), the Step 1.2 finding, identifier hygiene
    (FACADE-1 to FACADE-8 versus ToR G1-G8) and the E017 scope note are
    added.
  Effect on remaining work: one more milestone (EP-M1), a larger but bounded
  file count, and no change to the public success criterion.
