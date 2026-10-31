//! Contracts for the pinned prover command and explicit formal placeholders.

use cap_std::{ambient_authority, fs_utf8::Dir};
use rstest::{fixture, rstest};

/// A private recording executable and capability-scoped Make workspace.
#[path = "support/prover_tools_probe.rs"]
mod probe;
use probe::ProverProbe;

/// Reports fixture and command failures without mutating the parent environment.
type TestResult<T = ()> = Result<T, Box<dyn std::error::Error>>;

/// Return diagnostic failures so fallible tests preserve their Result contract.
fn check(condition: bool, expectation: impl std::fmt::Display) -> TestResult {
    if condition {
        Ok(())
    } else {
        Err(expectation.to_string().into())
    }
}

/// Reads a repository file through an explicit directory capability.
fn read(path: &str) -> TestResult<String> {
    Ok(
        Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())?
            .read_to_string(path)?,
    )
}

/// Give each case an independently owned recording workspace.
#[fixture]
fn prover() -> TestResult<ProverProbe> {
    // Separate fallible setup from rstest's generated return expression.
    let prepared = ProverProbe::new()?;
    Ok(prepared)
}

/// Requires a commit-qualified helper source and all verifier release pins.
#[test]
fn prover_release_pins_are_complete() -> TestResult {
    let reference = read("tools/rust-prover-tools/REF")?;
    let commit = reference
        .lines()
        .find_map(|line| line.strip_prefix("ref: "));
    check(
        commit
            .is_some_and(|value| value.len() == 40 && value.bytes().all(|b| b.is_ascii_hexdigit())),
        format_args!("prover-tools must identify a complete Git commit; got {commit:?}"),
    )?;
    check(
        read("tools/kani/VERSION")?.trim() == "0.67.0",
        "Kani must retain its calibrated release",
    )?;
    check(
        read("tools/verus/VERSION")?.trim() == "0.2026.09.06.8dea4a2",
        "Verus must retain its calibrated release",
    )?;
    check(
        read("tools/verus/SHA256SUMS")?.contains(concat!(
            "13d01e134c0620c3b29770874707d16c33b3d227c843a489c8ceb744d43c0a16  ",
            "verus-0.2026.09.06.8dea4a2-x86-linux.zip"
        )),
        "the checksum must bind the configured Verus archive",
    )
}

/// Prevents repository recipes from reimplementing prover installation.
#[test]
fn prover_recipes_use_the_pinned_helper() -> TestResult {
    let makefile = read("Makefile")?;
    for forbidden in [
        "cargo install",
        "cargo kani setup",
        "curl ",
        "unzip ",
        "sha256sum ",
        "rustup toolchain install",
    ] {
        check(
            !makefile
                .lines()
                .any(|line| line.starts_with('\t') && line.contains(forbidden)),
            format_args!("recipes must delegate rather than run {forbidden:?}"),
        )?;
    }
    for target in [
        "install-kani",
        "kani-check",
        "install-verus",
        "kani",
        "kani-full",
        "kani-log-corpus",
        "verus-probe",
    ] {
        check(
            makefile.lines().any(|line| {
                line.split_once(':').is_some_and(|(targets, _)| {
                    targets.split_whitespace().any(|name| name == target)
                })
            }),
            format_args!("the Makefile must expose {target}"),
        )?;
    }
    Ok(())
}

/// Keeps absent product proofs visible and permits strict callers to reject them.
#[rstest]
#[case("kani")]
#[case("kani-full")]
fn formal_placeholders_report_their_status(
    prover: TestResult<ProverProbe>,
    #[case] target: &str,
) -> TestResult {
    let fixture = prover?;
    let output = fixture.run(target, false, false)?;
    check(
        output.status.success(),
        format_args!(
            "{target} must succeed: {}",
            String::from_utf8_lossy(&output.stderr)
        ),
    )?;
    check(
        String::from_utf8_lossy(&output.stdout).contains("FORMAL-SKIP:"),
        format_args!("{target} must report its missing product proof"),
    )?;
    let calls = fixture.calls()?;
    check(
        calls
            == vec![vec![
                "kani",
                "check-version",
                "--repo-root",
                ".",
                "--kani-command",
                "cargo kani",
            ]],
        format_args!("the version check must precede the placeholder; got {calls:?}"),
    )?;
    let strict = fixture.run(target, true, false)?;
    check(
        !strict.status.success(),
        format_args!("strict placeholder {target} must fail"),
    )
}

/// Records real argument vectors and requires failed installations to propagate.
#[rstest]
#[case("install-kani", "kani", "install")]
#[case("install-verus", "verus", "install")]
#[case("kani-check", "kani", "check-version")]
fn helper_arguments_and_status_are_preserved(
    prover: TestResult<ProverProbe>,
    #[case] target: &str,
    #[case] tool: &str,
    #[case] action: &str,
) -> TestResult {
    let fixture = prover?;
    let output = fixture.run(target, false, false)?;
    check(
        output.status.success(),
        format_args!(
            "the fake helper must run: {}",
            String::from_utf8_lossy(&output.stderr)
        ),
    )?;
    let mut expected = vec![tool, action, "--repo-root", "."];
    if target == "kani-check" {
        expected.extend(["--kani-command", "cargo kani"]);
    }
    let calls = fixture.calls()?;
    check(
        calls == vec![expected],
        format_args!("{target} must preserve helper arguments; got {calls:?}"),
    )?;
    let failure = fixture.run(target, false, true)?;
    check(
        !failure.status.success(),
        format_args!("{target} must propagate helper failure"),
    )
}

/// An inherited fake must not replace the pin-qualified production helper.
#[rstest]
fn environment_cannot_unlock_the_helper(prover: TestResult<ProverProbe>) -> TestResult {
    let fixture = prover?;
    let output = fixture.environment_only()?;
    check(
        output.status.success(),
        "the dry-run must parse successfully",
    )?;
    let reference = read("tools/rust-prover-tools/REF")?;
    let pin = reference
        .lines()
        .find_map(|line| line.strip_prefix("ref: "))
        .ok_or("missing prover-tools ref")?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    check(
        stdout.contains("uv tool run --from") && stdout.contains(pin),
        format_args!("environment-only substitution must retain the pin: {stdout}"),
    )
}

/// A broken pin must reject Make before an executable recipe is selected.
#[rstest]
fn malformed_pin_fails_before_any_recipe(prover: TestResult<ProverProbe>) -> TestResult {
    let fixture = prover?;
    fixture.invalidate_pin()?;
    let output = fixture.run("install-kani", false, false)?;
    check(!output.status.success(), "a malformed pin must stop Make")?;
    check(
        String::from_utf8_lossy(&output.stderr).contains("PROVER_TOOLS_REF missing or malformed"),
        "the pin diagnostic must identify the failure",
    )?;
    check(
        fixture.calls().is_err(),
        "no helper invocation may precede pin validation",
    )
}

/// Exercises real orchestration while verifier executables are recording fakes.
#[rstest]
#[case("kani-log-corpus", "kani")]
#[case("verus-probe", "verus")]
fn probe_targets_preserve_the_real_command_boundary(
    prover: TestResult<ProverProbe>,
    #[case] target: &str,
    #[case] tool: &str,
) -> TestResult {
    let fixture = prover?;
    let output = fixture.run_probe(target, false)?;
    check(
        output.status.success(),
        format_args!(
            "{target} must run the fake tools: {}",
            String::from_utf8_lossy(&output.stderr)
        ),
    )?;
    let calls = fixture.calls()?;
    check(
        calls
            .first()
            .and_then(|args| args.first())
            .is_some_and(|name| name == "kani"),
        format_args!("the version check must precede {target}; got {calls:?}"),
    )?;
    let proof_file = format!(
        "{}/tools/verifier-fixtures/verus-wiring-probe/single-root.rs",
        env!("CARGO_MANIFEST_DIR")
    );
    let expected = if tool == "kani" {
        vec![
            "kani",
            "--harness",
            "harnesses::multiplication_timeout",
            "--exact",
            "--verbose",
            "-Z",
            "unstable-options",
            "--harness-timeout",
            "5s",
        ]
    } else {
        vec![
            "verus",
            "run",
            "--repo-root",
            env!("CARGO_MANIFEST_DIR"),
            "--proof-file",
            proof_file.as_str(),
            "--extra-arg=--crate-type=lib",
            "--extra-arg=--verify-root",
            "--extra-arg=--verify-function=mutant",
        ]
    }
    .into_iter()
    .map(str::to_owned)
    .collect::<Vec<_>>();
    check(
        calls.contains(&expected),
        format_args!("{target} must forward selected arguments; got {calls:?}"),
    )?;
    if tool == "verus" {
        for count in ["1 verified", "0 verified"] {
            fixture.set_count_inflation(Some(count))?;
            let inflated = fixture.run_probe(target, false)?;
            check(
                !inflated.status.success(),
                format_args!("inflated {count} must not qualify"),
            )?;
        }
    }
    fixture.set_count_inflation(None)?;
    let failure = fixture.run_probe(target, true)?;
    check(
        !failure.status.success(),
        format_args!("{target} must propagate failed execution"),
    )
}
