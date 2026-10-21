"""Own the ADR filename convention shared by the register and freeze checks.

An ADR lives at ``docs/adrs/adr-nnnn-title-slug.md``: ``nnnn`` is the serial
number in the document's H1 and ``title-slug`` is the kebab-case ASCII
rendering of the title without the ``Architectural decision record (ADR)
nnnn:`` prefix. ``check_adr_files`` uses the rule to reject a misnamed ADR, and
the freeze relocation check uses it to prove a moved ADR landed at the name its
own title requires. This module is a naming rule, not a filesystem or Git
adapter; it performs no I/O.
"""
from __future__ import annotations

import re
import unicodedata

ADR_NAME = re.compile(r'^docs/adrs/adr-[0-9]{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$', re.ASCII)
ADR_TITLE = re.compile(r'^# Architectural decision record \(ADR\) ([0-9]{4}): (.+)$')


def title_slug(title: str) -> str:
    """Render a title as the style guide's kebab-case ASCII slug.

    Accented letters are transliterated to their base letters and other
    punctuation or symbols are dropped rather than encoded::

        >>> title_slug('Pre-1.0 API, café policy')
        'pre-1-0-api-cafe-policy'
    """
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '-', ascii_title.lower()).strip('-')


def canonical_adr_path(text: str) -> str | None:
    """Return the canonical path implied by an ADR's numbered H1 title.

    A well-formed title names its own file::

        >>> canonical_adr_path('# Architectural decision record (ADR) 0002: Governance authority\\n')
        'docs/adrs/adr-0002-governance-authority.md'

    A document without a numbered H1 has no canonical path, so the result is
    ``None`` and any caller that requires the convention must reject it.
    """
    first_line = text.partition('\n')[0]
    match = ADR_TITLE.fullmatch(first_line)
    if match is None:
        return None
    return f'docs/adrs/adr-{match.group(1)}-{title_slug(match.group(2))}.md'
