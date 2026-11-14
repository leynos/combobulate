# User guide

Combobulate's array algebra is a minimal preview. The `combobulate` facade
crate carries an ordinary application path over I64 vectors — materialized
[`Array`](#build-and-run-an-array-expression) values, deferred expression
handles, and the `identity` and `add` operations — beside
[`BuildProfile`](#build-profile), which reports the features and target facts
compiled into the running binary. The unpublished `combobulate-kernel` crate
exposes only `TargetFacts`. Nothing in the workspace carries a stability
promise, and the `comb!` notation is not implemented. Use the examples in this
guide as working Rust; the illustrative code in the
[technical design](technical-design.md) and
[language reference](language-reference.md) describes intended behaviour and is
not compiled.

Read the [language reference](language-reference.md) for the intended `comb!`
pipeline notation, verbs, modifiers, and conjunctions. The
[technical design](technical-design.md) specifies shape errors, execution
boundaries, cost admission, and verification contracts. The
[roadmap](roadmap.md) records the experiments required before those proposals
become supported functionality.

For building and checking the current source, follow the
[developer guide](developers-guide.md).

## Project status, licence, and stability

Combobulate is ISC-licensed. It is not published to crates.io: publication
waits until the Core acceptance dossier (roadmap task 4.3.3) passes and the
sponsor approves release
([ADR-0004](adrs/adr-0004-licence-and-publication.md)). Until then, use it
from the Git repository only.

Before version 1.0, any release may change the API without compatibility shims,
following Cargo's rule that a change to the leftmost non-zero version component
is breaking. The public proof interface (logical models, pre- and
postconditions, lemmas, and trust declarations) is versioned with the crate: a
strengthened precondition or weakened postcondition is a breaking change even
when no Rust signature changes
([ADR-0005](adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md)). The
[evidence gate](adrs/adr-0009-proof-first-policy-and-evidence-gate.md) decides
what evidence backs each published proof claim. A schema-valid record reaches
`proof` only when it is deductive evidence or bounded evidence with
`type-complete` bounds, has a `verified` outcome, and its verdict is parsed
from a committed log with a digest. It must include at least one success
witness and every witness must be reached; it must include at least one
negative control, every required control must be rejected as intended, and no
control may be accepted or rejected for another reason. Every trusted item must
name a declared assumption or cited exception. The binding must match the
registered executable and specification digests, source revision, target,
features, semantic policy, backend profile, and implementation relation; the
run must use `full-profile`, and no exception may apply. Partial-bounds
evidence remains `bounded`, never `proof`. The initial release covers the Core
scope class of the [language reference](language-reference.md)
([ADR-0003](adrs/adr-0003-initial-release-scope.md)).

## Build profile

`BuildProfile` reports which features and target facts are compiled into the
binary, so an embedder can tell what backends it actually contains without
reading Cargo's build plan.

```rust
use combobulate::BuildProfile;

let profile = BuildProfile::current();
println!("{profile}");
```

The rendered line names the compiled backends and the target's pointer width,
for example `features: native, macros, polars; target usize: 64 bits`. Every
accessor is `const`, so the profile can be folded into constant context.

`BuildProfile` states compiled features and target facts only. It is **not** a
capability report: nothing may infer that an operation is supported from it.
Task 1.2.6 owns the Polars capability statuses.

### Cargo features

| Feature  | Default | Meaning                                                                         |
| -------- | ------- | ------------------------------------------------------------------------------- |
| `macros` | on      | Builds `combobulate-macros`. Reserved until task 2.3.1; exports nothing yet.    |
| `polars` | on      | Builds the crate-private Polars backend, which proves the pinned release links. |

Build with `default-features = false` to get a native-only build with no Polars
dependency and no macro crate. That route is what a consumer that must avoid
Polars entirely should select.

## Build and run an array expression

An array expression has three phases: apply operations to expression handles,
prepare a plan, and collect or execute it. The facade's names carry no type
arguments.

```rust
use combobulate::{Array, NativeExecutor, add, identity};

let values = Array::from_i64(vec![1, 2, 3]);
let shared = values.expr().then(&identity());
assert_eq!(
    shared.collect()?.as_i64_slice(),
    Some(&[1_i64, 2, 3][..]),
    "identity returns its operand unchanged"
);

let right = Array::from_i64(vec![10, 20, 30]);
let sum = add().apply(&values.expr(), &right.expr());
assert_eq!(
    sum.collect()?.as_i64_slice(),
    Some(&[11_i64, 22, 33][..]),
    "add sums matching positions"
);

let plan = sum.prepare(&NativeExecutor::sequential())?;
assert_eq!(
    plan.execute()?.as_i64_slice(),
    Some(&[11_i64, 22, 33][..]),
    "an explicit plan and collect agree"
);
# Ok::<(), combobulate::ExpressionError>(())
```

`collect` is preparation followed by execution with the default engine. Call
`prepare` and `execute` separately when you want the plan, for example to
inspect what preparation validated or to run it more than once.

### Error stages and codes

A failure is reported with the stage that found it and a registered code:

| Stage         | Code              | Meaning                                                    |
| ------------- | ----------------- | ---------------------------------------------------------- |
| `Preparation` | `ShapeAgreement`  | Two operands of an addition have different lengths.        |
| `Execution`   | `IntegerOverflow` | A sum leaves the I64 range; the report names the position. |

```rust
use combobulate::{Array, NativeExecutor, add};

let wide = Array::from_i64(vec![1, 2, 3]);
let narrow = Array::from_i64(vec![1, 2]);
let error = add()
    .apply(&wide.expr(), &narrow.expr())
    .prepare(&NativeExecutor::sequential())
    .expect_err("operands of different lengths cannot be prepared");
let [failure] = error.failures() else {
    panic!("one disagreement is one failure");
};
assert_eq!(failure.code(), "ShapeAgreement");
assert_eq!(error.stage(), combobulate::Stage::Preparation);
```

`prepare` reports every independent shape disagreement once, at the addition
whose own operands disagree, and `execute` stops at the first overflowing
addition. Formatting an `ExpressionError` gives the stage sentence and one line
per failure.

### Copying and sharing

`Array::from_i64` moves your vector into the array's shared buffer, so building
an array does not copy its elements. Cloning an `Array` clones the handle.
`identity` returns its operand's handle rather than a new node, so collecting
it returns an array that shares the input buffer.

An addition allocates one output buffer and leaves both operands unchanged. A
failed addition publishes nothing: the destination is not handed back holding
the positions that succeeded before the overflow.

### Current limits

- I64 vectors only. There are no other dtypes, no nulls, and no scalars.
- Rank-one only, with no broadcasting and no scalar extension.
- `identity` and elementwise `add` only; the `comb!` notation arrives in 2.3.1.
- `NativeExecutor::sequential()` is the only executor: a minimal preview
  engine, not a backend choice.
- Intermediate buffers live until the execution ends; freeing them earlier is
  task 2.3.5.

### Verification status

The shipped `add` kernel is checked locally with Verus; that result is not
admitted evidence. `make verus-kernel` runs the positive proof and rejects five
seeded wrapper mutants plus one body mutant, but the record it writes is a
development artefact under `tools/verifier-fixtures/verus-kernel/`. Admission
belongs to `PF05.proof@2.3.5`, which re-runs those proofs rather than adopting
the logs, so no proof claim in this guide is admitted evidence
([ADR-0009](adrs/adr-0009-proof-first-policy-and-evidence-gate.md)).

## Audit a source tree for trusted items

Run `scripts/trust_audit.py` to report every trusted item in Rust sources, in
the shape the evidence schema's `trust_audit.items` entries use.

```bash
scripts/trust_audit.py crates/combobulate-kernel
```

```json
[
  {
    "source": "crates/combobulate-kernel/src/lib.rs",
    "items": []
  }
]
```

Each argument is a file or a directory, and the command writes one JSON object
per audited source. A directory is expanded to the entry points Rust would
compile from it (`lib.rs`, `main.rs`, `mod.rs`, and every file under `tests/`,
`benches/`, and `examples/`), and the walk then follows `mod` declarations, so
a submodule is reported when, and only when, the crate compiles it.

An item carries its `item`, its `location` as `path:line:column`, and
`covered_by`, which is `null` unless the item names an assumption or an
exception declared in the repository's policy files. Use
`scripts/check_evidence.py` to admit evidence that cites an audit; see
[check proof-evidence records](#check-proof-evidence-records).

The command reads sources inside the repository only, because the driver paths
in its output are repository-relative and a path outside it has no such name.
It exits `0` when every source was audited, `1` when a source could not be (an
unreadable file, a path outside the repository, or a directory holding no Rust
entry point), and `2` for a usage error. A refusal matters: an empty audit is a
claim that a source holds no trusted items, so a source that could not be read
must fail the run rather than report nothing.

## Check proof-evidence records

Run
`uv run scripts/check_evidence.py --as-of YYYY-MM-DD [--require
proof|bounded|tested] spec/evidence/record.json`
to check one or more records. The date is required and makes exception
evaluation reproducible. The minimum level defaults to `tested`; `proof`,
`bounded`, and `tested` are the supported requirements. The command exits `0`
when every record meets the requirement, `1` when a record is admitted below
it, and `2` for unreadable input, a schema failure, or a usage error. A
verifier's verdict remains self-reported until a registered adapter validates
the cited log digest and supplies a matching result; registration by itself
cannot satisfy `proof` or `bounded`. Kani is registered and has an adapter, so
a Kani record that cites a committed log, its harness manifest, and that
manifest's sources is decided from those artefacts. The manifest must also bind
the `Cargo.toml` of each crate owning a bound source, because whether a crate's
string literals are code is read from it; a manifest that leaves it out refuses
its own audit. Verus has no adapter yet, so its records remain self-reported.

The command reads the repository policy files by default. To check records
against alternate or temporary inputs, pass all relevant paths explicitly:

```bash
uv run scripts/check_evidence.py --as-of 2026-10-11 \
  --bindings /tmp/evidence-bindings.json \
  --exceptions /tmp/exceptions.json \
  --decisions /tmp/decisions.json \
  --roadmap /tmp/roadmap.json \
  spec/evidence/record.json
```

The four options default to `spec/evidence-bindings.json`,
`spec/exceptions.json`, `spec/decisions.json`, and `spec/roadmap.json`.

Records use schema version 2. Version 1 records are rejected; see the
[evidence-record migration notes](revision-0.2.md#evidence-record-schema-migration)
and the [producer reference](evidence-and-decision-records.md) before updating
a producer.
