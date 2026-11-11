//! A fake Cargo executable for asserting what Make actually invokes.
//!
//! Make targets reach Cargo through `$(CARGO)`. Testing the routes therefore
//! means substituting that variable with something that records the call rather
//! than compiling. This module owns that substitute and the temporary directory
//! around it.
//!
//! The substitute answers `nextest --version` itself, so a single probe
//! exercises both the Nextest-present and Nextest-absent branches without
//! depending on what the host happens to have installed. Every other
//! invocation is appended to `cargo.log` for the caller to read back.
//!
//! `PYTHON` is substituted for the same reason. Several targets now build the
//! cardinality gate before running anything, and that recipe runs
//! `scripts/cardinality_ui_gate.py`. Letting the real script see a fake Cargo
//! would fail preparation — correctly, since a fake cannot report an
//! executable — and, worse, a fake that *could* satisfy it would overwrite the
//! gate's build record with a path no real build produced, breaking the root
//! cardinality test that shares this workspace. The stub therefore records the
//! call and does nothing, which is all these tests claim about it; the exact
//! argv and the real preparation are pinned by `tests/make_gate_order.rs` and
//! `scripts/tests/test_cardinality_ui_gate.py`.

use std::{
    error::Error,
    io,
    process::Command,
    sync::atomic::{AtomicUsize, Ordering},
};

use camino::{Utf8Path, Utf8PathBuf};
use cap_std::{
    ambient_authority,
    fs::{Permissions, PermissionsExt},
    fs_utf8::Dir,
};

/// Shorthand for the fallible reads the route tests perform.
pub type Read<T> = Result<T, Box<dyn Error>>;

/// Keeps probe directories from colliding across threads in one process.
static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

/// Owns a fake Cargo executable and records only its build invocations.
pub struct CargoProbe {
    parent: Dir,
    /// The probe directory, holding `cargo.log` and the fake tools.
    pub directory: Dir,
    name: String,
    /// The probe directory's path, for interpolating `CARGO=` arguments.
    pub path: Utf8PathBuf,
}

/// The independent Make branches exercised by one fake-Cargo invocation.
#[derive(Clone, Copy)]
pub struct MakeOptions<'a> {
    /// Whether the probe should report Nextest as unavailable.
    pub nextest_available: bool,
    /// Whether to run Make with `-n`.
    pub dry_run: bool,
    /// The value Make receives as `WITH_ACT`.
    pub with_act: bool,
    /// The executable Make runs as its build-tool preflight.
    pub check: &'a str,
}

impl CargoProbe {
    /// Creates an isolated probe directory with `probe-cargo` and `preflight`.
    ///
    /// `NEXTEST_AVAILABLE` is inverted on purpose: the Makefile probes with
    /// `cargo nextest --version` and treats success as "Nextest is present", so
    /// the script must exit non-zero to model an absent Nextest. The caller
    /// sets the variable to state which world it wants.
    pub fn new() -> Read<Self> {
        let parent_path = Utf8PathBuf::from_path_buf(std::env::temp_dir())
            .map_err(|path| io::Error::other(format!("non-UTF-8 temp path: {}", path.display())))?;
        let parent = Dir::open_ambient_dir(&parent_path, ambient_authority())?;
        let name = format!(
            "combobulate-cargo-probe-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        );
        parent.create_dir(&name)?;
        let directory = parent.open_dir(&name)?;
        directory.write(
            "probe-cargo",
            concat!(
                "#!/bin/sh\nif [ \"$1\" = nextest ] && [ \"$2\" = --version ]; then\n  if [ ",
                "\"${NEXTEST_AVAILABLE:-0}\" = 0 ]; then printf '%s\\n' 'cargo-nextest 0.9.0'; \
                 exit ",
                "0; fi\n  exit 1\nfi\nprintf '%s\\n' \"$*\" >> \"$CARGO_LOG\"\nif [ -n ",
                "\"${PRODUCTION_LOG:-}\" ]; then env | sort > \"$PRODUCTION_LOG\"; fi\n",
            ),
        )?;
        directory.set_permissions("probe-cargo", Permissions::from_mode(0o700))?;
        directory.write(
            "preflight",
            "#!/bin/sh\nprintf '%s\\n' preflight >> \"$CARGO_LOG\"\n",
        )?;
        directory.set_permissions("preflight", Permissions::from_mode(0o700))?;
        directory.write(
            "probe-python",
            "#!/bin/sh\nprintf '%s\\n' \"probe-python $*\" >> \"$CARGO_LOG\"\n",
        )?;
        directory.set_permissions("probe-python", Permissions::from_mode(0o700))?;
        Ok(Self {
            parent,
            directory,
            path: parent_path.join(&name),
            name,
        })
    }

    /// Runs one Make target with this probe standing in for Cargo.
    pub fn make(&self, target: &str, options: MakeOptions<'_>) -> io::Result<std::process::Output> {
        let mut command = Command::new("make");
        if options.dry_run {
            command.arg("-n");
        }
        command.arg("-B");
        command
            .arg(target)
            .arg(format!("CARGO={}", self.path.join("probe-cargo")))
            .arg(format!("PYTHON={}", self.path.join("probe-python")))
            .arg(format!("CHECK_BUILD_TOOLS={}", options.check))
            .arg("WHITAKER=true")
            .arg(format!("WITH_ACT={}", u8::from(options.with_act)))
            .current_dir(Utf8Path::new(env!("CARGO_MANIFEST_DIR")))
            .env(
                "NEXTEST_AVAILABLE",
                if options.nextest_available { "0" } else { "1" },
            )
            .env("CARGO_LOG", self.path.join("cargo.log").as_str())
            .output()
    }
}

impl Drop for CargoProbe {
    fn drop(&mut self) { drop(self.parent.remove_dir_all(&self.name)); }
}

/// Reads the probe's printed commands, rejecting a failed Make invocation.
///
/// The output is Make's own `-n` rendering rather than an executed call, so it
/// shows what the recipe would run without running it.
pub fn dry_run(probe: &CargoProbe, target: &str, nextest: bool, with_act: bool) -> Read<String> {
    let output = probe.make(
        target,
        MakeOptions {
            nextest_available: nextest,
            dry_run: true,
            with_act,
            check: "scripts/check-build-tools.sh",
        },
    )?;
    if !output.status.success() {
        return Err(format!(
            "make -n {target} failed: {}",
            String::from_utf8_lossy(&output.stderr)
        )
        .into());
    }
    Ok(String::from_utf8(output.stdout)?)
}

/// Detects an executable bare Cargo token rather than a printed diagnostic.
///
/// Make echoes some recipes through `printf` or `echo`; those lines mention
/// `cargo` as data. Only an unquoted leading or embedded `cargo` token is a
/// real invocation.
pub fn has_bare_cargo(commands: &str) -> bool {
    commands.lines().any(|line| {
        let trimmed = line.trim_start();
        !trimmed.starts_with("printf ")
            && !trimmed.starts_with("echo ")
            && (trimmed.starts_with("cargo ") || trimmed.contains(" cargo "))
    })
}
