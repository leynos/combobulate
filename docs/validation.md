# Combobulate document-pack validation

Revision 0.2. Checked: 6 October 2026. Scope: the Markdown, JSON declarations
and Python documentation models in this pack, not a Combobulate implementation.
[Machine-readable results](validation-results.json)
record the executed checks.

## Checks performed

The checker parses Markdown and verifies one title, fenced-block structure and
code widths, local links, source-register IDs and basic whitespace rules. It
compares the language-reference and bet Markdown with their JSON masters, and
requires `spec/roadmap.json` to equal a fresh export of the canonical
`docs/roadmap.md`. It validates unique IDs, requirement/goal/task mappings,
all-open task status and an acyclic earlier-dependency graph.

The pack contains 148 catalogue entries, 72 roadmap tasks, 11 requirements, 20
verification categories, 14 named proof obligations, eight testable bets and
nine planned backend capability probes. Every task carries a proof-first
contract and bet reference. All 19 numbered technical-design sections have task
references. This is structural coverage, not evidence that implementation is
complete or every theorem is proved.

The kernel-contract schema and planned sample validate. Removing mandatory
validity metadata fails. The scoped proof-evidence schema and planned example
also validate. Missing success witnesses, a claimed proof without actual
bindings/results, and unscoped trusted status fail their negative controls.
Schema validity checks the declaration, not the truth of its contents.

A separate small Python documentation model evaluates the original 20 semantic
cases, including right/left association, empty frames/cells, nulls, broadcasts,
shape constraints and row-aware neighbourhoods. Deliberately wrong association
and flattened-row-neighbour logic produce different outcomes. These examples do
not implement or verify the future Rust evaluator.

Fourteen additional documentation cases check exact/bounded/estimated/unknown
admission, target-width and zero cardinality, exact-prefix work and distinct
backing-allocation accounting. Negative controls distinguish a bound from an
exact excessive value, reject unknown-as-zero, expose alias double-counting and
separate 32-bit from 64-bit arithmetic. They are arithmetic checks in Python,
not Rust constant evaluation or a proof of analyser soundness.

The editing pass reconciled the two-crate proposal, preparation-only costing,
release-scope descriptions, public API catalogue and verification methods with
the new requirements. Original task and catalogue IDs remain unchanged. No
task, proof obligation or backend capability gained a fabricated completed
status.

## Reproduction

From the repository root:

```bash
python -m pip install -r tools/requirements.txt
python tools/generate_reference.py --check
scripts/export_roadmap.py --check
python tools/generate_bets.py --check
python tools/check_docs.py
```

The generators update only their marked Markdown regions when called without
`--check`; the roadmap exporter instead rewrites `spec/roadmap.json` from
`docs/roadmap.md`. By default, the checker verifies that the committed
`docs/validation-results.json` matches checks recomputed in memory. It rejects
invalid, stale or falsified reports without changing files. To regenerate the
report after a deliberate source change, run:

```bash
python tools/check_docs.py --write
make design-check
```

Review the report diff before committing it. Regeneration writes the report
only after all source checks pass. The supplied Python helpers do not invoke a
compiler, verifier or backend.

## Unrun checks and limits

No Combobulate implementation exists in the supplied pack. Rust compilation,
doctests, macro UI tests, actual const-evaluated cost admission, Kani/Verus
verification, external proof-consumer builds, optimized/reference execution,
Polars engine/spill/capability probes, Miri, numerical/performance
measurements, and trasic adoption remain unrun.

The design-model report does not claim repository Markdown lint or Rust CI
results. The repository runs those gates separately. The imported design has no
Mermaid diagrams; the inherited developer guide has build-route diagrams, which
`make nixie` checks independently.

Official technical pages and df12 skill files informed drafting through the
available web and GitHub tools. Some final Polars release/upgrade refreshes
failed, as recorded in [the source register](references.md). The offline
checker does not validate remote URLs. Exact implementation-time
dependency/profile selection and capability probes remain mandatory.

The repository bootstrap imports this pack and records its provenance in the
[bootstrap decision](adrs/adr-0001-repository-bootstrap.md). Its design check
also runs focused validator regressions through `make design-check`. Repository
integration does not change the planned status of product tasks, proofs, or
backend probes.
