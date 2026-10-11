# Acceptance calibration

This report records how the pre-registered acceptance controls `AC-01` to
`AC-07` in `spec/acceptance-controls.json` got their thresholds. The sponsor
delegated threshold selection (decision D12) on condition that thresholds rest
on realistic measurements on the development machine, extrapolated to the
GitHub-hosted runner class (4 vCPUs, 16 GB, x64), with the evidence recorded.
[ADR-0008](adrs/adr-0008-acceptance-control-pre-registration.md) states the
protocol. Calibration runs are not acceptance evidence: no control has been
measured for acceptance yet, and every threshold is registered, not met.

## Environments

Machine records live in `spec/calibration/`. Following decision D11, they name
hardware by class only.

| Record                         | Hardware class                                                  | Purpose                                 |
| ------------------------------ | --------------------------------------------------------------- | --------------------------------------- |
| `shared-workloads-local.json`  | Shared development host: AMD Ryzen 9 3900, 12 cores, 24 threads | Local half of the extrapolation factor  |
| `shared-workloads-runner.json` | GitHub-hosted runner, `ubuntu-24.04` image 20261004.327         | Hosted half of the extrapolation factor |
| `verifier-probe.json`          | Shared development host                                         | Verus and Kani costs (`AC-01`, `AC-02`) |
| `builds.json`                  | Shared development host                                         | Build costs (`AC-04`; informs `AC-03`)  |
| `ci-history.json`              | GitHub-hosted runners, last 20 successful runs                  | Pull request CI critical path (`AC-07`) |

_Table 1: Calibration records._

The development host was shared with other agents throughout: its load average
ranged from about 20 to 41 on 24 threads, and all four compile-admission slots
were usually held. Local wall times are therefore noisy and, if anything,
inflated; the method below is designed so that noise loosens thresholds rather
than tightening them.

## Method

1. Toolchains. Rust nightly-2026-08-27 with the repository's Cranelift dev
   profile; Verus 0.2026.09.06.8dea4a2 (Rust 1.98.0) with Z3 4.16.0; Kani
   0.67.0 (CBMC with CaDiCaL); Python 3.14; Polars 0.55.2 with the `lazy`
   feature, provisional until task 1.2.1 pins it.
2. Probe. `tools/calibration/cardinality-probe/` is a standalone crate, outside
   the repository package and workspace, with a checked cardinality function
   (zero extent first, then checked multiplication), a Verus proof of its full
   specification, and Kani harnesses with `cover!` statements. It is a
   calibration probe, not the shipped kernel, which task 1.2.4 owns.
3. Repetition. Five runs per workload (three for the Polars cold build, whose
   runs each take minutes on the shared host), reporting the median. Verus and
   Kani runs execute under `systemd-run --user`, which reports the process
   tree's peak memory from cgroup v2.
4. Parallelism. Builds run with four jobs to match the runner's four vCPUs.
   Compilations pass through the host's compile-admission queue; no waiting
   line was captured, but other builds still contended for the CPU.
5. Extrapolation factor. The same workload ran on both machines: the design
   checks' `unittest` and pytest suites at commit 398d2f6. Hosted to local
   median ratios were 0.92 (`unittest`: 28.4 s against 30.9 s) and 1.17
   (pytest: 3.73 s against 3.19 s). The factor is the larger, rounded up to
   1.2. This replaces a published processor benchmark, because the hosted
   runner's CPU model is not recorded.
6. Thresholds. Each time threshold is the local median times the factor
   times a safety margin of 2, rounded up to a stated granularity. Each memory
   ceiling is the measured peak times 1.5, rounded up to 64 MiB and capped at
   12 GiB (16 GB less a 4 GB reserve). The Verus `rlimit` is deterministic, so
   it is the primary proof budget and needs no factor.

## Results and thresholds

| Control | Measurement (median)                                                | Threshold                                                                   |
| ------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `AC-01` | Verus: 1.64 s wall; max per-function rlimit 146,824; peak 201.8 MiB | rlimit 300,000 per function; 10 s wall (30 s hard timeout); 320 MiB         |
| `AC-02` | Kani structural harnesses: 0.28 s and 1.01 s; peak 54.0 MiB         | 10 s per harness; 100 s per job; 128 MiB                                    |
| `AC-03` | Not calibrated: static admission does not exist yet                 | One-sided 95% upper bound of the rebuild ratio at most 1.25 (design target) |
| `AC-04` | Cold builds: native 2.02 s, proof-capable 4.08 s, Polars 231.5 s    | Polars cold 10 minutes; every other profile and phase 1 minute              |
| `AC-05` | Not calibrated: no executor exists                                  | Upper bound of each runtime ratio at most 1.5 (design target)               |
| `AC-06` | Not calibrated: a correctness bound                                 | No tracked peak above its admitted bound; no untracked allocation           |
| `AC-07` | CI `build-test` job p90 over 20 runs: 219 s                         | p90 within 8 minutes; the job's `timeout-minutes` is 8                      |

_Table 2: Calibrated measurements and registered thresholds._

## Findings

- Verus proves the probe's unbounded specification in under 2 s, and its
  `rlimit` was identical in every run. A seeded mutant that returns `Some(1)`
  for a zero extent fails with "postcondition not satisfied".
- Kani cannot discharge symbolic 64-bit multiplication on this host within a
  useful budget. A harness asserting the exact product of three full-width
  extents was stopped after 900 s, and one with extents below 2^16 after 18 min
  46 s (18 min 27 s of CPU, 154.5 MiB), both without a verdict. Both were
  removed from the probe. `AC-02` therefore scopes Kani to structural
  harnesses; multiplication belongs to Verus under `AC-01`, and a harness that
  needs symbolic multiplication requires an amendment with its own calibration.
  Task 1.2.4 should plan its proofs accordingly.
- Polars dominates build cost: a cold Polars-enabled build took 163 to 382 s
  locally, while every other profile built in seconds.

## Reproduction

From `tools/calibration/cardinality-probe/`, with `VERUS_Z3_PATH` naming a Z3
4.16.0 binary:

```bash
verus verus/cardinality.rs --num-threads 4 --time-expanded --output-json
cargo kani --harness verification::zero_extent_short_circuits --exact
CARGO_BUILD_JOBS=4 CARGO_TARGET_DIR=target/cal-polars cargo build --features polars
```

Wrap each command in `systemd-run --user --wait --pipe --collect` to obtain its
peak memory. The CI history comes from
`gh run list --workflow ci.yml --status success --limit 20` and the jobs
endpoint of the REST API. Record new calibration under `spec/calibration/` with
the measurement-record schema, and change a registered threshold only through a
sponsor-approved amendment.
