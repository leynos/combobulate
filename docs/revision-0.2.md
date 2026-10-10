# Combobulate revision 0.2 change summary

Date: 6 October 2026. Status: proposed design update. This revision updates the
five requested documents and their generated masters; it does not implement the
library or claim a verifier result. The original 0.1 archive remains unchanged.

## Required changes and where they live

| Request                                       | Normative design                                                                                                                        | Delivery/evidence path                                                                                                                       |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Proof first with Verus or Kani as appropriate | Technical design §§14 and 17; ToR C7, G7, S8/S10; requirements R8/R9.                                                                   | Every task has a proof-first obligation. PF01-PF14 name claims, methods, scopes and non-vacuity controls. B01/B02/B07/B08 govern acceptance. |
| Easier verification of consumer code          | Public collection/graph models, checked views, source-bound witnesses, callable/reducer contracts and explicit native execution in §17. | External Kani and Verus fixture crates use public APIs and real comb! calls before proof-API stabilization.                                  |
| Compile-time costing                          | Shared static/preparation/runtime analyser, typed cost confidence, residual checks and scoped schedule certificates in §18; R10.        | B03/B04 and tasks 2.4.1-2.4.3, 3.3.3, plus early shared-kernel probe 1.2.4.                                                                  |
| Polars 2 readiness                            | Capability-based Rust adapter with explicit engine/order/I/O policy in §19; R11.                                                        | PC01-PC09 and B05/B06; task 1.2.6 probes actual interfaces before optional adoption.                                                         |
| Testable roadmap bets                         | Each bet has a success witness, negative control, falsifier, measurements and a decision rule.                                          | Eight generated bets linked to the 72 open tasks; proof work remains inside vertical slices.                                                 |

The technical design now has 19 numbered sections. Its existing architecture,
API, planning, resource, verification and handoff sections refer to and conform
to the new contracts, rather than leaving contradictory old rules beside an
appendix. The context glossary and language-reference interfaces use the same
terms and scope distinctions.

## Important design decisions

The package boundary changes from a facade plus macro crate to those crates
plus an internal semantic kernel. The early bet must demonstrate executable
correspondence across ordinary Rust, constant evaluation, Kani and Verus. A
second unchecked “equivalent” checker is not an acceptable shortcut.

Proof-capable APIs expose logical meaning without publicizing storage or IR
internals. They specify successful results, success conditions and
failure/frame behaviour. Safe runtime constructors retain validation for
unverified callers. A proof configuration cannot silently replace the
production executor. Models, contracts and lemmas participate in compatibility
review.

Cost reports distinguish exact quantities, conservative bounds, estimates and
unknowns. A 128 MiB exact result cannot pass a 64 MiB payload budget; a 128 MiB
upper bound alone means the whole input domain cannot be certified, not that
every invocation must exceed the limit. Certificates bind actual semantic,
schedule, target and capability assumptions. They do not certify process RSS or
arbitrary backend allocations.

Polars integration uses actual Rust capability probes, not a `polars = "2"`
assumption. The default policy forbids unrequested temporary-disk effects. An
unenforceable strict no-spill guarantee fails admission; process-global
settings cannot pretend to provide per-query isolation. Optional
dtype/plugin/provenance hooks need both conformance and an explicit
benefit/disposition decision.

## Deliberately unchanged

`comb! { input |> stage }`, `arr!`, ordinary builders, graph reuse, typed-cell
atomicity, exact reduction/scan semantics, explicit broadcasting, true masking,
and the native/glam boundary remain intact. No `a!` replacement or mandatory
shape-generic tower enters the public frontend.

The original 52 roadmap task IDs and 132 catalogue IDs remain stable. This
revision adds 20 tasks and 16 interface entries. All task checkboxes remain
open. The 20 existing semantic examples retain their semantics; 14 additional
cost examples check documentation arithmetic and admission distinctions.

## Evidence and remaining decisions

The [validation report](validation.md) records actual document checks. Kani,
Verus, Rust compile-time evaluation, backend capability/spill probes,
benchmarks and real trasic integration remain unrun. Every proof and capability
record reflects that status.

The final refresh of several Polars release/upgrade pages failed; the source
register preserves that limitation. This does not block a forward-looking
contract: every such capability already requires a pinned Rust probe before it
can become eligible. No API availability or measured benefit is inferred from
the earlier discussion or a release label.

The implementation still needs exact tool/dependency/target profiles,
quantitative proof/build/performance controls, exception/release authority, and
a publication destination. These are open ToR decisions and early roadmap
tasks, not invented approvals. A change can narrow an optional optimization,
but cannot turn missing evidence into a passing proof-required route.
