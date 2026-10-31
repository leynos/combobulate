//! Expected Make gate stages and the executor calls they must produce.

use std::process::Command;

use super::{probe::GateProbe, records::Invocation};

/// Expected command stages for the complete ordered Make target.
pub(super) const ALL_STAGES: &[&str] = &[
    "fmt",
    "markdown-formatting",
    "preflight",
    "doc",
    "clippy",
    "preflight",
    "whitaker",
    "interrogate",
    "preflight",
    "nextest",
    "doctest",
    "spelling",
];

/// Checks the real Make target and confirms every selected executor call.
pub(super) fn assert_all_commands(
    invocations: &[Invocation],
) -> Result<(), Box<dyn std::error::Error>> {
    for (stage, executable, arguments) in [
        ("fmt", "probe-cargo", &["fmt", "--all", "--", "--check"][..]),
        (
            "markdown-formatting",
            "probe-mdtablefix",
            &[
                "--check",
                "--git",
                "--include-untracked",
                "--wrap",
                "--renumber",
                "--breaks",
                "--ellipsis",
                "--fences",
            ][..],
        ),
        ("preflight", "probe-check", &[][..]),
        ("doc", "probe-cargo", &["doc", "--no-deps"][..]),
        (
            "clippy",
            "probe-cargo",
            &[
                "clippy",
                "--all-targets",
                "--all-features",
                "--",
                "-D",
                "warnings",
            ][..],
        ),
        (
            "whitaker",
            "probe-whitaker",
            &["--all", "--", "--all-targets", "--all-features"][..],
        ),
        (
            "nextest-version-probe",
            "probe-cargo",
            &["nextest", "--version"][..],
        ),
        (
            "nextest",
            "probe-cargo",
            &["nextest", "run", "--all-targets", "--all-features"][..],
        ),
        (
            "doctest",
            "probe-cargo",
            &["test", "--doc", "--workspace", "--all-features"][..],
        ),
        ("spelling", "probe-spelling", &["gate"][..]),
    ] {
        GateProbe::assert_command(invocations, stage, executable, arguments);
    }
    assert_interrogate_command(invocations, 1)
}

/// Confirms Interrogate receives its pinned command and Git's complete Python inventory.
pub(super) fn assert_interrogate_command(
    invocations: &[Invocation],
    expected_count: usize,
) -> Result<(), Box<dyn std::error::Error>> {
    let interrogate_invocations = invocations
        .iter()
        .filter(|invocation| invocation.stage == "interrogate")
        .collect::<Vec<_>>();
    if interrogate_invocations.len() != expected_count {
        return Err(format!(
            "each lint run must record {expected_count} Interrogate invocation(s); found {}",
            interrogate_invocations.len()
        )
        .into());
    }

    let python_sources = python_sources_from_git()?;
    let expected_arguments = [
        "tool",
        "run",
        "--python",
        "3.14",
        "--from",
        "interrogate==1.7.0",
        "interrogate",
        "--fail-under",
        "100",
    ]
    .into_iter()
    .chain(python_sources.iter().map(String::as_str))
    .collect::<Vec<_>>();
    GateProbe::assert_command(invocations, "interrogate", "probe-uv", &expected_arguments);
    Ok(())
}

/// Reads the tracked and non-ignored untracked Python paths selected by Make.
fn python_sources_from_git() -> Result<Vec<String>, Box<dyn std::error::Error>> {
    let output = Command::new("git")
        .args([
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.py",
            "*.pyi",
        ])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()?;
    if !output.status.success() {
        return Err(format!(
            "Git must enumerate the Python sources used by the Make contract; exited with {}",
            output.status
        )
        .into());
    }
    Ok(String::from_utf8(output.stdout)?
        .lines()
        .map(str::to_owned)
        .collect())
}

/// Returns the composite stages through the selected failure boundary.
pub(super) fn expected_stages_through(failure: &str) -> Vec<String> {
    ALL_STAGES
        .iter()
        .take_while(|stage| **stage != failure)
        .copied()
        .chain(std::iter::once(failure))
        .map(str::to_owned)
        .collect()
}
