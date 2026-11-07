# ExecPlan progress: EP-M3 and EP-M4 of task 1.2.1

This is a continuation record for
`docs/execplans/1-2-1-establish-workspace-and-profiles.md`. The parent plan is
long and is the authority for every milestone; this file records the working
state of the two milestones currently in progress so a later session can resume
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

- [ ] Red recorded: `tests/features/build_profiles.feature`,
  `tests/build_profiles.rs`, the snapshot tests,
  `tests/native_consumer_e2e.rs`, and the VO-4 and VO-14 checks all fail because
  `BuildProfile` does not exist.
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
- [ ] `tests/native_consumer_e2e.rs` green: build, run, `cargo tree` check, and
  comparison with the `native-only` snapshot.
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
- [ ] CI shape (DL-03, DL-14): parallel Polars-enabled lint and test jobs in
  `ci.yml`, `coverage-main.yml` features set to the native-only profile
  explicitly, GitHub Actions sccache enabled and saved on `main` only.
- [ ] `ci_controls.py`, `preregistration.py`, and their tests accept the
  amended AC-07 workload; `spec/acceptance-controls.json` records the amendment
  with its new `ci.yml` digest.
- [ ] **Checkpoint, sponsor-owned:** approval of the AC-07 amendment text and
  the measured job sizes. EP-M3 is `BLOCKED` until that approval exists.

### EP-M3 findings so far

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
- A shell loop cannot be parallelised by Make and should not be: the point of
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
- [ ] `docs/adrs/adr-0010-workspace-crate-boundaries-and-profiles.md` as
  `Proposed`.
- [ ] Proposed D16 in `spec/decisions.json`, with Q3 added to
  `in_scope_questions` and the register regenerated.
- [ ] The AC-04 amendment drafted (DL-15).

### EP-M4 findings so far

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
D16 and ADR-0010. Note that commit `684f687` retired the approval ceremony, so
these readings are ordinary reviewed file changes; a control that changes after
its acceptance measurement is registered under a new identifier rather than
amended in place.

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

## Gate policy for this branch

Run every gate on `make` targets rather than bare Cargo, sequentially, one at a
time, and let the shared compile-admission queue serialise the rest. Do not run
a second build to speed up a queued one.
