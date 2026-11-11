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
use combobulate::{add, identity, Array, NativeExecutor};

let xs = Array::from_i64(vec![1, 2, 3]);
let ys = Array::from_i64(vec![10, 20, 30]);

let expression = add().apply(&xs.expr().then(&identity()), &ys.expr());
let plan = expression.prepare(&NativeExecutor::sequential())?;
let sum = plan.execute()?;
assert_eq!(sum.as_i64_slice(), Some(&[11, 22, 33][..]));

let same = xs.expr().then(&identity()).collect()?;
assert_eq!(same.as_i64_slice().map(<[i64]>::as_ptr),
           xs.as_i64_slice().map(<[i64]>::as_ptr));
# Ok::<(), combobulate::Error>(())
```

The program constructs an `I64` vector, builds a deferred expression with
`identity` and `add`, prepares it against an explicit executor, and executes
it. It also collects in one step with the default executor. No public type has
a generic parameter, and `identity` returns the very buffer it was given. The
element-wise `add` arithmetic runs in one kernel function. Verus proves that
function's success relation, success condition, first-overflow report and
mutation frame against the shipped body.

Observable success is:

1. A standalone fixture binary under `tools/fixtures/native-consumer/` runs.
   It builds with `default-features = false` and prints the identity and add
   results. `tests/native_consumer_e2e.rs` builds it, runs it, and compares its
   output.
2. `make verus-kernel` verifies the kernel proof root. Every seeded mutant
   fails at its own postcondition.
3. `make check-fmt`, `make lint`, `make test`, `make markdownlint`,
   `make design-check` and `make spelling` pass.

## Constraints

These are hard invariants. Violating one requires escalation, not a workaround.

- The kernel crate stays `#![no_std]` without `alloc` and declares no
  dependency (ADR-0010, VO-1, VO-6). Kernel code uses `core` only. Verus
  specification vocabulary enters only under `cfg(verus_keep_ghost)`, which is
  false in every ordinary build.
- No Polars or glam path appears outside `src/polars_backend.rs` (DL-19,
  VO-14). The new facade modules must compile and pass gates under both
  `native-only` (`--no-default-features`) and `polars-enabled` profiles.
- No public type exposes an internal graph generic (technical design R3). Every
  new public type is non-generic. `Unary` and `Binary` hide graph structure.
- The public API is the facade's. Consumers never need to name
  `combobulate_kernel`. The kernel's functions are `pub` only because the
  facade must call them.
- `unsafe_code` stays forbidden workspace-wide. No `unsafe` block is
  introduced to avoid a copy.
- One executable body: the facade executes exactly the kernel function that
  Verus verifies. No `cfg(kani)`, `cfg(verus_keep_ghost)` or feature flag may
  substitute another body (technical design §17.7, B01 falsifier).
- The trust audit (VO-10, `scripts/trust_audit.py`) must find zero trusted
  items in workspace sources. No `assume`, `admit`, `external_body`, `external`,
  `assume_specification` or `external_fn_specification` appears in product
  code or in the kernel proof root.
- Integer addition on `I64` is checked. Overflow is the `IntegerOverflow`
  failure, never wrapping or saturation (V001, ADR-0006, SC-04).
- Graph construction and preparation never invoke an arithmetic kernel. Only
  `PreparedPlan::execute` and `AExpr::collect` execute (ADR-0007 staging, E002,
  E004, E005).
- Names follow `spec/vocabulary.json`. `identity`, not `id`, which is an
  excluded alias (D06). No aliases, deprecated entry points or compatibility
  shims (ADR-0005).
- Each code file stays at or under 400 lines (`AGENTS.md`). Clippy pedantic
  settings, `clippy.toml` thresholds (cognitive complexity 9, four arguments,
  70 lines, nesting 4) and Whitaker must pass without new suppressions, except
  the single scoped `indexing_slicing` expectation recorded in `Decision log`.
- Tests must not mutate the process environment. The fixture build uses
  `Command::env`/`env_remove`, which is the permitted subprocess exemption.
- Completed ExecPlans for other tasks are historical. Do not edit them.

## Tolerances (exception triggers)

The ExecPlan file itself is excluded from every size count below.

- Scope: stop and escalate if the change touches more than 40 non-ExecPlan
  files or exceeds 3,200 net added lines of code and other documentation.
- Interface: stop and escalate if a public signature in
  `Interfaces and dependencies` must change shape (a renamed or added type
  parameter, a different return type, or a removed item) after approval. Adding
  a private helper is not an interface change.
- Dependencies: `proptest` as a dev-dependency is pre-approved by this plan
  (`Decision log`, DL-6). Any other new dependency, including `thiserror`,
  requires escalation.
- Verus feasibility: if the EP-M1 prototype cannot verify the kernel loop
  through the single-root `cfg_attr` route after three distinct attempts, stop
  and escalate with the logs. Do not fall back to `verus!` macro source, a
  mirror body, `external_body`, or recursion.
- Proof cost: if `make verus-kernel` takes more than 120 s wall-clock or
  4 GiB resident memory on this host, record the measurement and escalate.
  ADR-0008 pre-registers proof budgets (AC-01, AC-02). This plan does not
  relabel a timeout as success.
- Iterations: if a gate still fails after three fix attempts on the same
  cause, stop and escalate.
- Governance: if `make design-check` rejects a spec edit in a way that needs a
  validator change beyond adding the new values, stop and escalate.
- Ambiguity: if review or implementation finds two materially different
  readings of a requirement, stop and present the options.

## Risks

- Risk: Verus may not accept
  `cfg_attr(verus_keep_ghost, verus_spec(invariant …))` on a `while` loop
  inside production source. The wiring probe only verified a straight-line
  function. Severity: high. Likelihood: medium. Mitigation: EP-M1 is a
  prototyping milestone that settles this before any facade work, with the
  escalation rule above. The Verus attribute syntax supports loop
  specifications through `#[verus_spec(invariant …)]` on `while` statements
  (`rust_verify_test` `syntax_attr` tests). With `cfg_attr` false, an attribute
  on a statement is stable Rust.
- Risk: workspace clippy denies `indexing_slicing`. A Verus-friendly loop
  indexes slices directly. Severity: medium. Likelihood: certain. Mitigation:
  one function-scoped `#[expect(clippy::indexing_slicing, reason = …)]`. The
  reason cites the Verus obligation that discharges each bound. A rejected
  alternative uses `get`/`get_mut` with unreachable `None` arms; those arms are
  untestable lines that the coverage ratchet counts (see the project's lcov
  phantom-line lesson).
- Risk: vstd's specifications for `i64::checked_add`, slice `len` and slice
  indexing are themselves `assume_specification` items. They widen the trusted
  basis. Severity: low. Likelihood: certain. Mitigation: record them as named
  axioms in `Verification plan`. They live in vstd, not in workspace sources,
  so the VO-10 audit is unaffected. The proof root may use `checked_add` or
  compare against `i64::MIN`/`i64::MAX` in specification arithmetic. Prefer
  whichever needs fewer vstd assumptions; record the choice.
- Risk: Verus compiles the kernel with Rust 1.98.0 while ordinary builds use
  nightly-2026-11-06 (1.101). The verified and shipped object code come from
  different compilers. Severity: medium. Likelihood: certain. Mitigation: the
  same source is verified and shipped. Compiler agreement on this `core`-only
  subset is a declared axiom (AXIOM-3), and the ordinary unit and property
  tests exercise the shipped object code.
- Risk: a naive tree walk over a shared directed acyclic graph (DAG) is
  exponential. `let y = add().apply(&x, &x)` repeated 64 times would never
  finish. Deep `Arc` chains also overflow the stack in recursive traversal and
  in the default recursive `Drop`. Severity: high. Likelihood: high if
  unplanned. Mitigation: preparation and execution traverse iteratively with a
  visited map keyed by node identity. `Node` implements an iterative `Drop`.
  Tests G4 and G5 are negative controls for both hazards.
- Risk: the nested Cargo build in `tests/native_consumer_e2e.rs` lengthens
  `make test`. Each new fixture would add another facade build. Severity: low.
  Likelihood: medium. Mitigation: extend the existing `native-consumer` fixture
  with a second binary, so one nested build serves both binaries.
- Risk: governance validators may reject the spec edits, such as the new
  `ShapeMismatch` error code or the task tags added to vocabulary rows.
  Severity: medium. Likelihood: medium. Mitigation: run `make design-check` in
  EP-M5 before any documentation prose depends on the edits. Use the governance
  tolerance above.
- Risk: `proptest` adds a dev-dependency tree to `Cargo.lock` and to the
  dependency audit (`audit.yml`). Severity: low. Likelihood: certain.
  Mitigation: pin the caret version already in the shared cache (1.12.0, to be
  confirmed at implementation) with `default-features = true`. Run
  `cargo deny`/audit through the existing `make lint` and `audit.yml` routes.

## Progress

- [x] (2026-11-11) Branch renamed to `1-2-2-minimal-ordinary-application-path`.
- [x] (2026-11-11) Wyvern reconnaissance of the design, ADR, specification and
  tooling surfaces.
- [x] (2026-11-11) Draft ExecPlan written.
- [ ] Community-of-experts design review, with its revisions folded in.
- [ ] Draft PR opened for plan review.
- [ ] User approval of the plan (status becomes `APPROVED`).
- [ ] EP-M1: kernel `elementwise::add_i64_into`, its Verus proof root,
  seeded mutants and `make verus-kernel` (prototype go/no-go).
- [ ] EP-M2: facade values and expression handles.
- [ ] EP-M3: preparation, execution and errors.
- [ ] EP-M4: the public consumer fixture, boundary and workflow wiring.
- [ ] EP-M5: specification, documentation, completion record and roadmap tick.

## Surprises & discoveries

- Observation: no proof-obligation component in `spec/proof-obligations.json`
  names task 1.2.2. The Verus log parser is not registered until 1.2.4, so any
  Verus record made now is `verdict-self-reported` and the evidence gate
  rejects it. Evidence: ADR-0009 lines 132-144 and 183-243;
  `scripts/docs_validation/evidence_gate.py:121`. Impact: the Verus proof is
  run and committed as an artefact, but this task cannot gate on its admission.
  See DL-1.
- Observation: `tests/workspace_kernel_boundary.rs` (VO-6) scans only
  `crates/combobulate-kernel/src/lib.rs`. An `extern crate alloc` in a new
  kernel submodule would pass it. Evidence: Wyvern report on
  `tests/support/workspace_source.rs`. Impact: EP-M4 widens VO-6 to every `.rs`
  file under the kernel's `src/`, with a seeded fixture proving the widened
  scan rejects a submodule violation.
- Observation: `spec/semantic-contracts.json` has a closed `error_codes` set
  with no shape-agreement code. The language reference calls the `[8,3]` versus
  `[3]` outcome a "Shape error" without a code. Evidence:
  `spec/semantic-contracts.json:3-20`; `docs/language-reference.md:301`.
  Impact: DL-4 adds `ShapeMismatch`.

## Decision log

Each entry below is proposed and takes effect on plan approval, unless it says
otherwise.

- DL-1. Decision: this task adds no new gate component to
  `spec/proof-obligations.json`. The Verus proof of `add_i64_into` is committed
  and run (`make verus-kernel`) as a milestone acceptance criterion, and its
  logs are listed as artefacts in the 1.2.2 completion record. Admission of
  that proof as `proof`-level evidence waits for the registered Verus parser in
  1.2.4. A follow-up note in this plan's `Outcomes` will ask the 1.2.4
  implementer to record it under a component that the 1.2.4 plan creates.
  Rationale: a `proof`-accepting component on 1.2.2 could never be satisfied
  before 1.2.4. Under MS-4 that would make 1.2.2 untickable while the parser
  does not exist. A `tested` component would add an evidence record and binding
  machinery that no task has yet exercised, and its level would understate the
  Verus result. The ledger assigns PF04 (graph meaning) to 2.3.2, 2.3.5 and
  4.2.3 and PF05 (outcome/frame) to 2.3.5 onwards, so 1.2.2 linking no
  component matches the approved ledger. Approval needed: yes, because this
  places proof-admission work on 1.2.4's plan. Date/Author: 2026-11-11,
  planning agent.
- DL-2. Decision: values hold storage as `Arc<[i64]>`. `Array::from_i64`
  accepts `impl Into<Arc<[i64]>>`. Passing an `Arc<[i64]>` shares it with no
  copy. Passing a `Vec<i64>` or `&[i64]` copies once into shared storage, and
  the method documentation says so. Rationale: immutable handles share backing
  buffers (technical design §4.1). `Arc<[i64]>` is one allocation with no
  double indirection, and the kernel borrows it as `&[i64]` in place. A
  `Vec`-backed representation (`Arc<Vec<i64>>`) avoids the construction copy
  but adds an indirection on every later read. It also commits the storage
  shape before 2.1.4's views and 4.1's Polars import exist. Date/Author:
  2026-11-11, planning agent.
- DL-3. Decision: `identity().apply(&e)` and `e.then(&identity())` return a
  clone of `e`'s handle, adding no graph node. Rationale: V032 says identity
  "Shares the input handle; no evaluation or copy", and its execution column
  reads "Graph identity". Folding at construction makes buffer sharing
  structural rather than an executor optimization, and leaves nothing to prove
  about an identity kernel. Provenance labels (2.3.3) may later need an
  identity node. Pre-1.0 policy (D06) permits that change without a shim.
  Date/Author: 2026-11-11, planning agent.
- DL-4. Decision: add `ShapeMismatch` to the closed `error_codes` set in
  `spec/semantic-contracts.json`. Public failures carry codes from that set
  (`Failure::code`). Rationale: technical design §17.5 makes error categories
  public semantic values. Equal-shape agreement failure (technical design §5.1)
  is a category the set does not name. Approval needed: yes, because it amends
  a semantic-contract revision. Date/Author: 2026-11-11, planning agent.
- DL-5. Decision: introduce `NativeExecutor` with a single
  `const fn sequential()` constructor as the only engine and the default for
  `collect`. It has no caller-owned output and no scratch parameters, which
  remain with 2.3.5 (E017). Rationale: `.prepare(&engine)` needs an engine
  type. E017's name is the documented native route, so using it now avoids a
  placeholder type that 2.3.5 would have to delete. Date/Author: 2026-11-11,
  planning agent.
- DL-6. Decision: add `proptest` (caret `1.12.0`, confirmed at
  implementation) as a dev-dependency of the root package only. Rationale: the
  refinement claim (G1) quantifies over generated expression DAGs and values,
  including the overflow boundary. A finite `rstest` table cannot cover that
  space, and the user's brief authorizes property tests. Kani is not chosen for
  the facade because the facade allocates and traverses heap-shaped graphs, and
  the evidence gate caps Kani at `partial` before 1.2.4. Date/Author:
  2026-11-11, planning agent.
- DL-7. Decision: the kernel function takes caller-provided output,
  `add_i64_into(lhs, rhs, out) -> Result<(), AddFailure>`, rather than
  returning a buffer. Rationale: the kernel has no `alloc`. Caller-provided
  output gives a precise frame contract, which is also the shape 2.3.5's
  caller-owned-output route needs. The facade allocates the output once with
  `iter::repeat_n(0, n).collect::<Arc<[i64]>>()`, obtains `&mut [i64]` with
  `Arc::make_mut` (the handle is unique, so no clone happens), and publishes the
  `Arc` only on success. That is the atomic commit of SC-09: a failed
  execution publishes nothing. Date/Author: 2026-11-11, planning agent.
- DL-8. Decision: the kernel loop indexes slices directly under one
  function-scoped `#[expect(clippy::indexing_slicing, reason = "…")]`. Its
  reason states that the loop guard and the `requires`-free runtime length
  check bound every index, and that Verus discharges each in-bounds obligation.
  Rationale: see the matching risk. This is the only new lint suppression the
  plan permits. Date/Author: 2026-11-11, planning agent.
- DL-9. Decision: preparation reports every independent static failure, in
  deterministic post-order with left before right. Execution fails fast on the
  first dynamic failure: the lowest overflowing position of the first add node
  to fail in the same post-order. Rationale: technical design §8 says
  preparation "collects independent static errors without evaluating a first
  cell". A deterministic order makes failures testable and snapshot-stable.
  Date/Author: 2026-11-11, planning agent.
- DL-10. Decision: this task records an ADR,
  `docs/adrs/adr-0011-minimal-value-and-expression-representation.md`, for
  DL-2, DL-3, DL-7 and DL-9, and references it from technical design §§4.1 and
  8. It adds no decision-register entry, because none of these decisions
  controls acceptance. Rationale: these representation choices are hard to
  reverse once 1.2.5 exports public models over them (`AGENTS.md`, design
  decisions). Date/Author: 2026-11-11, planning agent.

## Outcomes & retrospective

Not started. Record at each milestone boundary and at completion.

## Context and orientation

The repository root is the facade package `combobulate` (`src/`). Today it
holds:

- `src/lib.rs`, 50 lines: the crate root. It forbids `unsafe`, declares
  `mod profile`, and declares `pub(crate) mod polars_backend` under
  `cfg(feature = "polars")`. It exports `BuildProfile`, `BackendProbeError` and
  a hidden `polars_backend_probe`.
- `src/profile.rs`: `BuildProfile`, a report of compiled features.
- `src/polars_backend.rs`: the crate-private Polars wiring probe.

`crates/combobulate-kernel/src/lib.rs` is the `#![no_std]` kernel. Its only
item is `TargetFacts`, and it already declares
`#[cfg(kani)] extern crate kani;`. `crates/combobulate-macros` exports nothing.

Key terms:

- Value (materialized value): an `Array` holding an actual buffer.
- Expression handle: an `AExpr`, a cheap cloneable reference to an immutable
  graph node that denotes a deferred result and holds no result itself
  (`docs/context.md:75`).
- Descriptor: a reusable operation such as `identity()` (a `Unary`) or
  `add()` (a `Binary`). Applying a descriptor builds a new graph node and never
  executes a kernel.
- Preparation: `AExpr::prepare(&NativeExecutor)` validates the graph's static
  facts (here, equal vector lengths) and returns a `PreparedPlan` or a static
  `Error`.
- Execution: `PreparedPlan::execute()` evaluates the plan and returns a new
  `Array` or a dynamic `Error`. `AExpr::collect()` is preparation plus
  execution with the default executor.
- Denotation: the mathematical meaning of an expression, defined in the
  `Verification plan` independently of the implementation.
- Single-root Verus wiring: production source carries
  `#[cfg_attr(verus_keep_ghost, verus_spec(...))]` attributes that ordinary
  builds ignore. A proof root file imports the production module with
  `#[path = ...]`, and `prover-tools verus run --proof-file` verifies it
  (ADR-0010, "Verus wiring"). The worked example is
  `tools/verifier-fixtures/verus-wiring-probe/production.rs` and
  `single-root.rs`.
- Seeded mutant: a deliberately wrong copy of a function body placed in the
  proof root under the same specification. It must fail verification at the
  named postcondition. This is the negative control that shows the
  specification can reject a wrong body.

Gate commands (see `AGENTS.md` and the `Makefile`):

- `make check-fmt` runs rustfmt and `mdtablefix --check`.
- `make lint` runs rustdoc, Clippy for each gate profile, Whitaker and the
  Python lint.
- `make test` runs nextest and doctests for each gate profile.
- `make markdownlint`, `make nixie`, `make spelling` and `make design-check`
  are the documentation and governance gates.

Verifier tooling: `make install-verus` installs the pinned Verus
(0.2026.09.06.8dea4a2, Rust 1.98.0, Z3 4.16.0, vstd `=0.0.0-2026-09-06-0133`).
`$(PROVER_TOOLS)` is
`uv tool run --from git+…rust-prover-tools.git@<REF> prover-tools`.

Existing test patterns to copy:

- `src/profile.rs` (`rstest` cases with messages).
- `tests/build_profiles.rs` with `tests/features/build_profiles.feature`
  (`rstest-bdd` 0.6, scenario modules, `insta` snapshots in `tests/snapshots/`).
- `tests/native_consumer_e2e.rs` with `tools/fixtures/native-consumer/` (a
  standalone consumer built with `--locked --offline`).
- `tests/workspace_kernel_boundary.rs` (`googletest` matchers).

Documentation and skills to keep at hand:

- `docs/technical-design.md` §§4, 5.1, 6.1, 7, 8 and 17.
- `docs/language-reference.md` rows V001, V032, E002, E004, E005 and E017.
- `docs/adrs/adr-0006-…`, `adr-0007-…`, `adr-0009-…` and `adr-0010-…`.
- `docs/testable-bets.md` (B01, B02).
- `docs/developers-guide.md` ("Workspace layout and module ownership" and
  "Verifier capability probes").
- `docs/rust-testing-with-rstest-fixtures.md`, `docs/rstest-bdd-users-guide.md`
  and `docs/rust-doctest-dry-guide.md`.
- `docs/reliable-testing-in-rust-via-dependency-injection.md` (no
  environment mutation).
- `docs/complexity-antipatterns-and-refactoring-strategies.md` (keep the
  traversal small).
- Skills: `rust-router`, then `rust-types-and-apis` (public surface),
  `rust-memory-and-state` (`Arc` sharing and iterative `Drop`), `verus`,
  `proptest`, `rust-unit-testing`, `nextest`, `execplans` and
  `en-gb-oxendict-style`.

## Conformance basis

Upstream artefacts, all at commit `b873322`:

- Terms of reference revision 0.2 (6 October 2026): goals G1, G2, G6, G7 and
  G8 (§6).
- Technical design revision 0.2 (6 October 2026), as amended through 1.2.1:
  R2, R3, R4, R8, R9; §4.1 (conceptual types and ownership); §5.1 (agreement);
  §6.1 (checked I64); §7 (ordinary application spelling); §8 (lifecycle);
  §17.1, §17.3, §17.5 and §17.7 (proof-first, public models, outcome/frame, one
  executor).
- Language reference revision 0.2: V001 `add`, V032 `identity`, E002
  `.apply`/`.then`, E004 `.prepare`, E005 `.collect`/`.execute`, and E017
  `NativeExecutor::sequential()`.
- ADR-0005 (pre-1.0 and proof interface), ADR-0006 (numeric contracts,
  SC-04, SC-06 and SC-09), ADR-0007 (staging), ADR-0009 (proof-first and the
  evidence gate), ADR-0010 (crate boundaries and Verus wiring).
- Decisions D06, D07, D10 and D16 (`docs/decision-register.md`).
- Bets B01 and B02 (`docs/testable-bets.md`, `spec/bets.json`).
- Proof obligations PF04 and PF05 are traced for orientation only. Per DL-1,
  no component is linked to 1.2.2.

Trace links:

```plaintext
G2 -> R2 -> §5.1, §6.1 -> EP-M1 -> verus: add_i64_into_{success,complete,first_overflow,frame}
G2 -> R2 -> §8 -> EP-M3 -> tests::ordinary_application::{prepare_reports_every_mismatch, overflow_surfaces_at_execution}
G3/G7 -> R3 -> §4.1 -> EP-M2 -> fixture native-consumer/ordinary_application (non-generic public names)
G6/G4 -> R4 -> §4.1 V032 -> EP-M2 -> tests::ordinary_application::identity_shares_the_input_buffer
G7 -> R8 -> §17.1, §17.7 -> EP-M1 -> make verus-kernel (+ seeded mutants rejected)
G7 -> R9 -> §17.3 -> EP-M3 -> property G1 (refinement to the reference denotation)
B01 -> EP-M1 (one executable body; no substitute) ; B02 -> EP-M4 (public-only consumer)
```

## Verification plan

### Abstract model (specified before implementation)

Values. An `Array` denotes a pair `(I64, s)` where `s` is a finite sequence of
mathematical integers, each within `[i64::MIN, i64::MAX]`. Its visible shape is
`[|s|]`. Every element is valid: nullability arrives with 2.1.1 and is outside
this task. Scalars (shape `[]`) and scalar extension also belong to 2.1.1. This
task's values are rank-one vectors only, including the empty vector `[0]`.

Expressions. Let `len(e)` be the static length model and `⟦e⟧` the dynamic
denotation, a function to `Ok(seq)` or `Err(failure)`:

```plaintext
len(input a)          = |a.s|
len(identity(e))      = len(e)
len(add(l, r))        = len(l)        provided len(l) = len(r)

static(e) = the post-order list of add nodes n = add(l, r) in e
            with len(l) ≠ len(r)                            (each node once)

⟦input a⟧             = Ok(a.s)
⟦identity(e)⟧         = ⟦e⟧
⟦add(l, r)⟧           = ⟦l⟧ >>= λx. ⟦r⟧ >>= λy. addv(x, y)
addv(x, y)            = Err(IntegerOverflow{p}) where p is the least i with
                        x[i] + y[i] ∉ [i64::MIN, i64::MAX], if such i exists
                      = Ok([x[0]+y[0], …, x[n-1]+y[n-1]]) otherwise
```

`>>=` propagates the first `Err`, so the left operand's failure wins. A shared
node (the same `AExpr` used twice) has one denotation, however many times it is
referenced.

Lifecycle contract:

- prepare(e) = `Err(Preparation, static(e))` when `static(e)` is non-empty,
  otherwise `Ok(plan_e)`. Preparation never evaluates `⟦·⟧`.
- execute(plan_e) = `⟦e⟧`, with `Err(Execution, [f])` for `⟦e⟧ = Err(f)`.
- collect(e) = prepare(e, sequential) then execute.
- Frame: no operation mutates an input `Array`. A failed execution publishes
  no output buffer.
- Sharing: if `⟦e⟧ = ⟦input a⟧` structurally (only identities applied), the
  result's buffer is `a`'s buffer.
- Termination: `e` is a finite DAG (handles are immutable and acyclic by
  construction), so preparation and execution visit each distinct node once and
  terminate.

Success witnesses: `[1,2,3] + [10,20,30] = [11,22,33]`; `[] + [] = []`;
`[i64::MAX] + [0] = [i64::MAX]`; `[i64::MIN] + [0] = [i64::MIN]`; identity of
`[7]` shares its buffer.

### Kernel obligations (Verus, unbounded)

The kernel function is
`combobulate_kernel::elementwise::add_i64_into(lhs: &[i64], rhs: &[i64], out:
&mut [i64]) -> Result<(), AddFailure>`,
where `AddFailure` is `LengthMismatch` or `Overflow { position: usize }`. Let
`n = lhs@.len()` and `in_range(v) := i64::MIN <= v <= i64::MAX` over `int`.

- K1. Success relation. `Ok(())` implies
  `lhs@.len() == rhs@.len() == out@.len()`, and for every `i < n`,
  `final(out)@[i] == lhs@[i] + rhs@[i]` with the sum in range.
- K2. Success condition (completeness). If the three lengths are equal and
  every `lhs@[i] + rhs@[i]` is in range, the result is `Ok(())`. Together with
  K1, `Ok` holds exactly when this premise holds. This rules out an
  always-`Err` body.
- K3. Length failure and frame. `Err(LengthMismatch)` holds exactly when the
  lengths differ, and then `final(out)@ == old(out)@`.
- K4. First overflow. `Err(Overflow { position: p })` implies the lengths are
  equal, `p < n`, the sum at `p` is not in range, and every `i < p` is in range.
- K5. Overflow frame. Under K4,
  `final(out)@[i] == lhs@[i] + rhs@[i]` for `i < p`, and
  `final(out)@[i] == old(out)@[i]` for `p <= i < n`.
- K6. Safety and termination. Every index is in bounds, the loop counter
  never overflows, and the loop terminates with `decreases n - i`. Verus checks
  these as part of verifying the body. They are what make the DL-8 lint
  expectation sound.

These five postconditions (K1-K5) are the single `ensures` clause on the
production function, and K6 follows from verifying its body. The proof root
`crates/combobulate-kernel/verus/elementwise.rs` imports
`../src/elementwise.rs` by `#[path]` and holds:

- `add_i64_into_contract`: a wrapper whose `ensures` restates K1-K5 and whose
  body calls the shipped function. It proves that the exported specification is
  usable by a caller. It is the success witness for consumers.
- `witness_small` (proof or exec): calls the function on `[1,2,3]` and
  `[10,20,30]`, asserting `Ok` and the sums. This makes the success premise
  inhabited, so K1 is non-vacuous.
- `witness_overflow`: `[0, i64::MAX]` and `[0, 1]` report
  `Overflow { position: 1 }`. This inhabits K4.
- Seeded mutants, each a function with K1-K5 as its contract and a wrong body,
  each of which must fail at a postcondition:
  - M-wrap: uses `wrapping_add` and never reports overflow (K4/K2).
  - M-late: reports `position: i + 1` (K4).
  - M-err: always returns `Err(Overflow { position: 0 })` (K2).
  - M-skip-frame: zeroes `out` before checking lengths (K3).

Method rationale: Verus suits arbitrary-length sequence relations and loop
invariants (technical design §17.1). Kani adds nothing here: Verus integer
arithmetic in specifications is exact, so the `i64` boundary is covered without
a bound. The evidence gate also caps Kani at `partial` before 1.2.4. Kani is
therefore not used in this task.

Artefacts and evidence: `make verus-kernel` runs
`$(PROVER_TOOLS) verus run --repo-root . --proof-file
crates/combobulate-kernel/verus/elementwise.rs --extra-arg=--crate-type=lib`
once for the positive functions (expected
`verification results:: N verified, 0 errors`). It then runs each mutant with
`--extra-arg=--verify-root --extra-arg=--verify-function=<mutant>` and requires
exit status 1 plus an `error: postcondition not satisfied` located at that
mutant's `ensures` span. The located-span check uses the existing
`scripts/verus_probe.py` helpers. Logs go to `/tmp` during development. At
EP-M5 they are captured under `crates/combobulate-kernel/verus/observations/`
with a `provenance.json` in the established probe format, so that 1.2.4's
parser can later admit them (DL-1).

Non-vacuity: the witnesses inhabit the success, overflow and length-failure
premises. Each mutant must be rejected at its own postcondition. A mutant
rejected by a syntax, type or unrelated error does not count, and the script
fails. Running `scripts/trust_audit.py` over the proof root must report zero
trust items. This shows the proof is not discharged by an assumption.

### Facade obligations (tests and properties)

- G1. Refinement to the denotation. For generated expression DAGs over up to
  four generated input vectors (length 0-16, elements drawn from
  `prop_oneof![any::<i64>(), boundary values near i64::MIN/MAX/0]`), up to 12
  nodes with shared subterms, `collect(e)` equals an independent reference
  evaluator. The reference evaluator lives in the test, recurses over a
  test-side mirror of the expression, and computes with `i128`. Method:
  `proptest` in `tests/ordinary_application_properties.rs`. It cannot reuse the
  kernel: the oracle independence rule of 1.2.3 is applied early. Non-vacuity:
  a deterministic-seed companion test draws 512 cases and asserts that the
  sample contains `Ok`, `IntegerOverflow` and `ShapeMismatch` outcomes and at
  least one shared-subterm case. Negative control: temporarily replacing the
  kernel call with `wrapping_add` makes G1 fail (recorded once in `Artefacts`,
  not committed).
- G2. Static failure completeness. `prepare(e)` fails exactly when the length
  model finds a mismatch. Its failures list every mismatched add node once, in
  post-order, with the left and right lengths. Method: named `rstest` cases
  (one mismatch, two independent mismatches, a mismatch below a shared node
  reported once) plus G1's generator. Non-vacuity: a case with two independent
  mismatches must report two failures.
- G3. No unnecessary copies. Method: `rstest` cases.
  - `identity` (by `then` and by `apply`) returns a result whose
    `as_i64_slice().as_ptr()` equals the input's, both through `collect` and
    through `prepare` then `execute`.
  - After `collect` of `add`, both inputs' pointers and contents are
    unchanged, and the output pointer differs from each input.
  - `Array::from_i64(arc.clone())` shares `arc`'s pointer.
  Non-vacuity: the `Vec` construction case asserts a different pointer from the
  source `Vec`'s, the documented copy, so the pointer comparison can fail.
- G4. Shared DAG evaluated once. Build `x0 = [1]`, then
  `x(k+1) = add(x(k), x(k))` for 62 levels. `collect` returns `[2^62]` and the
  63rd level returns `IntegerOverflow { position: 0 }` within the nextest
  default 60 s period. Without per-node memoization the walk visits 2^62 nodes
  and never finishes, so the test's completion is the negative control. It is
  recorded once by a temporary mutation, not committed.
- G5. Deep chains. A left-leaning chain of 100,000 `add` nodes over `[1]`
  builds, prepares, executes to `[100_001]`, and drops on a test thread with a
  2 MiB stack. Method: `rstest` with `std::thread::Builder::stack_size`.
  Recursive traversal or the default `Arc` drop overflows that stack, which is
  the negative control.
- G6. Staging. An expression whose execution overflows still prepares
  successfully (`Ok(plan)`), and the failure appears only from `execute` with
  `stage() == Stage::Execution`. A length mismatch fails at `prepare` with
  `stage() == Stage::Preparation` and never reaches a kernel. Method: `rstest`
  plus the BDD scenarios below.
- G7. Public surface. The consumer fixture names every public type without
  type arguments and imports only `combobulate::…`. Its `cargo tree` reaches no
  `polars`, `glam`, `kani`, `verus` or `vstd` package. Method: the extended
  `tests/native_consumer_e2e.rs`. Residual gap: there is no mechanical
  public-API snapshot. Generating rustdoc JSON inside a test would compile the
  repository from a test body, which the developers' guide forbids. Reviewers
  check `cargo doc` output instead, and the gap is recorded.
- G8. Diagnostics. `Display` for each failure kind and stage is snapshotted
  with `insta` (`tests/snapshots/ordinary_application__*.snap`). Each snapshot
  test pairs a semantic assertion on `Failure::code()`.

### Axioms (trusted, not verified here)

- AXIOM-1. The pinned Verus (0.2026.09.06.8dea4a2) and Z3 4.16.0 are sound for
  the features used.
- AXIOM-2. vstd's specifications for slice `len`, slice indexing, mutable index
  assignment and, if used, `i64::checked_add` match Rust semantics. These are
  vstd `assume_specification` items outside workspace sources.
- AXIOM-3. Rust 1.98.0 (Verus) and nightly-2026-11-06 (ordinary) give the same
  semantics to the kernel's `core`-only source.
- AXIOM-4. `Arc<[T]>` from a `TrustedLen` iterator allocates once, and
  `Arc::make_mut` on a unique `Arc` does not clone. G3 confirms these
  behaviours by pointer observation, not by assumption.

### Where Verus is not used, and why

The graph handles, preparation traversal and `Arc` storage are facade plumbing
over `alloc`. They sit outside the kernel's `core`-only boundary, which is the
only boundary ADR-0010 wires for Verus. Their meaning is the abstract model
above, checked by G1 and G2 against an independent oracle. PF04 (graph meaning
and preparation refinement) machine-checks this layer at 2.3.2, 2.3.5 and
4.2.3, once public logical models (E014, 1.2.5) exist. Diagnostic formatting
(G8) and fixture wiring (G7) carry no proof obligation.

## Plan of work

### Stage A: understand and propose (this document)

No code changes. The plan goes through community-of-experts review and user
approval.

### Stage B: red

Each milestone begins by adding its failing tests and BDD feature. For EP-M1 it
begins with the proof root's specifications and mutants. Each red run is
recorded with its expected failure reason in `Validation and acceptance`.

### Stage C: green

The smallest implementation that turns each red artefact green, in milestone
order.

### Stage D: refactor and document

Refactoring happens in separate commits once behaviour is green. EP-M5 holds
the documentation and specification work.

## Milestones and plateaus

### EP-M1 (prototyping): the verified kernel elementwise add

Outcome: `crates/combobulate-kernel/src/elementwise.rs` exists with
`AddFailure` and `add_i64_into`, carrying the K1-K5 `verus_spec` contract and a
loop invariant through `cfg_attr`. Its proof root
`crates/combobulate-kernel/verus/elementwise.rs` holds the contract wrapper,
witnesses and four mutants. `make verus-kernel` verifies the positives and
rejects each mutant at its located postcondition. Kernel unit tests (`rstest`)
cover each success witness and failure class at runtime.

Requirements: R2, R8; B01 (one body). Go/no-go: if the Verus tolerance is
reached, stop. Possible revisions are a different loop shape, a different
specification phrasing, or narrowing the claim. Each needs approval.

Acceptance evidence:

- `cargo nextest run -p combobulate-kernel` passes the new cases.
- `make verus-kernel` exits 0 and prints the verified count and four
  rejected mutants.
- `scripts/trust_audit.py crates/combobulate-kernel` reports zero items.
- The three gates pass.

Conformance check:

- The kernel stays `no_std` without `alloc`, and VO-1 and VO-6 still pass.
- No substitute body exists: the proof root imports the shipped file by
  `#[path]`.
- No new dependency is added to the kernel.
- The only lint suppression is DL-8's.

Recovery: the milestone is additive (a new module and a new Make target). It
reverts as a unit.

Remaining gaps: facade use (EP-M3) and the formal workflow step (EP-M4).

Compatibility decision: none.

### EP-M2: values and expression handles

Outcome: `src/array.rs` (`Array`, `Dtype`) and `src/expr.rs` (`AExpr`, `Unary`,
`Binary`, `OperationId`, `identity`, `add`, and the crate-private `Node` with
an iterative `Drop`). The crate root re-exports them. Unit tests cover
construction, `len`, `is_empty`, `dtype`, identity folding (G3's identity part)
and the deep-chain drop (G5's drop part).

Requirements: R3, R4; V032, E002.

Acceptance evidence: new `rstest` cases pass under both profiles, the doctests
compile and pass, and the gates pass.

Conformance check:

- Every public type is non-generic.
- No kernel is invoked during construction.
- No Polars path appears.

Recovery: additive; revert the two modules and their re-exports together.

Remaining gaps: `prepare`, `execute` and `collect` (EP-M3).

Compatibility decision: none.

### EP-M3: preparation, execution, and errors

Outcome:

- `src/error.rs`: `Error`, `Failure`, `Stage`.
- `src/plan.rs`: `NativeExecutor`, `PreparedPlan`, `AExpr::prepare`,
  `AExpr::collect` and `PreparedPlan::execute`. The traversal is iterative and
  memoized, and execution calls `add_i64_into`.

The tests are:

- `tests/ordinary_application.rs`, holding G2, G3, G4, G5, G6 and the G8
  snapshots;
- `tests/ordinary_application_properties.rs` (G1);
- `tests/ordinary_application_bdd.rs` with
  `tests/features/ordinary_application.feature`.

`proptest` is added as a dev-dependency.

Requirements: R2, R4, R9; E004, E005, E017 (minimal); SC-04 (checked add),
SC-09 (atomic publication).

Acceptance evidence: every new test passes in both profiles. Each was observed
red first: missing items fail compilation, and seeded behaviours fail
assertions. The gates pass.

Conformance check:

- Preparation runs no kernel (G6).
- Execution uses only the kernel body.
- Failures carry closed-set codes, with `ShapeMismatch` pending the DL-4
  spec edit in EP-M5. The EP-M5 spec edit is ordered before the PR is marked
  ready.

Recovery: additive over EP-M2. Revert `plan.rs`, `error.rs` and the tests
together.

Remaining gaps: the consumer fixture and documentation.

Compatibility decision: none.

### EP-M4: public consumer fixture, boundaries, and workflow wiring

Outcome:

- `tools/fixtures/native-consumer/src/bin/ordinary_application.rs` runs the
  public program from `Purpose` and prints three lines (see `Artefacts`).
- `tests/native_consumer_e2e.rs` selects each binary by target name from the
  build messages and checks both outputs. The new one is compared with
  `tests/snapshots/native_consumer_e2e__ordinary_application.snap`.
- VO-6 is widened to scan every kernel source file, with a seeded nested-module
  fixture under `tests/fixtures/` that must be rejected.
- `.github/workflows/formal.yml` gains `make verus-kernel` after
  `make install-verus`, with `tests/formal_workflow_contract.rs` updated in the
  same change.

Requirements: B02 (public-only consumer, ahead of 1.2.5), G7; roadmap success
criterion.

Acceptance evidence: `cargo nextest run --test native_consumer_e2e` and
`--test workspace_kernel_boundary` pass, and the gates pass.

Conformance check:

- The fixture imports only `combobulate` items.
- No proof package enters either ordinary profile (VO-3).
- The formal workflow still gates no merge.

Recovery: the fixture binary and the test changes revert together. The workflow
edit and its contract revert together.

Remaining gaps: documentation.

Compatibility decision: none.

### EP-M5: specification, documentation, completion, and roadmap tick

Outcome:

- Spec edits, followed by regeneration through the repository generators
  (`scripts/generate_reference.py` for the language-reference tables):
  - `spec/semantic-contracts.json` gains `ShapeMismatch` (DL-4);
  - `spec/vocabulary.json` adds task `1.2.2` to V001, E004 and E017 (each
    implemented minimally here), and the language-reference tables are
    regenerated.
- Documentation:
  - `docs/adrs/adr-0011-minimal-value-and-expression-representation.md`
    (DL-10), linked from `docs/contents.md` and technical design §§4.1 and 8.
  - Technical design §3 and §4.1: the facade's public items and the
    `elementwise` kernel module.
  - `docs/users-guide.md`: a new "Build and run an array expression" section
    with the `Purpose` example, the error stages, the copy and sharing rules,
    and the current limits (I64 vectors, no nulls, no scalars). It also
    corrects the "not yet implemented" status lines.
  - `docs/developers-guide.md`: ownership-table rows and a re-use policy for
    `elementwise` (only the facade executor calls it; each new kernel adds its
    own `verus_spec` and mutants), plus a "Product Verus proofs" subsection on
    `make verus-kernel`, the proof root and the mutant protocol.
  - `docs/repository-layout.md`: rows for the new paths.
  - `docs/contents.md`: this plan and ADR-0011.
- The captured Verus observations and `provenance.json` (DL-1).
- Completion:
  - `spec/task-completion.json` gains a 1.2.2 entry citing D07 and D16 and
    the artefacts;
  - `docs/roadmap.md` ticks 1.2.2;
  - `scripts/export_roadmap.py` refreshes `spec/roadmap.json`.

Acceptance evidence: `make design-check`, `make markdownlint`, `make nixie`,
`make spelling`, `make check-fmt`, `make lint` and `make test` all pass, and
`make verus-kernel` passes on the final head.

Conformance check:

- Every DL item is reflected in the ADR or in the design.
- No upstream assumption is silently changed.
- The trace links in `Conformance basis` resolve to real tests and files.

Recovery: documentation-only edits revert freely. The roadmap tick is the last
commit and reverts alone.

Remaining gaps: Verus evidence admission (1.2.4, per DL-1), and nulls, scalars
and other dtypes (2.1.x).

Compatibility decision: none.

## Concrete steps

Run every command from the worktree root. Tee long output to
`/tmp/$ACTION-combobulate-1-2-2-minimal-ordinary-application-path.out`.

EP-M1:

```sh
make install-verus                     # once per machine; idempotent
cargo nextest run -p combobulate-kernel 2>&1 | tee /tmp/test-kernel-…out
make verus-kernel 2>&1 | tee /tmp/verus-combobulate-1-2-2-minimal-ordinary-application-path.out
uv run --script scripts/trust_audit.py crates/combobulate-kernel
```

Expected `make verus-kernel` tail:

```plaintext
verification results:: 9 verified, 0 errors
mutant M-wrap: rejected at postcondition (elementwise.rs:<line>)
mutant M-late: rejected at postcondition (elementwise.rs:<line>)
mutant M-err: rejected at postcondition (elementwise.rs:<line>)
mutant M-skip-frame: rejected at postcondition (elementwise.rs:<line>)
```

(The verified count is whatever Verus reports for the positive functions. It is
recorded, not predicted.)

Every milestone, in this order (sequentially, never in parallel):

```sh
make check-fmt 2>&1 | tee /tmp/check-fmt-combobulate-1-2-2-minimal-ordinary-application-path.out
make lint 2>&1 | tee /tmp/lint-combobulate-1-2-2-minimal-ordinary-application-path.out
make test 2>&1 | tee /tmp/test-combobulate-1-2-2-minimal-ordinary-application-path.out
```

When documentation or specifications change, also run:

```sh
make fmt
make markdownlint 2>&1 | tee /tmp/markdownlint-combobulate-1-2-2-minimal-ordinary-application-path.out
make nixie
make spelling
make design-check 2>&1 | tee /tmp/design-check-combobulate-1-2-2-minimal-ordinary-application-path.out
```

Commit after each green step with an imperative subject naming the milestone,
for example `Add the verified kernel elementwise add (1.2.2, EP-M1)`.

## Validation and acceptance

Red, green and refactor evidence for each milestone:

- EP-M1 red: the kernel tests reference `elementwise::add_i64_into` before it
  exists, so `cargo nextest run -p combobulate-kernel` fails to compile with
  `E0432` or `E0425` naming the item. The proof root, run with the mutants
  only, must report each mutant rejected. This step checks the specification
  before the body exists, by verifying the mutants against a `todo!()`-free
  stub that returns `Err(LengthMismatch)`. That stub is itself rejected by K2.
  Green: the shipped body verifies and the tests pass.
- EP-M2 red: unit tests and doctests naming `Array`, `AExpr`, `identity` and
  `add` fail to compile. Green: they pass.
- EP-M3 red:
  - the behavioural feature runs with every scenario failing on missing steps
    or items;
  - the property test fails to compile;
  - after a minimal compile-only skeleton returning `Err` from `execute`, G1
    fails with a counterexample, which shows the oracle can fail.
  Green: all pass.
- EP-M4 red: the e2e test expects the `ordinary_application` binary and fails
  with "binary not found". The widened VO-6 seeded fixture fails the old
  scanner. Green: both pass.

BDD feature (`tests/features/ordinary_application.feature`):

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
    Then preparation fails with ShapeMismatch between lengths 3 and 2

  Scenario: Overflow fails at execution, not preparation
    Given an I64 vector [0, 9223372036854775807]
    And another I64 vector [0, 1]
    When add is applied and the expression is prepared
    Then preparation succeeds
    And executing the plan fails with IntegerOverflow at position 1
```

Quality criteria:

- Tests: `make test` passes in both profiles, with the new suites listed
  above.
- Verification: `make verus-kernel` verifies K1-K6 and rejects all four
  mutants. G1-G8 pass.
- Lint and format: `make lint` and `make check-fmt` pass with no new
  suppressions beyond DL-8.
- Documentation: `make markdownlint`, `make nixie` and `make spelling` pass.
- Governance: `make design-check` passes.
- Performance: no benchmark gate. The G4 and G5 timings fall inside nextest's
  default period.

## Idempotence and recovery

Every step can be repeated. `make install-verus` checks checksums and skips a
present installation. Generated files (`spec/roadmap.json`, the language
reference tables, `typos.toml`) are regenerated, never hand-edited. If a
milestone fails midway, reset to its last green commit with
`git reset --hard <sha>` on this branch only, after confirming the working tree
holds nothing worth keeping. Never stash with a bare `git stash`, because the
stash stack is shared across worktrees.

## Artefacts and notes

Expected fixture output (`ordinary_application` binary):

```plaintext
identity: [1, 2, 3] (shared buffer: true)
add: [11, 22, 33]
collect: [11, 22, 33]
```

Negative-control transcripts are added here as each one is observed: G1 with
`wrapping_add`, G4 without memoization, and each Verus mutant.

## Interfaces and dependencies

Kernel, in `crates/combobulate-kernel/src/elementwise.rs`, `core` only:

```rust
/// Why an elementwise I64 addition did not complete.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AddFailure {
    /// The operand and output lengths differ; `out` is unchanged.
    LengthMismatch,
    /// `lhs[position] + rhs[position]` is outside I64; `out[..position]`
    /// holds the sums and `out[position..]` is unchanged.
    Overflow { position: usize },
}

/// Add `lhs` and `rhs` element-wise into `out` with checked I64 arithmetic.
#[cfg_attr(verus_keep_ghost, verus_verify, verus_spec(result => ensures /* K1-K5 */))]
pub fn add_i64_into(lhs: &[i64], rhs: &[i64], out: &mut [i64]) -> Result<(), AddFailure>;
```

The kernel root adds `pub mod elementwise;`.

Facade, re-exported from `src/lib.rs` (every type non-generic):

```rust
// src/array.rs
#[non_exhaustive]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Dtype { I64 }

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Array { /* dtype, Arc<[i64]> */ }
impl Array {
    pub fn from_i64(values: impl Into<Arc<[i64]>>) -> Self;
    pub fn dtype(&self) -> Dtype;
    pub fn len(&self) -> usize;
    pub fn is_empty(&self) -> bool;
    pub fn as_i64_slice(&self) -> Option<&[i64]>;
    pub fn expr(&self) -> AExpr;
}

// src/expr.rs
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct OperationId(/* &'static str */);
impl OperationId { pub const fn name(self) -> &'static str; }

#[derive(Clone, Debug)] pub struct AExpr { /* Arc<Node> */ }
#[derive(Clone, Debug)] pub struct Unary { /* private kind */ }
#[derive(Clone, Debug)] pub struct Binary { /* private kind */ }

pub fn identity() -> Unary;
pub fn add() -> Binary;
impl Unary  { pub fn apply(&self, operand: &AExpr) -> AExpr; pub fn operation_id(&self) -> OperationId; }
impl Binary { pub fn apply(&self, lhs: &AExpr, rhs: &AExpr) -> AExpr; pub fn operation_id(&self) -> OperationId; }
impl AExpr  {
    pub fn then(&self, operation: &Unary) -> AExpr;
    pub fn prepare(&self, engine: &NativeExecutor) -> Result<PreparedPlan, Error>;
    pub fn collect(&self) -> Result<Array, Error>;
}

// src/plan.rs
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct NativeExecutor { /* no fields yet */ }
impl NativeExecutor { pub const fn sequential() -> Self; }

#[derive(Clone, Debug)]
pub struct PreparedPlan { /* validated root, executor */ }
impl PreparedPlan { pub fn execute(&self) -> Result<Array, Error>; }

// src/error.rs
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stage { Preparation, Execution }

#[non_exhaustive]
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Failure {
    ShapeMismatch { operation: OperationId, lhs_len: usize, rhs_len: usize },
    IntegerOverflow { operation: OperationId, position: usize },
}
impl Failure { pub const fn code(&self) -> &'static str; } // a semantic-contracts error code

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Error { /* stage, Box<[Failure]> (non-empty) */ }
impl Error { pub fn stage(&self) -> Stage; pub fn failures(&self) -> &[Failure]; }
impl core::fmt::Display for Error; impl std::error::Error for Error;
```

The operation identities are `OperationId::name()` values `"identity"` and
`"add"`, matching the catalogue names. `add` over `I64` executes
`combobulate_kernel::elementwise::add_i64_into`. ADR-0011 and the developers'
guide record that mapping as the executable identity that later proof bindings
(1.2.5 and PF04) cite, together with the structural digest of
`crates/combobulate-kernel/src/elementwise.rs` (`scripts/structural_digest.py`).

Dependencies:

- New dev-dependency `proptest = "1.12.0"` on the root package (DL-6).
- No new runtime dependency.
- No kernel dependency.
- Verus and vstd stay outside every Cargo manifest, as in ADR-0010.

Make: a new `verus-kernel` target, listed in `.PHONY` beside `verus-probe`. It
depends on nothing that builds Cargo targets, so it does not enter the
gate-order contract. A helper script runs the positive and mutant passes; it
extends `scripts/run_verifier_probes.py` with a `product` command, reusing
`verus_probe` solver selection and located-span checks, with tests under
`scripts/tests/`.

## Revision note

- 2026-11-11: initial draft from Wyvern reconnaissance, awaiting
  community-of-experts review.
