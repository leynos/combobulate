# Combobulate

> **APL escaped from 1966, stole Rust’s type system, acquired a cat, and is now
> attempting to raytrace the future.**

Combobulate is an experimental Rust library for expressive, composable,
inspectable array programming.

**Current reality:** this repository contains the development scaffold and
revision 0.2 design. The crate exports only a disposable `greet()` stub. The
array API, `comb!`, backends, costing, and verification interfaces described
below are proposed; the Rust snippets are conceptual sketches, not runnable
examples of the current crate. No completed Kani or Verus proof accompanies the
design. The [language reference](docs/language-reference.md) governs the
proposed API and its contracts.

It takes the parts of APL that feel like they were recovered from an alien
spacecraft, especially **verbs, higher-order operators, rank, reduction,
composition, and whole-array reasoning**, and asks:

> What if we kept the good bit, removed the keyboard summoning ritual, gave the
> compiler enough information to understand what we were doing, and then
> pointed the resulting contraption at a POV-Ray-style renderer?

This is that contraption.

```text
          ┌──────────────────────────────┐
          │  INCIDENT REPORT 5100-A     │
          ├──────────────────────────────┤
          │ Temporal anomaly detected.  │
          │ Cause: nested iterator soup │
          │ Severity: embarrassing      │
          └──────────────┬───────────────┘
                         │
                         ▼
                 /\_/\
                ( o.o )   "have you considered
                 > ^ <     rank polymorphism?"
                    \
                     \____ Ferris containment failure
```

## The year is 2036

Humanity has made several mistakes.

We put advertisements in refrigerators.

We invented seventeen JavaScript package managers.

Someone generalized `AbstractFactoryFactory`.

Most seriously, array programming was rediscovered independently by six
different industries, each of which implemented half of APL using method chains.

The resulting code was technically correct but spiritually devastating.

One desperate temporal engineer therefore travelled back to the early
twenty-first century seeking an **IBM 5100**, ostensibly because it could
emulate obscure legacy systems.

This explanation is obviously nonsense.

The IBM 5100 contained APL.

John Titor needed `⍤`.

Unfortunately, an equipment failure deposited him several decades too early,
whereupon his mission was intercepted by a small collective of Rust cat-enbies
who looked at APL, looked at Rust, looked at a raytracer, and said:

> “Fine. We’ll do it ourselves, but nobody is typing `⍉⍤¯1⊢` into production
> unless they really want to.”

Combobulate is the surviving artefact of this incident.

## What Combobulate actually is

Behind the temporal nonsense is a fairly serious idea.

Most conventional numerical Rust APIs expose operations primarily as function
calls, iterator chains, methods, or opaque closures.

Combobulate instead treats **operations themselves as structured values**.

A verb is not merely something that executes.

It can potentially be:

- composed;
- transformed;
- inspected;
- costed;
- optimized;
- lowered to different execution backends;
- rendered as an explanation;
- checked against shape and rank constraints;
- subjected to static analysis;
- and, where practical, exposed to proof and model-checking tools.

Conceptually:

```rust
let luminance =
    comb!(
        rgb
        |> map(linearize)
        |> inner(weights)
        |> clamp(0.0, 1.0)
    );
```

The exact syntax remains subject to evolution, temporal interference, and
compiler diagnostics.

The important property is that `luminance` is not necessarily an opaque Rust
closure containing unknowable computational fog.

It is an **inspectable expression describing a computation**.

That distinction powers most of the interesting bits.

## APL, but with fewer keyboard crimes

APL has an extraordinary idea hiding underneath its famous glyphs:

**functions can be transformed systematically into other functions.**

Reduction is not just another utility function.

Rank is not just another loop helper.

An outer product is not a bespoke matrix routine.

Composition is not merely punctuation.

These are ways of constructing computations from computations.

Combobulate borrows that model while presenting it through Rust concepts that
ordinary Earth keyboards can produce.

Roughly:

| APL idea                    | Combobulate idea             |
| --------------------------- | ---------------------------- |
| primitive function          | verb                         |
| operator deriving functions | conjunction / modifier       |
| reduction                   | `reduce(...)`                |
| scan                        | `scan(...)`                  |
| rank                        | `rank(...)`                  |
| outer product               | `outer(...)`                 |
| inner product               | `inner(...)`                 |
| composition                 | pipelines / composition      |
| array expression            | inspectable expression graph |
| terse alien transmission    | hopefully legible Rust       |

_Table 1: APL concepts and their proposed Combobulate counterparts._

This is not intended to be “APL with English names”.

That would miss the interesting part.

The goal is to preserve APL’s **compositional algebra of array operations**.

## Verbs

A verb represents an operation.

Examples might eventually include things such as:

```rust
add
mul
min
max
sum
mean
reshape
transpose
reverse
take
drop
rotate
select
where_
```

But verbs become much more interesting when combined with modifiers and
conjunctions.

```rust
let total = reduce(add);

let cumulative = scan(add);

let pairwise_distance =
    outer(sub)
    >> map(square)
    >> reduce(add)
    >> map(sqrt);
```

At that point we have stopped assembling calls and started constructing a small
program.

That program can have structure.

Structure can be analysed.

And once the compiler can see the machinery, we can begin doing improper things
with it.

## Rank: the bit everyone eventually reinvents badly

APL’s notion of **rank** lets an operation state what dimensional cells it
consumes, independently of the rank of the surrounding array.

Rather than manually writing:

```rust
for plane in volume {
    for row in plane {
        mysterious_operation(row);
    }
}
```

you can conceptually say:

```rust
rank(1, mysterious_operation)
```

and let the array model determine where that operation applies.

This matters because numerical programs often contain an enormous amount of
accidental iteration machinery.

Combobulate wants that machinery described declaratively enough that humans and
compilers can both reason about it.

## Why not just use iterators?

Rust iterators are excellent.

Combobulate is not an anti-iterator insurgency.

The difference is that:

```rust
things
    .iter()
    .map(...)
    .zip(...)
    .flat_map(...)
    .fold(...)
```

primarily describes an execution process.

Combobulate wants to preserve enough semantic structure to say things such as:

```text
This computation:

1. maps a pure scalar transformation over rank-1 cells;
2. performs a reduction using an associative verb;
3. transposes two axes;
4. feeds the result into an outer product;
5. requires approximately N×M applications of `distance`;
6. can execute on backend X;
7. admits optimization Y;
8. cannot currently be lowered to backend Z because operation Q lacks support.
```

That is a different abstraction boundary.

## Compile-time costing

Because expressions have structure, Combobulate can potentially estimate their
computational character before execution.

Not necessarily exact wall-clock time. We have not yet obtained the
Chronometric Oracle from CERN.

But useful symbolic properties may include:

```text
map(f) over shape [N, M]
    => N × M applications of f

outer(f) over [N] × [M]
    => N × M applications of f

reduce(f) over [N], for N >= 1
    => N - 1 applications of f

matrix-ish horror
    => "Payton, what have you done"
```

Empty reductions follow the verb’s explicit identity or error policy; they do
not perform a negative number of operations.

Compile-time analysis may therefore help identify:

- accidental quadratic operations;
- suspicious intermediate allocations;
- opportunities for fusion;
- parallelizable regions;
- backend-specific acceleration opportunities;
- memory-complexity problems;
- operations too expensive for a chosen execution policy.

Eventually, one should be able to ask an expression what it intends to cost
before unleashing it upon innocent silicon.

## Introspection

This:

```rust
let shader =
    comb!(
        normal
        |> dot(light_dir)
        |> max(0.0)
        |> mul(albedo)
    );
```

should eventually support something morally equivalent to:

```rust
shader.explain();
shader.cost();
shader.shape_contract();
shader.optimized();
```

producing information such as:

```text
Pipeline
 ├─ normal
 ├─ dot(light_dir)
 ├─ max(0)
 └─ mul(albedo)

Input:
    Vec3<f32>

Output:
    Vec3<f32>

Properties:
    pure
    deterministic
    elementwise after dot product

Optimization opportunities:
    fuse max + mul

Estimated primitive operations:
    3 scalar mul for dot
    2 scalar add for dot
    1 comparison
    3 scalar mul for albedo
```

The exact API will evolve.

The design principle will not:

**if Combobulate knows what your program means, it should be willing to tell
you.**

## Execution backends

Combobulate should not confuse its semantic model with any one execution engine.

Polars is an important backend and an obvious source of highly optimized
array/dataframe machinery.

It is not the ontology of the universe.

A Combobulate expression should, where practical, be lowerable onto different
mechanisms depending on its type, shape, and purpose.

Possibilities include:

```text
Combobulate expression
        │
        ├── scalar / native Rust
        ├── ndarray-ish execution
        ├── Polars
        ├── SIMD
        ├── threaded CPU
        ├── GPU
        ├── symbolic evaluator
        └── verification representation
```

No, all of these do not exist yet.

Yes, this diagram is bait.

## Verification

Rust can ensure that memory remains where memory ought to remain.

That does not prove your matrix algebra is correct.

Combobulate therefore aims to make computations unusually friendly to tools
such as **Kani** and **Verus**.

The general strategy is simple:

1. prefer explicit structured operations over arbitrary callbacks;
2. encode useful algebraic properties where possible;
3. maintain small pure semantic cores;
4. separate expression construction from execution;
5. provide bounded/reference models suitable for verification;
6. design APIs so downstream users can reason about Combobulate expressions
   without reverse-engineering optimizer entrails.

Some operations may eventually carry properties such as:

```rust
associative
commutative
identity(0)
pure
total
shape_preserving
```

Those properties need evidence for the actual operand domain. Floating-point
addition and checked integer addition do not acquire unrestricted associativity
merely by being named `add`.

Those properties are useful for optimization.

They are also useful for proof.

Which is convenient, because optimization based on false algebraic assumptions
is a surprisingly sophisticated way to generate incorrect numbers very quickly.

## Why a raytracer?

Because toy examples lie.

Any array abstraction can look elegant while computing:

```text
1 2 3 + 4 5 6
```

The interesting question is what happens when it encounters:

- vectors;
- matrices;
- ray bundles;
- transformations;
- bounding volumes;
- intersections;
- texture coordinates;
- colour calculations;
- image buffers;
- spatial acceleration;
- numerical edge cases;
- irregular control flow;
- performance-sensitive inner loops.

So Combobulate’s design uses a planned POV-Ray-inspired renderer as its proving
ground.

The renderer is not just a demo.

It is the arena.

If Combobulate makes the renderer clearer, easier to analyse, easier to
optimize, and easier to verify, excellent.

If the renderer becomes an eldritch cathedral of generic traits and macro
expansion, Combobulate has lost and must answer for its crimes.

## Why POV-Ray?

POV-Ray represents a particularly charming species of computational archaeology.

It combines:

- declarative scene description;
- geometry;
- numerical computation;
- recursive algorithms;
- procedural texture machinery;
- decades of accumulated rendering ideas;
- enough mathematical machinery to expose weak abstractions.

It also lets us produce pictures.

This is important because performance regressions are upsetting, but a
raytraced chrome teapot turning inside-out provides a much more emotionally
immediate code review.

## Humanistic errors

Macros can make APIs delightful.

Macros can also make an error message look like a compiler swallowed a polar
bear.

Combobulate treats diagnostic quality as part of the public API.

An ideal failure says something resembling:

```text
Cannot apply `dot` here.

`dot` expects rank-1 cells of equal length.

Left operand:
    shape [640, 480, 3]
    selected cell rank 1
    cell shape [3]

Right operand:
    shape [4]

Expected:
    right cell shape [3]

Perhaps:
    - use a 3-element vector;
    - reshape the right operand;
    - or change the rank at which `dot` is applied.
```

Not:

```text
error[E0277]: the trait bound
for<'a, 'b, const FROBNICATOR: usize>
<<<... 3,802 characters omitted ...>>>
is not satisfied
```

The latter may still exist underneath.

The user should not have to excavate it with a toothbrush.

## The cat-enby architecture review board

All major design decisions must conceptually pass through the following process:

```text
             ┌───────────────┐
             │ New abstraction│
             └───────┬───────┘
                     │
                     ▼
                 /\_/\
                ( -.- )  "why"
                 > ^ <
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   Is it composable?      Can we inspect it?
          │                     │
          └──────────┬──────────┘
                     ▼
              Does it improve
               real code?
                     │
              ┌──────┴──────┐
             yes            no
              │              │
              ▼              ▼
          probably        yeet it
           allowed
```

The cat is not impressed by cleverness.

The cat has seen Haskell.

## Things Combobulate is not

Combobulate is not:

- an attempt to replace Rust;
- an attempt to reproduce every feature of APL;
- a dataframe library with novelty macros;
- a numerical DSL that imprisons you inside itself;
- a declaration that loops are morally wrong;
- an elaborate plan to make every calculation lazy;
- a requirement that `2 + 2` become an expression graph with sixteen generic
  parameters;
- whatever **Hououin Kyouma** is allegedly doing in Akihabara.

There is no Organization.

There is no divergence meter.

There is no microwave connected to the development environment.

The maintainers categorically deny that compiling with
`--features el-psy-kongroo` changes the resulting binary.

Please stop asking.

## Example: progressively more Combobulated

Ordinary Rust:

```rust
let mut result = Vec::new();

for row in &image {
    let mut sum = 0.0;

    for pixel in row {
        sum += luminance(pixel);
    }

    result.push(sum / row.len() as f32);
}
```

More declarative:

```rust
let result = image
    .iter()
    .map(|row| row.iter().map(luminance).sum::<f32>() / row.len() as f32)
    .collect::<Vec<_>>();
```

These two Rust sketches assume nonempty rows and a scalar `luminance` function.
The proposed `mean` contract rejects empty cells; production code must choose
its empty-row policy explicitly.

Combobulate-shaped:

```rust
let row_luminance =
    mean
    << map(luminance);

let result =
    rank(1, row_luminance)
        .apply(image)?;
```

Or, eventually:

```rust
let result = comb!(
    image
    |> rank(1, map(luminance) >> mean)
)?;
```

Now the library knows rather more about what happened than “some closures ran”.

That information can be useful.

## Design priorities

When priorities conflict, Combobulate broadly favours:

```text
legibility
    >
semantic structure
    >
correctness
    >
diagnostics
    >
composability
    >
introspection
    >
verifiability
    >
optimization opportunities
    >
raw cleverness
```

Correctness obviously does not literally rank below legibility in the sense
that pretty wrong answers are acceptable.

This ordering instead reflects an architectural principle:

**we want abstractions whose correctness can remain visible.**

A 4% speed-up purchased with a new ontology and three pages of type signatures
may be rejected by the cat.

## Status

Combobulate is experimental.

Expect:

- API movement;
- unfinished verbs;
- missing conjunctions;
- optimizer experiments;
- backend experiments;
- proof experiments;
- raytraced objects that reveal uncomfortable truths;
- occasional discoveries that Kenneth Iverson had already solved our problem
  in 1964.

This is fine.

The project exists partly to discover where the abstraction should be.

## Read the design

Start with the [documentation contents](docs/contents.md).

- [Terms of reference](docs/terms-of-reference.md): users, scope, constraints,
  and success criteria.
- [Technical design](docs/technical-design.md): semantic contracts,
  proof-first delivery, consumer verification, compile-time costing, and Polars
  capability boundaries.
- [Language reference](docs/language-reference.md): proposed verbs,
  conjunctions, modifiers, macros, and execution interfaces.
- [GIST roadmap](docs/roadmap.md): delivery steps and acceptance criteria.
- [Testable bets](docs/testable-bets.md): witnesses, negative controls,
  falsifiers, and decision rules.

## Contributing

Useful contributions include:

- verbs;
- conjunctions and modifiers;
- better diagnostics;
- expression simplification;
- cost models;
- backend implementations;
- property tests;
- Kani harnesses;
- Verus specifications;
- raytracer workloads;
- documentation;
- examples demonstrating where the abstraction fails.

Especially valuable:

> “I tried to express this real computation and Combobulate made it worse.”

That is evidence.

Please bring it.

Install the pinned development toolchain and linker with
`make install-build-tools`. Run `make all` for the sequential Rust formatting,
Rustdoc, Clippy, Whitaker, test, and spelling gates. Run `make markdownlint` and
`make nixie` for Markdown and Mermaid checks.

Install the documentation check dependencies with
`python3 -m pip install -r tools/requirements.txt`, then run
`make design-check`. This validates the design fixtures, the generated
reference and bet documents, and the roadmap's derived JSON export. It does not
compile the proposed APIs or discharge proof obligations.

The [developer guide](docs/developers-guide.md) explains build routes and
contracts. The [repository layout](docs/repository-layout.md) assigns file
ownership. [AGENTS.md](AGENTS.md) records contributor instructions.

## Frequently anticipated questions

### Is this just APL without glyphs?

No.

APL supplies much of the conceptual skeleton, but Combobulate is designed
around Rust’s type system, ecosystem, tooling, execution environment, and
expectations of maintainability.

### Why call functions “verbs”?

Because the distinction between values, operations, and operators that
construct operations is useful.

Also because naming everything `FnImplAdapterFactory` would summon Java.

### Why “Combobulate”?

Because software has spent decades warning us about becoming discombobulated.

We are simply applying the inverse operation.

### Why Rust?

Because we would like high-level array composition, low-level control, strong
static guarantees, predictable native deployment, and enough type-system
machinery to make questionable architectural experiments possible.

Also Ferris.

Obviously Ferris.

### Is this production ready?

Absolutely not.

Please do not route the European power grid through Combobulate because you
enjoyed the README.

### Does the IBM 5100 matter?

Historically: yes.

Architecturally: no.

Spiritually: extremely.

## The temporal mission

Our working hypothesis is that the original timeline proceeded approximately as
follows:

```text
1962    APL notation developed
  │
1975    IBM 5100 ships with APL
  │
2000    John Titor appears online
  │
2006    Rust begins gestating
  │
2026    Combobulate
  │
2036    ???
  │
2038    integer overflow, probably
```

The obvious conclusion is left to the reader.

## Scaffold provenance

The build baseline comes from
[Peregrine Web PR #11](https://github.com/leynos/peregrine-web/pull/11), commit
`7a68360fb0ad3e8dfad1d6a22df62a19e41bc486`. This repository adapts its package
identity, build-contract tests, and engineering guides, repairs the inherited
complexity findings, and replaces its product design with the Combobulate
revision 0.2 archive. See the
[bootstrap decision](docs/adr-001-repository-bootstrap.md).

## Licence

The project uses the ISC licence. See [LICENSE](LICENSE).

No licence is granted for temporal paradoxes arising from attempts to send
optimized expression graphs to 1975.

## Final warning

If, while using Combobulate, you encounter a Rust cat-enby carrying an IBM 5100
and insisting that `reduce(add)` prevents World War III:

**do not interfere.**

The build is already green in their timeline.
