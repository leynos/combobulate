"""Guard the scratch workspace's lint tables against weaker inherited rules."""

import unittest

from verifier_probe_loader import ROOT, load_verifier_probe_support


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
            '[workspace.lints.rust]\nunsafe_code = "forbid"\n',
            'workspace lint tables must survive unchanged',
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