# M5 pixel-change tolerance

> 状态：2026-09-22，按用户要求移除像素一致性动作门禁；本地验证通过，无模型请求。

Frame validation no longer takes another screenshot or compares pixel hashes.
Frame identity, session/window ownership, window bounds, display geometry and
pre-dispatch stop checks remain. Observation image/scene hashes remain evidence,
not admission conditions. There is no similarity threshold or hidden retry.

This permits blinking carets, animation and unrelated application changes. It
also permits same-geometry content changes such as a moved button or popup;
the planner must inspect feedback and re-observe when needed. Pixel equality
was neither semantic target validation nor an atomic guarantee against changes
between checking and dispatch. Existing feedback and failed-batch rules remain.

Tests first reproduced three failures with inside/outside single-pixel changes.
The four full/window cases now allow dispatch and assert zero validation captures.
Two integrated/split cases permit complete repaints, including during locator
HTTP. Geometry changes still stop batches, and stale/session/window checks and
cancellation/deadline/revocation still prevent input. Stop tests now inject at
the geometry boundary rather than the removed screenshot boundary.

Local native verification retained independent before/after diagnostic captures.
Both full-screen menu-bar changes and window-bound Calculator input changes pass
validation with zero captures inside validation. This probe validates frame
admission; it does not dispatch a model-selected click or establish task success.
The first attempt stopped at Calculator reset, before either case. After explicitly
activating and positioning the window on the main display, the retry passed.
Both attempts restored apps, clipboard and cursor, closed controlled windows,
and observed no pressed keys/buttons. Generic timeout/cancel cleanup is pending.

Exact scripts, original captures, results and both cleanup records are archived;
artifacts.json hashes raw evidence. Diagnostic changed_pixels counts luminance
changes, not all RGB changes. No screenshots were sent externally. Old scene
reports and failed pilot evidence remain immutable historical results. Refresh
source pins before any next paid experiment; no production token settings changed.

Validation: backend **4988 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, changed-file pyright (three files), running
backend log, docs and protocol synchronization passed. Implementation: `978ca00`.
