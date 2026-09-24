# M5 B-protocol-only entry proposal

> 状态：2026-09-24，342 文件离线预检通过；复用上一轮相同 runtime，新轮未执行。

This proposal uses the unchanged 20260924-m5-contract-runtime and refreshes the
prepare_computer_batch.py pin for its fixed B-protocol-only entry. No agent,
model profile, source runtime or representative SDK request was regenerated.
The 17-entry schedule and schema v3 remain unchanged; full-batch live_ready=false.

execute_b_protocol_only chooses only scheduled row 1 (pilot-b-protocol-only),
after explicit authorization and complete proposal/source/runtime preflight.
It admits at most 16 planner/total HTTP requests and no locator requests, uses
120 agent seconds/15 steps, record-only token/cost and input cleanup, and has
no automatic follow-on. The A-control entry retains its previous fixed row.
The API does not obtain actual consent or prepare/restore the desktop.

See ../20260924-m5-b-protocol-ready for execution scope, reviewed launcher and
comparison checks. Historical live evidence and all previous proposals remain
unchanged. Zero model requests and zero physical desktop actions occurred here.

Validation: backend **5015 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, changed-file pyright, development-server
log, docs and protocol checks passed. Entry implementation: 901375e.
