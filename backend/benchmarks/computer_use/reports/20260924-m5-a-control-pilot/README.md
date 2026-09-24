# M5 refreshed A-control pilot

> 状态：2026-09-24，获本轮明确授权后执行 1 trial；strict 失败，自动输入清理及桌面恢复确认成功，未启动后续组。

The user approved sending the controlled Calculator/black-background/menu-bar
initial and feedback screenshots to https://dashscope.aliyuncs.com/compatible-mode/v1
using qwen3.7-flash-2026-07-15. The reviewed launcher ran once against the
20260924 freeze/proposal at revision be2c235. Limits were 16 HTTP requests,
120 agent seconds and 15 tool steps; token/cost admission was record-only.

Results: **16 HTTP responses, all 200; 234042 input + 4239 output = 238281 tokens**.
Agent time was 98.81 seconds; full trial time was 107.95 seconds. It stopped at
max_steps(15), not timeout or token/cost admission. Nine unique images appeared
56 times in request history. Usage is known for every request; no insufficient
balance response was observed. Monetary cost remains unpriced; zero monetary
ledger fields do not establish free usage or an actual bill.

The strict validator failed with AX display result 0. Independent original-size
inspection of shot_009.png also shows Calculator displaying 0, not 56.
An initial reviewer impression from the image preview that the window was absent
was withdrawn after original-resolution inspection and direct pixel verification.
The Calculator region is present in the archived images; do not classify this as
an established occlusion/environment failure. The generated assessment's pixels,
business and mouse-only fields remain unknown; this review does not rewrite raw data.

Observed tool failures (six of fifteen tool calls):

- Turn 2: unsupported computer_batch screenshot argument.
- Turn 3: actions serialized as a string rather than an array.
- Turn 4: unsupported screenshot frame_id argument.
- Turns 6 and 8: region serialized as a string; invalid screenshot region.
- Turn 9: mouse_move rejected for missing/stale frame identity. This is not a
  pixel-difference rejection; no scene/geometry-change rejection occurred.

Two clicks were dispatched to Quartz (739,291) and (1075,248). The model also
sent type_text strings 7, x8= and *8 return. Dispatch success does not establish
that the intended expression was entered. These observations support protocol,
frame-use and action-selection failure categories, not an isolated causal model
ranking. The six rejected calls and uncompleted calculation exhausted the steps.
A single trial does not establish a success rate or A/B/C/D comparison.

The automatic cleanup hook found no held keys/buttons before or after its finish
check and reported confirmed=true with no errors. External cleanup also confirmed
Calculator/background closed, hidden apps/clipboard/cursor restored and empty
held-input state. The batch completed its single entry without a cleanup stop;
completed means execution finished, not task success. No further paid trial ran.

Evidence: summary.json contains derived totals, errors and independent review;
live/ preserves the exact batch plan, request/usage journals, raw SSE response
bodies, trace, screenshots and original result. artifacts.json binds those files
and the executed launcher. Historical Sept22 evidence and Sept24 preparation
artifacts are unchanged.

Next: use this frozen trace for offline replay of malformed arguments and legacy
frame/coordinate use, then decide the next pilot comparison. Do not reintroduce
pixel equality gates or change production budgets. Four remaining pilot variants,
twelve core trials, phase-transition orchestration and the final comparison remain.

Validation after this run: backend **5004 passed / 1 skipped** and E2E
**16 scenarios / 63 steps passed**; web lint/TypeScript, backend/CLI ruff,
development-server log, docs and protocol checks passed. No Python code changed,
so changed-file pyright is not applicable. Full pytest used the documented Opus
library path; E2E required native browser permissions outside the sandbox.
