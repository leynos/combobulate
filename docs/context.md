# Combobulate context and ubiquitous language

Status: draft, revision 0.2. Date: 6 October 2026. Audience: implementers,
reviewers, extension authors, and adopting projects. Companions:
`terms-of-reference.md`, `technical-design.md`, `roadmap.md`,
`language-reference.md`, and `references.md`.

Decisions that control acceptance, with their authority, options, and status,
are recorded in the [decision register](decision-register.md).

## 1. Product context

Combobulate is a proposed Rust library for expressing computations over arrays
and collections as readable, reusable operations. It borrows rank application,
scalar extension, reductions, scans, products, stencils, and function-building
operators from array-language practice without targeting APL compatibility. The
project began with a Polars-backed array language and acquired a native
execution boundary when the trasic use case exposed the limits of treating all
collections as dataframe columns. Sources: C-01 through C-11 in
`references.md`. Revision 0.2 adds explicit proof-first delivery, public
verification contracts, staged costing, and a capability-based Polars 2
integration boundary.

The working thesis is: **an inspectable algebra of applying computations to
collections, with Polars integration and native domain kernels**. Polars is a
first-class execution route, not the definition of every logical value. Glam
supplies arithmetic within small geometric values; Combobulate coordinates
collections of those values. Trasic supplies geometric meaning, numerical
precautions, and rendering algorithms.

This is a greenfield design record. No implementation tree was available for
inspection. The pack does not imply that any API, benchmark, external adoption,
or release already exists.

## 2. Authority and document ownership

| Document                | Owns                                                                                    | Does not establish                                   |
| ----------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `terms-of-reference.md` | Problem, users, goals, exclusions, imposed constraints, and open questions.             | Architecture acceptance or implementation evidence.  |
| `context.md`            | Domain vocabulary, boundaries, and the meaning of recurring terms.                      | Delivery status or independent product requirements. |
| `technical-design.md`   | Proposed architecture, semantics, trade-offs, invariants, and verification obligations. | Benchmark results or release approval.               |
| `language-reference.md` | Initial public vocabulary, signatures, defaults, and scope classification.              | An existing or stable released API.                  |
| `roadmap.md`            | GIST hypotheses, workstreams, review-sized tasks, dependencies, and gates.              | Calendar promises or completed work.                 |
| `references.md`         | Evidence sources, inspected revisions, and limits of inspection.                        | Approval merely because a source is cited.           |
| `validation.md`         | Checks actually run on this document pack and their limitations.                        | Compilation or conformance of a future crate.        |

Explicit user constraints take precedence over generated design proposals.
Material contradictions require upstream reconciliation; repeating a proposal
in several documents does not approve it. The definitions below are canonical
within this draft. Durable decisions can later move to ADRs without creating
competing definitions.

## 3. Domain boundaries

| Boundary               | Inside Combobulate                                                                   | Outside Combobulate                                                          |
| ---------------------- | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| Array semantics        | Shapes, rank, agreement, ordering, validity, and operation contracts.                | Full APL syntax or compatibility.                                            |
| Execution              | Planning, capability matching, bounded batches, provenance, and result assembly.     | A general distributed scheduler or a new GPU compiler.                       |
| Relational integration | Explicit ordered table-to-array and array-to-table conversion.                       | Implicit joins or name-based alignment of array operands.                    |
| Small linear algebra   | Typed-cell adapters and explicit component views.                                    | Reimplementing glam's vector/matrix arithmetic.                              |
| Geometry               | Generic batch, mask, segment, gather, and reduction facilities.                      | Intersection mathematics, CSG tie policy, normal orientation, and materials. |
| Rendering              | Bounded collection transformations and explicit indexed accumulation.                | Selecting trasic's transport algorithm or requiring wavefront rendering.     |
| Extensibility          | Inspectable graph definitions, native kernels, contracts, and backend registrations. | Sandboxing arbitrary native Rust code.                                       |
| Effects                | Explicit resource access, guarded execution, and sink boundaries.                    | Treating every deferred expression as an IO monad.                           |

## 4. Canonical vocabulary

### 4.1. Values, descriptions, and execution

| Term              | Definition                                                                                             | Important distinction                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| Array             | Materialized homogeneous rectangular collection of scalar logical elements, including nullable values. | Not a Polars dataframe.                                              |
| Batch             | Materialized rectangular collection of typed logical elements, such as `DVec3` or `Ray<World>`.        | Its shape excludes the internal coordinates of an element.           |
| View              | Borrowed or shared access to existing values with a logical index mapping.                             | Borrowing does not promise contiguity.                               |
| Array expression  | Deferred graph producing an array; public shorthand `AExpr`.                                           | It contains no evaluated result merely by existing.                  |
| Batch expression  | Deferred graph producing a typed batch.                                                                | Coarse Rust typing does not prove arbitrary dynamic dimensions.      |
| Verb              | Reusable operation applied to data to produce a computation.                                           | A descriptor is not necessarily a Rust callable object.              |
| Unary / Binary    | Small public handles for one-input and two-input operations.                                           | They hide graph structure rather than expose nested generic types.   |
| Apply             | Construct an application node from an operation and arguments.                                         | Does not execute the array kernel.                                   |
| Prepare           | Validate known facts, select execution regions, and record runtime obligations.                        | Does not imply that data-dependent sizes are already known.          |
| Prepared plan     | Executable schedule plus schema, policy, resource, and binding requirements.                           | Cannot be reused against incompatible bindings without revalidation. |
| Execute / collect | Evaluate a prepared computation and produce data or an explicit sink result.                           | No hidden execution during graph construction.                       |
| Materialization   | Producing an actual buffer representation at an execution boundary.                                    | Distinct from merely creating another graph handle.                  |
| Native kernel     | Ordinary compiled Rust function over cells or batches behind a declared contract.                      | Opaque to graph algebra need not mean per-cell dynamic dispatch.     |
| Lowering          | Mapping logical operations to an eligible backend implementation.                                      | Cannot weaken logical or numerical semantics.                        |
| Physical region   | Connected work that shares a compatible execution and index-space contract.                            | One graph can contain several Polars and native regions.             |

### 4.2. Shape and logical identity

| Term               | Definition                                                             | Example or boundary                                    |
| ------------------ | ---------------------------------------------------------------------- | ------------------------------------------------------ |
| Shape              | Ordered nonnegative dimensions of a rectangular collection.            | Scalar `[]`; empty vector `[0]`; matrix `[r, c]`.      |
| Rank               | Number of visible collection axes.                                     | Not matrix rank from linear algebra.                   |
| Logical element    | Atomic value for collection operations.                                | A scalar in an Array; a whole normal in a typed Batch. |
| Rank cell          | Trailing subarray of a selected number of visible axes.                | In `[b, r, c]`, a rank-1 cell has shape `[c]`.         |
| Frame              | Leading dimensions indexing the cells to which an operation applies.   | The rank-1 frame of `[b, r, c]` is `[b, r]`.           |
| Cell schema        | Logical element type, fields, component interpretation, and validity.  | Not just scalar dtype and component count.             |
| Component view     | Explicit exposure of a typed element's coordinates as collection axes. | `Batch<DVec3>` becomes numeric shape `batch ++ [3]`.   |
| Agreement          | Rules that determine whether operands can pair.                        | Default: same shape or scalar extension.               |
| Scalar extension   | Reuse of a rank-0 operand at every position of another operand.        | Does not imply arbitrary singleton broadcasting.       |
| Frame extension    | Reuse of an operand with an empty frame across another frame.          | Distinct from extension of a scalar logical element.   |
| Broadcasting       | Explicit expansion across compatible singleton axes.                   | May increase cardinality drastically.                  |
| Axis               | A position, or optional declared name, within visible shape.           | Axis names do not perform data alignment.              |
| Index space        | Logical positions and their order for an operation.                    | Must survive chunking and physical-region changes.     |
| Batch domain       | In-process provenance of positions and their correspondence.           | Equal lengths do not establish correspondence.         |
| Alignment          | Known correspondence between paired positions.                         | `zip_aligned` checks it; it does not execute a join.   |
| Selection map      | Indices connecting selected positions to a source domain.              | Enables shared compaction and restoration.             |
| Canonical order    | Row-major traversal of visible axes; the last axis varies fastest.     | Not a claim about glam matrix memory layout.           |
| Symbolic dimension | A size not yet known but constrained by graph facts.                   | Compression yields `M <= N`.                           |

### 4.3. Operators and notation

The taxonomy is Combobulate's documentation vocabulary, not a claim about the
precise grammatical categories of APL, J, or Rust.

| Term                 | Definition                                                                             | Examples                                                        |
| -------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Modifier             | Derives an operation from one operation operand, often with static configuration.      | `each(f)`, `reduce(f)`, `rank(1, f)`.                           |
| Conjunction          | Combines two or more operation operands into another operation.                        | `compose(f, g)`, `fork(f, g, h)`, `inner(f, g)`.                |
| Section / binding    | Fixes a data argument of a multiargument operation.                                    | `sub.rhs(10)` means `x - 10`.                                   |
| Policy modifier      | Changes an explicit part of a derived operation's contract.                            | `.axis(0)`, `.keep_dims()`, `.skip_nulls()`.                    |
| Pipeline             | Left-to-right application of stages.                                                   | `comb! { x \|> f \|> g }` means `g(f(x))`.                      |
| Graph-building macro | Syntax translated into normal builders for an inspectable graph.                       | `comb!` and `verb!`.                                            |
| Host expression      | Rust code evaluated at plan construction, not traced as array algebra.                 | `host { configuration.threshold() }`.                           |
| Footprint            | Ordered selected offsets around a stencil anchor.                                      | A 3-by-3 footprint excluding its centre contains eight offsets. |
| Reducer              | Input-to-state accumulation plus finalization, optionally with a state merge contract. | Weighted film accumulation.                                     |
| Reduction            | Combining an axis with a binary operation under specified association.                 | Generic `reduce` is right-associated.                           |
| Scan                 | Reduction of each nonempty prefix under the generic reduction contract.                | Distinct from linear left accumulation.                         |
| Left scan            | Successive left-associated accumulation.                                               | `scan_left(f)`.                                                 |
| Inner product        | Contraction of the left final axis against the right first axis.                       | `L ++ [k]` with `[k] ++ R` yields `L ++ R`.                     |
| Batched matmul       | Matrix multiplication on final matrix axes with separately checked batch agreement.    | Not an alias for generalized `inner`.                           |

### 4.4. Validity, effects, and cost

| Term                  | Definition                                                                                          | What it must not conceal                                                        |
| --------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Null                  | Missing logical data according to a validity mask.                                                  | Not a floating-point NaN or an inactive ray.                                    |
| NaN                   | Floating-point value governed by a numerical policy.                                                | Does not count as missing data automatically.                                   |
| Active mask           | Identifies positions allowed to execute a guarded kernel.                                           | Does not merely select between precomputed values.                              |
| Miss                  | Ordinary negative result of a geometry query.                                                       | Not a failed computation.                                                       |
| Lane status           | Per-position domain result or numerical status.                                                     | Distinct from a whole-plan failure.                                             |
| Segmented collection  | Flat logical values plus offsets describing variable-length segments.                               | Cannot silently pose as a dense rectangular array.                              |
| Halo                  | Neighbourhood data required around a tile or partition.                                             | Chunk boundaries are not array boundaries.                                      |
| Cardinality           | Number of output positions relative to inputs.                                                      | Same cardinality does not imply chunk independence.                             |
| Pure operation        | Has no observable external effects beyond its values and declared failures.                         | Purity alone does not make speculative evaluation safe.                         |
| Guard                 | Execution condition that excludes inactive kernel invocations.                                      | Selection is not a guard.                                                       |
| Resource binding      | Explicit dependency on scene, sampler, texture, or other execution resource.                        | A closure capture is not automatically immutable or reproducible.               |
| Reassociation         | Permission to change grouping under a specified numerical contract.                                 | Does not imply reordering or permission to change checked failures.             |
| Reproducibility scope | Named conditions under which an execution result repeats.                                           | Not a blanket cross-platform bitwise promise.                                   |
| Budget                | Configured limits on named output, tracked storage, work, concurrency and permitted I/O quantities. | A scoped admission guarantee is not a process RSS ceiling.                      |
| Cost classification   | Exact quantity, conservative bounds, estimate, or unknown.                                          | An upper bound above a limit does not prove actual excess; unknown is not zero. |
| Static descriptor     | Immutable operation/schema/policy facts usable in constant evaluation.                              | An inspectable runtime graph is not automatically static.                       |
| Cost certificate      | Checked scoped relationship between an admitted schedule, resource model, bindings and policies.    | Not a wall-time forecast or a proof of arbitrary backend internals.             |
| Runtime obligation    | A check tied to the event that supplies missing facts and to consumers it guards.                   | It must run before dependent allocation or access.                              |
| Spill policy          | Explicit temporary-disk permission, quota, cleanup and isolation scope.                             | A process-global backend setting is not independent per-query control.          |
| Backend capability    | Evidence-backed support in an exact Rust/profile/engine configuration.                              | A Python release number or documented opportunity is insufficient.              |
| Evidence              | Observed result with revision, method, and limits.                                                  | A generated plan, an approval, and a passing unrelated test are not evidence.   |

### 4.5. Verification and consumer contracts

| Term                       | Definition                                                                                                                      | Important distinction                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Proof-first                | State the contract, proof scope and witnesses before implementation, then discharge applicable evidence in that delivery slice. | Not a demand to prove a nonexistent body or a late hardening phase.                      |
| Logical view               | Ghost/specification model of contents, validity, shape and origin, independent of storage.                                      | Distinct from an executable borrowed view or a copy.                                     |
| Checked view               | Runtime-validated borrowed access with public invariants and observers.                                                         | Safe unverified callers still receive validation.                                        |
| Witness                    | Reusable fact bound to a source extent/domain, state generation and policy.                                                     | Not an unscoped token authorizing unrelated inputs.                                      |
| Successful-result relation | The required meaning of an Ok result.                                                                                           | Alone it permits an always-Err implementation.                                           |
| Success conditions         | Input/resource/termination conditions under which success follows.                                                              | Must have a reachable witness; cancellation and external failure limits remain explicit. |
| Frame condition            | The state an operation leaves unchanged across a given outcome.                                                                 | Atomic output and partial commit have different contracts.                               |
| Callable contract          | Executable binding plus pre/postconditions, captures, effects and termination assumptions.                                      | One permitted desired output is not a universal postcondition guarantee.                 |
| Accumulator history        | Logical inputs represented by a reducer state.                                                                                  | A merge method does not prove an algebraic merge law.                                    |
| Proof evidence             | Tool result bound to actual code/specification, scope, target, assumptions and witnesses.                                       | Tests, bounded checks, proofs and trust have different meanings.                         |
| Trusted basis              | Unproved compiler/tool/backend or callable assumptions on which a claim depends.                                                | Naming or hashing an assumption does not discharge it.                                   |
| Refinement                 | An implementation or transformation preserves its declared logical meaning and observable outcomes.                             | A scalar reference implementation is not evidence for another backend by itself.         |
| Public proof API           | Versioned collection/graph models, contracts, lemmas and evidence boundaries available to consumers.                            | Private IR details remain private.                                                       |
| Testable bet               | Hypothesis with success witness, negative control, falsifier and continue/revise/decline rule.                                  | A planned experiment is not completed implementation evidence.                           |

## 5. Reference scenarios

### 5.1. Ordinary numeric work

A developer centres each row, transposes the result, and accumulates each new
row. The developer must see the rank transition and distinguish exact prefix
reductions from left accumulation. A shape error names the failing stage, input
shape, and expected relationship. Backend types stay out of the normal
diagnostic unless the developer asks for backend detail.

### 5.2. Empty and data-dependent inputs

`[0, 3] |> rows(mean)` has no cells and produces `[0]` without calling a kernel.
`[3, 0] |> rows(mean)` has three empty cells and reaches the empty-mean
policy. A compression can yield an unknown count until execution; downstream
constraints remain explicit obligations rather than guesses based on a first
value.

### 5.3. Geometry packets

A domain function intersects one ray with one primitive. A native batch adapter
applies that function to a bounded packet while preserving ray identities,
misses, active masks, and numerical statuses. The scalar function remains
available to scene elaboration without a Polars dependency. This scenario tests
orchestration, not whether array syntax can shorten a quadratic formula.

### 5.4. Boundary events and film accumulation

A ray can generate a variable number of CSG boundary events. Generic segmented
operations organize events; trasic defines boundary coincidence, orientation,
and material semantics. A render sample can contribute to several pixels;
indexed accumulation must define weighting, collision order, and failure
atomicity. Neither case requires Combobulate to choose a transport algorithm.

## 6. Decisions inherited, clarified, or superseded

| Earlier suggestion                                       | Consolidated position                                                                                                           | Reason                                                                                               |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `Array` contains the entire deferred computation.        | Materialized values, expression handles, and prepared plans are distinct.                                                       | Ownership and execution become observable.                                                           |
| Rank-2 arrays are always dataframe columns.              | Logical schema and physical layout are independent.                                                                             | Typed cells, differing cardinalities, and native kernels need other layouts.                         |
| `.pipe(f)` directly accepts every descriptor.            | `.then(f)` or `.pipe(f.as_fn())` is the ordinary API; `comb!` keeps concise stages.                                             | Avoid unstable custom callable objects.                                                              |
| A scalar transpose should fail.                          | Default transpose reverses visible axes; rank-0 and rank-1 values are unchanged.                                                | The earlier diagnostic example was not a semantic requirement.                                       |
| A generic scan is always a cumulative backend primitive. | Exact prefix reductions and left scans are separate.                                                                            | Nonassociative operations and numerical failures distinguish them.                                   |
| Property-tested laws are verified universally.           | Tests provide bounded evidence; proofs need stated assumptions and correspondence.                                              | Avoid turning sampled agreement into a theorem.                                                      |
| `sqrt(x*x + y*y)` is a universal `hypot` lowering.       | A lowering must preserve the operation's numerical contract.                                                                    | Intermediate overflow can change the result.                                                         |
| A raw callback is inherently a slow fallback.            | Static native batch kernels are first-class.                                                                                    | Opaqueness to graph rewriting says nothing by itself about loop efficiency.                          |
| `a!` replaces the frontend.                              | `comb!` remains the frontend; `a!` is absent.                                                                                   | Explicit user constraint.                                                                            |
| `&&` and `\|\|` become elementwise logic.                | Use `&`, `\|`, and `!`; reject array short-circuit notation.                                                                    | Keep guarded execution distinguishable.                                                              |
| Every extension needs an early published crate.          | Use facade, macro and internal semantic-kernel crates; add proof packaging only where verified-dependency integration needs it. | Shared executable const/runtime/proof semantics need dependency isolation, not many public products. |
| Cost admission happens only in prepare.                  | Compile-time, preparation and runtime share checked cost rules as facts become available.                                       | Static visibility varies; unresolved data-dependent checks remain explicit.                          |
| Internal Kani harnesses suffice for consumers.           | Export public models/contracts and require external Kani and Verus fixtures.                                                    | Consumer proofs must compose without private executor knowledge.                                     |
| A passing scalar proof certifies the selected backend.   | Each execution route needs refinement evidence or a reported trusted boundary.                                                  | A proof-only substitute executor cannot establish production behaviour.                              |
| Polars 2 can be acquired by choosing Cargo version 2.    | Pin an actual Rust revision and probe capabilities independently of Python numbering.                                           | Documentation opportunity, API availability and tested eligibility are different facts.              |

These are proposed consolidations except where the supplied user constraint
establishes otherwise. Formal acceptance remains open.

## 7. Integration invariants and open boundaries

Geometry types keep point, direction, normal, colour, and coordinate-space
meaning outside the generic array engine. The engine does not assume that three
components imply interchangeable semantics. Element component views must define
order and validity explicitly; storage adapters must check layout, alignment,
offsets, chunking, and lifetimes before borrowing.

Public proof contracts participate in compatibility review: a stronger
precondition or weaker postcondition can break downstream proofs without a Rust
signature change. Executable/specification and backend-profile changes
invalidate affected evidence.

This unreleased, pre-1.0 library uses no blanket source-API compatibility
machinery ([D06](decision-register.md#d06)). Ordinary domain wrappers and
backend adapters have semantic jobs; they do not preserve obsolete interfaces.
The draft supplementary contract guidance and its status appear in
`references.md` §D-CONTRACT.

The core release boundary is accepted ([D03](decision-register.md#d03)).
Unresolved choices include a dependency/toolchain baseline, quantitative
performance and compile-cost gates, and actual trasic adoption access. The ToR
owns those questions. The design and roadmap refer to them rather than
manufacture answers.
