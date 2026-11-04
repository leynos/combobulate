# `make fmt` and `make check-fmt` call mdtablefix directly. `--git` selects the
# Markdown files Git tracks and `--include-untracked` adds the untracked files
# Git does not ignore, so a new document is formatted before it is staged.
# Both modes need mdtablefix 0.6.1 or later; CI pins the version at its
# install-mdtablefix step.
MDTABLEFIX ?= mdtablefix
MDTABLEFIX_SELECT = --git --include-untracked
MDTABLEFIX_RULES = --wrap --renumber --breaks --ellipsis --fences

.PHONY: help all clean test test-ui prepare-dependencies prepare-ui-gate act-validation act-contract-smoke whitaker-driver-integration build release package coverage \
  lint lint-clippy lint-whitaker lint-python docstring-coverage check-python-sources fmt check-fmt markdownlint spelling nixie \
  audit rust-audit install-build-tools check-build-tools check-coverage-tools

SHELL := bash

# The prover targets are declared first so `make install-kani` and friends read
# beside their version pins. Without an explicit default goal Make would adopt
# `install-kani`, turning a bare `make` into a tool installation, so pin the
# ordinary build instead.
.DEFAULT_GOAL := build


override PROVER_TOOLS_REF_FILE := tools/rust-prover-tools/REF
override PROVER_TOOLS_REF := $(shell awk '/^ref:/ { print $$2 }' $(PROVER_TOOLS_REF_FILE))
ifeq ($(shell printf '%s' '$(PROVER_TOOLS_REF)' | grep -Ec '^[0-9a-f]{40}$$'),0)
$(error PROVER_TOOLS_REF missing or malformed; expected "ref: <40-hex>" in $(PROVER_TOOLS_REF_FILE))
endif
override PROVER_TOOLS_SOURCE := git+https://github.com/leynos/rust-prover-tools.git@$(PROVER_TOOLS_REF)
# Only the paired command-line seam may replace the pinned helper in tests.
PROVER_TOOLS_ORIGINS := $(origin PROVER_TOOLS_CONTRACT_TEST),$(origin PROVER_TOOLS),$(PROVER_TOOLS_CONTRACT_TEST)
ifeq ($(PROVER_TOOLS_ORIGINS),command line,command line,1)
else
override PROVER_TOOLS := uv tool run --from "$(PROVER_TOOLS_SOURCE)" prover-tools
endif
KANI ?= cargo kani
KANI_INSTALLATION ?= $(HOME)/.kani/kani-$(shell cat tools/kani/VERSION)
KANI_FLAGS ?=
KANI_PROBE_ROUTE ?= direct
VERUS_FLAGS ?=
FORMAL_STRICT ?= 0

.PHONY: install-kani kani-check install-verus kani kani-full kani-log-corpus verus-probe

install-kani: ## Install the pinned Kani release
	$(PROVER_TOOLS) kani install --repo-root .

kani-check: ## Require the calibrated Kani release
	$(PROVER_TOOLS) kani check-version --repo-root . --kani-command "$(KANI)"

install-verus: ## Install the checksum-verified Verus release
	$(PROVER_TOOLS) verus install --repo-root .

kani kani-full: kani-check ## Report that product proofs arrive in task 1.2.4
	@printf 'FORMAL-SKIP: %s has no product harnesses until task 1.2.4\n' '$@'
	@test "$(FORMAL_STRICT)" != 1

kani-log-corpus: kani-check ## Capture real Kani parser fixtures
	@uv run --script scripts/run_verifier_probes.py kani --prover-tools '$(PROVER_TOOLS)' --installation '$(KANI_INSTALLATION)' --route '$(KANI_PROBE_ROUTE)' $(KANI_FLAGS)

verus-probe: kani-check ## Compare the four pinned Verus wiring candidates
	@uv run --script scripts/run_verifier_probes.py verus --prover-tools '$(PROVER_TOOLS)' $(VERUS_FLAGS)

TARGET ?= libcombobulate.rlib

USER_WHITAKER := $(HOME)/.local/bin/whitaker
USER_BIN_PATH := $(HOME)/.cargo/bin:$(HOME)/.local/bin:$(HOME)/.bun/bin
CARGO ?= cargo
BUILD_JOBS ?=
BUILD_TOOLS_PREFIX ?= $(HOME)/.local
CHECK_BUILD_TOOLS ?= scripts/check-build-tools.sh
export BUILD_TOOLS_PREFIX
export PATH := $(BUILD_TOOLS_PREFIX)/bin:$(PATH)
POLONIUS_FLAGS ?=
RUST_FLAGS ?=
RUST_FLAGS := -D warnings $(RUST_FLAGS)
# The build standard: every `rustflags` source in `.cargo/config.toml` carries
# the parallel frontend, and the x86_64 GNU Linux source adds `mold`. Assigning `RUSTFLAGS`
# replaces those sources outright, so the gate targets restate the flags here.
# Development recipes add those flags to inherited RUSTFLAGS, including the CI
# setup-rust value. Coverage, release, and packaging take neither. The checked toolchain
# components come from rust-toolchain.toml. Native Cargo routes through the
# Clang wrapper, which puts pinned ld.mold first; coverage checks its lld linker.
DEV_THREADS_FLAGS ?= -Zthreads=8
BUILD_HOST_OS := $(shell uname -s)
# Only the native x86_64 GNU Linux route has a pinned mold linker.
BUILD_HOST_ARCH := $(shell uname -m)
BUILD_HOST_TRIPLE := $(shell rustup show 2>/dev/null | sed -n 's/^Default host: //p')
DEV_LINKER_FLAGS ?= $(if $(and $(filter Linux,$(BUILD_HOST_OS)),$(filter x86_64,$(BUILD_HOST_ARCH)),$(filter x86_64-unknown-linux-gnu,$(BUILD_HOST_TRIPLE))),-C link-arg=-fuse-ld=mold)
DEV_RUST_FLAGS ?= $(RUST_FLAGS) $(POLONIUS_FLAGS) $(DEV_THREADS_FLAGS) $(DEV_LINKER_FLAGS)
RELEASE_RUST_FLAGS ?= $(RUST_FLAGS) $(POLONIUS_FLAGS)
# The kernel and macro crates are unpublished (D05), so `cargo package` cannot
# resolve them from the registry on its own. Patch them to their workspace
# paths for this run: the packaged manifest still names versions, and
# verification still compiles the facade against the local members.
PACKAGE_FLAGS ?= -p combobulate \
	--config "patch.crates-io.combobulate-kernel.path='$(CURDIR)/crates/combobulate-kernel'" \
	--config "patch.crates-io.combobulate-macros.path='$(CURDIR)/crates/combobulate-macros'"
RUSTDOC_FLAGS ?=
RUSTDOC_FLAGS := --cfg docsrs -D warnings $(POLONIUS_FLAGS) $(RUSTDOC_FLAGS)
CARGO_FLAGS ?= --all-targets --all-features
CLIPPY_FLAGS ?= $(CARGO_FLAGS) -- $(RUST_FLAGS)
TEST_FLAGS ?= $(CARGO_FLAGS)
TEST_CMD := $(if $(shell $(CARGO) nextest --version 2>/dev/null),nextest run,test)
# The cardinality compile-fail gate is its own workspace: `tools/` is excluded
# from the root workspace, so it carries its own manifest, lockfile, and target
# directory. `make prepare-dependencies` fetches it, and `make test-ui` runs it
# directly; the root suite reaches it through `tests/cardinality_probe_ui.rs`.
UI_GATE_MANIFEST ?= tools/gates/cardinality-ui/Cargo.toml
UI_GATE_TEST ?= --test cardinality_ui
WITH_ACT ?= 0
ACT ?= act
ACT_RUNNER_IMAGE ?= catthehacker/ubuntu:act-latest
ACT_GIT_COMMON_DIR := $(shell git rev-parse --path-format=absolute --git-common-dir)
ACT_GITHUB_TOKEN ?= $(or $(GITHUB_TOKEN),$(GH_TOKEN))
COVERAGE_LINKER_FLAGS ?= -fuse-ld=lld
COVERAGE_RUST_FLAGS ?= $(RUST_FLAGS) $(POLONIUS_FLAGS) -C link-arg=$(COVERAGE_LINKER_FLAGS)
# RUSTFLAGS displaces configured flags, while the dev profile backend needs its
# own override so coverage runs LLVM instrumentation instead of Cranelift.
MDLINT ?= markdownlint-cli2
NIXIE ?= nixie
TYPOS_CONFIG_BUILDER = uv tool run --from \
	"git+https://github.com/leynos/typos-config-builder.git@v0.1.3" \
	typos-config-builder
WHITAKER ?= $(or $(shell command -v whitaker 2>/dev/null),$(wildcard $(USER_WHITAKER)),whitaker)

build: target/debug/$(TARGET) ## Build debug binary
release: ## Build the production release artefact with LLVM and the platform linker
	$(PRODUCTION_ENV) $(CARGO) build $(BUILD_JOBS) --release

package: ## Build and verify a publishable Cargo package with LLVM
	$(PRODUCTION_ENV) $(CARGO) package --locked $(PACKAGE_FLAGS)

all: ## Perform every commit gate sequentially, even with make -j
	+$(MAKE) check-fmt
	+$(MAKE) lint
	+$(MAKE) test
	+$(MAKE) spelling

clean: ## Remove build artefacts
	$(CARGO) clean
	rm -f .typos-oxendict-base.json .typos-oxendict-base.toml

BUILD_STANDARD_ENV = RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)"

test: prepare-ui-gate ## Run tests with warnings treated as errors
	$(BUILD_STANDARD_ENV) $(CARGO) $(TEST_CMD) $(TEST_FLAGS) $(BUILD_JOBS)
	$(BUILD_STANDARD_ENV) RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" $(CARGO) test --doc --workspace --all-features
	if [ "$(WITH_ACT)" = "1" ]; then $(MAKE) act-validation; fi

# Every Rust command a development route runs must compose the caller's
# RUSTFLAGS with the standard flags, and only an assignment does that: without
# one, Cargo falls back to `.cargo/config.toml` and silently drops the caller's
# flags. The acquisition step below compiles nothing, so its commands carry no
# assignment either way; the checks in `tests/build_standard_contract.rs` read
# `make -n` output and fail on a bare Cargo command in a development route, so
# any new command here needs the assignment too.
#
# Acquisition happens before any test body runs, and its failure names the
# manifest and the likely cause: a cold cache, an unreachable registry, or a
# lockfile that needs updating. `--locked` is deliberate, so a stale lockfile
# fails here rather than silently resolving new versions.
#
# A plain `cargo fetch` covers every target. `--target` takes a triple, not
# `all`, and Cargo resolves the entire lockfile graph for `fetch` regardless of
# the host, which is what the boundary checks' `cargo tree --target all` needs.
#
# `lint` runs this too, and that is not redundant. The hosted lane runs
# `make lint` before the coverage action and never runs `make test`, so this is
# the only place a hosted runner can populate the cache before the boundary
# tests execute inside the coverage action.
prepare-dependencies: check-build-tools ## Acquire locked dependencies before any test body runs
	@if ! $(BUILD_STANDARD_ENV) $(CARGO) fetch --locked; then \
		printf '\n%s\n\n' \
			"make prepare-dependencies could not acquire the workspace's dependencies." \
			"Run it directly to read the full error. The workspace boundary checks fetch" \
			"nothing themselves, so a cold or offline cache and a lockfile that needs" \
			"regenerating all fail there instead, as an unrelated-looking test failure." >&2; \
		exit 1; \
	fi
	@if ! $(BUILD_STANDARD_ENV) $(CARGO) fetch --locked --manifest-path '$(UI_GATE_MANIFEST)'; then \
		printf '\n%s\n\n' \
			"make prepare-dependencies could not acquire $(UI_GATE_MANIFEST)." \
			"Run it directly to read the full error. That package is its own workspace," \
			"so the workspace fetch above does not cover it." >&2; \
		exit 1; \
	fi

# The gate lives in its own workspace so its nested `trybuild` build inherits
# only the probe and `trybuild`. Running it from the root package would merge
# every root dependency and dev-dependency into that generated crate; this
# route keeps the diagnostic contract without making the nested build pay for
# the root package's graph.
#
# `prepare-ui-gate` chains onto `prepare-dependencies` rather than sitting
# beside it as a second prerequisite of `test`. Under `make -j` independent
# prerequisites run in parallel, and measurement showed the gate build then
# sometimes starting before the fetches that populate its own workspace: a
# build racing the acquisition it needs. The chain also makes the whole
# preparation phase linear, so the command contract has one order rather than
# two acceptable ones.
#
# `make test` builds the gate's test binary here, before any test body runs, so
# `tests/cardinality_probe_ui.rs` only has to locate and run it. Building inside
# that test body is what the incident did: a nested Cargo build, of a generated
# crate that inherited the root package's whole dev-dependency graph, under no
# deadline of its own. The
# build keeps `--no-run` so preparation cannot pass because the gate happened to
# pass on a previous run; the root test is the one that asserts the diagnostic.
prepare-ui-gate: prepare-dependencies ## Build the cardinality gate's test binary
	$(BUILD_STANDARD_ENV) $(CARGO) test --no-run --manifest-path '$(UI_GATE_MANIFEST)' $(UI_GATE_TEST)

# The direct route for a developer who wants only the gate. It builds and runs
# the workspace in one command, which is also how CI's cold path exercises it.
test-ui: prepare-dependencies ## Run the cardinality compile-fail gate outside the root workspace
	$(BUILD_STANDARD_ENV) $(CARGO) test --manifest-path '$(UI_GATE_MANIFEST)' $(UI_GATE_TEST)

act-validation: ## Run the CI workflow through Act after outer Cargo tests pass
	@GITHUB_TOKEN="$(ACT_GITHUB_TOKEN)" $(ACT) pull_request --bind \
		--container-options "--volume $(ACT_GIT_COMMON_DIR):$(ACT_GIT_COMMON_DIR):ro" \
		--secret GITHUB_TOKEN \
		--env ACT=true \
		--platform "ubuntu-24.04=$(ACT_RUNNER_IMAGE)" \
		--workflows .github/workflows/ci.yml --job build-test

act-contract-smoke: check-build-tools ## Check Act step routing with local action and command fixtures
	RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" $(CARGO) test --test act_workflow smoke::real_act_runs_derived_workflow_and_propagates_failure -- --ignored --exact

whitaker-driver-integration: ## Check cold then warm Dylint driver construction
	@set -euo pipefail; mkdir -p target; \
		cache_dir="$$(mktemp -d "$(CURDIR)/target/whitaker-driver.XXXXXX")"; \
		trap 'rm -rf "$$cache_dir"' EXIT; \
		DYLINT_DRIVER_PATH="$$cache_dir" $(MAKE) lint-whitaker; \
		DYLINT_DRIVER_PATH="$$cache_dir" $(MAKE) lint-whitaker

target/debug/$(TARGET): check-build-tools ## Build debug binary
	RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" $(CARGO) build $(BUILD_JOBS)

# Cargo packages the repository config and verifies with the dev profile. Both
# profiles therefore select LLVM; the native linker override bypasses the
# development wrapper even for release host/build-script units. An inherited
# encoded flags value would outrank RUSTFLAGS, so remove it explicitly.
PRODUCTION_ENV = env -u CARGO_ENCODED_RUSTFLAGS CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=clang CARGO_PROFILE_DEV_CODEGEN_BACKEND=llvm CARGO_PROFILE_RELEASE_CODEGEN_BACKEND=llvm RUSTFLAGS="$(RELEASE_RUST_FLAGS)"

# `prepare-ui-gate` is a prerequisite, not a trailing recipe line. `llvm-cov`
# runs the workspace suite, and the root `cardinality_probe_ui` test now finds a
# prebuilt gate binary rather than compiling one; without the prerequisite a
# clean tree would fail that test before the trailing `test-ui` ever ran. Making
# it a prerequisite also means the gate is no longer run twice, since the root
# test already executes it under the coverage run.
coverage: check-coverage-tools prepare-ui-gate ## Generate lcov coverage with lld for llvm-tools compatibility
	@echo "coverage linker flags: $(COVERAGE_LINKER_FLAGS)"
	CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=clang \
		CARGO_PROFILE_DEV_CODEGEN_BACKEND=llvm \
		RUSTFLAGS="$(COVERAGE_RUST_FLAGS)" \
		CFLAGS="$(COVERAGE_LINKER_FLAGS)" \
		LDFLAGS="$(COVERAGE_LINKER_FLAGS)" \
		$(CARGO) llvm-cov --lcov --output-path lcov.info $(TEST_FLAGS)

# `prepare-dependencies` is here, not only on `test`. The hosted lane runs
# `make lint` and then the coverage action, which runs `cargo llvm-cov nextest`
# itself; it never runs `make test`. Without this prerequisite a hosted runner
# reaches the workspace-boundary tests with whatever the action's own install
# steps happened to cache, and the offline `cargo tree` checks fail there with
# an unrelated-looking HTTP refusal.
lint: prepare-dependencies ## Run rustdoc, Clippy, Whitaker, and Python docstring coverage sequentially
	+$(MAKE) lint-clippy
	+$(MAKE) lint-whitaker
	+$(MAKE) lint-python

# Discover Python sources from Git so hidden workflow/action paths and new
# repository areas are included without maintaining a second source manifest.
PYTHON_TARGETS_FROM_GIT := $(if $(filter undefined,$(origin PYTHON_TARGETS)),1,0)
PYTHON_TARGETS ?=
INTERROGATE_VERSION ?= 1.7.0
UV ?= uv
ifeq ($(PYTHON_TARGETS_FROM_GIT),1)
check-python-sources:
	$(eval PYTHON_TARGETS := $(shell git ls-files --cached --others --exclude-standard '*.py' '*.pyi'))
	$(if $(filter 0,$(.SHELLSTATUS)),,$(error Error: git ls-files failed while discovering Python sources for PYTHON_TARGETS))
	$(if $(strip $(PYTHON_TARGETS)),,$(error Error: PYTHON_TARGETS is empty after source selection))
	@:
else
check-python-sources:
	$(if $(strip $(PYTHON_TARGETS)),,$(error Error: PYTHON_TARGETS is empty after source selection))
	@:
endif

lint-python: ## Require complete Interrogate coverage for all Python sources
	+$(MAKE) docstring-coverage

docstring-coverage: check-python-sources ## Check docstrings in tracked and untracked Python files
	$(UV) tool run --python 3.14 --from interrogate==$(INTERROGATE_VERSION) interrogate --fail-under 100 $(PYTHON_TARGETS)

lint-clippy: check-build-tools ## Run rustdoc and Clippy with warnings denied
	RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" $(CARGO) doc --no-deps
	RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" $(CARGO) clippy $(CLIPPY_FLAGS)

WHITAKER_CLEAN_ENV = env -u RUSTFLAGS -u CARGO_ENCODED_RUSTFLAGS \
	-u CARGO_PROFILE_DEV_CODEGEN_BACKEND -u CARGO_BUILD_TARGET \
	-u CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER \
	-u CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS -u CFLAGS -u LDFLAGS

lint-whitaker: ## Run Whitaker with clean driver inputs and repository Cargo defaults
	@$(WHITAKER_CLEAN_ENV) $(CHECK_BUILD_TOOLS)
	@echo "Whitaker binary: $(WHITAKER)"
	$(WHITAKER_CLEAN_ENV) PATH="$(USER_BIN_PATH):$(PATH)" DYLINT_RUSTFLAGS="$(RUST_FLAGS) $(POLONIUS_FLAGS)" $(WHITAKER) --all -- $(CARGO_FLAGS)

typecheck: check-build-tools ## Type-check without building
	RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(DEV_RUST_FLAGS)" $(CARGO) check $(CARGO_FLAGS)

install-build-tools: ## Install pinned `mold` and the repository toolchain
	@scripts/install-build-tools.sh

check-build-tools: ## Check pinned development build prerequisites
	@case " $(CARGO_FLAGS) $(TEST_FLAGS) $(BUILD_JOBS) " in *" --target "*|*" --target="*) \
		echo "build-tools: --target is outside the supported native Make build" >&2; exit 1;; \
	esac; $(CHECK_BUILD_TOOLS)

check-coverage-tools: ## Check coverage linker prerequisites
	@case " $(TEST_FLAGS) " in *" --target "*|*" --target="*) \
		echo "build-tools: --target is outside the supported native Make coverage" >&2; exit 1;; \
	esac; $(CHECK_BUILD_TOOLS) --coverage

fmt: ## Format Rust and Markdown sources
	$(CARGO) fmt --all
	$(MDTABLEFIX) --in-place $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)
	$(MDLINT) --fix "**/*.md"

check-fmt: ## Verify formatting
	$(CARGO) fmt --all -- --check
	$(MDTABLEFIX) --check $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)

markdownlint: ## Lint Markdown files
	$(MDLINT) '**/*.md'
	+$(MAKE) spelling
spelling: ## Enforce en-GB-oxendict spelling in Markdown prose
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		echo "make spelling needs a Git repository: the gate enumerates tracked files with git ls-files. Run: git init && git add -A" >&2; \
		exit 1; \
	fi
	@if [ -z "$$(git ls-files)" ]; then \
		echo "make spelling found no tracked files: the gate enumerates tracked files with git ls-files. Run: git add -A" >&2; \
		exit 1; \
	fi
# The managed session injects GitHub URL rewrites through an identity helper.
# The public pinned tool and local git ls-files input need no injected config.
	env -u GIT_CONFIG_COUNT $(TYPOS_CONFIG_BUILDER) gate

nixie: ## Validate Mermaid diagrams
	$(NIXIE) --no-sandbox

audit: rust-audit ## Audit dependencies for known vulnerabilities

rust-audit: ## Audit the Rust workspace for known vulnerabilities
	set -eo pipefail; \
	manifest_list=$$(mktemp); \
	trap 'rm -f "$$manifest_list"' EXIT; \
	printf "Audit metadata phase: deriving workspace manifests\n"; \
	$(CARGO) metadata --no-deps --format-version 1 | python3 -c 'import json, sys; metadata = json.load(sys.stdin); members = set(metadata["workspace_members"]); print(metadata["workspace_root"]); [print(package["manifest_path"]) for package in metadata["packages"] if package["id"] in members]' > "$$manifest_list"; \
	workspace_root=$$(sed -n '1p' "$$manifest_list"); \
	audit_flags=(); \
	for advisory in $$CARGO_AUDIT_IGNORES; do \
		audit_flags+=(--ignore "$$advisory"); \
	done; \
	printf "Auditing Rust workspace %s\n" "$$workspace_root"; \
	sed -n '2,$$p' "$$manifest_list" | while IFS= read -r manifest; do \
		manifest_dir=$$(dirname "$$manifest"); \
		printf "Workspace Rust manifest %s\n" "$$manifest_dir/Cargo.toml"; \
	done; \
	printf "Audit execution phase: running cargo audit\n"; \
	printf "Audit failures may indicate RustSec advisories, cargo metadata errors, or documented ignores that need CARGO_AUDIT_IGNORES entries.\n"; \
	(cd "$$workspace_root" && $(CARGO) audit "$${audit_flags[@]}")

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'


PYTHON ?= python3
# Date-dependent design checks use the HEAD commit date, never the wall clock.
AS_OF ?= $(shell git log -1 --format=%cs)
# Set BASE_REV (for example to the merge base) to reject edits to frozen registers.
BASE_REV ?=
.PHONY: design-check

design-check: ## Validate design documents, fixtures, and generator contracts
	$(PYTHON) scripts/check_docs.py --as-of $(AS_OF) $(if $(BASE_REV),--base-rev $(BASE_REV))
	$(PYTHON) -m unittest discover -s scripts/tests
	$(PYTHON) -m pytest -q scripts/tests
