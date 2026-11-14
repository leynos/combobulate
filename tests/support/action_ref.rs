//! Shared action-path and immutable-reference checks for workflow contracts.

/// The shared action that provisions Rust in every workflow.
pub(crate) const SETUP_RUST_PATH: &str = "leynos/shared-actions/.github/actions/setup-rust";

/// Returns the action path before its trailing `@` reference, if any.
pub(crate) fn action_path(uses: &str) -> &str {
    uses.rsplit_once('@').map_or(uses, |(path, _)| path)
}

/// Requires a full lowercase hexadecimal commit reference, independently of its value.
pub(crate) fn is_sha_pinned(uses: &str) -> bool {
    uses.rsplit_once('@').is_some_and(|(_, reference)| {
        reference.len() == 40
            && reference
                .bytes()
                .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    })
}

/// Checks the expected action identity and an immutable commit-shaped reference.
pub(crate) fn matches_pinned_action(uses: &str, expected_path: &str) -> bool {
    action_path(uses) == expected_path && is_sha_pinned(uses)
}

/// Extracts the reference that immediately follows an action's `@`.
///
/// Quoting and YAML flow delimiters end the reference as surely as whitespace
/// does. `uses: "path@SHA"` must yield `SHA`, not `SHA"`, and
/// `{uses: path@SHA}` must yield `SHA`, not `SHA}`; otherwise the replacement
/// consumes the closing character and leaves unparsable YAML behind.
fn current_reference(suffix: &str) -> Option<&str> {
    let ends_reference = |character: char| {
        character.is_whitespace() || matches!(character, '"' | '\'' | '{' | '}' | '[' | ']' | ',')
    };
    suffix
        .split(ends_reference)
        .next()
        .filter(|reference| !reference.is_empty())
}

/// Returns the byte offset where a YAML comment starts, if the line has one.
///
/// A `#` opens a comment only at the start of a line or after whitespace, so a
/// scalar fragment such as `path@ref#suffix` is not truncated.
fn comment_start(line: &str) -> Option<usize> {
    line.char_indices()
        .find(|(index, character)| {
            *character == '#'
                && (*index == 0
                    || line
                        .get(..*index)
                        .is_some_and(|prefix| prefix.ends_with(char::is_whitespace)))
        })
        .map(|(index, _)| index)
}

/// Returns the part of a line that YAML treats as code rather than prose.
fn code_before_comment(line: &str) -> &str {
    comment_start(line).map_or(line, |index| line.split_at(index).0)
}

/// Byte offsets of the scalar values that follow each `uses:` key on a line.
///
/// A flow sequence can hold more than one step, so every key on the line is
/// visited rather than only the first.
fn uses_value_starts(line: &str) -> Vec<usize> {
    let key = "uses:";
    let mut starts = Vec::new();
    let mut search = 0;
    while let Some(rest) = line.get(search..) {
        let Some(found) = rest.find(key) else {
            break;
        };
        let key_start = search + found;
        let is_key = key_start == 0
            || line.get(..key_start).is_some_and(|prefix| {
                prefix.ends_with(|character: char| {
                    character.is_whitespace() || matches!(character, '{' | ',')
                })
            });
        if is_key {
            starts.push(key_start + key.len());
        }
        search = key_start + key.len();
    }
    starts
}

/// Whether the scalar after `uses:` introduces a block value on the next line.
fn is_block_indicator(value: &str) -> bool {
    matches!(value.trim_start().chars().next(), Some('>' | '|'))
}

/// Resolves the scalar text that follows a `uses:` value position.
///
/// A block indicator (`>-`, `|`) places the scalar on the following line; any
/// other form keeps it on the same line. The returned offset is absolute.
fn uses_scalar<'a>(
    lines: &[(usize, &'a str)],
    index: usize,
    value_start: usize,
) -> Option<(usize, &'a str)> {
    let (line_start, line) = *lines.get(index)?;
    let value = code_before_comment(line).split_at(value_start).1;
    if !is_block_indicator(value) {
        let indent = value.len() - value.trim_start().len();
        return Some((line_start + value_start + indent, value.split_at(indent).1));
    }
    let (next_start, next_line) = *lines.get(index + 1)?;
    let next_code = code_before_comment(next_line);
    let indent = next_code.len() - next_code.trim_start().len();
    Some((next_start + indent, next_code.split_at(indent).1))
}

/// Byte ranges of action references that appear in job- or step-level `uses`.
///
/// Comments and every other key are excluded: prose that mentions an action, or
/// a `with:` input that restates one, is not a call site to repoint. Block
/// scalar `uses:` values are read from the following line.
fn reference_spans(source: &str, prefix: &str) -> Vec<(usize, usize)> {
    let lines = source
        .split_inclusive('\n')
        .scan(0usize, |offset, line| {
            let start = *offset;
            *offset += line.len();
            Some((start, line))
        })
        .collect::<Vec<_>>();
    let mut spans = Vec::new();
    for (index, (_, line)) in lines.iter().enumerate() {
        let code = code_before_comment(line);
        for value_start in uses_value_starts(code) {
            let Some((absolute, scalar)) = uses_scalar(&lines, index, value_start) else {
                continue;
            };
            let Some(found) = scalar.find(prefix) else {
                continue;
            };
            let start = absolute + found;
            let Some(reference) = current_reference(source.split_at(start + prefix.len()).1) else {
                continue;
            };
            spans.push((start, start + prefix.len() + reference.len()));
        }
    }
    spans
}

/// Replaces the first, or every, `uses` reference to an action path.
fn replace_references(
    source: &str,
    path: &str,
    replacement: &str,
    first_only: bool,
) -> Option<String> {
    let prefix = format!("{path}@");
    let mut changed = String::with_capacity(source.len());
    let mut cursor = 0;
    let mut replaced = false;
    for (start, end) in reference_spans(source, &prefix) {
        changed.push_str(source.get(cursor..start).unwrap_or_default());
        changed.push_str(&prefix);
        changed.push_str(replacement);
        cursor = end;
        replaced = true;
        if first_only {
            break;
        }
    }
    if !replaced {
        return None;
    }
    changed.push_str(source.get(cursor..).unwrap_or_default());
    Some(changed)
}

/// Replaces the first `uses` reference without coupling fixtures to its SHA.
pub(crate) fn repoint_action(source: &str, path: &str, replacement: &str) -> Option<String> {
    replace_references(source, path, replacement, true)
}

/// Replaces every `uses` reference to the action.
///
/// A coordinated bump must move all of an action's call sites: leaving one
/// behind would make the fixture test an inconsistency rather than a bump.
pub(crate) fn repoint_all_actions(source: &str, path: &str, replacement: &str) -> Option<String> {
    replace_references(source, path, replacement, false)
}

/// Shape and bump regressions shared by all action-reference consumers.
#[cfg(test)]
#[path = "action_ref_tests.rs"]
mod tests;
