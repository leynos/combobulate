//! Hermetic installer and Act archive-verification subprocess regressions.

#![cfg(target_os = "linux")]

#[path = "support/build_tools_installer.rs"]
mod support;

use std::error::Error;

use camino::Utf8Path;
use rstest::{fixture, rstest};
use serde_yaml::Value;
use support::{ARCHIVE_NAME, ARCHIVE_SHA256, InstallerFixture};

/// Fallible setup avoids panics outside a test function.
type FixtureResult = Result<InstallerFixture, Box<dyn Error>>;

/// A private installation prefix, fake host and offline command executors.
#[fixture]
fn installer() -> FixtureResult {
    let prepared = InstallerFixture::new()?;
    Ok(prepared)
}

/// A supported host verifies bytes before extraction and installs every pinned component.
#[rstest]
fn supported_host_installs_exact_pins_and_cleans_scratch(installer: FixtureResult) {
    let fixture = installer.expect("create offline installer fixture");
    let output = fixture
        .install(&[])
        .expect("run real installer with fake executors");
    assert!(
        output.status.success(),
        "supported installation must pass: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let curl = fixture
        .arguments("curl")
        .expect("read downloader argv")
        .expect("download must execute");
    let archive = curl.get(11).expect("curl must receive an output path");
    assert!(
        Utf8Path::new(archive).starts_with(fixture.path.join("scratch'quoted")),
        "the archive must stay in the private scratch directory"
    );
    assert_eq!(
        curl,
        vec![
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            "7",
            "--speed-limit",
            "321",
            "--speed-time",
            "9",
            "--output",
            archive,
            "https://fixture.invalid/mold/v9.8.7/mold-9.8.7-x86_64-linux.tar.gz",
        ],
        "the installer must retain download bounds and the exact fixture pin"
    );
    let prefix = fixture.path.join("prefix");
    assert_eq!(
        fixture.arguments("tar").expect("read extraction argv"),
        Some(vec![
            "--extract".to_owned(),
            "--gzip".to_owned(),
            "--strip-components=1".to_owned(),
            "--directory".to_owned(),
            prefix.to_string(),
            "--file".to_owned(),
            archive.clone(),
        ]),
        "extraction must use the verified archive and configured prefix"
    );
    assert_toolchain_arguments(&fixture);
    assert_eq!(
        fixture.scratch_entries().expect("read child scratch"),
        0,
        "the EXIT trap must remove quote-bearing scratch paths"
    );
}

/// Download, extraction and toolchain failures stop at their failing executor.
#[rstest]
#[case::download("CURL_FAIL", "failed to download", &["curl"])]
#[case::extraction("TAR_FAIL", "failed to unpack", &["curl", "tar"])]
#[case::toolchain("RUSTUP_FAIL", "failed to install toolchain", &["curl", "tar", "rustup"])]
fn failed_installation_stops_and_cleans_scratch(
    installer: FixtureResult,
    #[case] failure: &str,
    #[case] diagnostic: &str,
    #[case] invoked: &[&str],
) {
    let fixture = installer.expect("create offline installer fixture");
    let output = fixture
        .install(&[(failure, "1")])
        .expect("run failing installer");
    assert!(!output.status.success(), "{failure} must fail installation");
    assert!(
        String::from_utf8_lossy(&output.stderr).contains(diagnostic),
        "failure must explain {diagnostic}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    for executor in ["curl", "tar", "rustup"] {
        assert_eq!(
            fixture
                .arguments(executor)
                .expect("read executor argv")
                .is_some(),
            invoked.contains(&executor),
            "{failure} must stop at the correct executor: {executor}"
        );
    }
    assert_eq!(
        fixture.scratch_entries().expect("read child scratch"),
        0,
        "failure must clean all temporary downloads"
    );
}

/// Missing, ambiguous and incorrect checksum manifests fail before archive execution.
#[rstest]
#[case::missing(String::new(), "no checksum recorded")]
#[case::duplicate(format!("{ARCHIVE_SHA256}  {ARCHIVE_NAME}\n{ARCHIVE_SHA256}  {ARCHIVE_NAME}\n"), "2 checksums recorded")]
#[case::mismatched(format!("{}  {ARCHIVE_NAME}\n", "0".repeat(64)), "checksum mismatch")]
fn rejected_checksums_stop_before_extraction_and_toolchain(
    installer: FixtureResult,
    #[case] checksums: String,
    #[case] diagnostic: &str,
) {
    let fixture = installer.expect("create offline installer fixture");
    fixture
        .checksums(&checksums)
        .expect("write checksum fixture");
    let output = fixture.install(&[]).expect("run checksum rejection case");
    assert!(!output.status.success(), "{diagnostic} must fail closed");
    assert!(
        String::from_utf8_lossy(&output.stderr).contains(diagnostic),
        "checksum failure must explain {diagnostic}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    for executor in ["tar", "rustup"] {
        assert_eq!(
            fixture.arguments(executor).expect("read executor argv"),
            None,
            "checksum failure must stop before {executor}"
        );
    }
    assert_eq!(
        fixture.scratch_entries().expect("read child scratch"),
        0,
        "checksum rejection must clean the archive"
    );
}

/// Real checksum verification detects tampering of otherwise correctly pinned downloads.
#[rstest]
fn corrupted_download_stops_before_archive_execution(installer: FixtureResult) {
    let fixture = installer.expect("create offline installer fixture");
    let output = fixture
        .install(&[("CURL_CORRUPT", "1")])
        .expect("run corrupted download");
    assert!(
        !output.status.success(),
        "changed archive bytes must fail verification"
    );
    assert!(
        String::from_utf8_lossy(&output.stderr).contains("checksum mismatch"),
        "tampering must produce a checksum diagnostic"
    );
    assert_eq!(
        fixture.arguments("tar").expect("read tar argv"),
        None,
        "unverified bytes must never reach extraction"
    );
    assert_eq!(
        fixture.arguments("rustup").expect("read rustup argv"),
        None,
        "checksum failure must precede toolchain installation"
    );
    assert_eq!(
        fixture.scratch_entries().expect("read child scratch"),
        0,
        "tampered downloads must still be cleaned"
    );
}

/// Every unsupported host dimension skips mold while still installing the toolchain.
#[rstest]
#[case::os("FAKE_HOST_OS", "Darwin")]
#[case::architecture("FAKE_HOST_ARCH", "aarch64")]
#[case::abi("FAKE_HOST_TRIPLE", "x86_64-unknown-linux-musl")]
fn unsupported_hosts_skip_mold(
    installer: FixtureResult,
    #[case] variable: &str,
    #[case] value: &str,
) {
    let fixture = installer.expect("create offline installer fixture");
    let output = fixture
        .install(&[(variable, value)])
        .expect("run unsupported host case");
    assert!(
        output.status.success(),
        "unsupported mold hosts must still install the toolchain: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    for executor in ["curl", "tar"] {
        assert_eq!(
            fixture.arguments(executor).expect("read executor argv"),
            None,
            "unsupported hosts must skip {executor}"
        );
    }
    assert_toolchain_arguments(&fixture);
    assert_eq!(
        fixture.scratch_entries().expect("read child scratch"),
        0,
        "skipped mold must leave no scratch directories"
    );
}

/// Configured components reach rustup exactly and in pin-file order.
fn assert_toolchain_arguments(fixture: &InstallerFixture) {
    assert_eq!(
        fixture.arguments("rustup").ok().flatten(),
        Some(vec![
            "toolchain".to_owned(),
            "install".to_owned(),
            "nightly-2001-02-03".to_owned(),
            "--profile".to_owned(),
            "minimal".to_owned(),
            "--component".to_owned(),
            "clippy".to_owned(),
            "--component".to_owned(),
            "rustfmt".to_owned(),
        ]),
        "the installer must pass the exact pinned toolchain, profile and components"
    );
}

/// The committed Act script extracts only successfully verified archives.
#[rstest]
#[case::verified(&[], true)]
#[case::corrupted(&[("CURL_CORRUPT", "1")], false)]
#[case::download_failure(&[("CURL_FAIL", "1")], false)]
fn act_archive_is_verified_before_privileged_extraction(
    installer: FixtureResult,
    #[case] overrides: &[(&str, &str)],
    #[case] succeeds: bool,
) {
    let fixture = installer.expect("create offline installer fixture");
    let workflow: Value =
        serde_yaml::from_str(include_str!("../.github/workflows/act-validation.yml"))
            .expect("parse committed Act workflow");
    let step = workflow
        .get("jobs")
        .and_then(|jobs| jobs.get("act-validation"))
        .and_then(|job| job.get("steps"))
        .and_then(Value::as_sequence)
        .and_then(|steps| {
            steps
                .iter()
                .find(|step| step.get("name").and_then(Value::as_str) == Some("Install act"))
        })
        .expect("the manual workflow must install Act");
    let digest = step
        .get("env")
        .and_then(|env| env.get("ACT_SHA256"))
        .and_then(Value::as_str)
        .expect("the Act archive digest must be pinned");
    assert_eq!(digest.len(), 64, "Act must pin a complete SHA-256 digest");
    assert!(
        digest
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f')),
        "the archive pin must contain only lowercase hex digits"
    );
    let script = step
        .get("run")
        .and_then(Value::as_str)
        .expect("Act installation must have a shell script");
    let output = fixture
        .workflow_script(script, overrides)
        .expect("run the committed Act installer script");
    assert_eq!(
        output.status.success(),
        succeeds,
        "Act installation result must reflect archive verification: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        fixture.arguments("tar").expect("read tar argv").is_some(),
        succeeds,
        "only a verified archive may reach sudo tar"
    );
    assert_eq!(
        fixture.scratch_entries().expect("read child scratch"),
        0,
        "Act installation must clean downloaded archives on success and failure"
    );
}
