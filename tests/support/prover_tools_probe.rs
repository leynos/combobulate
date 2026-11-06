//! Capability-scoped Make fixture with a recording prover executable.

use std::{
    io,
    process::{Command, Output},
    sync::atomic::{AtomicUsize, Ordering},
};

use camino::Utf8PathBuf;
use cap_std::{
    ambient_authority,
    fs::{Permissions, PermissionsExt},
    fs_utf8::Dir,
};

/// Distinguishes private directories created concurrently within one test binary.
static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

/// The SDK toolchain the fake Kani release reports it was built from.
///
/// A real release records this beside its driver, and the probe reads it to
/// select the bundled LLVM toolchain instead of assuming the constant. The
/// probe rejects a release whose record names a different nightly, so the
/// fixture has to stage the value the pinned release actually ships. It
/// mirrors `KANI_SDK_TOOLCHAIN` in `scripts/verifier_probe_support.py`; that
/// test asserts the prefix, the Rust fixture supplies the target triple a real
/// record carries.
const KANI_SDK_TOOLCHAIN: &str = "nightly-2025-11-21-x86_64-unknown-linux-gnu";

/// A private Makefile, pin, and executable permit shell-boundary observations.
pub(super) struct ProverProbe {
    /// Capability used to clean up only this fixture.
    parent: Dir,
    /// Directory containing the recording fake and its log.
    directory: Dir,
    /// Fixture component beneath the temporary directory.
    name: String,
    /// Absolute path used by child commands.
    path: Utf8PathBuf,
}

impl ProverProbe {
    /// Creates an isolated Make working directory without copying build artefacts.
    pub(super) fn new() -> io::Result<Self> {
        let path = Utf8PathBuf::from_path_buf(std::env::temp_dir())
            .map_err(|_| io::Error::other("the fixture temp path must be UTF-8"))?;
        let parent = Dir::open_ambient_dir(&path, ambient_authority())?;
        let name = format!(
            "combobulate-prover-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        );
        parent.create_dir(&name)?;
        let directory = parent.open_dir(&name)?;
        let repository = Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())?;
        copy_repository_pins(&directory, &repository)?;
        directory.write("prover", PROVER_SCRIPT)?;
        directory.set_permissions("prover", Permissions::from_mode(0o755))?;
        directory.write(
            "z3",
            "#!/bin/bash\nprintf 'Z3 version 4.16.0 - 64 bit\\n'\n",
        )?;
        directory.set_permissions("z3", Permissions::from_mode(0o755))?;
        directory.create_dir("bin")?;
        for executable_name in ["bin/kani-driver", "cargo-verus"] {
            directory.write(executable_name, directory.read("prover")?)?;
            directory.set_permissions(executable_name, Permissions::from_mode(0o755))?;
        }
        // A real release records the SDK it bundled; the probe reads this to
        // select that toolchain rather than assuming it.
        directory.write("rust-toolchain-version", format!("{KANI_SDK_TOOLCHAIN}\n"))?;
        Ok(Self {
            parent,
            directory,
            name: name.clone(),
            path: path.join(name),
        })
    }
}

/// Copies the pinned manifests every probe target parses before execution.
fn copy_repository_pins(directory: &Dir, repository: &Dir) -> io::Result<()> {
    directory.write("Makefile", repository.read("Makefile")?)?;
    directory.create_dir_all("tools/rust-prover-tools")?;
    directory.create_dir_all("tools/kani")?;
    directory.write(
        "tools/rust-prover-tools/REF",
        repository.read("tools/rust-prover-tools/REF")?,
    )?;
    directory.write("tools/kani/VERSION", "0.67.0\n")
}

/// A recording prover whose answers are selected by the forwarded arguments.
const PROVER_SCRIPT: &str = concat!(
    "#!/bin/bash\n",
    "printf '%s\\0' \"$@\" >> \"$PROVER_LOG\"\n",
    "printf '\\n' >> \"$PROVER_LOG\"\n",
    "printf 'recording prover fixture\\n'\n",
    "if [ \"${PROVER_EXECUTION_EXIT:-0}\" != 0 ] && ",
    "[ \"${2-}\" != check-version ] && [ \"${2-}\" != --version ]; ",
    "then exit \"$PROVER_EXECUTION_EXIT\"; fi\n",
    "if [ \"${PROVER_EXIT:-0}\" != 0 ]; then exit \"$PROVER_EXIT\"; fi\n",
    "case \"$*\" in\n",
    "  *--version*) printf 'Kani Rust Verifier 0.67.0\\n' ;;\n",
    "  *--verify-function=mutant*) ",
    "src=; previous=; ",
    "for argument in \"$@\"; do ",
    "if [ \"$previous\" = --manifest-path ]; then ",
    "source_dir=\"$(dirname \"$argument\")\"; ",
    "src=\"$source_dir/../$(basename \"$source_dir\").rs\"; fi; ",
    "if [ \"$previous\" = --proof-file ]; then src=\"$argument\"; fi; ",
    "previous=\"$argument\"; done; ",
    "line=1; if [ -n \"$src\" ]; then ",
    "line=\"$(grep -n 'fn mutant' \"$src\" | head -n 1 | cut -d: -f1)\"; ",
    "[ -n \"$line\" ] || line=1; fi; ",
    "case \"${PROVER_MUTANT_LOCATION:-located}\" in ",
    "missing) printf 'error: postcondition not satisfied\\n' ;; ",
    "outside) printf 'error: postcondition not satisfied\\n  --> %s:1:13\\n' ",
    "\"$src\" ;; ",
    "*) printf 'error: postcondition not satisfied\\n  --> %s:%s:13\\n' ",
    "\"$src\" \"$line\" ;; ",
    "esac; printf 'verification results:: 0 verified, 1 errors\\n'; exit 1 ;;\n",
    "  *--verify-function=increment*) ",
    "printf 'note: verifying module production (selected functions)\\n'; ",
    "printf 'verification results:: 1 verified, 0 errors\\n' ;;\n",
    "  *--verify-function=capability*) ",
    "printf 'verification results:: 1 verified, 0 errors\\n' ;;\n",
    "  *--harness-timeout*) printf 'CBMC timed out\\n'; exit 1 ;;\n",
    "  *harnesses::multiplication_timeout*) sleep 9 ;;\n",
    "  *harnesses::counterexample*|*harnesses::insufficient_unwind*|",
    "*harnesses::unsupported*|*harnesses::seeded_wrapping_mutant*) exit 1 ;;\n",
    "  *) printf 'recording prover fixture\\n' ;;\n",
    "esac\n",
);

impl ProverProbe {
    /// Constructs a real Make command with child-only recording variables.
    pub(super) fn command(&self, target: &str) -> Command {
        let mut command = Command::new("make");
        command
            .args(["--no-print-directory", target])
            .current_dir(&self.path)
            .env("PROVER_LOG", self.path.join("calls").as_str());
        command
    }

    /// Enables the explicitly paired command-line substitution seam.
    pub(super) fn run(&self, target: &str, strict: bool, failure: bool) -> io::Result<Output> {
        self.command(target)
            .arg("PROVER_TOOLS_CONTRACT_TEST=1")
            .arg(format!("PROVER_TOOLS={}", self.path.join("prover")))
            .arg(format!("FORMAL_STRICT={}", u8::from(strict)))
            .env("PROVER_EXIT", if failure { "19" } else { "0" })
            .output()
    }

    /// Builds the probe invocation shared by the success and diagnostic cases.
    fn probe_command(&self, target: &str, failure: bool) -> Command {
        let mut command = self.command(target);
        command
            .current_dir(env!("CARGO_MANIFEST_DIR"))
            .arg("PROVER_TOOLS_CONTRACT_TEST=1")
            .arg(format!("PROVER_TOOLS={}", self.path.join("prover")))
            .arg(format!("KANI_INSTALLATION={}", self.path))
            .arg(format!(
                "KANI_FLAGS=--output-dir {}",
                self.path.join("output")
            ))
            .arg(format!(
                "VERUS_FLAGS=--output-dir {} --verus-installation {} --z3 {}",
                self.path.join("output"),
                self.path,
                self.path.join("z3")
            ))
            .env("PROVER_EXIT", "0")
            .env("PROVER_EXECUTION_EXIT", if failure { "19" } else { "0" });
        command
    }

    /// Runs actual probe orchestration with fake pinned executables and private outputs.
    pub(super) fn run_probe(&self, target: &str, failure: bool) -> io::Result<Output> {
        self.probe_command(target, failure).output()
    }

    /// Runs the probe with a chosen mutant diagnostic shape.
    pub(super) fn run_probe_with_diagnostic(
        &self,
        target: &str,
        location: &str,
    ) -> io::Result<Output> {
        self.probe_command(target, false)
            .env("PROVER_MUTANT_LOCATION", location)
            .output()
    }

    /// Sets optional count inflation, restoring the original fake when absent.
    pub(super) fn set_count_inflation(&self, count: Option<&str>) -> io::Result<()> {
        let mut script = self.directory.read_to_string("bin/kani-driver")?;
        if let Some(summary) = count {
            script = script.replace(summary, &format!("1{summary}"));
        }
        for executable in ["prover", "cargo-verus"] {
            self.directory.write(executable, &script)?;
        }
        Ok(())
    }

    /// Decodes newline-delimited, NUL-framed fake invocations.
    pub(super) fn calls(&self) -> io::Result<Vec<Vec<String>>> {
        Ok(self
            .directory
            .read_to_string("calls")?
            .lines()
            .map(|line| line.split_terminator('\0').map(str::to_owned).collect())
            .collect())
    }

    /// Corrupts only this fixture's pin to test fail-closed Make parsing.
    pub(super) fn invalidate_pin(&self) -> io::Result<()> {
        self.directory
            .write("tools/rust-prover-tools/REF", "ref: malformed\n")
    }

    /// Supplies the fake through the environment to exercise the locked boundary.
    pub(super) fn environment_only(&self) -> io::Result<Output> {
        self.command("install-kani")
            .arg("--dry-run")
            .env("PROVER_TOOLS_CONTRACT_TEST", "1")
            .env("PROVER_TOOLS", self.path.join("prover").as_str())
            .output()
    }
}

impl Drop for ProverProbe {
    /// Best-effort cleanup cannot propagate errors from Drop.
    fn drop(&mut self) { drop(self.parent.remove_dir_all(&self.name)); }
}
