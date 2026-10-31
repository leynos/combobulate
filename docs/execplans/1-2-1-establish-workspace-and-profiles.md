# Establish the workspace and pinned profiles (roadmap 1.2.1)

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: APPROVED. The sponsor approved execution on 2026-10-27 and directed
that Q3 join `in_scope_questions`, with its decision based on implementation
findings. The 2026-10-22 sponsor decisions remain subject to the final-text
approval checkpoints for the amendments, D16, and ADR-0010.

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
can at last admit a verifier verdict, because a verifier log parser exists, has
been tested against real logs, and is bound to an independently re-derived
trust audit.

After this work a reviewer can do the following, none of which is possible
today:

1. Build the external fixture `tools/fixtures/native-consumer/`, which depends
   on the facade by path with `default-features = false`, and run it. Its
   dependency graph contains no Polars, glam, Kani, or Verus package, and it
   prints a profile line that reports no Polars backend.
2. Build the default profile, which enables the `macros` and `polars` features
   and compiles a crate-private Polars module against the pinned Rust Polars
   0.55.2 release, chosen independently of the Python Polars 2 version label.
3. Ask Cargo for the kernel's dependency graph under every feature selection,
   every target, and every edge kind, and find no Polars or glam package; in
   this task the kernel declares no dependency at all.
4. Read `spec/toolchain-profiles.json`, which records the exact Rust nightly,
   Kani, CBMC, Verus, Z3, `vstd`, Polars, and target revisions, the rustup
   toolchains each verifier fetches, each profile's crates, features, and
   commands, every probed tool capability with a status of documented, tested,
   unsupported, or inconclusive, and each tool's trusted computing base.
   `make design-check` fails when any other pin in the repository disagrees
   with that record.
5. Run `make install-kani` and `make install-verus`, which delegate to the
   `prover-tools` command from `leynos/rust-prover-tools` at the commit pinned
   in `tools/rust-prover-tools/REF`, to install the Kani and Verus releases
   pinned in `tools/kani/VERSION` and `tools/verus/VERSION`. The Verus archive
   is checked against `tools/verus/SHA256SUMS`. `make kani-check` confirms that
   the running Kani matches its pin. Ordinary builds and every ordinary Make
   gate continue to pass on a host with neither tool installed.
6. Run `python3 scripts/check_evidence.py` over a fixture evidence record that
   cites a committed Kani log and harness manifest, and see the gate re-derive
   the verdict through the registered `kani` parser and the trust audit through
   the scanner. A timeout, an unsatisfied cover, a skipped harness, a truncated
   log, and a fabricated trust audit each produce their own rejection, using
   logs that the pinned Kani actually emitted.
7. Run `python3 scripts/trust_audit.py` over the workspace and see every
   ADR-0009 trusted item in code position reported, while the same words in
   comments, string literals, and ordinary Rust such as the standard
   `#[should_panic]` test attribute are not.

Compile-only evidence is not a theorem. Nothing in this task claims a proved
property of Combobulate itself. The capability records say what the tools did
on probe fixtures; the profile builds say what compiled; the parser and scanner
are tested gate components. Task 1.2.4 makes the first proof claim.

## Sponsor decisions

The sponsor (`leynos`, the D01 authority) was asked to settle these before
implementation begins. On 2026-10-22 the sponsor accepted the recommended
option for all eight, in this session. Items 2, 3, 4, and 7 are accepted in
direction; their final texts are approved at the checkpoints named. The sponsor
directed on 2026-10-27 that Q3 join `in_scope_questions`. Trade-offs are in
`Decision log`.

1. CI shape for the Polars-enabled profile (DL-03). Recommended: the
   `build-test` job keeps the native-only profile; parallel Polars-enabled lint
   and test jobs are added, each sized from hosted measurements so that its
   slowest observed cold run plus fixed overhead stays within 6 minutes. This
   edits the frozen `.github/workflows/ci.yml`, so it needs the AC-07 amendment
   in item 2.
2. AC-07 amendment (DL-14). Recommended content: the workload becomes every
   required pull-request job in `ci.yml`; per workflow run the statistic is the
   longest required job; nearest-rank p90 over the 20 most recent runs, with
   any failed, timed-out, cancelled, or missing job failing the control; the
   window restarts empty on the new shape, so AC-07 is inconclusive when task
   1.2.1 is ticked. The sponsor approves the final text, with measured job
   sizes, at the EP-M3 checkpoint and before the first attempt on the new shape.
3. AC-04 amendment (DL-15). AC-04 registers "the 1.2.1 foundational probe in
   its three feature profiles" with the calibration probe's manifest as its
   only source. Recommended: rebind its sources to the workspace manifests and
   map its three profiles to native-only, proof-capable Kani codegen, and
   Polars-enabled, keeping every threshold unchanged. Approved at EP-M4.
4. ADR-0009 amendment (DL-16). Recommended: the gate maps `trust` to
   `unaudited` unless the I/O shell supplies a scanner-derived audit whose
   items equal the record's; the vocabulary's matching rule is stated (DL-17);
   the 1.2.1 Kani parser always derives `partial` bounds. The rule table,
   levels, and properties P1-P6 are unchanged. Approved at EP-M5.
5. The empty macro crate (DL-05). Recommended: create `combobulate-macros` now
   with no exported macro and no dependency, wired through a default `macros`
   feature that the users' guide describes as reserved until task 2.3.1.
6. Which verifier parser task 1.2.1 registers (DL-07). Recommended: register
   only the Kani parser; the Verus parser stays with task 1.2.4.
7. Decision D16 and ADR-0010 (DL-02). Recommended: D16 accepts ADR-0010, which
   records the crate boundary, dependency direction, feature profiles, gate
   feature lists, and the supported-toolchain set that answers ToR Q3 in place
   of one MSRV. The sponsor accepts D16 after EP-M4 publishes ADR-0010; the
   approval reference is committed before the tick. Q3 joins
   `in_scope_questions` when D16 is proposed, informed by the probe findings.
8. PR title numbering (DL-12). The request asked for `(1.1)` in the title, but
   this task is roadmap item 1.2.1. The draft PR uses `(1.2.1)`; the sponsor
   may ask for the literal `(1.1)` instead.

## Constraints

- The semantic kernel `combobulate-kernel` must import neither Polars nor glam
  under any feature, target, or dependency-edge selection (technical design §3,
  roadmap 1.2.1).
- The kernel must never be compiled for the host as part of a target build:
  it may not appear in any build-dependency edge or in any procedural-macro
  crate's dependency closure (technical design §18.1, DL-06).
- Ordinary consumers must not need Kani, Verus, Z3, or any verifier
  installation to build, test, or use any ordinary profile (ToR line 152,
  technical design §§3, 17.7). Ordinary Make gates name their features
  explicitly; none uses `--all-features`, so a future proof feature cannot
  enter an ordinary route (DL-18).
- The Polars dependency is selected by its Rust crate release and tested
  public interface, never by the Python Polars 2 version number (technical
  design §19.1, context.md line 230, ToR Q9). Polars paths appear only in the
  facade's crate-private Polars module (VO-14).
- Proof support must not use `cfg(kani)` or a proof feature to replace a
  production body with a different implementation (technical design §17.7).
- Kani and Verus are preferably installed, version-checked, and run through
  `prover-tools` from `leynos/rust-prover-tools`, pinned by commit in
  `tools/rust-prover-tools/REF` and invoked through `uv tool run --from` that
  pinned Git source. No repository-owned installer script is written. Make
  recipes contain none of `cargo install`, `cargo kani setup`, `curl`, `unzip`,
  `sha256sum`, or `rustup toolchain install`, and route through an
  `override`-locked `$(PROVER_TOOLS)` variable whose only substitution seam is
  the contract-test pair `PROVER_TOOLS_CONTRACT_TEST=1 PROVER_TOOLS=<fake>`
  given on the `make` command line (the `kani` skill's project on-ramp). A
  probe that needs a capability unavailable through `prover-tools` may invoke
  the pinned tool directly, with the reason and invocation recorded.
- The pinned Kani 0.67.0, Verus 0.2026.09.06.8dea4a2, and Z3 4.16.0 revisions
  are part of the pre-registered environment of controls AC-01, AC-02, AC-04,
  and AC-07. Changing any of them requires a sponsor-approved control amendment
  under ADR-0008; newer releases (for example Kani 0.68.0) are not adopted by
  this task.
- `.github/workflows/ci.yml` is a frozen AC-07 source (sha256 `a7df0545…`).
  It must not change until the AC-07 amendment is sponsor-approved, and the
  amendment and the change land in one commit.
- Every hosted `build-test` attempt counts towards AC-07, and any failed,
  timed-out, or cancelled attempt fails it. No push may add the Polars
  dependency to the facade until the approved CI shape lands in the same push.
  No push may change any required job without a hosted measurement predicting
  that its slowest cold run fits within 6 minutes including fixed overhead.
- `tools/calibration/cardinality-probe/` is frozen by AC-01, AC-02, and AC-04
  and must not change.
- The repository remains unpublished: every workspace member states
  `publish = false` and `license = "ISC"` literally in its own manifest (D04,
  D05, ADR-0004); these fields are not inherited from `[workspace.package]`,
  because the package-policy checker reads them literally.
- Pre-1.0 policy (D06, ADR-0005): no aliases, deprecated entry points, or
  shims. The disposable `greet()` stub is removed rather than preserved.
- A verifier log parser may be registered in
  `spec/evidence-reason-codes.json` only after its tests over real logs,
  including a timeout, an unsatisfied cover, and a skipped harness, pass
  (roadmap 1.2.1 detail, D15).
- The evidence gate stays pure: `AdmissionContext` receives parsed log results
  and scanner-derived audits from an I/O shell and never reads files, the
  clock, or the environment (technical design §17.2, ADR-0009).
- Production code must not read environment variables outside a composition
  root; `clippy.toml` disallows the `std::env` accessors. Tests that spawn
  Cargo use `env!("CARGO")` and `Command::env_remove`, never in-process
  environment mutation (AGENTS.md).
- No `assume`, `admit`, `external_body`, Kani stub, or equivalent may appear in
  shipped crates. Probe fixtures may contain them only as labelled scanner or
  parser test subjects.
- No code file may exceed 400 lines. `tests/make_gate_order.rs` is already 481
  lines and must be split in a separate refactor commit before it is extended.
  Markdown wraps at 80 columns; prose uses en-GB-oxendict spelling (AGENTS.md).
- Completed ExecPlans, including
  `docs/execplans/1-1-resolve-acceptance-control-decisions.md`, are historical
  and must not be edited.

## Tolerances (exception triggers)

- Scope: stop and escalate if one milestone needs more than 40 changed files or
  more than 1,800 net added lines, excluding committed verifier logs,
  `Cargo.lock`, and generated exports. The sponsor approved an EP-M1-only limit
  of 1,825 lines on 2026-10-28 for count and pin-consistency fixes, and raised
  that EP-M1 limit to 3,600 lines on 2026-10-30 for the solver-selection fix,
  its regression test, and the regenerated verifier logs.
- Interface: stop if any public item beyond `BuildProfile` in the facade and
  `TargetFacts` in the kernel, and the two Cargo features named in
  `Interfaces and dependencies`, seems necessary.
- Dependencies: stop before adding any dependency not listed in
  `Interfaces and dependencies`, or a version other than the one listed.
- Toolchain capability: stop if Kani or Verus cannot process the probe
  arrangement under the repository's Cargo configuration without a change that
  weakens the ordinary build standard or a substitute body. That outcome is a
  B01 falsifier candidate and needs a representation decision, not a workaround.
- Budgets: stop if a hosted measurement predicts that a required job would
  exceed 6 minutes cold, if the AC-04 acceptance measurement fails a ceiling,
  if a probe exceeds its AC-01 or AC-02 budget, or if a hosted route exceeds 12
  GiB of peak memory or the runner's free disk.
- Upstream tooling: prefer `rust-prover-tools`; when a probe cannot use its
  interface, record the limitation and use the pinned tool directly.
- Iterations: stop if a gate still fails after three fix attempts on the same
  cause.
- Ambiguity: stop and present options when a choice materially changes a
  public interface, a trust boundary, an accepted ADR, or a pre-registered
  control.

## Risks

- Risk: cold Polars builds push a hosted job past its 8-minute hard timeout,
  failing AC-07. Locally a cold Cranelift build took a 163-second median, but
  382 seconds at worst; hosted runners set `CARGO_INCREMENTAL=0`, cache only
  `target/debug`, and today's job already spends about 75 seconds on setup and
  45 seconds on a cold Whitaker driver build. Polars would be compiled by
  rustdoc, Clippy, Whitaker (its own toolchain), Cranelift tests, and LLVM
  coverage. Severity: high. Likelihood: high. Mitigation: hosted measurement in
  EP-M1 using the slowest run, not the median; the DL-03 job split; GitHub
  Actions sccache enabled; caches saved only on `main`; no push before the
  prediction fits.
- Risk: cache thrash. Dependabot updates `Cargo.lock` often, each update mints
  new multi-gigabyte cache keys, eviction removes `main`'s cache, and a cold
  run times out. Severity: high. Likelihood: medium. Mitigation: jobs are sized
  for cold runs; caches saved only on `main`; every job logs its cache hit
  state; the Verus archive is never placed in the Actions cache.
- Risk: Polars pin churn. A grouped Dependabot update moves Polars to 0.55.3 or
  0.56, which fails VO-7 or the build inside the AC-07 window. Severity:
  medium. Likelihood: high. Mitigation: a Dependabot `ignore` entry for
  `polars*`, and a documented rule that the Polars pin moves only through a
  control amendment and a profile-record update.
- Risk: the runner exhausts memory or disk building Polars with LLVM under
  `-Zthreads=8` and four jobs on a 4 vCPU, 16 GB runner. Severity: medium.
  Likelihood: medium. Mitigation: EP-M1 records peak memory and `target/` size;
  jobs delete intermediate target directories; a hosted `-Zthreads=4` override
  is evaluated if memory exceeds the 12 GiB cap.
- Risk: the Verus driver, built on Rust 1.98.0, rejects the repository's
  nightly-only Cargo configuration (`[unstable] codegen-backend`, Cranelift in
  `[profile.dev]`, `-Zthreads=8`, the `mold` linker wrapper). Severity: high.
  Likelihood: medium. Mitigation: EP-M1 probes `cargo verus` in place; any
  override is scoped to the verifier route and leaves ordinary gates unchanged,
  or the tolerance triggers.
- Risk: the three compilers that must accept the kernel differ: the repository
  nightly (1.100.0-nightly, 2026-08-26), Kani 0.67.0's nightly-2025-11-21, and
  Verus's Rust 1.98.0. Severity: medium. Likelihood: medium. Mitigation: EP-M1
  records `rustc -vV` for each; the kernel restricts itself to their
  intersection; workspace `[lints.rust]` entries are checked against each
  toolchain because `unknown_lints = "deny"` turns a newer lint into an error.
- Risk: `make package` breaks once path dependencies exist, and its contract
  test uses a stub Cargo, so nothing notices. Severity: medium. Likelihood:
  high. Mitigation: path dependencies carry `version = "0.1.0"`; EP-M2 runs the
  real `make package` and decides whether the route becomes `-p combobulate`.
- Risk: `trybuild` in `tests/cardinality_probe_ui.rs` builds a generated crate
  in its own target directory with the current features, compiling Polars
  again. Severity: medium. Likelihood: medium. Mitigation: EP-M1 measures it;
  the UI test runs only in the native-only test route.
- Risk: repository contract tests assert exact Cargo argument vectors and
  break when routes change. Severity: medium. Likelihood: certain. Mitigation:
  route changes and their contract assertions land in one commit; the oversized
  `tests/make_gate_order.rs` is split first.
- Risk: the real Kani output format for a timeout, a skipped harness, or an
  undetermined result differs from the parser design. Severity: medium.
  Likelihood: medium. Mitigation: the corpus is captured first (EP-M1) and the
  extractor is written against it (EP-M5); unknown structure fails closed as
  `tool-error`.
- Risk: a text scanner cannot see identifiers that macros construct, so the
  trust audit could miss an item. Severity: medium. Likelihood: low.
  Mitigation: the scanner fails closed on `include!`, out-of-tree `#[path]`,
  `paste!`, and `concat_idents!`, and in procedural-macro crates it also
  reports vocabulary inside string literals.
- Risk: `trust_audit.py` and `kani_log.py` grow past 400 lines. Severity: low.
  Likelihood: high. Mitigation: planned module split (lexer, matcher, command;
  extractor, decision function, shell adapter).
- Risk: `rstest-bdd` 0.6.0 or `googletest` 0.14.3 requires an `rstest` release
  newer than the pinned 0.27.0. Severity: low. Likelihood: medium. Mitigation:
  checked in EP-M3; a bump to 0.28.0 is pre-authorized, anything larger
  escalates.
- Risk: the Verus archive omits Z3, leaving an uncontrolled solver selection.
  Severity: medium. Likelihood: observed. Mitigation: the probe selects
  `z3-solver==4.16.0.0`, checks Z3 4.16.0, and records its binary digest.
  Hosted installation remains unconfirmed until the measurement workflow runs.
- Risk: `prover-tools kani install` runs
  `cargo install --locked kani-verifier --version 0.67.0` and
  `cargo kani setup`, which downloads the Kani bundle without a repository-side
  digest check. Severity: medium. Likelihood: certain. Mitigation: the trusted
  computing base records the crates.io `kani-verifier` source and the
  unverified bundle download, with the release asset digest kept for reference
  in the profile record; a verified bundle option is proposed upstream to
  `rust-prover-tools`.
- Risk: `prover-tools` has no `cargo verus` route; `prover-tools verus run`
  verifies a single proof root. Severity: medium. Likelihood: certain.
  Mitigation: the EP-M1 wiring probe includes the estate's single-root pattern
  (DL-22); a crate-based wiring is selected only if it is decisively better,
  and then its `cargo verus` route is proposed upstream before task 1.2.4.
- Risk: `prover-tools verus install` unpacks about 456 MB into
  `.verus/<version>/` in each worktree, where Markdown, spelling, and Whitaker
  scans could find it. Severity: low. Likelihood: certain. Mitigation: ignore
  `.verus/` in `.gitignore` and in the Markdown lint configuration, and record
  the per-worktree disk cost in `docs/developers-guide.md`.
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
- [x] (2026-10-22) Draft this ExecPlan (commit `d2361d6`).
- [x] (2026-10-22) Community-of-experts review by four reviewers; findings
  applied in this revision (see `Design review record`).
- [x] (2026-10-22) Sponsor accepted the recommended option for all eight
  sponsor decisions.
- [x] (2026-10-27) Sponsor approved the plan and directed Q3 to join
  `in_scope_questions`, with the decision based on implementation findings.
- [x] (2026-10-28) EP-M1 in progress. Red prover-wiring contracts failed as
  expected (`/tmp/red-prover-tools-combobulate-epm1.out`): missing pins,
  targets, and explicit formal placeholders. Prototype: toolchain, profile, and
  hosted-cost probes.
- [x] (2026-10-28) EP-M1 local probes: repeated installs, 14 Kani observations
  with matching source/log digests, and exact positive/mutant Verus counts.
  `make kani-log-corpus` and `make verus-probe` passed; logs are under
  `/tmp/kani-corpus-combobulate-epm1.out` and
  `/tmp/verus-probe-combobulate-epm1.out`.
- [x] (2026-10-28) Polars 0.55.2 with only `lazy` passed its library, doctest,
  and UI checks. Eleven prover command contracts passed after Red evidence in
  `/tmp/red-prover-execution-status-combobulate-epm1.out` exposed a swallowed
  execution failure. Source and stderr copies retain the existing UI oracle.
- [x] (2026-10-28) Existing Python Make fixtures now copy the prover pin;
  `/tmp/green-docstring-fixture-combobulate-epm1.out` passes all three tests
  after design-check exposed their missing temporary-directory resource.
- [x] (2026-10-28) Count regression: inflated positive and mutant summaries
  failed before the fix; the scratch correction passed all eleven contracts.
  Evidence: `/tmp/red-count-review-combobulate-epm1.out`.
- [x] (2026-10-30) Solver selection: the default `z3` name now resolves the
  pinned `z3-solver==4.16.0.0` distribution before any `PATH` discovery, while
  an explicit solver name is still checked. `test_verifier_solver` failed
  against the previous source (`/tmp/red-durable-solver-combobulate-epm1.out`)
  and passes after the fix (`/tmp/green-durable-solver-combobulate-epm1.out`).
  The regenerated corpus keeps matching source and log digests.
- [x] (2026-10-31) Hosted measurement run `41148253840` measured rustdoc,
  clippy, nextest, coverage, and UI cold runs; its whitaker and verifier-free
  jobs failed on environment defects. The verifier-free image now installs
  `libatomic` (reproduced Red at `/tmp/epm1-verifier-free-red.log`; guarded by
  `scripts/tests/test_verifier_free_container.py`), and the measurement
  workflow pins `whitaker-installer` 0.2.11 so the dylint 6.0.1 driver is not
  built (DL-29). A replacement run is required before the go/no-go decision.
- [x] (2026-10-31) Hosted measurement run `41163302274` passed all seven jobs on
  head `4d4f031`: six routes cold three times each, plus verifier-free
  isolation. The go/no-go rule passes (DL-30); per-route timings, memory, and
  target sizes are recorded in `Artefacts and notes`.
- [x] EP-M1 hosted costs and verifier-free isolation; publish the measurement
  workflow, collect its artefacts, and apply the go/no-go rule before EP-M2.
- [ ] EP-M2. Workspace, crate boundaries, and dependency-direction checks.
- [ ] EP-M3. Feature profiles, `BuildProfile`, gate profiles, and CI shape.
- [ ] EP-M4. Profile record, pin consistency, and ADR-0010.
- [ ] EP-M5. Trust-audit scanner, Kani log parser, and gate binding.
- [ ] EP-M6. AC-04 measurement, documents, decisions, and roadmap tick.

Each Red step records its log path and the names of the failing tests here. A
Red state is never committed on its own, because it fails `make test`; it is
committed together with its Green change.

## Surprises & discoveries

- EP-M1 observations (2026-10-28): `DataFrame::new` in Rust Polars 0.55.2
  requires an explicit height. The `lazy` feature alone supports the required
  Int64 and lazy-collection path. Kani can return zero with an unsatisfied
  cover; statuses therefore remain transport checks, not proof verdicts. Its
  verbose CBMC command omits an explicit unwinding-assertion flag, so that
  capability remains inconclusive despite the observed failed unwind check.

- Observation: Kani 0.68.0 and newer `vstd` releases exist, but the
  pre-registered controls name Kani 0.67.0 and Verus 0.2026.09.06.8dea4a2.
  Evidence: `cargo search kani-verifier` reports 0.68.0; the AC-01, AC-02,
  AC-04, and AC-07 environments list the older pins. Impact: the pins stay.
- Observation: Kani's `--harness-timeout` exists in 0.67.0 but is experimental
  and requires `-Z unstable-options`. Evidence: `cargo kani --help`. Impact:
  the timeout corpus case uses that flag, and the capability record marks it
  `tested` with an experimental qualifier.
- Observation: the Verus binary used for calibration is a local source build
  under `~/.local/share/cuprum-verus-0.2026.09.06.8dea4a2`, and no Z3 binary is
  installed outside `/tmp`. Evidence: `verus --version` and a filesystem
  search. Impact: proof-tool installation must be scripted from release assets.
- Observation: the published `vstd` release dated 2026-09-06
  (`0.0.0-2026-09-06-0133`) is the candidate match for Verus
  0.2026.09.06.8dea4a2, but date proximity is not identity. Evidence: crates.io
  version list. Impact: EP-M1 confirms the match from the release contents.
- Observation: Polars 0.55.2 is the newest Rust release and declares no
  `rust-version`. Evidence: `cargo info polars@0.55.2`. Impact: its supported
  compilers are established only by building it in each profile.
- Observation: control AC-07 freezes `.github/workflows/ci.yml` by digest, and
  the checker accepts exactly one `ci-build-test` workload and reads only the
  `build-test` job's runner and timeout. Evidence:
  `scripts/docs_validation/acceptance_registration.py`,
  `scripts/docs_validation/ci_controls.py`,
  `scripts/docs_validation/preregistration.py`. Impact: any CI change needs an
  amendment and checker changes (DL-14).
- Observation: hosted CI never runs `make test`; its test step is the shared
  `generate-coverage` action with default features. Evidence:
  `.github/workflows/ci.yml` lines 105-126. Impact: profile checks need their
  own hosted steps, and coverage features must be set explicitly.
- Observation: `leynos/rust-prover-tools` (at
  `9c4a27a86c678ceac1155404f45d95ee4a14a172`, no tagged release) already
  provides `prover-tools kani install`, `kani check-version`, `kani exec`,
  `verus install`, and `verus run`. `kani exec` qualifies Kani 0.67.0 on Linux
  x86_64 for repositories like this one: it strips the Cranelift backend, the
  `mold` linker selection, and frontend threads from the child, keeps
  `RUSTC_WRAPPER` admission wrappers, and supports a `cargo-llvm-cov` parent.
  Evidence: its README and users' guide. Impact: the plan drops its own
  installer and the in-place Kani risk largely dissolves; EP-M1 still records
  the observed behaviour (DL-21).
- Observation: the trust audit is read from the record itself, and
  `VerifiedLogResult` carries no trust facts. Evidence:
  `scripts/docs_validation/evidence_gate.py` lines 73-98, 192-199, 303. Impact:
  registering a parser without binding the audit would let a fabricated audit
  reach `bounded` (DL-16).
- Observation (2026-10-31): hosted measurement run `41148253840` passed five of
  seven jobs. `measure-profile (whitaker)` failed because
  `dylint_driver v6.0.1` builds its driver by checking out `master` in
  `rust-lang/rust-clippy`, whose default branch was renamed to `main` on
  2026-10-28. `whitaker-installer` 0.2.9, the shared action's default and the
  pin the frozen `ci.yml` uses, ships cargo-dylint 6.0.1; 0.2.11 ships 6.3.0,
  whose `dylint_internal` no longer checks out `master`. Evidence: the run log,
  `Cargo.lock` at both whitaker tags, and the two `dylint_internal` sources.
  Impact: the frozen `ci.yml` whitaker route is broken upstream for reasons
  unrelated to this candidate; the measurement workflow pins installer 0.2.11
  with an independently verified digest, and the `ci.yml` bump belongs to the
  AC-07 amendment at EP-M3 (DL-29). Local `make lint` passes because the local
  driver is cargo-dylint 6.3.0.
- Observation (2026-10-31): the same run's `verifier-free` job failed before
  compiling the probe. The pinned `mold` binary is dynamically linked against
  `libatomic.so.1`, which Rocky's clang package does not install, so every
  container link exited 127 with "cannot open shared object file". Reproduced
  locally against the committed image recipe
  (`/tmp/epm1-verifier-free-red.log`); adding `libatomic` to the recipe makes
  the wrapper link and run (`LINK_AND_RUN_OK`). Impact: the recipe installs
  `libatomic` and a regression test guards the package list.
- Observation (2026-10-31): after both repairs, hosted run `41163302274` passed
  all seven jobs. Every route completed three cold runs; Whitaker's first run
  paid a 34 s driver build (57.71 s against 23.10 s and 27.23 s warm), setup
  took 61-80 s per job, and Clippy after rustdoc took 13.08 s, confirming that
  those routes share dependency metadata. The verifier-free job reported
  `status: pass` with exit 0 after proving `verus`, `cargo-kani`, and `~/.kani`
  absent inside the container. Impact: the go/no-go rule is satisfied and the
  milestone proceeds to EP-M2.

## Decision log

- DL-30 (2026-10-31). Hosted cost go/no-go: proceed. All six routes passed
  three cold runs and verifier-free isolation passed on a fresh runner.
  Predicted job size is the slowest cold run plus fixed setup overhead; the
  largest is the UI route at 134.23 s + 73 s = 207 s, inside the 6-minute
  ceiling, and peak memory is 2.10 GiB, far below the 12 GiB stop. Single-root
  Verus wiring and the in-place Kani run already succeeded without weakening
  the ordinary build standard (DL-24, DL-26). Evidence: hosted run
  `41163302274`, `Artefacts and notes`, and
  `tools/verifier-fixtures/verus-wiring-probe/verifier-free-hosted.json`.
  Date/Author: 2026-10-31, implementation agent.

- DL-29 (2026-10-31). Repair the hosted measurement without touching the frozen
  CI. Measure the Whitaker route with `whitaker-installer` 0.2.11 (cargo-dylint
  6.3.0), because 0.2.9's dylint 6.0.1 driver cannot build after the rust-clippy
  `master` to `main` rename; the digest `a32a665d…e5410236` was verified by an
  independent download. Leave `.github/workflows/ci.yml` unchanged: its
  installer bump is a required job change and lands with the sponsor-approved
  AC-07 amendment at EP-M3. Install `libatomic` in the verifier-free image so
  the pinned `mold` linker can run. Rationale: both failures are environment
  defects, not candidate behaviour, and measuring the runnable route is what
  the job-split prediction needs. Date/Author: 2026-10-31, implementation agent.
- DL-28 (2026-10-30). The sponsor raised the EP-M1 changed-line limit to 3,600
  so the solver-selection fix, its durable regression test, and the regenerated
  verifier logs can land in one gated commit. The fix resolves the pinned Z3
  distribution whenever the default `z3` name is used and keeps version
  checking for an explicitly named solver, which is the smallest change that
  satisfies the review finding without weakening the calibrated-solver rule.
  Date/Author: 2026-10-30, implementation agent at the sponsor's direction.
- DL-27 (2026-10-28). Review fixes exact counts, pins, and solver selection.
  Retain literal command provenance and the DL-21/VO-15 Kani preflight. The
  proposed complexity/NumPy rules have no repository instruction basis; retain
  existing interfaces. Duplicate findings share these dispositions.

- DL-24 (2026-10-28). The pinned helper refuses the existing backend keys with
  `Kani exec cannot prove isolation of Cargo backend configuration`. The
  explicit direct probe route uses the matching SDK's LLVM backend and runtime
  in the child, preserves compiler admission, and changes no ordinary Cargo
  configuration or executable body. Installation/version checks stay with the
  helper. Log: `/tmp/kani-first-combobulate-epm1.out`.
- DL-25 (2026-10-28). The checked Verus archive contains no Z3 executable.
  Use the pinned `z3-solver==4.16.0.0` tooling distribution, independently
  check Z3 4.16.0, and pass its resolved executable to the helper. This is a
  solver transport choice, not a solver-version or control-threshold change.
- DL-26 (2026-10-28). `cargo-verus` omits function-selection arguments from
  its fingerprint; refresh the candidate timestamp before each positive and
  mutant run. A cached zero-exit run without a fresh count is not evidence.
  Macro, optional-attribute, and single-root wiring passed exact positive and
  mutant counts; companion wiring could not see its ordinary dependency's
  specification. Prefer single-root wiring because it adds no kernel Cargo
  dependency. Hosted costs and verifier-free isolation remain pending.

- DL-01. Decision: the root package remains the `combobulate` facade and also
  becomes the workspace root, with members under `crates/`,
  `exclude = ["tools"]`, and `default-members` listing all three packages.
  Rationale: the repository contract tests in `tests/` already belong to the
  root package, and the Make, coverage, packaging, and Whitaker contracts are
  written against it; a virtual root would move all of them for no semantic
  gain. The exclusion is needed because the calibration probe is a path
  dev-dependency with its own `[workspace]` table. Date/Author: 2026-10-22,
  planning agent.
- DL-02. Decision (direction accepted by the sponsor, 2026-10-22; D16 itself
  is accepted after EP-M4): ADR-0010 records the crate boundary, dependency
  direction, feature profiles, gate feature lists, the proof-dependency
  allowlist for task 1.2.4, the selected Verus wiring, and the
  supported-toolchain set. It resolves candidate subjects CA3 and CA5 and
  answers ToR Q3 with a supported-toolchain set rather than one MSRV. A new
  decision is used because accepted decisions are append-only
  (`scripts/docs_validation/freeze.py`); superseding D07 would restate all
  eight candidate dispositions. The `adr` disposition schema has no `bet`
  field, so CA5's link to B01 is carried by ADR-0010, which states that B01 can
  still falsify the kernel in task 1.2.4. Rejected alternative: a separate
  `combobulate-polars` adapter crate (see DL-19). Date/Author: 2026-10-22,
  planning agent.
- DL-03. Decision (accepted by the sponsor, 2026-10-22): CI shape for the
  Polars-enabled profile. Options: (A) one `build-test` job with Polars in
  every route, which risks the hard timeout on every cold cache; (B) keep
  `build-test` on the native-only profile and add parallel Polars-enabled lint
  and test jobs, each sized from hosted measurements; (C) defer the facade's
  Polars dependency to task 1.2.6, which contradicts this task's success
  criterion. Recommended: B, with GitHub Actions sccache, coverage and Whitaker
  target caches, and cache saves only on `main`. Every option edits `ci.yml`
  and so needs DL-14. Coverage keeps measuring the native-only profile;
  `coverage-main.yml` changes in the same commit so that its baseline uses the
  same features. Date/Author: 2026-10-22, planning agent.
- DL-04. Decision: the kernel is `#![no_std]` without `alloc` and declares no
  dependency in this task. Its only item is `TargetFacts`, which reports the
  target's `usize` width as a constant evaluated for the compilation target.
  Rationale: technical design §3 asks the kernel to avoid unnecessary
  allocation and external state, and §18.1 forbids substituting the host's
  pointer width for the target's. Allocation can be admitted later only by an
  ADR-0010 amendment. Date/Author: 2026-10-22, planning agent.
- DL-05. Decision (accepted by the sponsor, 2026-10-22): `combobulate-macros`
  is created now as a `proc-macro = true` crate with no exported macro and no
  dependency; the facade's default `macros` feature enables it. Rationale: the
  task requires the macro boundary to exist, and its wiring and build cost
  belong in the profile record and AC-04, but adding `syn` or a placeholder
  macro before task 2.3.1 would be speculative. Alternative: defer the crate,
  which narrows this task's stated scope. Date/Author: 2026-10-22, planning
  agent.
- DL-06. Decision: the macro crate must not depend on the kernel, and the
  kernel may not appear in any build-dependency or procedural-macro closure.
  Rationale: a procedural macro and a build script run on the host, so
  host-side kernel evaluation would substitute host facts for target facts
  (technical design §18.1). Date/Author: 2026-10-22, planning agent.
- DL-07. Decision (accepted by the sponsor, 2026-10-22): task 1.2.1 builds and
  registers the Kani parser only; task 1.2.4 builds and registers the Verus
  parser. Rationale: the roadmap's three named log classes are Kani outcomes,
  and task 1.2.4 registers parsers "for this kernel's evidence". The
  trust-audit scanner covers both vocabularies now. Date/Author: 2026-10-22,
  planning agent.
- DL-08. Decision: the parser and scanner are Python modules in
  `scripts/docs_validation/`, beside the gate they feed. Rationale: the gate,
  `VerifiedLogResult`, and `AdmissionContext` are Python, and ADR-0009 keeps
  the Python gate as the reference model until task 1.2.4. Helper sweep:
  `scripts/docs_validation/grammar.py` `tokenize` recognizes the macro-grammar
  corpus only, does not handle comments or literals, and is due for deletion
  after task 2.3.1, so it is not reused. Date/Author: 2026-10-22, planning
  agent.
- DL-09. Decision: a skipped harness is defined against a committed harness
  manifest: any claim harness listed in the manifest without a result in the
  log is skipped. The manifest is bound by digest as a result artefact of the
  record, and `make design-check` requires its harness set to equal a lexical
  scan of `#[kani::proof]` and `#[kani::proof_for_contract]` items in the
  corpus sources. Rationale: a log cannot show what it omits; the bound
  manifest makes absence observable. Date/Author: 2026-10-22, planning agent.
- DL-10. Decision: the 1.2.1 Kani parser always derives `partial` bounds, so
  no 1.2.1 record can reach `proof` through Kani. Deriving `type-complete`
  moves to task 1.2.4 with its own mechanical rule (every harness input is
  `kani::any()` of the declared type, the scanner finds no assumption or stub
  in the harness, unwinding checks are observed) and ADR-0009 amendment.
  Rationale: a manifest declaration of type-completeness would be
  self-reporting on the one field that separates `proof` from `bounded`.
  Date/Author: 2026-10-22, planning agent.
- DL-11. Decision: no glam feature is declared in this task. Rationale: glam is
  opt-in and has no consumer until task 5.2.1; an unexercised feature would be
  an untested profile. The kernel boundary forbids glam regardless.
  Date/Author: 2026-10-22, planning agent.
- DL-12. Decision (accepted by the sponsor, 2026-10-22): the draft PR title is
  `Plan: establish the workspace and pinned profiles (1.2.1)`. Rationale: the
  request asked for `(1.1)`, but this task is roadmap item 1.2.1 and earlier
  PRs used the number of the item they delivered. Date/Author: 2026-10-22,
  planning agent.
- DL-13. Decision: neither Verus, Kani, nor `proptest` is used to establish a
  property of the Rust code in this task. Rationale: `TargetFacts` and
  `BuildProfile` are finite and definitional, so a lemma, harness, or generated
  property over them would be vacuous; the profile matrix is finite and checked
  exactly. The contractual logic introduced here is the Python parser's
  decision function, which receives an exhaustive enumeration check instead
  (VO-11b). Verus and Kani run only as probe subjects and log producers.
  Date/Author: 2026-10-22, planning agent.
- DL-14. Decision (direction accepted by the sponsor,
  2026-10-22; final text approved at EP-M3): the AC-07 amendment described in
  `Sponsor decisions` item 2, with matching changes to `ci_controls.py` and
  `preregistration.py` so that the checker accepts several required jobs and
  reads each job's runner and timeout. Date/Author: 2026-10-22, planning agent.
- DL-15. Decision (direction accepted by the sponsor,
  2026-10-22; final text approved at EP-M4): the AC-04 amendment described in
  `Sponsor decisions` item 3. If the selected Polars feature set differs from
  the calibrated `lazy` set, the amendment records the difference. Date/Author:
  2026-10-22, planning agent. On 2026-10-28 the sponsor directed that the
  amended measurement follow the rebased target configuration: warm builds
  reuse the target directory with incremental compilation disabled. Record the
  changed workload and environment in the amendment before measurement.
- DL-16. Decision (direction accepted by the sponsor,
  2026-10-22; final text approved at EP-M5): amend ADR-0009 so that
  `AdmissionContext` also carries scanner-derived trust audits. The I/O shell
  checks the digest of every source file the harness manifest names, runs the
  scanner over them, and passes a `VerifiedTrustAudit`; `abstract_record`
  derives `trust = 'unaudited'` unless an audit bound to the record's sources
  has an item multiset `(item, location)` equal to the record's. The shell
  accepts only Git-tracked log, manifest, and source paths inside the
  repository. A record whose `method.tool` names a registered parser must have
  `evidence_kind` deductive or bounded, so a Kani run cannot be relabelled as a
  test to bypass the parser. Date/Author: 2026-10-22, planning agent.
- DL-17. Decision (direction accepted with DL-16): the matching rule for the
  ADR-0009 vocabulary. The scanner lexes Rust, skips comments and literals, and
  reports an identifier as a trusted item when it is (i) a Kani vocabulary item
  reached through a path or `use` tree rooted at `kani`, including
  `kani::any_where` and `#[cfg_attr(kani, kani::stub(..))]`; (ii) a Verus
  vocabulary item inside a `verus!` body, a `#[verifier::…]`, `#[verifier(…)]`,
  `#[verus_verify(…)]`, or `#[verus_spec(…)]` attribute, a `cfg_attr` carrying
  one of those, or a `use` tree rooted at `vstd` or `verus_builtin`; or (iii)
  any unqualified vocabulary identifier in a file that imports from `kani`,
  `vstd`, or `verus_builtin` by glob or alias. An unqualified `should_panic`,
  `assume`, or `external` in a file with no such import is ordinary Rust and is
  not reported. The Verus list also covers `external_trait_specification`,
  `assume_specification[…]`, and `exec_allows_no_decreases_clause`.
  Date/Author: 2026-10-22, planning agent.
- DL-18. Decision: ordinary Make gates stop using `--all-features`. Each gate
  route runs per gate profile with an explicit feature list (native-only:
  `--no-default-features`; Polars-enabled: default features), selected by
  `GATE_PROFILE`, which defaults to running both locally. Rationale: a future
  `verus` feature would otherwise enter every ordinary route, and
  `--all-features` never lints `cfg(not(feature = "polars"))` code.
  Date/Author: 2026-10-22, planning agent.
- DL-19. Decision: the Polars code stays in a crate-private facade module,
  `src/polars_backend.rs`, rather than a separate `combobulate-polars` crate.
  Rationale: a separate crate saves no CI time (the default build still pulls
  Polars), contradicts the three-crate arrangement in technical design §3, and
  would force a premature `combobulate-core` split once the adapter needs
  facade-owned traits. VO-14 enforces confinement instead. ADR-0010 lists the
  adapter crate as a rejected option, to be revisited when task 1.2.6 or 4.2.1
  needs facade-owned traits in the adapter. Date/Author: 2026-10-22, planning
  agent.
- DL-20. Decision: delivery uses one stacked PR per milestone (the
  `github-stacks` skill), with a commit after each gated Green or Refactor
  step. Date/Author: 2026-10-22, planning agent.
- DL-21. Decision: prefer `rust-prover-tools` as installer and runner
  for Kani and Verus, following the `kani` and `verus` skills' project
  on-ramps. Pins live in `tools/kani/VERSION`, `tools/verus/VERSION`,
  `tools/verus/SHA256SUMS`, `tools/verus/README.md`, and
  `tools/rust-prover-tools/REF` (repository, branch, a 40-character `ref`, and a
  `verify` command that fetches the pinned commit). Make targets
  `install-kani`, `kani-check`, `install-verus`, and the probe targets delegate
  to `$(PROVER_TOOLS)`; every proof target depends on `kani-check`. Kani runs
  through
  `prover-tools kani exec --installation <kani-0.67.0> --cwd <proof package>`
  from the proof package, never with `--manifest-path`. Rationale: the user
  directed that the plan use these helpers; they already solve pinning,
  checksum verification, toolchain discovery, and this repository's build
  standard, and the estate's reviewers reject repository shell installers.
  Date/Author: 2026-10-22, planning agent at the sponsor's direction.
- DL-22. Decision: the EP-M1 Verus wiring probe adds candidate (d), the
  estate's established single-root pattern: production source carries
  `cfg_attr(verus_keep_ghost, …)` specification attributes that are inert in
  ordinary builds, and a proof root under `verus/` imports the production
  module with `#[path]`, run by `prover-tools verus run --proof-file`. A design
  check asserts that each `#[path]` target and the referenced items still
  exist. Rationale: (d) adds no dependency to the kernel, so VO-1 and VO-3 hold
  unchanged, and Verus compiles the same production source rather than a mirror
  (technical design §17.2). Candidates (a) to (c) remain for comparison; (d) is
  preferred if it passes the same exact-count acceptance. Date/Author:
  2026-10-22, planning agent.
- DL-23. Decision: formal jobs stay outside `ci.yml` in this task. Kani and
  Verus run in a separate, non-required workflow on a weekly schedule and on
  manual dispatch; a pull-request `kani-smoke` job arrives with task 1.2.4's
  first shipped harnesses. Until then, `make kani` and `make kani-full` are
  explicit stubs that print `FORMAL-SKIP: <target> not yet implemented` and
  exit 0 unless `FORMAL_STRICT=1`. Rationale: there is no shipped harness to
  run, and a required formal job would enter AC-07's amended workload for no
  evidence. Date/Author: 2026-10-22, planning agent.

## Design review record

Four reviewers covered the panel's lenses on commit `7d31060` on 2026-10-22:
structural integrity and contracts; verification and gate soundness; scaling,
cost, and failure modes with a pre-mortem; and alternatives, long-term
viability, and governance. Verdict: proceed with conditions. Every finding was
applied in this revision.

The design flaws found, and their resolutions, were these. The draft's checks
trusted `cargo metadata`'s resolve graph, which is not the built feature graph;
the checks now use `cargo tree` for closures and `cargo metadata --no-deps` for
declared edges. Inheriting `license` and `publish` would have broken the
package-policy checker; the fields stay literal. `make package` would break
silently; path dependencies get versions and the real route runs in EP-M2.
Editing `ci.yml` fails `make design-check` without an AC-07 amendment, under
any CI option; DL-14 adds the amendment and checker changes. AC-04 was bound to
the calibration probe, not the facade; DL-15 adds its amendment.
`tests/make_gate_order.rs` already breaks the 400-line limit; EP-M2 splits it
first. The vocabulary would have flagged ordinary Rust; DL-17 states the
matching rule. The trust audit remained self-reported after registration; DL-16
binds it. The mutation property could pass because mutants failed the digest
check first; VO-11 now recomputes digests. The hosted-cost prediction used
medians and a factor calibrated on Python suites; EP-M1 now measures on a
hosted runner and sizes jobs by the slowest run.

The pre-mortem scenarios (cache thrash, Polars pin churn, runner resource
exhaustion) appear in `Risks` with mitigations. The strongest alternative, a
separate Polars adapter crate, is recorded and rejected in DL-19.

## Outcomes & retrospective

EP-M1 is complete. Local probes, the Kani corpus, and the measurement workflow
are implemented and gated, and hosted run `41163302274` measured every route
and proved verifier-free isolation. Single-root Verus wiring preserves a
dependency-free ordinary kernel and passed its seeded mutant check. The
captured corpus supports the later parser work; no parser is registered and no
product theorem is claimed. The predicted required-job sizes are recorded in
DL-30 for the EP-M3 CI shape.

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
Hosted CI (`.github/workflows/ci.yml`, job `build-test`, 8-minute timeout) runs
the formatting, spelling, audit, and lint gates, then tests through the shared
`generate-coverage` action rather than `make test`.

The design-contract checker is the repository's governance machine. Decisions
live in `spec/decisions.json` and are rendered into
`docs/decision-register.md`. The roadmap in `docs/roadmap.md` is exported to
`spec/roadmap.json`; a task may be ticked only when its prerequisites are
ticked, its completion record in `spec/task-completion.json` cites accepted
decisions and resolvable artefacts, and every linked proof-obligation component
is satisfied (rule MS-4 in ADR-0009). No component in
`spec/proof-obligations.json` is linked to task 1.2.1. Acceptance controls in
`spec/acceptance-controls.json` freeze their workload sources by SHA-256; a
changed source fails the checker until a sponsor-approved amendment records the
new digest (ADR-0008).

The evidence gate in `scripts/docs_validation/evidence_gate.py` abstracts a
proof-evidence record (schema version 2, `spec/proof-evidence.schema.json`) to
ten finite fields and admits it at a level: `proof`, `bounded`, `tested`,
`restricted`, or `rejected`. A verifier verdict counts as parsed, rather than
self-reported, only when a registered log parser supplies a matching
`VerifiedLogResult` for the record's tool, log path, and digest. The registry
`spec/evidence-reason-codes.json` registers no parser today, so every verifier
record is rejected with `verdict-self-reported`. The fixture
`scripts/tests/fixtures/evidence/log-parsers.json` pretends a Kani parser
exists so tests can reach the `bounded` level.

A calibration probe in `tools/calibration/cardinality-probe/` is a standalone
crate with its own `[workspace]` table, used to measure verifier and build
costs for the acceptance controls. It is frozen and is not the shipped kernel.

Terms used in this plan:

- Facade: the `combobulate` crate that consumers depend on.
- Semantic kernel: `combobulate-kernel`, the small crate that will own checked
  shape, index, cost, and admission rules shared by runtime, constant
  evaluation, Kani, and Verus.
- Profile: a named combination of crates, features, toolchain, target, and
  command. This task defines four: `native-only` (facade with
  `--no-default-features`), `polars-enabled` (facade with default features,
  which are `macros` and `polars`), `proof-kani` (kernel and native-only facade
  under `cargo kani`), and `proof-verus` (kernel under `cargo verus`, wiring
  selected in EP-M1).
- Gate profile: the profile a Make gate route runs under, selected by
  `GATE_PROFILE` (`native-only`, `polars-enabled`, or both).
- Capability record: an entry stating what a pinned tool did on a probe, with
  a status of `documented` (stated upstream, not exercised), `tested`
  (exercised here and behaved as recorded), `unsupported` (exercised and
  refused or failed), or `inconclusive` (exercised without a decisive result).
  Roadmap task 1.2.6 uses the same four statuses for Polars.
- Trusted computing base (TCB): the components whose correctness a result
  assumes rather than checks, such as the compiler, the verifier, and the
  solver.
- Harness manifest: a committed JSON file listing a corpus crate's Kani
  harnesses, each with a role (`claim` or `control`), its declared covers, and
  for a control the property it must fail; it also lists the source files and
  their digests. Its harness set is checked against the sources.
- Component architecture document: technical design §3 and its component
  table; this repository has no separate architecture document.

## Conformance basis

EP-M1 adds no shipped API or dependency and leaves frozen calibration sources
and `ci.yml` unchanged. Hosted budget acceptance remains pending.

- Terms of reference: `docs/terms-of-reference.md`, revision 0.2 of 6 October
  2026, tracing G1, G2, G6, G7, G8; S7 (native-only, proof-capable, and
  Polars-enabled profiles within budgets); C1, C5, C7, C8; Q3 (MSRV and feature
  matrix); Q9 (verification profiles; no Rust feature inferred from Python
  numbering); the dependency-baseline requirement at line 223.
- Technical design: `docs/technical-design.md`, revision 0.2, 6 October 2026.
  Traced items: §3 package boundary and component table; R5, R7, R8; §10
  storage and Polars; §15 row 6, GAP4, GAP7, GAP8, GAP9; §17.1, §17.2 (trust
  audit and verdict parsing), §17.7 (profiles; no proof-feature body
  substitution), §17.8 (pinned tools, CI cost); §18.1 (target facts, not host
  facts); §19.1 (Rust release selected independently of Python numbering).
- Roadmap: `docs/roadmap.md` revision 0.2, task 1.2.1 and its detail on the
  trust-audit scanner and log parser; dependants 1.2.2, 1.2.4, 1.2.6.
- Bets: B01 (one executable semantic core), B05 (streaming Polars contract).
- Decisions: D04, D05, D06 (MSRV left to Q3 and 1.2.1), D07 (CA3 and CA5
  deferred to 1.2.1), D11, D12, D15; proposed D16.
- ADRs: ADR-0004, ADR-0005, ADR-0008, ADR-0009 (amendment proposed);
  proposed ADR-0010.
- Controls: AC-01, AC-02 (probe budgets), AC-04 (build budgets, amendment
  proposed), AC-07 (pull-request critical path, amendment proposed).
- Governing standards: `AGENTS.md`, `docs/documentation-style-guide.md`,
  `docs/developers-guide.md`, `docs/scripting-standards.md`.

Trace chains:

```plaintext
TD §3, §15 row 6, CA5 -> D16/ADR-0010 -> EP-M2 -> tests/workspace_boundaries.rs::kernel_excludes_backends
TD §18.1, DL-06 -> EP-M2 -> tests/workspace_boundaries.rs::kernel_never_host_compiled
TD §3, ToR line 152 -> EP-M2, EP-M3 -> tests/workspace_boundaries.rs::ordinary_profiles_exclude_verifiers
ToR S7, TD §3 -> EP-M3 -> tests/features/build_profiles.feature, tests/native_consumer_e2e.rs
TD §19.1, ToR Q9, B05 -> EP-M3, EP-M4 -> spec/toolchain-profiles.json -> scripts/tests/test_toolchain_profiles.py
ToR Q3, D06 -> D16/ADR-0010 -> EP-M4 -> spec/toolchain-profiles.json::supported_toolchains
TD §17.2, ADR-0009, D15 -> EP-M5 -> scripts/docs_validation/kani_log/ -> scripts/tests/test_kani_log.py
TD §17.2, ADR-0009 vocabulary, DL-17 -> EP-M5 -> scripts/docs_validation/trust_audit/ -> scripts/tests/test_trust_audit.py
AC-07, DL-03, DL-14 -> EP-M3 -> .github/workflows/ci.yml profile jobs
AC-04, DL-15 -> EP-M6 -> spec/measurements/ac-04-*.json
DL-21, kani and verus on-ramps -> EP-M1 -> tests/prover_tools_contract.rs
Roadmap 1.2.1 -> EP-M6 -> spec/task-completion.json -> ticked in docs/roadmap.md
```

Gaps addressed: GAP4 (exact Rust, dependency, and feature versions selected and
recorded; stable compilation claimed only for the recorded profiles); GAP9 in
part (a parser and a bound scanner exist). GAP7 and GAP8 stay open for tasks
1.2.4 and 1.2.6. A further gap is recorded for task 1.2.4: nothing yet ties a
verifier log to a record's `binding.executable_digest` or `source_revision`.

## Verification plan

EP-M1 transport contracts also reject a failing SDK execution after a passing
version preflight; the regression was observed before its fix.

### Method selection

This task introduces dependency-direction invariants, a profile-reporting
contract, a pin-consistency invariant, and two fail-closed gate adapters. The
only contractual decision logic is the Kani parser's mapping from per-harness
facts to an admission result; it gets an exhaustive enumeration check over a
finite abstraction, mirroring how the gate itself is checked over all states.
Dependency and profile obligations are finite facts, discharged by exact checks
over Cargo's own output. The scanner and the parser's structure extractor work
over arbitrary text, so Hypothesis properties, a deterministic cross-product of
lexical cases, and a real-log corpus discharge them; `mutmut` then audits
whether those suites notice plausible defects. No Verus proof is warranted
(DL-13).

The Rust test stack is `rstest` for fixtures and tables, `rstest-bdd` for the
profile behaviour scenarios, `googletest` matchers and `pretty_assertions`
diffs for clear failures, and `insta` as the single oracle for the rendered
profile line. Dependency predicates are pure functions over injected
`cargo tree` and `cargo metadata` output, tested against canned fixtures, and
exercised once against the real workspace through `env!("CARGO")` with
`--locked --offline` after `cargo fetch --locked`, with `RUSTFLAGS`,
`CARGO_ENCODED_RUSTFLAGS`, and `CARGO_BUILD_TARGET` removed from the child
environment. The Python stack follows `scripts/tests/`: `unittest` cases run by
both `unittest discover` and `pytest`, with Hypothesis 6.168.5.

### Obligations

- VO-1, kernel excludes backends: (i) in this task the kernel's
  `cargo metadata --no-deps` dependency list is empty; (ii) durably, no package
  whose name starts with `polars` or `glam` appears in
  `cargo tree -p combobulate-kernel --all-features --target all -e all`.
  - Method: pure predicate over injected output, parameterized by the canned
    fixtures and the live workspace.
  - Artefact: `tests/workspace_boundaries.rs::kernel_excludes_backends`.
  - Evidence: red before EP-M2 because the package does not exist.
  - Non-vacuity: a canned fixture in which the kernel reaches `glam` through a
    target-specific dependency must fail naming `glam`; the same query on the
    live `polars-enabled` facade must report `polars` (VO-4).
- VO-2, dependency direction: over declared edges of every kind and target in
  `cargo metadata --no-deps`, the macro crate depends on neither the kernel nor
  any backend; the kernel depends on no member; no member has a normal or build
  dependency on the facade (dev-dependency cycles are allowed); and the kernel
  never appears in a build-dependency edge or in any procedural-macro crate's
  closure.
  - Artefact: `tests/workspace_boundaries.rs::dependency_direction_holds` and
    `kernel_never_host_compiled`.
  - Non-vacuity: the facade's normal edges to both members must be observed;
    canned fixtures with a kernel build-dependency and a macro-to-kernel edge
    must each fail.
- VO-3, ordinary profiles exclude verifiers: in `native-only` and
  `polars-enabled`, no package whose name starts with `kani`, `vstd`, or
  `verus` appears in the facade's closure. The prefix list is confirmed against
  the lock file of the EP-M1 Verus probe.
  - Artefact:
    `tests/workspace_boundaries.rs::ordinary_profiles_exclude_verifiers`.
  - Non-vacuity: a canned fixture of a facade that depends on `vstd` must fail;
    building alone would not detect a leak, because `vstd` compiles without the
    Verus binary.
- VO-4, profile separation: the `native-only` closure contains no `polars*`
  package; the `polars-enabled` closure contains `polars` at exactly the pinned
  version and features.
  - Artefact: `tests/workspace_boundaries.rs::polars_appears_only_when_enabled`.
  - Non-vacuity: the positive case witnesses the negative case.
- VO-5, profile report: `BuildProfile::current()` reports exactly the features
  compiled into the binary.
  - Method: `rstest-bdd` scenarios tagged `@native` (bound under
    `cfg(not(feature = "polars"))`) and `@polars` (bound under
    `cfg(feature = "polars")`), `insta` snapshots of the rendered line named
    per profile, and an end-to-end run of `tools/fixtures/native-consumer/`.
  - Artefacts: `tests/features/build_profiles.feature`,
    `tests/build_profiles.rs`, `tests/native_consumer_e2e.rs`,
    `tests/snapshots/`.
  - Evidence: the `@native` scenarios run in the `native-only` test route, the
    `@polars` scenarios in the `polars-enabled` route. Red before EP-M3.
  - Non-vacuity: each scenario asserts the absence of the other profile's
    backend, so a report that always or never claims Polars fails one route;
    EP-M3 confirms that `rstest-bdd` rejects a tag filter matching no scenario,
    and if it does not, a test counts the executed scenarios instead. The
    end-to-end consumer's output must equal the `native-only` snapshot.
- VO-6, target facts: `TargetFacts::current().usize_bits()` equals
  `usize::BITS` and is usable in constant context; the kernel's `lib.rs`
  declares `#![no_std]`, contains no `extern crate alloc` or
  `extern crate std`, and denies `clippy::std_instead_of_core` and
  `clippy::alloc_instead_of_core`.
  - Method: unit test, a constant assertion in a doctest, and a source check in
    `tests/workspace_boundaries.rs`.
  - Rationale: definitional; the tests guard wiring and the no-allocation
    boundary.
- VO-7, pin consistency: every pinned revision agrees across
  `spec/toolchain-profiles.json`, `rust-toolchain.toml`, `Cargo.lock`,
  `tools/kani/VERSION`, `tools/verus/VERSION`, `tools/verus/SHA256SUMS`,
  `tools/rust-prover-tools/REF`, the probe CLI PEP 723 dependency, the
  `Makefile`, the workflows, and the `environment.toolchains` of controls
  AC-01, AC-02, AC-04, and AC-07; a sweep of tracked files for each pinned
  version string finds no pin site outside the enumerated sources.
  - Artefacts: `scripts/docs_validation/toolchain_profiles.py`,
    `scripts/tests/test_toolchain_profiles.py`.
  - Non-vacuity: one test per source mutates that source's pin in a temporary
    copy and requires failure naming it; a test adds an unlisted pin site and
    requires the sweep to fail.
- VO-8, capability records are evidence-backed: every capability marked
  `tested`, `unsupported`, or `inconclusive` cites a committed probe log by
  path and SHA-256, and every digest matches.
  - Non-vacuity: a `tested` entry without a log and an entry with a wrong
    digest must both fail.
- VO-9, trust-audit soundness under DL-17: for any Rust source text, every
  trusted item in code position is reported once with its line and column;
  aliased and glob imports are covered by rule (iii); comments, string, raw,
  byte, C-string, and character literals hide nothing and report nothing;
  ordinary Rust uses outside rule (iii) report nothing; and unterminated
  comments or literals, `include!`, out-of-tree `#[path]`, `paste!`, and
  `concat_idents!` make the scan fail closed with an error, never an empty
  audit. In procedural-macro crates, vocabulary inside string literals is also
  reported.
  - Method: a deterministic, parameterized cross-product of every vocabulary
    item with every lexical context (code position, each comment form, each
    literal form, qualified, aliased, glob-imported, inside `cfg_attr`);
    Hypothesis properties over generated token streams (inserting an item in
    code position adds exactly that item; inserting inside a comment or literal
    adds nothing; arbitrary text never raises an unhandled exception).
  - Artefacts: `scripts/docs_validation/trust_audit/` (lexer, matcher, command
    modules), `scripts/tests/test_trust_audit.py`,
    `scripts/tests/fixtures/trust_audit/`.
  - Non-vacuity: the cross-product enumerates every cell; a scanner variant
    with any one vocabulary entry or lexical rule removed must fail, which the
    suite demonstrates by running against those variants; `mutmut` over the
    package reports surviving mutants, each resolved by a new test or a
    recorded equivalence.
- VO-10, shipped crates are trust-free: the scan of every workspace member's
  sources, enumerated from `cargo metadata`, reports no item.
  - Method: design-checker check `trust-audit`.
  - Non-vacuity: the same check over `tools/verifier-fixtures/` must report
    the seeded items.
- VO-11a, Kani structure extraction: the extractor turns a log into
  per-harness facts (status, failed properties with identifiers and locations,
  cover results, unwinding-check results), the version banner, the output
  format, and the summary counts, or returns a structural error for any
  unrecognized, truncated, interleaved, or count-inconsistent log.
  - Method: the real-log corpus (one log per class below) plus Hypothesis
    mutations of corpus logs: truncation, line deletion, duplicated harness
    blocks, altered summary counts, altered version banners, and interleaved
    harness blocks. Each mutant's SHA-256 is recomputed and supplied as the
    expected digest, mutation operators only degrade or break structure, and
    each test asserts that the refusal reason is structural, never a digest
    mismatch.
  - Artefacts: `scripts/docs_validation/kani_log/extract.py`,
    `scripts/tests/test_kani_log.py`, `scripts/tests/fixtures/kani_logs/`.
- VO-11b, Kani decision function: a pure function from per-harness facts and
  the manifest to
  `(outcome, bounds, witness_statuses, negative_controls, run_mode)`.
  Precedence: structural error gives `tool-error`; otherwise any claim harness
  with a failed non-unwinding property gives `counterexample`; otherwise a
  timeout gives `resource-exhausted`, as does a failure of unwinding checks
  alone; otherwise an undetermined result gives `unsupported` when Kani names
  an unsupported construct and `solver-unknown` otherwise; otherwise a claim
  harness without a result gives `skipped`; otherwise `verified`. Bounds are
  always `partial` (DL-10). Each declared cover maps to `satisfied` or
  `unsatisfied`. Each control harness maps to `rejected-as-intended` when it
  failed exactly the property the manifest expects, `rejected-otherwise` for
  any other failure, `accepted` when it succeeded, and `not-run` when it has no
  result; `#[kani::should_panic]` may not mark a control, and a harness without
  a role is a structural error. `run_mode` is `full-profile` only when the
  claim results equal the manifest claim set, the log is a single sequential
  regular-format run, and unwinding checks are confirmed enabled; otherwise
  `focused`.
  - Method: exhaustive enumeration of every combination of per-harness facts
    for up to three harnesses, checked against a data table and against
    properties: monotonicity (degrading any fact never improves the outcome),
    counterexample dominance, and `verified` exactly when every claim harness
    succeeded with every declared cover satisfied.
  - Artefacts: `scripts/docs_validation/kani_log/decide.py`,
    `scripts/tests/fixtures/kani_decision_table.json`.
  - Non-vacuity: the corpus includes a log whose completion reports success
    while a cover is unsatisfied; the suite runs the corpus against three
    deliberately broken parsers (always `verified`; success line only; manifest
    ignored) and requires all three to fail; `mutmut` over the package.
- VO-12, gate integration: a fixture record citing a committed corpus log,
  manifest, and sources reaches `bounded` only through the parser and the
  scanner. The same record with a tampered log digest, a tampered manifest
  digest, an unregistered tool, an untracked path, a mismatched derived fact, a
  fabricated empty trust audit over a harness that uses `kani::assume`, or its
  Kani run relabelled as a test, is rejected with its intended reason. The gate
  function stays pure.
  - Method: integration tests over `scripts/check_evidence.py` and
    `evidence_records.admitted_evidence`.
  - Non-vacuity: the positive record must reach `bounded`, so the tests cannot
    pass by rejecting everything.
- VO-13, registration discipline: every name in `registered_log_parsers` has a
  corpus manifest whose logs, when parsed (not by their labels), cover the
  outcomes verified, counterexample, resource-exhausted (timeout),
  some-unsatisfied witness, skipped, tool-error (truncated), and unsupported or
  solver-unknown, and whose corpus tests run in `make design-check`.
  - Method: design-checker check `log-parser-registration`.
  - Non-vacuity: a registry entry whose corpus lacks the timeout class must
    fail.
- VO-14, Polars confinement: Polars paths appear only in
  `src/polars_backend.rs` and its submodules, checked with the trust-audit
  lexer.
  - Non-vacuity: a seeded `use polars::` in a copy of `src/profile.rs` must
    fail.
- VO-15, prover-tools wiring contract: installation and version checks delegate
  through `$(PROVER_TOOLS)`; the explicitly recorded direct probe routes retain
  the pinned SDK and admission. Test the exact argument vectors, flag
  forwarding, and exit-status propagation; every proof target depends on
  `kani-check`; no recipe contains `cargo install`, `cargo kani setup`, `curl`,
  `unzip`, `sha256sum`, or `rustup toolchain install`;
  `tools/rust-prover-tools/REF` holds a 40-character `ref`;
  `tools/kani/VERSION` and `tools/verus/VERSION` are non-empty; and
  `tools/verus/SHA256SUMS` has a row naming the configured archive. The
  `FORMAL-SKIP` stubs exit 0, and exit non-zero under `FORMAL_STRICT=1`.
  - Method: Make contract tests in the style of `tests/make_gate_order.rs`,
    running each target against a recording fake executable (not `echo`)
    passed as `PROVER_TOOLS_CONTRACT_TEST=1 PROVER_TOOLS=<fake>` on the `make`
    command line, plus static checks of the recipes and pin files.
  - Artefact: `tests/prover_tools_contract.rs` with helpers in `tests/support/`.
  - Non-vacuity: the same seam supplied only through the environment must not
    unlock the fake; a fake that exits non-zero must make the target fail; a
    malformed `ref` must stop Make before any recipe runs.

### Axioms

- AXIOM-01: rustc, Cargo, and the pinned Cranelift and LLVM backends compile
  what they accept faithfully, and `cargo tree` reports the dependency graph
  that Cargo builds for the stated features, targets, and edge kinds.
- AXIOM-02: Kani 0.67.0 with its bundled CBMC and CaDiCaL reports harness
  results faithfully in its regular output format.
- AXIOM-03: Verus 0.2026.09.06.8dea4a2 with Z3 4.16.0 and the matching `vstd`
  reports verification results faithfully; Verus's trusted basis includes
  `vstd`'s specifications and any `external` items it uses.
- AXIOM-04: GitHub-hosted `ubuntu-24.04` runners match the AC environment
  description closely enough for the registered thresholds to apply.
- AXIOM-05: Polars 0.55.2's public API behaves as documented for the small
  calls made in this task; no Polars capability is claimed.
- AXIOM-06: a harness manifest's roles and expected control failures are
  reviewed repository facts, bound to the record by digest and checked against
  the sources' harness set.
- AXIOM-07: `prover-tools` at the pinned commit installs and runs exactly the
  pinned releases it reports, verifies the Verus archive digest, and, through
  `kani exec`, removes only the flags its users' guide documents. Its
  `kani install` route trusts the crates.io `kani-verifier` crate and the Kani
  bundle that `cargo kani setup` downloads.

## Plan of work

Every milestone ends with `make check-fmt`, `make lint`, `make test`,
`make design-check`, `make markdownlint`, and `make spelling`, run sequentially
by the `scrutineer` agent, plus the milestone's own commands. Every milestone
records its Red evidence in `Progress`, ends with the conformance check in
`Milestones and plateaus`, and is delivered as one stacked PR.

### EP-M1. Prototype: toolchain, profile, and hosted-cost probes

This milestone records each tool and profile capability and trust boundary
before anything depends on it. Its probe crates are kept as fixtures when later
milestones use them and are deleted otherwise. No shipped code changes.

- Proof-tool pins and Make wiring (DL-21). Add `tools/rust-prover-tools/REF`
  pinning `9c4a27a86c678ceac1155404f45d95ee4a14a172` (or the `main` head at
  implementation time, recorded with its `verify` output); `tools/kani/VERSION`
  (0.67.0); `tools/verus/VERSION` (0.2026.09.06.8dea4a2);
  `tools/verus/SHA256SUMS` in `sha256sum` format, naming
  `verus-0.2026.09.06.8dea4a2-x86-linux.zip` with digest
  `13d01e134c0620c3b29770874707d16c33b3d227c843a489c8ceb744d43c0a16`; and
  `tools/verus/README.md` saying what is pinned and how to bump it. Add the
  `PROVER_TOOLS` block from the `kani` skill's on-ramp to the `Makefile`, with
  targets `install-kani`, `kani-check`, `install-verus`, `kani` and `kani-full`
  (`FORMAL-SKIP` stubs, DL-23), `kani-log-corpus`, and `verus-probe`. Ignore
  `.verus/` in Git and in the Markdown lint configuration. Red first: add
  `tests/prover_tools_contract.rs` (VO-15), run it, and record the failure.
  Then run `make install-kani`, `make kani-check`, and `make install-verus`,
  recording the rustup toolchains each fetches (nightly-2025-11-21 for Kani,
  1.98.0 for Verus), the crates.io `kani-verifier` source, whether the Verus
  archive bundles Z3 4.16.0, and, for reference, the Kani release asset digest
  `3b5f7afd3b51603ee720db7bc1bc4fe46b5a4f5d36daad9939c4b4c658b51ac0`.
- Kani log corpus. Create `tools/verifier-fixtures/kani-corpus/`, a standalone
  crate with its own `[workspace]` table and a harness manifest. Its labelled
  subjects produce, through `make kani-log-corpus` (which runs
  `make kani-check`, then
  `prover-tools kani exec --cwd tools/verifier-fixtures/kani-corpus` with each
  verifier argument passed as a separate `--extra-arg`), one log per class: a
  claim that passes with a satisfied cover; a claim with a counterexample; a
  claim whose success line hides an unreachable cover; a symbolic full-width
  multiplication run with `-Z unstable-options --harness-timeout 5s`; a failed
  unwinding check; a pure skip (`--harness X --exact`, with all run results
  passing); a `--fail-fast` run mixing a counterexample with skipped harnesses;
  a run killed from outside, leaving a truncated log; `kani::assume(false)`
  before a cover; an undetermined or unsupported construct; a
  `#[kani::should_panic]` claim; and control harnesses (seeded faults as
  separate functions, no `cfg` body swaps) that fail their expected property.
  Each log is stored under `scripts/tests/fixtures/kani_logs/` with
  `cargo kani list --format json` output and a provenance file naming the
  command, Kani version, digest, and whether `--verbose` output shows CBMC's
  unwinding-assertion flag; if it does not, the unwinding-check capability is
  recorded `inconclusive`.
- Verus wiring probe. Create `tools/verifier-fixtures/verus-wiring-probe/` with
  four candidates for the kernel's eventual proof profile, each a `#![no_std]`
  crate without `alloc`: (a) a non-optional `vstd` dependency
  (`default-features = false`) with `verus!` blocks; (b) an optional `vstd`
  dependency behind a `verus` feature, with attribute-form specifications inert
  in ordinary builds; (c) a companion proof crate that depends on the
  production crate and states lemmas about its public functions (technical
  design §17.7); and (d) the single-root pattern of DL-22, run by
  `prover-tools verus run --proof-file`. Candidates (a) to (c) need
  `cargo verus`, which `prover-tools` does not wrap, so they run the
  `cargo-verus` binary from the installed release directly and record that gap.
  Each holds one labelled capability lemma and one seeded mutant. Acceptance is
  by exact counts: the lemma run reports one function verified and zero errors
  (zero verified means the attributes were inert, which is a failure); the
  mutant run reports exactly one "postcondition not satisfied" located at the
  mutant. Record for each candidate whether its verifier route succeeds in
  place under the repository's `.cargo/config.toml`, whether an ordinary build
  succeeds without a verifier, tested in a rootless Podman container on a fresh
  hosted runner. Local admission launches compilers outside the container
  namespace, so local isolation is inconclusive. Record extra build time,
  package names (for VO-3), the scanner's trust items, and how VO-1 would be
  amended for that wiring. Confirm that `vstd` `0.0.0-2026-09-06-0133` matches
  the pinned Verus. The probe selects the wiring task 1.2.4 will use; it adds
  no proof content to the kernel.
- Kani in place. On a scratch copy of the planned kernel and native-only facade
  inside the repository tree, run one completed harness whose cover is
  satisfied through `prover-tools kani exec`, recording whether it accepts the
  repository's Cargo configuration, the compile-admission wrapper, the
  workspace lint tables, and a `#![no_std]` crate, and which flags it removed
  from the child.
- Toolchain identities. Record `rustc -vV` and `cargo -V` for the repository
  nightly, Kani's toolchain, and Verus's Rust 1.98.0.
- Polars feature set. Determine the smallest Polars 0.55.2 feature set,
  starting from the calibrated `default-features = false, features = ["lazy"]`,
  that builds an `Int64` `Series` and collects a trivial `LazyFrame`.
- Hosted cost. Add `tools/probes/polars-profile/`, a standalone crate that
  mirrors the planned facade with the selected Polars features, and
  `.github/workflows/profile-measurements.yml`, triggered by manual dispatch
  and by a `pull_request` event when the `measure-profiles` label is applied
  (guarded on that label name, checking out the PR head SHA, with a concurrency
  group). It runs on `ubuntu-24.04` in a job not named `build-test`, so it is
  outside AC-07, and measures each Polars route cold three times: rustdoc,
  Clippy, Whitaker, nextest under Cranelift, LLVM coverage, and the `trybuild`
  UI test. It records wall time, peak memory, `target/` size, whether rustdoc
  and Clippy share dependency metadata, and cache save time, with
  `CARGO_BUILD_JOBS=4` and the hosted `CARGO_INCREMENTAL` value recorded. A new
  workflow file leaves `ci.yml` untouched. Size each proposed job as its
  slowest observed run plus fixed overhead (setup, Whitaker driver, cache save)
  and require at most 6 minutes.
- Go/no-go: proceed only if at least one Verus wiring and the in-place Kani run
  succeed without weakening the ordinary build standard, and a job split is
  predicted within 6 minutes per job. Otherwise set status `BLOCKED` and record
  the deviation in `Decision log`.
- Validation: `make install-kani`, `make kani-check`, and `make install-verus`
  (each run twice, to show that a repeated install is harmless);
  `make kani-log-corpus`; `make verus-probe`, which runs each candidate's
  verifier route and checks the exact counts above; the hosted measurement run;
  then the common gates.
- Recovery: delete `tools/verifier-fixtures/`, `tools/probes/`, the pin files,
  the prover Make targets, and the measurement workflow; nothing else depends
  on them yet.

### EP-M2. Workspace, crate boundaries, and dependency-direction checks

- Refactor first, as its own commit: split `tests/make_gate_order.rs` (481
  lines) below 400 lines by moving case tables into `tests/support/`, with all
  existing tests passing before and after.
- Red: add `tests/workspace_boundaries.rs` with VO-1, VO-2, VO-3, and VO-6 as
  `rstest` tables using `googletest` matchers, over canned fixtures in
  `tests/fixtures/cargo/` and the live workspace; run it and record the
  failure, which arises because neither member crate exists.
- Convert `Cargo.toml` into a workspace root with `members = ["crates/*"]`,
  `default-members = [".", "crates/combobulate-kernel",
  "crates/combobulate-macros"]`,
  `exclude = ["tools"]`, and `resolver = "3"`. Move the lint tables to
  `[workspace.lints]`, add `unexpected_cfgs` with
  `check-cfg = ["cfg(kani)", "cfg(verus_keep_ghost)"]`, and set
  `lints.workspace = true` in every package. Share only edition, repository,
  and homepage through `[workspace.package]`; `license` and `publish` stay
  literal.
- Create `crates/combobulate-kernel/` (`#![no_std]`, no dependencies,
  `TargetFacts`) and `crates/combobulate-macros/` (`proc-macro = true`, no
  dependencies, crate documentation only). The facade depends on both by path
  with `version = "0.1.0"`.
- Extend `scripts/docs_validation/package_policy.py` and its test so that every
  member found through the root `members` globs carries the literal ISC licence
  and `publish = false`, and any `crates/*/Cargo.toml` outside those globs
  fails.
- Remove `greet()` and `tests/stub.rs`.
- Green: rerun the boundary tests; run the real `make package`, deciding and
  recording whether the route becomes `-p combobulate`; update route contract
  tests in the same commit as any route change.
- Acceptance: VO-1, VO-2, VO-3 (native-only), and VO-6 pass; the kernel
  isolation command under `Concrete steps` prints only the kernel; and
  `make package` succeeds.
- Conformance: kernel and direction rules hold; no public item besides
  `TargetFacts`; no new external dependency; no trust boundary change.
- Recovery: revert the milestone's commits; the single-crate state is
  self-consistent. Remaining gaps: features, profiles, CI, records.
- Compatibility decision: none; every changed surface is pre-1.0 and
  unreleased.

### EP-M3. Feature profiles, `BuildProfile`, gate profiles, and CI shape

This milestone adds Polars to the facade, so it lands in one push together with
the approved CI shape and the AC-07 amendment.

- Red: write `tests/features/build_profiles.feature` (below), its step
  definitions in `tests/build_profiles.rs`, `insta` snapshot tests of the
  rendered line, `tests/native_consumer_e2e.rs`, and VO-4 and VO-14 checks;
  record the failure, which arises because `BuildProfile` does not exist.
- Add the facade features `default = ["macros", "polars"]`,
  `macros = ["dep:combobulate-macros"]`, and `polars = ["dep:polars"]`, with
  `polars = { version = "0.55.2", default-features = false, features = [...] }`
  using the EP-M1 set. Add a Dependabot `ignore` for `polars*`.
- Add `src/profile.rs` with `BuildProfile`, and a crate-private
  `src/polars_backend.rs` behind `cfg(feature = "polars")` that builds an
  `Int64` `Series` in a unit test, proving the Polars-enabled build compiles
  and links without claiming any capability.
- Add `tools/fixtures/native-consumer/`, a standalone binary crate depending on
  the facade by path with `default-features = false`, which prints
  `BuildProfile::current()`. `tests/native_consumer_e2e.rs` builds and runs it
  through `env!("CARGO")` into `env!("CARGO_TARGET_TMPDIR")`, checks its
  `cargo tree`, and compares its output with the `native-only` snapshot.
- Gate profiles (DL-18): replace `--all-features` in `CARGO_FLAGS` with
  per-profile feature lists selected by `GATE_PROFILE`. Add `lint-profiles`
  (Clippy and Whitaker per profile) under `make lint` and `test-profiles`
  (nextest per profile, with the `trybuild` UI test only in `native-only`) under
  `make test`. Each runs profiles as separate Cargo invocations so that
  feature unification cannot mask a profile. Update the route contract tests in
  the same commit.
- CI shape (DL-03, DL-14): implement the approved job split in
  `.github/workflows/ci.yml` and `coverage-main.yml`, enable GitHub Actions
  sccache, save caches only on `main`, set the coverage features to the
  native-only profile explicitly, and update `ci_controls.py`,
  `preregistration.py`, and their tests to accept the amended AC-07 workload.
  Record the amendment, with its new `ci.yml` digest, in
  `spec/acceptance-controls.json` in the same commit.
- Checkpoint: the sponsor approves the AC-07 amendment text and job sizes
  before this push. Status is `BLOCKED` until then.
- Green: rerun the scenarios, snapshots, end-to-end test, and both profile
  routes; then the common gates and the hosted CI on the push.
- Acceptance: VO-4, VO-5, VO-14; both profiles lint and test locally; hosted
  jobs green within their sizes.
- Conformance: profiles match ADR-0010's draft; no capability claimed for
  Polars; no verifier in any ordinary closure.
- Recovery: revert the push as a unit; a partial revert would leave Polars in
  `build-test` without the split. Remaining gaps: profile record, scanner,
  parser, AC-04, documents.
- Compatibility decision: none.

The behaviour specification:

```gherkin
Feature: Build profiles report what was compiled

  @native
  Scenario: A native-only build reports no Polars backend
    Given the facade compiled without default features
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile does not report a Polars backend
    And the profile does not report the macro feature
    And the profile reports the target usize width

  @polars
  Scenario: The default build reports the Polars backend
    Given the facade compiled with default features
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile reports a Polars backend
    And the profile reports the macro feature
```

### EP-M4. Profile record, pin consistency, and ADR-0010

- Red: add `scripts/tests/test_toolchain_profiles.py` with the VO-7 and VO-8
  tests; record the failure.
- Add `spec/toolchain-profiles.schema.json` and `spec/toolchain-profiles.json`
  recording the repository nightly with its commit hash; Kani 0.67.0, its
  toolchain, CBMC, and CaDiCaL versions; Verus 0.2026.09.06.8dea4a2, Rust
  1.98.0, Z3 4.16.0, and the matching `vstd`; Polars 0.55.2 and its features;
  the target `x86_64-unknown-linux-gnu`; the four profiles with crates,
  features, toolchains, and commands; the supported-toolchain set; every EP-M1
  capability with status and log citation; and each tool's trusted computing
  base, including the rustup toolchains, the crates.io `kani-verifier` crate,
  the unverified Kani bundle download, and `rust-prover-tools` at its pinned
  commit.
- Add `scripts/docs_validation/toolchain_profiles.py`, registered in
  `scripts/check_docs.py`. Green: rerun.
- Write `docs/adrs/adr-0010-workspace-crate-boundaries-and-profiles.md` as
  `Proposed`, following the style guide's ADR template: CA3, CA5, Q3, the
  selected Verus wiring, the proof-dependency allowlist that VO-1 will admit in
  task 1.2.4, gate feature lists, the B01 falsification route, and the rejected
  adapter-crate option. Add proposed D16 to `spec/decisions.json` and
  regenerate the register. Draft the AC-04 amendment (DL-15).
- Checkpoint: the sponsor accepts the AC-04 amendment before EP-M6 measures.
- Acceptance: VO-7, VO-8; `make design-check` passes with D16 proposed.
- Recovery: revert; nothing downstream reads the record yet. Remaining gaps:
  D16 acceptance, scanner, parser, AC-04 record.
- Compatibility decision: none.

### EP-M5. Trust-audit scanner, Kani log parser, and gate binding

- Red: add `scripts/tests/test_trust_audit.py` and
  `scripts/tests/test_kani_log.py` (VO-9 to VO-13) over the EP-M1 corpus, and
  the VO-12 integration tests; record the failure.
- Implement `scripts/docs_validation/trust_audit/` (lexer, matcher, and command
  modules, each under 400 lines) with DL-17's rule, and the command
  `scripts/trust_audit.py PATH...`, which prints items in the schema's
  `trust_audit.items` shape. Add the `trust-audit` design check over members
  enumerated from `cargo metadata`.
- Implement `scripts/docs_validation/kani_log/` (structure extractor, decision
  function, and shell adapter). Extend `evidence_records.evidence_inputs` and
  `scripts/check_evidence.py` so the I/O shell reads each Git-tracked log,
  manifest, and source named by a record, checks digests, runs the registered
  adapter and the scanner, and passes `verified_log_results` and
  `verified_trust_audits` into `AdmissionContext`. Change `abstract_record` as
  DL-16 states; the rule table and levels do not change, and the existing gate
  property tests must still pass.
- Add fixture records under `scripts/tests/fixtures/evidence/` that cite corpus
  artefacts, never under `spec/evidence/`, so they cannot affect roadmap
  closure.
- Write the ADR-0009 amendment (DL-16, DL-17, DL-10). Checkpoint: the sponsor
  approves it before registration.
- Only when every corpus test passes, add `"kani"` to
  `registered_log_parsers`, add the `log-parser-registration` check, and update
  the description in `scripts/tests/fixtures/evidence/log-parsers.json`.
- Run `mutmut` over `trust_audit/` and `kani_log/`; resolve survivors.
- Acceptance: VO-9 to VO-13; `scripts/check_evidence.py --as-of DATE` over the
  fixture records prints `bounded` for the positive record and the intended
  reason for every negative one.
- Recovery: unregister the parser first, then revert. Remaining gaps: Verus
  parser and type-complete bounds (task 1.2.4).
- Compatibility decision: none.

### EP-M6. AC-04 measurement, documents, decisions, and roadmap tick

- Red: add a check rejecting a `deferred` candidate ADR subject whose roadmap
  item is ticked; with CA3 and CA5 still deferred to 1.2.1, a trial tick in a
  temporary copy must fail it.
- AC-04: extend `profile-measurements.yml` with the amended protocol: five cold
  and five warm builds per profile, profiles alternating run by run, one
  discarded warm-up; a fresh `CARGO_TARGET_DIR` for each cold run, deleted
  afterwards; warm runs reuse the target directory and touch `src/lib.rs` or
  `crates/combobulate-kernel/src/lib.rs`; sccache off with `RUSTC_WRAPPER`
  verified unset; incremental compilation remains disabled as on the rebased
  target; an untimed `cargo fetch --locked`; `CARGO_BUILD_JOBS=4`; one step per
  timed invocation; `nproc`, memory, and image version recorded; partial
  results uploaded with `if: always()`. The proof profile is Kani codegen of
  the kernel through `make install-kani`, `make kani-check`, and
  `prover-tools kani exec --cwd crates/combobulate-kernel` with
  `--extra-arg=--only-codegen` (plus `-Z unstable-options` if Kani 0.67.0
  requires it), timing only the `kani exec` step. Commit the acceptance record
  to `spec/measurements/` and report its verdict honestly.
- Add `.github/workflows/formal.yml` (DL-23), not required for merging,
  triggered weekly and by manual dispatch, which runs `make install-kani`,
  `make kani-check`, `make kani-log-corpus`, `make install-verus`, and
  `make verus-probe`, so the verifier route does not rot before task 1.2.4. It
  has its own `concurrency` group and timeout.
- Documents: ADR-0010; the decision register; technical design §3 (crate
  names, dependency direction, profiles, and the component table's reuse column
  for the kernel and the profile report), §15 (GAP4), §17.7 (profile wiring),
  and §19.1 (selected Polars release); `docs/users-guide.md` (features,
  native-only use, `BuildProfile`, the reserved `macros` feature);
  `docs/developers-guide.md` (workspace layout, profiles, `GATE_PROFILE`,
    proof-tool installation through `prover-tools`, the `.verus/` disk cost, a
  harness inventory for the Kani corpus with each harness's role, bounds, and
  expected outcome, the module-owner rows, and the re-use policies below);
  `docs/repository-layout.md`; `docs/contents.md` (ADR-0010 and this plan);
  `docs/evidence-and-decision-records.md`; `docs/validation.md` (GAP9 in part);
  `docs/references.md` (Kani, Verus, and Polars release sources);
  `docs/acceptance-calibration.md` (Polars no longer provisional); the
  `docs/terms-of-reference.md` §9 Q3 row linking `decision-register.md#d16`,
  with any open-status wording about Q3 retired.
- Decisions: the sponsor accepts D16 and ADR-0010; commit the approval
  reference (`author_login` and `accepted_by` both `leynos`, naming D16); then
  repoint CA3 and CA5 to `{"kind": "adr", "adrs": ["ADR-0010"]}` under D16.
- Tick: add the 1.2.1 entry to `spec/task-completion.json` citing D16 and its
  artefacts, tick task 1.2.1 and its detail in `docs/roadmap.md`, and regenerate
  `spec/roadmap.json`. AC-07 is inconclusive at this point because its window
  restarted; the sponsor accepted that in decision item 2.
- Acceptance: `make design-check` accepts the tick; the AC-04 record states
  pass or fail; the hosted jobs are green.
- Recovery: untick and revert the documents; the code milestones stand.
- Compatibility decision: none.

Re-use policies to record in `docs/developers-guide.md`:

- `TargetFacts` is kernel-owned, the single source of target facts for checked
  rules and later certificate keys. The macro crate must not construct it, and
  the facade exposes only derived values through `BuildProfile`.
- `BuildProfile` reports compiled features and target facts only. It is not a
  capability report: task 1.2.6 owns Polars capability statuses and must not
  infer them from `BuildProfile`.
- `trust_audit` serves the evidence gate's I/O shell and the `trust-audit`
  design check only; it is not a general Rust parser.
- `kani_log` serves the evidence gate's I/O shell only; its decision function
  is pure and must not read files.
- `toolchain_profiles` validates pins; other checks read pins from
  `spec/toolchain-profiles.json` rather than duplicating them.

## Milestones and plateaus

- EP-M1: probes, corpus, and measurements committed; no product code changed.
  Requirements: Q3, Q9, AC-04 and AC-07 inputs, B01 and B05 preconditions.
  Evidence: VO-15, `make kani-check`, `make kani-log-corpus`,
  `make verus-probe`, hosted measurement run.
- EP-M2: three-crate workspace; boundary tests green. Requirements: technical
  design §3, §18.1, CA5 structure. Evidence: VO-1, VO-2, VO-3 (native-only),
  VO-6, `make package`.
- EP-M3: features, `BuildProfile`, gate profiles, CI shape, AC-07 amendment.
  Requirements: ToR S7, technical design §3, §19.1. Evidence: VO-4, VO-5,
  VO-14, hosted jobs.
- EP-M4: profile record, pin checker, proposed ADR-0010 and D16, AC-04
  amendment. Requirements: GAP4, Q3. Evidence: VO-7, VO-8.
- EP-M5: scanner, parser, gate binding, ADR-0009 amendment, Kani registered.
  Requirements: D15, ADR-0009. Evidence: VO-9 to VO-13.
- EP-M6: AC-04 record, documents, D16 accepted, tick. Evidence: AC-04 record,
  `make design-check` accepting the tick.

Each milestone's recovery, remaining gaps, and compatibility decision are
stated in its `Plan of work` entry. At every boundary, run the focused
conformance check, one line per item:

- Requirements assigned to the milestone are satisfied.
- ADR-0010 (draft or accepted) is still followed.
- No B01, B05, or Q9 assumption has been falsified.
- No unapproved public interface or dependency was introduced.
- No unapproved trust boundary, control, or persisted-format change was made.
- Trace links in `Conformance basis` are current.

## Concrete steps

All commands run from the repository root. Long outputs go through `tee` into
`/tmp/$ACTION-combobulate-1-2-1-establish-workspace-and-profiles.out`.

```bash
make install-kani kani-check 2>&1 | tee /tmp/install-kani-combobulate-1-2-1-establish-workspace-and-profiles.out
make install-verus 2>&1 | tee /tmp/install-verus-combobulate-1-2-1-establish-workspace-and-profiles.out
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
$ cargo tree -p combobulate-kernel --all-features --target all -e all --prefix none
combobulate-kernel v0.1.0 (.../crates/combobulate-kernel)
```

Expected profile lines after EP-M3 (exact wording fixed by the snapshots):

```plaintext
$ cargo run --quiet --manifest-path tools/fixtures/native-consumer/Cargo.toml
features: native; target usize: 64 bits
```

```plaintext
polars-enabled snapshot: features: native, macros, polars; target usize: 64 bits
```

## Validation and acceptance

Quality criteria:

- Tests: `make test` (both gate profiles) and `make design-check` pass; the
  boundary, profile, end-to-end, pin, scanner, parser, and integration tests
  each failed before their implementation and pass after, with the Red logs
  recorded in `Progress`.
- Verification: VO-1 to VO-14 discharged as stated, with their non-vacuity
  controls observed; `make verus-probe` shows the exact counts for each wiring
  candidate; the Kani corpus parses to every required outcome class; `mutmut`
  survivors over the parser and scanner are resolved.
- Lint and format: `make check-fmt`, `make lint`, `make markdownlint`,
  `make spelling`, and `make nixie` pass.
- Performance: the AC-04 acceptance record states pass or fail against its
  ceilings; each hosted required job stays within its measured size; AC-07 is
  recorded as inconclusive at the tick.
- Security: `make audit` passes with Polars in the lock file; no new audit
  ignore is added without a recorded reason.

## Idempotence and recovery

Installation idempotence and download integrity belong to `prover-tools`;
`make kani-check` after every install, and the Verus archive's checksum,
establish that the installed tools match their pins. `make kani-log-corpus`
regenerates logs and provenance; regenerated logs differ in timings, so their
digests are refreshed together with the fixture records and manifests, and the
parser tests assert classifications rather than timings. Every milestone ends
in a committed, gated state, so reverting one milestone's commits returns to
the previous plateau; EP-M3 must be reverted as a unit.

## Artefacts and notes

Hosted profile measurements, run `41163302274` on head `4d4f031`
(`ubuntu24 20261026.354.1`, four vCPUs), 2026-10-31, three cold runs each:

- rustdoc: 38.45 / 36.85 / 36.75 s; peak 0.68 GiB; target 0.24 GiB
- clippy: 39.16 / 37.85 / 39.40 s; peak 0.68 GiB; target 0.24 GiB
- whitaker: 57.71 / 23.10 / 27.23 s; peak 0.83 GiB; target 0.47 GiB
- nextest: 52.08 / 51.50 / 51.03 s; peak 2.08 GiB; target 1.08 GiB
- coverage: 58.89 / 56.40 / 57.47 s; peak 1.68 GiB; target 0.95 GiB
- ui: 134.23 / 128.67 / 130.26 s; peak 2.10 GiB; target 1.13 GiB

Setup before the first run took 61-80 s per job. Clippy after rustdoc took
13.08 s, so those routes share dependency metadata. The verifier-free job
recorded `status: pass` in
`tools/verifier-fixtures/verus-wiring-probe/verifier-free-hosted.json`, with
the container build and probe logs beside its local counterparts.

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

In `src/profile.rs`, re-exported from the facade root; `TargetFacts` is not
re-exported:

```rust
/// Features and target facts compiled into this build of Combobulate.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BuildProfile { /* private fields */ }

impl BuildProfile {
    pub const fn current() -> Self;
    pub const fn has_macros(self) -> bool;
    pub const fn has_polars(self) -> bool;
    pub const fn target_usize_bits(self) -> u32;
}

impl core::fmt::Display for BuildProfile { /* the profile line */ }
```

Dependencies (caret requirements):

- Facade runtime: `combobulate-kernel` (path, version 0.1.0), optional
  `combobulate-macros` (path, version 0.1.0), optional `polars = "0.55.2"` with
  `default-features = false` and the EP-M1 feature set.
- Facade development: `rstest-bdd = "0.6.0"`, `googletest = "0.14.3"`,
  `pretty_assertions = "1.4.1"`, `insta = "1.49.0"`; `rstest` may move from
  0.27.0 to 0.28.0 only if `rstest-bdd` requires it.
- Kernel and macros: none.
- Python: none new; Hypothesis 6.168.5 and pytest 9.1.1 are already pinned.
  `mutmut` runs through `uv tool run` at a pinned version, not as a project
  dependency.
- Proof tools (not Cargo dependencies of shipped crates): Kani 0.67.0, Verus
  0.2026.09.06.8dea4a2, Z3 4.16.0, and `vstd` `=0.0.0-2026-09-06-0133` in the
  Verus probe's crate-based candidates only; the exact pin is required because
  Verus checks that `vstd` matches the verifier build.
- Prover tooling: `rust-prover-tools` at the commit in
  `tools/rust-prover-tools/REF`, run through `uv tool run --from` its pinned
  Git source (Python 3.14, already required by the repository's tooling); it is
  not a project dependency.

## Signposts

Read before implementing: `docs/technical-design.md` §§3, 10, 15, 17-19;
`docs/terms-of-reference.md` §6, §9, and Q3, Q9; `docs/testable-bets.md` B01,
B05; `docs/adrs/adr-0005-pre-1-0-api-and-proof-interface-policy.md`;
`docs/adrs/adr-0008-acceptance-control-pre-registration.md`;
`docs/adrs/adr-0009-proof-first-policy-and-evidence-gate.md`;
`docs/evidence-and-decision-records.md`; `docs/acceptance-calibration.md`;
`docs/decision-register.md`; `docs/developers-guide.md`;
`docs/reliable-testing-in-rust-via-dependency-injection.md`;
`docs/rust-testing-with-rstest-fixtures.md`; `docs/rstest-bdd-users-guide.md`;
`docs/rust-doctest-dry-guide.md`;
`docs/complexity-antipatterns-and-refactoring-strategies.md`;
`docs/references.md` (E-KANI-*, E-VERUS-*, E-POLARS2-*);
`docs/documentation-style-guide.md` (ADR template and naming);
`docs/scripting-standards.md`. Outside the repository: the
`leynos/rust-prover-tools` README, users' guide (`docs/users-guide.md`, in
particular "Explicit legacy Kani execution"), and CLI design
(`docs/prover-tools-cli-design.md`); and the `kani` and `verus` skills'
`references/project-on-ramp.md`.

Skills: `execplans`, `rust-router`, `arch-crate-design`,
`arch-decision-records`, `arch-supply-chain`, `rust-unit-testing`, `kani`,
`verus`, `rust-verification`, `hypothesis`, `mutmut`, `python-testing`,
`nextest`, `codegraph-mcp`, `firecrawl-mcp`, `github-stacks`,
`en-gb-oxendict-style`, `pr-creation`.

## Revision note

2026-10-22, revision 1: initial draft from Wyvern reconnaissance and external
research.

2026-10-22, revision 2: applied the community-of-experts review. Added the
AC-07, AC-04, and ADR-0009 amendments and their checkpoints; moved the CI
change into EP-M3 so that Polars never reaches `build-test` without the split;
replaced `--all-features` gates with explicit gate profiles; bound the trust
audit to the gate and stated the vocabulary's matching rule; fixed parser
bounds to `partial`; specified negative controls, `run_mode`, outcome
precedence, and the bound harness manifest; widened the Kani corpus; made the
Verus probe decisive with exact counts, a third wiring candidate, and a
container build; replaced metadata-graph checks with `cargo tree` and
declared-edge checks, added the host-compilation rule; trimmed the public API;
kept `license` and `publish` literal; added the package route, the
`make_gate_order.rs` split, the external native consumer, VO-14, re-use
policies, and per-milestone recovery and gates. Remaining work is unchanged in
scope: implementation begins only after sponsor approval.

2026-10-22, revision 3: recorded the sponsor's acceptance of the recommended
option for all eight sponsor decisions, and renamed the section to
`Sponsor decisions`. Explicit approval of the plan and the Q3
`in_scope_questions` answer remain before EP-M1 begins.

2026-10-22, revision 4: at the sponsor's direction, adopted
`leynos/rust-prover-tools` as the only installer and runner for Kani and Verus
(DL-21). Dropped the repository-owned installer; added the pinned
`tools/rust-prover-tools/REF`, the on-ramp's Make wiring and recording-fake
contract tests (VO-15), `prover-tools kani exec` as the Kani route, the
single-root Verus wiring candidate (DL-22), and a separate non-required formal
workflow with `FORMAL-SKIP` stubs (DL-23). New risks cover the unverified Kani
bundle download, the missing `cargo verus` route, and `.verus/` disk use.
Remaining work is unchanged otherwise; EP-M1 still awaits explicit plan
approval and the Q3 answer.

2026-10-27, revision 5: recorded sponsor approval to implement the plan and the
direction to bring Q3 into scope when its evidence-based D16 is proposed.

2026-10-28, revision 6: adopted the rebased development configuration for AC-04
warm measurements and clarified the amendment; prefer `prover-tools`, with a
documented direct pinned-tool route when a probe requires it.

2026-10-28, revision 7: recorded the local probe evidence, explicit helper
compatibility route, solver transport, and hosted acceptance gaps.
