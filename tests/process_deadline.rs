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
    os::unix::process::ExitStatusExt,
    time::{Duration, Instant},
};

#[path = "support/process_deadline.rs"]
mod deadline;
#[path = "support/process_deadline_fixture.rs"]
mod fixture;

use deadline::{CommandDeadline, DeadlineOutcome};
use fixture::{SHORT_DEADLINE, Scratch, is_reaped};

/// A deadline short enough to prove termination without a slow suite.
const ONE_SECOND: Duration = Duration::from_secs(1);

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

/// A child that ignores `SIGTERM` still ends, and reports the escalation.
///
/// This is the case the plain `124` predicate missed. GNU `timeout` runs out
/// of patience after `--kill-after` and sends `SIGKILL`; because the child runs
/// in its own process group, `timeout` then kills itself with the same signal,
/// so the run ends with no exit status rather than with 137. The older check
/// read that as "not a timeout". The wrapper's verbose announcement is what
/// identifies it.
#[test]
fn a_term_resistant_child_is_killed_and_reported_as_an_escalation() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let script = scratch
        .script("stubborn.sh", "trap '' TERM\nexec sleep 30")
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, ONE_SECOND);
    let started = Instant::now();
    let observed = command.output().expect("the stubborn fixture must start");

    assert_eq!(
        observed.outcome(),
        DeadlineOutcome::Escalated,
        "a child that ignored SIGTERM must be reported as an escalated deadline, got {:?} with \
         status {:?} and stderr {}",
        observed.outcome(),
        observed.status(),
        String::from_utf8_lossy(observed.stderr())
    );
    assert!(
        observed.exceeded_deadline(),
        "an escalated kill is still a deadline the wrapper enforced"
    );
    assert!(
        started.elapsed() < Duration::from_secs(20),
        "the kill grace must bound the run: {:?}",
        observed.duration()
    );
}

/// A descendant of a `SIGTERM`-resistant child does not survive either.
///
/// The child traps `SIGTERM`, so the group signal only reaches it; the
/// descendant is still in that group and receives the `SIGKILL` that follows.
/// Without that, a wedged shell could leave a build running after the deadline
/// the wrapper reported.
#[test]
fn a_descendant_of_a_term_resistant_child_does_not_survive() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let pid_file = scratch.path.join("stubborn-descendant.pid");
    let script = scratch
        .script(
            "stubborn-family.sh",
            &format!(
                "trap '' TERM\nsleep 30 &\nprintf '%s' \"$!\" > '{pid_file}'\nwhile :; do sleep 1; \
                 done"
            ),
        )
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, ONE_SECOND);
    let observed = command.output().expect("the stubborn family fixture must start");

    assert_eq!(
        observed.outcome(),
        DeadlineOutcome::Escalated,
        "the trapping parent must be killed rather than terminating cleanly, status {:?}, stderr \
         {}",
        observed.status(),
        String::from_utf8_lossy(observed.stderr())
    );
    let recorded = scratch
        .read("stubborn-descendant.pid")
        .expect("the fixture must have recorded its descendant");
    let pid: u32 = recorded
        .trim()
        .parse()
        .expect("the fixture must record a numeric descendant pid");
    assert!(
        is_reaped(pid),
        "the descendant {pid} must be killed with the process group, not left running"
    );
}

/// A kill the wrapper did not announce is not a timeout.
///
/// A child can die of `SIGKILL` for reasons that have nothing to do with the
/// deadline — an out-of-memory killer, or another process signalling it. The
/// run then ends of signal 9 with an empty standard error, which is
/// indistinguishable from an announced escalation except for the announcement
/// itself. The older predicate would have called it an overrun and hidden the
/// real cause.
#[test]
fn an_unannounced_kill_is_not_a_deadline_overrun() {
    let scratch = Scratch::new().expect("the fixture directory must be creatable");
    let script = scratch
        .script("selfkill.sh", "kill -KILL $$")
        .expect("the fixture script must be writable and executable");
    let mut command = CommandDeadline::with_deadline(&script, SHORT_DEADLINE);
    let observed = command.output().expect("the self-killing fixture must start");

    assert_eq!(
        observed.status().signal(),
        Some(9),
        "the fixture must report the signal that ended it"
    );
    assert!(
        observed.stderr().is_empty(),
        "an unannounced kill must leave the wrapper with nothing to report: {}",
        String::from_utf8_lossy(observed.stderr())
    );
    assert!(
        !observed.exceeded_deadline(),
        "a SIGKILL the wrapper never announced must not be reported as a deadline: status {:?}, \
         stderr {}",
        observed.status(),
        String::from_utf8_lossy(observed.stderr())
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

