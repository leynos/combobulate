# Combobulate technical design

Status: proposed design, revision 0.2. Date: 6 October 2026. Audience:
implementers, reviewers, backend and domain-extension authors. Companions:
`terms-of-reference.md`, `context.md`, `language-reference.md`, `roadmap.md`,
`references.md`, and `validation.md`.

Decisions that control acceptance, with their authority, options, and status,
are recorded in the [decision register](decision-register.md).

All API examples are proposed, uncompiled sketches. Requirement identifiers
below express this draft's design response, not independent approval.

## 1. Conformance basis and baseline

The explicit brief requires a Rust array language with Polars integration,
readable APL-inspired composition, the existing `comb!` pipeline ergonomics,
and the five requested documents. The supplied discussion adds proposed
contracts for understandable errors, extensibility, typed cells, numerical
semantics, and selective trasic use. Sources C-01 through C-11 in
`references.md` record that distinction. C-11 explicitly requires proof-first
delivery, downstream Kani and Verus verifiability, compile-time costing, and a
Polars 2-aware design. The implementation and public API remain proposals, not
completed capabilities.

No Combobulate implementation, package release, or benchmark forms the supplied
baseline. During the original 5 October inspection, GitHub returned
inaccessible/not-found results for the presumed Combobulate and trasic
repository names. This revision updates the supplied document pack rather than
a source tree. This is a greenfield design baseline, not an audit of either
project's source. No legacy migration programme follows from that absence. The
supplied trasic architecture is an integration scenario whose actual revision
and public contracts remain an adoption prerequisite.

The current documentation skills guide structure and editing. Supplementary
architecture-contract guidance comes from D-CONTRACT, recorded as an unmerged
draft at the original 5 October inspection. That guidance informs evidence
discipline but does not acquire approval by appearing here. No ExecPlan has
been produced or inspected.

`context.md` owns terminology. `language-reference.md` and
`../spec/vocabulary.json` own canonical initial names. This document owns the
semantic and architectural rules to which those names refer. A conflict with
explicit user intent requires revision; neither a generated schema nor an
optimized implementation may redefine the user's requirement silently.

## 2. Requirements, release scopes, and outcomes

The ToR goals map to the following small requirement set. Verification IDs
refer to §14. The roadmap is the execution sequence, not evidence of discharge.

| ID  | Design requirement                                                                                                                                                              | ToR goals  | Response       | Verification           |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------------- | ---------------------- |
| R1  | Preserve readable `comb!` composition with optional ordinary Rust application and first-screen domain diagnostics.                                                              | G1         | §§7, 13        | V1, V10                |
| R2  | Define shapes, rank, agreement, order, emptiness, validity, numeric behaviour, and failure preservation independently of a backend.                                             | G2         | §§4-6, 8       | V2-V8                  |
| R3  | Admit graph-defined and native third-party operations without modifying the core or exposing its internal generic graph types.                                                  | G3         | §§7, 9         | V4, V7, V11            |
| R4  | Make cardinality, copies, work estimates, execution boundaries, and resource limits observable and enforceable within stated bounds.                                            | G4, G6     | §§8, 10, 12-13 | V8-V10, V13            |
| R5  | Retain a first-class Polars route while keeping domain kernels and typed native execution independent of mandatory dataframe representation.                                    | G2, G3, G5 | §§3, 10-11     | V5, V7, V11-V12        |
| R6  | Preserve typed-cell meaning, correspondence, genuine masking, segment ownership, and explicit accumulation effects in demanding-client experiments.                             | G2, G5     | §§4, 9, 11     | V6-V7, V11-V12         |
| R7  | Limit packaging, compatibility machinery, and verification cost to evidence-backed needs.                                                                                       | G6         | §§3, 14-17     | V13, V20, scope review |
| R8  | Require proof-first contracts, tool selection, non-vacuous witnesses and scoped Verus/Kani evidence in the implementing slice; expose residual trust honestly.                  | G2, G6, G7 | §§14, 17       | V14, V17, V20          |
| R9  | Let downstream consumers compose proofs over public collection models, checked views, graph meanings, callable/reducer contracts and production execution.                      | G3, G7     | §§4, 7-9, 17   | V15, V19-V20           |
| R10 | Share target-aware checked costing across constant evaluation, preparation and runtime, with static certification, residual checks and scoped schedule certificates.            | G4, G8     | §§8, 12, 18    | V16-V17                |
| R11 | Probe and exploit Polars 2-era Rust capabilities through explicit engine, order, validity, spill/effect and evidence contracts without depending on version-number assumptions. | G2, G4, G8 | §§10, 19       | V18, V20               |

Three scope classes prevent the reference catalogue becoming an accidental
single-release promise. The classes remain proposed pending ToR Q4.

| Scope       | Designed deliverable                                                                                                                                                                                                        | Boundary                                                                                                                                                       |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core        | Bool/I64/F64 arrays, public graphs, exact numerics, rank/products/stencils, diagnostics, table integration, native/Polars routes, proof-capable numeric views, downstream proof fixtures, and staged costing/certification. | Required proof evidence and static-cost subset are release gates. Not every operation must lower to a native Polars expression or expose a fully static graph. |
| Integration | Typed cells/glam, correspondence, segments, genuine masking, reusable plans/resources and indexed sinks, with corresponding public models and downstream higher-order/commit proofs.                                        | Separate proof and conformance gates; actual trasic adoption remains an independent experiment. Core does not depend on trasic availability.                   |
| Deferred    | Specialized dense linear algebra, FFT, additional dtype families, GPU/JIT compilation, autodifferentiation, and a general adaptive graph-control language.                                                                  | No initial API or performance promise; evaluate through the final roadmap phase.                                                                               |

Full APL compatibility, implicit table joins, mandatory wavefront rendering,
and rewriting robust geometry interiors as tacit trains are non-goals, not
items waiting in the deferred queue. The project defines an algebra over
collections, not a replacement for every mathematical library.

## 3. Architecture and package boundary

The implementation starts with a facade/library crate, a procedural-macro
crate, and a small internal `combobulate-kernel` crate. The kernel owns checked
shape, index, restricted cost and admission rules shared by runtime, constant
evaluation, and verification. It imports neither Polars nor glam and avoids
unnecessary allocation, dynamic dispatch and external state in its checked
core. These are dependency boundaries, not three independently marketed release
units.

The proposed default facade features enable macros and Polars. Native-only
execution and optional proof SDK profiles remain available without Polars;
ordinary consumers need no verifier installation. Glam is opt-in. A companion
proof package can organize exported metadata/lemmas, but must bind to
production bodies rather than replace them. The early shared-kernel and
downstream probes must validate this arrangement before feature or proof-API
stabilization.

The dependency direction is frontend to semantic graph to planner to backend
ports. The semantic module must not import Polars or glam types. The public
facade may re-export supported adapters behind features. Domain extensions own
their types and kernels; backend registrations refer to operation identities
through core-owned registry interfaces.

| Component           | Responsibility and contracts                                                                                            | Principal failure                                                             | Reuse or reason for custom code                                                                        |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Syntax frontend     | Parse literals, pipelines, and graph bodies; attach source spans; build ordinary descriptors.                           | Syntax or unsupported host/DSL boundary.                                      | A token parser such as `syn` can supply Rust-expression parsing; the `\|>` grammar remains custom.     |
| Semantic kernel     | Checked shapes/indexing, restricted cost expressions, admission and schedule validation, with public logical contracts. | Invalid bounds, unsupported certificate, or failed proof obligation.          | One dependency-light executable core for const/runtime and the supported verifier subset.              |
| Semantic graph      | Own dynamic/static descriptors, schemas, effects, policies, provenance, and denotation.                                 | Inconsistent constraints or invalid application.                              | Array meaning stays independent of dataframe semantics; public proofs do not expose private IR layout. |
| Operation catalogue | Supply built-in descriptors and derived public operations.                                                              | Unsupported dtype, rank, or operator operand.                                 | One registry, with public composition used for examples rather than hidden special cases.              |
| Planner and checker | Propose eligible regions/schedules and validate semantic/resource obligations through the smaller kernel.               | Unsupported or invalid certificate, budget failure, or unresolved binding.    | Heuristic planning stays separate from checked rule/admission validity.                                |
| Native executor     | Run compiled scalar/cell/batch kernels with explicit views, scratch, masks, and cancellation points.                    | Kernel error, schema violation, or resource exhaustion.                       | Ordinary Rust loops and domain kernels; no new JIT is required.                                        |
| Polars adapter      | Translate eligible graph regions and table crossings while preserving semantics.                                        | Incompatible policy, unexpected backend schema, or backend execution failure. | Reuse expressions and query execution where their contract matches.                                    |
| Typed/glam adapter  | Map logical cell schemas to checked typed views and component layouts.                                                  | Invalid domain construction or incompatible layout/validity.                  | Reuse glam within a cell; keep geometric meaning in the consumer.                                      |
| Diagnostics         | Render structured failures and explain plans with user-level provenance.                                                | Missing or ambiguous origin after a rewrite.                                  | Shared source map and operation labels, not backend message parsing alone.                             |

A typical numeric pipeline flows through graph construction, schema inference,
preparation, region execution, and result assembly. A native geometry path
shares those collection contracts without routing a scalar ray query through a
Polars frame. Explicit structured views and contracts replace a diagram here;
there is no unvalidated Mermaid dependency in the pack.

Backend selection is observable. `require_backend(Polars)` means the selected
region must meet the requested Polars capability, or preparation fails. A mixed
plan can use a native stage when its policy permits it, but must display that
choice. An opaque native callback hosted by Polars is not described as an
optimizer-visible native expression.

## 4. Values, schemas, ownership, and logical identity

### 4.1. Public conceptual types

`Array` and `Batch<T>` hold materialized values or views. `AExpr` and
`BatchExpr<T>` describe deferred results. `Unary` and `Binary` hide reusable
graph fragments. A `PreparedPlan` records validated requirements, eligible
stages, dynamic obligations, resource bindings, and the chosen execution
policy. N-ary operations use the same internal argument-vector model without
adding large public generic types.

Array dtypes are dynamic metadata. Typed batches retain a coarse element type
in Rust. Optional rank markers can improve a small set of APIs, but arbitrary
shape arithmetic belongs in the semantic checker, not recursive type-level
traits. A value cannot become a point, normal, or matrix merely because its
buffer has the expected number of floats.

Immutable handles share graphs and backing buffers. `comb!` captures inputs by
handle, preserving ownership of a materialized array for reuse. Borrowed
operation syntax clones a descriptor, not its results. Host moves and mutable
captures require explicit syntax at the host boundary; the macro does not
invent repeated clones of arbitrary user objects.

A prepared plan can own immutable bindings through shared handles. The
integration interface may also execute against borrowed bindings whose lifetime
is bounded by that execution. Such a plan cannot outlive a borrowed resource.
Do not solve lifetime complexity by requiring every native domain value to be
`'static`, nor by storing unchecked erased pointers.

Public logical collection and graph models, checked borrowed views,
source-bound witnesses, and success/error/frame contracts are part of the API,
not private verification conveniences. Section 17 specifies them and the
boundary for unverified safe callers. Dynamic handles retain their small
ergonomic form; proof-capable native application also retains executable
callable bindings.

### 4.2. Shape and schema

A scalar has shape `[]` and one logical value. An empty vector has shape `[0]`.
A batch shape excludes internal cell coordinates. `Batch<DVec3>` with shape
`[height, width]` contains `height*width` vectors, not a scalar array whose
final axis happens to have length three.

The internal schema records cell type or scalar dtype, nullability, visible
shape, optional axis names, and logical-domain information. Dimensions are
known non-negative extents or constrained symbols. Compute products with
checked arithmetic. If any extent is zero, the cardinality is zero; do not
overflow an intermediate product before noticing that zero. Strides and byte
counts still need their own representability checks if a consumer constructs
them.

A schema function returns an output description and obligations. It must handle
empty frames without evaluating a kernel. An opaque operation supplies a schema
function or an explicit checked declaration. Returning a different shape or
dtype at execution is a kernel-contract error, not a reason to mutate the
prepared result schema silently.

A filtered extent `M` may remain symbolic with `0 <= M <= N`. A downstream
reshape records an equality obligation. The executor discharges that equality
once `M` becomes known and before allocating the incompatible consumer. An
unknown size is not zero, and a failed size estimate is not unlimited capacity.

### 4.3. Correspondence is more than shape

A domain identifier names logical positions within a collection. Selection and
permutation maps derive correspondence from those positions. Operations that
preserve one output per input retain the relevant mapping. Filters, gathers,
replication, and segment expansions produce explicit mapping relationships.

`zip_aligned` checks that two inputs refer to the same positions in the same
order. Equal dimensions do not establish that fact. `zip_positional` is an
explicit caller choice for separately imported arrays; it records a positional
boundary rather than fabricating common origin. Neither operation performs a
join by name, key, or dataframe column label.

Domain wrappers own semantic invariants. For example, a normalized normal type
requires a validated constructor; a plain `DVec3` cell does not certify unit
length. Scalar and batched paths must call the same domain validation policy.

## 5. Array, rank, structural, and neighbourhood semantics

### 5.1. Agreement and rank

Default elementwise agreement permits equal visible shapes or extension of a
scalar shape `[]`. Different non-scalar shapes fail. `broadcast(f)` enables
explicit trailing singleton agreement: equal extents match; extent one may
extend; zero with one yields zero; zero with a different non-one extent fails.
No operation infers a semantic row/column orientation from a coincidental
length match.

For unary rank application, split the input into `frame ++ cell_shape`, with
trailing `k` axes forming the cell. The result has shape
`frame ++ result_cell_shape`. `rank(k, f)` requires `0 <= k <= input_rank`.
`rank2(l, r, f)` requires equal frames or one empty frame; an empty frame
extends across the other. An empty frame is rank zero, not a frame containing a
zero extent. Wider frame broadcasting requires an explicit operation.

`rows(f)` means `rank(1, f)`. `cols(f)` applies `f` to each column of the
trailing matrix, retaining leading batch axes. Its initial convenience contract
supports scalar outputs `[..., columns]` and vector outputs
`[…, output_length, columns]`. More complicated output rank requires explicit
axis/rank composition rather than an arbitrary axis-insertion convention.

Dense assembly requires uniform output cells. A declared variable-length result
uses `Segmented<T>`. A checked dense assembly may discover uniformity at
runtime, but it must reject the first conflicting cell with a coordinate and
expected shape; it cannot substitute a ragged result under the same expression
type.

### 5.2. Ordering and structural operations

Logical scalar indexing is row-major. Physical storage need not be. `reshape`
requires equal element counts. `reshape_cycle` explicitly repeats or truncates
that logical ordering; a positive target from an empty source fails. The
initial API does not interpret negative dimensions or a magic inferred `-1`.

`transpose` reverses visible axes; rank-zero and rank-one inputs remain
unchanged. `permute_axes` validates a complete bijection. `ravel` follows
logical row-major order, never raw buffer order. Index transformations can
remain views until a consumer demands materialization.

`take` and `drop` use signed prefix/suffix counts and clamp to the existing
axis length; they do not create padding. `rotate(offset)` uses wrapping reads
from coordinate `i-offset`. `shift(offset).fill(value)` uses the same sign
convention without wrapping. A zero-length axis produces no reads.

Gather indices initially form a non-null rank-one I64 vector. Negative or
out-of-bounds indices fail. `compress` preserves relative order and requires a
matching mask for the chosen axis. `replicate` accepts non-negative counts and
checks their sum. Index, byte, and allocation calculations do not rely on
unchecked casts between I64 and `usize`.

Sorting is stable within each selected lane. Grade returns lane-local I64
indices, not a global flattened permutation. Null and NaN placement must be
explicit when the input contains them. Unique/membership operations use their
own documented key equivalence, not an accidental hash implementation of
floating-point equality. They remain integration scope.

### 5.3. Generalized products

`inner(reduce_op, pair_op)` contracts `L ++ [k]` with `[k] ++ R` to produce
`L ++ R`. For each output coordinate it applies `pair_op` to corresponding
contracted elements in increasing `k` order, then performs the specified right
reduction. Empty contractions require a registered or explicit empty identity.
No multiplication of two independent batch frames is inferred.

`matmul` requires inputs of rank at least two. It contracts final matrix axes
`[..., m, k]` and `[..., k, n]`, with equal batch frames or one empty batch
frame. Explicit broadcasting handles other intended batch agreement. Numeric
optimization must preserve the chosen accumulation contract; a fast matrix
library is not automatically equivalent to an exact right-associated sum.

`outer(f)` forms all pairs of logical elements and concatenates their visible
shapes. `outer_cells(l, r, f)` instead pairs cells and produces
`left_frame ++ right_frame ++ output_cell_shape`. Cost checks occur before
Cartesian expansion; tiling can reduce intermediate storage, not the inherent
size of a fully materialized result.

### 5.4. Stencils

A footprint supplies ordered active offsets over explicitly selected axes.
Offsets follow row-major traversal of the literal. Odd extents have a centred
default anchor; even extents require an explicit anchor. Reject an all-zero
footprint in the initial contract. Each neighbourhood is a rank-one logical
collection passed to the derived verb.

`Fill(value)` supplies an out-of-bounds cell. `Wrap` applies modulo per spatial
axis. `Reflect` excludes the boundary element on reflection: for extent `n>1`,
map an integer coordinate through period `2*(n-1)` and reflect its second half;
for `n=1`, every coordinate maps to zero. Zero-sized spatial dimensions produce
no output neighbourhoods. The rules apply independently to each selected axis.

Every output reads the original input snapshot. In-place updates cannot expose
partially computed neighbours. Physical chunks and tiles require halos; they
are not semantic boundaries. A flattened shift by one must check the column
coordinate before treating that value as a horizontal neighbour.

A recognized neighbourhood sum may fuse without allocating a full expanded
neighbourhood array. A generic kernel may materialize a bounded tile plus halo.
Both routes implement the same ordered neighbourhood and numeric contract.

## 6. Numerical, validity, and reduction contracts

### 6.1. Dtypes and exceptional values

Core scalar dtypes are Bool, I64, and F64. Bool is not a hidden integer
subtype. Mixed I64/F64 arithmetic requires an explicit cast except for `div`,
which means true division to F64. `idiv` truncates towards zero; `rem` follows
the truncating quotient. Checked integer operations reject overflow, including
the specified MIN/-1 division/remainder case. The conversion of large I64
values to F64 can round and remains explicit except within documented true
division and aggregate definitions.

F64 arithmetic follows the selected floating implementation's operation
semantics. Ordinary division, square root, logarithm, and power can produce
non-finite values rather than domain errors. `checked_div` instead rejects a
zero denominator, non-finite operands, or a non-finite result for active,
non-null inputs. Future checked operations must be named or policy-explicit.

Null is validity metadata, not NaN. Arithmetic propagates null. Comparisons
with null yield unknown. Boolean and/or use three-valued Kleene logic; xor is
unknown when either operand is unknown. Aggregate null propagation is stricter
than merely applying Kleene logic to a mixed-validity reduction: `any` and
`all` first honour the aggregate null policy. `.skip_nulls()` removes invalid
values in original order and then applies the normal empty-input rule.

`min`/`max` are binary numeric operations; `minimum`/`maximum` are aggregates.
The proposed binary contract propagates NaN, with signed-zero ties choosing
negative zero for min and positive zero for max. Diagnostic predicates produce
non-null masks: `is_null` tests validity; `is_nan` and `is_finite` return false
for a null input. Selection with an unknown mask returns an invalid result
cell; it does not reinterpret unknown as false unless a selection policy says
so.

External facts motivating adapter checks appear in E-POLARS-NULL. Combobulate's
rules above are deliberate definitions, not assertions about Polars defaults.

### 6.2. Association, emptiness, and scans

Generic `reduce(f)` removes the last axis and uses exact right association
without permuting inputs. `fold_left(f)` makes the other association explicit.
Both return a singleton unchanged. Their empty identity applies only to empty
lanes; it is not an injected seed. This matters for signed zero and fallible
operations. An explicit axis reduction of a scalar fails; whole-value
aggregates view a scalar as its one logical element.

`scan(f)` returns right-associated reductions of successive nonempty prefixes.
`scan_left(f)` performs inclusive left accumulation. For `[10, 3, 2]` and
subtraction, their results are `[10, 7, 9]` and `[10, 7, 5]`. A generic opaque
right-prefix scan may require `n*(n-1)/2` applications. The planner reports
that cost and must not substitute a linear left scan with different semantics.
Empty scans produce empty output without invoking the binary operation.

A `.reassociate()` permission authorizes a different grouping, not a
permutation or an unobserved dtype conversion. It also does not waive failure
equivalence. For checked I64, `MAX + (1 + -1)` succeeds while `(MAX + 1) + -1`
fails. Reassociation therefore requires a safe-domain proof, an equivalent
algorithm, or a separately accepted numeric policy. A metadata flag alone is
insufficient.

The exact contract makes some native Polars aggregations ineligible. Use a
faithful kernel rather than silently relaxing the request. Floating-point fast
paths require explicit conformance policy and evidence. The design does not
promise cross-platform bitwise identity for all transcendental functions.

### 6.3. Reducer state and statistical definitions

A reducer declares input schema, accumulator state, accumulate behaviour,
finalization, empty behaviour, and optionally state merging. A merge operation
also declares its ordering and numerical contract; its existence does not prove
associativity. This is the extension point for mean, richer statistics, and
weighted film accumulation, rather than forcing every aggregate into a
same-type binary verb.

Unqualified `sum`, `product`, `minimum`, `maximum`, `mean`, `variance`,
`stddev`, `any`, and `all` consume all visible axes of the current cell in
row-major order. `.axis(...)` restricts the aggregate; `.keep_dims()` retains
extent-one axes. Generic `reduce(f)` retains its distinct last-axis default.

Core `mean` converts inputs to F64, right-sums them, and divides by the count.
It rejects an empty input after null policy and counts above 2^53 for the exact
count-conversion range. `variance` uses a specified two-pass definition:
compute that mean, right-sum squared deviations, and divide by `count-ddof`.
`stddev` applies square root to the result. The default `ddof` is zero and the
count must exceed it. This deliberately simple reference definition is not a
claim of optimal numerical conditioning. Alternative stable or parallel
reducers require an explicit name or numeric policy and measured comparison.

Registered empty identities include typed zero for sum/add, one for
product/mul, false for any/or, and true for all/and. Minimum, maximum, and mean
have no silent finite default for empty input. `.identity(value)` supplies an
empty result only and must match the output schema.

Numerical equivalence is stronger than symbolic formula equivalence. In
particular, a scaled `hypot` implementation must not lower to `sqrt(x*x+y*y)`
where intermediate overflow changes a representable result. For the initial
`hypot` special-value contract, null propagates; an infinite operand produces
positive infinity even if the other operand is NaN; otherwise NaN propagates;
two zero operands produce positive zero. Every alternative lowering must match
this contract.

## 7. Macro grammar, application, and source provenance

The central spelling remains unchanged:

```rust
let centre = verb! {
    |x|
    let mu = mean(x);
    x - mu
};

let expression = comb! {
    measurements
    |> cast(F64)
    |> rows(&centre)
    |> transpose
};
```

The macro returns a graph expression. `.collect()?` executes it with the
default engine; `.prepare(&engine)?` separates validation/planning from
execution. The ordinary Rust equivalent uses `.expr().then(operation)` and
`.apply(...)`. `.as_fn()` supplies an ordinary closure for host composition.
E-RUST-CALL and E-TAP explain the stable-Rust boundary; custom callable-object
implementations are not required.

`comb!` parses left-to-right `|>` pipelines and a deliberately small expression
grammar. A stage lowers through an application protocol accepting built-in or
third-party descriptors. It must not use a hard-coded whitelist of operation
names. Descriptor-constructor calls such as `rows(mean)` are host construction
of graph objects; applying descriptors to graph arguments uses the DSL
application form. Arbitrary unknown host calls require `host { ... }` or a
native-kernel wrapper rather than inference from a function's name.

Arithmetic keeps familiar precedence. The macro lowers comparisons to array
nodes because ordinary Rust `PartialEq` returns bool (E-RUST-EQ). `&`, `|`, and
`!` denote elementwise Boolean logic. Array `&&` and `||` fail with a
diagnostic that directs the user to elementwise logic or a guarded operation.
The grammar must preserve `||` inside an explicit ordinary host closure rather
than misclassify host Rust as DSL syntax.

`verb!` uses placeholder inputs and immutable local bindings. A binding shares
one node. `host { ... }` executes once at graph construction, so two uses of
that binding do not repeat a host read or allocation. Graph application does
not execute a domain kernel. Resource sampling during execution uses an
explicit kernel/resource interface, not a construction-time escape.

`arr!` retains whitespace cells and semicolon rows. Complex and negative host
expressions require parentheses where whitespace notation would be ambiguous.
`array!` supplies ordinary nested comma-separated literals with the same shape
contract. Ragged literal rows receive compile-time source diagnostics. Runtime
extents and allocation failures remain domain errors. These are intentional
literal styles, not compatibility aliases for superseded APIs.

Source provenance includes the user's span, operation name, optional label,
stage position, and graph lineage. The macro evaluates an embedded host
expression once, binds it hygienically, and retains its span. Optimizations
carry origin sets and responsible sub-operation mappings into fused regions.
`#[track_caller]` supports ordinary Rust construction where practical, but does
not replace explicit macro-provided locations. E-RUST-MACRO grounds token/span
support; diagnostic quality still requires our own conformance tests.

Static descriptor retention is optional and preserves the same `comb!` grammar.
The frontend may emit const-evaluable cost checks only when it has the
necessary descriptors and target facts. It never evaluates arbitrary runtime
operation handles or `host` reads at compile time. Section 18 defines the
shared analyser and the strict versus adaptive admission distinction. Public
builder denotation and source provenance remain available to downstream proofs
(§17).

## 8. Preparation, planning, and graph lifecycle

Preparation refines any compile-time facts through deterministic graph
validation, schema propagation, effect analysis and candidate-lowering
selection. The planner proposes a schedule; the smaller checker admits its
semantic and resource obligations under explicit contracts (§18). Preparation
preserves public graph meaning and records its assumptions (§17). It collects
independent static errors without evaluating a first cell. Each dynamic
obligation has a producer event, a check location, and dependent consumers that
cannot start until it passes.

| State                      | Allowed work                                                                | Failure or transition                                                  |
| -------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Constructed                | Hold an immutable graph and unverified obligations.                         | Explain known structure; prepare against an engine.                    |
| Prepared                   | Bind compatible data/resources and inspect regions, obligations, and costs. | Execute; incompatible binding requires revalidation or re-preparation. |
| Running                    | Execute admitted stages and discharge newly known obligations.              | Produce a result, fail, or cancel according to sink policy.            |
| Completed                  | Expose immutable result or acknowledged sink commit.                        | Reuse the plan with new bindings, not the old result implicitly.       |
| Failed/cancelled execution | Retain structured error and committed-output status.                        | A new execution is explicit; no hidden retry of effectful work.        |

Plan caching keys include graph structure, operation/schema versions, policy,
required input schema, relevant resource generations, backend capabilities, and
feature/target constraints. Cost certificates additionally bind the accepted
rule and resource model; the Polars profile includes engine, spill-control
scope and capability evidence (§19). Relevant changes invalidate affected
certificates and verification metadata. Data values are bindings, not an
invitation to cache a previous result. If dynamic extents specialize a plan,
the cache key must capture that specialization or keep a runtime guard.

The planner forms regions with compatible logical index spaces, cardinality,
ordering, and policy. One graph can yield several native and Polars stages. An
elementwise vector of six values and a two-value aggregate cannot simply become
equally positioned columns without an explicit representation change. Nested
representations or separate regions may be appropriate; no global one-LazyFrame
rule exists.

Rewrites preserve values, validity, error categories, guard conditions, and
observable effects. Pure-total operations permit ordinary common-subexpression
elimination when their bindings match. Pure-fallible operations need stronger
guard/error analysis. Resource reads require declared stability; separate
random draws or sink writes cannot be merged because their syntax looks
identical. Optimizers must not lift a fallible expression outside the guard
that made it valid.

A physical rewrite carries checked side conditions and an eligibility reason,
or refuses the transformation. Explain output shows rejected high-value fast
paths when a semantic mismatch would otherwise confuse the user, such as
null-skipping or scan association. A performance preference never overrides a
requirement to execute faithfully.

## 9. Extension and kernel contracts

Three levels provide progressive integration. A graph-defined operation uses
public verbs and inherits their inference. A native operation supplies a Rust
callable plus schema and conservative execution metadata. A specialized
lowering registers a backend implementation for an operation identity and a
precisely eligible domain/policy. Users can start at the native level without
proving algebraic laws or modifying the core crate.

`../spec/kernel-contract.schema.json` and
`../spec/kernel-contract.example.json` provide a reviewable contract envelope.
They are design artefacts, not a stable plugin ABI or executable-plan format.
Schema validation checks that required fields exist, not whether a claim is
true. Implementation interfaces will use Rust types and a registry whose
versioning follows actual published contracts.

| Contract dimension | Required information                                                                       | Why it is separate                                                     |
| ------------------ | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| Schema             | Inputs, output rule, dtype/typed-cell invariants, and empty-frame inference.               | A valid shape cannot be learned by sampling a nonexistent first row.   |
| Cardinality        | Preserving, reducing, filtering, expanding, segmented, or constrained custom relationship. | Equal output length says nothing about partition independence.         |
| Read pattern       | Corresponding cells, indexed reads, neighbourhood, whole cell, or custom access.           | Determines bounds and halo obligations.                                |
| Partitioning       | Independent, prefix-state, halo, whole lane, segment, global, or explicit custom contract. | A scan requires prefix state even when its shape is unchanged.         |
| Ordering           | Input/output order, allowed regrouping, and permitted permutations.                        | Stable positions and exact numeric reduction are different guarantees. |
| Validity           | Null, NaN, inactive-cell, and unknown-mask rules.                                          | Missing data and guarded non-execution must not collapse.              |
| Effects            | Pure total, pure fallible, resource read, sink write, or opaque.                           | Controls caching, speculation, concurrency, and retries.               |
| Numerics           | Scalar domain, overflow, association, exceptional values, and equivalence requirement.     | Mathematical identity alone does not establish floating equivalence.   |
| Resources          | Borrowed/owned handles, scratch/output bounds, generations, and cancellation points.       | Prevents hidden lifetime, allocation, and sampling dependencies.       |

A native callback runs as trusted code in the host process. A panic is not a
normal miss or null result. The executor may translate unwind-safe boundaries
when supported, but cannot promise recovery from aborts, undefined behaviour,
or external side effects. A false metadata claim may produce a wrong answer; it
must never be the sole justification for unchecked memory access in an
otherwise safe extension API. Memory-unsafe adapters require explicit audited
unsafe boundaries with stronger contracts.

The native fast path dispatches once per batch region and runs a compiled loop.
It need not invoke a trait object for every cell. Polars callback wrappers may
bridge a native batch, but do not make opaque mathematics optimizer-visible.

Backend registrations use explicit operation identity/version plus eligibility
predicates. This avoids requiring an implementation of a foreign trait for a
foreign backend type. Ambiguous equally preferred registrations fail with their
names and contracts. The planner can expose a deterministic priority mechanism,
but priority must not resolve incompatible semantics.

An extension conformance harness exercises supplied schema/effect claims on
bounded generated inputs, including empty frames, invalid cells, partition
changes, and seeded faults. Tested law claims retain their bounds. They do not
become universally verified properties merely because the generator found no
counterexample.

The proof-capable extension API also specifies successful-result relations,
success conditions, failure/mutation frames, termination assumptions, and
higher-order callable or reducer invariants (§17). Its evidence identifies the
actual executable binding and verification scope. Consumers can still register
unverified native operations, but those declarations do not satisfy a
proof-required route or silently enable unsafe access. The updated contract
envelope records these distinctions and staged cost assumptions.

## 10. Storage, Polars, tables, and glam

A numeric Polars adapter may initially store a flat scalar `Series` plus
logical shape. The invariant is checked element count, not contiguity. Series
can span multiple chunks (E-POLARS-SERIES). Reshape can preserve canonical
storage; rechunking and physical transposes remain explicit costs.

Arrow-style fixed arrays, structure-of-arrays storage, and typed native buffers
are alternate representations, not semantic array categories. A nested parent
can be invalid even when its child storage contains ordinary values (E-ARROW).
Component extraction propagates the parent's validity and does not expose
hidden child values as valid data. One dataframe record batch requires equal
field lengths; differing array cardinalities need explicit stages or nesting.

The Polars adapter compares requested null, order, dtype, failure, and numeric
policies before using a native expression or aggregate. Mapping APIs require
correct schema and partition assumptions (E-POLARS-MAP). A failure to meet
those obligations selects an allowed faithful native stage or reports an
unsupported lowering. Catching a backend error and retrying a different
algorithm is not safe if the first attempt performed effects.

The table bridge accepts an explicitly ordered column selection and an explicit
common dtype. It preserves row order established by the relational plan; if
that plan has no guaranteed order, the caller must supply one before relying on
positional identity. Conversion back requires column names. No implicit name
alignment, join, or colour/point interpretation occurs. Projection and
filtering can stay relational before this boundary.

Glam supplies arithmetic within a logical cell. The adapter handles `Vec3`,
`Vec3A`, `DVec3`, matrices, and domain wrappers only through declared schemas.
It must account for column-major glam matrix storage, while scalar arrays use
logical row-major indexing. E-GLAM documents the relevant layout distinctions.
A component view of a matrix declares its row/column mapping; raw bytes do not
define that mapping. The initial component adapter requires a homogeneous
numeric cell schema. On reconstruction, all-valid components construct a cell,
all-null components produce a null cell, and partial component validity fails.
An arbitrary heterogeneous record needs a different explicit adapter.

A borrowed typed view requires validated representation, alignment, length,
validity, ownership, and lifetime conditions. `try_view` can fail without
copying; `to_owned_layout` can repack explicitly. Do not infer zero-copy
support solely from matching scalar count. Include SIMD/scalar feature
combinations in layout checks instead of assuming a single target layout
applies everywhere.

Trasic owns `Point3<Space>`, `Vector3<Space>`, `Normal3<Space>`, rays, hits,
and transform policy. An adapter preserves those distinctions but does not
define their physical meaning. Normal transformation and robust intersection
behaviour remain domain code; a matching vector size is not sufficient to
select a point transform for a normal.

Section 19 specifies the Polars 2-era capability contract. Engine selection,
ordering, optional schema/plugin hooks, spill permission and control scope are
explicit. The default policy permits no unrequested temporary-disk I/O. The
adapter must reject a strict guarantee it cannot enforce in the selected Rust
revision rather than borrow a Python API claim or race process-global settings.
No current Polars capability has been implementation-tested by this pack.

## 11. Structured execution and the trasic boundary

### 11.1. Guarded execution and state distinctions

`select(mask, a, b)` chooses among computed values. `masked_apply` guarantees
that inactive cells do not execute the guarded domain operation. An eligible
backend implements a genuine mask or a compact/evaluate/restore strategy.
Polars conditional expressions are not a general guard because branch
expressions may execute before selection (E-POLARS-SELECT).

For parallel cells, a failure may arrive in different wall-clock order. The
executor reports the failing operation and logical coordinate, not a promise
that the first scheduled failure is globally minimal. A diagnostic mode may
replay a pure failing slice to obtain a stable representative, but never
repeats an effectful kernel silently.

Miss, inactive, null, invalid input, and numerical failure have distinct domain
representations. A ray miss is an ordinary result, not `Err`. An inactive ray
does no work at a stage. A null cell has no value. A solver that cannot certify
an intersection reports its defined failure/status rather than manufacturing a
miss. Domain kernels choose whether failure applies to the whole operation or
returns an explicit per-cell status record.

### 11.2. Segments, reconstruction, and sinks

`Segmented<T>` stores validated offsets and logical values with per-segment
identity. Offsets are monotonic, start at zero, and terminate at the logical
value count; repeated offsets describe empty segments. `per_segment(f)`
respects segment boundaries independent of physical chunking. `flat_map_cells`
returns segmented output, not an unspecified dense shape.

CSG event merging can use this structure, but trasic defines coincident-event
policy, inside/outside transitions, orientation, materials, and boundary
provenance. Sorting stably is not by itself a correct geometric tie rule. The
experiment must compare domain results, not merely offsets and lengths.

Rendering samples retain sample identifiers and film positions across filtering
and reordering. A sampler resource declares whether output depends solely on an
explicit sample key or on a sequence whose order must be preserved. Do not
assume that changing scheduler order preserves the reference renderer's sample
sequence. A different sampler is an explicit compatibility/quality decision.

Reconstruction can emit several weighted splats per sample. Indexed film
accumulation uses a reducer state with a declared collision order and weight
finalization. Deterministic tile-local mode fixes the accumulation schedule
within its stated environment. It does not promise universal cross-hardware
bitwise equality or equate a generic mean with a reconstruction filter.

`execute_into` admits effects explicitly. The initial sink policy builds a
tile-local result and commits it once only after successful completion. Failure
or cancellation before commit leaves the destination unchanged. Larger
streaming sinks with partial commits require a distinct protocol that reports
committed ranges. They must not inherit atomicity by reusing the method name.

### 11.3. Three evidence-gated experiments

Packet geometry compares a direct Rust loop with a batch path that invokes the
same robust domain kernel. Vary singleton, small packet, and larger batch
sizes; include non-unit directions, tangencies, misses, and invalid active
inputs. Measure preparation, execution, allocations, and conversions separately.

Segmented CSG compares event generation/merging through explicit collections
against a straightforward domain implementation. Include empty segments,
coincident events, tangencies, and material provenance. The trasic owner
chooses the compatibility oracle and exact supported geometric subset before
execution.

A complete tile experiment combines sample generation, the existing transport
kernel, reconstruction, and film accumulation. Vary tile sizes, partitioning,
and permitted scheduling while retaining sample identity. Compare numerical
outputs, peak storage, execution overhead, and reviewer comprehension.

Each experiment records continue, revise, or decline, with measured evidence.
Direct scalar geometry remains usable without Combobulate or Polars. Wavefront
architecture is not a prerequisite; E-PBRT and E-DRJIT motivate examining costs
and specialized interfaces rather than assuming batch orchestration is faster.
No trasic performance or correctness result is claimed in this design.

## 12. Costs, cancellation, and trust boundaries

The execution policy carries maximum materialized elements, output payload,
tracked scratch/live allocation bounds, work admission, in-flight concurrency,
and explicit I/O/spill policies. Section 18 separates exact facts, conservative
bounds, estimates and unknowns. Static facts can fail a requested compile-time
admission check; preparation refines them and retains dynamic obligations.
Dynamic expansion performs checked counting/admission before the next
allocation or uses a bounded incremental builder that rejects growth at its
limit.

The planner proposes accounting for outputs, simultaneous distinct backing
allocations, copies, halos, layout conversions, metadata and aggregation state.
The schedule checker validates the obligations within the declared model. It
must not report only final output size as peak memory. An estimate labels its
confidence and any untracked backend allocations. Hard process-wide memory
ceilings require allocator or process isolation support; a library cannot
enforce them over arbitrary native callbacks that allocate outside its
accounting interface.

Cancellation is cooperative at stage/tile/kernel-declared checkpoints. A
non-cooperative native call cannot be safely interrupted merely because the
caller requested cancellation. Explain output identifies such regions. The
initial sink contract guarantees no tile commit after pre-commit cancellation;
it does not promise bounded cancellation latency for arbitrary Rust callbacks.

Untrusted dimensions, indices, masks, and imported validity metadata cross into
trusted indexing code. Validate those boundaries before unsafe access. Native
extensions remain trusted executable code, not sandboxed plugins. The core
performs no network I/O and does not serialize executable closures. Diagnostics
redact actual array/resource values by default; schemas, coordinates, and user
labels suffice for most failures.

Resource handles use ownership and generation checks, not hidden global state.
A stale or incompatible handle fails binding. Read-only resources may share
between workers under their declared synchronization guarantees. Mutable sinks
have an explicit ownership/commit discipline; no shared mutation hides behind a
nominally pure verb.

Budget numbers, supported target matrix, and performance thresholds remain ToR
Q2/Q3. The project must record them before gathering acceptance evidence, not
lower a target after observing a disappointing result.

## 13. Diagnostics and explainability

Errors expose a small stable category, operation identity, relevant schemas,
axis/cell coordinates, source location, causal stage, and a structured hint.
Detailed backend causes remain available through the error source chain and an
opt-in debug view. Translate known semantic mismatches using our preconditions,
not brittle parsing of Polars error prose.

| Category        | Example                                                | Useful context                                        |
| --------------- | ------------------------------------------------------ | ----------------------------------------------------- |
| Syntax          | Missing stage after `\|>`.                             | Original token span and expected grammar.             |
| Shape/rank      | Contraction dimensions differ.                         | Both shapes and contracted axes.                      |
| Cell schema     | Kernel returns a different dtype/shape.                | Declaration, actual result, cell coordinate.          |
| Validity/domain | Nullable selection mask or invalid active input.       | Explicit policy choices, not guessed intent.          |
| Numeric         | Checked overflow or empty mean.                        | Operation, coordinate, association/policy.            |
| Alignment       | Equal-sized batches have different ordering histories. | Selection/permutation lineage.                        |
| Capability      | No backend honours masked or exact-scan semantics.     | Rejected routes and eligible alternatives.            |
| Resource        | Expansion exceeds an admission limit.                  | Required/estimated size, configured limit, and stage. |

Hints must be shape-correct. For shape `[128,4]` plus `[128]`, a suggestion may
show per-row scalar agreement; it must not also suggest a feature-vector
broadcast that would require length four. Domain errors should identify what
must change without offering two contradictory guesses as equally valid fixes.

An unprepared expression can explain its valid prefix and static errors. A
prepared plan additionally displays logical shape transitions, native/Polars
regions, guards, halos, cardinality boundaries, materializations, resource
requirements, and unresolved runtime dimensions. Fused regions retain the
original operations for error attribution.

The first-screen criterion applies to a curated set of ordinary user mistakes,
not a claim that arbitrary third-party trait failures can never expose Rust
internals. Macro compile-fail fixtures and runtime snapshots enforce the stated
set. Code-generated span noise and backend type names count as regressions
within that acceptance surface.

## 14. Verification obligations and evidence limits

Every semantic delivery task follows the proof-first requirement in §17 and the
PF01-PF14 ledger. Formal proof targets, executable scope, trust assumptions,
success witnesses and negative controls precede implementation and remain in
the same review slice. The implementation also requires an independent scalar
reference evaluator for the core logical semantics. It must not share optimized
indexing or accumulation implementations with the routes it checks. Shared
schema/type definitions are acceptable; a shared faulty execution function is
not an independent oracle. The Python checks accompanying this documentation
validate a few examples only; they are not that future evaluator.

| ID  | Precise obligation                                                                                                                | Method, scope, and non-vacuity                                                                                                                                                                                 | Residual uncertainty                                                                             |
| --- | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| V1  | Host expressions execute once per graph construction; reusable bindings share nodes and preserve source spans.                    | Compile/run and UI corpus on actual macros; a side-effect counter and intentionally duplicated-expansion mutation must distinguish correct behaviour.                                                          | Does not certify arbitrary unsupported host syntax.                                              |
| V2  | Shape/cardinality inference matches logical execution, including scalar, zero-extent, and symbolic cases.                         | Verus shape/cardinality invariants plus Kani machine-width overflow checks on the shipped checker; include empty frame/cell and zero-times-large counterexamples. Reference enumeration remains supplementary. | Bounded enumeration is not proof for all ranks/extents.                                          |
| V3  | Structural index maps preserve intended coordinates and reject invalid bounds before unsafe access.                               | Verus coordinate/sequence refinement and Kani executable index/bounds checks; seed permutation and row-boundary faults. Miri and audited unsafe boundaries cover applicable alias/layout gaps.                 | Upstream allocator and compiler correctness remain assumptions.                                  |
| V4  | Rank output schema does not require a first cell; dense cells assemble uniformly or fail.                                         | Verus schema/frame relations and Kani bounded zero-call/nonuniform-output witnesses, with explicit declared-kernel assumptions.                                                                                | User-supplied schema mathematics can still be wrong outside tested domains.                      |
| V5  | Every eligible lowering matches value, validity, shape, order, and the applicable numerical/failure contract.                     | Prove owned lowering-eligibility rules where expressible; force actual native/Polars routes against an independent model. Upstream equivalence remains tested/trusted unless separately proved.                | Floating transcendental tolerance needs a declared envelope, not universal bitwise claims.       |
| V6  | Chunk/tile/segment partitioning does not create new semantic boundaries.                                                          | Verus partition/segment composition for owned kernels and Kani bounded halo/prefix-state controls; forced-backend repartitioning tests provide separate integration evidence.                                  | Does not prove throughput or all possible third-party partition contracts.                       |
| V7  | Inactive cells do not execute guarded operations; effects are not duplicated, merged, or retried illegally.                       | Verus guard/frame and sequential commit invariants; Kani explores actual faulting inactive cells, resource counters and commit transitions with reachable success/failure cases.                               | Native callbacks remain trusted; external effects cannot be rolled back generically.             |
| V8  | Exact reduction/scan, null, empty, signed-zero, and checked-overflow policies survive optimization.                               | Verus sequence association and reducer-history proofs; Kani finite-width/bit-pattern counterexamples including MAX regrouping and singleton -0. Numerical accuracy has its own scoped evidence.                | Sampled algebraic claims do not establish universal associativity.                               |
| V9  | Accounted allocations and dynamic expansion respect configured limits; unsafe access uses validated sizes.                        | Verus tracked-resource and checker-soundness invariants; Kani machine arithmetic and reservation transitions. Instrument the actual owned schedule; admit one workload and reject its next growth.             | Untracked native/backend allocation excludes a hard whole-process ceiling.                       |
| V10 | Curated user mistakes point to the original operation and a valid fix, even after fusion.                                         | UI/runtime snapshots plus reviewer tasks; faulty provenance and incorrect broadcast-hint mutations must fail acceptance.                                                                                       | Human comprehension evidence is local to reviewers/tasks, not a universal UX score.              |
| V11 | Independent extension crates can supply typed/native operations and lowerings without editing core.                               | External public-only numeric and typed fixtures, including downstream Kani/Verus contracts and a consumer-defined kernel; no private imports, assumed whole-executor body, or registry patch.                  | Does not imply ABI stability or safety of malicious native code.                                 |
| V12 | Selected trasic adapters preserve domain outputs, sample identity, segment provenance, and sink policy.                           | Three pre-registered experiments, scalar and external/domain oracles where applicable, partition and cancellation controls.                                                                                    | Actual trasic source and oracle selection remain unavailable in this commission.                 |
| V13 | Packaging and measured execution costs satisfy agreed acceptance boundaries.                                                      | Feature/target and proof-profile matrix, separately measured planning/execution/compilation/proving cost and actual allocation controls against pre-registered thresholds.                                     | No thresholds or benchmark outcomes currently exist.                                             |
| V14 | Required changes follow proof-first delivery and evidence binds to actual executable/specification identities.                    | PF ledger, pinned Kani/Verus profiles, positive witnesses, negative controls and TCB audit; timeout/skip/unsupported cannot count as proved.                                                                   | Compiler/solver assumptions remain explicit; a valid evidence schema is not a theorem.           |
| V15 | Downstream public contracts connect collection and graph models to production execution and meaningful successful/error outcomes. | External Kani/Verus consumers call comb! and only public APIs; wrong denotation, always-Err and substitute-executor mutations fail.                                                                            | Initial certified subset is explicit; opaque callbacks require their own evidence or trust.      |
| V16 | Static/preparation/runtime costing agrees for equal facts and target profiles and distinguishes certainty from unknowns.          | Shared checked analyser, Verus bound rules, Kani overflow checks, actual compile-pass/fail fixtures, and target-width cases.                                                                                   | Wall time and unknown backend allocations are estimates, not certified quantities.               |
| V17 | Checked schedules preserve declared semantics and scoped tracked-resource bounds.                                                 | Verus soundness theorem under kernel contracts; Kani malformed schedule, stale certificate, halo, alias and reservation controls.                                                                              | No planner-optimality or whole-process memory theorem; backend replanning needs covered choices. |
| V18 | Polars 2-era eligibility reflects actual pinned Rust capabilities, ordering and I/O control scope.                                | Capability probes, local policy-checker proofs and forced-engine null/order/chunk/spill failure tests; unsupported features remain ineligible.                                                                 | Upstream execution is external evidence, not automatically verified by an owned checker.         |
| V19 | Checked views, witnesses and higher-order/reducer contracts lift consumer relations over active cells and owned segments.         | Verus generic relations plus Kani actual callable/failure paths; stale witness, eager mask, wrong reducer and invalid offsets are negative controls.                                                           | Domain numerics and callback termination need distinct contracts.                                |
| V20 | Proof API and executable/backend binding changes invalidate affected evidence without exposing private layout.                    | External consumer compatibility fixtures, full dependency verification, stale metadata and changed pre/postcondition controls.                                                                                 | Source identity alone does not prove refinement; released specification changes require review.  |

The interaction matrix includes native-only versus Polars-enabled builds,
null-free versus nullable input, scalar/zero/singleton/multiaxis shapes,
canonical/view/chunked layouts, exact versus permitted-regrouping policies,
masked versus unmasked execution, and typed integration with/without SIMD
features. Add native/const/verifier profiles, exact/bounded/unknown static
visibility, public consumer packages, backend engines, spill/control scope and
proof-evidence revisions. Use covering combinations for broad interactions plus
exhaustive small cases for high-risk semantics. Mandatory triples include
null-parent/component-view/typed import, mask/fallibility/fusion, and
halo/chunk-boundary/zero-extent. Record uncovered combinations explicitly.

Negative controls must fail for the intended reason. An empty generator, a
filtered-away failing example, a skipped backend, or an expected-failure marker
does not discharge an obligation. The test runner records selected execution
routes so differential tests cannot accidentally compare the same fallback
against itself.

Performance evidence records workload, environment, policy, chosen route,
planning amortization, copying, samples, uncertainty, and the pre-agreed
target. Comprehension review compares the same tasks in ordinary Rust and
proposed composition, recording errors and explanation quality rather than
assuming fewer lines means greater clarity. Budget and acceptance changes
require owner approval, not silent benchmark edits.

## 15. Alternatives, decisions, and actionable gaps

| Proposed decision                                            | Alternative considered                                                              | Reason and cost                                                                                                                                                                  |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Inspectable graph with short handles.                        | Opaque closure chain or fully generic type-level expression tree.                   | Enables schema/cost/provenance inspection while limiting public trait noise; requires runtime semantic validation.                                                               |
| Backend-independent meaning with first-class Polars adapter. | Force every value and operation into a LazyFrame.                                   | Preserves typed cells, guards, and differing cardinalities; creates planner/backend conformance work.                                                                            |
| Native Rust cell/batch kernels.                              | Build a tracing/JIT renderer runtime immediately.                                   | Reuses existing domain code and avoids committing to a compiler project; some fusion opportunities remain unavailable.                                                           |
| Exact generic reductions with explicit alternatives.         | Inherit whatever cumulative/aggregate order the backend supplies.                   | Makes failures and results explainable; can exclude fast kernels and expose quadratic scans.                                                                                     |
| Explicit component and positional boundaries.                | Treat all vectors as anonymous scalar axes and all equal-length batches as aligned. | Prevents semantic/layout mistakes; callers must state conversions and pairing intent.                                                                                            |
| Facade, macro, and internal semantic-kernel crates.          | Duplicate static/runtime checkers or one backend-coupled monolith.                  | Shares checked executable semantics across compilation and verification without mandatory Polars/glam dependencies; early toolchain probe can falsify the representation choice. |
| Public proof models plus production execution bindings.      | Assume the whole executor or expose private IR to consumers.                        | Enables compositional application proofs; requires proof API compatibility and scoped TCB maintenance.                                                                           |
| Staged cost certification and a small schedule checker.      | Promise static cost for arbitrary runtime graphs or trust planner estimates.        | Preserves dynamic ergonomics while limiting guarantees to checked facts and resource models.                                                                                     |
| Capability-probed Polars 2-aware adapter.                    | Depend on a major version label or implicit global defaults.                        | Permits streaming/optimizer improvements while enforcing ordering and I/O scope.                                                                                                 |
| Draft APIs can change atomically.                            | Preserve every earlier sketch with aliases/shims.                                   | Avoids obsolete pre-1.0 compatibility machinery; adopters update against the chosen contract.                                                                                    |

Existing alternatives remain valid choices. `ndarray` offers conventional
multidimensional arrays, `glam` supplies small graphics maths, and `faer`
addresses dense linear algebra (E-NDARRAY, E-GLAM, E-FAER). Combobulate must
earn its custom layer through reusable rank composition, domain diagnostics,
and collection coordination, not through an unsupported claim that alternatives
cannot perform the calculations.

| Gap  | Requirement | Missing evidence/capability                                                                                       | Disposition and unblock condition                                                                                                       |
| ---- | ----------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| GAP1 | R1-R11      | No implementation or release baseline.                                                                            | Proposed work through roadmap phases 1-6; completion needs actual executable, verifier and adoption evidence within its declared scope. |
| GAP2 | R4, R7      | Unknown performance, memory, CI, compile-cost, and proof-cost acceptance numbers.                                 | ToR Q2; owner records controls and thresholds before acceptance experiments.                                                            |
| GAP3 | R5, R6      | Trasic tree, revision, and compatibility oracle unavailable.                                                      | Blocks real-client adoption evidence, not numeric core or synthetic typed fixture work; resolve Q5.                                     |
| GAP4 | R1, R3, R5  | Exact Rust/dependency/feature versions unselected.                                                                | Foundational probe and Q3 before publishing manifests or claiming stable compilation.                                                   |
| GAP5 | R7          | Initial release boundary, licence, and authorities unratified.                                                    | Q1/Q4/Q7; docs stay proposed and unreleased.                                                                                            |
| GAP6 | R1-R11      | GitHub publication destination unresolved.                                                                        | Q6; provide repository-ready files without creating unrelated remote records.                                                           |
| GAP7 | R8-R10      | Shared const/runtime/verifier subset and public proof dependencies untested.                                      | B01/B02 and tasks 1.2.4-1.2.5; narrow representation or certified subset without substituting an unproved body.                         |
| GAP8 | R11         | Polars 2-era Rust hooks, streaming/spill controls and benefit untested; final release/upgrade refresh incomplete. | PC probes, B05/B06 and task 1.2.6; document capabilities and refusal scope before eligibility.                                          |
| GAP9 | R8-R9       | Proof-exception and specification-compatibility authority unassigned.                                             | Q8/Q9 and task 1.1.4; exceptions cannot count as proof or remove ordinary runtime safety.                                               |

Candidate ADRs cover numerical/array semantics, macro staging and stable-Rust
application, backend/cell separation, initial feature/release scope, the shared
semantic kernel, public proof compatibility, resource certification, and
backend I/O control scope. No ADR is marked accepted merely because this table
names it. Domain adapters are necessary integration boundaries, not prohibited
obsolete-interface shims. No durable execution-plan wire format exists to
migrate in this baseline.

## 16. Execution handoff and change control

`roadmap.md` maps the requirements and verification obligations to bounded
workstreams. Before implementing a slice, its ExecPlan must inspect the current
repository, accepted document revision, applicable execution skill/template,
dependency versions, budgets, and task-specific assumptions. This pack does not
supply fabricated milestone evidence or confer implementation approval.

The scalar numeric/macro slice is ready for bounded implementation planning
subject to authority/toolchain decisions and the shared-kernel/downstream proof
probes. API stabilization and Core acceptance require the applicable
proof-first, static-cost and Polars capability bets; they are not deferred
hardening. The typed integration fixture is ready for design review. Real
trasic adoption remains blocked on its actual contracts and acceptance
controls. Optional backend or numerical acceleration must not redefine exact
semantics to obtain a green benchmark.

When an experiment falsifies a hypothesis, retain its result, propose the
smallest change that answers the evidence, and reconcile the ToR, context,
design, catalogue, and roadmap. A rejected trasic adoption can be a successful
experiment; it must not be relabelled as implemented benefit. Implementation,
verification, release, and outcome validation remain distinct records.

## 17. Proof-first development and the public verification contract

### 17.1. Required delivery discipline

Proof-first development is an explicit requirement from C-11, not optional
hardening after implementation. Before changing a semantic primitive, builder,
rewrite, admission rule, or public verification interface, the implementing
task must record its logical model, preconditions, postconditions, permitted
errors, mutation frame, termination claim, and trust boundary. It must select
Verus, Kani, or both, explain the choice, and supply an executable verification
target or a proof skeleton plus a meaningful success witness and negative
control.

The executable body and proof can develop together. “Proof first” does not mean
proving an implementation before it exists. It means that its obligations shape
the implementation and that the same delivery slice discharges those
obligations against the shipped body before claiming completion. A test suite
or a prose proof sketch alone does not discharge a requirement for
machine-checked evidence.

Verus is the preferred starting point for arbitrary-size structural properties,
sequence relations, loop invariants, and checker soundness. Kani is the
preferred starting point for executable finite-width arithmetic, boundary
failures, and bounded compositions. Use both where an abstract proof and
concrete machine behaviour need separate evidence. The pinned Kani contract
facilities may reduce unrolling costs, but experimental support requires an
early compatibility probe [E-KANI-CONTRACT]. The choice belongs in each
implementing task, not a late project-wide proving phase.

A verifier timeout, unsupported feature, failed unwinding assertion, skipped
harness, unsatisfied bound, or empty generator is inconclusive or failed
evidence. It is never success. A Kani bound describes the admitted proof
domain, not an implementation limit unless the API enforces that limit.
Harnesses keep unwinding checks and report their bounds [E-KANI-UNWIND]. A
large symbolic extent can exercise checked arithmetic without allocating an
array of that size.

A proof requiring an exception must identify its authority, reason, affected
claim, restrictions, and revisit trigger. An exception cannot turn an
assumption into a theorem, authorize a memory-unsafe safe API, or satisfy an
advertised proof-required route. Narrow or disable that route until its
obligations hold. Unverified external kernels may remain available through
explicitly weaker contracts. Required core proofs cannot disappear into an
unrestricted exception list. The release decision must inspect outstanding
exceptions and either resolve them or approve a truthful scope revision without
dropping C-11.

### 17.2. Obligations, evidence, and the trusted basis

[The proof-obligation ledger](../spec/proof-obligations.json) defines
PF01-PF14, links them to V1-V20 and implementing tasks, and records tool
selection, non-vacuity controls, and scope. All entries remain planned. The
existing scalar reference evaluator, Miri/audit work, fault injection, and
backend conformance remain necessary; formal verification complements rather
than renames them.

The [proof-evidence schema](../spec/proof-evidence.schema.json) separates
planned, proved, bounded-checked, tested, trusted, failed, and inconclusive
records. A record identifies the proposition, executable and specification
bindings, source revision, tool/solver versions, command, target/features,
numerical policy, backend profile, bounds, assumptions, termination scope,
positive witness, negative control, and result artefacts. A schema-valid record
establishes only that these fields exist. It does not establish the proposition.

Public claims distinguish successful-result correctness from success
conditions. An implementation that always returns `Err` must fail a success
witness. A masked-map proof with only inactive cells must also include a
nonempty active case. An expected failure must arise from the intended defect,
not an unrelated syntax or dependency failure. CI records successful
verification, counterexample, timeout, unsupported capability, and missing
evidence as distinct outcomes.

Verus external bodies, external specifications, and assumptions extend its
trusted basis; they do not verify the omitted implementation [E-VERUS-TCB].
Kani stubs likewise cannot assume the property the consumer wants to establish.
Typed symbol/specification bindings and revision fingerprints detect drift, but
a hash is an identity check rather than a refinement proof. Verify the same
executable body used in production where possible. If two bodies are
unavoidable, state and discharge their refinement relationship or report the
gap explicitly.

Separate collection correctness, numerical-policy preservation, and numerical
algorithm accuracy. A structural operation on F64 cells can preserve bit
patterns, including NaN payloads and signed zeros. A proof over mathematical
reals cannot silently replace that contract. A generic cell may remain
uninterpreted when only movement and correspondence matter. Deeper glam or
geometry mathematics needs a separate specification and evidence.

Kani's feature documentation describes incomplete undefined-behaviour coverage
and restrictions on floating-point and concurrent analysis [E-KANI-FEATURES].
Verus documents partial support for floating point, const constructs and trait
objects, and unsupported hardware intrinsics [E-VERUS-FEATURES]. Consequently,
scalar proofs do not establish SIMD correctness or race freedom. Unsafe views,
concurrent schedulers, floating kernels, allocators, and backend execution
retain explicit proof, test, audit, or trust dispositions. Never describe a
successful sequential harness as verification of a parallel scatter
implementation.

### 17.3. Public logical models and focused lemmas

Every proof-capable public collection exposes a specification view independent
of its storage. Array models contain visible shape, logical cells, validity,
and ordering. Batch models add cell schema and source-position correspondence.
Segmented models expose segment contents and ownership. Graph handles expose
the logical operation they denote, not private IR node layout.

These are ghost/specification models, not runtime copies. Verus supports the
`View`/`@` pattern and open or closed specification definitions [E-VERUS-VIEW,
E-VERUS-SPEC]. Keep small canonical definitions available and export focused
lemmas for transpose involution, permutation composition, gather
correspondence, rank/frame composition, stable selection, and segment
ownership. Do not require consumers to unfold the executor or automatically
load an unbounded collection of quantified lemmas.

For a successful rank-one gather, the public relation includes:

```text
result.length = indices.length
result[j] = input[indices[j]]
result.validity[j] = input.validity[indices[j]]
result.origin[j] = input.origin[indices[j]]
```

Invalid cells retain invalidity; the model does not expose hidden invalid
payloads as meaningful scalar values. Typed cells remain atomic until an
explicit component operation. This lets a consumer prove alignment of rays and
normals without proving the numerical implementation of normal transformation.

### 17.4. Checked inputs and source-scoped witnesses

Expose `DenseView<'a, T>`, `NullableView<'a, T>`, and `SegmentedView<'a, T>`
with checked constructors and inexpensive executable observers for shape,
length, validity, and logical indexing. These refine the ordinary dynamic API;
they do not require every consumer to use const generics. Core includes
dense/nullable numeric views. Integration supplies arbitrary typed cells and
segmented views.

Constructors establish representation and cardinality invariants at runtime.
Public safe entry points must remain safe for unverified Rust callers; a ghost
precondition cannot replace required validation. Verus's documented safe-API
boundary supports wrappers that check conditions before invoking a more
narrowly specified operation [E-VERUS-SAFE]. Ghost proof erasure must not
remove these runtime safety checks.

`Selection` and permutation witnesses capture reusable validated relationships.
A selection records its source domain/extent, chosen positions, validity
policy, and applicable immutable generation. A permutation additionally
establishes a bijection. An ordinary gather may repeat indices; a restoration
writer requires its separate uniqueness rule. The public contracts must not
conflate them.

A witness remains attached to the object and state for which it holds. New
data, resource generations, changed policies, interior mutation, or
incompatible plan bindings require revalidation of affected facts. Equal length
alone does not make a selection or alignment witness reusable. Safe callers
cannot construct unchecked witness fields. No global, unscoped `ProofToken`
grants access to arbitrary arrays.

### 17.5. Outcome, progress, and mutation contracts

Each proof-capable operation specifies three related claims: what successful
results mean, which failures are permitted and what they leave unchanged, and
which input/resource conditions guarantee successful completion. The last claim
includes callback termination or a bounded/fuelled protocol where necessary.
Partial correctness must not become an undocumented termination guarantee.

Error categories are public semantic values, not strings parsed from Polars.
Consumers can prove that a shape-valid checked gather cannot return a bounds
error, or that insufficient scratch leaves an atomic output unchanged. Dynamic
allocation failure, external I/O failure, cancellation, and nonterminating
callbacks remain explicit limits where the interface permits them.

The sequential native route accepts caller-owned output and scratch. Its Core
atomic-output form computes into admitted temporary storage and commits once;
failure or cancellation before commit leaves the destination unchanged.
Integration extends the same discipline to domain sinks and tile-local film
accumulation. A future partial-output protocol must have a distinct name and
committed-range/frame contract. No silently partial implementation may satisfy
the atomic interface.

### 17.6. Higher-order and reducer contracts

The proof-capable native path retains a typed binding between the executable
callable, its captured inputs, and its specification. General dynamic registry
handles remain available, but type erasure must not destroy the relationship on
which a consumer proof depends. A runtime declaration of purity, associativity,
or a cost bound is not evidence that it holds.

Mapping lifts a callable relation over corresponding cells. For every relevant
input the consumer establishes the callable precondition; for every output
allowed by the callable postcondition, the lifted result establishes the
desired relation. Verus's `call_requires`/`call_ensures` interface supports
this form [E-VERUS-HIGHER]. Asserting that one desired output satisfies a
postcondition is not enough: that says the output is permitted, not that it is
the only possible result.

For `masked_apply`, only active valid cells must satisfy the callable's domain
precondition, and inactive cells must not invoke it. Specify the inactive and
unknown-mask output rules separately. Immutable captures are preferred in the
initial verified subset; mutable resources use explicit borrowed state and
frame contracts. A Rust `Fn` bound does not establish purity, totality, or
freedom from interior mutation.

Reducers expose an invariant such as `AccumulatorModels(state, history)`.
Accumulation preserves that relation; finalization relates it to the returned
value; a merge relates both histories under the declared ordering and numerical
policy. A supplied merge method alone proves neither associativity nor safe
floating-point regrouping. Consumers can supply custom statistics or film
reducers without re-proving the library's traversal loop.

### 17.7. End-to-end meaning and verification profiles

The existing `comb!` notation remains unchanged. Its expansion calls specified
ordinary builders, which expose their denotation. Preparation proves or checks
a refinement from that denotation to an admitted schedule. Execution relates
the observable result and effects to the prepared meaning. The proof interface
must cover this entire chain; proving a scalar loop while leaving graph
construction unrelated is insufficient.

Expose an explicit production-usable `NativeExecutor::sequential()` route with
known resources, numeric policies, and no hidden backend fallback. Proof
support may add ghost models, lemmas, symbolic-input helpers, or verifier
metadata. It must not use `cfg(kani)` or another proof feature to silently
replace a Polars, SIMD, or concurrent executor by a different scalar
implementation. A scalar reference model remains valuable when labelled as
such, but backend refinement requires separate evidence.

For Kani, provide public executable observers, bounded input constructors and
stable contract targets. Bounds remain explicit in the consumer harness; valid
constructors must not assume the desired output or silently generate only empty
arrays. Avoid dependencies on stubbing private methods. Kani's contract support
is version-pinned and cannot generalize a bounded callee result beyond its
actual scope [E-KANI-CONTRACT, E-KANI-INPUT, E-KANI-STUB].

For Verus, provide public models/lemmas and a tested verified-dependency
profile using `cargo verus` [E-VERUS-CARGO]. A companion proof package may
organize these exports, but it must not consist of an assumed postcondition on
an unverified whole executor. Focused local verification can aid iteration; the
release gate must verify all required dependencies and bindings for the
declared profile. Ordinary library consumers do not need verifier tooling
installed.

External fixture crates must use only released-intended public interfaces and
actual `comb!` calls. Core fixtures cover structural round trips, shared
selection/validity, custom kernels/reducers, static costing, and atomic
failure. Integration adds active-only kernel preconditions, segmented
ownership, and tile commit. Both Kani and Verus receive positive and deliberate
negative consumers. Failures in unrelated imports or parsing do not count as
successful negative controls.

### 17.8. Proof API compatibility and CI cost

Public models, pre/postconditions, lemmas, effect policies, and trust
declarations form a versioned proof interface. Strengthening a precondition,
weakening a postcondition, or changing an open model can break consumers
without changing a Rust signature. Reconcile those changes explicitly. Internal
layout refactors should preserve downstream proofs that use only public
contracts. Obsolete unreleased interfaces still do not require compatibility
shims.

Verification artefacts identify target/features and executable/specification
bindings. Relevant changes invalidate them and any affected cost certificates.
Backend upgrades invalidate backend-dependent evidence, not unrelated
structural proofs. A report lists the remaining assumptions, rather than
exposing a single `verified` Boolean.

Pre-register proof runtime, solver memory, build latency, runner size, and
cache policy under ToR Q2. Use pinned tools, bounded jobs, cached artefacts,
and change-aware checks; perform full required-profile verification before
release. Timeouts and exhausted budgets trigger an explicit scope or
implementation decision, not suppressed assertions. Test the downstream
fixtures before stabilizing their API, not only after internal proofs succeed.

## 18. Compile-time costing and staged resource certification

### 18.1. Static visibility without a different language

An inspectable graph may contain runtime-built operation handles, dimensions,
and resources. A procedural macro receives tokens, not arbitrary local values
or a general type-checked Rust programme [E-RUST-MACRO]. It cannot discover the
body of a runtime `Unary` simply from its name.

Retain a static descriptor alongside dynamic graph ownership. A `StaticPlan` or
statically described reusable verb carries immutable operation identity,
schema/shape rules, policy, and cost templates. The existing `comb!` frontend
preserves this information when available; ordinary dynamic graphs remain
supported. Optional input bounds and strict policy declarations must not
require recursive type-level shape arithmetic or a new pipeline macro.

The same restricted checked analyser serves constant evaluation, preparation,
and runtime refinement. Its kernel must support immutable descriptors, checked
integer operations and finite bounded expression traversal. Rust constant
evaluation uses the target environment, including `usize` width [E-RUST-CONST].
Never substitute the procedural-macro host's pointer width or layout for the
target. Verus/const compatibility is an early testable bet, not an assumed
feature. If the chosen subset needs separate bodies, their refinement becomes
an explicit obligation before either can issue a certificate.

The macro never runs arbitrary `host { ... }` reads during compilation. It
emits static descriptors or ordinary runtime construction with single
evaluation. Rust name resolution and descriptor identity, not a textual
whitelist of verb names, determine the operation. Downstream compilation does
not run an arbitrary native kernel, contact a service, or launch a mandatory
SMT solver for costing.

### 18.2. Quantities and confidence

Each cost quantity names its unit, resource scope, target assumptions, and
classification. An exact value, conservative lower/upper bounds, a performance
estimate, and an unknown value are distinct. Unsupported cost expressions
remain unknown; they never become zero or an unlimited admission allowance.

| Facts available                                        | Available result                                                          | Required later checks                                                             |
| ------------------------------------------------------ | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Static graph, exact shapes, fixed eligible schedule    | Exact structural quantities and conservative tracked-storage/work bounds. | Binding/profile identity, actual kernel contract and runtime resource conditions. |
| Static graph with symbolic dimensions and input bounds | Formulae and conditional upper/lower bounds over that input domain.       | Bind symbols and discharge residual obligations before dependent work.            |
| Dynamic graph, data-dependent shape or opaque kernel   | Partial facts and explicit unknowns.                                      | Preparation/runtime analysis or refusal of a strict proof-required route.         |

Useful templates include `outer` result cardinality `L*R`, stable-filter
cardinality `0 <= M <= N`, straightforward exact right-prefix scan work
`n*(n-1)/2`, and a footprint-dependent upper bound on stencil reads. All
arithmetic is checked with zero/extreme extents handled deliberately. Early
failure or a mask can reduce actual work; an exact complete-execution operation
count must state that condition.

The count of arithmetic applications is not elapsed time. A native callback has
unknown internal work and storage unless it supplies a justified or enforced
contract. Numerical rewrites must preserve the failure/association policy;
mathematical equivalence does not justify changing the costed algorithm
silently.

### 18.3. Admission decisions and user diagnostics

For a hard budget `B`, a valid upper bound `U <= B` certifies that quantity
within its stated model. An exact value or valid lower bound greater than `B`
establishes certain excess. `U > B` alone establishes neither actual excess nor
universal failure: the admitted input domain is not certifiable against that
budget. Estimates do not discharge hard-budget obligations.

Two exact length-4096 vectors producing a materialized, non-null F64 outer
product need `4096*4096*8 = 134217728` payload bytes, or 128 MiB. A 64 MiB
output-payload budget rejects that result. Inputs whose lengths are merely at
most 4096 instead produce an uncertifiable-domain result; smaller bindings may
fit. Report the difference and suggest tighter bounds or a runtime admission
check.

Strict-static mode fails compilation when its requested static obligations
cannot be discharged, including unknowns. Adaptive mode retains preparation or
runtime checks. Ordinary dynamic use does not become invalid merely because the
compiler cannot see its graph. Diagnostics name the quantity, applicable bound,
input domain, limit and unresolved cause, and retain the user's source span.

The [cost cases](../spec/cost-cases.json) specify exact/bounded/unknown
examples, zero and target-width cases, right-prefix work, and aliased-storage
accounting. Their Python checker validates documentation arithmetic only; the
roadmap requires real compile-pass/fail consumers and runtime agreement later.

### 18.4. Peak storage belongs to the physical schedule

For a selected owned schedule, the tracked peak comprises distinct live backing
allocations at capacity, live validity/index/segment metadata, stage scratch,
halos, conversion buffers, and concurrent in-flight state. Views sharing one
allocation do not create independent copies; distinct simultaneous allocations
do not disappear because their logical values match.

The scoped rule is:

```text
peak_tracked <= max over execution states (
    sum(capacity_bytes of distinct tracked live backing allocations)
    + tracked stage scratch and metadata not already counted
)
```

The schedule declares which components the tracking model covers, allocation
rounding/alignment, and concurrency. Avoid double-counting metadata included in
a backing capacity. A streamed intermediate need not incur a fully materialized
logical output, while an API promising a fully materialized result must account
for that result regardless of streaming execution.

A planner proposes a schedule and rule justifications. A smaller checker
validates shape/index/guard constraints, resource-model assumptions and
liveness obligations. Verus targets checker soundness under declared kernel
contracts; Kani targets executable arithmetic and admission-state transitions.
Planner optimality is not part of the correctness theorem. Unknown rules,
invalid justifications or underestimated requirements refuse admission, rather
than trusting the planner's own success flag.

A certificate binds the semantic graph and rule version, selected schedule or
explicit class of permitted schedules, schema/input bounds, numeric/effect
policies, target/layout, kernel identities and evidence, backend capabilities,
and resource model. Rebinding or replanning rechecks affected facts. A dynamic
backend may choose another physical algorithm only when the certificate covers
that choice; otherwise it needs new admission or a weaker explicitly labelled
estimate.

### 18.5. Runtime guards and the limits of a certificate

Filtered or expanded sizes become known at producer events. The executor checks
new obligations before dependent allocation/access. An incremental builder
reserves tracked capacity before growth and fails at the first forbidden
reservation. Strict native kernels obtain output/scratch through the declared
execution context; arbitrary external allocation remains outside that guarantee.

A compile-time resource certificate proves neither available operating-system
memory nor allocation success. It also does not bound untracked Polars memory,
all process RSS, arbitrary callbacks, or elapsed time. Such limits need
enforceable external controls or narrower execution routes. Reports separate
output payload, owned scratch/liveness bounds, backend estimates, unknown
costs, and temporary I/O permission.

The resource checker has its own finite descriptor/work budget so a very large
expression cannot consume unbounded compilation resources. Pre-register
accepted compiler/proof overhead and measure cold and incremental builds. A
reduced static subset is an acceptable experiment outcome; silently disabling
its checks or changing `comb!` ergonomics is not.

## 19. Polars 2-era capability and execution contract

### 19.1. A versioned opportunity, not a Cargo version assumption

The Polars 2-era material discussed in C-09 motivates the capability probes
below [E-POLARS2-RELEASE]. The Rust package listing inspected for this revision
identifies 0.55.2 [E-POLARS2-RUST]; Python/API and Cargo version lines are not
interchangeable. This pack selects no production dependency and does not
prescribe `polars = "2"`. Choose an actual compatible Rust release or commit
and test its public interfaces. The final release/upgrade-page refresh failed,
as recorded in `references.md`; those opportunities remain conditional inputs,
not freshly confirmed implementation capabilities.

The [capability ledger](../spec/backend-capabilities.json) identifies
PC01-PC09, upstream evidence, probes and refusal rules. Every Rust probe
remains not run and no capability is marked eligible. Separate documented
upstream opportunity, compiled/tested support in the pinned Rust profile,
semantic eligibility, and unavailable/inconclusive results. Documentation and
Python methods are not proof that a particular Rust interface exists or honours
Combobulate's contract.

The adapter retains stable semantic ports and explicit capability negotiation.
Do not expose Polars internal plan types as the permanent public array or proof
API. A backend upgrade changes the profile and reruns affected conformance and
admission checks; it does not require changing `comb!` or proving unrelated
core lemmas again.

### 19.2. Engine and ordering discipline

Polars 2 makes streaming the lazy-query default, and operations such as joins,
grouping and unpivoting may reorder rows unless ordering is requested [
E-POLARS2-RELEASE]. Select the actual engine explicitly through the available
Rust API and record it in preparation and explain output. Do not inherit a
process-wide automatic choice while claiming a fixed route.

Each region declares logical ordering, allowed internal permutations,
correspondence maintenance and restoration boundaries. Preserve order where the
backend supports it; otherwise carry validated logical indices and restore only
where needed. Do not sort every intermediate as a substitute for a contract.
The table bridge accepts either an established order or an explicit fresh
positional-domain boundary; neither may fabricate alignment with another query.

Row-order preservation does not establish reduction association. Exact scans,
null propagation, numeric errors and genuinely masked execution retain their
independent eligibility checks. Streaming kernels preserve halos, prefix state,
and complete segment ownership across physical batches. Bound in-flight batches
and account for their simultaneous state in the selected resource model.

### 19.3. Spill is an effect and has a control scope

The release enables disk spilling, with a documented memory trigger around 80%
and a default 64 GB spill budget. Its initial out-of-core coverage includes
sorting, windows and many expressions, while joins/group-bys remain future work
in that announcement [E-POLARS2-RELEASE]. These are dated backend facts, not
Combobulate defaults or per-plan guarantees.

Combobulate's ordinary execution policy forbids unrequested temporary-disk I/O.
An opt-in spill policy declares permission, quota, location, cleanup,
cancellation, error handling, and isolation scope. The probe must establish
whether each control is per-query, per-engine, process-global or externally
enforced. Never mutate a global environment setting around concurrent queries
while presenting it as isolated per-plan state.

A strict no-spill or quota claim requires an enforceable route. If the pinned
backend cannot provide it, reject that region under that policy or use another
explicitly permitted route. An externally isolated executor is a separate
integration decision, not an implicit subprocess sandbox introduced by this
library. Spill failures must report cleanup/commit status; do not retry an
effectful plan with another engine automatically.

Out-of-core support is operation-specific. A streaming query can still retain
large backend state. Output payload, tracked native scratch, backend RAM
estimates, disk permission and disk bounds remain separate admission
quantities. A memory certificate for a native tile cannot certify an adaptive
Polars join.

### 19.4. Schema, extension, optimization, and provenance opportunities

The migration guide changes empty-list explosion, nested parent validity,
zero-width frame behaviour, and preservation of unknown Arrow extension types [
E-POLARS2-UPGRADE]. Use these as candidate simplifications only after
conformance on the chosen Rust profile. Distinguish empty from null segments,
and retain known Combobulate dtype information when an empty backend result
cannot infer it. Strict concatenation and non-lossy membership coercion
similarly fit our explicit agreement boundary, but do not replace it [
E-POLARS2-ANNOUNCE].

Extension metadata may transport a domain tag, coordinate space and schema
version with its storage. Imported metadata does not certify a unit normal,
prove a caller's domain invariant, or establish zero-copy glam layout. Validate
construction and component order exactly as §10 requires. A Map dtype does not
replace stable ordered segmented events.

Upstream dtype-dependent expression planning, deterministic-plugin
optimization, and physical-node attribution offer useful future hooks [
E-POLARS2-DTYPE, E-POLARS2-PLUGIN, E-POLARS2-PROVENANCE]. Probe their actual
Rust surface. Dtype specialization occurs at backend plan time unless
independently available as static facts. Plugin determinism is not sufficient
for speculation across a guard; pure/fallible/resource effects remain distinct.
Backend attribution can enrich our own source lineage, not replace it.

Measure each optional hook against the same disabled route and pre-registered
workload/cost criteria. An unavailable or unhelpful hook can receive a decline
or defer decision without discarding first-class Polars integration. This is a
forward-looking design, not a commitment to every new upstream feature.

### 19.5. Conformance and upgrade gates

The selected-backend record includes Rust revision, features, engine, target,
ordering, numeric/null/error policies, I/O controls and their scope, callable
registrations, and attribution capability. Include relevant fields in plan and
certificate compatibility keys. Changed capabilities invalidate dependent
lowerings and tests, not unrelated semantic proofs.

Force every claimed route in the conformance matrix. Exercise empty/null nested
values, zero-width shapes, positional reordering, guard/fallibility/CSE,
chunk/halo/prefix/segment boundaries, and no-spill/opt-in-spill failure paths.
Tests report the real engine so two silent native fallbacks cannot masquerade
as backend agreement. Unavailable features produce explicit dispositions, not
green skipped tests counted as support.

The owned capability/admission checker receives proof-first Verus/Kani
obligations. Upstream execution remains an explicit external contract backed by
conformance evidence unless an actual refinement proof exists. Requiring that
boundary keeps public consumer proofs honest while allowing Polars to improve
its internal optimizer independently.
