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
import datetime
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
    """Return shell text without comment-only lines, blanks, or trailing space.

    A line that follows a continuation backslash is part of the same command,
    so it is kept verbatim even when it looks like a comment or a blank.
    """
    kept = []
    continued = False
    for number, line in enumerate(text.splitlines()):
        stripped = line.rstrip()
        if continued:
            kept.append(line)
            continued = line.endswith('\\')
            continue
        if not stripped.strip():
            continue
        if stripped.endswith('\\'):
            # Whitespace after a continuation backslash escapes the space
            # instead of the newline, so it changes what the shell runs.
            stripped = line
            continued = True
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


def lint_tables(manifest_text: str) -> dict[str, dict]:
    """Return the manifest's lint tables by name, from one parse.

    Both ``[lints.<name>]`` and ``[workspace.lints.<name>]`` spellings are
    accepted. The scratch workspace text and the recorded digest are both made
    from this value, so the copy and the digest cannot disagree.

    Raises
    ------
    RuntimeError
        When no lint table exists, or a name is defined under both spellings.
    """
    document = tomllib.loads(manifest_text)
    workspace = document.get('workspace', {}).get('lints', {})
    # ``[lints] workspace = true`` is inheritance, not a table of lints.
    plain = {k: v for k, v in document.get('lints', {}).items() if isinstance(v, dict)}
    if set(workspace) & set(plain):
        raise RuntimeError('a lint table is defined under both lint spellings')
    tables = {**workspace, **plain}
    if not tables:
        raise RuntimeError('the root manifest must define at least one lint table')
    return tables


def _toml_key(key: str) -> str:
    """Return ``key`` as a bare TOML key when it can be, else quoted."""
    return key if re.fullmatch(r'[A-Za-z0-9_-]+', key) else json.dumps(key)


def _toml_value(value: object) -> str:
    """Render a parsed TOML value as TOML text."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, dict):
        inner = ', '.join(f'{_toml_key(k)} = {_toml_value(v)}' for k, v in value.items())
        return '{ ' + inner + ' }' if inner else '{}'
    if isinstance(value, list):
        return '[' + ', '.join(_toml_value(item) for item in value) + ']'
    if isinstance(value, (str, int, float)):
        return json.dumps(value)
    raise ValueError(f'cannot render a {type(value).__name__} lint value')


def render_lint_tables(tables: dict[str, dict]) -> str:
    """Render lint tables as ``[workspace.lints.<name>]`` TOML text.

    Each table is followed by a blank line, so tables can be concatenated.
    """
    chunks = []
    for name, table in tables.items():
        lines = [f'[workspace.lints.{_toml_key(name)}]']
        lines += [f'{_toml_key(k)} = {_toml_value(v)}' for k, v in table.items()]
        chunks.append('\n'.join(lines) + '\n\n')
    return ''.join(chunks)


def lint_tables_digest(manifest_text: str) -> str:
    """Return the structural digest of a manifest's lint tables.

    Only the parsed lint tables are hashed, so an unrelated dependency edit or
    a reformat leaves the digest alone.
    """
    tables = lint_tables(manifest_text)
    return PREFIX + hashlib.sha256(_canonical_json(tables).encode('utf-8')).hexdigest()


def recorded_channel(command: list[str]) -> str | None:
    """Return the toolchain channel a recorded container command selected.

    The hosted record keeps the channel it built with as a ``RUSTUP_TOOLCHAIN=``
    environment entry of its command; the digest map alone cannot name it.
    """
    for argument in command:
        if argument.startswith('RUSTUP_TOOLCHAIN='):
            return argument.removeprefix('RUSTUP_TOOLCHAIN=')
    return None


_CHANNEL = re.compile(
    r'(?:stable|beta|nightly)(?:-\d{4}-\d{2}-\d{2})?|\d+\.\d+(?:\.\d+)?(?:-beta(?:\.\d+)?)?'
)


def is_rustup_channel(value: object) -> bool:
    """Return whether ``value`` is a channel form rustup accepts.

    A dated channel must carry a real calendar date. That says nothing about
    whether an archive exists for it; only the toolchain install can.
    """
    if not isinstance(value, str) or _CHANNEL.fullmatch(value) is None:
        return False
    dated = re.search(r'(\d{4})-(\d{2})-(\d{2})$', value)
    if dated:
        try:
            datetime.date(*(int(part) for part in dated.groups()))
        except ValueError:
            return False
    return True


def _channel_only_drift(path: Path, expected: str, channel: str | None) -> bool:
    """Return whether only ``toolchain.channel`` separates ``path`` from the record."""
    if not is_rustup_channel(channel):
        return False
    document = tomllib.loads(path.read_text(encoding='utf-8'))
    toolchain = document.get('toolchain')
    if not isinstance(toolchain, dict) or not is_rustup_channel(toolchain.get('channel')):
        return False
    toolchain['channel'] = channel
    rebuilt = PREFIX + hashlib.sha256(_canonical_json(document).encode('utf-8')).hexdigest()
    return rebuilt == expected


def classify_drift(
    root: Path, digests: dict[str, str], command: list[str]
) -> tuple[list[str], str | None]:
    """Split a record's digest mismatches into failures and a toolchain note.

    A mismatch on ``rust-toolchain.toml`` that disappears when the file's
    channel is set back to the recorded one is channel-only drift: it yields a
    note, not a failure. Every other mismatch, including a toolchain change
    beyond the channel, is a failure.

    Returns the failing source names and the note (or ``None``).
    """
    failures: list[str] = []
    note = None
    for relative, expected in digests.items():
        path = root / relative
        if is_structural_digest(expected) and structural_digest(path) == expected:
            continue
        channel = recorded_channel(command)
        if (
            relative == 'rust-toolchain.toml'
            and is_structural_digest(expected)
            and _channel_only_drift(path, expected, channel)
        ):
            current = tomllib.loads(path.read_text(encoding='utf-8'))['toolchain']['channel']
            note = (
                f'Evidence captured for toolchain {channel}; '
                f'evidence missing for the current pin {current}.'
            )
            continue
        failures.append(relative)
    return failures, note
