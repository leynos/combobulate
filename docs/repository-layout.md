# Repository layout

Combobulate uses the Rust development structure adapted from Peregrine Web pull
request 11. The facade, `#![no_std]` kernel, and procedural-macro crates now
exist, together with the `native-only` and `polars-enabled` build profiles the
facade features select. The array algebra in the
[technical design](technical-design.md) remains a delivery proposal.

## Paths and responsibilities

| Path                                            | Responsibility                                                                                 |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `src/lib.rs`                                    | Facade crate root; re-exports `BuildProfile` and the gated Polars probe.                       |
| `src/profile.rs`                                | `BuildProfile`, reporting compiled features and target facts.                                  |
| `src/polars_backend.rs`                         | Crate-private Polars module, compiled only under `cfg(feature = "polars")`.                    |
| `crates/combobulate-kernel/`                    | `#![no_std]` kernel crate that owns `TargetFacts`.                                             |
| `crates/combobulate-macros/`                    | `proc-macro` crate for the future `comb!` notation; it exports no macro yet.                   |
| `tests/`                                        | Integration tests for build routes, workflow policy, Make commands, and shell preflights.      |
| `tests/support/`                                | Private helpers owned by the corresponding integration test modules.                           |
| `scripts/`                                      | Toolchain installation, build preflights, native Clang linker wrapper, and all Python scripts. |
| `scripts/tests/`                                | Python unittest and pytest suites, supporting helpers, and fixtures.                           |
| `scripts/docs_validation/`                      | Documentation-model checker package.                                                           |
| `scripts/docs_validation/trust_audit/`          | Trusted-item scanner behind the evidence gate and the trust-audit design check.                |
| `scripts/docs_validation/kani_log/`             | Kani log parser behind the evidence gate's I/O shell, with a pure decision function.           |
| `scripts/docs_validation/toolchain_profiles.py` | Checker binding `spec/toolchain-profiles.json` to every site that asserts a pin.               |
| `scripts/docs_validation/candidate_deferral.py` | Checker refusing a roadmap tick that a deferred candidate ADR subject has outrun.              |
| `scripts/requirements.txt`                      | Shared Python validation and test dependencies.                                                |
| `.cargo/config.toml`                            | Development compiler/backend/linker defaults.                                                  |
| `.github/workflows/ci.yml`                      | Authoritative hosted Rust and build-contract gate.                                             |
| `.github/workflows/design.yml`                  | Design-fixture and documentation-generator validation.                                         |
| `.github/workflows/coverage-main.yml`           | Main-branch coverage publication and ratchet baseline.                                         |
| `.github/workflows/act-validation.yml`          | Manually dispatched full Act compatibility check.                                              |
| `.github/workflows/profile-measurements.yml`    | Hosted profile and build-budget measurements that feed the acceptance controls.                |
| `.github/workflows/formal.yml`                  | Weekly verifier-route check; never gates a merge.                                              |
| `.github/workflows/audit.yml`                   | Scheduled dependency audit.                                                                    |
| `.github/workflows/mutation-testing.yml`        | Scheduled shared Rust mutation workflow.                                                       |
| `.github/dependabot.yml`                        | Cargo and GitHub Actions dependency updates.                                                   |
| `.verus/`                                       | Verus release unpacked by `make install-verus`; Git-ignored, about 1.5 GB per worktree.        |
| `docs/`                                         | Design, guides, reference material, and recorded decisions.                                    |
| `docs/contents.md`                              | Canonical documentation index.                                                                 |
| `docs/adrs/`                                    | ADRs named `adr-nnnn-title-slug.md`; four-digit, zero-padded numbers.                          |
| `docs/rfcs/`                                    | RFCs (none yet), named `rfc-nnnn-title-slug.md`; four-digit, zero-padded numbers.              |
| `docs/execplans/`                               | Execution plans for roadmap work, named after their branch.                                    |
| `spec/`                                         | Machine-readable language, roadmap, proof, cost, and backend contracts.                        |
| `spec/decisions.json`                           | Decision register master, rendered into `docs/decision-register.md`.                           |
| `spec/semantic-contracts.json`                  | Semantic contract records `SC-01` onward, with excluded names.                                 |
| `spec/macro-grammar.json`                       | The `comb!` precedence table and grammar corpus.                                               |
| `spec/acceptance-controls.json`                 | Pre-registered acceptance controls `AC-01` onward.                                             |
| `spec/calibration/`                             | Calibration measurement records behind the control thresholds.                                 |
| `spec/exceptions.json`                          | Trusted-boundary exception register (D02).                                                     |
| `spec/evidence-reason-codes.json`               | Evidence-gate levels, reason codes, and registered log parsers.                                |
| `spec/task-completion.json`                     | Completion records for ticked roadmap tasks.                                                   |
| `tools/`                                        | Calibration probes, linker pins, and reviewed tool metadata.                                   |
| `tools/calibration/`                            | Standalone calibration probes; not workspace members.                                          |
| `tools/kani/`                                   | Pinned Kani version used by the corpus routes.                                                 |
| `tools/verus/`                                  | Pinned Verus release markers and archive checksums.                                            |
| `tools/rust-prover-tools/`                      | Pinned `rust-prover-tools` revision that installs and runs both verifiers.                     |
| `tools/verifier-fixtures/`                      | Non-member Kani corpus and Verus wiring fixtures with captured observations.                   |
| `tools/probes/`                                 | Recorded toolchain and Polars capability observations, plus the Polars profile probe.          |
| `tools/gates/`                                  | Standalone compile-fail gates; each is its own workspace with its own lockfile.                |
| `tools/mold/`                                   | Pinned native linker version and archive digest.                                               |
| `Cargo.toml`, `Cargo.lock`                      | Package metadata, dependencies, lint policy, and lockfile.                                     |
| `rust-toolchain.toml`                           | Pinned nightly and required components.                                                        |
| `Makefile`                                      | Public build, test, lint, coverage, and documentation entrypoints.                             |
| `AGENTS.md`                                     | Contributor and agent instructions.                                                            |
| `clippy.toml`, `.rustfmt.toml`                  | Rust lint and formatting configuration.                                                        |
| `.markdownlint-cli2.jsonc`                      | Markdown lint policy.                                                                          |
| `typos.local.toml`, `typos.toml`                | Local spelling overlay and generated dictionary configuration.                                 |
| `codecov.yml`                                   | Coverage service configuration.                                                                |
| `README.md`, `LICENSE`                          | Project introduction and ISC licence.                                                          |

## Ownership boundaries

Keep the facade crate root under `src/`, and keep kernel and macro
implementation under `crates/`. Keep integration tests under `tests/`; support
modules serve their named suite and must not become a generic validation
framework. Toolchain scripts belong to the root build workflow. The kernel owns
`TargetFacts`; the macro crate must not construct it, and the facade exposes
only derived values through `BuildProfile`. The
[developer guide](developers-guide.md#workspace-layout-and-module-ownership)
states the re-use policy for each module in the table above.

`docs/roadmap.md` is canonical: edit it directly (preferably with `mapsplice`
for structural changes), then run `scripts/export_roadmap.py` to refresh its
derived JSON view, `spec/roadmap.json`. The remaining design generators consume
`spec/` and own the generated reference and bets in `docs/`; change the source
specification before regenerating those documents. Validation reports describe
documentation models and must not assert proof discharge or runtime capability
eligibility.

Keep durable requirements and decisions under `docs/`, and update
[contents](contents.md) when adding, removing, or renaming documents. Prefer
Make targets for contributor entrypoints. Keep workflow automation under
`.github/workflows/`. Exclude build outputs, local environments, and editor
state from commits.
