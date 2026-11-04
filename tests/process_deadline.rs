//! Behavioural tests for bounded execution of external commands.
//!
//! The boundary exists to stop a wedged child from holding a gate open, so
//! these cases cover every guarantee it claims: a deadline that ends the
//! command and its descendants, streams larger than a pipe buffer, the
//! caller's environment and directory reaching the wrapped program, and
//! diagnostics that name what ran.
//!
//! The tests themselves return `()` rather than `Result`. The workspace denies
//! `panic_in_result_fn`, so a fallible test body that asserts would have to
//! report every failed expectation as an error value, which buries the
//! expectation under plumbing. Fixture construction therefore returns `Result`
//! and the `#[test]` bodies unwrap it with `.expect`, which the workspace's
//! `allow-expect-in-tests` covers. Helpers outside a test body must not use
//! `expect`, so the fixture type propagates its errors instead.

use std::{
    error::Error,
    io,
    sync::atomic::{AtomicUsize, Ordering},
    time::{Duration, Instant},
};

use camino::Utf8PathBuf;
use cap_std::{
    ambient_authority,
    fs::{Permissions, PermissionsExt},
    fs_utf8::Dir,
};

#[path = "support/process_deadline.rs"]
mod deadline;

use deadline::CommandDeadline;

/// Shorthand for the fallible fixture construction the tests unwrap.
type Read<T> = Result<T, Box<dyn Error>>;

/// Supplies unique fixture names when tests run concurrently.
static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

/// A deadline short enough to prove termination without a slow suite.
const ONE_SECOND: Duration = Duration::from_secs(1);

/// Default period given to a test-owned command in this suite's fixtures.
///
/// A test-owned command here is a fake executor, a `kill -0` probe, or a shell
/// fixture that sleeps. None compiles anything, so a minute is a generous
/// ceiling that still fails a wedged child quickly.
const SHORT_DEADLINE: Duration = Duration::from_secs(60);

/// How long a terminated descendant may take to be reaped by its new parent.
const REAP_BUDGET: Duration = Duration::from_secs(10);

/// A private directory of deterministic fake executables.
struct Scratch {
    /// Ambient parent directory used only to remove the private fixture.
    parent: Dir,
    /// Capability handle for the private fixture directory.
    directory: Dir,
    /// Unique directory component beneath the system temporary directory.
    name: String,
    /// Absolute UTF-8 path handed to the command boundary.
    path: Utf8PathBuf,
}

impl Scratch {
    /// Creates an empty private fixture directory.
    fn new() -> Read<Self> {
        let parent_path = Utf8PathBuf::from_path_buf(std::env::temp_dir()).map_err(|path| {
            io::Error::other(format!(
                "the system temporary directory must be UTF-8 for shell fixtures: {}",
                path.display()
            ))
        })?;
        let parent = Dir::open_ambient_dir(&parent_path, ambient_authority())?;
        let name = format!(
            "combobulate-deadline-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        );
        parent.create_dir(&name)?;
        let directory = parent.open_dir(&name)?;
        Ok(Self {
            parent,
            directory,
            name: name.clone(),
            path: parent_path.join(name),
        })
    }

    /// Writes an executable shell fixture and returns its absolute path.
    fn script(&self, name: &str, body: &str) -> Read<Utf8PathBuf> {
        self.directory.write(name, format!("#!/bin/sh\n{body}\n"))?;
        self.directory
            .set_permissions(name, Permissions::from_mode(0o700))?;
        Ok(self.path.join(name))
    }

    /// Reads a file the fixture wrote.
    fn read(&self, name: &str) -> Read<String> { Ok(self.directory.read_to_string(name)?) }
}

impl Drop for Scratch {
    /// Removes only this fixture's private directory.
    fn drop(&mut self) { drop(self.parent.remove_dir_all(&self.name)); }
}

/// A completed command reports what it wrote, what it cost, and what it ran.
#[test]
fn a_completing_command_reports_status_output_and_duration() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let script = scratch
        .script("emit.sh", "printf 'out'; printf 'err' >&2")
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, SHORT_DEADLINE);
    let observed = command.output().expect("the emitting fixture must start");

    assert!(
        observed.status().success(),
        "the emitting fixture must succeed, stderr: {}",
        String::from_utf8_lossy(observed.stderr())
    );
    assert_eq!(
        observed.stdout(),
        b"out".as_slice(),
        "the boundary must capture standard output"
    );
    assert_eq!(
        observed.stderr(),
        b"err".as_slice(),
        "the boundary must capture standard error"
    );
    assert!(
        !observed.exceeded_deadline(),
        "a command that finished must not be reported as an overrun"
    );
    assert!(
        observed.line().contains("emit.sh"),
        "the diagnostic must name the program that ran: {}",
        observed.line()
    );
    assert!(
        observed.duration() < Duration::from_secs(30),
        "the recorded duration must describe the run, not the wrapper's start-up: {:?}",
        observed.duration()
    );
}

/// A non-zero exit is a completed run the caller inspects, not an I/O error.
#[test]
fn a_non_zero_exit_is_a_completed_run() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let script = scratch
        .script("refuse.sh", "printf 'diagnosis' >&2; exit 7")
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, SHORT_DEADLINE);
    let observed = command.output().expect("the refusing fixture must start");

    assert_eq!(
        observed.status().code(),
        Some(7),
        "the fixture's own exit status must survive the wrapper"
    );
    assert!(
        !observed.exceeded_deadline(),
        "an ordinary failure must not be mistaken for a deadline overrun"
    );
    assert_eq!(
        observed.stderr(),
        b"diagnosis".as_slice(),
        "diagnostics must survive a failing exit"
    );
}

/// A command that overruns its deadline is ended rather than waited on.
#[test]
fn a_command_that_overruns_its_deadline_is_terminated() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let script = scratch
        .script("wedged.sh", "exec sleep 30")
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, ONE_SECOND);
    let started = Instant::now();
    let observed = command.output().expect("the wedged fixture must start");

    assert!(
        observed.exceeded_deadline(),
        "the wrapper must report an overrun, got {:?}",
        observed.status()
    );
    assert!(
        started.elapsed() < Duration::from_secs(20),
        "the deadline must end the run promptly: {:?}",
        observed.duration()
    );
}

/// A descendant of a timed-out command does not survive its parent.
#[test]
fn a_descendant_of_a_timed_out_command_does_not_survive() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let pid_file = scratch.path.join("grandchild.pid");
    let script = scratch
        .script(
            "family.sh",
            &format!("sleep 30 &\nprintf '%s' \"$!\" > '{pid_file}'\nwait"),
        )
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, ONE_SECOND);
    let observed = command.output().expect("the family fixture must start");

    assert!(
        observed.exceeded_deadline(),
        "the waiting parent must be reported as an overrun, got {:?}",
        observed.status()
    );
    let recorded = scratch
        .read("grandchild.pid")
        .expect("the fixture must have recorded its descendant");
    let pid: u32 = recorded
        .trim()
        .parse()
        .expect("the fixture must record a numeric descendant pid");
    assert!(
        is_reaped(pid),
        "the waiting grandchild {pid} must be signalled with its process group"
    );
}

/// Output larger than a pipe buffer is drained rather than deadlocked.
#[test]
fn output_larger_than_a_pipe_buffer_is_drained_completely() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let script = scratch
        .script("flood.sh", "dd if=/dev/zero bs=1024 count=512 2>/dev/null")
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, SHORT_DEADLINE);
    let observed = command.output().expect("the flooding fixture must start");

    assert!(
        observed.status().success(),
        "the flooding fixture must complete, stderr: {}",
        String::from_utf8_lossy(observed.stderr())
    );
    assert_eq!(
        observed.stdout().len(),
        512 * 1024,
        "a stream larger than the pipe buffer must be drained in full"
    );
}

/// The caller's environment, removals, and directory reach the child.
#[test]
fn configuration_reaches_the_wrapped_program() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let script = scratch
        .script(
            "where.sh",
            "pwd\nprintf 'marker=%s\\n' \"$DEADLINE_MARKER\"\nprintf 'absent=%s\\n' \
             \"${DEADLINE_ABSENT-unset}\"",
        )
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, SHORT_DEADLINE);
    command
        .command()
        .current_dir(&scratch.path)
        .env("DEADLINE_MARKER", "forwarded")
        .env_remove("DEADLINE_ABSENT");
    let observed = command.output().expect("the reporting fixture must start");

    assert!(
        observed.status().success(),
        "the reporting fixture must succeed, stderr: {}",
        String::from_utf8_lossy(observed.stderr())
    );
    let text = String::from_utf8_lossy(observed.stdout()).into_owned();
    assert!(
        text.contains(&scratch.name),
        "the configured working directory must reach the child: {text}"
    );
    assert!(
        text.contains("marker=forwarded"),
        "the configured environment must reach the child: {text}"
    );
    assert!(
        text.contains("absent=unset"),
        "an environment removal must reach the child: {text}"
    );
}

/// A program the wrapper cannot find is reported, not silently awaited.
#[test]
fn a_missing_program_is_reported_by_the_wrapper() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let missing = scratch.path.join("absent-program");
    let mut command = CommandDeadline::with_deadline(&missing, SHORT_DEADLINE);
    let observed = command.output().expect("the wrapper itself must start");

    assert_eq!(
        observed.status().code(),
        Some(127),
        "GNU timeout reports an executable it cannot find as 127"
    );
    assert!(
        observed.line().contains("absent-program"),
        "the diagnostic must name the program the caller configured: {}",
        observed.line()
    );
}

/// Reports whether a descendant has been reaped, waiting out reparenting.
fn is_reaped(pid: u32) -> bool {
    let deadline = Instant::now() + REAP_BUDGET;
    while Instant::now() < deadline {
        if !is_running(pid) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    false
}

/// Reports whether a signal could still be delivered to the descendant.
fn is_running(pid: u32) -> bool {
    let mut probe = CommandDeadline::with_deadline("kill", SHORT_DEADLINE);
    probe.command().args(["-0", &pid.to_string()]);
    probe
        .output()
        .is_ok_and(|observed| observed.status().success())
}
