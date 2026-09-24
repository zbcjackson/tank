# M5 B-protocol-only single-pilot preparation

> 状态：2026-09-24，固定单轮入口及离线材料完成，等待本轮授权；真实请求为 0。

Next scheduled variant: B-protocol-only. It uses the same
20260924-m5-contract-runtime as the preceding A-control trial. Definitions differ
only in grounding.protocol: legacy → point. Host restoration stays false; model,
generation settings and task remain unchanged. comparison.json records the
checked definition/generation equality and exact selected trial.
The explicit point schema uses found with integer x/y coordinates normalized to
the full display; no separate locator model is called.

Proposed authorization scope: one Calculator trial using qwen3.7-flash-2026-07-15
at https://dashscope.aliyuncs.com/compatible-mode/v1. Images contain controlled
main-display Calculator, black background and menu bar, including initial and
feedback screenshots. Limits: at most 16 HTTP requests, 120 agent seconds and
15 steps, zero retries, token/cost record-only, stop on insufficient balance,
input cleanup enabled, no automatic next pilot/core. Native-work draining may
extend cleanup return time. Monetary cost remains unpriced.

The launcher differs from the previously executed contract launcher only in its
fixed entry call, proposal path, variant label and fresh output directory:
/tmp/tank-m5-b-protocol-only-20260924-preview or
/tmp/tank-m5-b-protocol-only-20260924-live.
Default execution is preview-only; --live is for explicit new authorization.
It first checks the frozen proposal, prepares the desktop, writes initial.png,
and waits for a go file after fresh original-resolution screenshot review before
loading credentials and making model requests. Old output directories cannot be
replayed. The historical reference image is
../20260924-m5-contract-pilot/live/initial.png; it is not a fresh preview.

From backend, the reviewed command is:
uv run --no-sync python benchmarks/computer_use/reports/20260924-m5-b-protocol-ready/launcher.py.txt
Add --live only after this trial is authorized. Desktop setup/scope guards and
clipboard/apps/cursor/window restoration are unchanged. They remain a controlled
test harness, not a general notification/privacy filter. The existing A-control
single-trial authorization has been consumed and does not authorize this variant.

Tests reuse the actual proposal preflight with only run_batch replaced: both
fixed entries reject missing authorization, preserve their exact variant/profile/
grounding and one-row request/cleanup limits, reject mutated runtime/order/cleanup,
and reject proposal changes during preflight. Five added parameterized cases
bring test_comparison_freeze.py to 74 passing cases. They establish execution
scope, not model effectiveness or pilot acceptance. No production agent/tool
behavior changed. Remaining variants/core runs are not authorized by this API.

Validation: backend **5015 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, changed-file pyright, development-server
log, docs and protocol checks passed. Entry implementation: 901375e.
