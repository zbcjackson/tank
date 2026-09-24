# M5 tool-contract batch proposal

> 状态：2026-09-24，342 文件离线预检通过，schema v3；尚未授权或执行新轮。

Generated against 20260924-m5-contract-runtime. The original 5-pilot + 12-core
schedule and 362-request full-batch ceiling are retained. Token and cost are
record-only; input_cleanup=true, effective agent token budget=0. Production
budgets are unchanged. Full-batch live_ready remains false: real environment,
independent scoring, pilot acceptance and scope authorization remain required.

The separate execute_a_control entry can run only the first trial, with at most
16 HTTP requests, 120 agent seconds and 15 steps. It cannot proceed to another
pilot or core trial. See ../20260924-m5-contract-ready for the reviewed launcher.
No real provider request or screenshot capture happened during this preparation.

Validation: backend **5010 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, development-server log, docs and protocol
checks passed. No production Python changed; changed-file pyright N/A.
