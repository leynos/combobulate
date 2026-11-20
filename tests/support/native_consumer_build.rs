//! Reading Cargo's JSON message stream for the consumer fixture's binaries.
//!
//! The fixture has more than one binary target, so one build names several
//! executables and their order is Cargo's business. Selecting by target name is
//! therefore the only stable way to find the one a test means: a positional
//! choice would quietly run the wrong program after a target is added. The
//! executable path itself still comes from Cargo's message rather than a
//! literal `debug/<name>`, which would stop matching under a custom profile and
//! would omit the platform's `.exe` suffix.

use std::{error::Error, path::PathBuf};

use serde_json::Value;

/// Finds the executable of the binary target named `target`.
///
/// ```text
/// binary_named(stream, "ordinary_application")
/// // the executable Cargo reported for that target, whatever its position
/// ```
pub(super) fn binary_named(stream: &str, target: &str) -> Result<PathBuf, Box<dyn Error>> {
    let executable = stream
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter(|message| is_binary_artifact(message, target))
        .find_map(|message| {
            message
                .get("executable")
                .and_then(Value::as_str)
                .map(str::to_owned)
        })
        .ok_or_else(|| format!("Cargo reported no executable for the binary target {target}"))?;
    Ok(PathBuf::from(executable))
}

/// Reports whether a Cargo JSON message describes the named binary target.
///
/// `pointer` is used rather than `Value`'s index operator because a message
/// whose shape is not the one Cargo documents must simply stop matching, not
/// panic or reach for a key that only some artifact kinds carry. The target
/// name is checked as well as the kind: an artifact for another binary in the
/// same build carries an executable too.
fn is_binary_artifact(message: &Value, target: &str) -> bool {
    let is_artifact = message.get("reason").and_then(Value::as_str) == Some("compiler-artifact");
    let is_named = message
        .pointer("/target/name")
        .and_then(Value::as_str)
        .is_some_and(|name| name == target);
    let is_bin = message
        .pointer("/target/kind")
        .and_then(Value::as_array)
        .is_some_and(|kinds| kinds.iter().any(|kind| kind.as_str() == Some("bin")));
    is_artifact && is_named && is_bin
}

#[cfg(test)]
mod tests {
    //! Lookup contracts for a stream that names more than one binary.
    //!
    //! Cargo may report the fixture's targets in any order and interleaves
    //! library artifacts, so each name is pinned against both orders: a lookup
    //! that took the first binary in the stream would pass one ordering and
    //! silently run the wrong program under the other.

    use std::path::Path;

    use rstest::rstest;

    use super::binary_named;

    /// A library artifact, a binary, and a second binary, in that order.
    const DEFAULT_FIRST: &str = concat!(
        r#"{"reason":"compiler-artifact","target":{"kind":["lib"],"name":"combobulate"},"#,
        r#""executable":null}"#,
        "\n",
        r#"{"reason":"compiler-artifact","target":{"kind":["bin"],"name":"native-consumer"},"#,
        r#""executable":"/tmp/target/debug/native-consumer"}"#,
        "\n",
        r#"{"reason":"compiler-artifact","target":{"kind":["bin"],"name":"ordinary_application"},"#,
        r#""executable":"/tmp/target/debug/ordinary_application"}"#,
        "\n"
    );

    /// The same artifacts with the two binaries in the other order.
    const ORDINARY_FIRST: &str = concat!(
        r#"{"reason":"compiler-artifact","target":{"kind":["bin"],"name":"ordinary_application"},"#,
        r#""executable":"/tmp/target/debug/ordinary_application"}"#,
        "\n",
        r#"{"reason":"compiler-artifact","target":{"kind":["bin"],"name":"native-consumer"},"#,
        r#""executable":"/tmp/target/debug/native-consumer"}"#,
        "\n"
    );

    /// Each name finds its own executable whichever order Cargo used.
    #[rstest]
    #[case::default_second(
        DEFAULT_FIRST,
        "ordinary_application",
        "/tmp/target/debug/ordinary_application"
    )]
    #[case::default_first(DEFAULT_FIRST, "native-consumer", "/tmp/target/debug/native-consumer")]
    #[case::ordinary_first(
        ORDINARY_FIRST,
        "ordinary_application",
        "/tmp/target/debug/ordinary_application"
    )]
    #[case::ordinary_only_binary(
        ORDINARY_FIRST,
        "native-consumer",
        "/tmp/target/debug/native-consumer"
    )]
    fn two_binaries_are_selected_by_target_name(
        #[case] stream: &str,
        #[case] target: &str,
        #[case] expected: &str,
    ) {
        assert_eq!(
            binary_named(stream, target).as_deref().ok(),
            Some(Path::new(expected)),
            "the {target} target must resolve to its own executable"
        );
    }

    /// A stream that names no such binary target is an error, not a guess.
    #[test]
    fn a_stream_without_the_named_binary_is_reported() {
        let absent = binary_named(DEFAULT_FIRST, "absent-binary").expect_err(
            "a stream with no such bin target must report the missing executable rather than guess",
        );
        assert!(
            absent.to_string().contains("absent-binary"),
            "the report must name the target it lacked, got {absent}"
        );
    }
}
