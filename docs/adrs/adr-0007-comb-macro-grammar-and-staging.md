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

Screen reader description: the following EBNF defines `comb!`, `verb!`,
`host { ... }`, `arr!`, and `array!`, including pipeline stages, placeholder
bindings, literal cell boundaries, and nested array structure.

```plaintext
comb-macro    = "comb!" , "{" , pipeline , "}" ;
pipeline      = stage , { "|>" , stage } ;                  (* left-associative, lowest *)
stage         = expr ;                                       (* Rust precedence, table below *)
expr          = comparison ;
comparison    = bitwise-or , [ comparison-op , bitwise-or ] ; (* no ungrouped chains *)
bitwise-or    = bitwise-xor , { "|" , bitwise-xor } ;
bitwise-xor   = bitwise-and , { "^" , bitwise-and } ;
bitwise-and   = shift , { "&" , shift } ;
shift         = additive , { ( "<<" | ">>" ) , additive } ;
additive      = multiplicative , { ( "+" | "-" ) , multiplicative } ;
multiplicative = unary , { ( "*" | "/" | "%" ) , unary } ;
unary         = { "-" | "!" } , postfix ;
postfix       = primary , { "." , name , arguments } ;
primary       = path | literal | path , arguments
              | "(" , pipeline , ")" | host-block ;
arguments     = "(" , [ argument , { "," , argument } ] , ")" ;
argument      = "&" , path | pipeline ;                        (* &name is a host reference *)
comparison-op = "==" | "!=" | "<" | ">" | "<=" | ">=" ;
host-block    = "host" , "{" , rust-token-tree , "}" ;        (* host Rust, evaluated once *)
verb-macro    = "verb!" , "{" , "|" , [placeholders] , "|" , {let-binding} , pipeline , "}" ;
placeholders  = name , { "," , name } ;
let-binding   = "let" , name , "=" , pipeline , ";" ;         (* immutable, shared graph node *)
arr-macro     = "arr!" , "[" , [arr-row , { ";" , arr-row }] , "]" ;
arr-row       = arr-cell , { whitespace , arr-cell } ;          (* whitespace separates cells *)
arr-cell      = path | literal | "(" , rust-expression , ")" ;
array-macro   = "array!" , array-literal ;
array-literal = "[" , [array-element , { "," , array-element }] , "]" ;
array-element = rust-expression | array-literal ;
name          = identifier ;
path          = Rust path tokens ;
literal       = Rust literal token ;
identifier    = Rust identifier token ;
rust-token-tree = balanced Rust token tree ;
rust-expression = Rust expression occupying one literal cell ;
whitespace    = one or more spaces or tabs ;
```

The EBNF names the five public forms recorded in `spec/macro-grammar.json`.
`comb!` and `verb!` use the graph-expression subset above. In `arr!`, top-level
whitespace separates cells and semicolons separate rows; parentheses keep a
compound Rust expression within one cell. `array!` uses recursively nested,
comma-separated Rust array literals. Both literal forms require rectangular
structure.

## Operator precedence

Levels follow the Rust Reference[^1], restricted to the DSL subset and listed
strongest first.

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

- `spec/macro-grammar.json` records all five macro forms and the corpus
  (`G01` to `G28`), covering every precedence level and rejection rule; a
  documentation-model recognizer checks it until task 2.3.1 replays every
  expression entry as a `trybuild` pass or fail fixture.
- Seeded grammar mutations (swapped `*` and `+`, right-associative `|>`,
  accepted `&&`, allowed comparison mixing) each change at least one corpus
  outcome.
- Token-level entries (`a|>b`, `a | > b`) are tagged `phase2_only`, because
  only the real token stream can distinguish joint from separate tokens.

[^1]: The Rust Reference, "Expressions: Expression precedence",
    <https://doc.rust-lang.org/reference/expressions.html#expression-precedence>,
    retrieved 2026-10-11.
