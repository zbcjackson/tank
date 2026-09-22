# M5 first live A-control pilot

> 状态：2026-09-22，真实 pilot 已执行 1 轮，strict 失败；停止后完成操作员清理，未追加 trial。

A-control ran calc-open with qwen3.7-flash-2026-07-15 on the configured DashScope
Beijing compatible endpoint. The user explicitly approved this single trial and
Calculator/black-background/menu-bar screenshots (including feedback), at most
16 HTTP requests and 120 agent seconds. Token/cost admission was record-only;
the effective agent token budget was zero. Production config was unchanged.

Results: 16/16 HTTP responses were 200, with 293,621 input and 1,822 output tokens
(**295,443 total**); no unknown usage or insufficient-balance response. Agent
time was 62.83 s; full trial time was 72.19 s. It reached 15 top-level tool steps,
with 11 successful primitives reported. There were 11 unique image hashes and
86 image occurrences across HTTP requests as image history accumulated. These
are real provider-reported usage counts; monetary cost remains unpriced and the
actual bill is unknown. Zero ledger monetary fields do not mean free requests.

The strict validator failed and returned display result `0`. Independent local
review of the final screenshot also sees `0`, not `56`. This one diagnostic trial
is not an estimate of success rate or an A/B/C/D comparison.

## Observed failures and limits of attribution

- The batch call included an unsupported `screenshot` argument (string `true`)
  and was rejected. The error text says split-mode despite this being integrated
  A-control; preserve the original evidence, do not infer the mode from that text.
- Two click attempts were refused because the scene/geometry changed. A later
  legacy location was a JSON string and was rejected as invalid. Those rejected
  clicks cannot be credited with completing calculator actions.
- The model sent `type_text` with `7`, `×`, `8`, `=`, `AC`, and `7*8=`. Dispatch
  success did not establish application effect; the final display remained zero.
  The trace/validator keeps business and mouse-only assessments unknown because
  input evidence is incomplete. No guessed semantic cause is promoted to truth.
- Driver cleanup remained unknown and the batch latched `cleanup_unconfirmed`.
  The external cleanup check found Command key 55 still pressed. A subsequent
  explicit key-up recovered it; keys and mouse buttons then read empty. The exact
  origin of the stuck modifier is not established by this observation. Do not
  relabel the original trial as automatically cleaned up or safe for continuation.
- Calculator/background windows were closed; hidden apps, cursor and clipboard
  were restored. No remaining pilot or core trial was started.

Next: reproduce the modifier/input and scene-rejection problems deterministically,
then fix and revalidate before resuming model trials. Token/cost bounds no longer
block this record-only experiment; this trial nearly reached the old 300k token
reference mainly through repeated input, not a large generated answer.

## Local preparation and evidence

Nine-point image/window calibration passed 9/9 with down/up delivery and exact
coordinates. A deterministic Calculator key sequence produced `7×8=56`; local
AX and screenshot agreed, and keys/buttons were released. Earlier preparation
failures (window ID type, off-main-display restored window and one reset failure)
are recorded in `preflight-attempts.json`. Positioning at (600,100), size 674×408,
made the final Calculator check pass; scientific layout was retained.

One local preview had an uncovered Finder window because the background followed
NSScreen.mainScreen instead of Quartz's captured display. It was rejected on local
visual review and was never sent to the model or archived here. The final backdrop
was bound to CGMainDisplayID, kept visible on deactivation and reviewed before
releasing the live request. Screenshot scope guards rejected other visible regular
apps or a missing backdrop. Menu bar remains intentionally inside the approved
scope. This is a controlled single-trial setup, not a general privacy guarantee.

The initial live launch was rejected by automatic approval review for lacking
explicit payload/destination authorization. No request was sent then. The user
subsequently approved the exact scope and endpoint, after which the launch passed.

- `summary.json`: actual totals and per-request input/output/image counts.
- `live/batch/`: immutable plan, journal, report, trace, images and raw SSE bodies.
- `live/cleanup.json`: original cleanup observation, including pressed key 55.
- `live/cleanup-recovery.json`: explicit release and successful final recheck.
- `oracle/`, `calibration/`, `local-preview/`: local-only preparation evidence.
- `launcher.py.txt`: exact one-shot operational script, not a reusable executor.
  Existing output directories prevent replay; credentials were loaded only in memory.

Tests: backend 4978 passed / 1 skipped; E2E 16 scenarios / 63 steps passed.
Web lint/TypeScript, backend/CLI ruff, development-server log and protocol checks
passed. No production Python changed (changed-file pyright N/A); docs consistency
also passed. These regression results do not convert this failed pilot to a pass.
