//! Behavioural contracts for the bare-Cargo native Clang linker wrapper.

#![cfg(all(target_os = "linux", target_arch = "x86_64"))]

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

type Read<T> = Result<T, Box<dyn Error>>;
static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

/// Opens the system temporary directory as a capability, returning it with its UTF-8 path.
fn open_temp_parent() -> Read<(Utf8PathBuf, Dir)> {
    let parent_path = Utf8PathBuf::from_path_buf(std::env::temp_dir())
        .map_err(|path| io::Error::other(format!("non-UTF-8 temp path: {}", path.display())))?;
    let parent = Dir::open_ambient_dir(&parent_path, ambient_authority())?;
    Ok((parent_path, parent))
}

/// Names a fixture directory uniquely within this process and across processes.
fn unique_fixture_name() -> String {
    format!(
        "combobulate-clang-wrapper-{}-{}",
        std::process::id(),
        NEXT_ID.fetch_add(1, Ordering::Relaxed)
    )
}

/// Writes the fake `mold`, `clang` and `rustup` executables into `directory`.
fn write_fake_tools(directory: &Dir) -> io::Result<()> {
    write_fake_mold(directory)?;
    write_fake_clang(directory)?;
    write_fake_rustup(directory)?;
    make_executable(directory, &["bin/mold", "clang", "rustup"])
}

/// Writes the fake `mold` linker and its `ld.mold` symlink.
fn write_fake_mold(directory: &Dir) -> io::Result<()> {
    directory.create_dir("bin")?;
    directory.write(
        "bin/mold",
        "#!/bin/sh\nprintf 'mold %s (compatible with GNU ld)\\n' \"$FAKE_MOLD_VERSION\"\n",
    )?;
    directory.symlink("mold", "bin/ld.mold")
}

/// Writes the fake `clang` that answers the linker probes and logs a real link.
fn write_fake_clang(directory: &Dir) -> io::Result<()> {
    directory.write(
        "clang",
        concat!(
            "#!/bin/sh\nselected=${FAKE_LINKER_PATH:-$BUILD_TOOLS_PREFIX/bin/ld.mold}\ncase \" $* ",
            "\" in\n  *' -print-prog-name=ld.mold '*) printf '%s\\n' \"$selected\" ;;\n  *' -### ",
            "'*) printf ' \"%s\" \"--hash-style=gnu\"\\n' \"$selected\" >&2 ;;\n  *) printf ",
            "'%s\\n' invoked > \"$LINKER_LOG\" ;;\nesac\n",
        ),
    )
}

/// Writes the fake `rustup` that reports the host triple.
fn write_fake_rustup(directory: &Dir) -> io::Result<()> {
    directory.write(
        "rustup",
        concat!(
            "#!/bin/sh\nif [ \"$1\" = show ]; then printf 'Default host: %s\\n' ",
            "\"$FAKE_HOST_TRIPLE\"; else exit 1; fi\n",
        ),
    )
}

/// Marks each named file in `directory` owner-executable.
fn make_executable(directory: &Dir, names: &[&str]) -> io::Result<()> {
    names
        .iter()
        .try_for_each(|name| directory.set_permissions(name, Permissions::from_mode(0o700)))
}

/// Owns a private Clang search path and records whether its linker was reached.
struct LinkerFixture {
    parent: Dir,
    directory: Dir,
    name: String,
    path: Utf8PathBuf,
}

/// Inputs that distinguish a supported link from an unsupported fallback.
struct LinkerSetting<'a> {
    version: &'a str,
    host: &'a str,
    selected: Option<&'a str>,
    requests_mold: bool,
}

impl LinkerFixture {
    fn new() -> Read<Self> {
        let (parent_path, parent) = open_temp_parent()?;
        let name = unique_fixture_name();
        parent.create_dir(&name)?;
        let directory = parent.open_dir(&name)?;
        write_fake_tools(&directory)?;
        Ok(Self {
            parent,
            directory,
            path: parent_path.join(&name),
            name,
        })
    }

    fn invoke(&self, setting: &LinkerSetting<'_>) -> io::Result<Output> {
        let root = Utf8Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut command = Command::new(root.join("scripts/native-clang-linker.sh"));
        if setting.requests_mold {
            command.arg("-fuse-ld=mold");
        }
        command
            .env("BUILD_TOOLS_PREFIX", self.path.as_str())
            .env("CLANG_COMMAND", self.path.join("clang").as_str())
            .env("PATH", format!("{}:/usr/bin:/bin", self.path))
            .env("FAKE_MOLD_VERSION", setting.version)
            .env("FAKE_HOST_TRIPLE", setting.host)
            .env("LINKER_LOG", self.path.join("linker.log").as_str());
        match setting.selected {
            Some(path) => {
                command.env("FAKE_LINKER_PATH", path);
            }
            None => {
                command.env_remove("FAKE_LINKER_PATH");
            }
        }
        command.output()
    }
}

impl Drop for LinkerFixture {
    fn drop(&mut self) { drop(self.parent.remove_dir_all(&self.name)); }
}

#[test]
fn bare_cargo_wrapper_uses_only_the_pinned_native_linker() {
    let fixture = LinkerFixture::new().expect("create a private native linker route");
    let supported = LinkerSetting {
        version: "2.41.0",
        host: "x86_64-unknown-linux-gnu",
        selected: None,
        requests_mold: true,
    };
    let output = fixture
        .invoke(&supported)
        .expect("invoke the native wrapper");
    assert!(
        output.status.success(),
        "a pinned native linker must run: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        output.stderr.is_empty(),
        "a successful linker must not emit stderr that rustc reports as linker_messages: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        fixture.directory.exists("linker.log"),
        "the validated Clang route must execute after verification"
    );
}

#[test]
fn bare_cargo_wrapper_refuses_diverted_and_wrong_version_linkers() {
    for (version, host, diverted, diagnostic) in [
        (
            "2.40.4",
            "x86_64-unknown-linux-gnu",
            false,
            "does not match",
        ),
        (
            "2.41.0",
            "x86_64-unknown-linux-musl",
            false,
            "requires a native",
        ),
        ("2.41.0", "x86_64-unknown-linux-gnu", true, "not pinned"),
    ] {
        let fixture = LinkerFixture::new().expect("create an isolated negative linker route");
        fixture
            .directory
            .write("other-ld.mold", "#!/bin/sh\nexit 0\n")
            .expect("create an alternate linker target");
        let other = fixture.path.join("other-ld.mold");
        let setting = LinkerSetting {
            version,
            host,
            selected: diverted.then_some(other.as_str()),
            requests_mold: true,
        };
        let output = fixture
            .invoke(&setting)
            .expect("invoke a rejected native route");
        assert!(
            !output.status.success(),
            "invalid linker version={version}, host={host}, diverted={diverted} must fail"
        );
        assert!(
            String::from_utf8_lossy(&output.stderr).contains(diagnostic),
            "a rejected native route needs guidance: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert!(
            !fixture.directory.exists("linker.log"),
            "Clang must not run after a rejected linker route"
        );
    }
}

#[test]
fn bare_cargo_wrapper_refuses_a_missing_pinned_linker() {
    let fixture = LinkerFixture::new().expect("create a missing-linker route");
    fixture
        .directory
        .remove_file("bin/ld.mold")
        .expect("remove the pinned linker alias");
    let missing = LinkerSetting {
        version: "2.41.0",
        host: "x86_64-unknown-linux-gnu",
        selected: None,
        requests_mold: true,
    };
    let output = fixture
        .invoke(&missing)
        .expect("invoke the missing-linker route");
    assert!(
        !output.status.success(),
        "the wrapper must refuse a missing pinned linker"
    );
    assert!(
        String::from_utf8_lossy(&output.stderr).contains("missing or not executable"),
        "a missing pinned linker needs an install hint: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        !fixture.directory.exists("linker.log"),
        "Clang must not fall through to a system linker"
    );
}

#[test]
fn release_link_without_mold_does_not_require_its_pin() {
    let fixture = LinkerFixture::new().expect("create a release linker route");
    fixture
        .directory
        .remove_file("bin/ld.mold")
        .expect("remove development-only mold from the fixture");
    let release = LinkerSetting {
        version: "2.41.0",
        host: "x86_64-unknown-linux-gnu",
        selected: None,
        requests_mold: false,
    };
    let output = fixture
        .invoke(&release)
        .expect("invoke a release linker route");
    assert!(
        output.status.success(),
        "a release link must not require mold: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        fixture.directory.exists("linker.log"),
        "Clang must receive the release link without a mold check"
    );
}
