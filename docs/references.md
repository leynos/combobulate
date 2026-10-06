# Combobulate source and evidence register

Status: draft source register, revision 0.2. Revision research: 6 October 2026.
Original source/skill inspection: 5 October 2026; dates below retain that
history. Companions: `context.md`, `terms-of-reference.md`,
`technical-design.md`, `roadmap.md`, and `language-reference.md`.

## Source discipline

The supplied design conversation establishes requested behaviour and proposed
choices, not measured performance or implementation. During the original
inspection, the GitHub connector returned 404 for both `leynos/combobulate` and
`leynos/trasic`; repository search also found no `combobulate` repository under
`leynos`. This establishes a limit of this inspection, not proof that either
project does not exist. No project source tree, release, benchmark, or CI
result forms an implementation baseline.

External references below support descriptions of existing tools. They do not
establish that Combobulate has implemented, tested, or inherited a capability.
`latest` and `dev` URLs are moving references. Resolve exact dependency
versions and feature sets before implementation; do not copy earlier
conversational version suggestions into a manifest without checking them.

## Supplied design input

| ID   | Input                                                                                                                                                                            | Authority and use                                                                                                               |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| C-01 | Initial request for a Rust array/matrix library with APL-like ergonomics and a Polars backend.                                                                                   | Explicit user intent; establishes the problem and integration requirement.                                                      |
| C-02 | Discussion of understandable errors and thin macros.                                                                                                                             | Proposed diagnostic architecture; preserves the user's concern about macro-generated error noise.                               |
| C-03 | Discussion of extensibility and generic application.                                                                                                                             | Proposed open extension model; no third-party implementation exists in this evidence set.                                       |
| C-04 | Discussion of trasic geometry/render applications and glam.                                                                                                                      | Proposed demanding client and integration boundaries; not a source-code audit.                                                  |
| C-05 | User-supplied alternative design and instruction to retain current `comb!` ergonomics.                                                                                           | Explicit notation constraint; alternative semantics constitute design input rather than an implemented API.                     |
| C-06 | Subsequent synthesis: values/plans, typed cells, native kernels, reduction order, schemas, and verification.                                                                     | Proposed target consolidated by this pack; formal acceptance remains open.                                                      |
| C-07 | Original request for ToR, technical design, context, GIST roadmap, and tabulated reference using df12 skills.                                                                    | Authorizes the original document pack; implementation remains proposed.                                                         |
| C-08 | Discussion of compile-time costing, shared semantic kernels, Kani and Verus.                                                                                                     | Proposed mechanisms and explicit distinctions between static facts, runtime obligations and scoped proof evidence.              |
| C-09 | Discussion of Polars 2 implementation implications.                                                                                                                              | Forward-looking adapter input; version/capability claims require actual pinned Rust probes.                                     |
| C-10 | Discussion of consumer-verifiable APIs.                                                                                                                                          | Public models, checked views/witnesses, higher-order contracts, production execution and proof-API compatibility.               |
| C-11 | Current request to update all design documents with proof-first requirements, consumer verification support, compile-time costing, Polars 2 readiness and testable roadmap bets. | Explicit user requirement for revision 0.2; authorizes document edits, not a claim of completed implementation or verification. |

These sources are the supplied conversation, not published transcripts. The
pack contains a technical synthesis, not private account or personal context.

## Documentation methods

### D-TOR

`leynos/df12-documentation-skills`,
[`skills/terms-of-reference-doc/SKILL.md`](https://github.com/leynos/df12-documentation-skills/blob/main/skills/terms-of-reference-doc/SKILL.md).
Inspected blob: `51782c18874ebe67072fb9feffe04785ca9c653d`.

The ToR separates problem intent from implementation choices, identifies users
and non-goals, and retains known, assumed, and open claims. Existing answers in
the supplied conversation replace a redundant interview. Unresolved questions
remain explicit; this pack does not claim a separate outline-approval session.

### D-TDD

[`skills/tech-design-doc/SKILL.md`](https://github.com/leynos/df12-documentation-skills/blob/main/skills/tech-design-doc/SKILL.md).
Inspected blob: `14ac70b19405c98a80681e0ff941b33fc88281e9`.

Also inspected its `references/document-anatomy.md`,
`references/research-protocol.md`, and `references/editing-checklist.md`. Their
respective blobs are `c4b40c97bab445760d846fe5de33e324f44a5f17`,
`f6097e4a35c4538bc47026f9db6c5f69ce156d5c`, and
`4b8778c356ae877142b9e84968b0b5b13461aeba`. The design records alternatives,
failure modes, interfaces, and bounded verification obligations. Structured
companion artefacts carry proposed contracts. No unvalidated Mermaid diagram
appears in this pack.

### D-GIST

[`skills/roadmap-doc/SKILL.md`](https://github.com/leynos/df12-documentation-skills/blob/main/skills/roadmap-doc/SKILL.md)
and its
[`references/conventions.md`](https://github.com/leynos/df12-documentation-skills/blob/main/skills/roadmap-doc/references/conventions.md).
Inspected blobs: `58e8df91aa63fbb60fdac4c045542bf8b3fcb686` and
`45cf6ea50da85be2c1ad1dbd8a84125839d01829`.

GIST means Goals, Ideas, Steps, and Tasks. Phases carry falsifiable ideas;
steps carry coherent workstreams; checkbox tasks carry review-sized execution
units, dotted dependencies, design citations, and observable success criteria.
The roadmap makes no calendar commitments. GIST does not mean a GitHub Gist.

### D-CONTRACT

[Documentation-skills PR number 12](https://github.com/leynos/df12-documentation-skills/pull/12)
remained an open, unmerged draft at inspection. Its head was
`9a28f29de1a147b7c5d7f0c589370f215381fd66`.

Supplementary references inspected at that exact revision:
[`problem-contract.md`](https://github.com/leynos/df12-documentation-skills/blob/9a28f29de1a147b7c5d7f0c589370f215381fd66/skills/terms-of-reference-doc/references/problem-contract.md)
and
[`architecture-contract.md`](https://github.com/leynos/df12-documentation-skills/blob/9a28f29de1a147b7c5d7f0c589370f215381fd66/skills/tech-design-doc/references/architecture-contract.md).
Their blobs are `2cf4df02bcada2574a633cf705d0ae56fb48bf95` and
`189ad5a0387b93ce2c2926d56ceba0d05b31464b`.

This pack uses their concern-to-requirement traceability, evidence/approval
separation, greenfield tailoring, and non-vacuity checks as supplementary
guidance. It does not present that branch as merged repository policy. The
current installed ExecPlan skill/template was not inspected for this
commission; execution planning must check it before implementation handoff.

### D-VOICE

[`skills/df12-copy/SKILL.md`](https://github.com/leynos/df12-documentation-skills/blob/main/skills/df12-copy/SKILL.md)
and its full `references/voice-and-copy-style-guide.md` informed the editing
pass. Blobs: `ac2e899f9e664c5835cfd590704cb9336d42e258` and
`5434b2cfa16d5570453208b5ab001132f3da51c5`. Repository prose uses British
English with Oxford spelling, sentence-case headings, and explicit uncertainty
rather than promotional claims.

The revision 0.2 pass reread the ToR, technical-design and roadmap skills,
roadmap conventions, and shared editing checklist through GitHub. Their
recorded paths guide this update. D-CONTRACT's unmerged status and revision are
historical 5 October observations, not a new claim about the current PR state.
No new ExecPlan or repository implementation has been created.

## External technical evidence

### E-RUST-CALL

[Rust Unstable Book: `fn_traits`](https://doc.rust-lang.org/beta/unstable-book/library-features/fn-traits.html).
Custom `Fn*` implementations require unstable features in the inspected
interface. Design consequence: operation descriptors expose `.apply(...)`;
macros supply convenient call notation; `.as_fn()` supplies an ordinary closure.

### E-RUST-MACRO

[Rust Reference: procedural macros](https://doc.rust-lang.org/reference/procedural-macros.html).
The token-stream and span model informs parsing, hygiene, source attribution,
and the separation between host expressions and array expressions.

### E-RUST-EQ

[Rust standard library: `PartialEq`](https://doc.rust-lang.org/std/cmp/trait.PartialEq.html).
Its equality method returns `bool`. Array-valued comparison notation therefore
belongs in macro lowering, not an expression-handle equality implementation.

### E-POLARS-MAP

[Polars Rust: `map_multiple`](https://docs.pola.rs/api/rust/dev/polars_lazy/dsl/fn.map_multiple.html).
The inspected page identified `polars_lazy` 0.54.3. It distinguishes
operations independent of groups from group applications and requires a correct
output schema. This is an inspected documentation version, not a selected
dependency or a claim about the newest published release.

### E-POLARS-NULL

[Polars user guide: missing data](https://docs.pola.rs/user-guide/expressions/missing-data/).
Polars distinguishes nulls from NaNs; numerical aggregates skip nulls and
normally propagate NaNs. Combobulate must adapt or reject a lowering whose
policy differs from the requested semantics.

### E-POLARS-SELECT

[Polars: `when`](https://docs.pola.rs/api/python/stable/reference/expressions/api/polars.when.html).
The documented expression semantics evaluate branch expressions before
selection. The Python-facing documentation is evidence for a semantic hazard,
not proof that a particular Rust lowering implements guarded execution. The
Rust adapter must establish its actual contract through integration tests.

### E-POLARS-ARRAY

[Polars user guide: lists and arrays](https://docs.pola.rs/user-guide/expressions/lists-and-arrays/).
Polars distinguishes variable-length `List` values from fixed-shape `Array`
values within columns. Neither supplies Combobulate's complete rank semantics.

### E-POLARS-SERIES

[Polars Rust: `Series`](https://docs.rs/polars/latest/polars/series/struct.Series.html).
A Series can contain multiple chunks. Logical flatness does not establish
contiguity or justify an unreported rechunk.

### E-ARROW

[Arrow columnar format](https://arrow.apache.org/docs/format/Columnar.html).
The inspected specification identifies format version 1.5. Fixed-size lists
index into child arrays, nested parents carry validity, and record-batch fields
have equal lengths. These constraints motivate explicit layout, validity, and
cardinality transitions. Library documentation version is not format version.

### E-GLAM

[glam Rust documentation](https://docs.rs/glam/latest/glam/). The inspected
documentation identifies glam 0.34.0. It documents concrete vector/matrix
families, column-major matrix storage, and distinct `Vec3` and `Vec3A` layouts.
It also documents optional type features and parameter-validity assertions.
Exact adapter features and layouts must be checked against the version selected
during implementation.

### E-NDARRAY

[ndarray Rust documentation](https://docs.rs/ndarray/latest/ndarray/). Owned
arrays, views, and dynamic-dimensional forms provide a credible existing
alternative and a comparison point for dense-array kernels. Combobulate's
proposed difference is its inspectable operation algebra and contracts, not an
assertion that ndarray cannot express array computations.

### E-FAER

[faer Rust documentation](https://docs.rs/faer/latest/faer/). Dense matrix
operations and decompositions make faer a candidate specialist backend, not a
justification for reimplementing numerical linear algebra. Its integration
remains deferred pending demand and semantic conformance.

### E-DRJIT

[Dr.Jit: what is Dr.Jit?](https://drjit.readthedocs.io/en/latest/what.html).
Dr.Jit's tracing and compiled execution provide rendering-oriented prior art.
Combobulate does not undertake to reproduce its JIT or automatic
differentiation system in the initial scope.

### E-PBRT

[PBRT: mapping path tracing to the GPU](https://pbr-book.org/4ed/Wavefront_Rendering_on_GPUs/Mapping_Path_Tracing_to_the_GPU).
Its discussion of execution and memory costs motivates measuring collection
orchestration rather than assuming a wavefront conversion improves a CPU
renderer. No PBRT performance number is a Combobulate benchmark.

### E-APL-SCAN

[Dyalog scan reference](https://docs.dyalog.com/21.0/language-reference-guide/primitive-operators/scan/).
The documented evaluation-order exceptions motivate an explicit local
contract. Combobulate defines its own exact prefix reductions and left
accumulations; it does not claim APL compatibility.

### E-TAP

[`tap::Pipe`](https://docs.rs/tap/latest/tap/pipe/trait.Pipe.html). The
ordinary function-piping interface supports host-language interoperability. It
does not inspect closures or determine array semantics.

## Revision 0.2 research sources and their limits

Access date: 6 October 2026. Official documentation informs capability choices;
no dependency manifest, compiled integration or verifier result follows from a
page being read. Moving URLs need a pinned implementation-time recheck. Final
Polars release/upgrade refresh failures appear explicitly below.

### E-RUST-CONST

[Rust Reference: constant evaluation](https://doc.rust-lang.org/reference/const_eval.html).

Constant evaluation has a restricted executable subset and uses the target
environment. The design must probe shared const/runtime/verifier support rather
than execute arbitrary host code in a proc macro.

### E-KANI-FEATURES

[Kani Rust feature support](https://model-checking.github.io/kani/rust-feature-support.html).

The feature table distinguishes supported Rust constructs from incomplete
undefined-behaviour, floating-point and concurrency coverage. A passing
sequential or scalar harness does not certify unsupported execution behaviour.

### E-KANI-CONTRACT

[Kani experimental contracts](https://model-checking.github.io/kani/reference/experimental/contracts.html).

Function and loop contracts offer compositional mechanisms under experimental,
version-sensitive interfaces. Pin actual support and the scope of callee
evidence before relying on it downstream.

### E-KANI-UNWIND

[Kani loop unwinding tutorial](https://model-checking.github.io/kani/tutorial-loop-unwinding.html).

Unwinding and its assertions expose the scope of bounded verification. The
design retains these checks and never turns inadequate unfolding into a passing
result.

### E-KANI-INPUT

[Kani nondeterministic variables](https://model-checking.github.io/kani/tutorial-nondeterministic-variables.html).

Symbolic constructors must preserve type invariants. Custom constructors can
make collection bounds explicit, including for external types that consumers
cannot extend through an orphan trait implementation.

### E-KANI-STUB

[Kani stubbing](https://model-checking.github.io/kani/reference/experimental/stubbing.html).

Stubbing and verified-contract abstractions support modular analysis, but their
assumptions and lifetime/signature limits matter. Private-method stubs create
brittle coupling; the public SDK must avoid requiring them.

### E-VERUS-FEATURES

[Verus supported language features](https://verus-lang.github.io/verus/guide/features.html).

The inspected matrix records partial const/generic/trait-object/floating
support and unsupported hardware intrinsics. Public proof-capable profiles must
exercise a tested subset and record excluded routes.

### E-VERUS-VIEW

[Verus view operator](https://verus-lang.github.io/verus/guide/reference-at-sign.html).

The specification-view convention supports abstraction from executable
containers to logical models. Combobulate must still define and verify its own
views and refinement.

### E-VERUS-SPEC

[Verus specification functions](https://verus-lang.github.io/verus/guide/spec_functions.html).

Open and closed specifications support stable abstraction boundaries. Focused
public lemmas can expose useful facts without exporting every implementation
definition.

### E-VERUS-HIGHER

[Verus passing functions as values](https://verus-lang.github.io/verus/guide/exec_funs_as_values.html).

call_requires expresses callable applicability; call_ensures constrains
possible results. Consumer claims must cover every permitted output, not assert
only that a desired output is possible.

### E-VERUS-SAFE

[Calling verified code from unverified code](https://verus-lang.github.io/verus/guide/calling-verified-from-unverified.html).

Public safe interfaces need runtime validation of required safety conditions.
Ghost assumptions must not make an otherwise safe constructor unsound for
ordinary Rust callers.

### E-VERUS-CARGO

[Verus Cargo integration](https://verus-lang.github.io/verus/guide/cargo_verus.html).

Verified dependency configuration and metadata allow cross-crate integration.
The release gate must check required dependencies and actual executable
bindings, not rely only on focused local verification.

### E-VERUS-TCB

[Verus trusted computing base](https://verus-lang.github.io/verus/guide/tcb.html).

External bodies, external specifications and assumptions enlarge the trusted
basis. A specification attached to an unverified executor is not an
implementation proof.

### E-POLARS2-RELEASE

[Polars 2 release material](https://pola.rs/posts/release-polars-2/).

The material inspected during the design discussion describes
streaming-by-default, operation-specific out-of-core execution and disk
spilling. The final refresh returned an access/cache error; retain these as
dated upstream opportunities requiring PC01-PC04 probes, not confirmed
behaviour of a selected Rust dependency.

### E-POLARS2-ANNOUNCE

[Polars 2 announcement](https://pola.rs/posts/announcing-polars-2/).

The discussed stricter concatenation and coercion behaviour motivates adapter
simplification candidates. The final refresh failed; actual Rust conformance
and explicit local policy remain mandatory.

### E-POLARS2-UPGRADE

[Polars 2 upgrade guide](https://docs.pola.rs/releases/upgrade/2/).

The discussed empty/nested/extension changes inform PC05-PC09. The guide was
examined during the design research, but a final re-fetch failed. None of these
observations constitutes a completed adapter test.

### E-POLARS2-RUST

[Polars Rust package documentation](https://docs.rs/crate/polars/latest).

The inspected package listing identifies Rust polars 0.55.2, separate from
Python/API major-version numbering. This is an observed documentation version,
not a selected production dependency or Rust capability guarantee.

### E-POLARS2-DTYPE

[Upstream dtype-aware expression planning change](https://github.com/pola-rs/polars/pull/29547).

Candidate planning-time specialization seam. Verify the actual public Rust
interface, metadata contract and dependency availability before enabling it; it
is not a Rust constant-evaluation facility.

### E-POLARS2-PLUGIN

[Upstream deterministic plugin optimization change](https://github.com/pola-rs/polars/pull/29428).

Candidate optimizer participation for declared deterministic plugins.
Combobulate additionally checks purity, fallibility, guards and resource
effects before applying a transformation.

### E-POLARS2-PROVENANCE

[Upstream physical/IR attribution change](https://github.com/pola-rs/polars/pull/29522).

Candidate backend provenance hook. Retain Combobulate-owned source lineage and
probe the pinned Rust surface before promising physical-to-source attribution.

## Freshness and residual gaps

Recheck dependency facts when selecting versions, enabling features, changing
layouts, or changing lowering routes. Recheck project availability before
publishing. Recheck the documentation skill revision before implementation
planning, especially if PR #12 merges or changes.

No project implementation, verifier run, benchmark, reader study, or HgPovRay
execution supplies evidence for revision 0.2. The validation report
distinguishes actual document checks from unrun implementation obligations. No
remote repository content changed in this revision.
