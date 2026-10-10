# Repository layout

Combobulate uses the Rust development structure adapted from Peregrine Web pull
request 11. The current crate is a scaffold; the multi-crate architecture in the
[technical design](technical-design.md) remains a delivery proposal.

## Paths and responsibilities

| Path                                     | Responsibility                                                                             |
| ---------------------------------------- | ------------------------------------------------------------------------------------------ |
| `src/lib.rs`                             | Current crate root and disposable greeting stub.                                           |
| `tests/`                                 | Integration tests for build routes, workflow policy, Make commands, and shell preflights.  |
| `tests/support/`                         | Private helpers owned by the corresponding integration test modules.                       |
| `scripts/`                               | Toolchain installation, build preflights, native Clang linker wrapper, and helper scripts. |
| `scripts/tests/`                         | Pytest suites for helper scripts, named after the script they cover.                       |
| `.cargo/config.toml`                     | Development compiler/backend/linker defaults.                                              |
| `.github/workflows/ci.yml`               | Authoritative hosted Rust and build-contract gate.                                         |
| `.github/workflows/design.yml`           | Design-fixture and documentation-generator validation.                                     |
| `.github/workflows/coverage-main.yml`    | Main-branch coverage publication and ratchet baseline.                                     |
| `.github/workflows/act-validation.yml`   | Manually dispatched full Act compatibility check.                                          |
| `.github/workflows/audit.yml`            | Scheduled dependency audit.                                                                |
| `.github/workflows/mutation-testing.yml` | Scheduled shared Rust mutation workflow.                                                   |
| `.github/dependabot.yml`                 | Cargo and GitHub Actions dependency updates.                                               |
| `docs/`                                  | Design, guides, reference material, and recorded decisions.                                |
| `docs/contents.md`                       | Canonical documentation index.                                                             |
| `spec/`                                  | Machine-readable language, roadmap, proof, cost, and backend contracts.                    |
| `tools/`                                 | Design generators and documentation-model validation.                                      |
| `tools/mold/`                            | Pinned native linker version and archive digest.                                           |
| `Cargo.toml`, `Cargo.lock`               | Package metadata, dependencies, lint policy, and lockfile.                                 |
| `rust-toolchain.toml`                    | Pinned nightly and required components.                                                    |
| `Makefile`                               | Public build, test, lint, coverage, and documentation entrypoints.                         |
| `AGENTS.md`                              | Contributor and agent instructions.                                                        |
| `clippy.toml`, `.rustfmt.toml`           | Rust lint and formatting configuration.                                                    |
| `.markdownlint-cli2.jsonc`               | Markdown lint policy.                                                                      |
| `typos.local.toml`, `typos.toml`         | Local spelling overlay and generated dictionary configuration.                             |
| `codecov.yml`                            | Coverage service configuration.                                                            |
| `README.md`, `LICENSE`                   | Project introduction and ISC licence.                                                      |

## Ownership boundaries

Keep library implementation under `src/` until the roadmap establishes the
planned crate boundaries. Keep integration tests under `tests/`; support
modules serve their named suite and must not become a generic validation
framework. Toolchain scripts belong to the root build workflow.

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
