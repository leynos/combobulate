//! Shell executors used by the real Make gate harness.

/// Cargo fixture that validates supported gate commands and nextest selection.
///
/// The two `fetch` forms are the preparation steps. Their manifests differ, so
/// the fixture distinguishes them: the root fetch has no `--manifest-path`,
/// while the gate fetch names the separate workspace it must populate. Any
/// other `fetch` shape is unexpected, which keeps the preparation contract and
/// the Make route from drifting apart silently.
///
/// The two `fmt --check` forms are reported as distinct stages for the same
/// reason. `tools/gates/cardinality-ui` is its own workspace, so the root
/// `cargo fmt --all` cannot reach it and the recipe must run a second pass with
/// `--manifest-path`. Giving that pass its own stage makes it visible in the
/// order evidence: collapsing both onto `fmt` would hide a dropped gate pass
/// behind a still-green root one.
pub(super) const CARGO_SCRIPT: &str = r#"
stage=unexpected-cargo
case "$1" in
  fetch)
    if [ "$#" -eq 2 ] && [ "$2" = --locked ]; then
      stage=prepare-dependencies
    elif [ "$#" -eq 4 ] && [ "$2" = --locked ] && [ "$3" = --manifest-path ] &&
        [ "$4" = tools/gates/cardinality-ui/Cargo.toml ]; then
      stage=prepare-ui-gate-dependencies
    else stage=unexpected-cargo; fi
    ;;
  fmt)
    if [ "$#" -eq 4 ] && [ "$2" = --all ] && [ "$3" = -- ] && [ "$4" = --check ]; then
      stage=fmt
    elif [ "$#" -eq 6 ] && [ "$2" = --manifest-path ] &&
        [ "$3" = tools/gates/cardinality-ui/Cargo.toml ] && [ "$4" = --all ] &&
        [ "$5" = -- ] && [ "$6" = --check ]; then
      stage=gate-formatting
    else stage=unexpected-cargo; fi
    ;;
  doc)
    stage=doc
    [ "$#" -eq 2 ] && [ "$2" = --no-deps ] || stage=unexpected-cargo
    ;;
  clippy)
    # DL-18: one clippy invocation per gate profile, and each gets its own
    # stage. Collapsing both onto one stage would let the argument assertion
    # compare the native-only command against the Polars-enabled record and
    # fail, or, worse, be loosened until neither exact command was checked.
    if [ "$#" -eq 6 ] && [ "$2" = --all-targets ] && \
        [ "$3" = --no-default-features ] && [ "$4" = -- ] && \
        [ "$5" = -D ] && [ "$6" = warnings ]; then
      stage=clippy-native-only
    elif [ "$#" -eq 5 ] && [ "$2" = --all-targets ] && [ "$3" = -- ] && \
        [ "$4" = -D ] && [ "$5" = warnings ]; then
      stage=clippy-polars-enabled
    else stage=unexpected-cargo; fi
    ;;
  nextest)
    if [ "$#" -eq 2 ] && [ "$2" = --version ]; then
      stage=nextest-version-probe
    elif [ "$#" -eq 4 ] && [ "$2" = run ] && [ "$3" = --all-targets ] &&
        [ "$4" = --no-default-features ]; then
      stage=nextest-native-only
    elif [ "$#" -eq 3 ] && [ "$2" = run ] && [ "$3" = --all-targets ]; then
      stage=nextest-polars-enabled
    else stage=unexpected-cargo; fi
    ;;
  test)
    # There is deliberately no gate-build form here. The gate is built through
    # `scripts/cardinality_ui_gate.py prepare`, which records the executable
    # path Cargo reported; a recipe that reached Cargo directly would bypass
    # that record and leave the root UI test without a path to run. Accepting
    # the old shape would let that regression pass the contract silently.
    if [ "$#" -eq 4 ] && [ "$2" = --doc ] && [ "$3" = --workspace ] &&
        [ "$4" = --no-default-features ]; then
      stage=doctest-native-only
    elif [ "$#" -eq 3 ] && [ "$2" = --doc ] && [ "$3" = --workspace ]; then
      stage=doctest-polars-enabled
    else stage=unexpected-cargo; fi
    ;;
  *) stage=unexpected-cargo ;;
esac
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
case "$stage" in unexpected-*) exit 64 ;; esac
if [ "${GATE_FAIL_AT-}" = "$stage" ]; then exit 1; fi
if [ "$stage" = nextest-version-probe ]; then printf '%s\n' 'cargo-nextest 0.9.0'; fi
"#;

/// Gate recipe fixture validates the exact prepare/run boundary.
///
/// The script owns both halves of the gate route: `prepare` builds and records
/// the binary, and `run` executes that record under a deadline. A recipe that
/// slips back to invoking Cargo directly, or that reaches Cargo without the
/// gate's environment, is a different command and therefore unexpected here.
pub(super) const GATE_SCRIPT: &str = r#"
stage=unexpected-gate
if [ "$#" -eq 2 ] && [ "$1" = scripts/cardinality_ui_gate.py ]; then
  case "$2" in
    prepare|run) stage=prepare-ui-gate ;;
  esac
fi
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
case "$stage" in unexpected-*) exit 64 ;; esac
[ "${GATE_FAIL_AT-}" != "$stage" ]
"#;

/// Interrogate fixture validates the pinned tool invocation and injects failure.
pub(super) const INTERROGATE_SCRIPT: &str = r#"
stage=interrogate
if [ "$#" -lt 10 ] || [ "$1" != tool ] || [ "$2" != run ] ||
   [ "$3" != --python ] || [ "$4" != 3.14 ] || [ "$5" != --from ] ||
   [ "$6" != interrogate==1.7.0 ] || [ "$7" != interrogate ] ||
   [ "$8" != --fail-under ] || [ "$9" != 100 ]; then
  stage=unexpected-interrogate
fi
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
[ "$stage" = interrogate ] || exit 64
[ "${GATE_FAIL_AT-}" != interrogate ]
"#;

/// Preflight fixture rejects arguments and supports controlled failure.
pub(super) const PREFLIGHT_SCRIPT: &str = r#"
stage=preflight
if [ "$#" -ne 0 ]; then
  stage=unexpected-preflight
  record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
  exit 64
fi
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
[ "${GATE_FAIL_AT-}" != "$stage" ]
"#;

/// Markdown formatter fixture validates the exact check-only command.
pub(super) const MDTABLEFIX_SCRIPT: &str = r#"
stage=markdown-formatting
[ "$#" -eq 8 ] && [ "$1" = --check ] && [ "$2" = --git ] &&
  [ "$3" = --include-untracked ] && [ "$4" = --wrap ] &&
  [ "$5" = --renumber ] && [ "$6" = --breaks ] &&
  [ "$7" = --ellipsis ] && [ "$8" = --fences ] || stage=unexpected-mdtablefix
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
[ "$stage" = markdown-formatting ] || exit 64
[ "${GATE_FAIL_AT-}" != "markdown-formatting" ]
"#;

/// markdownlint fixture detects unexpected execution during check-fmt.
pub(super) const MDLINT_SCRIPT: &str = r#"
stage=unexpected-markdownlint
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
exit 64
"#;

/// Spelling fixture validates the builder's binding `gate` command.
pub(super) const SPELLING_SCRIPT: &str = r#"
stage=spelling
if [ "$#" -ne 1 ] || [ "$1" != gate ]; then
  stage=unexpected-spelling
  record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
  exit 64
fi
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
[ "${GATE_FAIL_AT-}" != "$stage" ]
"#;

/// Act fixture detects a forbidden nested execution path.
pub(super) const ACT_SCRIPT: &str = r#"
stage=unexpected-act
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
exit 64
"#;

/// Whitaker fixture proves private cache warmth and repository Cargo settings.
///
/// DL-18: Whitaker forwards everything after `--` to `cargo check`, so it must
/// run once per gate profile and each run gets its own stage. A single
/// unflagged run would check only the default features — the Polars-enabled
/// profile — and the native-only `cfg(not(feature = "polars"))` code would
/// never reach a lint. Collapsing both onto one stage would let the argument
/// assertion compare one profile's argv against the other's record.
pub(super) const WHITAKER_SCRIPT: &str = r#"
cache="$DYLINT_DRIVER_PATH/driver-marker"
if [ -f "$cache" ]; then
  cache_state=warm
else
  mkdir -p "$DYLINT_DRIVER_PATH" && : > "$cache" || exit 1
  cache_state=cold
fi
if [ "$#" -eq 6 ] && [ "$1" = --lib ] && [ "$2" = whitaker_suite ] && \
   [ "$3" = --fail-on-no-libraries ] && [ "$4" = -- ] && \
   [ "$5" = --all-targets ] && [ "$6" = --no-default-features ]; then
  stage=whitaker-native-only
elif [ "$#" -eq 5 ] && [ "$1" = --lib ] && [ "$2" = whitaker_suite ] && \
   [ "$3" = --fail-on-no-libraries ] && [ "$4" = -- ] && \
   [ "$5" = --all-targets ]; then
  stage=whitaker-polars-enabled
else
  record_invocation "$GATE_LOG" unexpected-whitaker "${0##*/}" "$cache_state" none '' "$@"
  exit 64
fi
record_invocation "$GATE_LOG" "$stage" "${0##*/}" "$cache_state" none '' "$@"
if [ "${GATE_FAIL_AT-}" = "$stage" ]; then exit 1; fi
record_repository_config() {
  query=$1
  output=$(cargo -Z unstable-options config get "$query") || return 1
  record_invocation "$WHITAKER_ENV_LOG" repository-config cargo none value "$output" -Z unstable-options config get "$query"
}
record_repository_config profile.dev.codegen-backend || exit 1
record_repository_config build.rustflags || exit 1
record_repository_config target.x86_64-unknown-linux-gnu.linker || exit 1
record_repository_config target.x86_64-unknown-linux-gnu.rustflags || exit 1
"#;

/// `mktemp` fixture creates a private driver directory or injects failure.
pub(super) const MKTEMP_SCRIPT: &str = r#"
stage=mktemp
if [ "$#" -ne 2 ] || [ "$1" != -d ] ||
   [ "$2" != "$BUILD_TOOLS_PREFIX/target/whitaker-driver.XXXXXX" ]; then
  stage=unexpected-mktemp
fi
record_invocation "$GATE_LOG" "$stage" "${0##*/}" none none '' "$@"
[ "$stage" = mktemp ] || exit 64
[ "${GATE_FAIL_AT-}" != mktemp ] || exit 1
cache_dir="$BUILD_TOOLS_PREFIX/target/whitaker-driver.fixture"
mkdir "$cache_dir" || exit 1
printf '%s\n' "$cache_dir"
"#;
