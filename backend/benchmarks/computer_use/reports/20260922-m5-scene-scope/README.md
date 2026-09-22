# M5 local scene-scope diagnosis

> 状态：2026-09-22，本地对照完成；未新增模型请求，未修改生产场景校验或实验冻结。

A controlled Calculator desktop with a black background was captured through the
production cursor-free screenshot path. Each case took a fresh FrameTool
observation, waited 1.2 seconds, then invoked the actual observation validator.
The diagnostic wrapper retained the exact observation and validation PNG bytes.
No click was dispatched, no model client was created, and no screenshot was sent
externally. The input-control case sent a local `7` key press.

Results:

- Five full-screen idle cases: all rejected despite an unchanged Calculator crop.
  Changed pixels were confined to the menu-bar status area (x=1686..1775,
  y=7..26 across the cases), outside Calculator (600,100)-(1274,508).
- Three window-bound idle cases: all accepted while the menu bar still changed.
- One window-bound input case: rejected after `7` changed the Calculator image.
  Window-relative changed bounds were (487,95)-(664,167).

The inspected image shows status icons in this area; do not call this a proven
clock change. These paired captures establish an unrelated menu-bar-change
failure mode of exact full-screen hashing. They do not identify the cause of the
two historical pilot rejections, whose validation captures were not archived.

Four deterministic ToolManager/FrameTool regression cases preserve the scope
contract: a one-pixel menu-bar change rejects a full frame but permits an unchanged
window crop; a one-pixel change inside the window rejects both. Rejected cases
produce zero native click events. No hash tolerance, automatic crop switch or
coordinate coercion was introduced.

A window-scoped diagnostic is viable locally, but changing the model's image
scope also changes coordinate mapping and comparison conditions. The next live
preparation must specify one consistent observation policy across variants and
refresh source/config/request pins. Do not silently reuse the old A-control
freeze with window crops or treat this local test as an A/B result.

Cleanup: the external local script closed Calculator and its background, restored
hidden apps, clipboard and cursor, joined its worker, and observed no pressed keys
or mouse buttons. This is normal-exit local cleanup evidence only. The benchmark
driver still reports unknown physical cleanup for built-in grounding runs:
joining in-flight native operations is not an OS key/button release check. A
reusable cleanup hook, error/timeout/cancellation verification, and reporting into
the serial batch gate remain unfinished. Do not remove cleanup_unconfirmed.

Evidence: `local/result.json` records observation IDs, crop/geometry, PNG hashes,
rejection results and pixel-difference bounds; `local/*-before.png` and
`local/*-after.png` are exact local captures; `local/cleanup.json` is the final
restoration check. `changed_pixels` counts nonzero luminance differences and is
not a general RGB changed-pixel metric; rejection uses the production RGB hash.
`probe.py.txt` is the exact one-off script, not a reusable executor. All raw files
are hashed in `artifacts.json`. Original pilot evidence remains immutable.

Validation: backend **4987 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, changed-file pyright, running backend log,
docs and protocol synchronization passed. Regression commit: `bd90b81`.
