"""Check that every PEP 723 script declares what it imports.

``uv run --script`` builds the environment from the script's own metadata
block, so a third-party import that the block omits is absent on a cold machine
even when it is installed here. That is how a green local run and a red hosted
run can disagree: the local environment was built when something else had
already installed the package.

Each check reads the metadata block and the import graph beneath the script,
so it reports the mismatch statically and needs no network or environment.

For example::

    python3 -m unittest test_script_dependencies
"""

from __future__ import annotations

import ast
import re
import sys
import tempfile
import tomllib
import unittest
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]

_METADATA = re.compile(r'^# /// script\n(?P<body>.*?)^# ///', re.S | re.M)

# A distribution name differs from its import name often enough that guessing
# would produce false failures; these are the spellings this repository uses.
_DISTRIBUTION_NAMES = {'yaml': 'pyyaml', 'tree_sitter': 'tree-sitter'}


def _is_script(path: Path) -> bool:
    """Return whether ``path`` carries a ``uv run --script`` metadata block."""
    return bool(_METADATA.search(path.read_text(encoding='utf-8')))


def _scripts() -> Iterator[Path]:
    """Yield every Python script carrying a PEP 723 metadata block."""
    return (path for path in sorted(SCRIPTS.glob('*.py')) if _is_script(path))


def _is_absolute_import_from(node: ast.AST) -> bool:
    """Return whether ``node`` imports from an absolute, named module."""
    if not isinstance(node, ast.ImportFrom):
        return False
    return node.level == 0 and bool(node.module)


def _imported_modules(path: Path) -> Iterator[str]:
    """Yield each absolute module ``path`` imports, dotted names included."""
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif _is_absolute_import_from(node):
            yield node.module


def _local_sources(module: str) -> list[Path]:
    """Return the files holding local module ``module``, or nothing if absent."""
    for candidate in (SCRIPTS.joinpath(*module.split('.')),):
        if candidate.with_suffix('.py').exists():
            return [candidate.with_suffix('.py')]
        if candidate.is_dir():
            return sorted(candidate.rglob('*.py'))
    return []


def _resolve_module(module: str, visited: set[Path]) -> set[str]:
    """Return what importing ``module`` costs the script's environment.

    A standard-library module costs nothing, a module the repository itself
    supplies costs whatever its own imports cost, and anything else must be
    declared.
    """
    root = module.split('.')[0]
    if root in sys.stdlib_module_names:
        return set()
    local = _local_sources(module)
    if local:
        return {
            name
            for source in local
            for name in _third_party_imports(source, visited)
        }
    return {root}


def _third_party_imports(path: Path, seen: set[Path] | None = None) -> set[str]:
    """Return every non-stdlib, non-local module the script tree imports.

    Local modules are followed, because the script's environment must satisfy
    their imports too: ``kernel_record`` reaches ``tree_sitter`` only lazily,
    which a static scan of the script alone would miss.
    """
    visited = seen if seen is not None else set()
    if path in visited:
        return set()
    visited.add(path)
    return {
        name
        for module in _imported_modules(path)
        for name in _resolve_module(module, visited)
    }


def _normalise(name: str) -> str:
    """Return a distribution name in its PEP 503 comparison form."""
    return re.sub(r'[-_.]+', '-', name).lower()


def _requirement_name(spec: str) -> str:
    """Return the distribution name from a PEP 508 requirement string.

    Splitting on ``=`` alone would cut ``jsonschema>=4,<5`` at the ``>`` and
    keep the operator, so the name ends before any version specifier.
    """
    return re.split(r'[<>=!~\[; ]', spec, maxsplit=1)[0]


def _declared(script: Path) -> tuple[set[str], str]:
    """Return the block's dependency names and its interpreter specifier.

    PEP 723 defines the block as TOML, so it is parsed as TOML rather than
    with a regular expression. A pattern cannot find the end of a list whose
    entries contain brackets: ``jsonschema[format]>=4,<5`` closes the match at
    the ``]`` inside the requirement, and the truncated text then fails to
    evaluate or, worse, evaluates to the wrong list.
    """
    block = _METADATA.search(script.read_text(encoding='utf-8')).group('body')
    # Every line of the block is a Python comment; the TOML begins once its
    # ``# `` leader is removed.
    text = '\n'.join(
        line[2:] if line.startswith('# ') else line[1:]
        for line in block.splitlines()
    )
    metadata = tomllib.loads(text)
    specs = metadata.get('dependencies', [])
    names = {_normalise(_requirement_name(spec)) for spec in specs}
    return names, metadata.get('requires-python', '')


@dataclass(frozen=True)
class _Script:
    """One script's declared dependencies beside what it imports."""

    path: Path
    declared: set[str]
    imported: set[str]

    @property
    def undeclared(self) -> set[str]:
        """Return the imported distributions the metadata block omits."""
        return {_normalise(_DISTRIBUTION_NAMES.get(name, name)) for name in self.imported} - self.declared


class ScriptDependencyTests(unittest.TestCase):
    """Keep each script's declared environment able to import what it runs."""

    def test_every_script_declares_what_it_imports(self) -> None:
        """An undeclared import fails on a cold machine, not here.

        A leftover package in a warm environment hides the omission, so the
        check is static: the metadata block must name every distribution the
        script tree reaches.
        """
        missing = {}
        for script in _scripts():
            declared, _ = _declared(script)
            undeclared = _Script(script, declared, _third_party_imports(script)).undeclared
            if undeclared:
                missing[script.name] = sorted(undeclared)

        self.assertEqual(
            missing,
            {},
            f'PEP 723 blocks omit imported distributions: {missing}',
        )

    def test_the_kernel_record_parser_is_declared(self) -> None:
        """The record's Rust parser is reached lazily and must still be declared.

        ``kernel_record`` imports ``tree_sitter`` inside the function that
        digests Rust source. Nothing in the importing script's own text names
        it, which is exactly the case a source-only scan would pass.
        """
        script = SCRIPTS / 'verus_kernel.py'

        declared, _ = _declared(script)

        self.assertIn(
            'tree-sitter',
            declared,
            'verus_kernel.py must declare tree-sitter, which kernel_record imports',
        )
        self.assertIn(
            'tree-sitter-rust',
            declared,
            'verus_kernel.py must declare tree-sitter-rust for the Rust grammar',
        )

    def test_the_parser_grammar_pins_an_interpreter_with_wheels(self) -> None:
        """``tree-sitter-rust`` publishes abi3 wheels only up to CPython 3.14.

        Under a free-threaded 3.15 interpreter uv finds no wheel and builds
        the grammar from source, which fails. A ``requires-python`` open above
        3.14 therefore turns a missing dependency into a broken build.
        """
        _, specifier = _declared(SCRIPTS / 'verus_kernel.py')

        self.assertIn(
            '<3.15',
            specifier,
            f'verus_kernel.py must exclude 3.15, which has no grammar wheel; got {specifier!r}',
        )


class MetadataParsingTests(unittest.TestCase):
    """Parse the PEP 723 block as the TOML it is, not as a bracketed list."""

    def declared_from(self, block: str) -> tuple[set[str], str]:
        """Return the names and specifier a metadata body declares."""
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'script.py'
            script.write_text(
                f'# /// script\n{block}# ///\nprint("hi")\n',
                encoding='utf-8',
            )
            return _declared(script)

    def test_a_plain_requirement_is_read(self) -> None:
        """The common case: one pinned distribution and no extras."""
        names, specifier = self.declared_from(
            '# dependencies = ["cyclopts==5.2.0"]\n# requires-python = ">=3.14"\n'
        )

        self.assertEqual(names, {'cyclopts'}, f'expected only cyclopts, got {names}')
        self.assertEqual(specifier, '>=3.14', f'expected the specifier, got {specifier!r}')

    def test_a_requirement_with_extras_is_read_whole(self) -> None:
        """A bracket inside a requirement must not end the list.

        ``jsonschema[format]>=4,<5`` contains a ``]``, so a pattern that
        matched to the first one would truncate the list and either fail to
        evaluate or silently drop the requirements after it.
        """
        names, _ = self.declared_from(
            '# dependencies = ["jsonschema[format]>=4,<5", "PyYAML==6.0.3"]\n'
        )

        self.assertEqual(
            names,
            {'jsonschema', 'pyyaml'},
            f'both requirements must be read, got {names}',
        )

    def test_a_multi_line_list_is_read(self) -> None:
        """A list split across lines is still one TOML array."""
        names, _ = self.declared_from(
            '# dependencies = [\n#     "cyclopts==5.2.0",\n#     "cuprum==0.1.0",\n# ]\n'
        )

        self.assertEqual(
            names,
            {'cyclopts', 'cuprum'},
            f'every line of the list must be read, got {names}',
        )


if __name__ == '__main__':
    unittest.main()
