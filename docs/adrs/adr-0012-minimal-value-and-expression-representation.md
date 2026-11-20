# Architectural decision record (ADR) 0012: Minimal value and expression representation

## Status

Accepted on 2026-11-14: I64 values hold their elements in one `Arc<Vec<i64>>`;
applying `identity` returns the operand's handle rather than a node; a static
failure is reported only at the root-cause node and only once; execution walks
a linear schedule built from an iterative, memoized traversal; and each
verified kernel binds its executable identity to a structural digest. Records
the representation choices DL-2, DL-3, DL-7, DL-9, DL-12 and DL-14 of the
[1.2.2 ExecPlan](../execplans/1-2-2-minimal-ordinary-application-path.md),
which was approved before implementation began.

## Date

2026-11-14.

## Context and problem statement

Technical design §4.1 names `Array` and `AExpr` as the public conceptual types
but fixes none of the things a first implementation has to decide: what a value
holds, what applying an operation to an expression returns, how a static
disagreement is reported when several exist, what preparation produces, and
what ties a shipped kernel body to the specification it is supposed to refine.

Each of these choices is observable. A consumer can copy an input buffer, count
the failures one expression reports, or match on the stage word. A later
release cannot change them quietly, so they need a record and not only an
implementation.

The choices are also constrained by decisions already made elsewhere. `SC-12`
fixes the denotation and the error relation of I64 addition. `ADR-0009` fixes
that a proof claim is worthless unless the body it is about is bound to the
specification by identity. `PF05.proof@2.3.5` will re-run the proofs, so the
identity binding must survive a later release rather than being a one-off note.

## Decision drivers

- The roadmap's success criterion forbids copying input buffers unnecessarily.
- A proof obligation names a body. A record that cannot say which body was
  verified cannot support the admission 2.3.5 will perform.
- Preparation should collect independent static errors, per technical design
  §8; "independent" has to be made precise or two runs can report differently.
- A verified kernel must be revisable without invalidating an unrelated
  kernel's record.
- The repository denies `unsafe`, so a schedule cannot store raw pointers.

## Decision outcome

### Values hold one shared buffer

`Array` holds `Storage::I64(Arc<Vec<i64>>)`.
`Array::from_i64(values: Vec<i64>)` moves the vector into the `Arc` without
touching an element, and cloning an `Array` clones the handle rather than the
data.

`Arc<[i64]>` was rejected because it cannot be built from a `Vec` without a
copy: the slice needs its length header in front of data that already exists.
The extra indirection of the `Arc<Vec<i64>>` is paid once per kernel call, when
the kernel borrows `&[i64]`, and not per element. A constructor from
`Arc<[i64]>` is not added until a consumer needs one.

### Applying `identity` returns the operand

`Unary::apply` with the identity descriptor returns a clone of the operand's
handle and builds no node. `AExpr::then(op)` is defined as `op.apply(self)`, so
the two spellings cannot diverge, and `AExpr` carries no public generic
parameter.

This is what makes the shared-buffer property observable: `input.expr()` after
`then(&identity())` still describes the caller's own buffer, which the exposure
fixture in `tools/fixtures/native-consumer/` asserts by comparing pointers
rather than values.

### A static failure is reported at its root cause, once

The static length model is partial. `len(add(l, r))` is undefined when either
operand's length is undefined or when the two lengths differ. A disagreement is
reported only at the root-cause node, the `add` whose operands both have
defined, unequal lengths, so an ancestor of an undefined length reports nothing
rather than repeating its descendant's failure.

Preparation reports every root-cause mismatch once, in first-completion,
left-first post-order. Execution fails fast at the first failing `add` in the
same order. Lengths and a `mismatch_below` flag are computed in O(1) per node in
`Binary::apply` from the operands' cached facts, without running a kernel.

### Preparation produces a linear schedule

Preparation emits `Box<[Step]>`, where a step is an input binding or an indexed
addition. The traversal that builds it is iterative and memoized: an explicit
stack of finish and expand frames, with a visited set keyed by `Arc::as_ptr`.

The visited set lives only for the duration of `prepare`. The borrowed root
keeps every node alive for that whole walk, so an address cannot be reused
mid-traversal, and `PreparedPlan` never stores a pointer. Execution is then a
plain loop over the steps with no hashing.

Intermediate buffers live until execution ends. Freeing a buffer after its last
use is a recorded gap for task 2.3.5 and is not attempted here.

### A verified kernel binds its executable identity

Every `OperationId` reaches its kernel through one crate-private dispatch
function, and a unit test enforces that mapping. A verified kernel is one file,
so a later `sub` or `mul` cannot stale the `add` record.

The identity of `add` over I64 is the tuple:

- catalogue id `V001`;
- `OperationId::add()`, whose `name()` is `"add"` and whose `catalogue_id()` is
  `"V001"`;
- dtype `I64`;
- symbol `combobulate_kernel::elementwise_add::add_i64_into`;
- the structural executable digest of `src/elementwise_add.rs`;
- the specification digest of `verus/elementwise_add_contract.rs`;
- semantic policy `checked-i64`.

The tuple is recorded in the observation record under
`tools/verifier-fixtures/verus-kernel/provenance.json`. Technical design §17.2
asks for typed symbol and specification bindings plus revision fingerprints;
B01 asks for matched executable and specification identity.

## Consequences

A consumer of the exposure fixture can observe that the identity path shares
its input buffer and that an addition allocates exactly one output. Preparation
is deterministic, so a test can assert on the exact list of failures.

The digests bind the record to the bodies. Editing either source file without
re-running `make verus-kernel` fails `make design-check`, which is what makes
the record a statement about the shipped code rather than about whatever the
sources said when the note was written.

`Arc<Vec<i64>>` costs one extra indirection per kernel call. If a later release
needs a value that is built directly from a slice, it can add a constructor
without changing this record's value representation.

The schedule holds every intermediate buffer. That is the price of a plan that
can be executed more than once; task 2.3.5 revisits it when a caller can hand
the executor a destination it owns.

## Alternatives considered

- A generic `AExpr<T>`: rejected because the roadmap's success criterion asks a
  fixture to name the public types without type arguments, and dtypes are
  dynamic metadata in technical design §4.1.
- A recursive `Drop` and a derived `Debug` on the expression tree: rejected
  because a deep chain overflows the stack. Both are handwritten and iterative,
  and `src/expr/small_stack.rs` exercises them on a 2 MiB stack.
- Reporting a length mismatch at every ancestor whose length is undefined:
  rejected because it buries the one node a caller can fix under repeats of the
  same fact.
- Reusing the `Vec` for the first addition's destination: rejected because the
  kernel must leave `out` unchanged on every error, so a partially written
  caller buffer would publish a failed addition's prefix.
- Keying the visited set by a per-node identifier rather than by address:
  rejected because every node would carry a counter it does not otherwise need,
  and the address is already unique for the walk's lifetime. The walk's
  invariant, that the borrowed root outlives it so no node is freed and no
  address is reused, is what makes the address sound, and it is stated where
  the walk is written.

## References

- [1.2.2 ExecPlan](../execplans/1-2-2-minimal-ordinary-application-path.md).
- [ADR-0009](adr-0009-proof-first-policy-and-evidence-gate.md): proof-first
  policy and evidence gate.
- [ADR-0010](adr-0010-workspace-crate-boundaries-and-build-profiles.md):
  workspace crate boundaries and build profiles.
- [Technical design](../technical-design.md) §§4.1, 8, 17.
