# Architectural decision record (ADR) 0008: Acceptance-control pre-registration

## Status

Accepted on 2026-10-10: every acceptance experiment is registered, with its
workload, control, environment, estimand, statistic, and decision rule frozen
under a digest, before any acceptance measurement; thresholds come from
recorded calibration extrapolated to the hosted runner class. Records D11 and
D12 in the [decision register](../decision-register.md); the controls are
`AC-01` to `AC-07` in `spec/acceptance-controls.json`, calibrated in
[acceptance calibration](../acceptance-calibration.md).

## Date

2026-10-10.

## Context and problem statement

Terms of reference Q2 asked which runtime, memory, compile-cost, proof-cost,
and CI thresholds govern the experiments, and success criterion S7 requires
them to be recorded before candidate acceptance is measured. A threshold chosen
after seeing a result can be tuned to pass, and a measurement taken on a busy
development machine can say more about the machine than about the code. The
sponsor delegated threshold selection (D12) on condition that thresholds rest
on realistic local measurements extrapolated to the GitHub-hosted runner class,
with the evidence recorded.

## Decision drivers

- No acceptance measurement may predate its registration, and no
  registration may change silently afterwards.
- Thresholds must be reproducible from recorded calibration, not invented.
- Development machines are shared and variable; acceptance environments must
  not be.
- Records must not leak host identity (D11).

## Decision outcome

- Environment (D11). Acceptance measurements run on the GitHub-hosted
  `ubuntu-24.04` runner class (4 vCPUs, 16 GB, x64). Runtime ratios use paired,
  interleaved runs within one job, with instruction counts primary and wall
  time secondary. Proof and build ceilings use the same runner class. Shared
  development hosts are never acceptance environments; they serve only for
  calibration, and calibration runs never count as acceptance evidence.
- Registration. Each control freezes its workload and control sources (with
  digests), sizes, seeds, timed region, metric, unit, estimand, statistic,
  decision rule (including inconclusive and extension policy), warm-up,
  interleaving, sample counts, outlier policy, environment, cache policy, proof
  scope, measurement tool, analysis script, and calibration reference. Its
  digest is SHA-256 over the canonical JSON of those fields. Observed runner
  metadata is recorded per measurement, not frozen.
- Amendments. A frozen field changes only through an amendment approved by
  the sponsor, whose `replaces` equals the previous digest; amendments form an
  append-only chain. The design checks compare with the pull request's merge
  base, so changing a threshold and its digest together without an amendment
  fails. A change made after an acceptance measurement is a new control
  identifier, and the original result is retained.
- Outcomes. `budget-exceeded`, `resource-exhausted`, and a record missing
  because its job was killed are failures; `inconclusive` is never a pass.
  Every retry is recorded and counts.
- Thresholds (D12). Calibrate on a development machine with parallelism
  pinned to the runner's 4 vCPUs, take the median of repeated runs, and record
  compile-admission queueing separately. Extrapolate with a factor measured on
  an identical workload run both locally and on the hosted runner. A threshold
  is the extrapolated median times a safety margin of 2, rounded up to a stated
  granularity; a memory ceiling is the measured peak times 1.5, capped below
  the runner's memory minus a 4 GB reserve. Deterministic budgets, such as the
  Verus `rlimit`, are primary where they exist.
- Host identity (D11). Calibration and measurement records describe hardware
  by class only: CPU model, core and thread counts, memory, operating-system
  family, and kernel major version.

## Known risks and limitations

- Calibration on a contended machine overstates local times; the factor uses
  the least-contended local run of the shared workload to stay conservative.
- Runtime controls (`AC-05`) cannot be calibrated before an executor exists;
  their thresholds come from the design targets and are labelled as not
  calibrated.
- Without code-owner review (D13), the freeze check makes an unamended edit a
  named failure, and the sponsor's review is the human control.
