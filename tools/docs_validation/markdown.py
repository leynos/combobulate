"""Validate design-pack Markdown and semantic generated-content drift.

The repository's separate markdownlint gate owns the inherited engineering
handbook. Parsed token comparison tolerates formatter wrapping and table padding,
while preserving inline text, links, code, nesting, and checkbox state.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from .context import ValidationContext, require

MD = MarkdownIt('commonmark').enable('table')


def headings(text: str) -> set[str]:
    """Return GitHub-style heading anchors; repeated 'Title' adds 'title-1'."""
    ids: set[str] = set()
    seen: dict[str, int] = {}
    tokens = MD.parse(text)
    for index, token in enumerate(tokens):
        if token.type != 'heading_open':
            continue
        title = tokens[index + 1].content.lower().replace('`', '')
        slug = re.sub(r'[^\w\- ]', '', title).replace(' ', '-')
        repeat = seen.get(slug, 0)
        seen[slug] = repeat + 1
        ids.add(slug if not repeat else f'{slug}-{repeat}')
    return ids


def check_text_structure(text: str, path: Path) -> None:
    """Check pack style boundaries; e.g. a missing final newline fails."""
    require(text.endswith('\n'), f'Missing final newline: {path}')
    require('\r' not in text, f'CR newline: {path}')
    require('\u2014' not in text, f'Em dash: {path}')
    require(not re.search(r'[ \t]+$', text, re.M), f'Trailing whitespace: {path}')
    in_fence = False
    for line in text.splitlines():
        if re.match(r'^\s*```', line):
            if not in_fence:
                require(bool(re.match(r'^\s*```\w', line)), f'Fence lacks language: {path}')
            in_fence = not in_fence
        elif in_fence:
            require(len(line) <= 120, f'Code line over 120 columns in {path}: {line[:30]}')
    require(not in_fence, f'Unclosed fence: {path}')


def check_local_link(context: ValidationContext, path: Path, href: str) -> bool:
    """Validate a local href; e.g. '../README.md#title' must resolve inside root."""
    if urlsplit(href).scheme or href.startswith('//'):
        return False
    target, _, anchor = href.partition('#')
    dest = (path.parent / unquote(target)).resolve() if target else path.resolve()
    require(dest.is_relative_to(context.root.resolve()), f'Out-of-pack local link: {href}')
    require(dest.exists(), f'Broken local link: {path}: {href}')
    if anchor and dest.suffix == '.md':
        require(unquote(anchor) in headings(dest.read_text()), f'Broken anchor: {path}: {href}')
    return True


def check_markdown(context: ValidationContext) -> None:
    """Validate the explicit pack files; e.g. unrelated target/*.md stays excluded."""
    files = context.markdown_paths()
    links = 0
    for path in files:
        text = path.read_text(encoding='utf-8')
        check_text_structure(text, path)
        tokens = MD.parse(text)
        h1_count = sum(t.type == 'heading_open' and t.tag == 'h1' for t in tokens)
        require(h1_count == 1, f'Expected one title: {path}')
        for token in tokens:
            for child in token.children or []:
                if child.type == 'link_open':
                    links += check_local_link(context, path, child.attrGet('href') or '')
    context.record('markdown-structure', 'Markdown parses; titles, fences, code widths, whitespace, and local links pass. This is not the repository markdownlint gate.', len(files))
    context.record('local-links', 'All explicit local Markdown links resolve, including anchors where used.', links)


def semantic_tokens(text: str) -> tuple:
    """Normalize formatting only; e.g. wrapped prose equals its single-line form."""
    def normalize(token):
        if token.type == 'inline':
            content = ''
        elif token.type == 'softbreak':
            return ('text', '', 0, (), ' ', (), '')
        else:
            content = token.content
            if token.type == 'text':
                content = content.replace('…', '...')
        children = merge_text(tuple(normalize(child) for child in token.children or []))
        return (token.type, token.tag, token.nesting,
                tuple(sorted((token.attrs or {}).items())), content, children, token.info)

    return tuple(normalize(token) for token in MD.parse(text))


def merge_text(tokens: tuple) -> tuple:
    """Join adjacent text tokens; e.g. a soft line break becomes an ordinary space."""
    result = []
    for token in tokens:
        if result and token[0] == result[-1][0] == 'text':
            previous = result.pop()
            result.append((*previous[:4], previous[4] + token[4], previous[5], previous[6]))
        else:
            result.append(token)
    return tuple(result)


def generated_body(text: str, start: str, end: str) -> str:
    """Extract one ordered marker pair; duplicated or reversed markers fail."""
    require(text.count(start) == text.count(end) == 1,
            'Generated document must have exactly one marker pair')
    before, body = text.split(start)
    require(end not in before, 'Generated document markers are reversed')
    return body.split(end)[0].strip()


def generated_matches(text: str, expected: str, start: str, end: str) -> bool:
    """Compare generated Markdown semantics; padded tables pass, changed cells fail."""
    return semantic_tokens(generated_body(text, start, end)) == semantic_tokens(expected)
