# ExecPlan progress: EP-M3, EP-M4, EP-M5, and EP-M6 of task 1.2.1

This is a continuation record for
`docs/execplans/1-2-1-establish-workspace-and-profiles.md`. The parent plan is
long and is the authority for every milestone; this file records the working
state of the milestones currently in progress so a later session can resume
without re-deriving what has already been built and what has already been ruled
out.

It is a **living document**: update the checklists and the notes as work
proceeds, not at the end.

## Why this file exists

The parent plan's EP-M6 deferred the roadmap tick until the profile record,
ADR-0010, D16, the trust-audit scanner, the Kani log parser, and the AC-04
record all exist. A provisional attempt to tick 1.2.1 first was built and
measured, then withheld: the tick would have asserted a Polars-enabled build
and a registered trust-audit scanner that did not exist, and its completion
record cited no decisions where EP-M6 requires D16.

The withheld diff is preserved outside the repository at
`/tmp/premature-tick-1-2-1.patch` (122 lines, sha256
`13eb97dd7ff150ce2c30f013a0e19abe63adcf48d13390a2e1775c51db6f7daa`). It is
reusable once its claims become true, but it must not be applied before then.

## Branch

`1-2-1-profiles-and-trust-audit`, branched from `main` at `408aba7`.

## EP-M3 status: in progress

Specification: parent plan lines 2250-2320.

- [x] Red recorded: `tests/features/build_profiles.feature`,
  `tests/build_profiles.rs`, the snapshot tests,
  `tests/native_consumer_e2e.rs`, and the VO-4 and VO-14 checks all fail because
  `BuildProfile` does not exist. The step was observed before the
  implementation landed and every artefact it names exists; the item is ticked
  as a record of the TDD step, not as evidence that the suite is currently red.
- [x] Facade features `default = ["macros", "polars"]`,
  `macros = ["dep:combobulate-macros"]`, `polars = ["dep:polars"]`.
- [x] The facade's `polars` dependency selects `0.55.2` with
  `default-features = false` and `features = ["lazy"]`, matching the EP-M1
  calibrated probe.
- [x] Dependabot `ignore` for `polars*`, and the native-consumer fixture added
  to the `directories` list of the auxiliary Cargo entry.
- [x] `src/profile.rs` with `BuildProfile` and its `Display` line.
- [x] crate-private `src/polars_backend.rs` behind `cfg(feature = "polars")`,
  with a unit test building an `Int64` `Series` and collecting a trivial frame.
- [x] `tools/fixtures/native-consumer/`, a standalone binary crate depending on
  the facade by path with `default-features = false`, printing
  `BuildProfile::current()`.
- [x] `tests/native_consumer_e2e.rs` green: build, run, `cargo tree` check, and
  comparison with the `native-only` snapshot. The fixture's `Cargo.lock` is
  committed beside it, as every other fixture crate in the repository does;
  without it `--locked` fails before the fixture is built at all.
- [x] `tests/build_profiles.rs` compiles under both profiles
  (`cargo check --all-targets --no-default-features` exits 0). Running the
  scenarios is the step after this one.
- [x] Gate profiles (DL-18): `GATE_PROFILE` (default `both`), per-profile
  flags, and one `lint-clippy` / `test` loop that runs each profile as its own
  Cargo invocation. A first Makefile edit was reverted because it changed
  `CARGO_FLAGS` for every route and so invalidated roughly eight route-contract
  test files; the working form keeps `CARGO_FLAGS ?= --all-targets` and adds
  the profile selector only to the two per-profile loops, so the route contract
  changes only where a profile changes the recorded command.
- [x] Route contracts updated in the same change: `tests/act_makefile.rs`,
  `tests/support/act_make_assertions.rs`,
  `tests/support/act_make_contract_tests.rs`,
  `tests/support/act_make_harness.rs`,
  `tests/support/make_gate_order_commands.rs`,
  `tests/support/make_gate_order_scripts.rs`,
  `tests/support/make_gate_order_probe.rs`,
  `tests/support/make_gate_order_whitaker.rs`,
  `tests/support/make_gate_order_caller_environment.rs`,
  `tests/make_gate_order.rs`, and `tests/build_standard_contract.rs`.
- [x] (2026-11-08) CI shape (DL-03, DL-14): parallel Polars-enabled lint and
  test jobs in `ci.yml`, `coverage-main.yml` features set to the native-only
  profile explicitly, GitHub Actions sccache enabled and saved on `main` only.
  `ci.yml` now declares three required jobs on the same `ubuntu-24.04` runner
  and eight-minute timeout. `build-test` keeps `GATE_PROFILE: native-only`;
  `polars-lint` and `polars-test` set `GATE_PROFILE: polars-enabled`. The shared
  `setup-rust` action installs sccache through its `use-sccache` default,
  which this workflow states explicitly, but that input only provisions the
  binary; it sets no compiler wrapper, so see "DL-03's cache clause needed a
  wrapper the workflows never set" below. The only cache the caller controls is
  `generate-coverage`'s baseline publish; it is pinned to
  `publish-artefact: 'false'` and its ratchet baseline saves only from
  `coverage-main.yml` on `main`. `coverage-main.yml` names the same native-only
  features, so the ratchet compares like with like.
- [x] (2026-11-08) `ci_controls.py`, `preregistration.py`, and their tests
  accept the amended AC-07 workload; `spec/acceptance-controls.json` records
  the amended workload as an ordinary reviewed file, per ADR-0008's 2026-10-31
  amendment. The workload id is `ci-required-jobs`, the settings value carries
  one `RequiredJob` per unconditioned job, and `check_ci_calibration` still
  reads the registered `ci-build-test` record because that is the evidence the
  220 s threshold came from.
- [x] (2026-11-08) Both workflow contracts are re-keyed to the new shape.
  `tests/support/act_workflow_contract.rs` now contracts each job's ordered
  steps, actions, and environment separately; four typed mutation cases prove a
  step, action, or profile moved into or out of a `polars-*` job fails.
  `tests/coverage_backend_workflows.rs` asserts exactly one measuring job per
  workflow file, and `tests/whitaker_workflow.rs` checks a job that lints or
  installs Whitaker, so renaming the installer cannot exempt a lint job.
  `scripts/whitaker_probe.py` resolves the installer per job and requires one
  shared, full-length, lowercase SHA across all of them.
- [x] ~~Checkpoint, sponsor-owned: approval of the AC-07 amendment text and the
  measured job sizes.~~ **Withdrawn.** ADR-0008's 2026-10-31 amendment
  (`684f687`, on `main`) retired the acceptance-control approval ceremony: a
  control "is an ordinary reviewed file: a change goes through a pull request
  and Git history is the record". This checkpoint was written on 2026-11-07,
  five weeks after the retirement landed, so it asserted an authority that no
  longer existed. The sponsor confirmed on 2026-11-08 that the work proceeds
  without it.
- [x] (2026-11-08) Documentation and control text brought to the amended shape.
  `docs/acceptance-calibration.md` now describes the run-level sample and
  records that the registered `ci-build-test` evidence predates DL-14;
  `docs/developers-guide.md` describes the three required jobs, the per-job
  `RequiredJob` settings value, and the eight-minute timeout on every required
  job. `AC-07` reads `inconclusive`, not `pass`, once the 20-run window
  restarts.

### EP-M3 findings so far

- **The coverage ratchet is a gate, and `main`'s 100 % baseline was vacuous.**
  `coverage-main.yml` measured `main` at 100.00 % only because `src/lib.rs`
  contained no items, so the first real code had to be *fully* covered to clear
  `with-ratchet: 'true'` (±1 pp). The first hosted `build-test` run measured
  92.06 % = **58/63 instrumented lines** and failed the ratchet while every one
  of its 394 tests passed. The three defects, all found by lane-level coverage
  rather than by any assertion:
  - `src/profile.rs`: `Display::fmt` guarded the always-present `native` name
    with `if let Some(first) = names.next()`, leaving that `None` arm
    unreachable. The entry point is now `optional_backend_names`, which yields
    only the conditional names, so the render cannot omit every backend and has
    no dead branch.
  - `src/lib.rs`: `polars_backend_probe` was documented as existing "so `tests/`
    can execute the backend it links", but no test called it; only a doctest
    did, and `cargo llvm-cov nextest` does not run doctests. `tests/polars_backend.rs`
    now calls it from a dependent crate.
  - `src/polars_backend.rs`: the unit test's `let … else { panic!(…) }` left the
    panic arm uncovered. The test now asserts on `collected.as_ref().ok()` in
    one infallible assertion, which reports the Polars error and the wrong
    height through the same diagnostic and needs no panic arm.
  After the fixes the four measured files are 60/60 = **100 %**, and the
  native-only profile still compiles `tests/polars_backend.rs` to an empty test
  binary because the file is `#![cfg(feature = "polars")]`.
- **`cargo llvm-cov` reporting is unusable on this host, so reproduce the ratio
  from the raw profile.** This toolchain writes test binaries under
  `target/<profile>/build/<crate>/<hash>/out/` rather than `deps/`, so
  `llvm-cov report` fails with "not found object files (searched directories:
  …/llvm-cov-target/debug)". The working route is
  `cargo llvm-cov nextest --no-report`, then merge the `.profraw` files with
  the **pinned toolchain's** `llvm-profdata` and export with the same
  toolchain's `llvm-cov`. Mixing toolchain versions fails with "no profile can
  be merged".
- `make coverage` cannot run on this host at all: `check-coverage-tools`
  requires `ld.lld`, which is not installed. The lcov report does not depend on
  which linker is selected, so measuring with `mold` reproduces CI exactly.
- `rstest-bdd` 0.6.0 does **not** re-export its macros. `rstest-bdd-macros`
  0.6.0 is a separate direct dependency. Adding only `rstest-bdd` fails with
  `unresolved import rstest_bdd_macros`.
- `#[scenario(tags = "...")]` filters at macro-expansion time and is documented
  to error when nothing matches, which is exactly VO-5's non-vacuity control.
  Adding `rstest-bdd-macros` as a dependency is therefore safe: a mistyped tag
  cannot silently run zero scenarios.
- The dev-y graph now pins `insta` 1.49.0, `pretty_assertions` 1.4.1,
  `rstest-bdd` 0.6.0, `rstest-bdd-macros` 0.6.0, and `polars` 0.55.2, all
  confirmed in `Cargo.lock`.
- `Cargo.lock` grew substantially (Polars plus the BDD stack). `make audit`
  must pass with it.
- `#[scenario]` parameters are `rstest` fixtures, not free variables. A bare
  `fn scenario(observed: Observed)` fails with
  `error[E0433]: cannot find module or crate 'observed'`, because `rstest`
  reads the parameter name as a fixture path. The fix is a
  `#[fixture] fn observed() -> Observed` in the same module; the scenario then
  injects it and the steps receive it through `&Observed` / `&mut Observed`.
  `#[fixture]` comes from `rstest` itself, not from `rstest-bdd-macros`.
- `cfg(test)` is **not** set when compiling an integration-test crate, so
  `#[cfg(all(test, feature = "..."))]` silently compiles the module away. The
  profile gates in `tests/build_profiles.rs` are therefore plain
  `#[cfg(not(feature = "polars"))]` and `#[cfg(feature = "polars")]`.
- Clippy's `-D warnings` turns `unused_braces` into a build failure, so the
  single-line function form is wrong when the body is a block that Clippy can
  flatten. `fn observed() -> Observed { Observed::default() }` warns; the
  multi-line form does not.
- A repeated stage name is not a neutral choice in the gate-order harness.
  `GateProbe::assert_command` asserts the same argument vector for *every*
  invocation recorded under a stage, so recording both profiles' Clippy runs as
  `clippy` compares the native-only command against the Polars-enabled record
  and fails. Each profile therefore gets its own stage name
  (`clippy-native-only` / `clippy-polars-enabled`, and likewise for Nextest and
  the doctests). Collapsing them would have forced the assertion to be loosened
  until neither exact command was checked.
- `make -j 4` is the harness's default, and the profile loop is a single shell
  line, so the two profiles inside one target stay ordered. Ordering between
  `lint-clippy` and `lint-whitaker` is preserved by the recursive `$(MAKE)`
  calls, not by the loop.
- A shell loop cannot be parallelized by Make and should not be: the point of
  the per-profile invocation is that feature unification cannot mask a profile,
  which holds only while each profile builds in a separate Cargo process.

## EP-M4 status: in progress

Specification: parent plan lines 2322-2348.

- [x] `spec/toolchain-profiles.schema.json`: draft 2020-12, `$id`
  `urn:combobulate:design:toolchain-profiles:0.1`. Requires `revision`,
  `target`, `toolchains`, `pins`, `profiles` (exactly four),
  `supported_toolchain_set`, `capabilities`, and `trusted_computing_base`.
- [x] `spec/toolchain-profiles.json`: four toolchains, twelve pins each with a
  `sites` list, four profiles, three supported toolchains (exactly one
  `ordinary: true`), nine capabilities, six TCB entries.
- [x] `scripts/docs_validation/revision_reader.py::tracked_paths`, the sweep's
  enumerator. It reads `git ls-files --cached --others --exclude-standard`, so
  staged additions and untracked work are both in scope and a new file cannot
  escape the sweep before it is committed.
- [x] `scripts/docs_validation/toolchain_profiles.py`, registered in
  `scripts/check_docs.py` and green under `python3 scripts/check_docs.py`.
- [x] `scripts/tests/test_toolchain_profiles.py`: 19 tests covering VO-7
  (six sourced-pin drifts, a stale citation, an unlisted site, and the three
  ignorable classes) and VO-8 (missing evidence, wrong digest, and the positive
  case). All pass.
- [x] The validation report is regenerated, so the new check appears in
  `docs/validation-results.json`.
- [x] `docs/adrs/adr-0010-workspace-crate-boundaries-and-build-profiles.md`,
  published `Proposed` and then accepted on the sponsor's 2026-10-22 answer.
- [x] D16 in `spec/decisions.json`, `lifecycle: accepted`, `decided_option: B`,
  `accepted_on: 2026-10-22`, with Q3 added to `in_scope_questions` and the
  register regenerated. CA3 and CA5 are repointed to
  `{"kind": "adr", "adrs": ["ADR-0010"]}`, which drops the `candidate-deferral`
  count from 4 to 2.
- [x] The AC-04 amendment applied (DL-15): the workload is now the shipped
  workspace's three profiles with the workspace manifests as the only source,
  `timed_region` admits the `kani exec` codegen step, `measurement_tool` names
  the `build-budget` job that records `ImageOS` and `ImageVersion`, and
  `registered_on` moves to 2026-11-07 so a later acceptance record cannot
  predate the amendment. Every threshold is unchanged.
- [x] The AC-04 acceptance record in
  `spec/measurements/ac-04-profile-build-budgets-2026-11-08.json`, written from
  hosted run `42435047681` at `5f53ed6cc4eb`. Every job concluded `success` and
  the artefact supplied `image_os` (`ubuntu24`) and `image_version`
  (`20261101.360.1`), which is what the schema requires and what no local
  calibration can produce. All six medians sit far inside their ceilings:
  native cold 0.30 s, native incremental 0.15 s, proof cold 0.37 s, proof
  incremental 0.28 s, Polars cold 65.08 s, Polars incremental 0.33 s, against 1
  / 1 / 1 / 1 / 10 min / 1 min. `acceptance_evidence.verdict` reads `pass` and
  `check_measurement_binding` accepts the record.

### EP-M4 findings so far

- The frozen environment covers **five** toolchains, and the `build-budget` job
  observed only two. It reported `rustc` and `cargo kani` while AC-04 registers
  `rust`, `codegen_backend`, `linker`, `verus`, and `kani`, so no record the
  job produced could ever bind. Each of the three missing observations then
  cost a separate hosted failure to get right: the Verus release must be
  installed before it can be reported; `verus --version` runs the verifier and
  so needs the Rust the release was built against
  (`1.98.0-x86_64-unknown-linux-gnu`, read from the release's own
  `version.json`), not the repository nightly; and Z3 is not in the Verus
  archive, so the run takes it from the pinned `Z3_DISTRIBUTION` in
  `scripts/probe_provenance.py`. `mold` was already on the runner through
  `make install-build-tools`.
- The record is a further pin site, and the sweep found it: it names
  `nightly-2026-08-27`, `0.67.0`, `0.2026.09.06.8dea4a2`, and `4.16.0`, so it
  is listed under `repository_channel`, `kani_release`, `verus_release`, and
  `verus_z3`. That is the same coupling as every other site: a pin bump must
  edit the record, because the frozen environment the record registered is what
  the acceptance was measured against.
- Committing the first acceptance record broke
  `test_validation_report`'s identity case, which called
  `(spec/measurements).mkdir()` unconditionally in a fixture that copies
  `spec/` wholesale. It passed only while the directory did not exist, so the
  suite had encoded "the repository has no acceptance records" as a
  precondition rather than as a fact it could tolerate. `exist_ok=True` is the
  honest form; the alternative — letting the test assert absence — would make
  every committed record a test failure.
- **The coverage ratchet caught a real regression the local gates could not.**
  `357d9ef` moved the probe's error handling into a `map_err` closure in
  `collected_height`; the probe's `collect` succeeds for every frame it builds,
  so the closure never ran, and the existing error test constructed
  `BackendProbeError` from a struct literal and so bypassed it too. Hosted
  `build-test` failed the ratchet at `357d9ef` and at `5f53ed6` with 97.53 %
  against a 100 % baseline. `make lint` and `make test` both passed throughout:
  Clippy does not report unreachable-on-the-happy-path code, and the test that
  "covered" the error path asserted on a value it had built itself. Only the
  ratchet names the lines, so a green local suite is not evidence that a
  refactor kept its coverage. The reproduction route above resolves the ratio
  to the line, which is what made the two dead lines findable. The fix is
  `BackendProbeError::from_polars`, an ordinary item the suite calls directly
  with a hand-built `PolarsError::ComputeError`. Borrowing the error is what
  `clippy::needless_pass_by_value` requires of a value that is only rendered. A
  `From<PolarsError>` impl would have been the wrong shape twice over: it is
  public API, so it would hand every embedder a route from a Polars type to the
  facade's error, which is the leak DL-19 exists to prevent.
- **Hosted lint failed for an upstream reason, fixed repository-side by naming
  the suite.** The last green run (`ad5945b`) and `abc95b8` both downloaded the
  rolling suite archive `whitaker-lints-3a370bf`, where `libwhitaker_suite` is
  the only library. From `2040787` the installer fetches
  `whitaker-lints-cfa208c`, which ships eleven libraries, including a standalone
  `libstring_continuation_style` alongside `libwhitaker_suite`. Both contain
  that lint's registration, so `whitaker --all` loads it twice and rustc aborts
  with `duplicate specification of lint string_continuation_style`. The failure
  reproduced on a re-run at an identical installer pin (`0.2.11`), which rules
  out a mid-publish race. The suite is a rolling release and is deliberately
  never pinned (`suite-version is refused`), so the archive cannot be selected
  by date.

  The `DYLINT_LIBS` value in the hosted failure log names exactly what `--all`
  discovered: `libstring_continuation_style` and `libwhitaker_suite`. Locally
  only the suite is installed, which is why the same target stayed green here —
  the failure is a property of the published archive, not of this repository's
  sources. `--all` means "load all discovered libraries"; `--lib NAME` names
  one. A scratch crate with planted violations, run through
  `--lib whitaker_suite`, still reported `no_expect_outside_tests` and
  `no_std_fs_operations`, and `DYLINT_LIBS` again listed the suite alone; the
  libraries resolved from the standard install path with no
  `DYLINT_LIBRARY_PATH` supplied, so the recipe needs no extra environment.
  `whitaker list --lib-path` over the suite `.so` declares all ten lint crates,
  and upstream's installer selects the suite alone by default. Naming the suite
  therefore loads one library that already bundles every lint, which is
  coverage-neutral rather than a narrowing. `--fail-on-no-libraries` is added
  so a missing suite stays a failure instead of passing over nothing. This
  supersedes the earlier reading in this plan that called the lever a
  coverage-narrowing workaround.
- **The stale local suite had been hiding a lint class.** The suite installed
  on this workstation lists nine lints; the rolling `cfa208c` archive lists
  ten, the extra one being `string_continuation_style`. Because `make lint` ran
  the older suite, it could not report that lint at all, so a green local lint
  was not evidence that hosted lint would pass. Once the duplicate-registration
  panic was gone, hosted lint reported the real finding the panic had masked,
  and running the repository check against the downloaded `cfa208c` suite
  reproduced it here: fourteen sites across `tests/build_tool_workflows.rs`,
  `tests/cardinality_gate_scope.rs`, `tests/native_clang_wrapper.rs`,
  `tests/native_consumer_e2e.rs`, and `tests/support/cargo_probe.rs`.

  All were the same shape — a cooked string joined with a trailing `\` and
  re-indented continuation. That is the pattern `AGENTS.md` already forbids
  ("Use `concat!()` to combine long string literals rather than escaping
  newlines with a backslash"), so this is a lint catching an existing
  convention breach rather than a new rule. Each site is now `concat!`.

  Two traps are worth recording. `.rustfmt.toml` sets `format_strings = true`,
  so rustfmt reflows string *contents*; on one fixture it split a line with a
  trailing `\`, produced its own instability (a follow-up `--check` asked for a
  different split), and silently changed a YAML fixture's indentation. Keeping
  each `concat!` fragment short enough that rustfmt has no reason to reflow
  leaves it untouched, and the fixture was verified byte-identical to the
  original. And `format_args!` cannot capture from scope when the format string
  is produced by `concat!`, so the `format!` call sites keep their named or
  positional arguments.

  Local lint now checks against the same archive hosted uses, which is what
  makes the local gate evidence for the hosted one.
- The pin sweep is load-bearing rather than decorative: on its first run it
  reported 15 tracked files that name a pin the record did not list. Every one
  was a genuine site — a manifest selecting the version, a lockfile resolving
  it, a probe asserting it, or a test hard-asserting it — so all were added.
  Excluding them as "test fixtures" would have removed exactly the files that
  fail loudest when a pin moves.
- The sweep also caught the new test module itself, and that is correct: its
  drift cases hard-code the current values, so a pin bump must edit it. Listing
  it makes that coupling explicit instead of leaving a test that would silently
  stop testing drift.
- `facade-reaches-vstd.tree` reads like a capture but is a load-bearing test
  input: `tests/workspace_boundaries.rs` asserts the Verus package set from it,
  so the vstd release appears there and the record lists it.
- `spec/acceptance-controls.json` is deliberately **not** a `polars_release`
  site. AC-04 records the Polars release as a structured field rather than the
  literal `0.55.2`, and weakening the citation check to accommodate it would
  have made every citation check weaker.
- `spec/decisions.json` already carries a `prover_tools_ref` site in
  `scripts/probe_provenance.py`; the record's own file is excluded from the
  sweep so the record cannot satisfy its own citations.
- `check_toolchain_profiles` takes an optional `tracked` argument. Production
  passes nothing and sweeps the Git-tracked tree; the tests pass an explicit
  list so they can add or omit a candidate site without touching the checkout.
  The alternative — mutating the real tree in a test — would need a lock and
  would defeat parallel execution.

**Checkpoint, sponsor-owned:** acceptance of the AC-04 amendment, and later of
D16 and ADR-0010. Both are now cleared: the sponsor's 2026-10-22 turn accepts
D16 and ADR-0010, and approves the AC-04 amendment "at EP-M4", which is where
it was applied.

Two ceremonies were conflated here, and only one of them was retired. `684f687`
removed the *acceptance-control* ceremony: control digests, the amendment
chain, sponsor signatures on controls, source-file hashes, the
measurement-record digest, and the controls freeze. ADR-0008's Amendments
section scopes the retirement exactly that way — "A control is an ordinary
reviewed file" — and a control that changes after its acceptance measurement is
still registered under a new identifier rather than amended in place.

It did **not** touch the *decision-register* ceremony.
`docs/decision-register.md` still says that only the D01 authority accepts,
that "an agent or contributor drafts and recommends but never accepts", and
that an accepted record needs a structured approval reference whose author is
the accepting login. So the AC-04 amendment is now an ordinary reviewed file
change, while D16 acceptance is not, and must carry a reference the schema
accepts.

That reference exists and resolves. The sponsor's turn of 2026-10-22T02:43Z,
"Recommendations accepted: … Decision D16 and ADR-0010 (DL-02) …", is Lody
session item `f869eabd-267c-4624-91eb-8dddc9aae87c` in session
`9cc8f59f-14a7-4470-9239-a0dae798e739`
(`https://lody.ai/leynos/sessions/9cc8f59f-14a7-4470-9239-a0dae798e739`), which
`lody_session_history` returns verbatim. The wording fixes the timing — "The
sponsor accepts D16 after EP-M4 publishes ADR-0010; the approval reference is
committed before the tick" — and ADR-0010 is published as Proposed, so the
condition is met and the reference is the quoted answer naming D16.

The recorded answer quotes only the D16 item, between bracketed ellipses. The
full turn approves eight items, and the register's own preamble says "An
ambiguous approval accepts nothing", so an excerpt that names the decision
alone is the safer record than a transcript in which seven other approvals
could be read as conditioning it.

D16 acceptance does not tick anything by itself. A roadmap tick also needs the
EP-M3 CI shape and its AC-07 amendment (both now landed as ordinary reviewed
files; the withdrawn sponsor checkpoint had made them look blocked), the EP-M5
ADR-0009 amendment and its mutation triage, and the AC-04 acceptance record
from a hosted run. The tick is withheld until those close; `roadmap_status.py`
validates a claim's shape, not its truth. Ticking 1.2.1 does **not** claim
AC-07 passes: DL-14 restarts the 20-run window on the new three-job shape, so
the control reads `inconclusive` until the window refills.

## EP-M5 status: in progress

Specification: parent plan lines 2350-2383, and VO-9 to VO-13 at lines
1957-2046.

- [x] `scripts/docs_validation/trust_audit/` (lexer, matcher, command), each
  module under 400 lines, with DL-17's rule and `scripts/trust_audit.py` as its
  command-line form.
- [x] `scripts/docs_validation/kani_log/` (syntax, extract, model, manifest,
  reader, decide, shell), the decision function pure and file-free.
- [x] `scripts/docs_validation/evidence_binding.py`, `evidence_records`'
  `evidence_inputs`, and `scripts/check_evidence.py` pass
  `verified_log_results` and `verified_trust_audits` into `AdmissionContext`
  (DL-16).
- [x] `scripts/docs_validation/trust_audit_check.py`: the `trust-audit` check
  over members enumerated from `cargo metadata`, non-vacuous because the
  fixture corpus must still report its seeded items.
- [x] VO-12 positive fixture:
      `scripts/tests/fixtures/evidence/bounded-kani.json`
  cites `default_unwind.log` and `default-unwind-manifest.json` and reaches
  `bounded` with no blocking reasons.
- [x] Eight VO-12 negatives, each rejected for its intended reason.
- [x] `"kani"` registered in `spec/evidence-reason-codes.json`.
- [x] The `log-parser-registration` check, wired into `scripts/check_docs.py`.
- [x] `scripts/tests/fixtures/evidence/log-parsers.json`'s description updated:
  the repository registry no longer registers none.
- [x] ADR-0009 amendment (DL-10, DL-16, DL-17), recorded as the 2026-11-07
  entry in `docs/adrs/adr-0009-proof-first-policy-and-evidence-gate.md`. The
  sponsor approved DL-16 ("Approved at EP-M5") together with the rest of the
  2026-10-22 decision set; registration landed on the footing that DL-16 and
  DL-17 restate that approved technical design. The amendment states the three
  consequences rather than restating the options.
- [x] `mutmut` over `trust_audit/` and `kani_log/`; survivors resolved. Both
  censuses are closed: `kani_log/`'s triage is recorded in the parent plan, and
  `trust_audit/`'s final eleven-module selection leaves 23 killed and 23
  equivalent across 46 probes with nothing unaccounted for.
  - `kani_log/`: 1100 mutants, 986 killed, 110 survived, 4 timeouts on the
    first full run.
  - `trust_audit/`: 922 mutants, 760 killed, 153 survived, 9 timeouts.
  - The `trust_audit/` census was then re-measured against a widened test
    selection. mutmut's `pytest_add_cli_args_test_selection` is a fixed list,
    not a glob, so the census was running the four suites that existed when it
    was configured (`test_trust_audit.py`, `..._lexer.py`, `..._crates.py`,
    `..._check.py`) and three survivor modules, while six further trust-audit
    suites — including `test_trust_audit_module_survivors.py` — had never been
    selected. Listing every `scripts/tests/test_trust_audit*.py` and re-running
    the 75 outstanding survivors killed 42 that the narrower selection had left
    alive; a second pass over the residual 33 killed 6 more. 27 remain, and the
    21 the equivalence analysis already covered are confirmed.
  - The final six were run as explicit probes rather than left as survivors,
    because each needed a hand-built input the corpus never spells. Over that
    eleven-module selection the census is **23 killed, 23 equivalent, 0
    unaccounted** across 46 probes, with `baseline PASS` before and after, so
    the working tree each probe ran against was sound. Four were real test
    gaps and are now killed: `Cursor.skip_until_6` (`find` → `rfind`, which
    reports 5,332 differences across 523,137 probes and would let a raw
    literal swallow the code after it), `module_references_6` (`or` → `and`),
    `opening_bracket_10` and `opening_paren_10` (each a `-2` stop that wraps
    to `tokens[-1]`). Two are equivalent and argued in
    `test_trust_audit_structure_survivors.py`'s module docstring:
    `skip_visibility_2` and `skip_visibility_3`, distinguished from the
    pristine form only at index zero, where the answer is `0` under every
    form — an exhaustive differential run over 6,501,848 token sequences and
    indices, including exceptions, found no difference. Log:
    `/tmp/killmatrix-trust-1-2-1-profiles-and-trust-audit.out`.
  - Two production defects fell out of the survivor triage; see below.

### EP-M5 findings so far

- The corpus decided every outcome class except `verified` at full profile, so
  VO-12's positive record could not exist: `insufficient_unwind` reaches
  `full-profile` but is resource-exhausted. Kani 0.67.0 passes `--unwind N` to
  CBMC only when a per-harness bound is requested, and CBMC's own help says
  `--unwinding-assertions` "cannot be used with --cover", so every earlier
  corpus log decided `focused` no matter how complete its run. Capturing with
  `--default-unwind 2` makes CBMC echo `--unwind` for blocks the recording
  never asked to bound, which is what reaches the mode.
- `default_unwind.log` was captured through the probe's own CLI rather than by
  hand, so `provenance.json` records the exact command and `harnesses.json`
  gains the subject that reproduces it. A log captured by hand would have been
  the one capture in the corpus with no reproducible route.
- `_run_mode` compares the claim results with the manifest claim set as a
  **set**, with a guard for duplicates. Kani emits harness blocks in its own
  order regardless of `--harness` flag order, so a sequence comparison would
  fail for a correct run.
- `bound_sources` indexed `result_artefacts[0]` unconditionally. Nothing hit it
  while the registry was empty; registering `kani` made the scanner run over
  every record, and the schema permits an empty array. It now refuses with
  `MissingEvidence` — the fail-closed direction — rather than raising.
- The corpus is self-describing: a new log must be registered in
  `expected.json`'s `logs` *and* `decisions`, or `test_kani_log_decide.py`
  raises `KeyError`. Deriving the entry from the parsed log and then checking
  every field against the raw text is what keeps the recorded facts honest.
- VO-13 has two axes, not one. ``some-unsatisfied-witness`` is not an outcome:
  `unsatisfied_cover` decides `verified` while its cover failed, so a check
  reading outcomes alone would let that log be deleted without noticing. The
  check now reads outcomes and witness statuses, and each axis has its own
  non-vacuity case.
- The first `required_classes` implementation returned
  `REQUIRED_OUTCOMES - seen`, a `frozenset`, and then called `.add`. The
  repository corpus masked it because it reaches an undetermined outcome; the
  success-only non-vacuity case caught it immediately. This is the second
  defect a non-vacuity case has found in this milestone, which is the argument
  for writing them.
- `trust_audit/lexer.py`'s `literal_body` measured a raw string's closing fence
  as the symmetric `"#"`, but the real terminator is `"#` — the opening fence
  minus its leading `r`. Every raw literal therefore lost its last character,
  and a proc-macro crate with `let s = r#"kani::assume"#;` audited clean.
  Mutation testing found this; no other test did, because the raw-fence cases
  that existed put vocabulary in the middle of the literal, where losing the
  final character is invisible.
- `trust_audit/matcher.py`'s `_path_attribute` stepped back one token at a time
  through an attribute list and landed on the `#` of the preceding attribute
  rather than its `]`. For `#[path = "…"] #[allow(dead_code)] mod x;` it gave
  up and fell back to the bare `mod x;` search, so the audit read a *different
  file* from the one the crate compiles. With a decoy `src/renamed.rs` present,
  a crate using `kani::assume` audited as `[]`. Both attribute orders were
  confirmed to compile with `rustc --edition 2021`; the walk now searches
  backwards for the `]` rather than assuming a fixed distance, which also
  handles `#![…]` correctly.
- The largest survivor class in both packages was **refusal-message wording**:
  mutations padding a message with `XX…XX`, upper-casing it, or replacing it
  with `None`. Those survive because the tests asserted that *a* refusal
  occurred, not which one. `kani_log`'s own mutations module opens by saying "a
  refusal is only useful if it is the *right* refusal", so the wording is the
  contract; `test_kani_refusal_messages.py` now pins each structural reason in
  full, because a substring assertion is what let the padding survive.
- `command.py`'s `_manifest_for` and `is_procedural_macro_crate` had no direct
  test at all, though they decide whether a crate's *literals* are scanned.
  Inverting the detection, or making the lookup stop at the workspace root
  instead of the nearest manifest, survived every test. A proc-macro member
  beside an ordinary one now covers both directions and the per-member lookup.
- `_first_mismatch` and `bound_sources` share the "exactly one result
  artefact" rule and the same refusal text, so each copy's message mutation
  survived while the other copy was exercised. Both paths are reached, so this
  was never a test gap; the string is now one constant (`ONE_ARTEFACT`) so a
  change to the rule cannot drift between the two refusals.
- `_skip_block_comment` had two one-character edge cases that nothing covered.
  `/**/ x` refused as an *unterminated* comment, because consuming three
  characters at the opener ate the `/` of the closer. And `/*a*/x` lost the `x`
  entirely, because consuming three at the closer ate its first letter —
  invisible in `/*a*/ x`, where the extra character is whitespace. Both are
  fail-open: the first refuses a valid file, the second silently drops code
  from the audit. Both now have cases in `test_trust_audit_lexer.py`.
- Nine mutants remain `not checked` in every trust sweep, and they are all
  hangs rather than failures: they mutate `_skip_trivia`'s loop-exit condition
  or `tokenize`'s literal branch into a form that never advances the cursor. A
  timeout is mutmut's honest report for them, and they are flagged rather than
  silently counted as killed.
- `test_validation_report.py`'s fixture must copy every directory a pin site
  lives in — `tests`, `crates`, and `src` as well as the five it already had —
  because `_pin_sites` requires a cited site to exist and `cargo metadata`
  needs the workspace members. Weakening either rule would have made the
  fixture easier and the check weaker.

## EP-M4 review round: the AC-04 workload and the profile splits

The 2026-11-07 CodeRabbit ExecPlan assessment raised seven findings. This
section records the four that changed production code or the measurement
workflow; the plan checkboxes above record the rest.

- **F4, the AC-04 job measured the wrong thing.** `build-budget` was a matrix
  over the two Cargo profiles, so AC-04's "Profiles alternate run by run" could
  not happen — each leg is a separate machine — and the proof profile was not
  measured at all. It is now a single leg with no `strategy`, and each of five
  passes measures `native-only`, `polars-enabled`, then `proof`, in both
  phases. An `alternates within one runner` case pins the absent `strategy`, so
  reintroducing a matrix fails rather than silently un-interleaving the record.
- The pre-repair workflow was proved wrong by a hosted run rather than by
  reading. Dispatch run
  [42426500134](https://github.com/leynos/combobulate/actions/runs/42426500134)
  on head `ad5945b` failed only at `build-budget (proof)`: the other nine legs
  passed. Its log shows
  `prover-tools kani exec --cwd crates/combobulate-kernel` stopped with
  `Command "kani exec" parameter --installation requires an argument`, exit 2,
  before any compilation. So the proof profile supplied no sample at all under
  the old shape, and the helper route was not merely unreachable for this
  repository's backend but under-specified in the workflow.
- The proof profile could not use the helper's `kani exec` route.
  `prover-tools kani exec` fails with
  `Kani exec cannot prove isolation of Cargo backend configuration`
  (`rust_prover_tools/kani_release_config.py`'s `_UNPROVED_BACKEND`) because
  `.cargo/config.toml` selects Cranelift for the dev profile. That is DL-24's
  recorded behaviour, not a defect to repair: the accepted route for this
  repository is the direct driver, which is also what the corpus uses. The job
  now writes a `build-budget/kani-codegen` launcher that invokes
  `"$KANI_HOME/bin/kani-driver" kani --only-codegen` with the environment the
  driver needs — the release's own SDK toolchain via `RUSTUP_TOOLCHAIN`,
  `RUSTFLAGS="-D warnings"`, an LLVM `CARGO_PROFILE_DEV_CODEGEN_BACKEND`, and
  the release's `bin` and `toolchain/bin` ahead of `PATH`. The launcher is
  written once and its text is preserved in the artefact upload, so five
  samples cannot drift apart. `KANI_HOME` is derived from `tools/kani/VERSION`,
  and the comment deliberately does not restate the version: doing so would
  duplicate the pin and had already tripped the pin sweep.
- The kernel was not a legal Kani codegen subject. `combobulate-kernel` is
  `#![no_std]` and has no harness until task 1.2.4, so Kani refused it with
  `Failed to detect Kani functions`. `#[cfg(kani)] extern crate kani;` is
  Kani's own prescribed fix. It adds no dependency edge, `cfg(kani)` is false
  in every ordinary build, and the workspace already declares `cfg(kani)` in its
  `unexpected_cfgs` table. It replaces no production body, which is the
  substitution technical design §17.7 forbids; the code comment records that
  distinction.
- Cold and incremental semantics were not actually enforced. Cold targets are
  now emptied before every timed invocation and deleted afterwards (ten live
  targets would exhaust the runner's disk), and one warm-up is discarded per
  phase *including the proof profile* — without that, the measured first
  incremental sample would include the initial compile. The incremental phase
  touches each profile's own crate root and reverts it afterwards.
- **F6/F7, the gate profiles reached only Clippy.** `make lint` linted per
  profile for Clippy but ran Whitaker once with no flags, so Whitaker checked
  only the default features — which are the Polars-enabled profile. The
  `cfg(not(feature = "polars"))` code the native-only profile exists to cover
  never reached any lint. `lint-whitaker` now loops over `GATE_PROFILES` and
  forwards each profile's flags after `--`; Whitaker shells out to
  `cargo check`, so that selection is what it type-checks.
- Polars leaked its own error type out of the module that owns it.
  `polars_backend_probe` returned `polars::prelude::PolarsResult`, putting a
  `polars::` path in the facade's public signature, which DL-19's confinement
  and the new `polars-confinement` gate (VO-14) reject. The backend now reports
  its own `BackendProbeError` carrying Polars' message as text, converted once
  in a private `collect()`, and the facade re-exports that type only under the
  feature.
- The outward-facing checks moved to `tests/workspace_profiles.rs`. Adding
  VO-4's resolved-feature assertion to `tests/workspace_boundaries.rs` pushed
  it past the 400-line limit, so the profile contracts split out and the shared
  read layer became `tests/support/live_cargo.rs`. Both binaries declare it, so
  it carries an `#[expect(dead_code)]` naming the reason rather than an
  `allow`; the exception fails loudly once the split is no longer needed.
- `bound_sources` no longer restates a source's refusal. It used to replace
  `read_tracked`'s reason with "it is not a tracked file inside the repository"
  for every failure, which made an untracked source, a digest drift, and an
  unreadable file indistinguishable to the record's author and hid the digest
  check DL-16 requires. It now propagates `read_artefact`'s refusal, and the
  scanner cases pin the untracked and drifted classes separately. The
  empty-source refusal still belongs to the manifest: a manifest whose sources
  carry no digest names nothing auditable, which is a defect in the manifest.
- **F2's alias rule is a module, not a method on the matcher.** Teaching
  `matcher.py` about `use kani as k;` pushed it from 399 to 451 lines, past the
  400-line limit. The `use`-tree reader — root, alias, and statement end —
  moved to `trust_audit/use_tree.py` (91 lines), which is a coherent unit: it
  reads what the source says and decides nothing about vocabulary. The matcher
  imports `alias_bindings` and `use_root` and keeps its own rules. Its cases
  moved with it to `test_trust_audit_use_tree.py`, which exercises the reader
  directly rather than through `scan`, so a mutant there is caught by the
  function it lives in.
- The manifest source-list cases moved to `test_kani_manifest_source_list.py`.
  They test `shell._manifest_sources`'s *input shape*, while
  `test_kani_binding_survivors.py` tests the decision and binding surfaces
  built on top, and the combined module had grown to 439 lines. The equivalence
  argument for the moved defaults stays in the survivor module's docstring with
  a pointer to the new home, so the mutation-census record is still complete.
- The confinement detector takes text, not a path. `_polars_paths` used to read
  the file itself, so the only way to test it was to write a temporary source
  tree and the only thing it could be asked about was a file that existed. It
  now accepts `text: str` and the one caller in `check_polars_confinement`
  reads the file, which lets the rename cases — `use polars as p;`,
  `use polars::{self as p};`, and `use polars::prelude as p;` — be stated as
  three strings rather than three fixtures. It also lets the seeded-detector
  case judge the detector the real check uses, because a double can now stand
  in where a file path could not be substituted. The rename resolution is
  `alias_bindings` from the trust audit, so the confinement rule and the audit
  cannot disagree about what renames a root; that sharing is why the detector
  moved to a text signature without a second lexer of its own.

## Ruled out

- Ticking 1.2.1 before EP-M3 to EP-M6 complete. The parent plan's EP-M6 binds
  the tick to D16 and to the milestones; `roadmap_status.py` validates a
  claim's shape rather than its truth, so the checks passing does not make the
  claim true.
- Ticking the task's detail checkbox. `scripts/export_roadmap.py` raises
  `detail checkboxes are not tracked; tick the task instead`, and no ticked
  task in the repository carries a ticked detail.
- Copying `.cargo`, `crates`, and `src` into the `test_validation_report`
  fixture was needed only by the withheld tick, whose record cited manifests in
  those directories. It is not part of EP-M3 and stays in the withheld patch.

## Resolving the hosted coverage shortfall

Hosted `build-test` reports `Current coverage: 98.92%` against a 100 % baseline
at `59f8f2a`, and the ratchet fails. The figure is stable across runs, so it is
a real measurement rather than noise.

The measurement path is now known exactly, and three of the assumptions made
earlier in this branch were wrong:

- The percentage is `sum(LH) / sum(LF)` over every `end_of_record` in
  `lcov.info`, computed by `get_line_coverage_percent_from_lcov` in the
  shared-actions action pinned as `generate-coverage@dbe2e22c`. There is no
  file filter, no path exclusion, and no `--ignore-filename-regex` anywhere in
  the action.
- The command is a plain `cargo llvm-cov nextest` over the manifest and
  workspace, exporting lcov, with `with-default-features: true`,
  `all-targets: false`, and `doctests: false`. `cucumber` is disabled, so the
  `_merge_lcov` path never runs and `lcov.info` is exactly what
  `cargo llvm-cov` wrote.
- `LF` is not the number of `DA` records. A closure the suite never executes
  still contributes an `LF` line while carrying no `DA` record at all, so that
  line is counted in `LF` and never in `LH`. This is what produced the
  shortfall, and it is not a property of multi-line expressions in general.

Locally, reproducing the ratio needed the same codegen backend the action
forces. `.cargo/config.toml` selects `cranelift` for the dev profile, while the
workflow sets `CARGO_PROFILE_DEV_CODEGEN_BACKEND: llvm`; the two backends emit
different line tables for the same source. The workflow's
`-C link-arg=-fuse-ld=lld` cannot be reproduced on this host because `lld` is
not installed and there is no passwordless `sudo` to add it, so local
reproduction substitutes `mold`. The linker does not affect which source lines
are instrumented, so the substitution is sound for this question.

The arithmetic that reconciles the hosted figure, using the widest `LF` each
production file reports in any single binary: `crates/combobulate-kernel` 10/10,
`src/lib.rs` 3/3, `src/profile.rs` 34/34, and `src/polars_backend.rs` 45/46
sum to 92/93, which is 98.92 % exactly. The `profile.rs` and `src/lib.rs`
figures come from the binary that reaches their test modules; a partial union
reports less for them, because a binary that does not link a test module cannot
record it. `crates/combobulate-macros` contributes nothing: it is a
`proc-macro` crate whose five lines are all `//!` documentation, so it has no
executable line to count.

The one uncovered line was line 85, the `map_err` **closure** in
`collected_height`:

```rust
collect().map_err(|error| BackendProbeError::from_polars(&error))
```

`collect()` succeeds for every frame the probe builds, so the closure never
runs. The earlier reading of this section was wrong on that point: it blamed a
continuation line inside `write!` and proposed splitting the `Display` body.
That change was applied, measured, and **falsified** — it left `LF=94 LH=93`
untouched, and isolation probes in a scratch crate gave `gap=0` for both
`Display` shapes. The `Display` body is unrelated to the defect and is
unchanged.

What the evidence actually shows is a property of **closures**, not of
multi-line expressions. The raw record for the file carried 45 `DA` records,
every one of them hit, alongside `LF:46` and `LH:45`, and
`llvm-cov report --summary-only` named one missed line and one missed function:
the zero-total instantiation `collected_height::{closure#0}`, with both of its
regions on line 85. A closure the suite cannot reach is still a function
instantiation, and llvm attributes its line to `LF` while never emitting a `DA`
record for it, so no test can turn that line green. A scratch probe confirmed
the mechanism directly: an inline `map_err` closure that *is* exercised still
produced `LF=26` against 25 `DA` records, while a `match` in the same position
produced none.

The fix is therefore not a new test and not a reflowed expression: it is
removal of the closure. The fold is now a named item that `collected_height`
calls, and its error arm calls `from_polars` with a borrow:

```rust
fn fold_collected(collected: PolarsResult<usize>) -> Result<usize, BackendProbeError> {
    match collected {
        Ok(height) => Ok(height),
        Err(error) => Err(BackendProbeError::from_polars(&error)),
    }
}
```

A first attempt kept `map_err` and made `from_polars` take its error by value,
so it could be passed as a function item with no closure. That measured 100 %
too, and was rejected by the gate: `error.to_string()` only borrows, so Clippy
rejected the by-value parameter as `needless_pass_by_value`. The `match` shape
has neither problem — no closure to instantiate and no unconsumed argument.

`from_polars` stays its own item for the reason already recorded on it: the
suite must be able to call it with a hand-built `ComputeError`, because the
probe's own collection never fails. It is deliberately not a
`From<PolarsError>` impl — that would be public API handing every embedder a
route from a Polars type to the facade's error, which is the leak DL-19 exists
to prevent.

Measured on a full-workspace export under the hosted backend and link flags
(`CARGO_PROFILE_DEV_CODEGEN_BACKEND=llvm`, `-C link-arg=-fuse-ld=mold` as the
`lld` substitute), with all 398 tests passing:

| file                 | before    | after     |
| -------------------- | --------- | --------- |
| `combobulate-kernel` | 10/10     | 10/10     |
| `src/lib.rs`         | 3/3       | 3/3       |
| `src/profile.rs`     | 34/34     | 34/34     |
| `src/polars_backend` | 45/46     | 45/45     |
| **total**            | **92/93** | **92/92** |

`92/92` is 100.00 %, and `cargo llvm-cov report --summary-only` now reports
`polars_backend.rs` with 45 lines, 0 missed, and 8 functions, 0 missed. The
line total fell from 47 to 45 rather than from 46 to 45 because the phantom
pair went with the closure; the executed lines were already all covered. The
92/93 reconciliation quoted earlier in this section was therefore correct
arithmetic built on a misidentified line, and its conclusion — that nothing
short of a source change would close the gap — was right for the wrong reason.

The lesson recorded here is about method, not about llvm: the diagnosis was
adopted before it was measured, and three successive hypotheses were asserted
as confirmed and then falsified. The one that survived is the one that was
checked against llvm's own missed-line and missed-function counts before being
written down.

## Rebase onto the target branch

The branch was cut at `408aba7`; `origin/main` has since advanced to `0f41741`
with four pull requests, one of which touches files this branch also edits. Two
of them are reconciled in the rebase rather than carried as divergent copies:

- `tests/workspace_boundaries.rs` and
  `tests/support/make_gate_order_commands.rs` lost `CommandDeadline` upstream:
  `0f41741` ("Let nextest own test timeouts; remove `CommandDeadline`") deleted
  `tests/process_deadline.rs`, `tests/support/process_deadline.rs`, and
  `tests/support/process_deadline_fixture.rs`, and replaced every live read
  with a plain `std::process::Command`. This branch had added a VO-4 Polars
  test to `workspace_boundaries.rs` on top of the old, bounded `run_bounded`
  helper; the rebase keeps the upstream shape — `run_read` returning `Output`,
  no deadline module — and re-attaches `polars_appears_only_when_enabled` and
  `PINNED_POLARS` to it. The rest of the branch's edits to
  `make_gate_order_commands.rs` (the DL-18 per-profile stages) are unrelated to
  the removal and merge cleanly.
- `docs/developers-guide.md` upstream now states that tests start plain
  commands and that nextest owns the bound. The branch's new sections (Gate
  profiles, Workspace layout and module ownership) sit below that text.

`tests/cardinality_probe_ui.rs` and the three `process_deadline` modules are
untouched by this branch, so the rebase takes upstream's deletion and rewrite
without conflict; `make test-ui` remains the one bounded route, as the target's
developer guide now states.

## Gate policy for this branch

Run every gate on `make` targets rather than bare Cargo, sequentially, one at a
time, and let the shared compile-admission queue serialize the rest. Do not run
a second build to speed up a queued one.

## Staging discipline while a mutation census runs

`git add -A` captured a live mutant. While the `artisan` held
`skip_visibility_2` (`>= 0` → `> 0`) applied to
`scripts/docs_validation/trust_audit/structure.py`, a commit ran and recorded
the mutant as production source. The mutant is semantically equivalent, so no
gate result was invalidated by behaviour — but the provenance was wrong, and
that is the failure that matters: a committed file must be the change the
commit message describes, not whatever a concurrent process had written at the
instant `add` ran.

The diagnosis took longer than the fix because it was first run backwards. The
committed text was assumed authoritative and the snapshot in `/tmp` assumed
contaminated, and a `git checkout --` on that assumption preserved the mutant
and discarded the good copy. The artisan's report was the only thing pointing
the other way; four witnesses confirmed it — `mutmut show`, the census tree,
and two revisions predating the commit — and a fifth settled it: `8107e4d` and
`2a7b7a0` are the *same tree* saved 33 seconds apart for an unrelated rebase,
and both read `>= 0`, so two independent captures agreed against the commit.

The rules that follow:

- Commit only after confirming no subagent is mutating the tree. A census that
  applies mutants in place and restores them has no safe overlap with `add`.
- Stage explicitly by path, never `-A`, while any process may be writing.
- Prefer a pre-census snapshot over the working tree when adjudicating
  contamination. Git history is the oracle; a `/tmp` census tree is a working
  copy that mutmut leaves with a mutant applied, so it is not pristine either.
- When HEAD and a snapshot disagree, do not assume HEAD is right. Ask when each
  was produced, and prefer the one written before the suspect event.

The mutant was removed from history by amending, which was safe because the
branch had never been pushed. Production source under `scripts/` is now
byte-identical to the pre-contamination snapshot; the only remaining deltas
against that snapshot are documentation, `spec/` records, and the survivor
tests the artisan deliberately wrote.

## The hosted gate profile leaks into the Make contract probes

Hosted CI ran three Makefile-contract tests red that pass locally. The cause
was not the contracts: each hosted job exports `GATE_PROFILE` for the single
profile it was scheduled to measure, and every probe shelled out to a child
`make` without neutralizing it. The Makefile honours the inherited value, so an
asserted two-profile route collapsed to one — `9` recorded executors became
`7`, and `nextest run --all-targets --no-default-features` became
`nextest run --all-targets`. nextest cancels the remaining tests after a first
failure, so the hosted run reported three failures while `387` further tests
never ran; the same exposure in `make_gate_order` and `build_standard_contract`
was latent rather than absent.

Make's precedence is what makes one rule cover every delivery route, verified
directly in a scratch Makefile:

- an exported `GATE_PROFILE` reaches a nested `make` and wins on level;
- a command-line assignment on the child outranks the exported value;
- a command-line assignment on the child also outranks the same assignment
  replayed through inherited `MAKEFLAGS`, which is the one route an inherited
  command-line assignment cannot beat.

So each harness that asserts the default route now passes `GATE_PROFILE=both`
on the child command line and removes the variable from the child environment.
The pin alone covers the `MAKEFLAGS` route; the removal alone covers the
exported route; together they cover both. The regression in
`tests/make_gate_order.rs` injects each route separately and was confirmed to
fail with the pin removed, so it tests the defect rather than passing vacuously.

The lesson generalizes past `GATE_PROFILE`: a contract probe that shells out to
a build tool inherits whatever the measuring job exported, so the probe must
state the routing it assumes rather than accept the caller's. A local pass is
not evidence about the hosted route for this class of test.

## The native-only measurement missed the optional-backend loop

Once the Make contracts went green, hosted `build-test` still failed, now on
the other side of the job: `Current coverage: 95.45%` against a 100 % baseline,
`Coverage decreased`, tolerance ±1.00 percentage points. 95.45 % is exactly
21/22, and it is the **native-only** route, so it is a different measurement
from the 92/93 = 98.92 % reconciled above — that one was taken with default
features, where `src/polars_backend.rs` is the file under test. Nothing in the
earlier section applies to this failure except its method.

The whole workspace under `--no-default-features` instruments two files. A local
`cargo llvm-cov nextest --workspace --no-default-features --lcov` reproduction
(hosted backend and link flags, 402 tests passing) gave:

| file                 | hit/found |
| -------------------- | --------- |
| `combobulate-kernel` | 10/10     |
| `src/profile.rs`     | 32/34     |
| **total**            | **42/44** |

`42/44` is 95.4545 %, which rounds to 95.45 %. The two missed lines are 78 and
79, the body of the loop in `Display`:

```rust
for name in self.optional_backend_names() {
    formatter.write_str(", ")?;
    formatter.write_str(name)?;
}
```

This is a genuine test gap and not the closure artefact recorded earlier. The
loop is reached and its `for` header is hit, but the body executes only when a
backend is present. In the native-only profile both `has_macros` and
`has_polars` are compile-time `false`, so the iterator is always empty, the
body can never run, and no integration test built native-only can reach it. The
existing unit tests call `to_string()` too, but in that profile they render the
empty case as well.

The fix constructs the profile directly, which is possible because the test
module is a child of the defining module, and renders all four combinations:

```rust
#[rstest]
#[case::native(false, false, "native")]
#[case::macros(true, false, "native, macros")]
#[case::polars(false, true, "native, polars")]
#[case::both(true, true, "native, macros, polars")]
fn display_names_each_compiled_backend(/* ... */) { /* ... */ }
```

Measuring the fix on the narrowed target
(`-p combobulate --lib --no-default-features`) gave `src/profile.rs` 34/34, so
the workspace figure becomes 44/44 = 100.00 %, and hosted `build-test` at the
pushed head reported `Current coverage: 100.00%` against the same 100.0
baseline.

The denominator did not grow, which is worth recording because the opposite is
the natural guess. `LF` stayed at 34 and only `LH` moved, 32 to 34. The new
test body carries **no `DA` records at all**; the report's instrumented lines
skip the whole span the function occupies. That is the same `LF`-versus-`DA`
asymmetry recorded earlier in this document, running in the opposite direction:
there, a line counted toward `LF` with no `DA` record; here, the `rstest`
expansion is attributed no line at all, so adding it costs the ratio nothing.
The two lines it does cover were already in the denominator, because they
belong to the production `Display` body rather than to the test.

This is a property of this expansion, not a general licence to assume tests are
free. A handwritten test module's own statements *are* instrumented — the `DA`
records at lines 128-149 are the pre-existing unit tests — so a new `#[test]`
written by hand can lower the ratio if part of it does not run. The cases here
land in an expansion llvm attributes no line to, which is why the measurement
moved in one direction only.

The broader lesson is the one this branch keeps relearning: a profile is a
different program. Code that is unreachable under `--no-default-features` is
not covered by a test that passes in both profiles, and the only way to know
which lines those are is to measure the profile the gate measures.

## The coverage baseline is vacuous on `main`

The 100 % baseline the ratchet compares against was not earned. On
`origin/main` the only instrumented source is
`crates/combobulate-kernel/src/lib.rs`; the facade's `src/lib.rs` and
`crates/combobulate-macros/src/lib.rs` are doc-comment only and contribute no
executable line, and main has no `[features]` table at all. `coverage-main.yml`
on main also omits `with-default-features`, so it measures the default profile.
The baseline is therefore "100 % of a tree with one small file in it", and any
branch that adds real code starts below it.

This cannot be bootstrapped from this branch by editing anything. The stored
baseline is not a tracked file: it is an Actions cache entry written by the
action's "Save baselines" step, and that step runs only when
`inputs.publish-baseline == 'always'` or the event is a push to
`refs/heads/main`. A pull request cannot advance it, by design, so that a
branch run never moves the trunk baseline later pull requests are compared
against.

Merging this branch is therefore the bootstrap, and it works because of the
`coverage-main.yml` change it carries. On `main` today that workflow omits
`with-default-features`, so it measures the default profile over a tree that
has one small file and reports 100 %. After the merge it passes
`with-default-features: 'false'` and `features: ''`, exactly as `ci.yml` does,
so `main` re-measures **44/44 = 100.00 %** over the same native-only profile
the pull request gate checks. The baseline holds at 100.0 (the advance branch
needs `current > baseline + 1.0`), and from then on the 100 % figure means
"every one of the 44 instrumented lines in the native-only profile executes"
rather than "the tree is nearly empty".

The defensible resolution is therefore the one taken: make the branch's
measured profile genuinely 100 % covered, which is a real statement about the
code rather than a re-based number, and leave the baseline where it is. The
alternative — lowering the stored baseline — would record a regression against
a number that was never earned, and would hide exactly the kind of gap this
section was written to find.

One residual caveat is worth stating rather than discovering later. The
baseline cache is restored by prefix `ratchet-baseline-${{ runner.os }}-` and
newest-match wins, so a `main` run always reads the entry the previous `main`
run wrote. The first `main` run after the merge restores the 100.0 written by
the last vacuous measurement and saves a fresh 100.00 over the native-only
profile; from the second run onward the comparison is native-only to
native-only. The one handover is therefore a comparison of the same number
computed two different ways, which passes because both are exactly 100.00, not
because the tolerance absorbs it.

## DL-03's cache clause needed a wrapper the workflows never set

DL-03 says every hosted job runs sccache with the GitHub Actions cache backend,
and the workflows said `use-sccache: 'true'` on the pinned `setup-rust` action,
so the clause looked satisfied. It was not. That action runs
`mozilla-actions/sccache-action`, which installs the binary and exports
`SCCACHE_PATH`, and never sets `RUSTC_WRAPPER`; its own README asks the caller
to set both `RUSTC_WRAPPER: sccache` and `SCCACHE_GHA_ENABLED: "true"`. No job
set either, so every hosted compile ran unwrapped and the cache recorded
`Compile requests 0`.

The failure is silent by construction, which is why it survived several green
runs. Cargo does not reject an unusable `RUSTC_WRAPPER`; it ignores it. A value
naming a file that does not exist, or that is not executable, leaves the build
successful and uncached. So the claim "sccache is enabled" could be made in
good faith from the workflow text while being false of the run.

The remedy is threefold and each part is separately contracted:

- all three `ci.yml` jobs and `coverage-main.yml`'s `coverage-upload` declare
  `RUSTC_WRAPPER: sccache` and `SCCACHE_GHA_ENABLED: "true"` in the job `env`,
  so the provisioning steps and the gate routes inherit them;
- each job runs `Report sccache wiring`, which resolves the wrapper on `PATH`
  with `command -v` and prints `sccache --show-stats`, whose cache-location
  line names the backend the server is using. `--show-stats` needs no compile,
  so the evidence exists before a gate can fail and hide it;
- `tests/support/act_workflow_jobs.rs` pins both variables per job and the
  wiring step's position, `act_workflow_policy.rs` pins the step's exact
  script, and three new mutations in `act_workflow_contract_tests.rs` prove a
  lost wrapper, a lost backend, and a lost `--show-stats` each fail the
  contract.

Wrapping measured coverage was the part worth checking before it was done,
because the coverage step sets `CARGO_PROFILE_DEV_CODEGEN_BACKEND: llvm` and
`RUSTFLAGS` with `-C instrument-coverage`. Two facts settle it, both read from
sccache v0.19.0's `src/compiler/rust.rs`: `-C instrument-coverage` is not a
`cannot_cache!` trigger, and the full rustc command line is part of the cache
key, so an instrumented object and an uninstrumented one are never the same
entry. Wrapping the coverage step therefore cannot serve a wrong object.

The Act smoke needed a matching change, because the derived job now runs the
wiring step before `make install-build-tools` and the fixture PATH carried no
`sccache`. A stub that answers `--show-stats` is written beside the existing
`make`/`cargo`/`rustc` stubs, and the stub's trace line records it like any
other executor.

### The evidence step first named a flag that does not exist

The first version of the wiring step called `sccache --show-config`. No sccache
release has that flag; 0.19.0's own usage line lists `--dist-auth`,
`--debug-preprocessor-cache`, `--dist-status`, `--show-stats`,
`--show-adv-stats`, `--start-server`, `--stop-server`, `--zero-stats`,
`--package-toolchain`, and a compiler command, and `--show-config` is not among
them. The step exited 2 and failed `build-test`, `polars-test`, and
`polars-lint` on the first hosted run at `71e5ea1`, which is the run that was
supposed to prove the wiring.

The failure is worth recording for two reasons. First, it is the mirror image
of the defect the step was added to catch: a claim about a tool's behaviour
made from its name rather than from its interface. The remedy that worked for
the missing wrapper — make the claim observable — is what exposed this one,
because a step that silently did nothing could not have failed. Second, the
contract pin did not help: `act_workflow_policy.rs` pinned the exact script,
including the bad flag, so the tests were green and the suite asserted the
mistake rather than catching it. Pinning a command's text proves the workflow
says what was intended; only running the command against the real binary proves
the text works.

`--show-stats` is the substitute, chosen because it is present in both the
pinned 0.19.0 and older releases and its `Cache location` line reports the
backend the server is actually using, which is the fact the step exists to
record. The local host's 0.14.0 prints the same line, so the diagnostic does
not depend on the version. The lesson is narrower than "check your action's
inputs". An action can provide a tool without making it reachable, a tool that
is silently optional will not report its own absence, and a flag named from
memory rather than from the binary's usage is a claim that needs the same
evidence as any other. Where a claim is load-bearing, the pipeline needs a step
whose failure is observable — and the step's own commands need to be real.

## AC-04 stays representative after the cache change

The acceptance record's conditions already read "no sccache", so adding
`RUSTC_WRAPPER` to the gate jobs raises the question of whether the measurement
still describes the shipped build.

The first version of this section claimed the control's workload was unchanged.
That was wrong, and the error is worth keeping visible: a reviewer asked for
the representativeness argument, and the answer written here compared the files
that are easiest to name rather than the files the timed commands actually
compile. Blob comparison against `5f53ed6` gives the real picture.

Identical: `Cargo.toml`, `Cargo.lock`, `.cargo/config.toml`,
`rust-toolchain.toml`, `src/lib.rs`, `crates/combobulate-kernel/Cargo.toml`, and
`crates/combobulate-kernel/src/lib.rs`. So the manifests, the dependency
graph, the toolchain pins, the backend selection, and the proof profile's
entire subject are the same as the recorded run's.

Changed: `src/profile.rs` (+34) and `src/polars_backend.rs` (+95). Both are
inside the compiled graphs of the two Cargo profiles, so the measured
workspaces are not textually identical to the recorded one. The recorded
medians — native cold 0.30 s and Polars cold 65.08 s — measured a workspace
about 124 lines smaller.

Unchanged where it matters: `build-budget` has no diff from `5f53ed6`. The one
change in `profile-measurements.yml` is in the separate `measure-profile` job,
which AC-04 does not register. And the lane still measures with no cache:
`build-budget` asserts `test -z "${RUSTC_WRAPPER-}"`, and
`test_profile_measurement_workflow.py` pins that assertion along with the
absence of `SCCACHE_RECACHE`.

The verdict is therefore narrower than "representative". The conditions and the
protocol are unchanged and no cache contaminates the samples; the workload grew
slightly, which inflates a measured build without changing what the control
measures. Every median sits far inside its ceiling — the tightest margin is
Polars cold at roughly 9× headroom against 10 minutes — so growth of this order
cannot plausibly move a verdict. That is an inference from headroom, not a
re-measurement. Re-running `build-budget` at this head is what would discharge
it, and it was not run: the lane is reserved, takes about 90 minutes, and its
result would replace a record `check_measurement_binding` currently accepts.
Recorded so the inference is visible rather than mistaken for proof.

One weakness is real and deliberately left for its own change. The
`RUSTC_WRAPPER` assertion sits before the `setup-rust` step rather than after
it, so it proves the ambient environment at job start rather than the
environment the timed builds inherit. `setup-rust` sets neither `RUSTC_WRAPPER`
nor `SCCACHE_GHA_ENABLED` — verified against the pinned `47b337e4` action,
which only runs `mozilla-actions/sccache-action` and exports nothing — so the
two environments agree today. Moving the assertion to the last step before the
loop is still the right hardening, because it would survive a future change to
the action's outputs. It is not part of this change: it alters a different
workflow from the one under repair, and the defect it guards against cannot
currently fire. Recorded here so the follow-up has its rationale.

## Round 2: two findings that survived the first disposition

The second assessment accepted five of the earlier findings and raised two new
ones. Both are real. Recording them here with the evidence, because each was
established by running the code rather than by reading it.

### A grouped import was read one root deep

`use_tree.use_root` returns the first identifier of a `use` statement. For
`use {std::mem, kani as k};` that is `std`, so `alias_bindings` skips the
statement entirely and `k::assume` is never reported. The bug is visible as an
order dependence, which is what makes it a defect rather than a stated limit:

```text
use {std::mem, kani as k};   bindings ['kani']        <- alias lost
use {kani as k, std::mem};   bindings ['k', 'kani']   <- alias found
```

The same statement must not mean two different things because of member order.
The audit has two consumers of that reader and both were wrong in the same way:
`matcher._imported_roots` also calls `use_root`, so even an unaliased
`use {std::mem, kani};` left `kani` out of the imported-root set that gates
rule (iii). And `polars_confinement._polars_paths` resolves through
`alias_bindings`, so `use {std::mem, polars as p};` escaped the confinement
control by the same route.

The repair reads every root a statement names, with its own alias, instead of
one. `use_roots` returns one `(root, alias)` per root in the tree; the single-
root callers keep working because the rarer spellings degrade to no alias
rather than to no root.

The split is keyed on how the statement *starts*, not on whether a brace
appears anywhere. A statement beginning with `{` names several roots, so its
top-level members are read one by one; a statement beginning with an identifier
names one root, and any later brace lists that root's members. That distinction
is what keeps `use kani::{self as k};` working through the existing
per-statement code rather than a second implementation. Six reader-level
regressions and one per consumer pin it, including both member orders of the
same import, since the order dependence is the thing that made the old answer
wrong.

### The cache saved on every pull request

DL-03's decision text ends "cache saves only on `main`". Nothing enforced it,
and the cache metadata shows the policy inverted. Across 1255 entries (5.59 GB,
against GitHub's 10 GB limit):

| ref                  | entries | bytes   |
| -------------------- | ------- | ------- |
| `refs/pull/53/merge` | 1090    | 1.02 GB |
| `refs/heads/main`    | 25      | 154 MB  |
| `refs/pull/19/merge` | 20      | 831 MB  |

Pulls write; `main` barely does. That is the opposite of what DL-03 asks for,
and at 1 GB per pull it evicts the entries `main` needs.

The first reading of the finding was that `SCCACHE_GHA_ENABLED` has no
read-only mode. That was wrong, and checking the released binary rather than
the action's inputs is what corrected it. `mozilla/sccache` gained
`SCCACHE_GHA_RW_MODE` in `bdbab18`, which `v0.16.0` through `v0.19.0` all
contain, and 0.19.0 is the version the hosted action installs. Its accepted
values are `READ_ONLY` and `READ_WRITE`:

```rust
string_from_env_var(env_var_name).and_then(|value| match value.to_uppercase().as_str() {
    "READ_ONLY" => Some(CacheModeConfig::ReadOnly),
    "READ_WRITE" => Some(CacheModeConfig::ReadWrite),
```

So the repair is a job-level variable rather than a restructure: pull-request
runs read the cache and do not write it, while a push to `main` keeps
`READ_WRITE`. Writes on a pull request are also wasted work — a cache entry
scoped to `refs/pull/N/merge` is never read by a later run of the same branch
once the merge ref advances — so this costs the pull-request jobs nothing they
were benefiting from.

One constraint shaped where the switch lives: `profile-measurements.yml` asserts
`test -z "${RUSTC_WRAPPER-}"` because AC-04 measures with no cache at all.
That lane must keep neither a wrapper nor a cache backend, so the switch
belongs to the three gate jobs in `ci.yml` and to `coverage-main.yml`, never to
the measurement workflows.
