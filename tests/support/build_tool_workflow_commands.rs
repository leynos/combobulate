//! Classify the shell commands a workflow's `run:` steps would execute.
//!
//! A workflow step can run a suite directly, or through Make, or not at all.
//! Deciding which is a question about shell text, and it is answered here so
//! the provisioning rules in [`super::build_tool_workflows`] can stay about
//! jobs and steps.
//!
//! Every rule here fails closed. A command the classifier cannot resolve is an
//! error rather than a "no suite", because silently treating an unreadable
//! command as harmless is how an unprovisioned suite would escape the check.

use std::process::Command;

pub(super) type Read<T> = Result<T, Box<dyn std::error::Error>>;

/// One shell line with its tokens retained for conservative suite detection.
pub(super) struct WorkflowCommand<'a> {
    pub(super) source: &'a str,
    pub(super) words: Vec<&'a str>,
}

/// Detect a test suite in a dry-run of a Make goal, including prerequisites.
///
/// The profile route is pinned rather than inherited, for the same reason
/// `dry_run` in `build_standard_contract.rs` pins it: a hosted job exports the
/// single profile it was scheduled to measure, and an inherited value would
/// halve the recipes this dry run reads. Pinning on the command line outranks
/// an inherited value however it arrives.
fn make_goal_runs_suite(goal: &str) -> Read<bool> {
    let output = Command::new("make")
        .env_remove("GATE_PROFILE")
        .args([
            "-n",
            "-B",
            "GATE_PROFILE=both",
            "CARGO=probe-cargo",
            "CHECK_BUILD_TOOLS=true",
            goal,
        ])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()?;
    if !output.status.success() {
        return Err(format!("cannot inspect Make goal {goal}").into());
    }
    let commands = String::from_utf8_lossy(&output.stdout);
    Ok(commands.contains("probe-cargo test")
        || commands.contains("probe-cargo nextest run")
        || commands.contains("probe-cargo llvm-cov"))
}

/// Resolve one Make command, failing closed on options or dynamic goals.
fn make_line_reaches_suite(command: &WorkflowCommand<'_>) -> Read<bool> {
    for (index, word) in command.words.iter().enumerate() {
        if !matches!(*word, "make" | "$(MAKE)") {
            continue;
        }
        let goal = command
            .words
            .get(index + 1)
            .map(|value| value.trim_end_matches(';'))
            .ok_or_else(|| format!("Make invocation has no goal: {}", command.source))?;
        if goal.starts_with('-') || goal.contains('$') {
            return Err(format!("unresolved Make goal in workflow: {}", command.source).into());
        }
        if make_goal_runs_suite(goal)? {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Resolve one direct Cargo command without mistaking binstall for a suite.
///
/// A workflow may spell a build's flags as a shell array and expand it, as
/// `profile-measurements.yml` does so one `run:` block can measure all three
/// profiles. An expansion after a subcommand that never runs tests cannot
/// become one, because Cargo takes the subcommand positionally and everything
/// after it is that subcommand's own argument. So the command is resolved by
/// identifying the subcommand rather than by rejecting every `$`.
///
/// The allowlist below is deliberate. An option that takes its value as a
/// separate word puts that value where the subcommand would be, and no such
/// name is on the list, so the command stays unresolved and the check still
/// fails closed.
fn cargo_line_reaches_suite(command: &WorkflowCommand<'_>) -> Read<bool> {
    let Some(index) = command.words.iter().position(|word| *word == "cargo") else {
        return Ok(false);
    };
    let arguments = command
        .words
        .get(index + 1..)
        .ok_or("Cargo command has no arguments")?;
    if cargo_arguments_reach_suite(arguments) {
        return Ok(true);
    }
    if arguments.iter().any(|argument| argument.contains('$'))
        && !cargo_subcommand_runs_no_tests(arguments)
    {
        return Err(format!("unresolved Cargo command in workflow: {}", command.source).into());
    }
    Ok(false)
}

/// Report whether the command's subcommand is one that runs no test target.
///
/// Cargo's grammar is `cargo [global option]… <subcommand> [argument]…`, so the
/// first word that is neither an option nor a `+toolchain` override is the
/// subcommand. If that word is not a literal, or is not a subcommand known to
/// run no tests, this reports false and the caller treats the command as
/// unresolved.
fn cargo_subcommand_runs_no_tests(arguments: &[&str]) -> bool {
    /// Subcommands that compile, fetch, inspect or install, but never run a suite.
    const NON_SUITE: &[&str] = &[
        "binstall", "build", "check", "clean", "clippy", "doc", "fetch", "install", "metadata",
        "package", "publish", "tree", "update",
    ];
    arguments
        .iter()
        .find(|word| !word.starts_with('-') && !word.starts_with('+'))
        .is_some_and(|subcommand| NON_SUITE.contains(subcommand))
}

/// Recognize suite subcommands even after a toolchain or Cargo option.
fn cargo_arguments_reach_suite(arguments: &[&str]) -> bool {
    arguments.contains(&"test")
        || arguments.contains(&"llvm-cov")
        || arguments.windows(2).any(|pair| pair == ["nextest", "run"])
}

/// Recognize directly invoked test tools and Make goals in a workflow script.
pub(in crate::support) fn run_reaches_suite(script: &str) -> Read<bool> {
    for line in script
        .lines()
        .map(str::trim)
        .filter(|line| !line.starts_with('#'))
    {
        let command = WorkflowCommand {
            source: line,
            words: line.split_whitespace().collect(),
        };
        if command.words.first().is_some_and(|word| {
            matches!(*word, "bash" | "sh" | "source" | "eval") || word.starts_with("./")
        }) {
            return Err(format!("unresolved shell command in workflow: {line}").into());
        }
        if cargo_line_reaches_suite(&command)? || make_line_reaches_suite(&command)? {
            return Ok(true);
        }
    }
    Ok(false)
}
