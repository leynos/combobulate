"""Match ADR-0009's trust vocabulary against lexed Rust (DL-17, VO-9).

The audit exists to answer one question about a proof: *what did the author
tell the verifier to accept without proof?* ADR-0009 fixes the vocabulary that
can do so; this module decides which occurrences of those words are really
trust, and which are ordinary Rust that merely spells the same.

That distinction cannot be made by searching for the words. `assume` is also an
ordinary identifier, `should_panic` is a standard test attribute, and `external`
appears in prose and in paths. DL-17 therefore resolves a word to trust only
through a context that gives it meaning:

(i) a Kani item reached through a path rooted at `kani`, including one inside a
``use`` tree or a ``cfg_attr``;
(ii) a Verus item inside a ``verus!`` body, a ``verifier``/``verus_verify``/
``verus_spec`` attribute, or a ``cfg_attr`` carrying one of those;
(iii) any unqualified vocabulary word in a file that imports from one of those
roots.

Rule (iii) is the fail-closed direction, and this module reads it slightly wider
than DL-17's wording: a *named* import such as ``use kani::assume;`` triggers it
as well as a glob or an alias. A bare ``assume(..)`` after a named import is a
real trust use that no other rule reaches, so excluding it would leave the audit
unsound in exactly the case the rule exists to catch. The deliberate consequence
is a superset: a file that imports one Kani name and separately defines its own
``external`` item reports the latter too. An audit that over-reports is safe —
the record must then cover the item — where one that under-reports is not.

The scan refuses source it cannot reason about rather than reporting an empty
audit: ``include!``, ``paste!``, and ``concat_idents!`` generate or splice code
the lexer never sees. A ``#[path = "…"]`` target is reported to the caller
instead of being refused, because the caller knows the repository root and can
resolve it; :mod:`docs_validation.trust_audit.command` does that and refuses a
target outside the repository.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .lexer import Kind, Token, TrustAuditError, literal_body, tokenize
from .structure import (
    attribute_spans,
    matching,
    opening_bracket,
    path_value,
    previous_closer,
    skip_visibility,
)
from .use_tree import alias_bindings, statement_end, use_roots

# ADR-0009 plus DL-17's stated additions. `any_where` is Kani's own assumption
# surface; the Verus list gains the three forms DL-17 names.
KANI_VOCABULARY = frozenset({'assume', 'any_where', 'stub', 'stub_verified', 'should_panic'})
VERUS_VOCABULARY = frozenset({
    'assume', 'admit', 'external_body', 'external', 'external_fn_specification',
    'assume_specification', 'external_type_specification',
    'external_trait_specification', 'exec_allows_no_decreases_clause',
})
VOCABULARY = KANI_VOCABULARY | VERUS_VOCABULARY

KANI_ROOT = 'kani'
VERUS_ROOTS = frozenset({'vstd', 'verus_builtin'})
TRUST_ROOTS = frozenset({KANI_ROOT}) | VERUS_ROOTS
VERUS_ATTRIBUTE_HEADS = frozenset({'verifier', 'verus_verify', 'verus_spec'})
# Macros that produce code the lexer never sees, so the scan cannot be complete.
OPAQUE_MACROS = frozenset({'include', 'paste', 'concat_idents'})


@dataclass(frozen=True, slots=True)
class TrustItem:
    """One trusted item, located by path, line, and column.

    The location is the item's own token, not its enclosing statement, because
    DL-16 compares the scanner's ``(item, location)`` multiset with the record's
    and two uses on one line must stay distinguishable. ``item`` is the word as
    written, so a qualified ``kani::assume`` and a bare ``assume`` reached by
    rule (iii) stay distinguishable too.
    """

    item: str
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class ModuleReference:
    """A module file this source compiles, for the caller to resolve and scan.

    ``path`` is set when a ``#[path = "…"]`` attribute names the file directly;
    otherwise the caller derives it from ``name`` by Rust's usual search.

    ``enclosing`` lists the inline modules the declaration sits inside, outermost
    first. It is what separates ``mod nested { mod trusted; }`` in ``src/lib.rs``
    — which compiles ``src/nested/trusted.rs`` — from a top-level
    ``mod trusted;``, which compiles ``src/trusted.rs``. Dropping it audits the
    wrong file, and where the wrong file exists as a decoy the audit reports a
    clean scan of code the crate never compiles.
    """

    name: str
    path: str | None
    line: int
    column: int
    enclosing: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Everything one source file contributes to an audit."""

    items: tuple[TrustItem, ...]
    modules: tuple[ModuleReference, ...]


def scan(text: str, procedural_macro: bool = False) -> ScanResult:
    """Report every trusted item in one Rust source.

    Parameters
    ----------
    text
        Rust source text; it need not be a complete or valid crate.
    procedural_macro
        Scan string literals for vocabulary too. A proc-macro crate's literals
        can become code, so its vocabulary is not confined to code position.

    Returns
    -------
    ScanResult
        Items in source order, each reported once, plus any ``#[path]`` target
        the caller must resolve.

    Raises
    ------
    TrustAuditError
        If the source never terminates a comment or literal, or uses a macro
        whose expansion the scan cannot see.

    Examples
    --------
    scan('kani::assume(x);') reports ``assume`` at line 1, column 7;
    scan('// kani::assume') reports nothing, because the comment contributes no
    code token.
    """
    tokens = tokenize(text)
    _refuse_opaque_macros(tokens)
    context = _Context(tokens, procedural_macro)
    return ScanResult(context.run(), _module_references(tokens))


def _refuse_opaque_macros(tokens: tuple[Token, ...]) -> None:
    """Fail closed on a macro whose expansion the scanner cannot read."""
    for current, following in zip(tokens, tokens[1:], strict=False):
        if (current.kind is Kind.IDENT and current.text in OPAQUE_MACROS
                and following.text == '!'):
            raise TrustAuditError(
                f'{current.text}! at line {current.line}, column {current.column} '
                'generates code the trust audit cannot read'
            )


class _Context:
    """Hold one file's lexical facts and accumulate its items.

    The facts (which roots the file imports, where its ``verus!`` bodies and
    Verus attributes are) are file-scoped: rule (iii) is decided by an import on
    the other side of the file from the use it makes ambiguous.
    """

    def __init__(self, tokens: tuple[Token, ...], procedural_macro: bool) -> None:
        """Record the tokens and the file-scoped facts the rules depend on."""
        self.tokens = tokens
        self.imported_roots = _imported_roots(tokens)
        # A trust root may be in scope under another name. `use kani as k;`
        # makes `k::assume` the same call as `kani::assume`, and a scan that
        # only matched the literal root would report nothing for the file.
        self.kani_names = alias_bindings(tokens, KANI_ROOT)
        self.verus_regions = _verus_regions(tokens)
        self.items: list[TrustItem] = []
        self._procedural_macro = procedural_macro

    def run(self) -> tuple[TrustItem, ...]:
        """Apply the three rules to every token in source order."""
        for index, token in enumerate(self.tokens):
            if token.kind is Kind.LITERAL:
                if self._procedural_macro:
                    self._scan_literal(token)
            elif token.kind is Kind.IDENT:
                self._classify(index, token)
        return tuple(self.items)

    def _classify(self, index: int, token: Token) -> None:
        """Report the token if any rule makes it trust.

        Each rule uses the vocabulary of the system it names: a ``kani::`` path
        is Kani's, a Verus body or attribute is Verus'. A Kani-only word inside
        a ``verus!`` body is not Verus trust and is not reported — rule (iii)
        already covers the case where a file imports from a trust root, and
        reporting it here would make the audit's location claim misleading.
        """
        if self._is_kani_path(index):
            self._report(token.text, token)
        elif self._is_verus_context(index):
            if token.text in VERUS_VOCABULARY:
                self._report(token.text, token)
        elif self.imported_roots and _is_bare_use(self.tokens, index):
            self._report_if_vocabulary(token.text, token)

    def _is_kani_path(self, index: int) -> bool:
        """Report whether this token is the last segment of a ``kani::`` path.

        A ``use kani as k;`` in the file makes ``k::`` the same qualified path,
        so the root position is matched against the literal root and against
        every local name the file binds that root to.
        """
        token = self.tokens[index]
        return (token.text in KANI_VOCABULARY and index >= 2
                and self.tokens[index - 1].text == '::'
                and self.tokens[index - 2].text in self.kani_names)

    def _is_verus_context(self, index: int) -> bool:
        """Report whether this index sits in a Verus body or attribute."""
        return any(start <= index <= end for start, end in self.verus_regions)

    def _report_if_vocabulary(self, word: str, token: Token) -> None:
        """Report a vocabulary word found in a context that gives it meaning."""
        if word in VOCABULARY:
            self._report(word, token)

    def _report(self, item: str, token: Token) -> None:
        """Record one item, skipping a token an earlier rule already claimed.

        One token can satisfy several rules — the ``stub`` in
        ``kani::stub(..)`` inside a ``cfg_attr`` satisfying both (i) and (ii) —
        and the audit must report it once.
        """
        if any(existing.item == item and existing.line == token.line
               and existing.column == token.column for existing in self.items):
            return
        self.items.append(TrustItem(item, token.line, token.column))

    def _scan_literal(self, token: Token) -> None:
        """Report vocabulary inside a proc-macro crate's string literal.

        The escaped body keeps its backslashes, so a ``\\n`` there is two
        characters rather than a newline. Translating it would make the offset
        arithmetic disagree with what the author sees in their editor, so the
        body is scanned as written and positions count characters.
        """
        offset, body = literal_body(token.text)
        for match in _QUALIFIED_KANI.finditer(body):
            if match[1] in KANI_VOCABULARY:
                self._report_at(match[1], token, offset + match.start(1))
        for match in _WORD.finditer(body):
            if match[0] in VOCABULARY:
                self._report_at(match[0], token, offset + match.start())

    def _report_at(self, item: str, token: Token, offset: int) -> None:
        """Locate a literal match precisely enough that two stay distinct.

        Positions outside a literal are token positions, which the lexer already
        counts. Inside one, the token is opaque, so the offset is measured from
        the token's start and advanced over any newline the literal contains.
        """
        prefix = token.text[:offset]
        line = token.line + prefix.count('\n')
        column = (len(prefix) - prefix.rindex('\n') if '\n' in prefix
                  else token.column + offset)
        if any(item_.item == item and (item_.line, item_.column) == (line, column)
               for item_ in self.items):
            return
        self.items.append(TrustItem(item, line, column))


_QUALIFIED_KANI = re.compile(r'\bkani\s*::\s*([A-Za-z_][A-Za-z0-9_]*)')
_WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _is_bare_use(tokens: tuple[Token, ...], index: int) -> bool:
    """Report whether rule (iii) makes this token a bare use.

    A word after ``::`` belongs to a path and a word after ``.`` to a field or
    method; neither is the unqualified use rule (iii) is about. Rule (i) has
    already claimed the ``kani::`` case, so only the remaining positions matter.
    """
    previous = tokens[index - 1] if index else None
    return previous is None or previous.text not in ('::', '.')


def _imported_roots(tokens: tuple[Token, ...]) -> frozenset[str]:
    """Return the trust roots this file imports, by ``use`` or ``extern crate``.

    Every root of every statement counts, not just its leading word.
    ``use {std::mem, kani};`` imports ``kani`` as surely as the ungrouped form
    does, and reading only the first identifier would leave it out — which
    quietly disables rule (iii) for that file.

    ``extern crate kani;`` is the same import spelled without a ``use``, and it
    likewise makes a bare ``assume`` resolve to Kani, so it counts too.
    """
    roots = set()
    for index, token in enumerate(tokens):
        if token.kind is not Kind.IDENT:
            continue
        if token.text == 'extern' and index + 2 < len(tokens) and tokens[index + 1].text == 'crate':
            roots.add(tokens[index + 2].text)
        if token.text != 'use':
            continue
        end = statement_end(tokens, index + 1)
        roots.update(root for root, _ in use_roots(tokens, index + 1, end))
    return frozenset(roots & TRUST_ROOTS)


def _verus_regions(tokens: tuple[Token, ...]) -> tuple[tuple[int, int], ...]:
    """Return the token ranges whose identifiers carry Verus' own vocabulary.

    Two forms create a region: a ``verus!`` macro body, and a Verus attribute
    anywhere in an attribute list, including one nested in a ``cfg_attr``.
    """
    regions = list(_verus_bodies(tokens))
    for open_index, close_index in attribute_spans(tokens):
        regions.extend(_verus_attribute_regions(tokens, open_index, close_index))
    return tuple(regions)


def _verus_bodies(tokens: tuple[Token, ...]) -> tuple[tuple[int, int], ...]:
    """Locate each ``verus! { … }`` body, tolerating nesting."""
    bodies = []
    for index in range(len(tokens) - 2):
        if (tokens[index].text == 'verus' and tokens[index + 1].text == '!'
                and tokens[index + 2].text == '{'):
            bodies.append((index + 3, matching(tokens, index + 2, '{', '}')))
    return tuple(bodies)


def _verus_attribute_regions(tokens: tuple[Token, ...],
                             open_index: int, close_index: int) -> tuple[tuple[int, int], ...]:
    """Return the range of an attribute whose identifiers are Verus vocabulary."""
    head = tokens[open_index + 1] if open_index + 1 < close_index else None
    if head is None:
        return ()
    if head.text in VERUS_ATTRIBUTE_HEADS:
        return ((open_index + 1, close_index - 1),)
    if head.text == 'cfg_attr' and _carries_verus(tokens, open_index + 2, close_index):
        return ((open_index + 1, close_index - 1),)
    return ()


def _carries_verus(tokens: tuple[Token, ...], start: int, end: int) -> bool:
    """Report whether a ``cfg_attr`` carries a Verus attribute after its predicate."""
    return any(token.kind is Kind.IDENT and token.text in VERUS_ATTRIBUTE_HEADS
               for token in tokens[start:end])


def _module_references(tokens: tuple[Token, ...]) -> tuple[ModuleReference, ...]:
    """Collect the module files this source compiles.

    A ``mod x { … }`` body is already in this file, so only ``mod x;`` names a
    file elsewhere. Its ``#[path]`` attribute, when present, is what decides
    which file that is; without one the caller searches by Rust's rules. Both
    are surfaced rather than resolved here, because resolution needs a
    repository root this module does not have.

    An inline module still contributes a *directory*, because a ``mod x;``
    inside it compiles ``…/x.rs`` relative to the module path, not to the
    declaring file's own directory. The enclosing inline names travel with the
    reference so the caller can apply that rule.
    """
    references = []
    spans = dict(attribute_spans(tokens))
    inline = _InlineModules(tokens)
    for index, token in enumerate(tokens):
        if token.kind is not Kind.IDENT or token.text != 'mod':
            continue
        name = tokens[index + 1] if index + 1 < len(tokens) else None
        following = tokens[index + 2] if index + 2 < len(tokens) else None
        if name is None or name.kind is not Kind.IDENT or following is None:
            continue
        if following.text != ';':
            continue
        references.append(ModuleReference(name.text, _path_attribute(tokens, spans, index),
                                         name.line, name.column, inline.enclosing(index)))
    return tuple(references)


class _InlineModules:
    """Report the inline ``mod`` names that enclose a token.

    A single left-to-right walk pairs every ``mod name {`` with the ``}`` that
    closes it, so the enclosing chain at any index is the stack the walk holds
    there. Building that once per file keeps the lookup from re-scanning the
    token stream for every ``mod`` declaration.
    """

    def __init__(self, tokens: tuple[Token, ...]) -> None:
        """Pair every inline module's braces and record each token's chain."""
        self._chains: list[tuple[str, ...]] = [()] * len(tokens)
        stack: list[tuple[str, int]] = []
        for index, token in enumerate(tokens):
            # A closing brace belongs to the module that *holds* the inline one,
            # so it is popped before the chain is recorded for that position.
            if stack and index == stack[-1][1]:
                stack.pop()
            self._chains[index] = tuple(name for name, _ in stack)
            if (token.kind is Kind.IDENT and token.text == 'mod'
                    and index + 2 < len(tokens) and tokens[index + 1].kind is Kind.IDENT
                    and tokens[index + 2].text == '{'):
                stack.append((tokens[index + 1].text, matching(tokens, index + 2, '{', '}')))

    def enclosing(self, index: int) -> tuple[str, ...]:
        """Return the inline module names enclosing the token at ``index``."""
        return self._chains[index]


def _path_attribute(tokens: tuple[Token, ...], spans: Mapping[int, int],
                    mod_index: int) -> str | None:
    """Return the ``#[path]`` value attached to the item at ``mod_index``.

    The attribute list is the run of ``#[…]`` spans immediately before the
    declaration, but a visibility modifier may sit between the two:
    ``#[path = "x.rs"] pub(crate) mod x;`` attaches the attribute to the
    declaration all the same. So the walk starts by stepping over any
    ``pub``/``pub(...)`` and only then looks for ``]``.

    Every attribute in the run applies to the declaration, so the walk continues
    past an attribute that is not ``#[path]``. Missing that step is not a
    refusal a caller can notice: the module then falls back to Rust's bare
    ``mod x;`` search, which reads a different file from the one the crate
    compiles and can report a clean audit of code that is not in the proof.
    """
    index = skip_visibility(tokens, mod_index - 1)
    while index >= 0:
        if tokens[index].text != ']':
            return None
        opener = opening_bracket(tokens, index)
        if opener is None or opener not in spans:
            return None
        value = path_value(tokens, opener, index)
        if value is not None:
            return value
        index = previous_closer(tokens, opener)
    return None
