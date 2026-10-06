# Combobulate

Combobulate is a proposed inspectable array and typed-collection algebra for
Rust, with readable APL-style composition, a first-class Polars route, and
native domain kernels. Its intended notation is
`comb! { input |> stage |> stage }`.

This repository contains the development scaffold and revision 0.2 design. The
array API, macros, backends, static costing, and verification interfaces remain
proposed. The crate currently exports only a disposable greeting stub; no
completed Kani or Verus proof accompanies the design.

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

## Contributor workflow

Install the pinned development toolchain and linker with
`make install-build-tools`. Run `make all` for the sequential Rust formatting,
Rustdoc, Clippy, Whitaker, test, and spelling gates. Run `make markdownlint` and
`make nixie` for Markdown and Mermaid checks.

Install the documentation check dependencies with
`python3 -m pip install -r tools/requirements.txt`, then run
`make design-check`. This validates the design fixtures and generated
reference, roadmap, and bet documents. It does not compile the proposed APIs or
discharge proof obligations.

The [developer guide](docs/developers-guide.md) explains build routes and
contracts. The [repository layout](docs/repository-layout.md) assigns file
ownership. [AGENTS.md](AGENTS.md) records contributor instructions.

## Scaffold provenance

The build baseline comes from
[Peregrine Web PR #11](https://github.com/leynos/peregrine-web/pull/11), commit
`7a68360fb0ad3e8dfad1d6a22df62a19e41bc486`. This repository adapts its package
identity, build-contract tests, and engineering guides, repairs the inherited
complexity findings, and replaces its product design with the Combobulate
revision 0.2 archive. See the
[bootstrap decision](docs/adr-001-repository-bootstrap.md).

The project uses the ISC licence.
