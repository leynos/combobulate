# Combobulate library changes in this delivery

Date: 11 November 2026. Status: delivered, unreleased. This note records what
changed in the library and the shipped scripts since the repository's last
tagged state, so a consumer upgrading from it knows what to read first. The
repository has never been published to crates.io and carries no tags, so
"upgrade" here means moving to a later commit from an earlier one.

The crate remains `0.1.0` with `publish = false`
([ADR-0004](adrs/adr-0004-licence-and-publication.md)). Nothing in this note is
a stability promise; [ADR-0005][adr-0005] still governs that.

## Who should read this

- A consumer who builds the facade and wants to know which items and features
  exist now.
- A producer who writes or checks proof-evidence records.
- A contributor who runs the gate profiles by hand.

If you only consume the design documents, nothing here changes them. The
design revision is recorded separately in [Revision 0.2](revision-0.2.md).

## Facade features and the native-only build

The facade now declares two features and enables both by default:
`macros = ["dep:combobulate-macros"]` and `polars = ["dep:polars"]`. A consumer
that must not compile Polars, or must not compile a procedural-macro crate,
selects the native-only route:

```toml
combobulate = { path = "…", default-features = false }
```

That build has no Polars dependency and no macro crate. The repository's own
end-to-end check is `tools/fixtures/native-consumer/`, which depends on the
facade exactly this way and asserts that its dependency graph contains no
Polars, glam, Kani, or Verus package.

`polars` is pinned to `0.55.2` with `default-features = false` and
`features = ["lazy"]`, matching the calibrated measurement. The choice, and
the reasoning behind a crate-private module rather than a fourth crate, are in
[ADR-0010](adrs/adr-0010-workspace-crate-boundaries-and-build-profiles.md).

## The `BuildProfile` item

`combobulate::BuildProfile` reports which features and target facts the running
binary was compiled with:

```rust
use combobulate::BuildProfile;

let profile = BuildProfile::current();
println!("{profile}");
```

The rendered line names the compiled backends and the target's pointer width,
for example `features: native, macros, polars; target usize: 64 bits`. Every
accessor is `const`, so a profile can be folded into constant context.

`BuildProfile` is a report of compiled features and target facts. It is **not**
a capability report: nothing may infer that an operation is supported from it.

### Gate profiles a contributor can select

`make` selects a build profile with `GATE_PROFILE`. The values are
`native-only`, `polars-enabled`, `both` (the default), and the two
single-feature isolation profiles `macros-only` and `polars-only`. A profile is
its own Cargo invocation, so feature unification cannot let one profile mask
another. `macros-only` and `polars-only` are deliberately not part of `both`:
they exist to catch a swap of the two feature flags, and adding their cold
builds to the pull-request lane would spend the AC-07 budget.

## The trust-audit command

`scripts/trust_audit.py` reports every trusted item in Rust sources, in the
shape the evidence schema's `trust_audit.items` entries use. See
[the user guide](users-guide.md#audit-a-source-tree-for-trusted-items).

## The evidence gate admits a parsed Kani verdict

A proof-evidence record for Kani can now reach `bounded` or `proof` without its
verdict being self-reported. The gate binds three artefacts the record cites —
the log, the harness manifest, and the manifest's sources — and re-derives the
verdict itself. A record citing a log whose bytes changed, an unbound module,
or a manifest the parser cannot read is refused and falls back to
`self-reported`, which blocks verifier evidence.

The binding is per record and per manifest: a result is matched only when its
tool, log path and digest, and manifest path and digest all agree with the
record's own. Two records citing one capture against different manifests are
two verdicts, and neither can answer for the other.

Verus has no adapter yet, so its records remain self-reported.

## Migration checklist

- Replace any `combobulate = { … }` dependency that relied on a featureless
  facade with an explicit feature choice, or accept the new defaults.
- If you must avoid Polars, set `default-features = false` and check that the
  build still reports the features you expect.
- If you produce evidence records, cite the harness manifest as the record's
  `result_artefacts` entry. A Kani record without one is not decided from its
  log.
- Run `make check-fmt`, `make lint`, and `make test` before committing; all
  three now iterate the profiles rather than building one.

[adr-0005]: adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md
