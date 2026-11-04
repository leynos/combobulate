//! Bounded execution of external commands started by tests.
//!
//! Every gate and measurement route in this repository ultimately runs a child
//! process: Cargo, Make, Act, Git, or a shell fixture. A child that never
//! returns used to be bounded only by whatever clock sat outside it, and the
//! incident behind this helper sat inside a nested Cargo build with no clock
//! at all for over two and a quarter hours.
//!
//! [`CommandDeadline`] wraps such a command in GNU `timeout`, which puts the
//! child in its own process group and, after the deadline, signals the whole
//! group, then kills whatever ignored `SIGTERM`. The wrapper is test support,
//! not a general execution framework: it exists for command lines this suite
//! builds itself and it deliberately does not grow into a second process API
//! beside `std::process`.
//!
//! Ownership, permitted callers, and the deadline tiers are recorded in
//! "Test timeouts" in `docs/developers-guide.md`; change that section with
//! this file.

use std::{
    ffi::OsStr,
    fmt::Display,
    io,
    process::{Command, ExitStatus},
    time::{Duration, Instant},
};

/// An external command with an explicit deadline attached.
///
/// The caller configures the command it wants to run; the deadline is installed
/// when the command is executed, because `timeout` takes its own options before
/// the program it wraps.
///
/// The deadline is always supplied by the caller rather than defaulted here.
/// This module is compiled into more than one test binary, and a default would
/// be dead code in every binary that chooses a different tier; the tiers
/// themselves are policy and belong with the test that measures them.
pub(crate) struct CommandDeadline {
    target: Command,
    deadline: Duration,
}

impl CommandDeadline {
    /// Starts a command that will run under an explicit deadline.
    pub(crate) fn with_deadline(program: impl AsRef<OsStr>, deadline: Duration) -> Self {
        Self {
            target: Command::new(program),
            deadline,
        }
    }

    /// Gives the caller the command to configure.
    ///
    /// Arguments, working directory, and environment changes apply to the
    /// wrapped program and are replayed onto the wrapper before it runs, which
    /// preserves the usual `Command` ergonomics at the call site.
    pub(crate) const fn command(&mut self) -> &mut Command { &mut self.target }

    /// Runs the wrapped command to completion within the deadline.
    ///
    /// # Errors
    ///
    /// Returns the spawn failure or the I/O failure; a child that exits
    /// non-zero is a successful run whose [`ExitStatus`] records it. A child
    /// that overruns is reported by [`Observed::exceeded_deadline`].
    pub(crate) fn output(&mut self) -> Result<Observed, DeadlineError> {
        let started = Instant::now();
        let output = self
            .wrapper()
            .output()
            .map_err(|source| self.spawn_error(source))?;
        Ok(Observed {
            status: output.status,
            stdout: output.stdout,
            stderr: output.stderr,
            line: self.line(),
            duration: started.elapsed(),
        })
    }

    /// Builds the `timeout` invocation that wraps the configured command.
    ///
    /// `timeout` re-executes the configured program, so every argument,
    /// environment change, and working directory has to be replayed onto the
    /// wrapper. It runs without `--foreground`, which means `timeout` also
    /// becomes the child's process-group leader: a signal then reaches the
    /// program's descendants, not just the program.
    fn wrapper(&self) -> Command {
        let mut wrapper = Command::new("timeout");
        wrapper.args(timeout_options(self.deadline));
        wrapper.arg(self.target.get_program());
        wrapper.args(self.target.get_args());
        for (name, setting) in self.target.get_envs() {
            match setting {
                Some(value) => {
                    wrapper.env(name, value);
                }
                None => {
                    wrapper.env_remove(name);
                }
            }
        }
        if let Some(directory) = self.target.get_current_dir() {
            wrapper.current_dir(directory);
        }
        wrapper
    }

    /// Describes the failed invocation, naming the program the caller configured.
    fn spawn_error(&self, source: io::Error) -> DeadlineError {
        DeadlineError::Spawn {
            line: self.line(),
            source,
        }
    }

    /// Renders the configured command line for diagnostics.
    fn line(&self) -> String {
        let arguments: Vec<String> = self
            .target
            .get_args()
            .map(|argument| argument.to_string_lossy().into_owned())
            .collect();
        CommandLine {
            program: self.target.get_program().to_string_lossy().into_owned(),
            arguments,
        }
        .to_string()
    }
}

/// The `timeout` options this helper always applies.
///
/// `--signal=TERM` states the signal rather than inheriting the coreutils
/// default, and `--kill-after` turns a child that ignores `SIGTERM` into one
/// that receives `SIGKILL` two seconds later. Together they make the deadline a
/// guarantee rather than a request.
fn timeout_options(deadline: Duration) -> [String; 3] {
    [
        "--signal=TERM".to_owned(),
        format!("--kill-after={KILL_GRACE}"),
        format!("{}", deadline.as_secs_f64().max(MINIMUM_SECONDS)),
    ]
}

/// How long a child may ignore `SIGTERM` before `SIGKILL` follows.
const KILL_GRACE: &str = "2s";

/// A deadline never rounds down to zero, which `timeout` rejects.
const MINIMUM_SECONDS: f64 = 0.001;

/// Exit status 124, which `timeout` uses to report that the deadline expired.
const TIMEOUT_EXIT: i32 = 124;

/// A finished command together with what the run itself cost.
pub(crate) struct Observed {
    status: ExitStatus,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    line: String,
    duration: Duration,
}

impl Observed {
    /// Returns the exit status the child or its wrapper reported.
    pub(crate) const fn status(&self) -> ExitStatus { self.status }

    /// Returns the captured standard output, empty for a status-only run.
    pub(crate) fn stdout(&self) -> &[u8] { &self.stdout }

    /// Returns the captured standard error, empty for a status-only run.
    pub(crate) fn stderr(&self) -> &[u8] { &self.stderr }

    /// Returns the command line that produced this result.
    pub(crate) fn line(&self) -> &str { &self.line }

    /// Returns how long the run took.
    pub(crate) const fn duration(&self) -> Duration { self.duration }

    /// Reports whether the run ended because its deadline expired.
    pub(crate) fn exceeded_deadline(&self) -> bool { self.status.code() == Some(TIMEOUT_EXIT) }
}

/// A command line rendered for an error message.
struct CommandLine {
    program: String,
    arguments: Vec<String>,
}

impl Display for CommandLine {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.program)?;
        for argument in &self.arguments {
            write!(formatter, " {argument}")?;
        }
        Ok(())
    }
}

/// A command that could not be started under its deadline.
#[derive(Debug)]
pub(crate) enum DeadlineError {
    /// The `timeout` wrapper, or the program it was asked to run, could not start.
    Spawn {
        /// The command line the caller configured.
        line: String,
        /// The operating-system error that stopped it.
        source: io::Error,
    },
}

impl Display for DeadlineError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Spawn { line, source } => {
                write!(
                    formatter,
                    "could not start `{line}` under its deadline: {source}"
                )
            }
        }
    }
}

impl std::error::Error for DeadlineError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Spawn { source, .. } => Some(source),
        }
    }
}
