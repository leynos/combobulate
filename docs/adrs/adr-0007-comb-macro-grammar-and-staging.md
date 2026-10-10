# Architectural decision record (ADR) 0007: `comb!` macro grammar and staging

## Status

Accepted on 2026-10-10: `comb!` keeps its pipeline spelling, splits `|>` from
the token stream first, and otherwise uses Rust expression precedence over a
small documented subset, rejecting ambiguous comparison mixes. Records D08, and
the macro staging and stable-Rust application subject assigned here by D07, in
the [decision register](../decision-register.md). The corpus is
`spec/macro-grammar.json`; the contract is `SC-10`.

## Date

2026-10-10.

## Context and problem statement

Technical design §7 fixes the `comb!` spelling (terms of reference C2) but not
its operator precedence. Rust parses `a & b > c` as `(a & b) > c`, which array
users commonly misread, and rejects `a < b < c` with a parser error that names
Rust rather than Combobulate. The macro also has to separate DSL expressions
from host Rust, such as closures, without inferring meaning from function names.

## Grammar

Screen reader description: the following EBNF defines a pipeline as stages
separated by `|>`, a stage as a Rust-precedence expression over the documented
operators, and primaries as names, literals, calls, method calls, parenthesized
pipelines, and `host` blocks.

```plaintext
pipeline  = stage , { "|>" , stage } ;              (* left-associative, lowest *)
stage     = expr ;                                    (* precedence climbing, table below *)
expr      = unary , { binary-op , unary } ;
unary     = { "-" | "!" } , postfix ;
postfix   = primary , { "." , name , arguments } ;
primary   = path | literal | path , arguments | "(" , pipeline , ")" | host-block ;
arguments = "(" , [ argument , { "," , argument } ] , ")" ;
argument  = "&" , name | pipeline ;                  (* &name is a host reference *)
host-block = "host" , "{" , rust-tokens , "}" ;      (* host Rust, evaluated once *)
```

`verb! { |inputs| body }` binds placeholder inputs and immutable `let` bindings
around the same expression grammar. `arr!` takes whitespace cells and semicolon
rows, and `array!` takes nested comma-separated rows; both require rectangular
literals.

## Operator precedence

Levels follow the Rust Reference[^rust-precedence], restricted to the DSL
subset and listed strongest first.

| Level          | Operators                   | Associativity |
| -------------- | --------------------------- | ------------- |
| Unary          | `-` `!`                     | Prefix        |
| Multiplicative | `*` `/` `%`                 | Left          |
| Additive       | `+` `-`                     | Left          |
| Shift          | `<<` `>>`                   | Left          |
| Bitwise and    | `&`                         | Left          |
| Bitwise xor    | `^`                         | Left          |
| Bitwise or     | `\|`                        | Left          |
| Comparison     | `==` `!=` `<` `>` `<=` `>=` | None          |
| Pipeline       | `\|>`                       | Left          |

_Table 1: `comb!` operator precedence, strongest first._

## Decision outcome

- `|>` is split from the token stream first, where `|` and `>` are adjacent
  (joint) tokens; it is the lowest-precedence operator and left-associative,
  and it may appear inside parentheses. `a | > b` is a syntax error.
- Each stage is parsed with Rust precedence as `syn` parses it. A comparison
  that is the unparenthesized operand of `&`, `|`, or `^`, or that has one as
  an operand, is rejected with a first-screen diagnostic; `syn`'s "comparison
  operators cannot be chained" error is translated into the same diagnostic.
- Array `&&` and `||`, `as`, ranges, and assignment are rejected; `&`, `|`,
  and `!` are elementwise logic. Closures and `||` are accepted only inside
  `host { ... }`.
- Calls such as `rows(&centre)` construct graph objects from host values;
  unknown host calls need `host { ... }` or a native-kernel wrapper.
- Staging. Parsing and lowering run at macro expansion; `host { ... }` runs
  once at graph construction; graph application never runs a domain kernel;
  `.prepare(&engine)` validates and plans; `.collect()` executes. Static
  descriptor retention is optional: when descriptors and target facts are
  available, the frontend may emit const-evaluable cost checks, but it never
  evaluates runtime handles or `host` reads at compile time.

## Consequences

- `spec/macro-grammar.json` records the corpus (`G01` to `G28`), covering
  every level and rejection rule; a documentation-model recognizer checks it
  until task 2.3.1 replays every entry as a `trybuild` pass or fail fixture.
- Seeded grammar mutations (swapped `*` and `+`, right-associative `|>`,
  accepted `&&`, allowed comparison mixing) each change at least one corpus
  outcome.
- Token-level entries (`a|>b`, `a | > b`) are tagged `phase2_only`, because
  only the real token stream can distinguish joint from separate tokens.

[^rust-precedence]: The Rust Reference, "Expressions: Expression precedence",
    <https://doc.rust-lang.org/reference/expressions.html#expression-precedence>,
    retrieved 2026-10-11.
