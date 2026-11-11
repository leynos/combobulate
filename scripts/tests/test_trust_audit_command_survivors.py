"""Kill the command-layer mutants a corpus sweep leaves alive (VO-9, VO-10).

The mutation census over :mod:`docs_validation.trust_audit.command` leaves
survivors where the walk's *bookkeeping* moves rather than its scanning: the
separator normalisation a Windows driver depends on, the default that decides
whether a crate's literals are code, and the loop that must keep walking after
it revisits a file it has already read. A committed corpus is scanned on one
platform by a walk that never names a file twice, so no case in it exercises
these mutations.

One family is an equivalent rather than a gap, and it is recorded here because
the mutated code lives in this module even though the argument is about
Python's codec registry. ``scan_tree`` and ``is_procedural_macro_crate`` read
with ``encoding='utf-8'``; ``encoding=None`` selects the locale's preferred
encoding, which this repository's gates run as UTF-8, and ``'UTF-8'`` is the
same codec under another name. Every byte sequence the audit reads decodes
identically under all three, so no file can tell the variants apart. The cases
that read files through this module live in
:mod:`test_trust_audit_lexer_survivors`, whose docstring states the same
equivalence.

Examples
--------
>>> audit_tree(root, ['src/lib.rs'])[0].path
'src/lib.rs'
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import audit_tree, scan_tree


def write(root: Path, relative: str, text: str) -> None:
    """Write one scratch source, creating its parent directory."""
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')


class DriverSeparators(unittest.TestCase):
    """Require a Windows-style driver to name the same file as a POSIX one."""

    def test_a_backslash_driver_reaches_the_file_it_names(self):
        """Require both separator replacements, since a driver may arrive
        either way.

        A driver written with ``\\`` is what a caller on Windows passes. The
        walk normalises it to ``/`` before resolving, so both spellings reach
        the one file. A mutation that stops replacing the separator -- or
        replaces it with a padding string -- leaves the backslash in the path,
        ``resolve_repository_path`` cannot find the file, and the audit refuses
        a crate it should have read.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, 'src/lib.rs', 'fn f() { kani::assume(a); }\n')
            self.assertEqual([entry.path for entry in audit_tree(root, ['src\\lib.rs'])],
                             ['src/lib.rs'],
                             'a backslash-separated driver must name the same file')


class LiteralScanningDefault(unittest.TestCase):
    """Require literal scanning to be opted into, not assumed."""

    def test_a_literal_is_scanned_only_when_the_crate_is_a_procedural_macro(self):
        """Require the default to be ``False``, which is what gives the flag
        its meaning.

        An ordinary crate's string literal is data: trust vocabulary spelled
        inside one is not code the compiler expands. Defaulting the parameter
        to ``True`` would report every literal in every crate, so a record
        covering only the real uses would look incomplete and an audit of a
        clean crate would claim trust it does not contain. The second assertion
        keeps the first from passing for a scanner that never reads a literal
        at all.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, 'x.rs', 'let s = "kani::assume(x)";\n')
            self.assertEqual(scan_tree(root, 'x.rs').items, (),
                             'an ordinary crate must not report vocabulary inside a literal')
            self.assertEqual([item.item for item in
                              scan_tree(root, 'x.rs', procedural_macro=True).items],
                             ['assume'],
                             'a proc-macro crate must report the literal it opts into')


class RevisitedFiles(unittest.TestCase):
    """Require the walk to continue after it meets a file already read."""

    def test_a_revisit_does_not_end_the_walk(self):
        """Require ``continue``, so a repeat is not the end of the audit.

        ``lib`` declares ``p``, and ``p`` declares ``x`` before re-declaring
        ``lib`` through ``#[path]``. The stack then holds ``x`` and the
        revisited ``lib``, and ``lib`` is popped first. Treating that repeat as
        the end of the walk drops ``x`` -- the only file carrying a trust item
        -- so a crate that does use trust audits clean.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, 'src/lib.rs', 'mod p;\n')
            # `x` is a child of the non-root module `p`, so Rust puts it under
            # `src/p/`. Placing it beside `src/p.rs` would have resolved only
            # under the sibling search this module's cases no longer allow.
            write(root, 'src/p.rs', 'mod x;\n#[path = "lib.rs"] mod again;\n')
            write(root, 'src/p/x.rs', 'fn f() { kani::assume(a); }\n')
            self.assertEqual([entry.path for entry in audit_tree(root, ['src/lib.rs'])],
                             ['src/p/x.rs'],
                             'a revisited file must not stop the walk before its neighbours')


class NestedModuleResolution(unittest.TestCase):
    """Require a child module to resolve under its parent's own directory.

    Rust does not search a module file's sibling directory for its children: a
    child of ``src/foo.rs`` lives in ``src/foo/``. Searching ``src/`` instead
    finds an unrelated file of the same name -- a decoy, or a sibling module --
    and audits it as though it were compiled into the module that declared it.
    """

    def test_a_child_of_a_non_root_module_resolves_under_it(self):
        """Require `src/foo.rs`'s `mod bar;` to find `src/foo/bar.rs`."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, 'src/lib.rs', 'mod foo;\n')
            write(root, 'src/foo.rs', 'mod bar;\n')
            write(root, 'src/bar.rs', 'fn decoy() { kani::assume(a); }\n')
            write(root, 'src/foo/bar.rs', 'fn real() { kani::assume(b); }\n')
            self.assertEqual([entry.path for entry in audit_tree(root, ['src/lib.rs'])],
                             ['src/foo/bar.rs'],
                             'a child of a non-root module must resolve under that module')

    def test_a_child_of_a_mod_root_module_resolves_beside_it(self):
        """Require `src/foo/mod.rs`'s `mod bar;` to find `src/foo/bar.rs`."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, 'src/lib.rs', 'mod foo;\n')
            write(root, 'src/foo/mod.rs', 'mod bar;\n')
            write(root, 'src/foo/bar.rs', 'fn f() { kani::assume(a); }\n')
            self.assertEqual([entry.path for entry in audit_tree(root, ['src/lib.rs'])],
                             ['src/foo/bar.rs'],
                             'a `mod.rs` root must search its own directory')

    def test_a_crate_root_child_resolves_beside_it(self):
        """Require `src/lib.rs`'s `mod foo;` to keep finding `src/foo.rs`."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, 'src/lib.rs', 'mod foo;\n')
            write(root, 'src/foo.rs', 'fn f() { kani::assume(a); }\n')
            self.assertEqual([entry.path for entry in audit_tree(root, ['src/lib.rs'])],
                             ['src/foo.rs'],
                             'a crate root must still search its own directory')

    def test_a_deeply_nested_child_resolves_under_its_own_stem(self):
        """Require `src/foo/bar.rs`'s `mod baz;` to find `src/foo/bar/baz.rs`."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, 'src/lib.rs', 'mod foo;\n')
            write(root, 'src/foo.rs', 'mod bar;\n')
            write(root, 'src/foo/bar.rs', 'mod baz;\n')
            write(root, 'src/foo/baz.rs', 'fn decoy() { kani::assume(a); }\n')
            write(root, 'src/foo/bar/baz.rs', 'fn real() { kani::assume(c); }\n')
            self.assertEqual([entry.path for entry in audit_tree(root, ['src/lib.rs'])],
                             ['src/foo/bar/baz.rs'],
                             'each non-root module contributes its own directory')


if __name__ == '__main__':
    unittest.main()
