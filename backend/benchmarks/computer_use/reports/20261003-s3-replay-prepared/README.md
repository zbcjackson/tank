# S3 replay prepared — 2026-10-03

Status: preparation verified and reviewed; **no real model requests made**. This directory contains
an experiment proposal, not Jev/Qwen comparison results or a calibration conclusion.

- [freeze.json](freeze.json): 24 cases, public evidence and independent labels,
  12 calibration / 12 holdout, model/endpoint/price limits and implementation hashes.
- [Fixture protocol](../../fixtures/s3/README.md): scope, candidate recall vs selection,
  gates, strict control labels and calibration rule.
- [Concrete paid-batch proposal](../../fixtures/s3/experiment.md): 64 requests maximum,
  32 each to pinned Jev and Qwen; $0.25 shared conservative reservation limit.
- [Harness](../../s3_replay.py): offline preparation by default; live execution requires
  the separately approved digest and refuses reused journals.

The dataset and all implementation hashes are checked again before live execution.
The fixed sample only covers the current single-milestone click/fill candidate
builder. Model wrappers differ, while state/question/options match within each
stage. Candidate recall failures, host gates and invalid/nonexecuted model rows
remain distinguishable. No thresholds are installed into production.

Current digest: `9bfed6bbe775859db0fd80f6d0adc91accdebd187d217b6fc8707f45d7ed327c`.
Real execution awaits separate authorization required by the strategy-ladder plan.


Preparation acceptance: 56 focused tests; full backend 5518 passed / 1 skipped;
E2E 17 scenarios / 67 steps passed, applicable lint/type/docs checks passed. Review
round 1 corrected positive-target position bias (10 positives now balanced 5:5,
with calibration 3:2 and holdout 2:3); round 2 found no remaining actionable issues.
This is tooling/fixture acceptance only, not model performance evidence. No spend
journal or real result file exists for this batch.
