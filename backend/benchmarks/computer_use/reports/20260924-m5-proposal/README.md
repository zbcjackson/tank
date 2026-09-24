# M5 refreshed proposal

> 状态：2026-09-24，schema v3 离线预检通过，input_cleanup=true；完整 17-trial 批次未启动。

The unchanged 5-pilot + 12-core schedule is refreshed against the new runtime and
current source. Schema v3 requires input_cleanup=true and record_only=true.
Preflight verifies 342 pinned files. Token and monetary numbers are reference
values only; the user's record-only decision remains effective. HTTP counts,
timeouts and step limits remain enforced. No new model request occurred.

The full-batch preflight retains live_ready=false: independent scoring, actual
environment preparation, pilot acceptance and screenshot authorization still
apply to a full run. The separate execute_a_control API can execute only the
first trial, after explicit caller authorization and controlled-desktop setup;
it does not transition to another pilot or core trial. See ../20260924-m5-pilot-ready.

Validation: backend **5004 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, changed-file pyright, running backend log,
docs and protocol synchronization passed. Entry implementation: `92070ff`.
