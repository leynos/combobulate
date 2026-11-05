//! Private shell fixtures and liveness probes for the deadline tests.
//!
//! The tests need somewhere to write throwaway executables and a way to ask
//! whether a descendant is still running. Both are fixture plumbing rather
//! than deadline policy, so they live here and keep `tests/process_deadline.rs`
//! inside the repository's 400-line file limit.
//!
//! Nothing in this module asserts: every operation returns `Result`, and the
//! `#[test]` bodies that consume it decide how a failure is reported.

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

use super::deadline::CommandDeadline;

/// Shorthand for the fallible fixture construction the tests unwrap.
pub(crate) type Read<T> = Result<T, Box<dyn Error>>;

/// Supplies unique fixture names when tests run concurrently.
static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

/// Default period given to a test-owned command in this suite's fixtures.
///
/// A test-owned command here is a shell fixture or a `kill -0` probe. None
/// compiles anything, so a minute is a generous ceiling that still fails a
/// wedged child quickly.
pub(crate) const SHORT_DEADLINE: Duration = Duration::from_secs(60);

/// How long a terminated descendant may take to be reaped by its new parent.
const REAP_BUDGET: Duration = Duration::from_secs(10);

/// A private directory of deterministic fake executables.
pub(crate) struct Scratch {
    /// Ambient parent directory used only to remove the private fixture.
    parent: Dir,
    /// Capability handle for the private fixture directory.
    directory: Dir,
    /// Unique directory component beneath the system temporary directory.
    pub(crate) name: String,
    /// Absolute UTF-8 path handed to the command boundary.
    pub(crate) path: Utf8PathBuf,
}

impl Scratch {
    /// Creates an empty private fixture directory.
    pub(crate) fn new() -> Read<Self> {
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
    pub(crate) fn script(&self, name: &str, body: &str) -> Read<Utf8PathBuf> {
        self.directory.write(name, format!("#!/bin/sh\n{body}\n"))?;
        self.directory
            .set_permissions(name, Permissions::from_mode(0o700))?;
        Ok(self.path.join(name))
    }

    /// Reads a file the fixture wrote.
    pub(crate) fn read(&self, name: &str) -> Read<String> {
        Ok(self.directory.read_to_string(name)?)
    }
}

impl Drop for Scratch {
    /// Removes only this fixture's private directory.
    fn drop(&mut self) { drop(self.parent.remove_dir_all(&self.name)); }
}

/// Reports whether a descendant has been reaped, waiting out reparenting.
pub(crate) fn is_reaped(pid: u32) -> bool {
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
