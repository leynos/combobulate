"""Recognize the `comb!` corpus in `spec/macro-grammar.json` (ADR-0007, D08).

This models the corpus, not the macro: precedence climbing over the grammar
file's table, with `|>` split first as the lowest, left-associative operator.
Comparison chains, comparison mixed unparenthesized with `&`, `|`, or `^`,
array `&&` and `||`, `as`, ranges, assignment, and closures outside `host`
blocks are rejected by named rule. Seeded mutations alter one rule each. Task
2.3.1 replays the corpus through `trybuild`, then this recognizer is deleted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN = re.compile(r"\s*(?:(?P<host>host\s*\{)|(?P<word>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)|(?P<number>\d+(?:\.\d+)?)"
                   r"|(?P<op>\|>|<<=|>>=|\.\.=|==|!=|<=|>=|&&|\|\||<<|>>|[-+*/%&|^]=|\.\.|[-+*/%&|^!<>=(),.]))")
REJECTED_INFIX = {'&&': 'logical-operator', '||': 'logical-operator', 'as': 'cast-keyword', '..': 'range',
                  '..=': 'range'}
ASSIGNMENT, BITWISE = re.compile(r'^(?:=|[-+*/%&|^]=|<<=|>>=)$'), {'&', '|', '^'}


@dataclass(frozen=True)
class Parsed:
    """An accepted source and its fully parenthesized tree; e.g. Parsed('(+ a (* b c))')."""

    tree: str


@dataclass(frozen=True)
class Rejected:
    """A rejected source and the grammar rule that rejects it; e.g. Rejected('comparison-chain')."""

    rule: str


class Rejection(Exception):
    """Carry a rejection rule out of the recursive parser."""


@dataclass(frozen=True)
class Node:
    """A parsed operand: its tree, its top operator (None for atoms), and whether it was parenthesized."""

    tree: str
    op: str | None = None
    grouped: bool = False


def tokenize(source: str) -> list[str]:
    """Split a source string into DSL tokens, treating a host block as one token.

    Parameters
    ----------
    source : str
        Expression text from the grammar corpus.

    Returns
    -------
    list[str]
        Ordered tokens with host blocks represented by ``'host'``.

    Raises
    ------
    Rejection
        If the source contains an invalid token or an unclosed host block.

    Examples
    --------
    ``tokenize('x + 1')`` returns ``['x', '+', '1']``.
    """
    tokens, position = [], 0
    while position < len(source.rstrip()):
        match = TOKEN.match(source, position)
        if match is None:
            raise Rejection('syntax')
        if match.group('host'):
            depth, position = 1, match.end()
            while depth and position < len(source):
                depth, position = depth + {'{': 1, '}': -1}.get(source[position], 0), position + 1
            if depth:
                raise Rejection('syntax')
            tokens.append('host')
            continue
        tokens.append(match.group(match.lastgroup))
        position = match.end()
    return tokens


class Parser:
    """Precedence climbing over one token list, configured by the corpus precedence table."""

    def __init__(self, tokens: list[str], table: dict[str, tuple[int, str]], mutations: frozenset[str]) -> None:
        self.tokens, self.table, self.mutations, self.position = tokens, table, mutations, 0

    def peek(self) -> str | None:
        """Return the next token without consuming it; e.g. ``['x']`` yields ``'x'``."""
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self, expected: str | None = None) -> str:
        """Consume the next token, optionally requiring a spelling.

        Parameters
        ----------
        expected : str or None, optional
            Required token spelling, when the caller needs one.

        Returns
        -------
        str
            The consumed token.

        Raises
        ------
        Rejection
            If input is exhausted or the token differs from ``expected``.

        Examples
        --------
        ``take('(')`` consumes and returns ``'('`` when it is next.
        """
        token = self.peek()
        if token is None or (expected is not None and token != expected):
            raise Rejection('syntax')
        self.position += 1
        return token

    def arguments(self) -> list[str]:
        """Parse a parenthesized argument list, including host references.

        Returns
        -------
        list[str]
            One tree per argument.

        Raises
        ------
        Rejection
            If an argument or closing parenthesis is malformed.

        Examples
        --------
        ``rows(&centre)`` records its reference argument as ``(ref centre)``.
        """
        self.take('(')
        items: list[str] = []
        while self.peek() != ')':
            if self.peek() == '&':
                self.take()
                items.append(f'(ref {self.take()})')
            else:
                items.append(self.pipeline().tree)
            if self.peek() == ',':
                self.take()
        self.take(')')
        return items

    def atom(self) -> Node:
        """Parse one operand; e.g. token ``x`` becomes a node with tree ``'x'``."""
        token = self.take()
        if token in {'|', '||'}:
            raise Rejection('closure-outside-host')
        if token in {'-', '!'}:
            name = 'neg' if token == '-' else 'not'
            return Node(f'({name} {self.postfix(self.atom()).tree})', name)
        if token == '(':
            inner = self.pipeline()
            self.take(')')
            return Node(inner.tree, inner.op, grouped=True)
        if token == 'host':
            return Node('(host)')
        if not re.match(r'\w', token):
            raise Rejection('syntax')
        if self.peek() == '(':
            return Node(' '.join(['(call', token, *self.arguments()]) + ')')
        return Node(token)

    def postfix(self, node: Node) -> Node:
        """Apply any method calls that follow an operand.

        Parameters
        ----------
        node : Node
            Initial receiver expression.

        Returns
        -------
        Node
            Receiver wrapped in each method call.

        Raises
        ------
        Rejection
            If a method name or argument list is malformed.

        Examples
        --------
        ``x.sum().axis(1)`` produces two nested method nodes.
        """
        while self.peek() == '.':
            self.take()
            name = self.take()
            node = Node(' '.join(['(method', node.tree, name, *self.arguments()]) + ')')
        return node

    def operator(self) -> tuple[str, int, str] | None:
        """Read the next operator and its precedence metadata.

        Returns
        -------
        tuple[str, int, str] or None
            Operator, binding level, and associativity, or ``None`` at a boundary.

        Raises
        ------
        Rejection
            If the next token is forbidden or absent from the precedence table.

        Examples
        --------
        A configured ``+`` is returned with its left-associative binding.
        """
        token = self.peek()
        if token is None or token in {')', ',', '|>'}:
            return None
        if token in REJECTED_INFIX and not (token in {'&&', '||'} and 'accept-logical' in self.mutations):
            raise Rejection(REJECTED_INFIX[token])
        if ASSIGNMENT.match(token):
            raise Rejection('assignment')
        if token in {'&&', '||'}:
            return token, 0, 'left'
        if token not in self.table:
            raise Rejection('syntax')
        return (token, *self.table[token])

    def combine(self, op: str, left: Node, right: Node) -> Node:
        """Build a binary tree node and enforce comparison constraints.

        Parameters
        ----------
        op : str
            Binary operator spelling.
        left, right : Node
            Parsed operands.

        Returns
        -------
        Node
            Parenthesized operator tree.

        Raises
        ------
        Rejection
            If comparison-chain or comparison-bitwise rules are violated.

        Examples
        --------
        Combining ``a`` and ``b`` with ``+`` yields ``'(+ a b)'``.
        """
        comparison = self.table.get(op, (0, ''))[1] == 'none'
        if comparison and 'allow-comparison-mix' not in self.mutations:
            if any(not side.grouped and side.op in BITWISE for side in (left, right)):
                raise Rejection('comparison-bitwise-mix')
        if comparison and not left.grouped and self.table.get(left.op or '', (0, ''))[1] == 'none':
            raise Rejection('comparison-chain')
        return Node(f'({op} {left.tree} {right.tree})', op)

    def expression(self, minimum: int) -> Node:
        """Parse operators whose binding level meets ``minimum``.

        Parameters
        ----------
        minimum : int
            Lowest operator binding level accepted at this recursion depth.

        Returns
        -------
        Node
            The parsed expression tree.

        Raises
        ------
        Rejection
            If an operand or operator is invalid under the grammar.

        Examples
        --------
        ``a + b * c`` groups multiplication before addition.
        """
        left = self.postfix(self.atom())
        while (found := self.operator()) is not None and found[1] >= minimum:
            op, level, associativity = found
            self.take()
            right = self.expression(level if associativity == 'right' else level + 1)
            left = self.combine(op, left, right)
        return left

    def pipeline(self) -> Node:
        """Parse pipeline stages after splitting at the lowest-precedence operator.

        Returns
        -------
        Node
            A left-associated pipeline unless the mutation requests otherwise.

        Raises
        ------
        Rejection
            If any stage is invalid.

        Examples
        --------
        ``a |> b |> c`` becomes ``'(|> (|> a b) c)'``.
        """
        stages = [self.expression(0)]
        while self.peek() == '|>':
            self.take()
            stages.append(self.expression(0))
        if 'right-associative-pipe' in self.mutations:
            tree = stages[-1].tree
            for stage in reversed(stages[:-1]):
                tree = f'(|> {stage.tree} {tree})'
        else:
            tree = stages[0].tree
            for stage in stages[1:]:
                tree = f'(|> {tree} {stage.tree})'
        return Node(tree, '|>' if len(stages) > 1 else stages[0].op)


def precedence_table(grammar: dict, mutations: frozenset[str] = frozenset()) -> dict[str, tuple[int, str]]:
    """Map each operator to its binding level and associativity.

    Parameters
    ----------
    grammar : dict
        Parsed macro grammar document.
    mutations : frozenset[str], optional
        Seeded deviations used to prove corpus sensitivity.

    Returns
    -------
    dict[str, tuple[int, str]]
        Operator bindings; larger levels bind more tightly.

    Examples
    --------
    The table gives ``*`` a tighter binding level than ``+``.
    """
    levels = [level for level in grammar['precedence'] if level['name'] not in {'unary', 'pipe'}]
    table = {op: (len(levels) - index, level['associativity'])
             for index, level in enumerate(levels) for op in level['operators']}
    if 'swap-mul-add' in mutations:
        multiplicative, additive = table['*'][0], table['+'][0]
        table.update({op: (additive, 'left') for op in '*/%'} | {op: (multiplicative, 'left') for op in '+-'})
    return table


def parse(source: str, grammar: dict, mutations: frozenset[str] = frozenset()) -> Parsed | Rejected:
    """Recognize one source and return its tree or named rejection.

    Parameters
    ----------
    source : str
        Expression to recognize.
    grammar : dict
        Precedence and rejection rules from ``spec/macro-grammar.json``.
    mutations : frozenset[str], optional
        Seeded deviations used by negative controls.

    Returns
    -------
    Parsed or Rejected
        Parsed tree on acceptance, or the rule that rejected the source.

    Examples
    --------
    A comparison chain returns ``Rejected('comparison-chain')``.
    """
    try:
        parser = Parser(tokenize(source), precedence_table(grammar, mutations), mutations)
        tree = parser.pipeline().tree
        if parser.peek() is not None:
            raise Rejection('syntax')
        return Parsed(tree)
    except Rejection as rejection:
        return Rejected(str(rejection))
