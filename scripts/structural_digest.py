"""Digest a recorded verifier input by its structure rather than its bytes.

A verifier record binds the inputs a verdict depends on. Hashing bytes made
that binding break on a reformat or a comment edit, which changes nothing the
verifiers saw. This module hashes each input's parsed form instead, so only a
real change to what was parsed moves the digest. The generators and the digest
test both call :func:`structural_digest`, so they cannot drift apart.

Each digest carries the ``ast-sha256:`` prefix. A plain 64-digit hex value is a
legacy byte digest and is never accepted as a structural one.

The route depends on the file type:

* ``.toml`` and ``Cargo.lock``: parsed, then canonical JSON (sorted keys).
* ``.json``: parsed, then canonical JSON.
* ``.rs``: the tree-sitter-rust syntax tree with plain comments dropped. Doc
  comments are kept because rustdoc turns them into ``#[doc]`` attributes.
  Source that does not parse cleanly is refused rather than hashed.
* ``.py``: the ``ast`` dump of the parsed module plus its PEP 723 script
  metadata block, which ``uv run --script`` reads from comments.
* ``.sh`` and ``VERSION``: shell has no standard parser, so the text is
  normalised instead: comment-only and blank lines are dropped (a leading
  shebang is kept) and trailing whitespace is stripped, except after a
  continuation backslash. This is the honest limit: a comment-like line inside
  a here-document is also dropped. A ``VERSION`` file must hold exactly one line,
  as the build's pin reader requires.

The ``ast-sha256:`` prefix names the normalisation revision. Changing any rule
above, or bumping the pinned tree-sitter packages in a way that alters the
tree, must change the prefix so an older record cannot read as current.

For example::

    structural_digest(Path('rust-toolchain.toml'))
    # 'ast-sha256:...'
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from pathlib import Path

PREFIX = 'ast-sha256:'

_COMMENTS = frozenset({'line_comment', 'block_comment'})
_DOC_MARKERS = frozenset({'outer_doc_comment_marker', 'inner_doc_comment_marker'})


def is_structural_digest(value: str) -> bool:
    """Return whether ``value`` is a versioned structural digest.

    Examples
    --------
    >>> is_structural_digest('a' * 64)
    False
    """
    digest = value.removeprefix(PREFIX)
    return (
        value.startswith(PREFIX)
        and len(digest) == 64
        and all(character in '0123456789abcdef' for character in digest)
    )


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
        # Verbatim: trailing whitespace in a doc comment is part of the doc
        # attribute rustdoc sees, so it is content rather than layout.
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


def _shell_form(text: str) -> str:
    """Return shell text without comment-only lines, blanks, or trailing space."""
    kept = []
    for number, line in enumerate(text.splitlines()):
        stripped = line.rstrip()
        if not stripped.strip():
            continue
        if stripped.endswith('\\'):
            # Whitespace after a continuation backslash escapes the space
            # instead of the newline, so it changes what the shell runs.
            stripped = line.rstrip('\r\n')
        if stripped.lstrip().startswith('#') and not (
            number == 0 and stripped.startswith('#!')
        ):
            continue
        kept.append(stripped)
    return '\n'.join(kept)


def _version_form(text: str, path: Path) -> str:
    """Return the single pin a ``VERSION`` file holds, refusing anything else.

    The build's pin reader rejects a multiline file, so a blank or extra line
    is a real defect that must not hash as the same pin.
    """
    pin = text.removesuffix('\n')
    if not pin.strip() or '\n' in pin:
        raise ValueError(f'{path}: a VERSION file must hold exactly one line')
    return pin.strip()


def _python_form(text: str) -> str:
    """Return the module tree plus its PEP 723 script metadata, if any.

    ``uv run --script`` reads dependencies from a comment block, so that block
    decides what the script executes and is content rather than a comment.
    """
    metadata = re.search(
        r'(?m)^# /// script$(?P<body>(?:\n#(?: .*)?$)*?)\n# ///$', text
    )
    block = ''
    if metadata:
        block = '\n'.join(
            line.removeprefix('# ').removeprefix('#')
            for line in metadata.group('body').splitlines()
        )
    return _canonical_json([block, ast.dump(ast.parse(text))])


def _form(path: Path) -> str:
    """Return the canonical parsed form of ``path`` for its file type."""
    suffix = path.suffix
    if suffix == '.rs':
        return _rust_form(path.read_bytes())
    text = path.read_text(encoding='utf-8')
    if suffix == '.toml' or path.name == 'Cargo.lock':
        return _canonical_json(tomllib.loads(text))
    if suffix == '.json':
        return _canonical_json(json.loads(text))
    if suffix == '.py':
        return _python_form(text)
    if suffix == '.sh' or path.name == 'VERSION':
        return _version_form(text, path) if path.name == 'VERSION' else _shell_form(text)
    raise ValueError(
        f'no structural digest is defined for {path.name}; '
        'a byte fallback would reintroduce brittle digests'
    )


def structural_digest(path: Path) -> str:
    """Return the versioned structural digest of the file at ``path``.

    Examples
    --------
    Reformatting TOML leaves the digest alone::

        # a = 1  ->  a   =   1  # comment
    """
    try:
        form = _form(path)
    except (ValueError, SyntaxError, UnicodeDecodeError) as error:
        # TOML and JSON decode errors are ValueError subclasses; name the file
        # so a failing generator or test says which input and why.
        raise ValueError(f'cannot digest {path}: {error}') from error
    return PREFIX + hashlib.sha256(form.encode('utf-8')).hexdigest()
