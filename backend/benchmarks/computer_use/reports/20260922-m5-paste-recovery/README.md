# M5 local paste recovery

> 状态：2026-09-22，Command 残留已复现并修复；仅本地验证，未新增模型请求。

The same local Calculator experiment before and after the fix pasted `56`,
read the AX display, then cleared and typed `7`. Before: the display was `56`
but key 55 remained down. After: the display was `56` and no keys were down.
Both runs subsequently displayed `7`; this evidence establishes the modifier
leak, not a causal explanation for every failed input in the original pilot.
Both runs restored the clipboard/input source and closed Calculator. The
finally block explicitly released V/Command; the recorded `after_paste_keys`
was sampled before that recovery. No screenshots or model requests were made.

The production clipboard path now sends balanced Command/V events and releases
both keys in finally blocks, including partial dispatch failures. Stateful unit
regressions failed before the fix and passed afterwards. This is a shared macOS
input-tool correction, not a production token-budget change or a general physical
cleanup guarantee. OS-level key-up delivery failures can still require recovery.

With the corrected path, replaying the six pilot text inputs yielded displays
`7`, `7`, `78`, `78`, `0`, `0`, with no held keys at every checkpoint. Calculator
ignored pasted `×`, `=`, and `7*8=`. Text dispatch is therefore not calculator
operation success. The tool must not silently translate arbitrary pasted text
into application-specific commands. The earlier deterministic key-press oracle
already established `7`, `shift+8`, `8`, `enter` produces `56`.

Two malformed pilot payload shapes now have integrated-mode regressions:
unsupported batch `screenshot="true"` and a JSON-string location remain rejected
without clicking or calling a locator. Unknown arguments now name the offending
fields rather than misleadingly claiming split mode. Protocol restrictions remain.

Scene validation remains unchanged: it compares the current cursor-free capture
against the observed crop's exact pixel hash and geometry. The original trace
does not archive the rejected validation captures, so it cannot distinguish menu
clock changes, animation, or other scene changes. Do not label those rejections
false positives or bypass the check. The next diagnostic work needs local paired
observation/validation captures and a scoped decision about scene stability.

The original failed trial and its source/request freezes remain immutable.
Any next paid trial needs fresh source pins and an explicit execution scope;
this report does not authorize or initiate one. Remaining M5 work includes scene
attribution, automatic physical cleanup, refreshed pilot preparation, remaining
pilot groups and paired core comparisons.

Evidence: `before.json`, `after.json`, `input-replay.json`; exact local scripts
are saved as `.py.txt` with SHA-256 hashes in `artifacts.json`. No clipboard
contents or credentials are stored.

Validation: backend **4983 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, changed-file pyright (four Python files),
running backend log, docs and protocol synchronization checks passed.
Implementation commit: `210dd46`. The failed pilot remains failed.
