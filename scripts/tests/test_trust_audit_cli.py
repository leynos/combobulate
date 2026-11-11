"""Require the trust-audit command to find every crate under its arguments.

``scripts/trust_audit.py PATH...`` expands each argument to the entry points
Rust compiles from it. A crate directory keeps its sources in ``src/``, so a
reader that looked only at the argument's immediate files found nothing there
and refused ``crates/`` with "contains no Rust entry point to audit" — an
argument Cargo builds without complaint. The same reader named its drivers
relative to the argument rather than the repository, so a submodule reaching a
sibling of the argument could not be resolved at all.

The cases load the real command module. It imports Cyclopts and inserts
``scripts/`` on ``sys.path`` before its own imports, which a test process can
do once; doing so twice would re-execute it under a second module identity.
Examples
--------
>>> drivers(tmp / 'crates')[0][0]
'crates/one/src/lib.rs'
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent


def load_command() -> object:
    """Load ``scripts/trust_audit.py`` as the CLI module.

    The command is a script rather than a package module, so it is loaded by
    path. Loading is deferred to the first caller and cached: the module
    derives ``ROOT`` from its own location, and a second execution would give
    two modules with different identities, one of which no test could reach.
    """
    cached = sys.modules.get('trust_audit_cli')
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location('trust_audit_cli', SCRIPTS / 'trust_audit.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['trust_audit_cli'] = module
    spec.loader.exec_module(module)
    return module


class DriverDiscovery(unittest.TestCase):
    """Expand a directory argument to the entries Rust compiles under it."""

    def setUp(self) -> None:
        """Build a scratch workspace whose crates keep their sources in ``src/``."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self._write('Cargo.toml', '[workspace]\nmembers = ["crates/one"]\n')
        self._write('crates/one/Cargo.toml', '[package]\nname = "one"\n')
        self._write('crates/one/src/lib.rs', 'pub fn one() {}\n')
        self._write('crates/one/src/child.rs', 'pub fn child() {}\n')
        self._write('crates/one/tests/it.rs', '#[test]\nfn it() {}\n')
        self._write('crates/two/Cargo.toml', '[package]\nname = "two"\n')
        self._write('crates/two/src/main.rs', 'fn main() {}\n')
        self.command = load_command()
        self._root = self.command.ROOT
        self.command.ROOT = self.root

    def tearDown(self) -> None:
        """Restore the command's repository root for any later case."""
        self.command.ROOT = self._root

    def _write(self, relative: str, text: str) -> None:
        """Write one scratch file, creating its parent directory."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def test_a_crate_directory_contributes_its_own_src_entry_points(self) -> None:
        """Find ``src/lib.rs`` when the argument is the crate directory itself."""
        drivers = [driver for driver, _ in self.command._drivers(self.root / 'crates/one')]
        self.assertIn('crates/one/src/lib.rs', drivers,
                      'a crate directory must contribute the entry point under src/')
        self.assertNotIn('crates/one/src/child.rs', drivers,
                         'a module reached by `mod` is not an entry point')

    def test_a_workspace_directory_contributes_every_crate(self) -> None:
        """Walk for each manifest, so a directory of crates expands to all of them."""
        drivers = [driver for driver, _ in self.command._drivers(self.root / 'crates')]
        self.assertEqual(sorted(drivers),
                         ['crates/one/src/lib.rs', 'crates/one/tests/it.rs',
                          'crates/two/src/main.rs'],
                         'the workspace directory must expand to every crate entry point')

    def test_drivers_are_repository_relative(self) -> None:
        """Name drivers from the repository, not from the argument.

        The walk is given ``ROOT`` and refuses a driver that leaves it. Naming
        a driver relative to the argument put the two out of step as soon as
        the argument was not the root.
        """
        roots = {root for _, root in self.command._drivers(self.root / 'crates')}
        self.assertEqual(roots, {self.root},
                         'every driver must be resolved against the repository root')
        drivers = [driver for driver, _ in self.command._drivers(self.root)] + \
                  [driver for driver, _ in self.command._drivers(self.root / 'crates')]
        self.assertTrue(all(not Path(driver).is_absolute() for driver in drivers),
                        'a driver must stay repository-relative so an absolute path cannot escape')

    def test_an_argument_outside_the_repository_is_refused(self) -> None:
        """Refuse a path the audit does not own, rather than reading it."""
        with self.assertRaises(self.command.TrustAuditError) as raised:
            self.command._drivers(self.root.parent)
        self.assertIn('outside the repository', str(raised.exception),
                      'the refusal must say the argument left the repository')

    def test_a_directory_with_no_rust_is_refused(self) -> None:
        """Keep the empty-directory refusal, which is what an empty audit would hide."""
        self._write('docs/notes.txt', 'nothing to audit\n')
        with self.assertRaises(self.command.TrustAuditError) as raised:
            self.command._drivers(self.root / 'docs')
        self.assertIn('contains no Rust entry point', str(raised.exception),
                      'a directory with no entry point must fail rather than audit nothing')

    def test_a_file_argument_is_its_own_driver(self) -> None:
        """Audit a named file directly, which is the form the docs show first."""
        drivers = list(self.command._drivers(self.root / 'crates/one/src/lib.rs'))
        self.assertEqual(drivers, [('crates/one/src/lib.rs', self.root)],
                         'a file argument must be its own repository-relative driver')


class StandaloneEntryPoint(unittest.TestCase):
    """Run the script the way its shebang does, over its own declared dependencies.

    The cases above load the command in-process, so they exercise the discovery
    helpers without proving the thing a user invokes. They cannot catch a
    missing PEP 723 dependency either: the test environment installs
    ``scripts/requirements.txt``, which happens to pin what the script imports.
    Running it as a subprocess with the mode Git records and the dependencies
    the script itself declares is the only check that reaches the real entry
    point.
    """

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Invoke the script from the repository root, as its documentation shows."""
        return subprocess.run(
            [str(SCRIPTS / 'trust_audit.py'), *arguments],
            capture_output=True, check=False, text=True, timeout=180, cwd=ROOT,
        )

    def test_the_documented_entry_point_is_executable(self) -> None:
        """Require the executable bit, because the docs show the path being run directly.

        ``git ls-files -s`` reports the mode Git will check out, which is the
        mode a fresh clone gets; the working tree's own bit would hide a mode
        that was never committed.
        """
        recorded = subprocess.run(
            ['git', 'ls-files', '-s', '--', 'scripts/trust_audit.py'],
            capture_output=True, check=True, text=True, cwd=ROOT,
        ).stdout
        self.assertIn('100755', recorded,
                      'scripts/trust_audit.py is documented as runnable, so Git must record it executable')

    def test_standalone_entrypoint_reports_json_for_one_source(self) -> None:
        """Print the audit as JSON, using only the dependencies the script declares."""
        result = self._run('crates/combobulate-kernel/src/lib.rs')
        self.assertEqual(result.returncode, 0,
                         f'auditing a source must succeed: {result.stderr}')
        audited = json.loads(result.stdout)
        self.assertEqual([entry['source'] for entry in audited],
                         ['crates/combobulate-kernel/src/lib.rs'],
                         'the audit names the source it read')
        self.assertIsInstance(audited[0]['items'], list,
                              'each audited source reports its trusted items as a list')

    def test_standalone_entrypoint_exits_non_zero_and_says_why(self) -> None:
        """Reject a path that does not exist with status 1 rather than an empty audit."""
        result = self._run('scratch/no-such-source.rs')
        self.assertEqual(result.returncode, 1,
                         'a path that cannot be audited must fail rather than audit nothing')
        self.assertIn('does not exist', result.stderr,
                      'the refusal names the reason')
        self.assertEqual(result.stdout, '',
                         'a refused audit writes no JSON, so a caller cannot read it as an empty result')


if __name__ == '__main__':
    unittest.main()
