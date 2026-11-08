"""Prove structural digests ignore layout and comments but not real changes.

The digest test binds verifier records to their inputs. These cases pin what
"the same input" means: reformatting or re-commenting a Rust or TOML file must
leave the digest alone, while changing a code token, a doc comment, or the
toolchain channel must move it.

For example::

    python3 -m unittest test_structural_digest
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verifier_probe_loader import load_structural_digest

DIGEST = load_structural_digest()

RUST = '''\
//! Crate docs.

/// Adds one.
pub fn add(value: u32) -> u32 {
    // plain comment
    value + 1 /* inline */
}
'''

TOOLCHAIN = '''\
[toolchain]
channel = "nightly-2026-08-27"
components = ["clippy", "rustfmt"]
'''


class StructuralDigestTests(unittest.TestCase):
    """Check which edits move a structural digest."""

    def setUp(self) -> None:
        """Create a scratch directory removed after each case."""
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)

    def digest(self, name: str, text: str) -> str:
        """Write ``text`` as ``name`` and return its structural digest."""
        path = self.directory / name
        path.write_text(text, encoding='utf-8')
        return DIGEST.structural_digest(path)

    def assertSame(self, name: str, before: str, after: str, why: str) -> None:
        """Assert two spellings of one input share a digest."""
        self.assertEqual(self.digest(name, before), self.digest(name, after), why)

    def assertDiffers(self, name: str, before: str, after: str, why: str) -> None:
        """Assert a real change moves the digest."""
        self.assertNotEqual(self.digest(name, before), self.digest(name, after), why)

    def test_digest_is_versioned(self) -> None:
        """A structural digest carries its prefix; a bare hex value is legacy."""
        value = self.digest('a.toml', TOOLCHAIN)
        self.assertTrue(DIGEST.is_structural_digest(value), 'prefix and 64 hex digits')
        self.assertFalse(DIGEST.is_structural_digest('a' * 64), 'legacy digest is refused')

    def test_rust_reformat_and_plain_comments_are_ignored(self) -> None:
        """Layout and plain comments do not change what the compiler sees."""
        reformatted = (
            '//! Crate docs.\n/// Adds one.\n'
            'pub fn add(value:u32)->u32{ /* other */ value+1 }\n// trailing\n'
        )
        self.assertSame('a.rs', RUST, reformatted, 'reformat plus comment edit')

    def test_rust_code_token_change_is_detected(self) -> None:
        """A different literal is a different program."""
        self.assertDiffers('a.rs', RUST, RUST.replace('+ 1', '+ 2'), 'code token')

    def test_rust_doc_comments_are_kept_in_every_form(self) -> None:
        """Doc comments are attributes, so editing any form moves the digest."""
        for before, after in (
            ('/// one\nfn f() {}\n', '/// two\nfn f() {}\n'),
            ('//! one\nfn f() {}\n', '//! two\nfn f() {}\n'),
            ('/** one */\nfn f() {}\n', '/** two */\nfn f() {}\n'),
            ('/*! one */\nfn f() {}\n', '/*! two */\nfn f() {}\n'),
        ):
            with self.subTest(form=before.split()[0]):
                self.assertDiffers('d.rs', before, after, 'doc comment text')

    def test_rust_lexical_edge_cases_are_not_mistaken_for_comments(self) -> None:
        """Comment markers inside literals are content; nesting is respected."""
        cases = {
            'nested block': ('fn f() { /* a /* b */ c */ }\n', 'fn f() { }\n', True),
            'slashes in string': ('const S: &str = "a // b";\n', 'const S: &str = "a // c";\n', False),
            'raw string': ('const S: &str = r#"x // "y""#;\n', 'const S: &str = r#"x // "z""#;\n', False),
            'raw byte string': ('const S: &[u8] = br##"a /* b"##;\n', 'const S: &[u8] = br##"a /* c"##;\n', False),
            'byte string': ('const S: &[u8] = b"a // b";\n', 'const S: &[u8] = b"a // c";\n', False),
            'c string': ('const S: &core::ffi::CStr = c"a // b";\n', 'const S: &core::ffi::CStr = c"a // c";\n', False),
            'char literal': ("const C: char = 'a';\n", "const C: char = 'b';\n", False),
            'lifetime': ("fn f<'a>(x: &'a u8) {}\n", "fn f<'b>(x: &'b u8) {}\n", False),
        }
        for label, (before, after, same) in cases.items():
            with self.subTest(case=label):
                check = self.assertSame if same else self.assertDiffers
                check('e.rs', before, after, label)

    def test_rust_that_does_not_parse_is_refused(self) -> None:
        """A broken file must not produce a digest."""
        path = self.directory / 'bad.rs'
        path.write_text('fn (', encoding='utf-8')
        with self.assertRaises(ValueError):
            DIGEST.structural_digest(path)

    def test_toml_layout_comments_and_key_order_are_ignored(self) -> None:
        """TOML is hashed as parsed data."""
        reformatted = (
            '# pinned\n[toolchain]\ncomponents = [\n  "clippy",\n  "rustfmt",\n]\n'
            'channel   =   "nightly-2026-08-27"  # moved\n'
        )
        self.assertSame('rust-toolchain.toml', TOOLCHAIN, reformatted, 'toml reformat')

    def test_toml_toolchain_channel_change_is_detected(self) -> None:
        """Moving the channel changes the parsed toolchain."""
        moved = TOOLCHAIN.replace('2026-08-27', '2026-08-28')
        self.assertDiffers('rust-toolchain.toml', TOOLCHAIN, moved, 'channel')

    def test_json_layout_is_ignored_and_values_are_not(self) -> None:
        """JSON is hashed as canonical JSON."""
        self.assertSame('a.json', '{"a":1,"b":[1,2]}', '{ "b": [1, 2],\n "a": 1 }', 'layout')
        self.assertDiffers('a.json', '{"a":1}', '{"a":2}', 'value')

    def test_python_comments_are_ignored_and_code_is_not(self) -> None:
        """Python is hashed as its parsed tree."""
        self.assertSame('a.py', 'x = 1  # one\n', 'x=1\n\n# note\n', 'comment')
        self.assertDiffers('a.py', 'x = 1\n', 'x = 2\n', 'code')

    def test_shell_comment_lines_and_blanks_are_ignored(self) -> None:
        """Shell text drops comment-only and blank lines, and keeps the shebang."""
        base = '#!/bin/sh\n# note\n\nexec true\n'
        self.assertSame('a.sh', base, '#!/bin/sh\nexec true  \n# end\n', 'comment')
        self.assertDiffers('a.sh', base, '#!/bin/bash\nexec true\n', 'shebang')
        self.assertDiffers('a.sh', base, '#!/bin/sh\nexec false\n', 'command')

    def test_python_script_metadata_is_content_not_a_comment(self) -> None:
        """``uv run --script`` reads dependencies from a comment block."""
        header = '# /// script\n# dependencies = ["tool==1"]\n# ///\nx = 1\n'
        self.assertDiffers('s.py', header, header.replace('tool==1', 'tool==2'), 'pin')
        self.assertSame('s.py', header, header + '# trailing note\n', 'other comment')

    def test_shell_whitespace_after_a_continuation_backslash_matters(self) -> None:
        """A space after the backslash changes the command, so it is kept."""
        self.assertDiffers('c.sh', 'echo a \\\n  b\n', 'echo a \\ \n  b\n', 'backslash')

    def test_a_version_file_must_hold_one_line(self) -> None:
        """The build's pin reader rejects extra lines, so the digest does too."""
        self.assertSame('VERSION', '2.41.0\n', '2.41.0', 'trailing newline')
        self.assertDiffers('VERSION', '2.41.0\n', '2.42.0\n', 'pin')
        with self.assertRaises(ValueError):
            self.digest('VERSION', '2.41.0\n\n')

    def test_doc_comment_trailing_whitespace_is_kept(self) -> None:
        """A doc comment's text is content, trailing whitespace included."""
        self.assertDiffers('d.rs', '/// one\nfn f() {}\n', '/// one \nfn f() {}\n', 'doc')

    def test_parse_failures_name_the_input(self) -> None:
        """A failing generator or test must say which file and why."""
        path = self.directory / 'broken.toml'
        path.write_text('a = = 1', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'cannot digest .*broken.toml'):
            DIGEST.structural_digest(path)

    def drift(self, toolchain_now: str, other: str = 'a = 1\n'):
        """Record against a recorded toolchain, then classify the current tree."""
        recorded_toolchain = TOOLCHAIN
        (self.directory / 'rust-toolchain.toml').write_text(recorded_toolchain)
        (self.directory / 'other.toml').write_text('a = 1\n')
        digests = {
            name: DIGEST.structural_digest(self.directory / name)
            for name in ('rust-toolchain.toml', 'other.toml')
        }
        (self.directory / 'rust-toolchain.toml').write_text(toolchain_now)
        (self.directory / 'other.toml').write_text(other)
        command = ['podman', 'RUSTUP_TOOLCHAIN=nightly-2026-08-27']
        return DIGEST.classify_drift(self.directory, digests, command)

    def test_channel_only_toolchain_drift_warns_and_passes(self) -> None:
        """A bumped channel is a note naming both values, not a failure."""
        failures, note = self.drift(TOOLCHAIN.replace('2026-08-27', '2026-09-30'))
        self.assertEqual(failures, [], 'channel-only drift must not fail')
        self.assertEqual(
            note,
            'Evidence captured for toolchain nightly-2026-08-27; '
            'evidence missing for the current pin nightly-2026-09-30.',
            'the note must name the recorded and current channels',
        )

    def test_another_input_changing_fails(self) -> None:
        """Only the toolchain is soft; any other input still fails."""
        failures, note = self.drift(TOOLCHAIN, other='a = 2\n')
        self.assertEqual(failures, ['other.toml'], 'other input must fail')
        self.assertIsNone(note, 'an unchanged toolchain needs no note')

    def test_non_channel_toolchain_change_fails(self) -> None:
        """Components or targets changing is a real change, even with a new channel."""
        for changed in (
            TOOLCHAIN.replace('"rustfmt"', '"rustfmt", "miri"'),
            TOOLCHAIN.replace('2026-08-27', '2026-09-30').replace('"rustfmt"', '"miri"'),
            TOOLCHAIN + 'targets = ["wasm32-unknown-unknown"]\n',
        ):
            with self.subTest(changed=changed):
                failures, note = self.drift(changed)
                self.assertEqual(failures, ['rust-toolchain.toml'], 'must fail')
                self.assertIsNone(note, 'a failure must not be softened')

    def test_an_invalid_current_channel_fails_instead_of_warning(self) -> None:
        """Only a channel rustup accepts may be softened to a warning."""
        for bad in ('channel = 42\n', 'channel = "not a channel"\n', 'channel = ""\n'):
            with self.subTest(channel=bad):
                failures, note = self.drift(
                    '[toolchain]\n' + bad + 'components = ["clippy", "rustfmt"]\n'
                )
                self.assertEqual(failures, ['rust-toolchain.toml'], 'must fail')
                self.assertIsNone(note, 'no warning for an invalid channel')
        for good in ('stable', 'beta', 'nightly', 'nightly-2026-09-30', '1.94', '1.94.1'):
            self.assertTrue(DIGEST.is_rustup_channel(good), good)

    def test_impossible_calendar_dates_are_not_channels(self) -> None:
        """A dated channel needs a real date, so drift cannot hide behind one."""
        for bad in ('nightly-2026-99-99', 'nightly-2026-02-30', 'beta-2026-13-01'):
            self.assertFalse(DIGEST.is_rustup_channel(bad), bad)
        self.assertTrue(DIGEST.is_rustup_channel('nightly-2026-02-28'), 'real date')
        failures, note = self.drift(TOOLCHAIN.replace('2026-08-27', '2026-99-99'))
        self.assertEqual(failures, ['rust-toolchain.toml'], 'impossible date fails')
        self.assertIsNone(note, 'no warning for an impossible date')

    def test_shell_lines_after_a_continuation_backslash_are_kept(self) -> None:
        """A comment-looking line inside a continued command is not a comment."""
        base = 'echo a \\\n  b\n'
        with_comment = 'echo a \\\n# not a comment\n  b\n'
        self.assertDiffers('k.sh', base, with_comment, 'continued line')
        self.assertDiffers('k.sh', base, 'echo a \\\n\n  b\n', 'continued blank')
        self.assertSame('k.sh', base, base + '# after\n', 'ordinary comment')

    def test_commenting_out_a_script_dependency_is_detected(self) -> None:
        """Only the PEP 723 line prefix is removed, so a hidden pin still moves it."""
        header = '# /// script\n# dependencies = [\n#   "tool==1",\n# ]\n# ///\nx = 1\n'
        hidden = header.replace('#   "tool==1"', '# #  "tool==1"')
        self.assertDiffers('s.py', header, hidden, 'commented-out dependency')

    def test_comment_like_text_inside_a_shell_quote_is_content(self) -> None:
        """A quoted line that starts with a hash is not a comment."""
        base = "echo 'a\nb'\n"
        self.assertDiffers('q.sh', base, "echo 'a\n# x\nb'\n", 'single quote')
        self.assertDiffers('q.sh', 'echo "a\nb"\n', 'echo "a\n# x\nb"\n', 'double quote')
        self.assertSame('q.sh', "echo 'a'\n", "# it's fine\necho 'a'\n", 'apostrophe in comment')

    def test_lint_tables_digest_follows_the_tables_only(self) -> None:
        """Dependency edits and layout leave the digest alone; a lint level moves it."""
        base = '[workspace.lints.clippy]\nunwrap_used = "deny"\n[dependencies]\na = "1"\n'
        same = '[dependencies]\na = "2"  # bumped\n\n[workspace.lints.clippy]\nunwrap_used   = "deny"\n'
        self.assertEqual(
            DIGEST.lint_tables_digest(base), DIGEST.lint_tables_digest(same), 'unrelated edit'
        )
        self.assertNotEqual(
            DIGEST.lint_tables_digest(base),
            DIGEST.lint_tables_digest(base.replace('"deny"', '"warn"')),
            'lint level',
        )

    def test_unknown_suffix_has_no_byte_fallback(self) -> None:
        """An unsupported file type is an error, never a byte hash."""
        path = self.directory / 'a.bin'
        path.write_bytes(b'x')
        with self.assertRaises(ValueError):
            DIGEST.structural_digest(path)


if __name__ == '__main__':
    unittest.main()
