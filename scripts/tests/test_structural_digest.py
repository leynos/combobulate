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

    def test_unknown_suffix_has_no_byte_fallback(self) -> None:
        """An unsupported file type is an error, never a byte hash."""
        path = self.directory / 'a.bin'
        path.write_bytes(b'x')
        with self.assertRaises(ValueError):
            DIGEST.structural_digest(path)


if __name__ == '__main__':
    unittest.main()
