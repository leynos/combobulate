# Combobulate roadmap

Revision 0.2, 6 October 2026. All work remains proposed and open.

Decisions that control acceptance, with their authority, options, and status,
are recorded in the [decision register](decision-register.md).

This roadmap translates `terms-of-reference.md`, `technical-design.md`,
`context.md`, and `language-reference.md` into proposed delivery work. It makes
no date or duration commitments. Every checkbox is open: this pack documents
work, not implementation evidence. Read `technical-design.md` §1 and
`references.md` for the inspected baseline and source limitations.

GIST means Goals, Ideas, Steps, and Tasks. ToR goals G1-G8 supply the outcomes;
phases state falsifiable ideas; steps answer delivery questions; tasks are
review-sized execution units with dependencies, design references, and success
criteria. Unit, property, and fault-injection evidence belongs inside the
implementing task. Cross-feature E2E suites have explicit tasks where their
scope exceeds one implementation review.

Each implementing task carries a proof-first obligation and bet identifiers.
[The bet register](testable-bets.md) records B01-B08, their success witnesses,
negative controls, falsifiers and decision rules. Verus/Kani work belongs in
the slice that changes the corresponding contract, not an isolated proving
phase. A supported profile requires actual downstream proof fixtures before its
public API stabilizes. Optional Polars hooks may be declined; that does not
waive the first-class backend contract or required semantic proofs.

The foundational phase resolves candidate ADRs identified in
`technical-design.md` §15; no accepted ADR or ExecPlan exists in this evidence
set. Core scope ends at 4.3.3, including public consumer and staged-cost gates.
Integration scope has a separate gate at 6.3.4; its real-client experiments
require source access, while synthetic extensions do not. The final phase
contains bounded evaluations, not promised features.

<!-- roadmap:start -->

## 1. Foundational contracts and a demonstrable build spine

Idea: If one small executable semantic kernel can serve ordinary Rust, constant
evaluation, Kani, and Verus, proof-first development can expose downstream
contracts without separate unverified models or mandatory heavy backend
dependencies.

Goals: G1, G2, G6, G7, G8 in `terms-of-reference.md` §6.

This phase permits foundational work, but its output must include a runnable
public path. Document preparation alone does not complete a task.

Gate: Continue only when the pinned shared-kernel and public-only consumer
probes execute and verify with recorded assumptions and non-vacuous negative
controls. Revise the representation or narrow the certified subset if the
toolchains cannot share an executable binding. The Polars probe must report
actual capabilities, not infer them from a version label.

### 1.1. Resolve the decisions that control acceptance

Which constraints are approved, and which remain experiments? The answer bounds
every later implementation and prevents retrospective changes to success
criteria. See `technical-design.md` §§1-2, 15-16.

- [ ] 1.1.1. Record the scope, decision authority, licence, and pre-1.0 API
  policy.
  - See `technical-design.md` §§1-2, 15-16, 17.
  - Proof first: Write decision and exception authority before accepting claims;
    approval is not verification. Bets: B01.
  - Success: ToR Q1/Q4/Q7 have explicit owner decisions; the Core/Integration
    boundary and candidate ADR disposition match all five documents.
- [ ] 1.1.2. Record the numeric, validity, reduction, and macro-staging
  contracts.
  - Requires 1.1.1.
  - See `technical-design.md` §§4-7, 17.
  - Proof first: Write pre/postconditions, empty/failure rules, and a
    non-vacuous example before implementing each primitive. Bets: B01, B02.
  - Success: Accepted contract records resolve association, empty identities,
    dtype conversion, macro grammar, and typed-cell atomicity without
    superseded-name shims.
- [ ] 1.1.3. Pre-register resource and performance acceptance controls.
  - Requires 1.1.1.
  - See `technical-design.md` §§12, 14, 17.
  - Proof first: Pre-register proof/build budgets too; a timeout or changed
    threshold cannot be relabelled as a proved property. Bets: B01, B03.
  - Success: ToR Q2 has named workloads, controls, target environments, budgets,
    uncertainty handling, and thresholds recorded before acceptance
    measurements.
- [ ] 1.1.4. Record the proof-first policy, public proof contract, and
  trusted-boundary authority.
  - Requires 1.1.1, 1.1.2, 1.1.3.
  - See `technical-design.md` §§14, 16-19, 17.
  - Proof first: Specify the merge-state rules before implementing the gate; an
    invalid record with no success witness or with an unreported assumption must
    fail. Bets: B01, B02, B08.
  - Success: The obligation/evidence schema binds claims to executable and
    specification identities, toolchains, scopes, assumptions, and negative
    controls. Approved exceptions have owners, expiry/revisit triggers, and
    claim restrictions; timeout, skipped or vacuous results cannot pass a proof
    gate.

### 1.2. Prove that the proposed package and public path are viable

Can a small public Rust program create and execute an array without Polars or
custom Fn implementations? The result informs feature selection and the
baseline dependency lock. See `technical-design.md` §§3-4, 7, 10.

- [ ] 1.2.1. Establish the facade, macro, and internal semantic-kernel workspace
  with pinned feature/toolchain profiles.
  - Requires 1.1.1, 1.1.4.
  - See `technical-design.md` §§3, 10, 15, 17-19.
  - Proof first: Record each tool/profile capability and trust boundary first;
    compile-only evidence is not a theorem. Bets: B01, B05.
  - Success: Record exact Rust, Kani, Verus, solver, and dependency revisions
    and target/features. Native-only and Polars-enabled builds compile; proof
    tooling is optional for ordinary consumers. The semantic kernel imports
    neither Polars nor glam; select the Rust backend independently of the Python
    Polars 2 version.
- [ ] 1.2.2. Implement the minimal values, expression handles, and ordinary
  application path.
  - Requires 1.1.2, 1.2.1.
  - See `technical-design.md` §§4, 7-8, 17.
  - Proof first: Specify materialized/graph denotation and success witnesses
    first; expose executable identities for later proof bindings. Bets: B01,
    B02.
  - Success: A public fixture constructs an I64 vector, applies identity/add,
    prepares, and collects it without exposing internal graph generics or
    copying input buffers unnecessarily.
- [ ] 1.2.3. Introduce the independent semantic-example runner and
  route-identifying harness.
  - Requires 1.2.2.
  - See `technical-design.md` §14, 17.
  - Proof first: State the oracle independence boundary first; a seeded wrong
    result must fail rather than share the same faulty body. Bets: B01.
  - Success: The harness reads the golden-case contract, reports the selected
    executor, and detects a seeded wrong-result mutation; reference execution
    does not reuse the optimized operation implementation.
- [ ] 1.2.4. Deliver one checked cardinality kernel through runtime, constant
  evaluation, Kani, and Verus.
  - Requires 1.2.3.
  - See `technical-design.md` §§3, 4, 17-18.
  - Proof first: Write the mathematical zero-product and representability
    contract first; require a satisfiable valid-input witness and a seeded
    multiply-before-zero defect that fails the intended check. Bets: B01, B03.
  - Success: The same shipped executable body, or an explicit checked refinement
    to it, passes runtime/const agreement, Kani machine-width overflow/zero
    witnesses, and a Verus cardinality invariant. Pin supported targets and
    reject unsupported static certificates rather than substituting an unchecked
    checker. Record compile/proof cost against pre-registered limits.
- [ ] 1.2.5. Export the first collection model and verified dependency for an
  external identity consumer.
  - Requires 1.2.4.
  - See `technical-design.md` §§4, 17.
  - Proof first: State the logical-view and successful-construction
    postconditions before the implementation; a consumer which asserts a wrong
    value must fail for that assertion. Bets: B01, B02.
  - Success: A separate crate imports only public API/specifications and
    establishes identity over typed I64 storage in both pinned toolchains.
    Ordinary safe constructors check inputs. The published executable binding
    and imported verification metadata identify the same implementation; no
    external_body assertion stands in for the whole executor.
- [ ] 1.2.6. Produce the pinned Polars capability probe and minimal
  explicit-engine execution report.
  - Requires 1.2.1, 1.2.2.
  - See `technical-design.md` §§10, 19, 17.
  - Proof first: Specify capability-evidence admission before probing; a Python
    release number alone must not enable a Rust capability or a strict no-spill
    guarantee. Bets: B05, B06.
  - Success: An actual Rust fixture selects and reports an engine and compares a
    small positional result with native execution. The report records
    documented, tested, unsupported, or inconclusive capability status for every
    PC entry; probe spill-control scope without changing process globals
    concurrently. Missing future capabilities remain unavailable, not emulated
    invisibly.

## 2. Readable numeric pipelines with trustworthy failures

Idea: If public contracts, exact numerics, and preserved comb! notation compose
with the same checked static/runtime cost rules, consumers can write readable
numerical programmes and establish both successful outcomes and controlled
failures without private internals.

Goals: G1, G2, G4, G7, G8 in `terms-of-reference.md` §6.

This slice delivers useful numerical transformations and readable diagnostics
end to end. It does not wait for rendering or relational integration.

Gate: Continue when public numeric programmes, statically admitted/rejected
examples, runtime residual checks, and meaningful downstream proofs pass.
Revise the static subset if compile-cost limits fail; unknowns must remain
visible and no alternate DSL or silent scalar-only proof configuration may
replace comb!.

### 2.1. Make shapes and logical indexing reliable on real values

Do scalars, empty axes, views, and dynamic dimensions share a consistent public
model? The result supplies the base for reductions and rank application. See
`technical-design.md` §§4-5.

- [ ] 2.1.1. Implement checked shapes, nullability, scalar extension, and
  explicit broadcast inference.
  - Requires 1.2.3, 1.2.4, 1.2.5.
  - See `technical-design.md` §§4-5, 14, 17.
  - Proof first: Verus proves cardinality/agreement rules; Kani checks
    machine-size overflow and zero-extents on the shipped checker. Write
    invariants first. Bets: B01, B03.
  - Success: V2 witnesses scalar [], empty [0], zero-times-large extents,
    singleton agreement, and rejected non-scalar ambiguity; seeded
    broadcast/zero-product faults fail.
- [ ] 2.1.2. Implement literal construction, shape queries, iota/range, reshape,
  ravel, and axis permutation.
  - Requires 2.1.1.
  - See `technical-design.md` §§4-5, 7, 17.
  - Proof first: Specify coordinate mapping first; Verus proves
    reshape/permutation relations, Kani checks executable bounds, and Miri/audit
    covers applicable unsafe gaps. Bets: B02.
  - Success: V3 validates logical row-major indexing and scalar transpose
    identity; invalid literal/shape sizes fail before allocation; public
    fixtures expose copies when a view cannot satisfy a consumer.
- [ ] 2.1.3. Implement runtime shape obligations and binding-time checks.
  - Requires 2.1.1.
  - See `technical-design.md` §§4, 8, 17.
  - Proof first: Specify obligation producer/consumer guards first; Kani
    explores binding transitions and Verus relates admitted shapes to model
    facts. Bets: B03, B04.
  - Success: A symbolic filtered size can feed a checked reshape; an impossible
    downstream shape fails before its allocation rather than sampling input data
    during preparation.
- [ ] 2.1.4. Implement checked dense and nullable borrowed views with public
  invariants and observers.
  - Requires 1.2.5, 2.1.3.
  - See `technical-design.md` §§4, 17.
  - Proof first: Declare representation, lifetime, error, and successful-result
    relations first. Verify constructors and index observers against the actual
    body; test non-null and null-parent counterexamples. Bets: B02.
  - Success: Consumers construct shape-checked views and inspect length, shape,
    validity, and checked logical indexing without allocation or private storage
    access. Verus models and Kani constructors cover invalid extents and
    validity lengths; a safe unverified caller cannot bypass runtime validation.

### 2.2. Make numerical results and exceptional paths explicit

Can the evaluator preserve the promised dtype, null, and association rules
without borrowing accidental backend defaults? The result determines which
later optimizations are eligible. See `technical-design.md` §6.

- [ ] 2.2.1. Implement scalar arithmetic, explicit casts, comparisons,
  predicates, and three-valued logic.
  - Requires 1.1.2, 2.1.1.
  - See `technical-design.md` §6, 17.
  - Proof first: Prove/check integer and validity primitives with Kani; separate
    structural/policy claims from floating accuracy and document unsupported
    models before coding. Bets: B02.
  - Success: All core scalar verbs have numeric/special-value tables; checked
    overflow and cast failures have coordinates; Bool counting requires a cast;
    comparison/null/NaN controls pass V5/V8.
- [ ] 2.2.2. Implement exact reductions, left folds, and empty-identity
  handling.
  - Requires 2.2.1.
  - See `technical-design.md` §6, 17.
  - Proof first: Verus proves sequence association and empty/singleton
    traversal; Kani checks signed-zero bits and checked-overflow counterexamples
    on executable paths. Bets: B02.
  - Success: Right subtraction gives 9, left gives 5, singleton -0 remains -0,
    and the MAX regrouping negative control rejects an invalid optimization.
- [ ] 2.2.3. Implement exact prefix scans and explicit left accumulation with
  cost estimates.
  - Requires 1.1.3, 2.2.2.
  - See `technical-design.md` §§6, 12, 17.
  - Proof first: State right-prefix semantics and work count before loops; Verus
    proves sequence/count rules and Kani distinguishes left-scan substitution
    and overflow. Bets: B03.
  - Success: scan(sub) and scan_left(sub) differ as specified; empty scans
    invoke no operation; the generic quadratic route is visible and respects
    admitted work limits.
- [ ] 2.2.4. Implement reducer-state finalization and the core statistical
  aggregates.
  - Requires 2.2.2.
  - See `technical-design.md` §6, 17.
  - Proof first: Specify accumulator/finalizer invariant first; verify
    control/count arithmetic, and disclose floating primitive assumptions
    instead of modelling IEEE values as reals silently. Bets: B02.
  - Success: Mean/variance/stddev follow their specified algorithms,
    null/empty/ddof policies, and count bounds; state merging cannot bypass
    numerical eligibility.
- [ ] 2.2.5. Export reducer-state invariants and typed callable contracts for a
  sequential native aggregate.
  - Requires 2.1.4, 2.2.4.
  - See `technical-design.md` §§6, 9, 17.
  - Proof first: Specify accumulator history and finalization before code; prove
    traversal with Verus and bounded executable failure paths with Kani. A
    wrong-count finalizer and an invalid checked-overflow merge must fail. Bets:
    B02, B07.
  - Success: An external reducer proves the relation between state and processed
    inputs, including empty and failure outcomes. Higher-order contracts
    quantify over all outputs allowed by the callable contract, not one desired
    possible output. A supplied merge function gains no reassociation permission
    without its required law.

### 2.3. Make the preserved macro notation explain itself

Does the established comb! syntax build the same graph as ordinary Rust, while
preserving ownership and source diagnostics? The result determines whether the
frontend earns its complexity. See `technical-design.md` §§7, 13.

- [ ] 2.3.1. Implement comb!, arr!, and array! over the ordinary application
  interface.
  - Requires 2.1.2, 2.2.1.
  - See `technical-design.md` §7, 17.
  - Proof first: Specify macro lowering through ordinary builders before parser
    work; Kani consumer calls and UI tests detect duplicated host evaluation.
    Bets: B02, B03.
  - Success: Public pipeline and literal examples work; malformed stages/ragged
    literals point to original tokens; embedded host expressions execute once;
    no custom Fn implementation is required.
- [ ] 2.3.2. Implement verb!, shared lets, operator composition, sections, and
  flow!.
  - Requires 2.2.4, 2.3.1.
  - See `technical-design.md` §§7-9, 17.
  - Proof first: Specify composition denotation and shared-node/effect relations
    first; prove builder rules and Kani-check bounded graph construction. Bets:
    B02.
  - Success: fork/compose/flow/hook/over/flip/dup and lhs/rhs binding build
    inspectable graphs; an external descriptor participates without a macro-name
    whitelist.
- [ ] 2.3.3. Implement structured errors, provenance lineage, and failed-plan
  explain output.
  - Requires 2.1.3, 2.3.1.
  - See `technical-design.md` §§8, 13, 17.
  - Proof first: Specify error category/provenance preservation first; test UI
    spans and Kani-check bounded provenance transformations, not human
    readability as a theorem. Bets: B02.
  - Success: V1/V10 counterexamples detect duplicated host evaluation and lost
    spans; routine dtype/shape errors display operation and valid suggestions
    without backend types on the first screen.
- [ ] 2.3.4. Deliver a vector-statistics example with a comprehension and
  failure corpus.
  - Requires 2.2.3, 2.3.2, 2.3.3.
  - See `technical-design.md` §§7, 13-14, 17.
  - Proof first: Publish public-only successful/error witnesses; test
    comprehension empirically and identify which semantic claims the chosen
    verifier establishes. Bets: B02.
  - Success: A public example composes reusable statistics and scans without
    private primitives; an independently reviewed equivalent Rust version
    records comprehension differences rather than only line counts.
- [ ] 2.3.5. Expose a sequential native execution route with caller-owned output
  and scratch and graph-meaning contracts.
  - Requires 2.1.4, 2.2.5, 2.3.4.
  - See `technical-design.md` §§7-9, 17.
  - Proof first: Write builder-denotation, preparation-refinement, and
    atomic-output relations first. An always-Err implementation must fail the
    success witness; a partial-write mutation must fail unchanged-output checks.
    Bets: B02, B07.
  - Success: A production-usable native route executes comb! through specified
    builders and preparation, without Polars, private imports, or cfg-dependent
    semantic substitution. Contracts cover values, validity, permitted errors,
    success conditions, and unchanged output on pre-commit failure; insufficient
    scratch is a structured error.

### 2.4. Admit small numerical programmes using static and runtime costs

Can a consumer obtain useful checked resource bounds without encoding every
shape in generic types or changing comb! syntax? The result determines the
certified static subset and the runtime fallback contract. See
`technical-design.md` §§7-8, 12, 18.

- [ ] 2.4.1. Retain static descriptors and implement the restricted shared
  cost-expression evaluator.
  - Requires 1.2.4, 2.3.5.
  - See `technical-design.md` §§7-8, 12, 18, 17.
  - Proof first: State the abstract work/payload model and checked arithmetic
    before implementation. Verus establishes conservative composition and Kani
    checks machine overflow; no mandatory solver runs in downstream macros.
    Bets: B03.
  - Success: Static, symbolic-bounded, and dynamic descriptors share semantic
    identities and the checked analyser. Runtime and constant evaluation agree
    on scalar, zero, product, and exact-prefix-scan cases. Target pointer
    width/layout comes from the target; host escapes still execute only once
    during ordinary construction.
- [ ] 2.4.2. Implement static certification and residual runtime admission with
  precise cost diagnostics.
  - Requires 2.1.3, 2.4.1.
  - See `technical-design.md` §§8, 12-13, 18, 17.
  - Proof first: Prove each admission transition against
    exact/bounded/estimated/unknown meanings; Kani checks next-reservation
    rejection, and Verus states the bound theorem with explicit assumptions.
    Bets: B03, B04.
  - Success: Exact 4096-by-4096 F64 materialization fails a 64 MiB payload
    budget; at-most-4096 bounds report uncertifiable-domain rather than
    universal overflow. Unknown callback cost never becomes zero. Strict mode
    rejects undisclosed obligations; adaptive mode retains checks before
    allocation. Under-budget witnesses succeed.
- [ ] 2.4.3. Deliver an external compile-time-costing and runtime-equivalence
  consumer suite.
  - Requires 2.4.2.
  - See `technical-design.md` §§14, 17-18.
  - Proof first: Use successful and deliberately rejected resource witnesses,
    including zero-times-large dimensions and an underestimated native contract.
    A source-hash match alone must not certify semantics. Bets: B03, B04.
  - Success: Compile-pass/fail consumers retain comb! notation, exercise both
    target-width profiles and a runtime-bound plan, and compare cost records
    without executing host code during compilation. Record build latency and
    diagnostic spans; certificates for changed policy/target/descriptors fail
    validation.

## 3. Matrix and neighbourhood transformations without indexing surprises

Idea: If rank, contraction, and stencil operations share logical coordinates
and infer empty results without sampling data, compact matrix and neighbourhood
programs can remain faithful across layouts and partitions.

Goals: G1, G2, G4, G7, G8 in `terms-of-reference.md` §6.

This slice delivers row normalization, pairwise comparisons, generalized
products, Minesweeper counts, and Life from public primitives.

Gate: Continue when rank/product/stencil examples match the independent
coordinate model and seeded row-boundary/empty-frame faults fail. Revise
convenience rules rather than encode special cases for the examples. The
independent downstream suite and checked native schedule must establish their
scoped contracts before the public proof API stabilizes.

### 3.1. Apply operations to cells without guessing from a first row

Can rank application infer uniform results for arbitrary frames, including
empty ones? The result establishes the contract that native extensions later
inherit. See `technical-design.md` §§4-5, 9.

- [ ] 3.1.1. Implement rank, rank2, each, rows, and bounded cols convenience.
  - Requires 2.1.3, 2.3.2.
  - See `technical-design.md` §5, 17.
  - Proof first: Verus proves frame/cell shape composition without evaluation;
    Kani verifies empty-frame zero-call and empty-cell failure witnesses. Bets:
    B02.
  - Success: V4 verifies [0,3,4] rank-2 transpose -> [0,4,3] with zero calls,
    [0,3] rows(mean) -> [0], and [3,0] rows(mean) failure.
- [ ] 3.1.2. Implement uniform dense cell assembly and schema-contract failures.
  - Requires 3.1.1.
  - See `technical-design.md` §§4-5, 9, 17.
  - Proof first: Specify successful schema and failure relations before
    assembly; Kani rejects nonuniform outputs and Verus preserves logical-cell
    correspondence. Bets: B02.
  - Success: A native test operation returning inconsistent cell shapes fails
    with the first identified conflicting coordinate; it never changes the
    declared result to ragged data silently.

### 3.2. Express matrix relationships and ordered selections directly

Do public indexing, ordering, and product operators replace dimension
manipulation without hiding cost or order? The results inform planner region
and cardinality contracts. See `technical-design.md` §5.

- [ ] 3.2.1. Implement take/drop/reverse/rotate/shift, gather/compress, and
  concat.
  - Requires 2.1.2, 2.1.3, 3.1.1.
  - See `technical-design.md` §5, 17.
  - Proof first: Prove coordinate/selection relations with Verus and Kani-check
    bounds, MIN counts, unknown masks, and checked casts before unsafe access.
    Bets: B02.
  - Success: Coordinate models validate prefix/suffix signs, fill/wrap
    distinctions, selected-axis bounds, nullable-mask policy, and stable
    selection order.
- [ ] 3.2.2. Implement stable sort and grade with explicit exceptional-value
  ordering.
  - Requires 2.2.1, 3.2.1.
  - See `technical-design.md` §§5-6, 17.
  - Proof first: State ordering/stability and exceptional-key equivalence first;
    Verus supplies permutation/stability obligations and Kani checks bounded
    equal-key cases. Bets: B02.
  - Success: Grades are lane-local indices; null/NaN input requires deliberate
    placement; equal keys retain stable order across views and partitions.
- [ ] 3.2.3. Implement outer, outer_cells, generalized inner, and explicit
  batched matmul.
  - Requires 1.1.3, 2.2.2, 3.1.2.
  - See `technical-design.md` §§5-6, 12, 17.
  - Proof first: Specify contraction indexing and association first; Verus
    proves shape/index/work bounds and Kani checks empty contraction and
    arithmetic admission. Bets: B03, B04.
  - Success: Scalar and small-matrix numeric/Boolean/min-plus cases match the
    independent evaluator; mismatched contraction or batch frames fail; empty
    products and output budgets obey the contract.
- [ ] 3.2.4. Implement source-scoped selections and permutation witnesses with
  reusable correspondence lemmas.
  - Requires 2.1.4, 3.2.3.
  - See `technical-design.md` §§4-5, 17.
  - Proof first: State applicability and frame conditions first; prove generic
    element movement in Verus and bounded executable invalid-map cases in Kani,
    including empty selections. Bets: B02.
  - Success: Public Selection and permutation constructors attach facts to
    extent/domain and immutable generation. Consumers prove shared gathers
    preserve correspondence. Reusing a witness on another source, stale
    generation, or incompatible policy fails; duplicates remain legal for gather
    but not for a permutation/restoration witness.

### 3.3. Prove neighbourhood semantics across real boundaries

Can stencil kernels avoid full neighbourhood expansion without changing input
snapshots or boundary rules? The answer validates halo-dependent execution as a
generic facility. See `technical-design.md` §§5, 9, 14.

- [ ] 3.3.1. Implement footprint!, explicit anchors/boundaries, and the scalar
  stencil path.
  - Requires 3.1.2, 3.2.1.
  - See `technical-design.md` §§5, 7, 17.
  - Proof first: Verus proves coordinate/boundary mappings; Kani exercises even
    anchors, extent-one and zero cases. The flattened-wrap mutation must fail.
    Bets: B02.
  - Success: Odd/even anchors, Fill/Wrap/Reflect, single-element axes, and zero
    extents have fixtures; a seeded flattened-horizontal-shift fault fails on a
    rectangular image.
- [ ] 3.3.2. Implement bounded tile-and-halo execution and public
  Minesweeper/Life examples.
  - Requires 1.1.3, 2.3.3, 3.3.1.
  - See `technical-design.md` §§5, 9, 12, 14, 17.
  - Proof first: State halo/snapshot invariants before optimization; prove
    partition equivalence in Verus and Kani-check bounded alias/halo and
    reservation paths. Bets: B04.
  - Success: V6 exercises one-cell and awkward partitions; all reads observe the
    input snapshot; measured temporary storage remains within the admitted
    tile/halo bound.
- [ ] 3.3.3. Implement a small schedule checker and tracked-storage certificate
  for product and stencil schedules.
  - Requires 2.4.3, 3.2.4, 3.3.2.
  - See `technical-design.md` §§8-9, 12, 18, 17.
  - Proof first: Prove checker soundness relative to the explicit
    schedule/kernel resource contracts with Verus; Kani checks allocation
    transitions and rejected malformed schedules. No whole-process RSS guarantee
    follows. Bets: B04.
  - Success: The planner proposes a schedule; a separate checker validates
    index/guard obligations, liveness, distinct backing-buffer capacity,
    halo/scratch reservations, and admission. A native route runs only after
    checking. Underestimated scratch, duplicate alias accounting, missing halo,
    and stale certificates produce distinguishable results.

### 3.4. Let a downstream crate compose proofs over actual array programmes

Can consumers prove useful numeric application properties using public
contracts rather than library internals? This decides which API and
specification surfaces can stabilize. See `technical-design.md` §§14, 17-18.

- [ ] 3.4.1. Deliver public-only Kani and Verus consumer programmes and
  proof-compatibility controls.
  - Requires 2.3.5, 3.3.3.
  - See `technical-design.md` §§14, 17-18.
  - Proof first: Define consumer goals before freezing signatures; retain failed
    fixtures for wrong denotation, always-Err, private API dependency, and fake
    trusted executor. Record all remaining assumptions and exact Kani scopes.
    Bets: B02, B08.
  - Success: External fixtures verify a transpose round trip, shared
    gather/validity, custom callable/reducer, and preallocated atomic failure
    through actual comb! calls. Both success and error branches have witnesses.
    Breaking a public pre/postcondition or executable binding invalidates a
    consumer proof; proof-SDK configuration does not swap executors.

## 4. Polars-backed workflows with visible semantic and resource boundaries

Idea: If a capability-probed adapter treats streaming order, spill effects, and
optimizer permissions as contracts, Polars 2-era improvements can benefit real
workflows without weakening array meaning, downstream proof assumptions, or
stated resource limits.

Goals: G2, G4, G6, G7, G8 in `terms-of-reference.md` §6.

This is the Core acceptance slice. Core publication is a separate authority
decision after evidence; an accessible repository and licence remain
prerequisites.

Gate: Accept the Core scope only after B01-B05 and the Core part of B08 pass,
and B06 records a measured adoption or an explicit decline/defer decision, with
scoped verifier evidence, public consumer fixtures, compile/runtime cost
admission, forced-engine conformance, and explicit disk-policy controls.
Unsupported future capabilities stay unavailable. Record negative benefit
results and narrow acceleration rather than weakening semantics.

### 4.1. Cross between ordered tables and arrays deliberately

Can an ordered, homogeneous array emerge from a relational pipeline without
name-based alignment or discarded validity? The result defines the Polars
interoperability boundary. See `technical-design.md` §10.

- [ ] 4.1.1. Implement ordered table-to-array and named array-to-table
  conversion.
  - Requires 1.2.1, 3.2.1.
  - See `technical-design.md` §10, 17.
  - Proof first: Specify the relational-to-positional contract first; check the
    adapter locally and force backend ordering counterexamples in integration
    tests. Bets: B05.
  - Success: Column order/common dtype and output names are explicit; an
    unordered relational source cannot masquerade as established positional
    correspondence.
- [ ] 4.1.2. Implement chunked scalar and nested-array import/export with parent
  validity.
  - Requires 2.1.2, 4.1.1.
  - See `technical-design.md` §10, 17.
  - Proof first: Prove local parent-validity/index mapping where expressible;
    Kani checks small chunk/slice cases and audit/Miri covers unsafe
    representation obligations. Bets: B05.
  - Success: Round-trips preserve logical order and invalid parents; flattening
    cannot reveal hidden child values; copies/rechunking appear in explain
    output.
- [ ] 4.1.3. Implement explicit streaming order, nested-validity, and
  batch-boundary contracts.
  - Requires 1.2.6, 4.1.2.
  - See `technical-design.md` §§5, 9-10, 19, 17.
  - Proof first: Specify index/validity obligations in the adapter before
    lowering. Verify local validators with Kani or Verus, and run backend
    conformance with row-shuffle, lost-parent-validity, and split-segment
    negative controls. Bets: B05.
  - Success: Forced available engines preserve declared position/validity
    through one-cell and awkward batches, including empty versus null segments
    and zero-width frames. Missing order prevents an alignment claim; logical
    indices restore correspondence only where required. Prefix/halo state
    crosses physical boundaries.

### 4.2. Execute only faithful backend regions

Can capability matching choose useful native Polars operations while rejecting
wrong null/order/guard semantics? The result determines the supported backend
matrix. See `technical-design.md` §§8-10.

- [ ] 4.2.1. Implement lowering registration and policy-aware Polars elementwise
  regions.
  - Requires 2.3.3, 3.4.1, 4.1.2, 4.1.3.
  - See `technical-design.md` §§8-10, 17.
  - Proof first: Write lowering eligibility predicates before registration;
    Kani/Verus validate the owned decision logic, while upstream execution
    remains a reported external assumption. Bets: B05, B06.
  - Success: Forced eligible operations exercise real Polars expressions; null,
    cast, and failure contracts match; ambiguous registrations and unsupported
    policies return domain errors.
- [ ] 4.2.2. Implement cardinality-aware region boundaries and faithful
  reduction/scan routes.
  - Requires 2.2.3, 3.2.3, 4.2.1.
  - See `technical-design.md` §§6, 8-10, 17.
  - Proof first: Prove region-boundary and exact-association checks before
    enabling routes; forced-engine tests must not compare two uses of the same
    fallback. Bets: B05.
  - Success: Differing-length results do not enter a flat dataframe without
    representation changes; exact scans cannot silently route to a
    left-cumulative kernel; fallback choice is visible.
- [ ] 4.2.3. Integrate native halo/product kernels and guard-aware rewrite
  eligibility.
  - Requires 3.3.2, 4.2.2.
  - See `technical-design.md` §§8-10, 17.
  - Proof first: Prove local rewrite side conditions before enabling fusion;
    Kani checks guard/CSE counterexamples and Verus relates logical and physical
    schedules. Bets: B04, B06.
  - Success: Fused and unfused paths agree on values and failures; a fallible
    branch cannot move outside a guard; custom batch kernels retain partition
    contracts.
- [ ] 4.2.4. Gate dtype specialization, deterministic plugins, and physical
  provenance by measured backend capabilities.
  - Requires 1.2.6, 4.2.3.
  - See `technical-design.md` §§8-10, 13, 19, 17.
  - Proof first: Prove local eligibility rules with Kani or Verus; a
    deterministic-but-fallible guarded callback must not gain speculative
    execution permission. Compare enabled/disabled routes for benefit under
    pre-registered controls. Bets: B06.
  - Success: Use only public interfaces available in the pinned Rust revision.
    Planning-time dtype specialization retains cell/extension metadata without
    claiming compile-time evaluation. CSE requires effect/guard/failure
    eligibility, and provenance maps to source spans. Unsupported features
    produce an explicit capability result.
- [ ] 4.2.5. Implement execution I/O and spill policies with truthful control
  scope.
  - Requires 3.3.3, 4.2.4.
  - See `technical-design.md` §§8, 12, 19, 17.
  - Proof first: State admission and cleanup invariants first; Kani checks
    policy transitions and failure paths. Integration tests exercise
    quota/cancel failures and concurrent-policy conflicts without claiming
    untracked backend allocation is verified. Bets: B05, B04.
  - Success: Default execution forbids unrequested temporary-disk effects. A
    strict route without enforceable no-spill control refuses admission. Opt-in
    spill records quota, location, cleanup and cancellation semantics;
    process-global controls cannot masquerade as per-query isolation.
    Distinguish streamed sinks from materialized results and operation-specific
    OOC support.

### 4.3. Release a measured and supportable numeric core

Does the integrated core meet its actual cost, diagnostic, and conformance
promises on selected environments? The outcome permits a release decision
rather than an assumption of readiness. See `technical-design.md` §§12-16.

- [ ] 4.3.1. Implement admitted allocation/work limits, cancellation
  checkpoints, and cost reporting.
  - Requires 1.1.3, 3.3.3, 4.2.3, 4.2.5.
  - See `technical-design.md` §§8, 12-13, 17.
  - Proof first: Verus proves tracked reservation invariants and Kani checks
    failures/cancellation; distinguish resource estimates from enforced bounds
    before admission code. Bets: B04, B05.
  - Success: Known excessive work fails before execution, dynamic expansion
    stops before the next forbidden allocation, untracked backend/native
    allocation is labelled, and no hard process ceiling is falsely reported.
- [ ] 4.3.2. Deliver the route-forced E2E and combinatorial core conformance
  suite.
  - Requires 2.4.3, 3.2.2, 3.4.1, 4.3.1.
  - See `technical-design.md` §14, 17.
  - Proof first: Run actual consumer/verifier and backend routes, plus seeded
    faults; skipped routes and unmet tool bounds remain incomplete evidence.
    Bets: B02, B05, B08.
  - Success: V1-V10 run over the declared interaction matrix with route IDs and
    negative controls; tests cannot compare the same unnoticed fallback against
    itself.
- [ ] 4.3.3. Publish a Core acceptance dossier and reference/example coverage
  report.
  - Requires 1.1.1, 4.3.2.
  - See `technical-design.md` §§2, 14-16, 17.
  - Proof first: Audit proof coverage, non-vacuity, TCB, exact bindings,
    cost/capability records, and open exceptions before the release decision.
    Bets: B01, B08.
  - Success: Every Core catalogue row maps to implementation evidence or an
    explicitly approved scope revision; measurements meet pre-registered gates;
    owner release/publication decisions remain separate from test success. Core
    admission also requires B01-B05 and the Core portion of B08, a documented
    B06 adoption/decline/defer decision, all required proof obligations
    discharged or scope narrowed without weakening the user mandate, and a
    published trusted-boundary report. No skipped backend or verifier result
    counts as success.

## 5. Typed native collections without flattening domain meaning

Idea: If typed cells, layout-aware adapters, and declarative native contracts
remain independent of Polars, geometry-shaped batches can reuse readable scalar
kernels without losing semantic types or correspondence.

Goals: G3, G5, G6, G7 in `terms-of-reference.md` §6.

Synthetic geometry fixtures can proceed without a trasic checkout. They
establish extension capability, not real trasic adoption or external-renderer
compatibility.

Gate: Continue when independently packaged numeric and typed extensions work
without core patches, preserve layout/validity/correspondence, and show
acceptable measured overhead. Decline automatic batching where the direct loop
remains clearer or cheaper.

### 5.1. Let a third party extend the collection algebra

Can an external crate describe schemas and execution properties with low
ceremony and no internal imports? The answer tests the open extension boundary.
See `technical-design.md` §§4, 9.

- [ ] 5.1.1. Implement typed Batch values and native operation schema/contract
  registration.
  - Requires 3.1.2, 4.2.1.
  - See `technical-design.md` §§4, 9, 17.
  - Proof first: Specify cell models and runtime-safe contract validation first;
    Verus/Kani check owned schema boundaries without trusting metadata for
    unchecked safety. Bets: B02.
  - Success: `Batch<T>` keeps internal coordinates closed; native calls supply
    empty-frame inference; wrong output schemas fail without relying on metadata
    for unchecked safety.
- [ ] 5.1.2. Implement batch-dispatched map_cells and the extension conformance
  harness.
  - Requires 5.1.1.
  - See `technical-design.md` §§9, 14, 17.
  - Proof first: Specify higher-order map traversal first; prove preservation
    for an arbitrary cell/kernel relation and check bounded executable errors
    with Kani. Bets: B02, B07.
  - Success: A compiled loop uses one region dispatch; faulting declarations and
    unsupported partition claims fail the harness; evidence records actual
    tested bounds.
- [ ] 5.1.3. Deliver independently packaged numeric and typed extension
  examples.
  - Requires 5.1.2.
  - See `technical-design.md` §§9, 14, 17.
  - Proof first: Use external consumer proof fixtures without private imports or
    assumed executor bodies; demonstrate a wrong user contract is rejected.
    Bets: B02.
  - Success: V11 proves both fixtures use only public interfaces and can
    register a lowering without editing core or implementing an impossible
    foreign-trait/foreign-type pairing.
- [ ] 5.1.4. Lift consumer-supplied kernel contracts through typed batch
  application.
  - Requires 3.4.1, 5.1.3.
  - See `technical-design.md` §§9, 17.
  - Proof first: Export map pre/post and error/frame contracts before extension
    interfaces stabilize. Verus checks higher-order composition; Kani exercises
    actual custom kernels under declared bounds and deliberate contract defects.
    Bets: B02, B07.
  - Success: External typed native functions retain their
    executable/specification binding through map_cells; an arbitrary cell type
    can remain uninterpreted in structural proofs. Consumer pre/postconditions
    compose without proving Polars or glam internals. Opaque contracts remain
    explicitly trusted or exclude proof-required routes.

### 5.2. Cross the glam and component boundary honestly

Do declared cell schemas make checked borrowing and conversion transparent
across target layouts? The result bounds zero-copy claims and typed-kernel
performance. See `technical-design.md` §10.

- [ ] 5.2.1. Implement glam cell adapters, explicit components, and checked
  reconstruction.
  - Requires 4.1.2, 5.1.2, 5.1.4.
  - See `technical-design.md` §10, 17.
  - Proof first: State representation and component refinement before adapters;
    verify owned transforms where supported, and label glam math/unsafe layouts
    separately. Bets: B02, B07.
  - Success: Vec3/Vec3A/DVec3 and matrix fixtures preserve component order,
    parent validity, alignment, and domain checks; matrix row/column mapping is
    not inferred from raw layout.
- [ ] 5.2.2. Implement typed-view eligibility and measured layout conversion
  reporting.
  - Requires 4.3.1, 5.2.1.
  - See `technical-design.md` §§10, 12, 14, 17.
  - Proof first: Prove/check eligibility arithmetic and lifetime boundaries;
    Kani coverage does not replace unsafe audit or certify an untested SIMD
    route. Bets: B07.
  - Success: SIMD/scalar and AoS/SoA/native/Arrow cases expose borrow success or
    repack; invalid alignment/length/validity rejects borrowing; copied bytes
    and conversion time are measured separately.

### 5.3. Preserve identity and actual guarded execution across batches

Can selection and resource binding preserve the identity of each logical item,
including inactive lanes? The outcome controls whether rendering-shaped
orchestration is safe to attempt. See `technical-design.md` §§4, 8, 11.

- [ ] 5.3.1. Implement domain mappings, zip_aligned/zip_positional, compact, and
  restore.
  - Requires 3.2.1, 5.1.2.
  - See `technical-design.md` §§4, 11, 17.
  - Proof first: Verus proves generic origin/selection/restoration relations;
    Kani rejects equal-length different-domain and duplicate-writer cases. Bets:
    B02, B07.
  - Success: Equal-sized but differently reordered batches fail aligned zip;
    explicit positional pairing works; restoration validates unique in-range
    indices and preserves untouched template cells.
- [ ] 5.3.2. Implement masked_apply with explicit inactive and unknown-mask
  policies.
  - Requires 4.2.3, 5.3.1.
  - See `technical-design.md` §§9, 11, 17.
  - Proof first: State active-only callable preconditions and
    no-inactive-invocation before implementation; verify guard lowering and its
    negative controls with both tools at their stated scope. Bets: B07.
  - Success: A deliberately faulting inactive kernel is never invoked; actual
    masks or compact/evaluate/restore pass V7; select-style eager evaluation
    fails the negative control.
- [ ] 5.3.3. Implement parameterized prepared plans and
  lifetime/generation-checked resources.
  - Requires 2.1.3, 4.3.1, 5.1.1.
  - See `technical-design.md` §§4, 8, 11-12, 17.
  - Proof first: Specify resource/binding generations before caching; Kani
    explores stale handles and Verus preserves witness validity across permitted
    reuse. Bets: B04, B07.
  - Success: Plans reuse schema work without caching old results; stale resource
    generations/incompatible bindings fail; borrowed resources cannot outlive
    execution; sample reads occur at the declared stage.
- [ ] 5.3.4. Deliver downstream proofs of aligned selection and genuinely masked
  custom kernels.
  - Requires 5.1.4, 5.3.2, 5.3.3.
  - See `technical-design.md` §§4, 9, 11, 17.
  - Proof first: Write the active-cell higher-order contract before the harness
    and implementation; include nonempty active and inactive witnesses, not an
    all-false mask that proves nothing about results. Bets: B02, B07.
  - Success: Public-only Kani and Verus consumers require the kernel
    precondition only on active valid cells and establish preserved
    origin/order. A faulting inactive cell never invokes the callable; stale
    witnesses and eager select substitutions fail. Concurrent/SIMD
    implementations keep distinct evidence from the sequential native proof.

## 6. Segmented work and measured rendering adoption

Idea: If segmented collections and explicit accumulation effects preserve
domain provenance and sample identity, selected CSG and tile workflows can
remove coordination code without replacing their numerical algorithms.

Goals: G2, G3, G4, G5, G7 in `terms-of-reference.md` §6.

This phase closes the collection features needed by demanding-client
experiments. It does not impose a wavefront integrator, GPU backend, or new CSG
tie policy.

Gate: Accept Integration scope only after the typed/segmented suite and
relevant adoption evidence pass. Record a continue, revise, or decline result
separately for each trasic experiment; lack of repository access leaves
adoption unverified, not failed or complete. B07/B08 and all public Integration
proof contracts require actual downstream evidence even when the real-client
adoption decision is deferred.

### 6.1. Represent variable output counts without pretending they are dense

Can segmented offsets and expansion maps retain empty segments, ownership, and
bounded memory? The answer informs CSG events and reconstruction splats. See
`technical-design.md` §§4, 9, 11-12.

- [ ] 6.1.1. Implement `Segmented<T>`, per_segment, and flat_map_cells.
  - Requires 4.3.1, 5.1.2, 5.3.1.
  - See `technical-design.md` §§4, 9, 11, 17.
  - Proof first: Prove segment invariants with Verus and check malformed
    offsets/expansion in Kani; no first-segment schema sampling. Bets: B07.
  - Success: Offset monotonicity/terminal length checks hold, empty segments
    infer schema, and variable cell outputs never silently become dense;
    expansion respects admitted budgets.
- [ ] 6.1.2. Implement explicit replication/cycling and stable unique/membership
  integration verbs.
  - Requires 3.2.2, 6.1.1.
  - See `technical-design.md` §§5-6, 12, 17.
  - Proof first: Specify count and key-equivalence rules first; Verus proves
    maps and Kani checks checked sums/empty cycles and stable equivalence cases.
    Bets: B07.
  - Success: Replication and cycling validate empty/count rules and mapping
    provenance; unique/member use the documented null/NaN/signed-zero key
    equivalence with stable order.
- [ ] 6.1.3. Export segmented logical views and checked segment ownership for
  downstream verification.
  - Requires 5.3.4, 6.1.2.
  - See `technical-design.md` §§4, 11, 17.
  - Proof first: Specify generic segment/selection relations first; Verus proves
    arbitrary-size structural invariants and Kani checks malformed offsets,
    target-width arithmetic, and bounded expansion paths. Bets: B02, B07.
  - Success: Public SegmentedView constructors prove monotonic offsets/terminal
    length and expose segment contents without storage internals. An external
    consumer proves empty-segment preservation and variable-output ownership.
    Invalid offsets and over-budget expansion fail before access or allocation.

### 6.2. Accumulate indexed contributions with a visible effect boundary

Can the engine describe collision, weighting, order, and cancellation without
hidden shared mutation? The result determines whether film accumulation is a
safe consumer. See `technical-design.md` §§6, 11-12.

- [ ] 6.2.1. Implement reduce_by and scatter_reduce using declared reducer
  state.
  - Requires 2.2.4, 5.3.3, 6.1.1, 6.1.3.
  - See `technical-design.md` §§6, 11, 17.
  - Proof first: Specify accumulator history and collision order before loops;
    Verus proves reduction/merge obligations and Kani checks executable
    bounds/failure paths. Bets: B07.
  - Success: Key/index bounds and collision policies are explicit;
    weighted-splat fixtures preserve their denominators and prescribed order;
    merge eligibility never assumes floating associativity.
- [ ] 6.2.2. Implement tile-local execute_into commit and cancellation
  semantics.
  - Requires 4.3.1, 6.2.1.
  - See `technical-design.md` §§11-12, 17.
  - Proof first: Write atomic commit/frame conditions first; prove the
    sequential transition relation and Kani-check success, precommit failure,
    and cancellation reachability. Bets: B07.
  - Success: V7 state-machine witnesses show no destination change before
    successful commit and no pre-commit cancelled tile commits; non-cooperative
    kernel latency remains an explicit limit.
- [ ] 6.2.3. Deliver the typed/segmented/resource combinatorial acceptance
  suite.
  - Requires 5.2.2, 5.3.2, 6.1.2, 6.2.2.
  - See `technical-design.md` §14, 17.
  - Proof first: Exercise actual typed consumers and claimed backends; negative
    controls must preserve enough valid input to expose the intended wrong
    behaviour. Bets: B07, B08.
  - Success: Mandatory mask/fallibility/fusion,
    parent-validity/components/import, and segment/partition/cancellation
    combinations exercise real routes; seeded correspondence and
    duplicate-commit faults fail.
- [ ] 6.2.4. Publish downstream reducer and tile-commit proofs with the
  Integration evidence boundary.
  - Requires 5.3.4, 6.1.3, 6.2.3.
  - See `technical-design.md` §§6, 11, 14, 17.
  - Proof first: Prove sequential state transitions and frame conditions; list
    scheduler, unsafe adapter, numerical algorithm, and external effects
    separately in the trusted basis. A sequential proof is not a race-freedom
    proof. Bets: B07, B08.
  - Success: Both toolchain consumers establish accumulator-history correctness
    and unchanged destination on pre-commit error/cancellation. Successful
    commit and cancellation paths are reachable. Duplicate commit, wrong
    denominator, and erased callback assumptions fail. API/specification drift
    invalidates the right dependent evidence.

### 6.3. Decide whether actual trasic adoption earns its cost

Which concrete geometry and render workflows improve without losing meaning or
exceeding agreed overhead? Each experiment can reject adoption independently
and must inform the final integration boundary. See `technical-design.md` §§11,
14-16.

- [ ] 6.3.1. Pin the trasic revision, kernels, oracles, and experiment-specific
  acceptance controls.
  - Requires 1.1.3, 5.1.3.
  - See `technical-design.md` §§1, 11, 14-16, 17.
  - Proof first: State which application properties follow from collection
    contracts and which need domain/oracle evidence before measuring adoption.
    Bets: B07.
  - Success: Q5 resolves against an accessible actual source tree; direct-loop
    baselines and compatibility oracles are named; unavailable access leaves
    these experiments explicitly blocked.
- [ ] 6.3.2. Run the packet-geometry adoption experiment through the actual
  scalar kernels.
  - Requires 5.2.2, 5.3.2, 6.3.1.
  - See `technical-design.md` §§11, 14, 17.
  - Proof first: Compose the packet consumer contract first; verify structural
    correspondence independently of the trusted numerical intersection
    implementation. Bets: B07.
  - Success: Record correctness, preparation/execution overhead,
    allocations/layout changes, and comprehension for singleton/small/large
    batches; publish continue/revise/decline without changing the kernel to
    favour the abstraction.
- [ ] 6.3.3. Run the segmented CSG boundary-event adoption experiment.
  - Requires 6.1.1, 6.2.3, 6.3.1.
  - See `technical-design.md` §§11, 14, 17.
  - Proof first: Prove segment ownership through public contracts; geometric
    coincidence/tie correctness needs its own domain proof or external evidence.
    Bets: B07.
  - Success: Compare empty/coincident/tangent events and material/orientation
    provenance against the chosen domain oracle; generic stable sorting is not
    accepted as a substitute for CSG tie semantics.
- [ ] 6.3.4. Run the complete tile adoption experiment and record the
  Integration release decision.
  - Requires 6.2.3, 6.2.4, 6.3.2, 6.3.3.
  - See `technical-design.md` §§11-16, 17.
  - Proof first: Carry the consumer proof scope and remaining
    numerical/scheduler assumptions into the adoption dossier; no release claim
    exceeds the evidence. Bets: B07, B08.
  - Success: Sample identity, weighting, cancellation, output, peak storage, and
    comprehension meet the pre-registered controls or produce explicit
    revision/decline decisions; no core/runtime benefit is inferred from a
    merged adapter alone. Integration proof obligations and downstream fixtures
    pass before publishing corresponding proof-capable APIs, independently of
    whether trasic adoption continues.

## 7. Deferred extensions after the core contract earns trust

Idea: If the core and any adopted integrations have explicit evidence and
stable requirements, broader capabilities can be evaluated on user value
without silently destabilizing the established semantics.

Goals: G3, G5, G6, G7, G8 in `terms-of-reference.md` §6.

Deferred scope is not required to complete the Core or Integration acceptance
gates. Explicit non-goals remain excluded even if adjacent extensions are
investigated.

Gate: Promote an extension only after a bounded proposal names its users,
semantics, evidence, and cost. A declined proposal is a valid outcome. These
tasks do not promise the deferred implementation.

### 7.1. Evaluate specialized numerical engines against an actual workload

Would a dense decomposition/FFT route solve a demonstrated problem better than
an external library call? The outcome controls whether another adapter is
justified. See `technical-design.md` §§2, 10, 15.

- [ ] 7.1.1. Prepare a workload-backed proposal for dense linear algebra or
  signal operations.
  - Requires 4.3.3.
  - See `technical-design.md` §§2, 10, 15, 17.
  - Proof first: Any promoted backend requires a proof-first contract and
    refinement/TCB disposition before implementation, including numeric
    equivalence. Bets: B08.
  - Success: Specify exact versus relaxed numerical policy, materialization/copy
    cost, and existing-library alternatives; accept or decline without adding an
    unmeasured backend.

### 7.2. Evaluate adaptive control and advanced scalar domains

Does a real application require graph-level iteration or additional scalar
families rather than a named native kernel? The outcome bounds any semantic
expansion. See `technical-design.md` §§2, 6, 9.

- [ ] 7.2.1. Prepare separate contracts for demonstrated adaptive-control or
  dtype needs.
  - Requires 5.1.3.
  - See `technical-design.md` §§2, 6, 9, 17.
  - Proof first: Specify termination, effects and scalar model before promotion;
    an unsupported proof domain cannot become an implicit trusted primitive.
    Bets: B08.
  - Success: Each proposal states termination/domain/failure rules, inference
    obligations, and existing-kernel alternatives; no list-monad or
    arbitrary-loop claim enters the core by implication.

### 7.3. Evaluate accelerator compilation only with a measured execution case

Can GPU/JIT or differentiation benefits pay for their compiler, control-flow,
and verification obligations? The outcome determines whether a new project
boundary is necessary. See `technical-design.md` §§2-3, 9, 15.

- [ ] 7.3.1. Produce a separate accelerator/differentiation architecture and
  cost case.
  - Requires 6.3.4.
  - See `technical-design.md` §§2-3, 9, 15, 17.
  - Proof first: Promotion requires a new execution/refinement and concurrency
    proof plan; scalar evidence cannot certify the accelerator by association.
    Bets: B08.
  - Success: A representative adopted workload, transfer/control-flow costs, and
    verification plan justify or reject the extension; no Rust array syntax
    alone counts as a performance case.

<!-- roadmap:end -->
