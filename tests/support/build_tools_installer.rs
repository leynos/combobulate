//! Offline executors and private pin files for installer subprocess contracts.

use std::{
    error::Error,
    io,
    process::{Command, Output},
    sync::atomic::{AtomicUsize, Ordering},
};

use camino::{Utf8Path, Utf8PathBuf};
use cap_std::{
    ambient_authority,
    fs::{Permissions, PermissionsExt},
    fs_utf8::Dir,
};

/// Errors from private fixture I/O and invocation decoding.
type Read<T> = Result<T, Box<dyn Error>>;
/// Prevents collisions between parallel installer subprocesses.
static NEXT_ID: AtomicUsize = AtomicUsize::new(0);
/// SHA-256 of the fixture archive bytes, independently calculated once.
pub(super) const ARCHIVE_SHA256: &str =
    "b82d14bd3717287c78a2e1351107a49a925192cae59c0f844437eed8a0d6caef";
/// Fixture archive name corresponding to the fixture mold pin.
pub(super) const ARCHIVE_NAME: &str = "mold-9.8.7-x86_64-linux.tar.gz";

/// Owns private executors, pin files, logs and quote-bearing scratch paths.
pub(super) struct InstallerFixture {
    /// Capability parent used for cleanup only.
    parent: Dir,
    /// Capability root for all fixture reads and writes.
    pub(super) directory: Dir,
    /// Unique private directory component.
    name: String,
    /// Absolute UTF-8 fixture root passed to child processes.
    pub(super) path: Utf8PathBuf,
}

impl InstallerFixture {
    /// Constructs fake tools without changing the test process environment.
    pub(super) fn new() -> Read<Self> {
        let parent_path = Utf8PathBuf::from_path_buf(std::env::temp_dir())
            .map_err(|path| io::Error::other(format!("non-UTF-8 temp path: {}", path.display())))?;
        let parent = Dir::open_ambient_dir(&parent_path, ambient_authority())?;
        let name = format!(
            "combobulate-installer-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        );
        parent.create_dir(&name)?;
        let fixture = Self {
            directory: parent.open_dir(&name)?,
            path: parent_path.join(&name),
            parent,
            name,
        };
        fixture.directory.create_dir("scratch'quoted")?;
        fixture.directory.write("archive", "fixture archive\n")?;
        fixture.directory.write("mold-version", "9.8.7\n")?;
        fixture.directory.write(
            "toolchain.toml",
            "[toolchain]\nchannel = \"nightly-2001-02-03\"\ncomponents = [\n  \"clippy\",\n  \
             \"rustfmt\",\n]\n",
        )?;
        fixture.checksums(&format!("{ARCHIVE_SHA256}  {ARCHIVE_NAME}\n"))?;
        fixture.write_executors()?;
        Ok(fixture)
    }

    /// Writes a chosen checksum manifest while preserving the fixture's identity.
    pub(super) fn checksums(&self, contents: &str) -> io::Result<()> {
        self.directory.write("SHA256SUMS", contents)
    }

    /// Runs the real repository installer with explicit child-only overrides.
    pub(super) fn install(&self, overrides: &[(&str, &str)]) -> io::Result<Output> {
        let mut command = self.command(overrides);
        command
            .arg(Utf8Path::new(env!("CARGO_MANIFEST_DIR")).join("scripts/install-build-tools.sh"));
        command.output()
    }

    /// Executes a committed workflow fragment through the same offline tools.
    pub(super) fn workflow_script(
        &self,
        script: &str,
        overrides: &[(&str, &str)],
    ) -> io::Result<Output> {
        self.command(overrides).args(["-c", script]).output()
    }

    /// Supplies only fixture pins, fake host inputs, and ordinary shell utilities.
    fn command(&self, overrides: &[(&str, &str)]) -> Command {
        let mut command = Command::new("/bin/bash");
        command
            .env_clear()
            .env("PATH", format!("{}:/usr/bin:/bin", self.path))
            .env("BUILD_TOOLS_PREFIX", self.path.join("prefix"))
            .env("MOLD_VERSION_FILE", self.path.join("mold-version"))
            .env("MOLD_SHA256SUMS_FILE", self.path.join("SHA256SUMS"))
            .env("RUST_TOOLCHAIN_FILE", self.path.join("toolchain.toml"))
            .env("MOLD_RELEASE_BASE_URL", "https://fixture.invalid/mold")
            .env("TMPDIR", self.path.join("scratch'quoted"))
            .env("RUNNER_TEMP", self.path.join("scratch'quoted"))
            .env("FIXTURE_ROOT", &self.path)
            .env("ACT_VERSION", "v0.2.89")
            .env("ACT_SHA256", ARCHIVE_SHA256)
            .env("FAKE_HOST_OS", "Linux")
            .env("FAKE_HOST_ARCH", "x86_64")
            .env("FAKE_HOST_TRIPLE", "x86_64-unknown-linux-gnu")
            .env("CURL_CONNECT_TIMEOUT", "7")
            .env("CURL_MIN_BYTES_PER_SECOND", "321")
            .env("CURL_STALL_SECONDS", "9");
        for (name, value) in overrides {
            command.env(name, value);
        }
        command
    }

    /// Returns argv from one fake executor, or no record when it did not run.
    pub(super) fn arguments(&self, executor: &str) -> Read<Option<Vec<String>>> {
        let bytes = match self.directory.read(format!("{executor}.args")) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error.into()),
        };
        let fields = bytes
            .strip_suffix(&[0])
            .ok_or("executor argv must end with NUL")?;
        Ok(Some(
            fields
                .split(|byte| *byte == 0)
                .map(|field| String::from_utf8(field.to_vec()))
                .collect::<Result<Vec<_>, _>>()?,
        ))
    }

    /// Counts remaining child scratch entries after the EXIT trap has run.
    pub(super) fn scratch_entries(&self) -> io::Result<usize> {
        Ok(self
            .directory
            .read_dir("scratch'quoted")?
            .collect::<io::Result<Vec<_>>>()?
            .len())
    }

    /// Writes controlled download, extraction, toolchain and host executors.
    fn write_executors(&self) -> io::Result<()> {
        for (name, script) in [
            ("curl", CURL_SCRIPT),
            ("tar", TAR_SCRIPT),
            ("rustup", RUSTUP_SCRIPT),
            ("uname", UNAME_SCRIPT),
            ("sudo", "exec \"$@\"\n"),
        ] {
            self.directory
                .write(name, format!("#!/bin/sh\nset -eu\n{script}"))?;
            self.directory
                .set_permissions(name, Permissions::from_mode(0o700))?;
        }
        Ok(())
    }
}

impl Drop for InstallerFixture {
    /// Removes only this subprocess fixture's private capability directory.
    fn drop(&mut self) { drop(self.parent.remove_dir_all(&self.name)); }
}

/// Downloads fixture bytes and records exact argv without contacting a network.
const CURL_SCRIPT: &str = concat!(
    "printf '%s\\0' \"$@\" > \"$FIXTURE_ROOT/curl.args\"\n",
    "[ \"${CURL_FAIL:-0}\" != 1 ] || exit 7\n",
    "destination=\n",
    "while [ \"$#\" -gt 0 ]; do\n",
    "  if [ \"$1\" = --output ]; then shift; destination=$1; fi\n",
    "  shift\n",
    "done\n",
    "[ -n \"$destination\" ] || exit 97\n",
    "if [ \"${CURL_CORRUPT:-0}\" = 1 ]; then printf 'tampered\\n' > \"$destination\";\n",
    "else cp \"$FIXTURE_ROOT/archive\" \"$destination\"; fi\n",
);
/// Extraction records prove checksum failures cannot reach archive execution.
const TAR_SCRIPT: &str = concat!(
    "printf '%s\\0' \"$@\" > \"$FIXTURE_ROOT/tar.args\"\n",
    "[ \"${TAR_FAIL:-0}\" != 1 ]\n",
);
/// Separates host probing from exact toolchain installation arguments.
const RUSTUP_SCRIPT: &str = concat!(
    "if [ \"$1\" = show ]; then printf 'Default host: %s\\n' \"$FAKE_HOST_TRIPLE\"; exit 0; fi\n",
    "printf '%s\\0' \"$@\" > \"$FIXTURE_ROOT/rustup.args\"\n",
    "[ \"${RUSTUP_FAIL:-0}\" != 1 ]\n",
);
/// Makes supported and unsupported hosts independent of the test machine.
const UNAME_SCRIPT: &str = concat!(
    "case \"$1\" in\n",
    "  -s) printf '%s\\n' \"$FAKE_HOST_OS\" ;;\n",
    "  -m) printf '%s\\n' \"$FAKE_HOST_ARCH\" ;;\n",
    "  -sm) printf '%s %s\\n' \"$FAKE_HOST_OS\" \"$FAKE_HOST_ARCH\" ;;\n",
    "  *) exit 97 ;;\n",
    "esac\n",
);
