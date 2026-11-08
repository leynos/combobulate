"""Guard the scratch workspace's lint tables against weaker inherited rules."""

import tomllib
import unittest

from verifier_probe_loader import (
    ROOT,
    load_structural_digest,
    load_verifier_probe_support,
)


class WorkspaceLintTableTests(unittest.TestCase):
    """Exercise lint-table extraction for the native scratch workspace."""

    def test_lint_tables_are_renamed_and_following_tables_dropped(self) -> None:
        """A table after the lints must not reach the virtual manifest."""
        manifest = (
            '[package]\nname = "probe"\n\n'
            '[lints.clippy]\nlint = "deny"\n\n'
            '[lints.rust]\nother = "deny"\n\n'
            '[dev-dependencies]\ndep = "1"\n'
        )

        tables = load_verifier_probe_support().workspace_lint_tables(manifest)

        self.assertEqual(
            tables,
            '[workspace.lints.clippy]\nlint = "deny"\n\n'
            '[workspace.lints.rust]\nother = "deny"\n\n',
            'only lint tables may reach the virtual workspace manifest',
        )

    def test_workspace_spelling_is_accepted(self) -> None:
        """The planned three-crate spelling must keep working."""
        manifest = '[workspace.lints.rust]\nunsafe_code = "forbid"\n'

        tables = load_verifier_probe_support().workspace_lint_tables(manifest)

        self.assertEqual(
            tables,
            '[workspace.lints.rust]\nunsafe_code = "forbid"\n\n',
            'workspace lint tables must survive unchanged',
        )

    def test_a_header_with_a_trailing_comment_is_extracted_and_digested(self) -> None:
        """The copy and the digest come from one parse, so they cannot disagree."""
        digest = load_structural_digest()
        plain = '[lints.clippy]\nlint = "deny"\n'
        commented = '[lints.clippy]  # strict\nlint = "deny"  # never warn\n'
        support = load_verifier_probe_support()

        self.assertEqual(
            support.workspace_lint_tables(commented),
            support.workspace_lint_tables(plain),
            'a comment on a header must not drop or alter the table',
        )
        self.assertEqual(
            digest.lint_tables_digest(commented),
            digest.lint_tables_digest(plain),
            'the digest must see the same table as the copy',
        )
        self.assertNotEqual(
            digest.lint_tables_digest(plain),
            digest.lint_tables_digest(plain.replace('deny', 'warn')),
            'a weakened lint must move the digest',
        )

    def test_the_repository_copy_parses_back_to_the_same_tables(self) -> None:
        """Rendering must not change what the scratch workspace applies."""
        manifest = (ROOT / 'Cargo.toml').read_text(encoding='utf-8')
        copied = tomllib.loads(
            load_verifier_probe_support().workspace_lint_tables(manifest)
        )['workspace']['lints']
        self.assertEqual(
            copied,
            load_structural_digest().lint_tables(manifest),
            'the scratch tables must equal the parsed repository tables',
        )

    def test_missing_lint_table_is_reported(self) -> None:
        """A manifest without lints must fail clearly, not by index error."""
        with self.assertRaisesRegex(
            RuntimeError,
            'at least one lint table',
            msg='a manifest without lint tables must be rejected',
        ):
            load_verifier_probe_support().workspace_lint_tables(
                '[package]\nname = "probe"\n'
            )

    def test_repository_manifest_supplies_every_lint_table(self) -> None:
        """The scratch workspace inherits all three repository lint tables."""
        manifest = (ROOT / 'Cargo.toml').read_text()

        tables = load_verifier_probe_support().workspace_lint_tables(manifest)

        for name in ('clippy', 'rust', 'rustdoc'):
            self.assertIn(
                f'[workspace.lints.{name}]',
                tables,
                f'the scratch workspace must inherit the {name} lint table',
            )
        self.assertNotIn(
            '\n[dev-dependencies]',
            tables,
            'a non-lint table must not enter the virtual manifest',
        )