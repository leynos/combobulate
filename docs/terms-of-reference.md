# Combobulate terms of reference

Status: draft, revision 0.2. Date: 6 October 2026. Audience: project sponsor,
implementers, reviewers, and prospective adopters. Companions: `context.md`,
`technical-design.md`, `roadmap.md`, `language-reference.md`, and
`references.md`.

Decisions that control acceptance, with their authority, options, and status,
are recorded in the [decision register](decision-register.md).

## 1. Background and motivation

Combobulate addresses a readability and reuse problem in Rust collection
computations: the intended transformation can disappear among indexing, shape
bookkeeping, closures, conversions, and backend-specific machinery. The sponsor
requested APL-like compositional expressiveness without specialist glyph
notation, then challenged the proposal against understandable errors,
third-party extension, and geometry/rendering workloads. These requests are
established input, not measured evidence of a market-wide deficiency [C-01–C-07,
`references.md`].

The timing comes from the sponsor's current array-language exploration and
proposed trasic work. No external deadline, customer contract, or quantified
market demand was supplied. The first obligation is to determine whether the
abstraction improves actual code without hiding numerical meaning or cost.

The revision 0.2 brief adds an explicit assurance requirement: develop
applicable contracts and machine-checked evidence before accepting
implementation, support Kani and Verus users who verify their own programmes,
analyse eligible costs at compile time, and prepare the integration boundary
for Polars 2 [C-08-C-11]. These are user-imposed requirements. Their
implementation details and bounded proof scope belong to the technical design.

## 2. Domain

The domain is collection-oriented scientific and systems programming:
rectangular arrays, repeated application to subarrays, neighbourhood
computations, and typed batches of domain values. `context.md` §§3–4 defines
the vocabulary and distinguishes arrays, tables, typed cells, and segmented
collections.

Users need to reason about axes, association, correspondence, missing values,
and variable output sizes. They also need to reuse existing numerical and
domain functions. A shorter expression does not constitute an improvement when
it hides a domain precondition, numerical safeguard, allocation, or execution
boundary.

No regulated-data or legal-compliance requirement was supplied. Inputs may
still be malformed or untrusted; invalid dimensions and expansion requests must
not undermine memory safety or bypass configured resource controls.

## 3. Existing alternatives and proposed gap

| Alternative                                   | Existing role                                                                       | Question Combobulate must answer                                                               |
| --------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Ordinary Rust functions, loops, and iterators | Direct control over algorithms and data traversal.                                  | Does the new abstraction remove coordination work rather than merely rename loops?             |
| ndarray                                       | Multidimensional owned arrays and views [E-NDARRAY].                                | Does a reusable inspectable operation algebra add enough value to justify another layer?       |
| Polars                                        | Column-oriented expressions and tabular work [E-POLARS-MAP, E-POLARS-ARRAY].        | Can positional array meaning remain clear across the relational boundary?                      |
| glam                                          | Concrete small vector/matrix arithmetic [E-GLAM].                                   | Can collection composition preserve semantic cell types without replacing existing arithmetic? |
| faer                                          | Matrix operations and decompositions [E-FAER].                                      | Can specialist mathematics remain delegated rather than recreated?                             |
| Dr.Jit                                        | Traced, compiled numerical computation with rendering-oriented prior art [E-DRJIT]. | Can a smaller Rust-native scope solve the immediate job without building another JIT?          |

The proposed gap is the combination of readable operation composition, explicit
collection semantics, understandable diagnostics, and open native extension.
The project must test that combination against the alternatives. It does not
claim that existing libraries cannot express the same mathematics.

## 4. Users, concerns, and decision rights

| Role                                             | Context and concern                                                                                             | Required evidence                                                                                       | Decision right                                                                                                                  |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Rust developer, primary user                     | Writes array or batch transformations and needs to explain them to another engineer.                            | Paired examples, shape/failure predictions, and readable diagnostics.                                   | Supplies usability evidence; no automatic release authority.                                                                    |
| Domain/extension author, primary user            | Owns numerical or geometry kernels and needs generic application without a core fork.                           | An external extension crate works through documented interfaces.                                        | Owns the domain algorithm and its declared contract.                                                                            |
| Reviewer or maintenance engineer, secondary user | Must understand provenance, effects, resource use, and failure modes.                                           | Explain output, source-linked failures, and traceable contracts.                                        | Reviews evidence; does not approve product scope by implication.                                                                |
| Verification-oriented consumer, primary user     | Must establish application properties without depending on private collection internals or an assumed executor. | Public-only downstream proof fixtures, successful/failing witnesses, and explicit residual assumptions. | Owns application/kernel contracts; does not certify an upstream backend by implication.                                         |
| Project sponsor, Payton                          | Chooses scope and assesses whether the work earns its ongoing cost.                                             | Falsifiable milestones and measured outcomes.                                                           | Final technical and release authority, as sponsor and technical owner, GitHub login `leynos` ([D01](decision-register.md#d01)). |

The initial audience has Rust experience. A general-purpose educational
interpreter, spreadsheet user interface, or automatic renderer conversion is
not a target user journey.

## 5. Jobs to be done

When a Rust developer expresses a repeated calculation over a structured
collection, they want the code to reveal the operation and its shape changes,
so another engineer can review or modify it without reconstructing indexing
logic from loops and temporary buffers.

When a domain author already has a trustworthy scalar or batch function, they
want to apply it across compatible collections while preserving identity,
validity, and numerical meaning, so they can reuse that function rather than
rewrite the algorithm for each storage backend.

When a reviewer investigates a failed or unexpectedly expensive computation,
they want the failing stage, relevant input contract, and actual execution
boundary, so they can correct the source without reverse-engineering generated
Rust types or backend internals.

When an application author verifies collection-oriented code, they want public
models and contracts that compose with their domain claims, so a change in
physical representation does not require re-proving library internals. They
also need to know exactly which executable route, scope and assumptions the
evidence covers.

When a caller supplies fixed or bounded inputs, they want early resource
admission with truthful uncertainty, so compilation can reject certain
excessive requests without preventing legitimate data-dependent use. Backend
evolution must not introduce silent reordering or disk effects behind those
guarantees.

## 6. Scope

### 6.1. Goals

| ID  | Goal                                                                                                                                                       | Origin            |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| G1  | Make representative array transformations understandable from their public expressions and diagnostics.                                                    | C-01, C-02, C-05. |
| G2  | Give shape, ordering, validity, numerical behaviour, and failures a predictable meaning across supported execution routes.                                 | C-02, C-05, C-06. |
| G3  | Let domain authors add operations and apply them generically without changing the core library.                                                            | C-03, C-04.       |
| G4  | Expose and control execution cost, especially copying, expansion, and batch boundaries.                                                                    | C-04–C-06.        |
| G5  | Establish whether typed geometry and rendering collections benefit without displacing their mathematical kernels.                                          | C-04.             |
| G6  | Keep the implementation and maintenance burden proportionate to the demonstrated benefit.                                                                  | C-03, C-06.       |
| G7  | Let consumers compose justified application proofs over public collection contracts, and require proof-first delivery of applicable implementation claims. | C-08, C-10, C-11. |
| G8  | Admit resource demands as early as the available facts permit and benefit from backend evolution without weakening semantic or effect guarantees.          | C-08, C-09, C-11. |

These are proposed project goals reconstructed from the supplied discussion.
The explicit notation/platform constraints below have stronger provenance than
the unmeasured outcome hypotheses.

### 6.2. Non-goals

Full APL compatibility, a new programming-language runtime, and implicit
name-based dataframe alignment are out of scope. Users retain ordinary Rust and
relational tools for those different jobs.

The initial product will not replace small-vector mathematics or specialist
linear-algebra algorithms, require a whole renderer rewrite, or mandate
wavefront rendering. It will not add GPU compilation, automatic
differentiation, distributed execution, or arbitrary sparse/ragged nesting to
justify its first release.

Source-API compatibility layers for obsolete unreleased interfaces are not a
delivery goal. Source changes may update all affected pre-1.0 callers together.
Persisted data or wire contracts, should they later exist, require a separate
assessment. Native extensions are trusted code, not sandboxed plugins.

Universal verification of arbitrary user callbacks, every floating numerical
algorithm, Polars internals, and all concurrent or SIMD routes is not an
initial claim. These boundaries require explicit evidence or trust
dispositions. They do not exempt owned semantic, admission, or public proof
contracts from the proof-first requirement. Ordinary consumers need not install
verification tools.

## 7. Success criteria

No benchmark or reader-study baseline exists in this evidence set. The
following criteria define proposed evidence, not results already achieved.
Quantitative performance, compile-cost, proof-cost, and CI thresholds are
pre-registered as controls `AC-01` to `AC-07` in `spec/acceptance-controls.json`
([D11](decision-register.md#d11), [D12](decision-register.md#d12), [ADR-0008](adrs/adr-0008-acceptance-control-pre-registration.md)).
They are registered, not met.

| ID  | Observable criterion                                                                                                                          | Baseline and target                                                                                                                                | Method and accountability                                                                        |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| S1  | Public examples express row centring, generalized contraction, neighbourhood counting, and typed batch application without private shortcuts. | Baseline: ordinary Rust versions to be captured. Target: every example uses documented public primitives.                                          | Executable examples plus independent reviewer walkthrough; maintainer to designate reviewers.    |
| S2  | Supported routes agree on values, shapes, validity, and specified failures.                                                                   | Baseline: none. Target: no unexplained divergence within the published corpus and tested bounds.                                                   | Independent reference evaluation, seeded faults, and backend conformance evidence.               |
| S3  | Ordinary errors identify the source operation and the violated domain contract.                                                               | Baseline: none. Target: curated misuse corpus produces first-screen array/domain diagnostics rather than backend plumbing.                         | Diagnostic snapshots and source-location checks; no claim over all arbitrary Rust errors.        |
| S4  | An independently packaged extension runs and reports a valid contract without a core change.                                                  | Baseline: none. Target: one numeric and one typed-domain example.                                                                                  | Consumer fixture using only public extension interfaces.                                         |
| S5  | Cost reports distinguish planning, execution, conversion, and temporary storage.                                                              | Baseline: control implementations to be measured. Target: observable accounting and rejection of known over-budget expansion.                      | Measurements on named workloads and selected physical routes.                                    |
| S6  | Trasic adoption has an evidence-backed continue, revise, or decline decision.                                                                 | Baseline: source access not established. Target: packet, segmented-event, and tile experiments report benefit and regressions separately.          | Domain review, adapter comparisons, and independent geometry/reference evidence where available. |
| S7  | The supported package/feature surface builds without unnecessary backend coupling.                                                            | Baseline: no implementation. Target: native-only, proof-capable and Polars-enabled profiles within pre-registered build/proof budgets.             | Feature-matrix checks and build-cost records.                                                    |
| S8  | Separate Kani and Verus consumers establish useful success/error properties through public APIs and actual comb! programmes.                  | Baseline: none. Target: declared Core and Integration fixtures need no private imports, assumed executor, or proof-only semantic substitute.       | Positive/negative consumer suites and reported trust/implementation bindings.                    |
| S9  | Eligible cost checks agree across compilation, preparation and runtime and distinguish bounds from estimates/unknowns.                        | Baseline: none. Target: exact over-budget cases fail early, bounded-domain uncertainty remains explicit, and dynamic inputs retain safe admission. | Compile-pass/fail and runtime witnesses with target-width and malformed-certificate controls.    |
| S10 | Every accepted semantic slice has its applicable proof-first evidence and limitations recorded.                                               | Baseline: no implementation proofs. Target: no missing, vacuous, skipped or inconclusive result counts as a required proof.                        | Per-task obligation ledger, executable binding, non-vacuity and exception review.                |
| S11 | The selected Polars revision supplies tested capabilities without hidden order or I/O changes.                                                | Baseline: upstream documentation only. Target: explicit capability/engine/control-scope evidence and dispositions for unsupported future features. | Forced-route conformance, spill/order failures and enabled/disabled opportunity measurements.    |

User-facing success primarily concerns comprehension and correct task
completion. Operational success concerns bounded execution and maintainable
integration. Strategic success means the sponsor judges the resulting reusable
capability worth retaining; adoption counts or revenue targets were not given.

## 8. Constraints, assumptions, and dependencies

### 8.1. Constraints

| ID  | Constraint                                                                                                                   | Evidence and status                                                                                                    |
| --- | ---------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| C1  | The implementation language is Rust and Polars integration is a first-class requirement.                                     | [KNOWN] Explicit request C-01. Backend-independent semantics are a proposed refinement, not permission to omit Polars. |
| C2  | Retain `comb! { input \|> stage \|> stage }` ergonomics and readable names. Do not replace it with `a!` or glyph notation.   | [KNOWN] Explicit request C-05.                                                                                         |
| C3  | Use the df12 documentation methods and deliver all five requested documents.                                                 | [KNOWN] Current request C-07.                                                                                          |
| C4  | Preserve ordinary domain kernels and make deep trasic adoption contingent on evidence.                                       | Proposed response to C-04, not evidence that trasic has adopted it.                                                    |
| C5  | Do not add obsolete-interface preservation for private, test-only, pre-1.0, or unreleased source APIs.                       | Supplementary df12 guidance D-CONTRACT; retain the guidance's draft status in provenance.                              |
| C6  | Do not invent owners, accepted thresholds, release dates, or deployment claims.                                              | Evidence discipline from D-TOR and D-CONTRACT.                                                                         |
| C7  | Require proof-first development with Verus or Kani as appropriate, and public support for consumers using both tools.        | [KNOWN] Explicit revision request C-11; details in C-08/C-10.                                                          |
| C8  | Incorporate compile-time costing and make the design forward-looking for Polars 2 without changing comb! ergonomics.         | [KNOWN] Explicit C-11 plus C-05 and the C-08/C-09 design discussion.                                                   |
| C9  | Express these changes as falsifiable GIST bets with executable acceptance criteria, not merely aspirational future features. | [KNOWN] Explicit C-11.                                                                                                 |

Stable-Rust callable support, coarse public types, backend selection, and
storage representations are design choices, not problem-space facts. The
technical design owns them.

### 8.2. Assumptions

| ID  | Assumption                                                                      | Consequence if false                                                                               | Verification and expiry                                                                 |
| --- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| A1  | Operation composition improves comprehension for the selected Rust audience.    | Keep ordinary functions/loops where the abstraction obscures intent; reconsider the product scope. | Paired reader tasks; expires on a major syntax or audience change.                      |
| A2  | Enough useful operations can use Polars without weakening semantics.            | Narrow the lowering surface or reconsider the integration boundary openly.                         | First end-to-end Polars slice; expires on dependency/API changes.                       |
| A3  | Native typed batches can reuse domain kernels with acceptable overhead.         | Restrict adoption to coarse batch boundaries or decline the client integration.                    | Packet and tile measurements; expires on representation/kernel changes.                 |
| A4  | The initial feature surface fits the sponsor's maintenance and resource budget. | Reduce scope before release rather than silently increase the budget.                              | Compile/runtime/proof-cost accounting; expires on new backend or major dtype expansion. |
| A5  | Trasic remains a suitable demanding client.                                     | Use an independent geometric fixture; do not block generic array delivery.                         | Obtain a current source/design revision before adoption work.                           |

Additional assumptions now require early tests. A dependency-light executable
subset must support the selected ordinary/const/Kani/Verus profiles (B01).
Public models must let downstream proofs avoid implementation internals (B02).
The static analyser must deliver useful admission within the accepted build
cost (B03/B04). Polars opportunities must have compatible actual Rust
interfaces and measurable value (B05/B06). Falsification requires an explicit
representation, capability or certified-scope decision, not weakened claims.

### 8.3. Dependencies

| Dependency                           | Provider and consumer                                           | Exact condition                                                             | What it gates                                                      |
| ------------------------------------ | --------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Dependency/toolchain baseline        | Rust and selected upstream crates to Combobulate maintainers.   | Document a compatible version/feature matrix and verify it.                 | Implementation and release, not this draft.                        |
| Domain kernels and comparison inputs | Trasic or an independent fixture to the typed-batch experiment. | Obtain inspectable interfaces and suitable reference cases.                 | Real client adoption; generic contracts can proceed independently. |
| Quantitative budgets                 | Sponsor/design authority to experiment owners.                  | Record thresholds, workloads, and measurement conditions before acceptance. | Performance-dependent decisions, not semantic development.         |
| Repository access and destination    | Repository owner to publisher.                                  | Resolve an accessible target and its contribution instructions.             | GitHub publication only.                                           |

## 9. Open questions

| ID  | Question                                                                                                              | Why it matters and resolution condition                                                                           | Authority                                                                                                                 |
| --- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Q1  | Which maintainer accepts architecture, scope changes, and release readiness?                                          | Record decision rights before implementation approval; advice is not approval.                                    | Accepted: sponsor and technical owner `leynos` ([D01](decision-register.md#d01)).                                         |
| Q2  | Which runtime, memory, compile-cost, proof-runtime/solver-memory, and CI thresholds govern the experiments?           | Record control workloads and thresholds before measuring candidate acceptance.                                    | Accepted: hosted runner class ([D11](decision-register.md#d11)); calibrated thresholds ([D12](decision-register.md#d12)). |
| Q3  | Which Rust/MSRV and exact dependency feature matrix form the initial baseline?                                        | Resolve from current compatible releases and execute the proposed build matrix.                                   | Technical owner.                                                                                                          |
| Q4  | Is the proposed core/integration split the intended release boundary?                                                 | Accept or amend the scope matrix in `technical-design.md` §2.                                                     | Accepted: scope split unchanged ([D03](decision-register.md#d03)).                                                        |
| Q5  | Which current trasic source revision and geometry/reference contracts should adoption target?                         | Inspect that revision before claiming integration or performance benefit.                                         | Trasic maintainer, not yet identified here.                                                                               |
| Q6  | Where should this pack be published, and under which repository contribution rules?                                   | Resolve an accessible repository; no destination was established in this inspection.                              | Repository owner.                                                                                                         |
| Q7  | What package licence and external publication policy apply?                                                           | Record before publishing code or promising distribution terms.                                                    | Accepted: ISC, unpublished until task 4.3.3 ([D04](decision-register.md#d04), [D05](decision-register.md#d05)).           |
| Q8  | Who accepts scoped trusted-boundary exceptions and released proof-API changes?                                        | Assign authority and expiry/revisit policy; an exception cannot count as proof or waive ordinary safe-API checks. | Accepted: `leynos` ([D01](decision-register.md#d01)); exception policy ([D02](decision-register.md#d02)).                 |
| Q9  | Which exact verification profiles, theorem scope and optional Polars capabilities are supported at each release gate? | Resolve through B01/B02/B05/B06 and record unsupported targets; do not infer Rust features from Python numbering. | Technical and assurance owners, not yet designated.                                                                       |

## 10. Handoff

The material is sufficient for design review and bounded implementation
planning. It does not itself approve a release or set budgets. The
[decision register](decision-register.md) records the answers to the questions
above as they are accepted; Q1, Q4, Q7, and Q8 are answered.
`technical-design.md` maps goals to requirements and verification obligations;
`roadmap.md` sequences those obligations as falsifiable workstreams.
`context.md` owns domain terminology.

The register's
[candidate ADR subjects](decision-register.md#candidate-adr-subjects) record
the disposition of each potential ADR subject (D07): the semantic and numerical
contract, macro staging and the stable-Rust application interface, and the
initial release scope are each assigned an ADR (ADR-0006, ADR-0007, and
ADR-0003); the backend and cell boundary is deferred to task 1.2.1.

Implementation that contradicts an agreed requirement must surface the conflict
and reconcile the upstream documents before claiming completion. An unmeasured
benefit remains a hypothesis even after code merges.
