# Refreshed A-control pilot ready for review

> 状态：2026-09-24，执行入口/冻结/本地预览准备完成；尚未发送模型请求，待本轮单独授权。

Review scope is in review.json: one A-control Calculator trial with
qwen3.7-flash-2026-07-15 at https://dashscope.aliyuncs.com/compatible-mode/v1,
up to 16 HTTP requests, 120 agent seconds and 15 top-level steps. Token/cost are
record-only, input cleanup is enabled, retries are disabled, and there is no
automatic follow-on trial. Cleanup may extend return time while native work joins.

The user-approved earlier one-trial screenshot scope was consumed by the failed
20260922 pilot. This new trial has not been authorized or run. The local preview
contains Calculator, black background and the menu bar on the Quartz main display.
The launcher checks visible regular apps and backdrop presence around captures;
this is a controlled setup, not a general privacy filter. Native preview cleanup
confirmed closed controlled windows, restored clipboard/apps/cursor and no held
keys/buttons. The preview branch exits before loading credentials or constructing
a model client.

launcher.py.txt is the concrete reviewed one-off harness. Its default mode is
preview-only; --live is reserved for execution after explicit user consent.
Live mode uses a fresh /tmp/tank-m5-a-control-20260924-live directory, writes an
initial.png and waits for an operator-created go file after visual scope review.
Both modes refuse existing output directories. It activates and positions
Calculator before reset to avoid the previous restored-window setup failure.

The harness calls prepare_computer_batch.execute_a_control. The API refuses
missing authorization, verifies the fixed proposal/source/config/runtime, pins
the exact proposal bytes, and passes only one A-control entry to run_batch with
input_cleanup=True and record_only=True. Runtime directory inventory and proposal
hashes are rechecked by the batch. It cannot launch the other 16 entries.
A boolean/API call is an execution gate, not evidence of actual user consent.

Five new regressions cover missing authorization, exact one-trial limits and
cleanup, modified cleanup flags/runtime/order, and proposal mutation during
preflight. Existing proposal and generated-runtime checks still apply. These
replace HTTP/desktop execution at the batch boundary and do not measure model
quality. The previous failed trial remains failed; no success inference is made
from offline fixtures or this preview.

Next, after single-trial approval: recheck frozen inputs and the live screenshot,
run once, retain raw responses/usage/input cleanup and strict AX scoring, then
independently review the final screenshot and classify failures before choosing
whether to proceed. Full pilot-to-core automation remains unfinished.

Validation: backend **5004 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, changed-file pyright, running backend log,
docs and protocol synchronization passed. Entry implementation: `92070ff`.
