# Establish the workspace and pinned profiles (roadmap 1.2.1)

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: DRAFT. The plan awaits sponsor approval. No implementation milestone
may begin until the sponsor approves this plan and answers the open decisions
listed under `Decisions requested at approval`.

## Purpose / big picture

Roadmap task 1.2.1 turns the single scaffold crate into the package arrangement
that the technical design proposes: a facade library, a procedural-macro crate,
and a small internal semantic kernel. It also pins every compiler, verifier,
solver, and backend revision that later proof and backend work will rely on,
and it records what each pinned tool can and cannot do before any claim depends
on it.

The roadmap phase idea is that one small executable semantic kernel can serve
ordinary Rust, constant evaluation, Kani, and Verus. Task 1.2.1 does not test
that idea; task 1.2.4 does. Task 1.2.1 builds the ground on which that test can
be run honestly: a kernel crate that cannot import Polars or glam, profiles
whose features and toolchains are recorded exactly, and an evidence gate that
can at last admit a verifier verdict, because a verifier log parser exists and
has been tested against real logs.

After this work a reviewer can do the following, none of which is possible
today:

1. Depend on the facade with `default-features = false` and build a native-only
   programme whose dependency graph contains no Polars, glam, Kani, or Verus
   package. Running `cargo run --example build_profile --no-default-features`
   prints a profile line that reports no Polars backend.
2. Build the default profile, which enables the `macros` and `polars` features
   and compiles a crate-private Polars module against the pinned Rust Polars
   release, independent of the Python Polars 2 version label.
3. Ask Cargo for the kernel's dependency graph under every feature and target
   selection and see only `combobulate-kernel` itself.
4. Read `spec/toolchain-profiles.json`, which records the exact Rust nightly,
   Kani, CBMC, Verus, Z3, `vstd`, Polars, and target revisions, each profile's
   features and commands, every probed tool capability with a status of
   documented, tested, unsupported, or inconclusive, and each tool's trusted
   computing base. `make design-check` fails when any other pin in the
   repository disagrees with that record.
5. Run `make install-proof-tools` to obtain the pinned Kani and Verus releases
   through checksum-verified downloads, while ordinary builds and every
   ordinary Make gate continue to pass on a host with neither tool installed.
6. Run `python3 scripts/check_evidence.py` over an evidence record that cites
   a committed Kani log and see the gate re-derive its verdict through the
   registered `kani` log parser. A timeout, an unsatisfied cover, and a skipped
   harness each produce their own rejection reason, using logs that the pinned
   Kani actually emitted.
7. Run `python3 scripts/trust_audit.py crates` and see every occurrence of the
   ADR-0009 trusted-item vocabulary in code position reported, while the same
   words in comments and string literals are not. `make design-check` requires
   the shipped crates to contain no uncovered trusted item.

Compile-only evidence is not a theorem. Nothing in this task claims a proved
property of Combobulate itself. The capability records say what the tools did
on probe fixtures; the profile builds say what compiled; the parser and scanner
are tested gate components. Task 1.2.4 makes the first proof claim.

## Decisions requested at approval

The sponsor (`leynos`, the D01 authority) is asked to settle these before
implementation begins. Each has a recommended option; the full trade-offs are in
`Decision log`.

1. CI shape for the Polars-enabled profile (DL-03). Recommended: split the
   Polars-enabled lint and test routes into parallel hosted jobs sized from the
   EP-M1 measurements, and amend control AC-07 so that its workload is the
   slowest required pull-request job rather than `build-test` alone.
2. The empty macro crate (DL-05). Recommended: create `combobulate-macros` now
   with no exported macro and no dependency, wired through a default `macros`
   feature that the users' guide describes truthfully as reserved until task
   2.3.1.
3. Which verifier parser task 1.2.1 registers (DL-07). Recommended: register
   only the Kani parser here, because the roadmap's three named log classes are
   Kani outcomes; the Verus parser stays with task 1.2.4.
4. Resolution of candidate ADR subjects CA3 and CA5 and of ToR Q3 (DL-02).
   Recommended: a new decision D16 accepting ADR-0010, which records the crate
   boundary, the feature profiles, and the supported-toolchain set in place of
   a single minimum supported Rust version (MSRV).
5. PR title numbering (DL-12). The request asked for `(1.1)` in the title, but
   this task is roadmap item 1.2.1. The draft PR uses `(1.2.1)`; the sponsor
   may ask for the literal `(1.1)` instead.

## Constraints

- The semantic kernel `combobulate-kernel` must import neither Polars nor glam
  under any feature or target selection (technical design §3, roadmap 1.2.1).
- Ordinary consumers must not need Kani, Verus, Z3, or any verifier
  installation to build, test, or use any ordinary profile (ToR line 152,
  technical design §§3, 17.7).
- The Polars dependency is selected by its Rust crate release and tested
  public interface, never by the Python Polars 2 version number (technical
  design §19.1, context.md line 230, ToR Q9).
- Proof support must not use `cfg(kani)` or a proof feature to replace a
  production body with a different implementation (technical design §17.7).
- The pinned Kani 0.67.0, Verus 0.2026.09.06.8dea4a2, and Z3 4.16.0 revisions
  are part of the pre-registered environment of controls AC-01, AC-02, AC-04,
  and AC-07. Changing any of them requires a sponsor-approved control amendment
  under ADR-0008; newer releases (for example Kani 0.68.0) are not adopted by
  this task.
- Every hosted `build-test` attempt counts towards AC-07, and any failed,
  timed-out, or cancelled attempt fails that control independently of its 90th
  percentile. No commit may be pushed whose `build-test` duration has not been
  predicted, from local measurement, to stay within the 8-minute hard timeout
  with at least 25% headroom.
- The repository remains unpublished: every workspace member keeps
  `publish = false` and the ISC licence (D04, D05, ADR-0004).
- Pre-1.0 policy (D06, ADR-0005): no aliases, deprecated entry points, or
  shims. The disposable `greet()` stub is removed rather than preserved.
- A verifier log parser may be registered in
  `spec/evidence-reason-codes.json` only after its tests over real logs,
  including a timeout, an unsatisfied cover, and a skipped harness, pass
  (roadmap 1.2.1 detail, D15).
- The evidence gate stays pure: `AdmissionContext` receives parsed log
  results from an I/O shell and never reads files, the clock, or the
  environment (technical design §17.2, ADR-0009).
- Production code must not read environment variables outside a composition
  root; `clippy.toml` already disallows the `std::env` accessors (AGENTS.md).
- No `assume`, `admit`, `external_body`, Kani stub, or equivalent may appear
  in shipped crates. Probe fixtures may contain them only as labelled scanner
  or parser test subjects.
- No code file may exceed 400 lines; Markdown wraps at 80 columns; prose uses
  en-GB-oxendict spelling (AGENTS.md).
- Completed ExecPlans, including
  `docs/execplans/1-1-resolve-acceptance-control-decisions.md`, are historical
  and must not be edited.

## Tolerances (exception triggers)

- Scope: stop and escalate if the implementation needs more than 90 changed
  files or more than 4,500 net added lines excluding committed verifier logs,
  `Cargo.lock`, and generated exports.
- Interface: stop if any public item beyond `BuildProfile`, `TargetFacts`, and
  the three Cargo features named in `Interfaces and dependencies` seems
  necessary.
- Dependencies: stop before adding any dependency not listed in
  `Interfaces and dependencies`, or a version other than the one listed.
- Toolchain capability: stop if Kani or Verus cannot process a workspace member
  under the repository's Cargo configuration without either a configuration
  change that weakens the ordinary build standard or a substitute body. That
  outcome is a B01 falsifier candidate and needs a representation decision, not
  a workaround.
- Budgets: stop if any EP-M1 measurement predicts that a hosted required job
  would exceed 6 minutes cold, if the AC-04 acceptance measurement fails a
  ceiling, or if a Kani or Verus probe exceeds its AC-01 or AC-02 budget.
- Iterations: stop if a gate still fails after three fix attempts on the same
  cause.
- Ambiguity: stop and present options when a choice materially changes a
  public interface, a trust boundary, or a pre-registered control.

## Risks

- Risk: cold Polars builds push the hosted `build-test` job past its 8-minute
  hard timeout, failing AC-07. Calibration measured a 163-second median cold
  Cranelift build locally (range 60-382 s), and the job builds dependencies
  separately for rustdoc, Clippy, Whitaker, and LLVM coverage. Severity: high.
  Likelihood: high if Polars joins every route. Mitigation: EP-M1 measures each
  route cold with four jobs; DL-03 selects a job shape before any push; no CI
  attempt runs until the prediction fits.
- Risk: the Verus driver, built on Rust 1.98.0, rejects the repository's
  nightly-only Cargo configuration (`[unstable] codegen-backend`, Cranelift in
  `[profile.dev]`, `-Zthreads=8`, the `mold` linker wrapper). Severity: high.
  Likelihood: medium. Mitigation: EP-M1 probes `cargo verus` in place and
  records the finding; any override must be scoped to the verifier route and
  must leave ordinary gates unchanged, or the tolerance triggers.
- Risk: the three compilers that must accept the kernel differ: the repository
  nightly (1.100.0-nightly, 2026-08-26), Kani 0.67.0's bundled
  nightly-2025-11-21, and Verus's Rust 1.98.0. Language or lint features newer
  than the oldest of them break the proof routes. Severity: medium. Likelihood:
  medium. Mitigation: EP-M1 records `rustc -vV` for each; the kernel restricts
  itself to the intersection; workspace `[lints.rust]` entries are checked
  against each toolchain because `unknown_lints = "deny"` turns a newer lint
  name into an error.
- Risk: making the root package a workspace root turns the path
  dev-dependency `tools/calibration/cardinality-probe`, which has its own
  `[workspace]` table, into an implicit member and fails resolution. Severity:
  medium. Likelihood: high. Mitigation: `exclude = ["tools"]` in the root
  `[workspace]` table, tested in EP-M2.
- Risk: repository contract tests (`tests/make_gate_order.rs`,
  `tests/make_cargo_routes.rs`, `tests/build_standard_contract.rs`) assert
  exact Cargo argument vectors and break when routes change. Severity: medium.
  Likelihood: high. Mitigation: `default-members` keeps bare Cargo routes
  covering every member, so existing argument vectors stay valid; new routes
  get their own contract assertions in the same commit.
- Risk: the real Kani output format for a timeout or a skipped harness differs
  from what the parser design expects. Severity: medium. Likelihood: medium.
  Mitigation: the corpus is captured first (EP-M1) and the parser is written
  against it (EP-M5); unknown structure fails closed as `tool-error`.
- Risk: `rstest-bdd` 0.6.0 or `googletest` 0.14.3 requires an `rstest` release
  newer than the pinned 0.27.0. Severity: low. Likelihood: medium. Mitigation:
  check during EP-M3; an `rstest` bump to 0.28.0 is pre-authorized in
  `Interfaces and dependencies`, anything larger escalates.
- Risk: the Verus release archive is 456 MB, so a hosted verifier job is slow
  and download-bound. Severity: low. Likelihood: high. Mitigation: no Verus run
  on the pull-request critical path in this task; the hosted verifier workflow
  is manual-dispatch and cached by archive digest.
- Risk: the Z3 binary used during calibration lived under `/tmp` and is no
  longer reproducible from the repository. Severity: medium. Likelihood:
  certain. Mitigation: `make install-proof-tools` installs Z3 from the Verus
  release archive or a pinned, checksum-verified Z3 release, and the profile
  record names its source.
- Risk: the AC-04 hosted measurement fails a ceiling, most plausibly the
  10-minute Polars cold build. Severity: medium. Likelihood: low to medium.
  Mitigation: none by extension (AC-04 forbids it); a failure stops the task
  for a scope or implementation decision under technical design §17.8.

## Progress

- [x] (2026-10-22) Rename the branch to
  `1-2-1-establish-workspace-and-profiles` with upstream
  `origin/1-2-1-establish-workspace-and-profiles`.
- [x] (2026-10-22) Reconnaissance with a Wyvern team: tooling and Make routes,
  bets and decisions, documentation conventions.
- [x] (2026-10-22) External research: Verus release assets and `vstd`
  versions, Kani 0.67.0 assets and options, Polars 0.55.2 features, current
  crate versions.
- [x] (2026-10-22) Draft this ExecPlan.
- [ ] Community-of-experts design review and revision of this plan.
- [ ] Sponsor approval of the plan and of the decisions requested at approval.
- [ ] EP-M1. Prototype: toolchain and profile capability probes.
- [ ] EP-M2. Workspace, crate boundaries, and dependency-direction checks.
- [ ] EP-M3. Feature profiles, `BuildProfile`, and profile behaviour tests.
- [ ] EP-M4. Profile record, pin consistency, proof-tool installation, ADR.
- [ ] EP-M5. Trust-audit scanner and Kani log parser; parser registration.
- [ ] EP-M6. CI profile jobs, AC-04 measurement, documents, and roadmap tick.

## Surprises & discoveries

- Observation: Kani 0.68.0 and newer `vstd` releases exist, but the
  pre-registered controls name Kani 0.67.0 and Verus 0.2026.09.06.8dea4a2.
  Evidence: `cargo search kani-verifier` reports 0.68.0; AC-01, AC-02, AC-04,
  and AC-07 environments list the older pins. Impact: the pins stay; upgrading
  is a control amendment, not part of this task.
- Observation: Kani's `--harness-timeout` exists in 0.67.0 but is experimental
  and requires `-Z unstable-options`. Evidence: `cargo kani --help`. Impact:
  the timeout corpus case uses that flag, and the capability record marks it
  `tested` with an experimental qualifier rather than as a stable interface.
- Observation: the Verus binary used for calibration is a local source build
  under `~/.local/share/cuprum-verus-0.2026.09.06.8dea4a2`, and no Z3 binary is
  installed outside `/tmp`. Evidence: `verus --version` and a filesystem
  search. Impact: proof-tool installation must be scripted from release assets
  before any probe result is reproducible.
- Observation: the published `vstd` release dated 2026-09-06
  (`0.0.0-2026-09-06-0133`) is the candidate match for Verus
  0.2026.09.06.8dea4a2, but date proximity is not identity. Evidence: crates.io
  version list. Impact: EP-M1 must confirm the match from the release contents
  before the profile record names it.
- Observation: Polars 0.55.2 is the newest Rust release and declares no
  `rust-version`. Evidence: `cargo info polars@0.55.2`. Impact: its supported
  compilers are established only by building it in each profile.

## Decision log

- DL-01. Decision: the root package remains the `combobulate` facade and also
  becomes the workspace root, with members under `crates/`. Rationale: the
  repository contract tests in `tests/` already belong to the root package, and
  the Make routes, coverage, packaging, and Whitaker contracts are written
  against it. A virtual root would move every one of those tests for no
  semantic gain. `default-members` lists all three packages so bare Cargo
  routes cover the whole workspace and existing argument vectors stay valid.
  Date/Author: 2026-10-22, planning agent.
- DL-02. Decision (proposed, needs sponsor acceptance as D16): record the crate
  boundary, dependency direction, feature profiles, and supported-toolchain set
  in a new ADR-0010, resolving candidate subjects CA3 (backend and cell
  separation) and CA5 (shared semantic kernel), and answering ToR Q3 with a
  supported-toolchain set rather than one MSRV. Rationale: D07 deferred CA3 and
  CA5 to this task; D06 left the MSRV with Q3 and this task. The repository
  builds with a pinned nightly and the kernel must also compile under Kani's
  and Verus's own compilers, so a single `rust-version` number would
  misdescribe the contract. CA5 stays falsifiable by B01 in task 1.2.4; the ADR
  must say so. Date/Author: 2026-10-22, planning agent.
- DL-03. Decision (proposed, needs sponsor choice): CI shape for the
  Polars-enabled profile. Options: (A) one `build-test` job with Polars in
  every route, which risks the 8-minute hard timeout on every cold cache; (B)
  keep `build-test` on the native-only and macro features and add parallel
  Polars-enabled lint and test jobs sized so each is predicted at no more than
  6 minutes cold, with an AC-07 amendment so the control measures the slowest
  required job; (C) defer the facade's Polars dependency to task 1.2.6, which
  contradicts this task's success criterion. Recommended: B. Rationale: B keeps
  every profile linted and tested, keeps the critical path measurable, and
  avoids pushing attempts that are likely to fail AC-07. The local `make lint`
  and `make test` still run every profile, so the developer gate and the hosted
  gates cover the same routes. Date/Author: 2026-10-22, planning agent.
- DL-04. Decision: the kernel is `#![no_std]` without `alloc` and has no
  dependencies in this task. Its only item is `TargetFacts`, which reports the
  target's `usize` width as a constant evaluated for the compilation target.
  Rationale: technical design §3 asks the kernel to avoid unnecessary
  allocation and external state, and §18.1 forbids substituting the
  procedural-macro host's pointer width for the target's; `TargetFacts` is the
  kernel-owned home for target facts that later cost certificates and profile
  keys must carry. Allocation can be admitted later only by an ADR amendment.
  Date/Author: 2026-10-22, planning agent.
- DL-05. Decision (proposed, needs sponsor choice): `combobulate-macros` is
  created now as a `proc-macro = true` crate with no exported macro and no
  dependency; the facade's default `macros` feature enables it as an optional
  dependency. Rationale: the task requires the macro boundary to exist, and its
  feature wiring and build cost belong in the profile record and AC-04, but
  adding `syn` or a placeholder macro before task 2.3.1 would be speculative.
  The users' guide states plainly that the feature exports nothing yet.
  Alternative: defer the crate to 2.3.1, which narrows this task's stated
  scope. Date/Author: 2026-10-22, planning agent.
- DL-06. Decision: the macro crate must not depend on the kernel. Rationale:
  technical design §18.1 requires static cost checks to use the target's
  environment, and a procedural macro runs on the host, so host-side kernel
  evaluation would substitute host facts for target facts. The macro emits code
  that the target evaluates instead. Date/Author: 2026-10-22, planning agent.
- DL-07. Decision (proposed, needs sponsor choice): task 1.2.1 builds and
  registers the Kani log parser only; the Verus parser is built and registered
  by task 1.2.4. Rationale: the roadmap names a timeout, an unsatisfied cover,
  and a skipped harness, which are Kani outcomes; task 1.2.4 says it registers
  the Verus and Kani parsers "for this kernel's evidence". The trust-audit
  scanner covers both vocabularies now. Date/Author: 2026-10-22, planning agent.
- DL-08. Decision: the log parser and trust-audit scanner are Python modules in
  `scripts/docs_validation/`, beside the gate they feed. Rationale: the gate,
  `VerifiedLogResult`, and `AdmissionContext` are Python, and ADR-0009 keeps
  the Python gate as the reference model until task 1.2.4 replays it from Rust.
  Writing the adapters in Rust now would need a second gate binding.
  Date/Author: 2026-10-22, planning agent.
- DL-09. Decision: a skipped harness is defined against a committed harness
  manifest captured with `cargo kani list --format json`: any listed harness
  without a verification result in the log is skipped. Rationale: a log alone
  cannot show what it omits; the manifest makes absence observable and makes a
  filtered or interrupted run fail closed. Date/Author: 2026-10-22, planning
  agent.
- DL-10. Decision: the parser derives `bounds` from the committed harness
  manifest, which declares each harness as type-complete or partial, and
  cross-checks the log's unwinding-assertion results; a harness whose unwinding
  checks are absent or failed is never type-complete. Rationale: a Kani log
  does not state whether a harness's inputs span the whole type, so that
  declaration is a reviewed repository fact, recorded as axiom AXIOM-06.
  Date/Author: 2026-10-22, planning agent.
- DL-11. Decision: no glam feature is declared in this task. Rationale: glam is
  opt-in (technical design §3) and has no consumer until task 5.2.1; an
  unexercised feature would be an untested profile. The kernel dependency check
  forbids glam regardless. Date/Author: 2026-10-22, planning agent.
- DL-12. Decision (proposed): the draft PR title is
  `Plan: establish the workspace and pinned profiles (1.2.1)`. Rationale: the
  request asked for `(1.1)`, but this task is roadmap item 1.2.1 and earlier
  PRs used the number of the item they delivered. Date/Author: 2026-10-22,
  planning agent.
- DL-13. Decision: Verus is not used to prove any property in this task; it is
  exercised only as a capability probe. Rationale: task 1.2.1 introduces no
  contractual business logic in Rust. `TargetFacts` is a definitional constant,
  the profile report is plumbing, and the parser and scanner are Python. An
  artificial lemma would be the vacuous obligation the proof-first policy
  forbids. See `Verification plan`. Date/Author: 2026-10-22, planning agent.

## Outcomes & retrospective

Not yet started.

## Context and orientation

Combobulate is a proposed Rust library for inspectable array and
typed-collection algebra with a first-class Polars route and a proof-first
delivery discipline. Until this task, the Rust code is a scaffold: `Cargo.toml`
declares one package, `combobulate`, with no runtime dependency, and
`src/lib.rs` holds only a disposable `greet()` stub tested by `tests/stub.rs`.
The rest of `tests/` holds repository contract tests that check the Makefile,
the workflows, the toolchain pin, and the build standard, not library behaviour.

The repository's build standard pins `nightly-2026-08-27` in
`rust-toolchain.toml`, uses Cranelift for development builds and `mold` as the
linker through `scripts/native-clang-linker.sh` (configured in
`.cargo/config.toml`), and runs gates through the `Makefile`: `make check-fmt`,
`make lint` (rustdoc, Clippy, Whitaker, Python docstring coverage), `make test`
(nextest plus doctests), and `make design-check` (the Python design-contract
checker in `scripts/check_docs.py` and its tests under `scripts/tests/`).

The design-contract checker is the repository's governance machine. Decisions
live in `spec/decisions.json` and are rendered into
`docs/decision-register.md`. The roadmap in `docs/roadmap.md` is exported to
`spec/roadmap.json`; a task may be ticked only when its completion record in
`spec/task-completion.json` cites accepted decisions and resolvable artefacts,
and every linked proof-obligation component is satisfied (rule MS-4 in
ADR-0009). No proof-obligation component in `spec/proof-obligations.json` is
linked to task 1.2.1.

The evidence gate in `scripts/docs_validation/evidence_gate.py` abstracts a
proof-evidence record (schema version 2, `spec/proof-evidence.schema.json`) to
ten finite fields and admits it at a level: `proof`, `bounded`, `tested`,
`restricted`, or `rejected`. A verifier verdict counts as parsed, rather than
self-reported, only when a registered log parser supplies a matching
`VerifiedLogResult` for the record's tool, log path, and digest. The registry
`spec/evidence-reason-codes.json` currently registers no parser, so every
verifier record is rejected with `verdict-self-reported`. The test fixture
`scripts/tests/fixtures/evidence/log-parsers.json` pretends a Kani parser
exists so tests can reach the `bounded` level.

A calibration probe in `tools/calibration/cardinality-probe/` is a standalone
crate with its own `[workspace]` table. It was used to measure verifier and
build costs for the acceptance controls in `spec/acceptance-controls.json`. It
is not the shipped kernel and this task does not change it.

Terms used in this plan:

- Facade: the `combobulate` crate that consumers depend on. It re-exports
  supported items from the other crates behind features.
- Semantic kernel: `combobulate-kernel`, the small crate that will own checked
  shape, index, cost, and admission rules shared by runtime, constant
  evaluation, Kani, and Verus.
- Profile: a named combination of crate, features, toolchain, target, and
  command. This task defines four: native-only, Polars-enabled (the default),
  proof-capable Kani, and proof-capable Verus.
- Capability record: an entry stating what a pinned tool did on a probe, with
  a status of `documented` (stated upstream, not exercised), `tested`
  (exercised here and behaved as recorded), `unsupported` (exercised and
  refused or failed), or `inconclusive` (exercised without a decisive result).
  These are the four statuses roadmap task 1.2.6 uses for Polars.
- Trusted computing base (TCB): the components whose correctness a result
  assumes rather than checks, such as the compiler, the verifier, and the
  solver.
- Harness manifest: the JSON list of Kani proof harnesses that
  `cargo kani list --format json` reports for a crate, committed beside the
  logs it describes.

## Conformance basis

- Terms of reference: `docs/terms-of-reference.md`, revision 0.2 of 6 October
  2026, tracing G1, G2, G6, G7, G8; S7 (native-only, proof-capable, and
  Polars-enabled profiles within budgets); C1, C5, C7, C8; Q3 (MSRV and feature
  matrix); Q9 (verification profiles; no Rust feature inferred from Python
  numbering); the dependency-baseline requirement at line 223.
- Technical design: `docs/technical-design.md`, revision 0.2, 6 October 2026.
  Traced items: §3 package boundary and component table; R5, R7, R8; §10
  storage and Polars; §15 row 6 (facade, macro, and kernel crates), GAP4, GAP7,
  GAP8, GAP9; §17.1, §17.2 (trust audit and verdict parsing), §17.7 (profiles;
  no proof-feature body substitution), §17.8 (pinned tools, CI cost); §18.1
  (target facts, not host facts); §19.1 (Rust release selected independently of
  Python numbering).
- Roadmap: `docs/roadmap.md` revision 0.2, task 1.2.1 and its detail on the
  trust-audit scanner and log parser; dependants 1.2.2, 1.2.4, 1.2.6.
- Bets: B01 (one executable semantic core), B05 (streaming Polars contract),
  in `docs/testable-bets.md`.
- Decisions: D04, D05 (licence, publication), D06 (pre-1.0 API, MSRV left to
  Q3 and 1.2.1), D07 (CA3 and CA5 deferred to 1.2.1), D11, D12 (controls), D15
  (parsers and scanner in 1.2.1 and 1.2.4); proposed D16.
- ADRs: ADR-0004, ADR-0005, ADR-0008, ADR-0009; proposed ADR-0010.
- Controls: AC-01, AC-02 (verifier budgets, for the probes), AC-04 (build
  budgets for the three profiles, task 1.2.1), AC-07 (pull-request critical
  path, task 1.2.1).
- Governing standards: `AGENTS.md`, `docs/documentation-style-guide.md`,
  `docs/developers-guide.md`, `docs/scripting-standards.md`.

Trace chains:

```plaintext
TD §3, §15 row 6, CA5 -> D16/ADR-0010 -> EP-M2 -> tests/workspace_boundaries.rs::kernel_closure_is_self_only
TD §3, ToR line 152 -> EP-M2, EP-M3 -> tests/workspace_boundaries.rs::ordinary_profiles_exclude_verifiers
ToR S7, TD §3 -> EP-M3 -> tests/features/build_profiles.feature -> make check-profiles
TD §19.1, ToR Q9, B05 -> EP-M3, EP-M4 -> spec/toolchain-profiles.json -> scripts/tests/test_toolchain_profiles.py
ToR Q3, D06 -> D16/ADR-0010 -> EP-M4 -> spec/toolchain-profiles.json::supported_toolchains
TD §17.2, ADR-0009, D15 -> EP-M5 -> scripts/docs_validation/kani_log.py -> scripts/tests/test_kani_log.py
TD §17.2, ADR-0009 vocabulary -> EP-M5 -> scripts/docs_validation/trust_audit.py -> scripts/tests/test_trust_audit.py
AC-04 -> EP-M6 -> spec/measurements/ac-04-*.json
AC-07, DL-03 -> EP-M6 -> .github/workflows/ci.yml profile jobs
Roadmap 1.2.1 -> EP-M6 -> spec/task-completion.json -> ticked in docs/roadmap.md
```

Gaps addressed: GAP4 (exact Rust, dependency, and feature versions selected and
recorded; stable compilation claimed only for the recorded profiles); GAP9 in
part (a parser and the scanner exist). GAP7 and GAP8 stay open for tasks 1.2.4
and 1.2.6.

## Verification plan

### Method selection

This task introduces dependency-direction invariants, a profile-reporting
contract, a pin-consistency invariant, and two fail-closed gate adapters. None
is contractual business logic over unbounded Rust data, so no Verus proof is
warranted (DL-13). Each obligation below is either a finite fact about a
dependency graph or profile matrix, which an exact parameterized check
discharges, or a property of a Python adapter over arbitrary text, which
Hypothesis property tests plus a real-log corpus discharge. Kani and Verus
appear only as subjects of capability probes and as producers of the real logs
the parser is tested against.

The Rust test stack is `rstest` for fixtures and tables, `rstest-bdd` for the
profile behaviour scenarios, `googletest` matchers and `pretty_assertions`
diffs for clear failures, and `insta` for the rendered profile line across
profiles. The Python stack follows `scripts/tests/`: `unittest` cases run by
both `unittest discover` and `pytest`, with the pinned Hypothesis 6.168.5 for
properties.

### Obligations

- Obligation VO-1, kernel isolation: for every feature selection and for the
  default target, the normal and build dependency closure of
  `combobulate-kernel` is exactly `{combobulate-kernel}`.
  - Method: exact check over `cargo tree` output, parameterized by feature
    selection (`--no-default-features`, default, `--all-features`).
  - Artefact: `tests/workspace_boundaries.rs::kernel_closure_is_self_only`.
  - Evidence: `cargo nextest run --test workspace_boundaries`; red before
    EP-M2 because the package does not exist.
  - Non-vacuity: the same query run on the default facade must contain
    `polars` (VO-4), proving the query reports transitive dependencies. A
    seeded fixture manifest that adds `glam` to a copy of the kernel must fail
    the check with a message naming `glam`.
- Obligation VO-2, dependency direction: the macro crate depends on neither
  the kernel nor any backend; no member depends on the facade; the kernel
  depends on no member.
  - Method: exact check over `cargo metadata --format-version 1`.
  - Artefact: `tests/workspace_boundaries.rs::dependency_direction_holds`.
  - Non-vacuity: the facade's edges to both members must be observed, so the
    check cannot pass on an empty graph.
- Obligation VO-3, ordinary profiles exclude verifiers: in the native-only and
  default profiles, no package named `kani`, `vstd`, or `verus_*` appears in
  the facade's dependency closure.
  - Method: exact check, parameterized by profile.
  - Artefact:
    `tests/workspace_boundaries.rs::ordinary_profiles_exclude_verifiers`.
  - Non-vacuity: the hosted `build-test` job runs without Kani or Verus on its
    path, so a hidden verifier dependency would fail the build rather than
    pass silently.
- Obligation VO-4, native-only and Polars-enabled separation: the native-only
  facade closure contains no `polars*` package; the default closure contains
  `polars` at exactly the pinned version with exactly the selected features.
  - Method: exact check, two cases.
  - Artefact: `tests/workspace_boundaries.rs::polars_appears_only_when_enabled`.
  - Non-vacuity: the default case is the positive witness for the negative
    case.
- Obligation VO-5, profile report: `BuildProfile::current()` reports exactly
  the features compiled into the binary, and its rendered line is stable per
  profile.
  - Method: `rstest-bdd` scenarios selected by tag per profile, plus `insta`
    snapshots of the rendered line per profile, plus the example binary run by
    `make check-profiles` in each profile.
  - Artefacts: `tests/features/build_profiles.feature`,
    `tests/build_profiles.rs`, `examples/build_profile.rs`,
    `tests/snapshots/`.
  - Evidence: the `@native` scenarios run under
    `cargo nextest run --no-default-features --features macros`; the
    `@polars` scenarios run under the default profile. Red before EP-M3.
  - Non-vacuity: each profile's scenario asserts the absence of the other
    profile's backend, so a report that always claims Polars, or never does,
    fails one of the two runs. `rstest-bdd` errors when a tag filter matches
    no scenario, so an empty selection cannot pass.
- Obligation VO-6, target facts: `TargetFacts::current().usize_bits()` equals
  `usize::BITS` for the compilation target and is usable in constant context.
  - Method: unit test plus a `const` assertion in a doctest.
  - Artefact: `crates/combobulate-kernel/src/lib.rs` tests and doctest.
  - Rationale: this is definitional; the test guards wiring, not mathematics.
- Obligation VO-7, pin consistency: every pinned revision agrees across
  `spec/toolchain-profiles.json`, `rust-toolchain.toml`, `Cargo.lock`,
  `tools/kani/VERSION`, `tools/verus/VERSION`, the installer scripts, and the
  `environment.toolchains` of controls AC-01, AC-02, AC-04, and AC-07.
  - Method: exact cross-check in the design checker, plus table-driven tests.
  - Artefacts: `scripts/docs_validation/toolchain_profiles.py`,
    `scripts/tests/test_toolchain_profiles.py`.
  - Non-vacuity: one test per source mutates that source's pin in a temporary
    copy and requires the checker to fail naming that source.
- Obligation VO-8, capability records are evidence-backed: every capability
  marked `tested` or `unsupported` cites a committed probe log by path and
  SHA-256, and every cited digest matches.
  - Method: exact check in the design checker.
  - Non-vacuity: a record with a `tested` status and no log, and a record whose
    digest differs from its file, must both fail.
- Obligation VO-9, trust-audit soundness: for any Rust source text, every
  occurrence of an ADR-0009 vocabulary item in code position is reported once
  with its line and column; aliased imports of a vocabulary item are reported;
  occurrences inside comments, string literals, raw strings, byte strings, and
  character literals are not reported; unterminated comments or literals make
  the scan fail closed with an error, never with an empty audit.
  - Method: Hypothesis properties over generated token streams (insertion of
    an item in code position adds exactly that item; insertion inside a comment
    or literal adds nothing; arbitrary text never raises an unhandled
    exception), plus a handwritten corpus with one fixture per vocabulary
    item and per lexical trap (nested block comments, `r#"..."#`, lifetimes
    such as `'a` versus character literals).
  - Artefacts: `scripts/docs_validation/trust_audit.py`,
    `scripts/tests/test_trust_audit.py`, `scripts/tests/fixtures/trust_audit/`.
  - Non-vacuity: Hypothesis classification (`hypothesis.event`) must show every
    vocabulary item and every lexical context generated; a scanner variant with
    any one vocabulary entry removed must fail the corpus test, which the test
    suite demonstrates by running the corpus against that variant.
- Obligation VO-10, shipped crates are trust-free: the scan of `src/` and
  `crates/` reports no item.
  - Method: design-checker check `trust-audit`.
  - Non-vacuity: the same check over `tools/verifier-fixtures/` must report the
    seeded items, proving the check reads real files.
- Obligation VO-11, Kani parser fail-closed derivation: given a log, its digest,
  and its harness manifest, the parser returns a `VerifiedLogResult` whose
  outcome is `verified` only when the version banner names Kani 0.67.0, every
  manifest harness has a successful verification result, every declared cover
  is satisfied, no unwinding assertion failed, no timeout occurred, and the
  summary counts agree with the per-harness results. Otherwise it returns
  `counterexample`, `resource-exhausted` (timeout), `skipped` (a manifest
  harness without a result), or `tool-error` (unrecognized or inconsistent
  structure, wrong version, digest mismatch), and witness statuses mark each
  unsatisfied cover.
  - Method: real-log corpus tests (one log per outcome class, captured from
    pinned Kani in EP-M1) plus Hypothesis properties over log mutations:
    truncation, line deletion, duplicated harness blocks, altered summary
    counts, and altered version banners never yield `verified`.
  - Artefacts: `scripts/docs_validation/kani_log.py`,
    `scripts/tests/test_kani_log.py`, `scripts/tests/fixtures/kani_logs/`.
  - Evidence: the corpus test fails before the parser exists (red) and passes
    after; `scripts/check_evidence.py` over the corpus records prints each
    record's level and reasons.
  - Non-vacuity: the corpus includes a log whose final line reports success
    while a cover is unsatisfied, so a parser that reads only the summary fails;
    the suite runs the corpus against two deliberately broken parsers (always
    `verified`; success line only) and requires both to fail.
- Obligation VO-12, gate integration: an evidence record citing a committed
  Kani log reaches `bounded` or `proof` only through the parser; the same
  record with a tampered digest, an unregistered tool, or a mismatched derived
  fact is `verdict-self-reported` and rejected. The gate function stays pure:
  the shell reads bytes and passes parsed results into `AdmissionContext`.
  - Method: integration tests over `scripts/check_evidence.py` and
    `evidence_records.admitted_evidence`.
  - Non-vacuity: the positive record must reach `bounded` or `proof`, so the
    integration cannot pass by rejecting everything.
- Obligation VO-13, registration discipline: every name in
  `registered_log_parsers` has a corpus manifest that includes the outcome
  classes success, counterexample, timeout, unsatisfied cover, and skipped
  harness, each backed by a committed log, and its corpus tests are part of
  `make design-check`.
  - Method: design-checker check `log-parser-registration`.
  - Non-vacuity: registering a name with a manifest that lacks the timeout
    class must fail.

### Axioms

- AXIOM-01: rustc, Cargo, and the pinned Cranelift and LLVM backends compile
  what they accept faithfully; Cargo's dependency resolution reported by
  `cargo tree` and `cargo metadata` is the graph that is built.
- AXIOM-02: Kani 0.67.0 with its bundled CBMC and CaDiCaL reports harness
  results faithfully in its regular output format.
- AXIOM-03: Verus 0.2026.09.06.8dea4a2 with Z3 4.16.0 and the matching `vstd`
  reports verification results faithfully; Verus's trusted basis includes
  `vstd`'s specifications and any `external` items it uses.
- AXIOM-04: GitHub-hosted `ubuntu-24.04` runners match the AC environment
  description closely enough for the registered thresholds to apply.
- AXIOM-05: Polars 0.55.2's public API behaves as documented for the small calls
  made in this task; no Polars capability is claimed.
- AXIOM-06: the harness manifest's type-complete or partial declaration for each
  corpus harness is a reviewed repository fact (DL-10).

## Plan of work

### EP-M1. Prototype: toolchain and profile capability probes

This milestone records each tool and profile capability and trust boundary
before anything depends on it. It is a prototyping milestone: its probe crates
are kept as fixtures if they serve later milestones and deleted otherwise.

- Write `scripts/install-proof-tools.sh` and `make install-proof-tools`. Pin
  Kani in `tools/kani/VERSION` (0.67.0) and `tools/kani/SHA256SUMS` (the
  release asset digest
  `3b5f7afd3b51603ee720db7bc1bc4fe46b5a4f5d36daad9939c4b4c658b51ac0` for
  `kani-0.67.0-x86_64-unknown-linux-gnu.tar.gz`), and Verus in
  `tools/verus/VERSION` (0.2026.09.06.8dea4a2) and `tools/verus/SHA256SUMS`
  (`13d01e134c0620c3b29770874707d16c33b3d227c843a489c8ceb744d43c0a16` for
  `verus-0.2026.09.06.8dea4a2-x86-linux.zip`). Install into
  `${XDG_DATA_HOME:-$HOME/.local/share}/combobulate-proof-tools/`, never into
  `/tmp`. Determine whether the Verus archive bundles Z3 4.16.0; if not, pin a
  Z3 release asset the same way. Follow `docs/scripting-standards.md` and the
  existing `scripts/install-build-tools.sh` pattern.
- Create `tools/verifier-fixtures/kani-corpus/`, a standalone crate with its
  own `[workspace]` table (like the calibration probe), holding labelled test
  subjects: a passing harness with a satisfied cover; a harness with a
  counterexample; a harness that passes with an unreachable cover; a harness
  given symbolic full-width multiplication, which calibration showed does not
  finish, run with `-Z unstable-options --harness-timeout 5s`; a harness with a
  failed unwinding assertion; and a run with `--fail-fast` after a failure so
  that later harnesses are skipped. Capture each run's full output with
  `make kani-log-corpus` into `scripts/tests/fixtures/kani_logs/`, together with
  `cargo kani list --format json` output as the harness manifest and a
  provenance file naming command, Kani version, and digest.
- Create `tools/verifier-fixtures/verus-wiring-probe/`, a crate that tests two
  candidate wirings for the kernel's eventual proof profile: (a) a non-optional
  `vstd` dependency with `verus!` blocks, and (b) an optional `vstd` dependency
  behind a `verus` feature, with specifications attached by attributes that are
  inert in ordinary builds. Each candidate holds one tiny labelled capability
  lemma and one seeded mutant. Record for each candidate whether
  `cargo verus verify` succeeds in place under the repository's
  `.cargo/config.toml`, whether the mutant fails for the intended reason,
  whether an ordinary `cargo build` succeeds without a verifier installed, and
  the extra build time. Confirm that `vstd` `0.0.0-2026-09-06-0133` is the
  release matching the pinned Verus. This probe selects the wiring that task
  1.2.4 will use; it does not add proof content to the kernel.
- Probe the proof-capable Kani build in place: `cargo kani --only-codegen` on a
  scratch copy of the planned kernel and native-only facade inside the
  repository tree, recording whether the repository's Cargo configuration and
  lint tables are accepted by Kani's nightly-2025-11-21.
- Record `rustc -vV` and `cargo -V` for the repository nightly, Kani's bundled
  toolchain, and Verus's Rust 1.98.0.
- Measure, with `CARGO_BUILD_JOBS=4` and empty target directories, the cold
  duration of each hosted route that would build Polars 0.55.2 with the
  candidate feature set: rustdoc, Clippy, Whitaker, nextest under Cranelift,
  and LLVM coverage. Use these to predict hosted durations (local median times
  the AC-04 calibration factor 1.2) and to settle DL-03 before any push.
- Determine the smallest Polars 0.55.2 feature set (starting from
  `default-features = false, features = ["lazy"]`, the calibrated set) that
  builds an `Int64` `Series` and collects a trivial `LazyFrame`; record it.
- Go/no-go: proceed only if both verifiers process at least one wiring in
  place without weakening the ordinary build standard, and if a CI shape is
  predicted within the 6-minute per-job tolerance. Otherwise stop and record
  the deviation in `Decision log` with status `BLOCKED`.
- Validation: `make install-proof-tools`; `make kani-log-corpus`;
  `make verus-probe`, which runs `cargo verus verify` on each wiring candidate
  and expects the candidate lemma to verify and the seeded mutant to fail with
  "postcondition not satisfied"; then `make check-fmt`, `make lint`,
  `make test`, `make design-check`, `make markdownlint`, and `make spelling`.

### EP-M2. Workspace, crate boundaries, and dependency-direction checks

- Red: add `tests/workspace_boundaries.rs` with VO-1 to VO-4 as `rstest`
  tables using `googletest` matchers. Run it and observe failure because
  neither member crate exists.
- Convert `Cargo.toml` into a workspace root with `members = ["crates/*"]`,
  `default-members = [".", "crates/combobulate-kernel",
  "crates/combobulate-macros"]`,
  `exclude = ["tools"]`, and `resolver = "3"`. Move the lint tables to
  `[workspace.lints]` and set `lints.workspace = true` in every package, as the
  developers' guide already requires. Move shared package metadata (edition,
  licence, repository, `publish = false`) to `[workspace.package]`.
- Create `crates/combobulate-kernel/` (`#![no_std]`, no dependencies,
  `TargetFacts`) and `crates/combobulate-macros/` (`proc-macro = true`, no
  dependencies, crate documentation only).
- Extend `scripts/docs_validation/package_policy.py` and
  `scripts/tests/test_package_policy.py` so that every workspace member, not
  only the root, must carry the ISC licence and `publish = false`.
- Remove `greet()` and `tests/stub.rs`.
- Green: rerun the boundary tests; then run the full gates.
- Update contract tests only where a route genuinely changed; record each such
  change in `Decision log`.

### EP-M3. Feature profiles, `BuildProfile`, and profile behaviour tests

- Red: write `tests/features/build_profiles.feature` (below), its step
  definitions in `tests/build_profiles.rs`, and `insta` snapshot tests of the
  rendered profile line. Run them and observe failure because `BuildProfile`
  does not exist.
- Add the facade features `default = ["macros", "polars"]`,
  `macros = ["dep:combobulate-macros"]`, and `polars = ["dep:polars"]`, with
  `polars = { version = "0.55.2", default-features = false, features = [...] }`
  using the EP-M1 feature set.
- Add `src/profile.rs` with `BuildProfile` and the re-export of `TargetFacts`,
  and a crate-private `src/polars_backend.rs` behind `cfg(feature = "polars")`
  that builds an `Int64` `Series` in a unit test, proving the Polars-enabled
  build compiles and links without claiming any capability.
- Add `examples/build_profile.rs`, which prints `BuildProfile::current()`.
- Add `make check-profiles`, which runs, as separate Cargo invocations so that
  feature unification cannot mask a profile: Clippy and nextest for the
  native-only profile (`--no-default-features --features macros` and
  `--no-default-features`); the example in each profile, comparing its output
  with `tests/fixtures/profiles/<profile>.txt`. Call it from `make test`, and
  add its argument vectors to `tests/make_gate_order.rs`.
- Green: rerun the scenarios, snapshots, and `make check-profiles`.

The behaviour specification:

```gherkin
Feature: Build profiles report what was compiled

  @native
  Scenario: A native-only build reports no Polars backend
    Given the facade compiled without default features
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile does not report a Polars backend
    And the profile reports the target usize width

  @polars
  Scenario: The default build reports the Polars backend
    Given the facade compiled with default features
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile reports a Polars backend
    And the profile reports the macro feature
```

### EP-M4. Profile record, pin consistency, proof-tool installation, ADR

- Red: add `scripts/tests/test_toolchain_profiles.py` with the VO-7 and VO-8
  mutation tests; observe failure.
- Add `spec/toolchain-profiles.schema.json` and `spec/toolchain-profiles.json`
  recording: the repository nightly with its commit hash; Kani 0.67.0, its
  bundled toolchain, CBMC and CaDiCaL versions; Verus 0.2026.09.06.8dea4a2, its
  Rust 1.98.0, Z3 4.16.0, and the matching `vstd`; Polars 0.55.2 with its
  selected features; the target `x86_64-unknown-linux-gnu`; the four profiles
  with their crates, features, toolchains, and commands; every EP-M1 capability
  with status and log citation; and each tool's trusted computing base.
- Add `scripts/docs_validation/toolchain_profiles.py` and register its check in
  `scripts/check_docs.py`. Green: rerun.
- Write ADR-0010
  (`docs/adrs/adr-0010-workspace-crate-boundaries-and-profiles.md`) as
  `Proposed`, covering CA3, CA5, Q3, and the selected Verus wiring; add
  proposed decision D16 to `spec/decisions.json` and regenerate the register.
  The sponsor accepts both before EP-M6 ticks the task.

### EP-M5. Trust-audit scanner and Kani log parser; parser registration

- Red: add `scripts/tests/test_trust_audit.py` and
  `scripts/tests/test_kani_log.py` (VO-9 to VO-13) over the EP-M1 corpus;
  observe failure.
- Implement `scripts/docs_validation/trust_audit.py` (a small Rust lexer that
  skips comments and literals, then a token matcher over the ADR-0009
  vocabulary, including `#[verifier::...]` and `#[verifier(...)]` attribute
  forms) and the command `scripts/trust_audit.py PATH...`, which prints items
  in the schema's `trust_audit.items` shape. Add the `trust-audit` design check.
- Implement `scripts/docs_validation/kani_log.py`, which takes bytes, an
  expected digest, and a harness manifest, and returns a `VerifiedLogResult` or
  a typed refusal. Extend `evidence_records.evidence_inputs` and
  `scripts/check_evidence.py` so the I/O shell reads each log named by a
  record, runs the registered adapter, and passes the results into
  `AdmissionContext.verified_log_results`.
- Add fixture evidence records under `scripts/tests/fixtures/evidence/` that
  cite corpus logs (not under `spec/evidence/`, so they cannot affect roadmap
  closure).
- Only when every corpus test passes, add `"kani"` to
  `registered_log_parsers` in `spec/evidence-reason-codes.json`, add the
  `log-parser-registration` check, and update the description in
  `scripts/tests/fixtures/evidence/log-parsers.json`.

### EP-M6. CI profile jobs, AC-04 measurement, documents, and roadmap tick

- Implement the approved DL-03 CI shape in `.github/workflows/ci.yml`, with
  contract tests in `tests/` updated in the same commit. Before pushing, show
  from EP-M1 measurements that each required job is predicted within 6 minutes
  cold.
- Add `.github/workflows/profile-builds.yml` (manual dispatch, plus a
  `pull_request` trigger when the `measure-profiles` label is applied) that
  runs the AC-04 protocol: five cold and five incremental builds per profile,
  profiles alternating run by run, one discarded incremental warm-up. Commit
  the resulting acceptance record to `spec/measurements/` and report its
  verdict honestly.
- Documentation: ADR-0010; the decision register; technical design §3 (crate
  names, dependency direction, profile names), §15 (GAP4), §17.7 (profile
  wiring), and §19.1 (selected Polars release); `docs/users-guide.md`
  (features, native-only use, `BuildProfile`, the reserved `macros` feature);
  `docs/developers-guide.md` (workspace layout, profiles, proof-tool
  installation, `make check-profiles`, module-owner rows for
  `toolchain_profiles.py`, `trust_audit.py`, and `kani_log.py` with their
  re-use boundaries); `docs/repository-layout.md`; `docs/contents.md`;
  `docs/evidence-and-decision-records.md` (the Kani parser is registered); an
  ADR-0009 amendment noting the registration; `docs/acceptance-calibration.md`
  (Polars no longer provisional); `docs/terms-of-reference.md` Q3 status.
- Add the 1.2.1 entry to `spec/task-completion.json` citing D16 and its
  artefacts, tick task 1.2.1 and its detail in `docs/roadmap.md`, and regenerate
  `spec/roadmap.json`.

## Milestones and plateaus

- EP-M1: capability probes, logs, and measurements committed; no product code
  changed. Requirements: Q3, Q9, AC-04 inputs, B01 and B05 preconditions.
  Evidence: `make kani-log-corpus`, `make verus-probe`, probe records.
  Recovery: delete `tools/verifier-fixtures/` and revert the installer.
  Remaining: everything else.
- EP-M2: three-crate workspace; boundary tests green. Requirements: TD §3,
  CA5 structure. Evidence: VO-1 to VO-4 (VO-4 partially until EP-M3). Recovery:
  revert the commit; the single-crate state is self-consistent.
- EP-M3: features and `BuildProfile`; both profiles build and report.
  Requirements: ToR S7, TD §3, §19.1. Evidence: VO-4, VO-5, VO-6,
  `make check-profiles`.
- EP-M4: profile record and pin checker; proposed ADR-0010 and D16.
  Requirements: GAP4, Q3. Evidence: VO-7, VO-8.
- EP-M5: scanner and parser; Kani registered. Requirements: D15, ADR-0009.
  Evidence: VO-9 to VO-13.
- EP-M6: CI shape, AC-04 record, documents, tick. Evidence: hosted CI green,
  AC-04 record, `make design-check` accepting the tick.

At each boundary run the focused conformance check: requirements assigned to
the milestone satisfied; ADR-0010 still followed; no B01, B05, or Q9 assumption
falsified; no unapproved public interface, dependency, or trust boundary; trace
links current. Compatibility decision for every milestone: none, because every
changed surface is pre-1.0 and unreleased.

## Concrete steps

All commands run from the repository root. Long outputs go through `tee` into
`/tmp/$ACTION-combobulate-1-2-1-establish-workspace-and-profiles.out`.

```bash
make install-proof-tools 2>&1 | tee /tmp/install-proof-tools-combobulate-1-2-1-establish-workspace-and-profiles.out
make kani-log-corpus 2>&1 | tee /tmp/kani-corpus-combobulate-1-2-1-establish-workspace-and-profiles.out
make verus-probe 2>&1 | tee /tmp/verus-probe-combobulate-1-2-1-establish-workspace-and-profiles.out
make check-fmt 2>&1 | tee /tmp/check-fmt-combobulate-1-2-1-establish-workspace-and-profiles.out
make lint 2>&1 | tee /tmp/lint-combobulate-1-2-1-establish-workspace-and-profiles.out
make test 2>&1 | tee /tmp/test-combobulate-1-2-1-establish-workspace-and-profiles.out
make design-check 2>&1 | tee /tmp/design-check-combobulate-1-2-1-establish-workspace-and-profiles.out
make markdownlint 2>&1 | tee /tmp/markdownlint-combobulate-1-2-1-establish-workspace-and-profiles.out
```

Expected kernel isolation after EP-M2:

```plaintext
$ cargo tree -p combobulate-kernel --all-features -e normal,build --prefix none
combobulate-kernel v0.1.0 (.../crates/combobulate-kernel)
```

Expected profile lines after EP-M3 (exact wording fixed by the snapshots):

```plaintext
$ cargo run --quiet --example build_profile --no-default-features
features: native; target usize: 64 bits
$ cargo run --quiet --example build_profile
features: native, macros, polars; target usize: 64 bits
```

## Validation and acceptance

Quality criteria:

- Tests: `make test` (including `make check-profiles`) and `make design-check`
  pass; the boundary, profile, pin, scanner, and parser tests each failed
  before their implementation and pass after.
- Verification: VO-1 to VO-13 discharged as stated, with their non-vacuity
  controls observed; `make verus-probe` shows each wiring candidate's lemma
  verified and its mutant rejected with "postcondition not satisfied"; the Kani
  corpus shows each outcome class.
- Lint and format: `make check-fmt`, `make lint`, `make markdownlint`,
  `make spelling`, and `make nixie` pass.
- Performance: the AC-04 acceptance record states pass or fail against its
  ceilings; the hosted `build-test` job and any profile jobs stay within the
  approved AC-07 workload.
- Security: `make audit` passes with Polars in the lock file; no new audit
  ignore is added without a recorded reason.

## Idempotence and recovery

The installer is idempotent: it verifies digests and skips installed matching
versions. `make kani-log-corpus` regenerates logs and provenance; regenerated
logs differ in timings, so their digests are refreshed together with the
fixture records, and the parser tests assert classifications rather than
timings. Every milestone ends in a committed, gated state, so `git revert` of
one milestone's commits returns to the previous plateau.

## Artefacts and notes

Release digests obtained on 2026-10-22 from the GitHub releases API:

```plaintext
verus-0.2026.09.06.8dea4a2-x86-linux.zip  sha256:13d01e134c0620c3b29770874707d16c33b3d227c843a489c8ceb744d43c0a16
kani-0.67.0-x86_64-unknown-linux-gnu.tar.gz  sha256:3b5f7afd3b51603ee720db7bc1bc4fe46b5a4f5d36daad9939c4b4c658b51ac0
```

## Interfaces and dependencies

In `crates/combobulate-kernel/src/lib.rs`:

```rust
/// Facts about the compilation target that checked rules must use.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TargetFacts { usize_bits: u32 }

impl TargetFacts {
    /// Facts for the target this crate is compiled for.
    pub const fn current() -> Self { Self { usize_bits: usize::BITS } }
    /// Width of `usize` on the target, in bits.
    pub const fn usize_bits(self) -> u32 { self.usize_bits }
}
```

In `src/profile.rs`, re-exported from the crate root:

```rust
/// Features and target facts compiled into this build of Combobulate.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[non_exhaustive]
pub struct BuildProfile { /* private fields */ }

impl BuildProfile {
    pub const fn current() -> Self;
    pub const fn has_macros(self) -> bool;
    pub const fn has_polars(self) -> bool;
    pub const fn target(self) -> TargetFacts;
}

impl core::fmt::Display for BuildProfile { /* the profile line */ }
```

Dependencies (caret requirements):

- Facade runtime: `combobulate-kernel` (path), optional `combobulate-macros`
  (path), optional `polars = "0.55.2"` with `default-features = false` and the
  EP-M1 feature set.
- Facade development: `rstest-bdd = "0.6.0"`, `googletest = "0.14.3"`,
  `pretty_assertions = "1.4.1"`, `insta = "1.49.0"`; `rstest` may move from
  0.27.0 to 0.28.0 only if `rstest-bdd` requires it.
- Kernel and macros: none.
- Proof tools (not Cargo dependencies): Kani 0.67.0, Verus
  0.2026.09.06.8dea4a2, Z3 4.16.0, `vstd` `=0.0.0-2026-09-06-0133` in the Verus
  probe only (an exact pin is required because Verus checks that `vstd` matches
  the verifier build).

## Signposts

Read before implementing: `docs/technical-design.md` §§3, 10, 15, 17-19;
`docs/terms-of-reference.md` §6 and Q3, Q9; `docs/testable-bets.md` B01, B05;
`docs/adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md`;
`docs/adrs/adr-0008-acceptance-control-pre-registration.md`;
`docs/adrs/adr-0009-proof-first-policy-and-evidence-gate.md`;
`docs/evidence-and-decision-records.md`; `docs/acceptance-calibration.md`;
`docs/developers-guide.md`;
`docs/reliable-testing-in-rust-via-dependency-injection.md`;
`docs/rust-testing-with-rstest-fixtures.md`; `docs/rstest-bdd-users-guide.md`;
`docs/rust-doctest-dry-guide.md`;
`docs/complexity-antipatterns-and-refactoring-strategies.md`;
`docs/references.md` (E-KANI-*, E-VERUS-*, E-POLARS2-*);
`docs/documentation-style-guide.md` (ADR template and naming).

Skills: `execplans`, `rust-router`, `arch-crate-design`,
`arch-decision-records`, `arch-supply-chain`, `rust-unit-testing`, `kani`,
`verus`, `rust-verification`, `hypothesis`, `python-testing`, `nextest`,
`codegraph-mcp`, `firecrawl-mcp`, `en-gb-oxendict-style`, `pr-creation`.

## Revision note

2026-10-22: initial draft from Wyvern reconnaissance and external research.
Pending the community-of-experts review and sponsor approval.
