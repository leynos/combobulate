# Architectural decision record (ADR) 0010: Workspace crate boundaries and build profiles

## Status

Accepted on 2026-10-22: a facade over a `#![no_std]` semantic kernel and an
empty procedural-macro crate, with Polars behind a crate-private module and a
default `polars` feature; dependency edges point one way; each gate profile is
its own Cargo invocation; and ToR Q3 is answered with a supported-toolchain set
rather than a single minimum-supported Rust version (MSRV). Records D16 and
resolves the candidate subjects CA3 (backend and cell separation) and CA5
(shared semantic kernel) in the [decision register](../decision-register.md).

## Date

2026-10-22.

## Context and problem statement

Technical design §3 proposes three crates: a facade, a procedural-macro crate,
and a small `combobulate-kernel`. It also says the kernel imports neither
Polars nor glam, and that the default facade features enable macros and Polars
while native-only execution remains available without Polars. None of that was
decided: CA3 and CA5 were deferred to task 1.2.1, and ToR Q3 asks which Rust
and feature matrix forms the baseline.

Two things forced the question now rather than later. First, B01 hypothesizes
that one dependency-light kernel can serve production, `const`-evaluated,
Kani-checked, and Verus-verified execution, and the kernel's dependency set is
the precondition for that claim to be testable at all. Second, a facade with a
Polars dependency changes what every gate and every hosted job must build, so
the feature profiles and the tools that consume them have to be decided
together. A record that named a single MSRV would not answer Q3: this
repository builds ordinary crates with one toolchain and proof subjects with
two others that ship their own pinned compilers, and no single MSRV describes
that.

## Decision drivers

- The kernel's dependency set must be empty in this task, so B01's claim about
  shared executable semantics is testable rather than assumed.
- Ordinary consumers must not need a verifier installed, and a native-only
  consumer must not compile Polars.
- A pinned version must agree everywhere it appears, or the record that pins it
  is worse than no record.
- A gate profile must be its own Cargo invocation, so feature unification cannot
  let one profile mask another.
- CI must keep a cold-cache job inside its timeout, which the Polars dependency
  makes non-trivial.
- Every claim about a capability needs a committed log, not a recollection.

## Requirements

### Functional requirements

- The kernel exposes checked shape, index, cost, and admission rules shared by
  runtime, `const` evaluation, and verification.
- The facade re-exports supported adapters behind features; a consumer chooses
  the profile by choosing features.
- Native-only execution stays available without Polars.

### Technical requirements

- The kernel is `#![no_std]` without `alloc` and declares no dependency in this
  task (DL-04).
- The kernel never appears in a build-dependency edge or in a procedural-macro
  crate's closure (VO-2).
- The macro crate depends on neither the kernel nor a backend.
- Every pinned revision agrees across every site that names it (VO-7).
- A capability claiming an observation cites a committed log by path and
  SHA-256 (VO-8).

## Options considered

### Option A: A separate `combobulate-polars` adapter crate

Move the Polars code into its own crate, so the facade depends on it only when
the feature is enabled.

It saves no CI time, because the default build still pulls Polars through the
facade. It contradicts the three-crate arrangement in technical design §3. It
would also force a premature `combobulate-core` split as soon as the adapter
needs facade-owned traits, moving every boundary the workspace tests assert.

### Option B: A crate-private facade module behind the feature

Keep the Polars code in `src/polars_backend.rs`, compiled only under
`cfg(feature = "polars")`, and enforce confinement with a workspace test
(VO-14) rather than with a crate boundary.

This keeps the three crates of technical design §3, keeps the default build
honest, and gives one place to revisit when task 1.2.6 or 4.2.1 needs
facade-owned traits inside the adapter.

### Option C: Defer the Polars dependency to task 1.2.6

Remove the dependency from this task entirely. This contradicts the task's own
success criterion, which requires a Polars-enabled build to exist and be gated.

| Topic               | A: adapter crate | B: private module | C: defer         |
| ------------------- | ---------------- | ----------------- | ---------------- |
| CI cost, default    | unchanged        | unchanged         | lower now, later |
| Number of crates    | four             | three             | three            |
| Adapter confinement | crate boundary   | feature + VO-14   | not applicable   |
| Task success        | met              | met               | not met          |
| Later `core` split  | forced early     | when needed       | when needed      |

_Table 1: Comparison of the crate-boundary options._

## Decision outcome

Option B is accepted.

The kernel is `#![no_std]` without `alloc` and declares no dependency. Its one
item in this task is `TargetFacts`, which reports the target's `usize` width as
a constant evaluated for the compilation target, never the host's pointer width.

The workspace has three crates. `combobulate` is the facade and workspace root
package. `combobulate-kernel` is dependency-free. `combobulate-macros` is the
procedural-macro crate. The Polars adapter is a crate-private module inside the
facade, behind `cfg(feature = "polars")`.

The facade's features are `default = ["macros", "polars"]`,
`macros = ["dep:combobulate-macros"]`, and `polars = ["dep:polars"]`. The
`polars` dependency selects `0.55.2` with `default-features = false` and
`features = ["lazy"]`, matching the calibrated EP-M1 probe.

### Gate feature lists

Four profiles are recorded in `spec/toolchain-profiles.json`:

- `native-only` builds the facade and kernel with `--no-default-features`, and
  runs the Clippy, nextest, and doctest gates in its own Cargo invocation.
- `polars-enabled` builds the facade, kernel, macros, and Polars with default
  features, and runs the same three gates in a second invocation.
- `proof-kani` compiles the Kani corpus with Kani 0.67.0's pinned toolchain. No
  shipped crate builds with it.
- `proof-verus` verifies the Verus wiring probe with Verus 0.2026.09.06.8dea4a2
  on Rust 1.98.0 and Z3 4.16.0.

`make` selects them with `GATE_PROFILE`, defaulting to `both`. Each profile is
its own Cargo invocation precisely so feature unification cannot let one
profile mask another.

`make` also accepts `macros-only` and `polars-only`. Neither is a record in
`spec/toolchain-profiles.json`, because neither pins a toolchain: each is one
of the two build profiles above with a different feature selection. Both are
absent from `GATE_PROFILE=both`; see the addendum below for why they exist and
why that lane omits them.

### The supported-toolchain set (Q3)

Q3 asks for a Rust/MSRV and feature matrix. The record answers it with a set,
because this repository has three toolchains with distinct roles:

- `rustup:nightly-2026-11-06` (rustc 1.101.0-nightly) is the only ordinary
  build toolchain. It compiles, lints, tests, and documents every shipped crate.
- `nightly-2025-11-21` (rustc 1.93.0-nightly) is Kani 0.67.0's pinned
  toolchain. It compiles harness subjects only.
- `1.98.0` is Verus's pinned Rust. It compiles and verifies proof subjects only.

Exactly one member of the set is `ordinary`. A downstream consumer needs only
that one.

### Verus wiring

The selected wiring is the estate's single-root pattern (DL-22): production
source carries `cfg_attr(verus_keep_ghost, …)` specification attributes that
are inert in ordinary builds, and a proof root under `verus/` imports the
production module with `#[path]`, run by `prover-tools verus run --proof-file`.
Verus compiles the same production source rather than a mirror of it, and adds
no dependency to the kernel.

### Proof-dependency allowlist

Task 1.2.4 admits proof dependencies only through this allowlist. A crate not
on it cannot appear in the kernel's closure:

- `vstd` at its Verus-pinned release, for specification vocabulary.
- Verus built-ins, which are language items rather than crates.
- Kani's `kani` crate, in `proof-kani` subjects only, never in the kernel.

`glam` stays opt-in and never enters the kernel.

### How B01 can still be falsified

This ADR does not claim B01. Task 1.2.4 attempts the falsification: if the
selected language and toolchain subset needs an unproved substitute executable
body, a trusted whole-executor axiom, or proof costs above the pre-registered
limits, then B01 is falsified and the kernel representation or the certified
subset is narrowed before stabilization. The decision rule forbids hiding a
duplicate checker or abandoning the proof-first requirement instead. Recording
that route here is what keeps CA5's link to B01 explicit.

### Pin consistency

Every pin is recorded once, in `spec/toolchain-profiles.json`, together with
the sites that assert it. Two checks hold the record to its word. Each pin with
an unambiguous owning file is re-derived from that file and compared. The
tracked tree is then swept for each literal pin value, and a file that names a
pin without being listed fails the check. A site list maintained by hand would
shrink to whichever files a change happened to touch; the sweep is what stops
that.

## Goals and non-goals

- Goals:
  - Keep the kernel's dependency set empty so B01 is testable.
  - Keep a native-only consumer free of Polars.
  - Make every gate profile independently built and independently reported.
  - Make every pin and every capability claim checkable from the repository.
- Non-goals:
  - Publishing separate crates; the facade sets `publish = false`.
  - Claiming B01, or any proof obligation, in this task.
  - Deciding the resource-certification or input-control subjects (CA7, CA8).

## Migration plan

1. Land the three crates and the facade features, and make both ordinary
   profiles build and pass their gates.
2. Land `spec/toolchain-profiles.json` with its schema and VO-7/VO-8 checks.
3. Land this ADR and D16 in the register, D16 accepted on the sponsor's
   2026-10-22 answer.
4. Make the CI shape match the profiles: a native-only `build-test`, parallel
   Polars-enabled lint and test jobs, and coverage measuring native-only.
5. Task 1.2.4 adds the proof-dependency allowlist check and attempts B01's
   falsification.

## Known risks and limitations

- Polars churn. The pin is a caret requirement, and Dependabot is told to ignore
  `polars*`, so an upgrade is a deliberate edit that must update every site the
  record names. The sweep will report any site left behind.
- The Kani bundle download is not verified against a digest by this repository.
  `trusted_computing_base` records that explicitly so no reader mistakes it for
  an audited input.
- The Polars adapter lives inside the facade. If task 1.2.6 or 4.2.1 needs
  facade-owned traits in the adapter, Option A is revisited rather than reached
  for by default.
- A cold-cache Polars job is slow. CI sizing uses hosted measurements of the
  real facade, not of the earlier probe crate.

## Outstanding decisions

- Acceptance of the AC-04 amendment, which registers the amended workload
  before EP-M6 measures.
- The final job sizing for the parallel Polars-enabled jobs, from hosted
  measurements of the facade.

## Addendum: the single-feature gate profiles (2026-11-11)

The "Gate feature lists" section above originally listed two build profiles and
two proof profiles. It now also records `macros-only` and `polars-only` as
`make`-only gate profiles.

This is not a decision that changes the ADR's outcome. It records the defect
that motivated the addition, so a later reader does not delete the two profiles
as redundant. Every shipped route before this change turned `macros` and
`polars` on together or off together: `native-only` has neither and
`polars-enabled` has both. `src/profile.rs` reads each flag separately with
`cfg!(feature = ...)`, so a swap of the two — `has_macros` reporting the Polars
flag and `has_polars` reporting the macro flag — would satisfy both existing
routes. No test could have distinguished a correct implementation from that one.

The repair has three parts. `make` now accepts `GATE_PROFILE=macros-only` and
`GATE_PROFILE=polars-only`, each running the existing per-profile loops with
the single feature selected. `tests/build_profiles.rs` binds one BDD scenario
per route, each gated on the exact feature pair it describes, so a build with
exactly one feature asserts that the report names that feature and not the
other. Each route snapshots its rendered line.

The two new profiles are deliberately absent from `GATE_PROFILE=both`. The
hosted pull-request lane measures the AC-07 build budgets against the two jobs
`both` runs, and adding a cold Polars build for `polars-only` to the same job
would spend them. They are the isolation check for a change that touches either
flag, not a second pull-request lane.

`spec/toolchain-profiles.json` still records four profiles, because a profile
there pins a toolchain and neither single-feature build pins a different one.
