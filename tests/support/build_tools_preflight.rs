//! Fake pinned build tools used by the preflight integration tests.

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

/// Reads the pinned toolchain channel from `rust-toolchain.toml`.
pub(super) fn pinned_channel() -> Read<String> {
    let root = Dir::open_ambient_dir(
        Utf8Path::new(env!("CARGO_MANIFEST_DIR")),
        ambient_authority(),
    )?;
    let document: toml::Value = toml::from_str(&root.read_to_string("rust-toolchain.toml")?)?;
    let channel = document
        .get("toolchain")
        .and_then(|toolchain| toolchain.get("channel"))
        .and_then(toml::Value::as_str)
        .ok_or("toolchain channel must be a string")?;
    Ok(channel.to_owned())
}

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
        "combobulate-build-tools-{}-{}",
        std::process::id(),
        NEXT_ID.fetch_add(1, Ordering::Relaxed)
    )
}

/// Writes the fake `rustup` and the toolchain list it prints, then marks it executable.
fn write_rustup_stub(directory: &Dir) -> Read<()> {
    directory.write(
        "rustup",
        "#!/bin/sh\ncase \"$1 $2\" in\n  'toolchain list') cat \"$FAKE_TOOLCHAINS\" ;;\n  \
         'component list') cat \"$FAKE_COMPONENTS\" ;;\n  'show ') printf '%s\\n' 'Default host: \
         x86_64-unknown-linux-gnu' ;;\n  *) exit 1 ;;\nesac\n",
    )?;
    directory.write(
        "toolchains",
        format!("{}-x86_64-unknown-linux-gnu (default)\n", pinned_channel()?),
    )?;
    Ok(directory.set_permissions("rustup", Permissions::from_mode(0o700))?)
}

/// Writes the fake `mold`, `clang` and `ld.lld`, and marks them executable.
fn write_linker_stubs(directory: &Dir) -> io::Result<()> {
    directory.create_dir("bin")?;
    directory.write(
        "bin/mold",
        "#!/bin/sh\nprintf 'mold %s (compatible with GNU ld)\\n' \"$FAKE_MOLD_VERSION\"\n",
    )?;
    directory.symlink("mold", "bin/ld.mold")?;
    directory.write(
        "clang",
        "#!/bin/sh\nselected=${FAKE_LINKER_PATH:-$BUILD_TOOLS_PREFIX/bin/ld.mold}\ncase \" $* \" \
         in\n  *' -print-prog-name=ld.mold '*) printf '%s\\n' \"$selected\" ;;\n  *' -### '*) \
         printf ' \"%s\" \"--hash-style=gnu\"\\n' \"$selected\" >&2 ;;\n  *) exit 0 ;;\nesac\n",
    )?;
    directory.write("ld.lld", "#!/bin/sh\nexit 0\n")?;
    ["bin/mold", "clang", "ld.lld"]
        .iter()
        .try_for_each(|name| directory.set_permissions(name, Permissions::from_mode(0o700)))
}

/// Reads the pinned toolchain's component names from `rust-toolchain.toml`.
fn toolchain_components() -> Read<Vec<String>> {
    let root = Dir::open_ambient_dir(
        Utf8Path::new(env!("CARGO_MANIFEST_DIR")),
        ambient_authority(),
    )?;
    let source = root.read_to_string("rust-toolchain.toml")?;
    let document: toml::Value = toml::from_str(&source)?;
    let components = document
        .get("toolchain")
        .and_then(|toolchain| toolchain.get("components"))
        .and_then(toml::Value::as_array)
        .ok_or("toolchain components must be an array")?;
    Ok(components
        .iter()
        .filter_map(toml::Value::as_str)
        .map(str::to_owned)
        .collect())
}

/// Lists each component as `rustup component list` prints it, minus `omitted`.
fn component_listing(components: &[String], omitted: Option<&str>) -> String {
    components
        .iter()
        .filter(|component| Some(component.as_str()) != omitted)
        .map(|component| {
            let alias = component.strip_suffix("-preview").unwrap_or(component);
            [alias, "-x86_64-unknown-linux-gnu\n"].concat()
        })
        .collect()
}

/// Owns fake build tools in a private scratch directory.
pub(super) struct ToolFixture {
    parent: Dir,
    pub(super) directory: Dir,
    name: String,
    pub(super) path: Utf8PathBuf,
}

impl ToolFixture {
    pub(super) fn new() -> Read<Self> {
        let (parent_path, parent) = open_temp_parent()?;
        let name = unique_fixture_name();
        parent.create_dir(&name)?;
        let directory = parent.open_dir(&name)?;
        write_rustup_stub(&directory)?;
        write_linker_stubs(&directory)?;
        let fixture = Self {
            parent,
            directory,
            path: parent_path.join(&name),
            name,
        };
        fixture.write_components(None)?;
        Ok(fixture)
    }

    pub(super) fn write_components(&self, omitted: Option<&str>) -> Read<()> {
        let listing = component_listing(&toolchain_components()?, omitted);
        Ok(self.directory.write("components", listing)?)
    }

    pub(super) fn check(
        &self,
        coverage: bool,
        missing: Option<&str>,
        override_var: Option<(&str, &str)>,
    ) -> io::Result<Output> {
        let root = Utf8Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut command = Command::new("bash");
        command.arg(root.join("scripts/check-build-tools.sh"));
        if coverage {
            command.arg("--coverage");
        }
        command
            .env_clear()
            .env("PATH", format!("{}:/usr/bin:/bin", self.path))
            .env("FAKE_COMPONENTS", self.path.join("components").as_str())
            .env("FAKE_TOOLCHAINS", self.path.join("toolchains").as_str())
            .env("FAKE_MOLD_VERSION", "2.41.0")
            .env("BUILD_TOOLS_PREFIX", self.path.as_str())
            .env("CLANG_COMMAND", self.path.join("clang").as_str())
            .env("LLD_COMMAND", self.path.join("ld.lld").as_str());
        for variable in [
            "CARGO_PROFILE_DEV_CODEGEN_BACKEND",
            "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER",
            "CARGO_BUILD_TARGET",
            "CARGO_ENCODED_RUSTFLAGS",
        ] {
            command.env_remove(variable);
        }
        if let Some(variable) = missing {
            command.env(variable, "missing-build-tool");
        }
        if let Some((variable, value)) = override_var {
            command.env(variable, value);
        }
        command.output()
    }
}

impl Drop for ToolFixture {
    fn drop(&mut self) { drop(self.parent.remove_dir_all(&self.name)); }
}
