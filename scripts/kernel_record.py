"""Digest the files a kernel proof record binds, and name the repository root.

DL-14's identity tuple carries a *structural* digest of the kernel body and of
its specification, so a reformat or a comment edit does not invalidate the
record while a real change does. The same digest binds each script that
decided the recorded verdicts, because a reader must be able to tell which
code produced them.

Only the two file kinds the record binds are understood: Rust sources, which
are parsed with tree-sitter, and the driver scripts, which are hashed through
their Python abstract syntax tree plus their PEP 723 metadata block (``uv run
--script`` reads dependencies from that comment block, so it decides what the
script executes).

A byte digest is offered beside the structural one for the captured logs:
those are prose rather than code, and a reader checking a log against the
record wants the exact bytes.

For example, editing a comment in the kernel body leaves
:func:`structural_digest` unchanged, while adding a loop changes it.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PREFIX = 'ast-sha256:'

_COMMENTS = frozenset({'line_comment', 'block_comment'})
_DOC_MARKERS = frozenset({'outer_doc_comment_marker', 'inner_doc_comment_marker'})
_SCRIPT_BLOCK = re.compile(r'(?m)^# /// script$(?P<body>(?:\n#(?: .*)?$)*?)\n# ///$')


def is_structural_digest(value: str) -> bool:
    """Return whether ``value`` is a versioned structural digest.

    Examples
    --------
    >>> is_structural_digest('a' * 64)
    False
    >>> is_structural_digest(PREFIX + 'a' * 64)
    True
    """
    digest = value.removeprefix(PREFIX)
    return (
        value.startswith(PREFIX)
        and len(digest) == 64
        and all(character in '0123456789abcdef' for character in digest)
    )


def exact_digest(path: Path) -> str:
    """Return the SHA-256 of the file's exact bytes, as captured logs need."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_argument(text: str) -> str:
    """Replace the repository root and home directory with stable markers.

    A committed record that named an absolute worktree path would differ on
    every checkout, so the record would describe one host rather than the code.
    """
    return text.replace(str(ROOT), '<repo>').replace(str(Path.home()), '~')


def portable_text(text: str) -> str:
    """Apply :func:`portable_argument` to a whole captured log."""
    return portable_argument(text)


def structural_digest(path: Path) -> str:
    """Return the versioned structural digest of ``path``.

    Raises
    ------
    ValueError
        When the file's suffix is not one this module understands, or when the
        Rust source does not parse cleanly. Digesting bytes in the second case
        would bind a record to source no verifier could have compiled.
    """
    suffix = path.suffix
    if suffix == '.rs':
        return PREFIX + _hash(_rust_form(path.read_bytes()))
    if suffix == '.py':
        return PREFIX + _hash(_python_form(path.read_text(encoding='utf-8')))
    raise ValueError(f'{path}: no structural form is defined for {suffix!r} files')


def _hash(text: str) -> str:
    """Return the SHA-256 of a normalised form."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _canonical_json(document: object) -> str:
    """Return compact JSON with sorted keys, so layout cannot matter."""
    return json.dumps(
        document, sort_keys=True, separators=(',', ':'), ensure_ascii=True
    )


def _rust_node(node) -> object:  # noqa: ANN001 - tree_sitter is imported lazily
    """Return the canonical form of one syntax node, or ``None`` for noise."""
    if node.type in _COMMENTS:
        if not any(child.type in _DOC_MARKERS for child in node.children):
            return None
        # A doc comment becomes a `#[doc]` attribute, so it is content rather
        # than layout; trailing whitespace inside it is preserved verbatim.
        return ['doc', node.text.decode('utf-8')]
    if node.child_count == 0:
        return [node.type, node.text.decode('utf-8')]
    children = [_rust_node(child) for child in node.children]
    return [node.type, [child for child in children if child is not None]]


def _rust_form(source: bytes) -> str:
    """Return the canonical text of a Rust file's tree without plain comments."""
    import tree_sitter  # noqa: PLC0415 - only Rust inputs need the parser
    import tree_sitter_rust  # noqa: PLC0415

    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_rust.language()))
    root = parser.parse(source).root_node
    if root.has_error:
        raise ValueError('Rust source does not parse cleanly; refusing to digest it')
    return _canonical_json(_rust_node(root))


def _python_form(text: str) -> str:
    """Return the module tree plus its PEP 723 script metadata, if any.

    ``uv run --script`` reads dependencies from that comment block, so the
    block decides what the script executes and is content rather than a
    comment. Dropping it would let a dependency change hash as a no-op.
    """
    metadata = _SCRIPT_BLOCK.search(text)
    block = ''
    if metadata:
        block = '\n'.join(
            line[2:] if line.startswith('# ') else ''
            for line in metadata.group('body').splitlines()
        )
    return _canonical_json([block, ast.dump(ast.parse(text))])
