"""Prove the audit follows the module tree and reads each crate's own manifest (VO-9, VO-10).

A trust audit is only as good as the set of files it reads. Following the
module graph matters in both directions: a file no ``mod`` names is not
compiled, so reporting its items would describe code that is not in the proof,
and a module reached through ``#[path]`` or ``mod.rs`` must still be found or
its trust would be invisible.

The manifest half is the same kind of boundary. A proc-macro crate's string
literals become the tokens its macro emits, so trust vocabulary spelled inside
one is code the crate really expands; every other crate's literals are data. The
owning manifest is the nearest ``Cargo.toml`` above the file, not simply the
root's, because the audit runs over a workspace whose members each carry their
own.

Examples
--------
>>> len(audit_tree(root, ['src/lib.rs'])) >= 0
True
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.trust_audit import (
    TrustAuditError,
    audit_bound_tree,
    audit_tree,
    is_procedural_macro_crate,
    items_of,
    scan,
)


def item_names(text: str, **options) -> tuple[str, ...]:
    """Return the item names one source reports, in source order."""
    return tuple(item.item for item in scan(text, **options).items)

class OpaqueMacros(unittest.TestCase):
    """Refuse expansion the scanner cannot read, rather than reporting a guess."""

    def test_include_is_refused(self):
        """Refuse ``include!`` because its target is not lexed."""
        with self.assertRaises(TrustAuditError) as raised:
            scan('include!("other.rs");')
        self.assertIn('generates code', str(raised.exception),
                      'the refusal must say why the source cannot be audited')

    def test_paste_is_refused(self):
        """Refuse ``paste!`` because its expansion is not lexed."""
        with self.assertRaises(TrustAuditError):
            scan('paste! { fn f() {} }')

    def test_ordinary_macro_is_not_refused(self):
        """Allow a macro whose arguments are already code in this file."""
        self.assertEqual(item_names('println!("{}", kani::assume(x));'), ('assume',),
                         'an ordinary macro keeps its arguments visible')


class ProceduralMacroCrates(unittest.TestCase):
    """Scan a proc-macro crate's literals, because they can become code."""

    def test_literal_content_is_reported_only_for_a_proc_macro_crate(self):
        """Report vocabulary inside a literal when the caller says it is code."""
        text = 'let body = "kani::assume(x);";'
        self.assertEqual(item_names(text), (),
                         'an ordinary crate must not report literal content')
        self.assertEqual(item_names(text, procedural_macro=True), ('assume',),
                         'a proc-macro crate must report its literal content')

    def test_literal_position_is_precise_enough_to_separate_two_items(self):
        """Report distinct columns for two uses inside one literal."""
        items = scan('let body = "kani::assume(a); kani::assume(b);"',
                     procedural_macro=True).items
        self.assertEqual([item.column for item in items], [19, 36],
                         'two literal uses must stay distinguishable by column')

    def test_literal_position_counts_newlines(self):
        """Report the line the use sits on.

        An escape is two characters, and the body is scanned as written, so a
        ``\\n`` stays on the line it was typed on rather than starting a new one.
        """
        items = scan('let body = "a\\nkani::assume(x);";', procedural_macro=True).items
        self.assertEqual([(item.line, item.column) for item in items], [(1, 22)],
                         'an escaped newline is two characters, so the position stays on line 1')


class ModuleResolution(unittest.TestCase):
    """Follow ``mod`` declarations rather than sweeping directories.

    A file no ``mod`` names is not compiled, so reporting its items would
    describe code that is not in the proof. The converse matters too: a module
    reached through ``#[path]`` or ``mod.rs`` must still be found, or its trust
    would be invisible.
    """

    def setUp(self):
        """Create a scratch crate whose modules use every resolution form."""
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self._write('src/lib.rs', 'mod plain;\nmod nested;\n'
                                  '#[path = "elsewhere.rs"] pub(crate) mod renamed;\n')
        self._write('src/plain.rs', 'fn f() { kani::assume(x); }')
        self._write('src/nested/mod.rs', 'mod inner;\n')
        self._write('src/nested/inner.rs', 'fn g() { kani::stub(a, b); }')
        self._write('src/elsewhere.rs', 'fn h() { kani::should_panic(); }')
        self._write('src/orphan.rs', 'fn i() { kani::assume(y); }')

    def tearDown(self):
        """Remove the scratch crate."""
        self._directory.cleanup()

    def _write(self, relative: str, text: str) -> None:
        """Write one scratch source, creating its directory."""
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def test_reachable_modules_are_audited_and_orphans_are_not(self):
        """Audit each reachable module and leave the unreachable file alone."""
        reported = {entry.path: [item.item for item in entry.items]
                    for entry in audit_tree(self.root, ['src/lib.rs'])}
        self.assertEqual(
            reported,
            {
                'src/plain.rs': ['assume'],
                'src/nested/inner.rs': ['stub'],
                'src/elsewhere.rs': ['should_panic'],
            },
            'only modules a declaration reaches, and that contain an item, may be reported',
        )

    def test_items_carry_file_line_and_column(self):
        """Render each item with the location the schema compares."""
        self.assertIn(
            {'item': 'assume', 'location': 'src/plain.rs:1:16', 'covered_by': None},
            items_of(audit_tree(self.root, ['src/lib.rs'])),
            'the audit must render the schema location form',
        )

    def test_a_module_target_must_exist(self):
        """Refuse a declaration whose file is absent rather than skipping it."""
        self._write('src/lib.rs', 'mod missing;\n')
        with self.assertRaises(TrustAuditError) as raised:
            audit_tree(self.root, ['src/lib.rs'])
        self.assertIn('missing', str(raised.exception),
                      'the refusal must name the module that cannot be resolved')

    def test_an_absolute_path_is_refused(self):
        """Refuse a driver outside the root the audit was given."""
        with self.assertRaises(TrustAuditError):
            audit_tree(self.root, [str(self.root / 'src/lib.rs')])

    def test_a_path_attribute_escaping_the_root_is_refused(self):
        """Refuse a ``#[path]`` that resolves outside the repository."""
        self._write('src/lib.rs', '#[path = "../../elsewhere.rs"] mod escaped;\n')
        with self.assertRaises(TrustAuditError) as raised:
            audit_tree(self.root, ['src/lib.rs'])
        self.assertIn('outside', str(raised.exception),
                      'the refusal must say the target leaves the repository')

    def test_an_inline_module_declaration_resolves_under_its_ancestor(self):
        """Resolve ``mod nested { mod trusted; }`` to ``src/nested/trusted.rs``.

        The inline module is itself a module, so its child lives one directory
        deeper than the declaring file. A decoy at ``src/trusted.rs`` is where
        the shallow reading lands: the audit then reports a clean scan of a
        file the crate never compiles, while the module carrying the trust
        call goes unread.
        """
        self._write('src/lib.rs', 'mod nested { mod trusted; }')
        self._write('src/nested/trusted.rs', 'fn g() { kani::assume(x); }')
        self._write('src/trusted.rs', 'fn h() {}')
        reported = {entry.path: [item.item for item in entry.items]
                    for entry in audit_tree(self.root, ['src/lib.rs'])}
        self.assertEqual(reported, {'src/nested/trusted.rs': ['assume']},
                         'an inline ancestor must direct the child to its own directory')

    def test_a_path_attribute_survives_a_later_attribute(self):
        """Require ``#[path]`` to be found wherever it sits in the attribute list.

        Rust attaches every attribute in the run to the declaration, so
        ``#[path = "…"] #[allow(…)] mod x;`` still compiles the named file.
        Losing the path does not refuse — the declaration falls back to the bare
        ``mod x;`` search — so the audit can read a different file from the one
        the crate compiles and report a clean scan of code outside the proof.
        """
        self._write('src/lib.rs', '#[path = "elsewhere.rs"]\n#[allow(dead_code)]\nmod renamed;\n')
        self.assertEqual([entry.path for entry in audit_tree(self.root, ['src/lib.rs'])],
                         ['src/elsewhere.rs'],
                         'a #[path] before another attribute must still name the target')

    def test_a_decoy_module_does_not_stand_in_for_a_path_target(self):
        """Require the path target to be read even when the bare name also resolves.

        Both files exist here, so a lost ``#[path]`` resolves successfully to the
        wrong one; the audit then reports no items for a crate that does use
        trust. Refusing to fall back is what makes the loss visible.
        """
        self._write('src/lib.rs', '#[path = "elsewhere.rs"]\n#[allow(dead_code)]\nmod renamed;\n')
        self._write('src/renamed.rs', 'fn decoy() {}\n')
        self.assertEqual([(entry.path, [item.item for item in entry.items])
                          for entry in audit_tree(self.root, ['src/lib.rs'])],
                         [('src/elsewhere.rs', ['should_panic'])],
                         'the audit must read the file the crate compiles, not the bare name')

    def test_driver_order_does_not_change_the_result(self):
        """Report the same audit whatever order the drivers arrive in."""
        forward = audit_tree(self.root, ['src/lib.rs', 'src/orphan.rs'])
        backward = audit_tree(self.root, ['src/orphan.rs', 'src/lib.rs'])
        self.assertEqual([entry.path for entry in forward], [entry.path for entry in backward],
                         'an audit must be stable across driver order')
        self.assertEqual([item.item for entry in forward for item in entry.items],
                         [item.item for entry in backward for item in entry.items],
                         'an audit must report the same items in the same order')


class ProceduralMacroCrateDetection(unittest.TestCase):
    """Choose literal scanning from the manifest that owns each source file.

    A proc-macro crate's string literals become the tokens its macro emits, so a
    trust word spelled inside one is code the crate really expands. Every other
    crate's literals are just data. The choice is therefore a correctness
    boundary: detecting it wrongly in the quiet direction under-reports trust
    for the one kind of crate that can synthesize it, and detecting it wrongly
    in the loud direction reports data as code.

    The owning manifest is the nearest ``Cargo.toml`` above the file, not simply
    the root's, because the audit runs over a workspace whose members each carry
    their own.
    """

    def setUp(self):
        """Create a workspace with a proc-macro member beside an ordinary one."""
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self._write('Cargo.toml', '[workspace]\nmembers = ["macros", "ordinary"]\n')
        self._write('macros/Cargo.toml', '[lib]\nproc-macro = true\n')
        self._write('ordinary/Cargo.toml', '[package]\nname = "ordinary"\n')
        self._write('macros/src/lib.rs', 'let s = r#"kani::assume"#;')
        self._write('ordinary/src/lib.rs', 'let s = r#"kani::assume"#;')

    def tearDown(self):
        """Remove the scratch workspace."""
        self._directory.cleanup()

    def _write(self, relative: str, text: str) -> None:
        """Write one scratch file, creating its directory."""
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def test_a_proc_macro_member_has_its_literals_scanned(self):
        """Report the literal's content for the member that expands literals."""
        self.assertEqual([item.item for item in audit_tree(self.root, ['macros/src/lib.rs'])[0].items],
                         ['assume'],
                         'a proc-macro crate literal must be scanned for trust vocabulary')

    def test_an_ordinary_member_does_not_have_its_literals_scanned(self):
        """Leave the ordinary member's literal alone, since it is data."""
        self.assertEqual([(entry.path, [item.item for item in entry.items])
                          for entry in audit_tree(self.root, ['ordinary/src/lib.rs'])],
                         [],
                         'an ordinary crate literal is data and must not be reported as code')

    def test_the_nearest_manifest_decides_not_the_workspace_root(self):
        """Require each member's own manifest to be found.

        Both drivers sit under the same root manifest, which declares no
        proc-macro target. A lookup that stopped at the root would give every
        member the same answer and silently lose the macros crate's items.
        """
        reported = {entry.path: [item.item for item in entry.items]
                    for entry in audit_tree(self.root,
                                            ['macros/src/lib.rs', 'ordinary/src/lib.rs'])}
        self.assertEqual(reported, {'macros/src/lib.rs': ['assume']},
                         'the owning manifest must be selected per source file')

    def test_a_manifest_without_the_directive_is_not_procedural(self):
        """Require the negative case, which a ``not in`` test would invert."""
        self.assertFalse(is_procedural_macro_crate(self.root / 'ordinary/Cargo.toml'),
                         'a manifest with no proc-macro target is an ordinary crate')

    def test_an_unreadable_manifest_is_not_procedural(self):
        """Refuse to guess proc-macro mode when the manifest cannot be read.

        The alternative — reporting True — would scan an ordinary crate's data
        as code, which is the loud direction and produces false trust items.
        """
        self.assertFalse(is_procedural_macro_crate(self.root / 'absent/Cargo.toml'),
                         'a missing manifest must not be read as a proc-macro crate')

    def test_the_directive_is_recognised_however_it_is_spaced(self):
        """Require TOML's spacing freedom to reach the same answer.

        TOML does not fix the whitespace around ``=``, so ``proc-macro=true``
        and ``proc-macro   =   true`` declare exactly the same crate as the
        spaced form. Matching the directive as text would audit the first two
        as ordinary libraries and silently stop scanning their literals, which
        are the tokens their macros emit.
        """
        for directive in ('proc-macro = true', 'proc-macro=true',
                          'proc-macro   =   true', 'proc-macro\t=\ttrue'):
            with self.subTest(directive=directive):
                manifest = self.root / 'spaced/Cargo.toml'
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text(f'[lib]\n{directive}\n', encoding='utf-8')
                self.assertTrue(is_procedural_macro_crate(manifest),
                                f'{directive!r} must be read as the directive')

    def test_a_commented_out_directive_is_not_procedural(self):
        """Require a commented directive to be ignored.

        A manifest may keep the line as a comment while the crate is ordinary.
        Reading it as a declaration would scan an ordinary crate's data as code
        and invent trust items the author never wrote.
        """
        manifest = self.root / 'commented/Cargo.toml'
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text('[lib]\n# proc-macro = true\n', encoding='utf-8')
        self.assertFalse(is_procedural_macro_crate(manifest),
                         'a commented-out directive must not make a crate procedural')

    def test_a_directive_carrying_a_comment_is_procedural(self):
        """Require a trailing comment not to hide the declaration.

        TOML lets an author explain a key on its own line. A reader that
        matched the declaration as text would reject it, audit a real proc-macro
        crate as an ordinary library, and leave the literals its macros emit
        unscanned.
        """
        manifest = self.root / 'explained/Cargo.toml'
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text('[lib]\nproc-macro = true  # emits the harness\n', encoding='utf-8')
        self.assertTrue(is_procedural_macro_crate(manifest),
                        'a trailing comment must not hide the directive')

    def test_a_dotted_directive_is_procedural(self):
        """Require the dotted spelling TOML defines for the same table.

        ``lib.proc-macro = true`` before any table header declares exactly the
        crate that ``[lib]`` followed by ``proc-macro = true`` declares, so the
        two must reach the same answer.
        """
        manifest = self.root / 'dotted/Cargo.toml'
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text('lib.proc-macro = true\n', encoding='utf-8')
        self.assertTrue(is_procedural_macro_crate(manifest),
                        'the dotted spelling of the directive must be read')

    def test_a_directive_under_another_table_is_not_procedural(self):
        """Require the key to be read from ``[lib]``, not from anywhere in the document.

        ``proc-macro`` is only meaningful under ``[lib]``. A reader that scanned
        the parsed document for the key would call a crate procedural because a
        dev-dependency or a feature happened to be named the same.
        """
        manifest = self.root / 'elsewhere/Cargo.toml'
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text('[features]\nproc-macro = true\n', encoding='utf-8')
        self.assertFalse(is_procedural_macro_crate(manifest),
                         'only the [lib] table may declare a proc-macro target')

    def test_a_non_boolean_directive_is_not_procedural(self):
        """Require the value to be the boolean ``true``, not merely present.

        TOML permits a quoted string where a boolean belongs. That manifest is
        invalid for Cargo, and the audit must not read it as a declaration; the
        loud direction reports a literal as data rather than inventing trust.
        """
        manifest = self.root / 'quoted/Cargo.toml'
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text('[lib]\nproc-macro = "true"\n', encoding='utf-8')
        self.assertFalse(is_procedural_macro_crate(manifest),
                         'a quoted value is not the boolean the directive needs')

    def test_an_unparsable_manifest_is_not_procedural(self):
        """Refuse to guess proc-macro mode when the manifest is not valid TOML.

        The audit reads manifests it did not write. Text that merely contains
        the directive is not a manifest Cargo would accept, and reading it as
        one would scan an unknown crate's data as code.
        """
        manifest = self.root / 'broken/Cargo.toml'
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text('[lib\nproc-macro = true\n', encoding='utf-8')
        self.assertFalse(is_procedural_macro_crate(manifest),
                         'a manifest that cannot be parsed must not select proc-macro mode')


class ManifestDiscoveryFailsClosed(unittest.TestCase):
    """Require the manifest lookup to fail closed when no crate owns the file.

    A source with no owning manifest is not compiled by any crate, so its
    literals are data and must not be scanned for vocabulary. The lookup still
    has to name the file Cargo itself reads — exactly ``Cargo.toml`` — because a
    lookalike beside it is not a manifest Cargo would ever use, and treating one
    as the owner would scan a stranger's data as though it were code.
    """

    def setUp(self):
        """Create a tree whose root carries no manifest at all."""
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        (self.root / 'src').mkdir()
        (self.root / 'src/lib.rs').write_text('let s = r#"kani::assume"#;', encoding='utf-8')

    def tearDown(self):
        """Remove the scratch tree."""
        self._directory.cleanup()

    def test_a_file_no_manifest_owns_is_not_scanned_for_literals(self):
        """Report nothing, rather than guessing a crate's mode."""
        self.assertEqual(audit_tree(self.root, ['src/lib.rs']), (),
                         'a source with no owning manifest carries data, not code')

    def test_a_lookalike_manifest_does_not_become_the_owner(self):
        """Require the exact filename, not another spelling of it."""
        for name in ('cargo.toml', 'CARGO.TOML', 'XXCargo.tomlXX'):
            (self.root / name).write_text('[lib]\nproc-macro = true\n', encoding='utf-8')
        self.assertEqual(audit_tree(self.root, ['src/lib.rs']), (),
                         'only the manifest Cargo reads may select proc-macro mode')


class BoundAuditStopsAtTheVerifiedSet(unittest.TestCase):
    """Require the bound walk to read only the bytes its caller verified.

    The evidence gate binds each manifest source to a digest before auditing it.
    A walk that then opened the working tree would audit bytes nobody checked,
    so a local edit to a child module could change the item multiset a record is
    matched against. Refusing an unbound child is the same policy one level
    down: the walk may not leave the set it was handed.
    """

    def setUp(self):
        """Create a scratch crate whose ``lib.rs`` compiles one child module."""
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self._write('src/lib.rs', 'mod child;\n')
        self._write('src/child.rs', 'fn f() { kani::assume(x); }')

    def tearDown(self):
        """Remove the scratch crate."""
        self._directory.cleanup()

    def _write(self, relative: str, text: str) -> None:
        """Write one scratch source, creating its directory."""
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def test_the_audited_text_is_the_verified_bytes_not_the_working_tree(self):
        """Audit the caller's bytes, so an edit on disk cannot reach the result."""
        bound = {'src/lib.rs': b'mod child;\n',
                 'src/child.rs': b'fn f() { kani::assume(x); }'}
        # The working tree now disagrees with the bound bytes. The audit must
        # report what the caller verified, not what the file has become.
        self._write('src/child.rs', 'fn f() { kani::stub(a, b); }')
        reported = {entry.path: [item.item for item in entry.items]
                    for entry in audit_bound_tree(self.root, bound)}
        self.assertEqual(reported, {'src/child.rs': ['assume']},
                         'the audit must read the verified bytes, not the edited file')

    def test_a_module_the_bound_set_does_not_name_is_refused(self):
        """Refuse an unbound child rather than reading it from disk.

        Reading it would put a file the manifest never bound into the item
        multiset, which is exactly the escape DL-16 exists to prevent.
        """
        bound = {'src/lib.rs': b'mod child;\n'}
        with self.assertRaises(TrustAuditError) as raised:
            audit_bound_tree(self.root, bound)
        self.assertIn('not itself bound to a digest', str(raised.exception),
                      'the refusal must say the module left the bound set')


