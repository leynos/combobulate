# Assistant instructions

## Code style and structure

- **Code is for humans.** Write code with clarity and empathy—assume a
  tired teammate will need to debug it at 3 a.m.
- **Comment *why*, not *what*.** Explain assumptions, edge cases, trade-offs, or
  complexity. Don't echo the obvious.
- **Clarity over cleverness.** Be concise, but favour explicit over terse or
  obscure idioms. Prefer code that's easy to follow.
- **Use functions and composition.** Avoid repetition by extracting reusable
  logic. Prefer generators or comprehensions, and declarative code to
  imperative repetition when readable.
- **Small, meaningful functions.** Functions must be small, clear in purpose,
  single responsibility, and obey command/query segregation.
- **Clear commit messages.** Commit messages should be descriptive, explaining
  what was changed and why.
- **Name things precisely.** Use clear, descriptive variable and function names.
  For booleans, prefer names with `is`, `has`, or `should`.
- **Structure logically.** Each file should encapsulate a coherent module. Group
  related code (e.g., models + utilities + fixtures) close together.
- **Group by feature, not layer.** Colocate views, logic, fixtures, and helpers
  related to a domain concept rather than splitting by type.
- **Use consistent spelling and grammar.** Comments must use en-GB-oxendict
  ("-ize" / "-yse" / "-our") spelling and grammar, with the exception of
  references to external APIs. See [Spelling](#spelling).
- **Illustrate with clear examples.** Function documentation must include clear
  examples demonstrating the usage and outcome of the function. Test
  documentation should omit examples where the example serves only to reiterate
  the test logic.
- **Keep file size manageable.** No single code file may be longer than 400
  lines.  Long switch statements or dispatch tables should be broken up by
  feature and constituents colocated with targets. Large blocks of test data
  should be moved to external data files.

## Documentation maintenance

- **Reference:** Use the markdown files within the `docs/` directory as a
  knowledge base and source of truth for project requirements, dependency
  choices, and architectural decisions. Start with
  [documentation contents](docs/contents.md) and
  [repository layout](docs/repository-layout.md) when orienting within the
  project.
- **Update:** When new decisions are made, requirements change, libraries are
  added/removed, or architectural patterns evolve, **proactively update** the
  relevant file(s) in the `docs/` directory to reflect the latest state. Ensure
  the documentation remains accurate and current.
- **Design decisions:** Record design decisions in the relevant design
  document. When a decision is substantive, capture it in an Architectural
  Decision Record (ADR) following the documentation style guide, and reference
  that ADR from the design document.
- **User-facing behaviour:** Update [users' guide](docs/users-guide.md) for
  behaviour or user-interface changes that users should know about. Add
  migration guidance for compatibility or usage changes, and keep maintained
  translations synchronized.
- **Internal interfaces:** Document internally facing interfaces in the
  relevant component architecture document. Document internally facing
  conventions and practices in [developers' guide](docs/developers-guide.md).
- **Build tooling:** When changing build tooling, document the effective
  toolchain, inherited flags, backend and linker selection, and deliberate
  differences between validation commands.
- **Style:** All documentation must adhere to the
  [documentation style guide](docs/documentation-style-guide.md).
- **Accuracy:** Verify changed examples, commands, imports, links, paths, and
  stated guarantees against the implementation. Update maintained copies and
  indexes when names or locations change. Keep transient validation results in
  the PR or execution record.
- **Decision history:** Preserve accepted ADR decisions; record subsequent
  changes through the
  [ADR amendment and supersession process](docs/documentation-style-guide.md#architectural-decision-records-adrs).
  Capture proof-driven API, representation, and invariant decisions in the
  design documentation.
- **Completed execplans:** Completed execplans are historical documents and
  should reflect the state of the repository at time of implementation. Do not
  retroactively update completed execplan documents to reflect subsequent
  changes in API, structures, or behaviour.

## Planning and verification

- For non-trivial work, prepare or update a self-contained ExecPlan using the
  available planning guidance. Identify the outcome, relevant roadmap and
  design references, prerequisites, scope exclusions, and observable acceptance
  criteria. Signpost relevant documentation and skills.
- Identify affected behavioural contracts, invariants, and failure modes before
  choosing the implementation. Use these to pressure-test the proposed API and
  verification strategy.
- Plan the smallest useful increment. Preserve decision gates and stopping
  conditions; defer abstractions, dependencies, macros, or published components
  until the preceding evidence justifies them.
- Where formal verification is selected, first sketch the independent model,
  premises, invariants, representation relationships, and principal proof
  obligations. Treat proposed lemmas as provisional. Defer detailed proof
  engineering until implementation exposes the verification conditions; do not
  add assumptions, admissions, or trusted proof bodies merely to make
  incomplete proofs pass. Unproved statements may remain in the plan until that
  milestone.
- Give each major milestone explicit acceptance commands, including applicable
  proof checks and the formatting, linting, and test gates. Keep commits
  coherent and useful as rollback points.
- When plan approval is required, deliver the plan for review and wait for
  approval before implementation. Keep the active plan current, and mark
  relevant roadmap entries complete only after their acceptance criteria pass.

## Rebases and active plans

- Treat the fetched target branch as authoritative after a rebase. Reconcile
  active plans, measurements, and implementation with accepted target changes;
  do not stop merely because the target has evolved. Preserve the purpose of
  both branches, update affected records, and validate the resulting candidate.
- When a target change affects a pre-registered control, record the actual
  environment and follow its amendment process before measuring. Continue work
  that does not depend on the amended measurement.

## Change quality & committing

- **Atomicity:** Aim for small, focused, atomic changes. Each change (and
  subsequent commit) should represent a single logical unit of work.
- **Quality Gates:** Before considering a change complete or proposing a commit,
  ensure it meets the following criteria:
  - New functionality or changes in behaviour are fully validated by relevant
    unit tests and behavioural tests.
  - Where a bug is being fixed, a unittest has been provided demonstrating the
    behaviour being corrected both to validate the fix and to guard against
    regression.
  - Passes all relevant unit and behavioural tests according to the guidelines
    above.
  - Passes lint checks
  - Adheres to formatting standards tested using a formatting validator.
- **Before review:** Inspect the complete diff, including tests, fixtures,
  scripts, examples, and documentation. Check file-size limits, module
  documentation, doc-comment placement, assertion diagnostics, duplicated test
  setup, and applicable spelling and formatting gates. Link relevant roadmap
  entries, issues, and the ExecPlan in the PR description.
- **Committing:**
  - Only changes that meet all the quality gates above should be committed.
  - Write clear, descriptive commit messages summarizing the change, following
    these formatting guidelines:
    - **Imperative Mood:** Use the imperative mood in the subject line (e.g.,
      "Fix bug", "Add feature" instead of "Fixed bug", "Added feature").
    - **Subject Line:** The first line should be a concise summary of the change
      (ideally 50 characters or fewer).
    - **Body:** Separate the subject from the body with a blank line. Subsequent
      lines should explain the *what* and *why* of the change in more detail,
      including rationale, goals, and scope. Wrap the body at 72 characters.
    - **Formatting:** Use Markdown for any formatted text (like bullet points or
      code snippets) within the commit message body.
  - Do not commit changes that fail any of the quality gates.

## Refactoring heuristics & workflow

- **Recognizing Refactoring Needs:** Regularly assess the codebase for potential
  refactoring opportunities. Perform refactoring when observing:
  - **Long Methods/Functions:** Functions or methods that are excessively long
    or try to do too many things.
  - **Duplicated Code:** Identical or very similar code blocks appearing in
    multiple places.
  - **Complex Conditionals:** Deeply nested or overly complex `if`/`else` or
    `switch` statements (high cyclomatic complexity).
  - **Large Code Blocks for Single Values:** Significant chunks of logic
    dedicated solely to calculating or deriving a single value.
  - **Primitive Obsession / Data Clumps:** Groups of simple variables (strings,
    numbers, booleans) that are frequently passed around together, often
    indicating a missing class or object structure.
  - **Excessive Parameters:** Functions or methods requiring a very long list of
    parameters.
  - **Feature Envy:** Methods that seem more interested in the data of another
    class/object than their own.
  - **Shotgun Surgery:** A single change requiring small modifications in many
    different classes or functions.
- **Abstraction / port / helper policy:** Before implementing an abstraction,
  port, or extracted helper, the agent must:
  1. Sweep the repository and approved dependencies for equivalent behaviour.
     Reuse it unless demonstrably unsuitable. New abstractions must simplify
     the current change or have a concrete reuse case.
  2. Document the new abstraction's intended scope and re-use policy
     (ownership boundaries, permitted call-sites, and composition rules).
  3. Record the decision in the appropriate architecture, design, or
     developers-guide document using `docs/contents.md` as the index to select
     the correct location.
- **Post-Commit Review:** After committing a functional change or bug fix (that
  meets all quality gates), review the changed code and surrounding areas using
  the heuristics above.
- **Separate Atomic Refactors:** If refactoring is deemed necessary:
  - Perform the refactoring as a **separate, atomic commit** *after* the
    functional change commit.
  - Ensure refactoring adheres to the testing guidelines (behavioural tests
    pass before and after, unit tests added for new units).
  - Ensure the refactoring commit itself passes all quality gates.

## Architecture and operational boundaries

- Keep domain policy separate from filesystem, process, network, framework,
  and telemetry adapters. Inject dependencies where needed through existing
  interfaces or narrow closures; avoid speculative layers and dependency cycles.
- Make fallibility, mutation, and side-effects explicit in APIs. Preserve I/O,
  parsing, and permission errors rather than silently converting them into
  absence, `false`, or empty success. Compose side-effects at orchestration
  boundaries; queries must not hide writes or unrelated workflow policy.
- For streams, subprocesses, retries, caches, queues, and background tasks,
  define applicable size limits, deadlines, ownership, cancellation, and
  cleanup. A timeout does not bound accumulated bytes. Include waiting and
  cleanup in the operation's budget. Define partial-failure and retry behaviour
  where updates span multiple effects; keep locks narrow and ordered, avoiding
  holds across awaits or external calls unless explicitly justified.
- Validate untrusted inputs before privileged effects, use structured APIs
  instead of executable string construction, and grant only required
  permissions.
- When performance materially motivates a change, measure realistic inputs and
  distinguish build, execution, queueing, and cache state. Avoid repeated I/O
  or unnecessary allocation in per-item loops and blocking work on async
  executors.

## Rust specific guidance

This repository is written in Rust and uses Cargo for building and dependency
management. Contributors should follow these best practices when working on the
project:

- `rust-toolchain.toml` pins the nightly, Cranelift, rust-analyzer, rustfmt,
  Clippy, and LLVM tools. Run `make install-build-tools` to install that
  toolchain and the checksum-verified `mold` 2.41.0 release. Run
  `make check-build-tools` to inspect development prerequisites;
  `make coverage` additionally checks clang and lld.
- Bare Cargo development builds use Cranelift and the parallel frontend from
  `.cargo/config.toml`; native x86_64 GNU Linux builds use the repository's
  Clang wrapper to select pinned `mold` ahead of the system linker. Make
  targets that assign `RUSTFLAGS` restate the development flags because Cargo
  does not merge them with its configuration. Use `make release` and
  `make package` for production artefacts; both set their own flags and select
  LLVM for the dev and release profiles because package verification uses the
  dev profile. Measured coverage also selects LLVM. These routes exclude the
  parallel frontend, Cranelift, and `mold`. Coverage uses lld. Development Make
  gates reject a non-Cranelift `CARGO_PROFILE_DEV_CODEGEN_BACKEND` override.
  Cross-target Make builds, x86_64 Linux musl, and encoded Rust flags are
  unsupported for the `mold` route; native linker overrides must select the
  repository's Clang wrapper.
- Run `make check-fmt`, `make lint`, and `make test` before committing. These
  targets wrap the following commands, so contributors understand the exact
  behaviour and policy enforced:
  - `make check-fmt` executes:

    ```sh
    cargo fmt --all -- --check
    cargo fmt --manifest-path tools/gates/cardinality-ui/Cargo.toml --all -- --check
    mdtablefix --check --git --include-untracked \
      --wrap --renumber --breaks --ellipsis --fences
    ```

    validating Rust formatting across the root workspace and the separate
    cardinality compile-fail gate workspace, and Markdown formatting across
    files Git tracks plus untracked files Git does not ignore, without
    modifying files. The Markdown check needs mdtablefix 0.6.1 or later on
    `PATH`; install it with
    `cargo binstall --no-confirm mdtablefix@0.6.1` (or
    `cargo install --locked mdtablefix@0.6.1`), the version CI pins. `make fmt`
    applies the same formatting: `cargo fmt --all`, the gate workspace's
    `cargo fmt`, `mdtablefix --in-place` with the same selection and rules, and
    then `markdownlint-cli2 --fix "**/*.md"`.
  - `make lint` first runs `prepare-dependencies`, which executes
    `cargo fetch --locked` for the root workspace and for the cardinality gate
    manifest, and then `prepare-ui-gate`, which builds that gate's test binary.
    It then runs `lint-clippy`, `lint-whitaker`, and `lint-python` through
    recursive Make calls in that order, so `make -j lint` cannot overlap their
    Cargo work. Their effective commands are:

    ```makefile
    # lint-clippy: rustdoc once, then Clippy once per selected gate profile
    RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" \
      RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" $(CARGO) doc --no-deps
    RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" \
      $(CARGO) clippy $(CARGO_FLAGS) $(PROFILE_FLAGS) -- $(RUST_FLAGS)
    # lint-whitaker: clean driver inputs, preflight, then once per profile
    $(WHITAKER_CLEAN_ENV) $(CHECK_BUILD_TOOLS)
    $(WHITAKER_CLEAN_ENV) PATH="$(USER_BIN_PATH):$(PATH)" \
      DYLINT_RUSTFLAGS="$(RUST_FLAGS) $(POLONIUS_FLAGS)" \
      $(WHITAKER) --lib whitaker_suite --fail-on-no-libraries -- $(CARGO_FLAGS) $(PROFILE_FLAGS)
    # lint-python: every tracked or untracked Python source
    $(UV) tool run --python 3.14 --from interrogate==1.7.0 \
      interrogate --fail-under 100 $(PYTHON_TARGETS)
    ```

    `GATE_PROFILE` selects `native-only`, `polars-enabled`, `macros-only`,
    `polars-only`, or `both` (the default, which runs `native-only` and
    `polars-enabled`). A profile is its own Cargo invocation, because
    sharing one lets feature unification mask a profile. `WHITAKER_CLEAN_ENV`
    unsets the inherited `RUSTFLAGS`, `CARGO_ENCODED_RUSTFLAGS`,
    `CARGO_PROFILE_DEV_CODEGEN_BACKEND`, `CARGO_BUILD_TARGET`, the x86_64 GNU
    linker and rustflags variables, `CFLAGS`, and `LDFLAGS` before Whitaker
    runs. Whitaker is named by its `whitaker_suite` library rather than
    `--all`, because loading both a standalone lint crate and the suite that
    bundles it aborts rustc with a duplicate-lint error. `POLONIUS_FLAGS`
    defaults to empty, and this repository does not enable Polonius.
    Documentation warnings, Clippy warnings, and Whitaker findings fail the
    command. `make all` runs formatting, linting, testing, and spelling in
    order even under `make -j all`.
  - `make test` first runs `prepare-ui-gate`, which checks the build
    prerequisites and builds the cardinality gate's test binary. It then runs,
    for each selected profile, the workspace tests with `cargo-nextest` when
    available and `cargo test` otherwise, followed by the workspace doctests
    with Rustdoc warnings denied:

    ```makefile
    TEST_CMD := $(if $(shell $(CARGO) nextest --version 2>/dev/null),nextest run,test)
    # One run per profile in $(GATE_PROFILES), with that profile's flags.
    RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" \
      $(CARGO) $(TEST_CMD) $(TEST_FLAGS) $(PROFILE_FLAGS) $(BUILD_JOBS)
    RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" \
      RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" $(CARGO) test --doc --workspace $(PROFILE_FLAGS)
    if [ "$(WITH_ACT)" = "1" ]; then $(MAKE) act-validation; fi
    ```

    Both Cargo commands retain caller `RUSTFLAGS` alongside the development
    flags; doctests also deny Rustdoc warnings. `make test-profiles` runs the
    `build_profiles` integration test under the `macros-only` and
    `polars-only` profiles, which `make test` does not select by default.

  The hosted `build-test` job is the authoritative repository gate. Every PR
  runs workflow-structure and command-contract tests through `make test`.
  `.github/workflows/act-validation.yml` is manual-dispatch only; its full Act
  run checks local runner compatibility and does not prove parity with hosted
  GitHub Actions. `make test WITH_ACT=1` remains available for that local
  integration check. Keep the cold Whitaker driver integration check: the
  contract stubs verify command wiring, while the hosted lint route constructs
  the real driver and checks the repository. `make act-contract-smoke` runs the
  focused Act test against a derived CI workflow with fixture actions and
  controlled executors. Use `make whitaker-driver-integration` to run real
  `make lint-whitaker` checks with a private cold driver cache and then the
  same warm cache; hosted CI also forces a cold driver directory for each lint
  job.
- Clippy warnings MUST be disallowed.
- Fix any warnings emitted during tests in the code itself rather than
  silencing them.
- Every `assert!`, `assert_eq!`, and `assert_ne!` invocation must include a
  custom diagnostic message that states the failed expectation and, where
  useful, the relevant values.
- Where a function is too long, extract meaningfully named helper functions
  adhering to separation of concerns and CQRS.
- Where a function has too many parameters, group related parameters in
  meaningfully named structs.
- Keep returned error types semantically focused and small. If a necessary
  payload makes an error variant large, place that payload behind `Box`; use
  `Arc` only when shared ownership or cheap cloning is required.
- Ensure that new features are validated with unit tests using `rstest` and
  behavioural tests using `rstest-bdd` where applicable. Cover happy paths,
  unhappy paths, and relevant edge cases.
- Add snapshot tests using `insta` where structured output, user-interface
  output, diagnostics, or other multivariant output formats need meaningful,
  stable assertions. Keep snapshots focused on stable output boundaries, pair
  them with semantic assertions for business rules and schema contracts, and
  normalize nondeterministic fields before snapshotting. Do not accept brittle
  snapshots that churn after unrelated changes; update snapshots only after
  confirming a snapshot failure identifies a real contract change.
- Add compile-time behaviour tests using `trybuild` where macro expansion,
  trait bounds, feature-gated APIs, or other compile-fail and compile-pass
  contracts are relevant to the requirements. Keep compile-time fixtures free
  of unrelated runtime work.
- Add end-to-end tests where a change affects externally observable workflows,
  integration contracts, persistence, command-line behaviour, network
  boundaries, UI flows, or other system-level behaviour.
- Select verification proportionately: named examples or `rstest` tables for
  finite contracts, `proptest` for broad input spaces or operation sequences,
  and `kani` for exhaustive exploration within explicit bounds. Use `verus` for
  selected lemmas or contractual invariants requiring unbounded proof over a
  suitable semantic model. Proofs must establish the property from appropriate
  premises, not restate or assume it. Straightforward integration and
  presentation work must not acquire artificial proof obligations. Keep
  executable integration and behavioural tests alongside proofs.
- Run relevant unit, behavioural, property, model-checking, proof, and
  end-to-end suites before and after making any change.
- Every module **must** begin with a module level (`//!`) comment explaining the
  module's purpose and utility, including test modules and fixture crate roots.
- Document public APIs using Rustdoc comments (`///`) so documentation can be
  generated with cargo doc.
- Prefer immutable data and avoid unnecessary `mut` bindings.
- Clone to express intentional ownership, sharing, or snapshot semantics;
  prefer borrowing or ownership transfer when a new owned value is unnecessary.
- Use explicit version ranges in `Cargo.toml` and keep dependencies up-to-date.
- Avoid `unsafe` code unless absolutely necessary, and document any usage
  clearly with a "SAFETY" comment.
- Place function attributes **after** doc comments.
- Do not use `return` in single-line functions.
- Use predicate functions for conditional criteria with more than two branches.
- Lints must not be silenced except as a **last resort**.
- Use item-scoped `#[expect(lint, reason = "...")]`; blanket allowances and
  artificial references that hide unused code are forbidden. Narrow feature and
  test-support compilation boundaries instead. Delete unused helpers unless
  concrete tracked work justifies a temporary expectation linked to that work.
- Use `concat!()` to combine long string literals rather than escaping newlines
  with a backslash.
- Prefer single line versions of functions where appropriate. i.e.,

  ```rust
  pub fn new(id: u64) -> Self { Self(id) }
  ```

  Instead of:

  ```rust
  pub fn new(id: u64) -> Self {
      Self(id)
  }
  ```

- Use NewTypes to model domain values and eliminate "integer soup". Reach for
  `newt-hype` when introducing many homogeneous wrappers that share behaviour;
  add small shims such as `From<&str>` and `AsRef<str>` for string-backed
  wrappers. For path-centric wrappers implement `AsRef<Path>` alongside
  `into_inner()` and `to_path_buf()`. Prefer explicit tuple structs whenever
  bespoke validation or tailored trait surfaces are required, customizing
  `Deref`, `AsRef`, and `TryFrom` per type. Use `the-newtype` when defining
  traits and needing blanket implementations that apply across wrappers
  satisfying `Newtype + AsRef/AsMut<Inner>`, or when establishing a coherent
  internal convention that keeps trait forwarding consistent without per-type
  boilerplate. Combine approaches: lean on `newt-hype` for the common case,
  tuple structs for outliers, and `the-newtype` to unify behaviour when owning
  the trait definitions.
- Use `cap_std` and `cap_std::fs_utf8` / `camino` in place of `std::fs` and
  `std::path` for enhanced cross-platform support and capabilities oriented
  filesystem access.

### Testing

- For each changed behaviour, identify a plausible incorrect implementation
  and ensure the test rejects it. Assert observable results, errors, and
  side-effects; mock calls or configuration text alone do not prove execution.
  Negative tests must establish the precondition that would expose the defect.
- Exercise the boundary that owns the promise: public API, executable, or
  protocol adapter. Private-helper tests complement this coverage. Fakes must
  support relevant failures and verify their propagation through orchestration.
  Test local integration contracts rather than third-party tools themselves.
- Test relevant partial failures, cancellation, shutdown, and cleanup with
  deterministic coordination where practical. Avoid relying solely on sleeps or
  exact deltas from shared global counters. Restore fixture resources even when
  assertions fail, and account for host capabilities and privileges.
- Use `rstest` fixtures for shared setup.
- Replace duplicated tests with `#[rstest(...)]` parameterized cases.
- Prefer `mockall` for ad hoc mocks/stubs.
- **Inject the environment instead.** Any behaviour depending upon environment
  variables must accept an injected environment: `mockable::Env`, with
  `mockable::DefaultEnv` supplied at the production composition root and
  `mockable::MockEnv` in tests. A narrow closure seam of the same shape is
  acceptable where a trait object would be disproportionate. Production code
  must not reach for `std::env::var`/`var_os` outside that composition root.
  This repository enforces the `std::env` part of this rule through the
  `disallowed-methods` list in `clippy.toml`, which also covers `set_var` and
  `remove_var` in tests.
- **Process-wide locks are not an escape hatch.** Serializing environment
  mutation behind a shared `Mutex`, `OnceLock`, or `serial_test` attribute is
  not an accepted fallback. It serializes the suite, defeats property-based
  tests that run many cases within one process, and leaves the ambient
  dependency embedded in the production signature. Where injection looks
  impossible the signature is wrong; correct the signature.
- **Subprocess isolation is the sole exemption.** End-to-end behavioural tests
  invoking the generated application binary through `assert_cmd` may configure
  the environment via `Command::env`/`Command::env_clear`, because the mutation
  is confined to the child process. A test manipulating the environment
  in-process does not qualify, whatever layer it claims to occupy.

### Dependency management

- **Mandate caret requirements for all dependencies.** All crate versions
  specified in `Cargo.toml` must use SemVer-compatible caret requirements (e.g.,
  `some-crate = "1.2.3"`, equivalent to `^1.2.3`). This is Cargo's default and
  allows for safe, non-breaking updates to minor and patch versions while
  preventing breaking changes from new major versions. This approach is
  critical for ensuring build stability and reproducibility.
- **Prohibit unstable version specifiers.** The use of wildcard (`*`) or
  open-ended inequality (`>=`) version requirements is strictly forbidden, as
  they introduce unacceptable risk and unpredictability. Tilde requirements (
  `~`) should only be used where a dependency must be locked to patch-level
  updates for a specific, documented reason.

### Error handling

- **Prefer semantic error enums**. Derive `std::error::Error` (via the
  `thiserror` crate) for any condition the caller might inspect, retry, or map
  to an HTTP status.
- **Use an *opaque* error only at the app boundary**. Use `eyre::Report` for
  human-readable logs; these should not be exposed in public APIs.
- **Never export the opaque type from a library**. Convert to domain enums at
  API boundaries, and to `eyre` only in the main `main()` entrypoint or
  top-level async task.
- In tests, prefer `.expect(...)` over `.unwrap()` to surface clearer failure
  diagnostics.
- In production code and shared fixtures, avoid `.expect()` entirely: return
  `Result` and use `?` to propagate errors instead of panicking.
- Keep `expect_used` **strict**; do not suppress the lint.
- Recognize that `allow-expect-in-tests = true` **doesn’t cover** helpers
  outside `#[cfg(test)]` or `#[test]`; avoid `expect` in such fixtures.
- Use `anyhow`/`eyre` with `.context(...)` to **preserve backtraces** and
  provide clear, typed failure paths.
- Update helpers (e.g., `set_dir`) to **return errors** rather than panicking.
- Consume fallible fixtures in `rstest` by **making the test return `Result`**
  and applying `?` to the fixture.

### Observability

- Use `tracing` for logging and diagnostics. Prefer structured
  `tracing::{trace, debug, info, warn, error}` events and spans over `println!`,
  `eprintln!`, or direct `log` macros. Add fields for identifiers, state, and
  error context so downstream subscribers can filter and correlate events
  without parsing message text.
- Use `#[tracing::instrument]` or explicit spans around request handling,
  command execution, retries, background jobs, and other meaningful units of
  work. Do not hold `Span::enter()` guards across `.await`; use
  `Instrument::instrument` or scoped synchronous spans instead.
- Use the `metrics` crate for metric emission where usage, uptake, failure,
  or mitigation metrics are required. Prefer `counter!` for cumulative events,
  `gauge!` for values that rise and fall, and `histogram!` for distributions
  such as latency or payload size.
- Describe emitted metrics with `describe_counter!`, `describe_gauge!`, or
  `describe_histogram!` where the unit or purpose is not obvious from the
  metric name. Keep metric names stable and labels low-cardinality; do not put
  user input, request IDs, paths with unbounded parameters, or raw error
  strings into labels.
- Libraries may emit `metrics` and `tracing` instrumentation, but must not
  install global recorders or subscribers. Applications should initialize
  exporters/subscribers once, as early as practical in startup.
- Keep secrets, credentials, raw payloads, and sensitive paths out of logs,
  errors, traces, and snapshots. Prefer stable error categories and bounded
  contextual fields over arbitrary error text.
- For new operational telemetry, document and exercise the application's
  collection path. Verify a relevant event produces a non-zero signal through
  that path; helper-only assertions or comparisons of zero counters do not
  establish useful instrumentation.

## Markdown guidance

- Validate Markdown files using `make markdownlint`. This target also runs the
  en-GB-oxendict spelling gate.
- Run `make fmt` after any documentation changes to format all Markdown
  files and fix table markup.
- Validate Mermaid diagrams in Markdown files by running `make nixie`.
- Markdown paragraphs and bullet points must be wrapped at 80 columns.
- Code blocks must be wrapped at 120 columns.
- Tables and headings must not be wrapped.
- Use dashes (`-`) for list bullets.
- Use GitHub-flavoured Markdown footnotes (`[^1]`) for references and
  footnotes.
- Avoid first-person prose outside README and BDD feature files; allow
  second-person prose in README, AGENTS, BDD feature files, and agent skill
  directories. These exceptions qualify the documentation style guide.
- Quoted API names and identifiers retain upstream spelling. Mark them as
  code using backticks or fenced blocks rather than adding spelling exceptions.

<!-- typos-config-builder:agents-md:start -->

## Spelling

- `make spelling` runs the pinned `typos-config-builder gate`, which
  regenerates `typos.toml` from the shared en-GB-oxendict dictionary and
  `typos.local.toml`, then checks spelling and the shared phrase corrections.
- `typos.toml` is generated: never edit it by hand. Put narrow
  repository-specific exceptions in `typos.local.toml`, as exact or full-line
  patterns rather than bare accepted words.
- When `make spelling` changes `typos.toml`, commit the regenerated file. If
  the change is unrelated to your work, commit it in a separate base pull
  request and stack your branch on it, so each review diff stays focused.

<!-- typos-config-builder:agents-md:end -->

## Project documentation

Record design decisions in the design document. Where a decision is
substantive, record it in an ADR document following the documentation style
guide, then reference that ADR from the design document.

Update `docs/users-guide.md` for any change to application behaviour or user
interface that a user should know about. Document internally facing interfaces
or practices in the relevant component architecture document. Document
internally facing conventions or practices in `docs/developers-guide.md`.
