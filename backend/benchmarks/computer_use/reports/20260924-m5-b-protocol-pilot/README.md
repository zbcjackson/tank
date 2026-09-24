# M5 B-protocol-only native abort

> 状态：2026-09-24，本轮已获授权并发出 5 次请求，benchmark 进程 SIGTRAP 崩溃；未完成评分，自动清理未确认，停止后续 trial。

The user explicitly approved one B-protocol-only trial with Calculator, black
background and menu-bar screenshots, including feedback, sent to
https://dashscope.aliyuncs.com/compatible-mode/v1 using
qwen3.7-flash-2026-07-15. The original-resolution initial screenshot was reviewed
before admission. Revision ba7de7e used the unchanged contract-runtime and the
B-protocol proposal, with at most 16 requests/120 agent seconds/15 steps.

The process exited 133 (SIGTRAP), not a Python exception or budget/time stop.
Five HTTP requests returned 200 and settled in the durable spend journal:
**50477 input + 722 output = 51199 tokens**. All five usage records are known;
no balance error was observed. Monetary cost is unpriced. Four distinct image
hashes appeared ten times in requests. Five tool calls started, four have results;
the final launch_app has no result. There is no driver_done, trial result, final
report, batch-result or automatic cleanup record. Do not manufacture a normal
strict failure or success from these incomplete artifacts.

The macOS crash report identifies python3.13 PID 67896, faulting thread 2,
EXC_BREAKPOINT/SIGTRAP and _dispatch_assert_queue_fail. Its native stack includes
islGetInputSourceListWithAdditions → TISCreateInputSourceList →
TISCopyInputSourceForLanguage, followed by ctypes and Python asyncio frames.
The benchmark's RepinImeAfterLaunchTool calls pin_ascii_input_source after a
successful launch; _select_english_source calls that Carbon API. The harness
runs the async pilot on a worker thread. This locates a native queue/thread
constraint failure in the IME path; the required scheduling fix still needs a
local reproduction and validation. Python try/finally cannot recover from this
process-level trap. The preceding cmd+tab is recorded context, not proof that
it alone caused the crash.

The point-format batch at turn 2 was accepted and dispatched four clicks. Its
first target maps to Quartz (1661,262), to the right of the Calculator visible
in the initial frame. Turn 4 sent cmd+tab. The last saved feedback image has a
Finder menu bar and black background; the earlier Calculator rectangle is all
black on pixel inspection. There is no final screenshot verification of 56.
A later local AX recovery read returned 0. These partial observations cannot
establish a point-vs-legacy success-rate comparison.

Recovery was performed without any new model request:

- The crashed process and its backdrop were absent. Native keys/buttons were
  empty before and after inspection, so no synthetic releases were necessary.
- Calculator was closed; the session application was made visible again.
- Original hidden-app list, cursor and input-source restoration were not
  recoverable from the in-memory baseline. Other applications were not blindly
  unhidden because pre-existing hidden state is unknown. The clipboard snapshot
  was also only in memory; the saved trace contains no type_text call. Full
  restoration remains unknown and is not relabeled confirmed.

live/recovery.json preserves operator checks separately from the immutable raw
batch data. Its first unhide return value was false; a subsequent open-by-bundle
and fresh state check confirmed the conversation app visible. Calculator's
asynchronous quit was likewise confirmed by a fresh check. No automatic cleanup
or complete desktop restoration is claimed.

summary.json derives usage and completion status from the raw trace/journal.
crash-summary.json retains selected exception fields and symbol names, plus the
original local crash-report filename/hash; the full system report is not copied.
artifacts.json binds these files and the exact launcher. Earlier evidence and
freezes remain unchanged. No production source changed during this run.

Next: fix and locally validate IME queue/thread affinity; persist a recoverable
non-secret desktop baseline before hiding apps/moving the cursor, with cleanup
outside the process that can crash. Include native app-switch/launch re-pin
reproduction and subprocess-crash recovery tests. Do not send another paid trial
until these issues are resolved. This B pilot remains incomplete; its retry,
three other pilot variants, twelve core trials and phase-transition work remain.

Regression validation: backend **5015 passed / 1 skipped**, E2E **16 scenarios /
63 steps**; web lint/TypeScript, backend/CLI ruff, development-server log,
docs and protocol checks passed. No Python code changed; pyright N/A. These
passing suites mock the native IME boundary and do not resolve this live crash.
