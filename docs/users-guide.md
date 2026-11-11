# User guide

Combobulate's array algebra is not yet implemented. The `combobulate` facade
crate exports one public item, [`BuildProfile`](#build-profile), which reports
the features and target facts compiled into the running binary. The unpublished
`combobulate-kernel` crate exposes only `TargetFacts`. Nothing in the workspace
carries a stability promise. Do not use the proposed design examples as working
Rust examples.

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
manifest's sources is decided from those artefacts. Verus has no adapter yet,
so its records remain self-reported.

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
