# Combobulate testable bets

Revision 0.2, 6 October 2026. All experiments are planned, not run. The
[roadmap](roadmap.md) schedules their implementation and acceptance work.
[The technical design](technical-design.md) owns the required contracts; this
register records how the proposed mechanisms can be falsified.

`spec/bets.json` is the machine-readable master. Each bet names a positive
witness, a deliberate defect, a falsifier and a response. Categorical
correctness criteria apply now; performance, proof-runtime and build-cost
thresholds are pre-registered as controls `AC-01` to `AC-07` in
`spec/acceptance-controls.json` before any acceptance measurement. No benchmark
result or verification success is implied by a completed design document.

B01-B05 and the applicable B07/B08 claims require passing evidence for the
advertised release scope. B06 concerns optional upstream hooks: a supported,
measurably useful implementation or an explicit decline/defer decision closes
the experiment. It cannot waive the first-class Polars conformance requirement.
A scope revision cannot convert unknown costs or unproved assumptions into
certified results.

<!-- bets:start -->

## B01. One executable semantic core supports proof-first development

Hypothesis: A dependency-light kernel can share production, const-evaluated,
Kani-checked and Verus-verified executable semantics at acceptable proof/build
cost.

Success witness: The cardinality kernel and external identity consumer succeed
in every declared profile, with matched executable/specification identity and a
recorded target-aware contract.

Negative control: Multiply before noticing a zero extent; remove a constructor
invariant; suppress a failed harness. Each must fail its intended gate.

Falsifier: The selected language/toolchain subset needs an unproved substitute
executable body, a trusted whole-executor axiom, or proof costs above
pre-registered limits.

Decision rule: Revise the kernel representation or narrow the certified subset
before stabilization; do not abandon the proof-first requirement or hide a
duplicate checker.

Measurement: Record workload, compiler/verifier/backend revisions,
target/features, assumptions, and cost against the pre-registered acceptance
controls (spec/acceptance-controls.json). Correctness gates are categorical;
empirical thresholds are the registered controls.

Requirements: R8, R10. Tasks: 1.1.4, 1.2.4, 1.2.5, 4.3.3.

Status: planned-not-run.

## B02. Consumers compose application proofs through the public API

Hypothesis: Logical views, typed checked inputs, and higher-order contracts let
separate consumer crates verify useful programmes without internal imports or
new notation.

Success witness: Kani and Verus consumers establish round-trip and selection
properties through comb!, custom kernels and reducers, including success and
failure witnesses with exact scopes.

Negative control: Wrong transpose result, always-Err executor, stale source
witness, or an assumed executor postcondition must not pass.

Falsifier: A consumer must unfold private executor code, import private
symbols, change executable routes under proof cfg, or assume the very property
being claimed.

Decision rule: Revise public contracts/views and preserve production bindings
before stabilizing them; record unsupported advanced properties explicitly.

Measurement: Record workload, compiler/verifier/backend revisions,
target/features, assumptions, and cost against the pre-registered acceptance
controls (spec/acceptance-controls.json). Correctness gates are categorical;
empirical thresholds are the registered controls.

Requirements: R3, R9. Tasks: 1.2.5, 2.1.4, 2.3.5, 3.2.4, 3.4.1, 5.1.4, 5.3.4,
6.1.3.

Status: planned-not-run.

## B03. Compile-time admission is useful without type-level shape machinery

Hypothesis: Static or bounded descriptors can discharge useful resource
obligations through the same restricted analyser used during preparation and
execution.

Success witness: Exact 4096^2 non-null F64 materialization rejects 64 MiB;
bounded inputs distinguish uncertifiable domain from certain excess; smaller
exact inputs pass. Runtime and const checks agree on both target-width profiles.

Negative control: Treat unknown as zero, treat an upper bound as a lower bound,
use host usize layout, or execute a host configuration read during compilation.

Falsifier: The compiler accepts a known over-budget case, rejects all dynamic
uses, reports false certainty, or needs unacceptable compile latency to certify
the agreed examples.

Decision rule: Reduce static expression/shape scope and retain explicit runtime
admission; strict certification fails closed without changing comb! ergonomics.

Measurement: Record workload, compiler/verifier/backend revisions,
target/features, assumptions, and cost against the pre-registered acceptance
controls (spec/acceptance-controls.json). Correctness gates are categorical;
empirical thresholds are the registered controls.

Requirements: R4, R10. Tasks: 2.4.1, 2.4.2, 2.4.3.

Status: planned-not-run.

## B04. A small checker can validate scoped resource and rewrite claims

Hypothesis: A planner can propose schedules while a smaller checked kernel
validates shape, guard, liveness and resource obligations independently of
planner heuristics.

Success witness: Admitted native schedules respect distinct live backing
capacities plus scratch/halos under declared kernel contracts; runtime
reservations reject the first forbidden expansion.

Negative control: Understate halo scratch, reuse a stale certificate,
double-count one alias, omit a guard or permit untracked disk writes in a
strict profile.

Falsifier: The checker admits a violating schedule, certifies choices the
backend may replace with unbounded alternatives, or relies on an unvalidated
kernel declaration as unconditional evidence.

Decision rule: Restrict schedules/capabilities or require runtime checks;
narrow certificates to tracked resources and list external assumptions instead
of promising process RSS.

Measurement: Record workload, compiler/verifier/backend revisions,
target/features, assumptions, and cost against the pre-registered acceptance
controls (spec/acceptance-controls.json). Correctness gates are categorical;
empirical thresholds are the registered controls.

Requirements: R4, R8, R10. Tasks: 2.4.2, 3.3.3, 4.2.5, 4.3.1.

Status: planned-not-run.

## B05. Streaming Polars preserves the positional and resource contract

Hypothesis: Explicit engine/order/spill policies can admit useful Polars 2-era
regions while preserving correspondence, validity and bounded owned resources.

Success witness: Pinned Rust engines pass forced-order/null/empty/chunk/halo
cases; no-spill requirements are enforced or admission refuses the route.
Opt-in spill exercises quota and cancellation cleanup.

Negative control: Shuffle rows, lose a parent validity bit, split a segment, or
apply a process-global policy as if it were independent per-query state.

Falsifier: A supported route changes positional meaning, performs undisclosed
I/O, or reports a hard per-plan bound without an available control.

Decision rule: Disable the capability or select a faithful explicitly permitted
route; keep strict policy failures visible and do not infer support from Python
versioning.

Measurement: Record workload, compiler/verifier/backend revisions,
target/features, assumptions, and cost against the pre-registered acceptance
controls (spec/acceptance-controls.json). Correctness gates are categorical;
empirical thresholds are the registered controls.

Requirements: R5, R11. Tasks: 1.2.6, 4.1.3, 4.2.5, 4.3.2.

Status: planned-not-run.

## B06. New upstream optimizer hooks produce measurable benefit without semantic leakage

Hypothesis: Dtype-aware planning, deterministic-plugin optimization and
physical provenance can improve the adapter when the pinned Rust API exposes
compatible capabilities.

Success witness: A named workload compares capability-enabled and disabled
routes under pre-registered criteria; results/failures match and source
attribution survives. Unsupported hooks have explicit dispositions.

Negative control: Use determinism alone to speculate a fallible branch, treat
metadata as a valid Normal3, or claim planning-time specialization is Rust
compile-time evaluation.

Falsifier: No supported interface exists, required equivalence fails, or
measured benefit does not justify coupling and maintenance cost.

Decision rule: Decline that optional hook while retaining the semantic port and
first-class Polars baseline; capability availability is not a mandate to use it.

Measurement: Record workload, compiler/verifier/backend revisions,
target/features, assumptions, and cost against the pre-registered acceptance
controls (spec/acceptance-controls.json). Correctness gates are categorical;
empirical thresholds are the registered controls.

Requirements: R5, R11. Tasks: 1.2.6, 4.2.4, 4.3.3.

Status: planned-not-run.

## B07. Typed and segmented consumers prove orchestration without replacing domain mathematics

Hypothesis: Public cell, mask, segment and reducer contracts let
rendering-shaped consumers establish identity, active-only execution and atomic
commit independently of their numeric kernels.

Success witness: Both downstream toolchain fixtures establish correspondence,
segment ownership, reducer history and pre-commit unchanged output with actual
user kernels; geometry/scheduler assumptions remain separately listed.

Negative control: Invoke a faulting inactive kernel, permute only normals, drop
empty segments, merge float accumulators without permission, or commit a
cancelled tile.

Falsifier: The proof requires inventing numerical correctness, assuming
callback termination without disclosure, or silently replacing the
concurrent/SIMD implementation by scalar code.

Decision rule: Keep direct domain code and narrow the proven orchestration
route; record continue/revise/decline for trasic separately from proof SDK
acceptance.

Measurement: Record workload, compiler/verifier/backend revisions,
target/features, assumptions, and cost against the pre-registered acceptance
controls (spec/acceptance-controls.json). Correctness gates are categorical;
empirical thresholds are the registered controls.

Requirements: R6, R9. Tasks: 5.1.4, 5.3.4, 6.1.3, 6.2.4, 6.3.4.

Status: planned-not-run.

## B08. Evidence and proof-API compatibility remain maintainable

Hypothesis: Versioned models, executable bindings and scoped proof records
allow downstream proofs to survive legitimate internals changes and fail when
their assumptions change.

Success witness: An internal refactor preserves public proofs; precondition
strengthening, postcondition weakening, backend/profile changes and stale
specification bindings invalidate the affected evidence and cache entries.

Negative control: Import verification metadata from a different executable
revision, use focus/skip mode as release evidence, or label bounded Kani
evidence as unbounded. The evidence gate (ADR-0009) rejects these as
binding-stale, run-focused or outcome-skipped, and admits partial-bounds
evidence only at bounded.

Falsifier: Consumers depend on private IR layout, relevant source changes do
not invalidate evidence, or proof CI exceeds agreed limits without an explicit
scope decision.

Decision rule: Refine the public lemma surface, cache keys and verification
profiles; no compatibility shim is required for obsolete unreleased APIs, but
released proof contracts get deliberate versioning.

Measurement: Record workload, compiler/verifier/backend revisions,
target/features, assumptions, and cost against the pre-registered acceptance
controls (spec/acceptance-controls.json). Correctness gates are categorical;
empirical thresholds are the registered controls.

Requirements: R7, R8, R9, R11. Tasks: 1.1.4, 3.4.1, 4.3.3, 6.2.4.

Status: planned-not-run.

<!-- bets:end -->
