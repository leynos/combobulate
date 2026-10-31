# Architectural decision record (ADR) 0008: Acceptance-control pre-registration

## Status

Accepted on 2026-10-10: every acceptance experiment is registered, with its
workload, control, environment, estimand, statistic, and decision rule defined
before any acceptance measurement; thresholds come from recorded calibration
extrapolated to the hosted runner class. Amended on 2026-10-31: the digests,
source hashes and sponsor-approved amendments are retired (see
[Amendments](#amendments)). Records D11 and D12 in the
[decision register](../decision-register.md); the controls are `AC-01` to
`AC-07` in `spec/acceptance-controls.json`, calibrated in
[acceptance calibration](../acceptance-calibration.md).

## Date

2026-10-10.

## Context and problem statement

Terms of reference Q2 asked which runtime, memory, compile-cost, proof-cost,
and CI thresholds govern the experiments, and success criterion S7 requires
them to be recorded before candidate acceptance is measured. A threshold chosen
after seeing a result can be tuned to pass, and a measurement taken on a busy
development machine can say more about the machine than about the code.
Threshold selection (D12) rests on realistic local measurements extrapolated to
the GitHub-hosted runner class, with the evidence recorded.

## Decision drivers

- No acceptance measurement may predate its registration, and a change to a
  registration is visible in review and Git history.
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
  Acceptance records validate the vCPU, memory, and architecture class, record
  GitHub Actions `ImageOS` and `ImageVersion`, and include measured versions
  for the frozen toolchain requirements.
- Registration. Each control defines its workload and control, sizes, seeds,
  timed region, metric, unit, estimand, statistic, decision rule (including
  inconclusive and extension policy), warm-up, interleaving, sample counts,
  outlier policy, environment, cache policy, proof scope, measurement tool,
  analysis script, calibration reference and registration date. Observed runner
  metadata is recorded per measurement, not defined by the control.
- Changes. A control is an ordinary reviewed file: a change to it goes through
  a pull request, and Git history is the record. Each acceptance record must
  name its control, postdate the control's registration date, and use the
  hosted acceptance environment. A threshold chosen after seeing a result can
  be tuned to pass, so reviewers treat a threshold change after a measurement
  as a new control identifier rather than an edit.
- Outcomes. `budget-exceeded`, `resource-exhausted`, and a record missing
  because its job was killed are failures; `inconclusive` is never a pass.
  Every retry is recorded and counts.
- CI control (`AC-07`). The rolling window contains the 20 most recent
  eligible `build-test` job attempts on main and pull requests, including
  reruns and every conclusion. The p90 uses all available attempt durations;
  any failed, timed-out, cancelled, resource-exhausted, or missing attempt
  fails the control independently of the p90. The job pins
  `runs-on: ubuntu-24.04` and its timeout to the registered eight-minute budget.
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
- Without code-owner review (D13), review of the pull request that changes a
  control is the only control on its thresholds.

## Amendments

2026-10-31: the approval process for acceptance controls is retired, on the
maintainer's ruling that a contract test which breaks on a reformat wastes
everyone's time and that this is a single developer and a set of robots with no
sponsor to approve anything. Removed: the SHA-256 digest of each control and
its amendment chain, the sponsor-approved amendment and its approval reference,
the registered SHA-256 of the workload source files (including the `ci.yml`
hash that failed on any edit of the workflow), the digest on measurement
records, and the base-revision freeze of the controls register. Kept: each
control's measurement definition (workload, metric, estimand, statistic,
decision rule, environment, calibration), the schema that types it, and the
checks that bind records to their control, registration date, hosted runner and
toolchains.
