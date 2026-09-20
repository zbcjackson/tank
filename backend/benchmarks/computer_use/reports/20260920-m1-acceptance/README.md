# M1 acceptance — 2026-09-20

M1's bounded input, local image-evidence and prompt-only comparison work is
complete. This does **not** establish better model grounding, a real-model GUI
closed-loop score, generic automatic pixel grading or multi-display support.
Production input fixes are committed as `dac426f`; default model and coordinate
interface remain unchanged. The active plan continues with M2/M3/M4.

## Prior cleanup and execution environment

[Prior cleanup](prior-cleanup.json) confirmed the old controlled TextEdit document
was still open and unmodified. It was closed by exact path. Closing while
iterating invalidated an AppleScript document index; an independent subsequent
query returned zero matching documents. Other documents were not closed.
The old clipboard restoration cannot be verified retrospectively: the prior
script kept its snapshot only in memory. The prior trial dispatched no input.

Screen Recording and Accessibility were available outside the execution sandbox.
Sandboxed AppKit did not expose the foreground application. AppleScript activate
alone again failed the foreground gate; native activation plus pumping the
AppKit run loop allowed the controlled tests to proceed. This does not establish
an AppleEvent timeout root cause or change production app activation.

The first two new attempts dispatched no test inputs and confirmed document,
clipboard and foreground cleanup: [attempt 1](matrix.json),
[attempt 2](matrix-02.json). [Attempt 3](matrix-03.json) reproduced the IME failures
and stopped at Calculator setup. Its document/clipboard cleanup passed;
foreground initially appeared unconfirmed, then a separate native read observed
Paseo in front before the next trial. [Calculator preflight](calc-preflight.json)
subsequently confirmed display access and foreground restoration.

## Input matrix and fixes

[Attempt 3](matrix-03.json) inserted `Abc123` as `啊A编程23` under the current
non-ASCII-capable input source; explicit paste, punctuation and Chinese worked.
Enter after IME-processed text did not produce the intended newline. A failing
unit test preceded the fix: `auto` now checks the current Carbon input-source
ASCII capability and pastes when it is false or unavailable. ASCII-capable
sources retain the existing alphanumeric keystroke path. The tool reports the
actual path used, and does not change the user's input method.

[Attempt 4](matrix-04.json) passed all six TextEdit cases and reproduced
`shift+8` inserting `8` in Calculator (`788` instead of `7×8 = 56`). A second
failing test preceded using physical key codes for shifted mapped keys. Ordinary
character shortcuts retain their existing path.

Attempt 4 also showed that the controlled windows were on a secondary display.
Its main-display screenshots are **not** visual evidence for those app results.
The final trial moved the test window and Calculator to the main display and
restored Calculator's original position afterwards.

[Final matrix](matrix-05.json) records all 14 cases:

- TextEdit: alphanumeric, punctuation, Chinese, multiline, forced paste and
  separate Enter all matched the expected document text (6/6).
- Calculator: `123` via auto/paste → `123`; `7*8` via auto/paste → `56` without
  a displayed expression; `1.5` → `1.5`; letters and Chinese were ignored (`0`).
  Ignored input is recorded as application behavior, not successful text entry.
- Separate `7`, `shift+8`, `8`, Enter produced expression `7×8` and result `56`.
  This establishes keyboard/input semantics, **not mouse grounding**. Paste
  cases do not become historical strict-expression successes.
- Cleanup independently confirmed: temporary document closed, all saved
  clipboard item bytes/types restored, original foreground restored, Calculator
  reset to zero and original window position restored.

## Local pixel evidence and SDK feedback

Actual production `ScreenshotTool` captures have image hashes and timestamps.
Full screenshots remain only in `/tmp/tank-m1-20260920/`; none are in this report
or sent to the Qwen endpoint. Display-only crops use the recorded main-display
window bounds, with hash-linked originals.

[Local OCR](pixel-check.json) uses Apple's Vision framework with language
correction disabled. [Initial truncated ROI](pixel-check-v1-truncated-roi.json)
and [expanded Vision ROI](pixel-check-v2-vision-roi.json) are retained, including
misread digits and unknowns. OCR recognizes the complete keyboard result
`7×8 = 56`, but misreads some isolated digits (including `56` as `99`). Thus
this is **not a reliable general automatic grader**; disagreements stay unknown
for acceptance rather than proving wrong application output.

[Independent visual review](visual-review.json) of the eight local display-only
crops confirms the visible results recorded above, including `0` for the negative
control, which rejects a false expected `56`. Reviewer: this assistant examining
the crops, independently of the deterministic input script; not the Qwen action
model and not a claim of human sign-off. Generic benchmark `pixels` remains
`unknown`; these per-image observations do not rewrite old reports.

[SDK replay](sdk-image-replay.json) passed all 14 captured images through the
production screenshot follow-up message builder and actual OpenAI SDK to an
in-process fake HTTP transport. Every serialized image matched its capture hash.
Capture and HTTP timestamps are both recorded. This verifies saved-image
feedback serialization; it does **not** claim a live provider received the real
screenshots or establish screenshot freshness during a real-model GUI task.

## Prompt-only model A/B

[Manifest](prompt-ab-manifest.json), [per-request results](prompt-ab-results.json),
[summary](prompt-ab-summary.json) and `prompt-ab-responses/` retain all outcomes.

The actual configured Qwen model and DashScope endpoint handled 12 serial
requests: three generated layouts × two repetitions × old/corrected system
prompts. Both variants reuse the M0 request tools and settings, including the
historical input-tool descriptions; this freezes the prompt factor independently
of today's input fixes. The same synthetic image and task are used within each
pair. Both add `stream_options.include_usage=true`; actual SDK HTTP payloads
were checked against the prepared requests. No model action was executed.

Each request was bounded by 60 seconds and 40,000 output tokens, with zero
retries; the batch had a conservative 300,000-token stop. Actual usage was
73,940 tokens across all 12 requests, all reporting the configured model ID.
There was no independent verification of the provider's internal deployment.
Pricing checked against the [official Beijing pricing page](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash):
$0.028/M input, $0.11/M output for input ≤32K. Budget estimate was $0.018
(conservative request-cap estimate $0.064). Reported usage implies about
$0.00236 at uncached list price; this is an estimate, not an invoice.

Both variants hit **0/6**. All responses selected the available `click` tool;
no self-delegation occurred in this small sample. Legacy produced six parseable
points, corrected produced one parseable point and five malformed bbox values.
Malformed responses remain failures. Coordinates were scored against the
synthetic rounded-button mask, with no clicks and no compensating transform.
Three layouts, not six independent layouts, underlie each score.

Conclusion: the deterministic prompt conflict is removed, but this small
first-action comparison shows **no grounding benefit**. It also does not prove
that the prompt causes malformed boxes in general. Keep failures for M3,
retain the current default model, and test full task effects in M5/M6.

## Tests and verification

- Red→green regression tests for IME-sensitive ASCII text and shifted digits;
  native input-source ownership/null-property cases; existing paste, Chinese,
  punctuation, batch and keyboard regression tests: 93 passed.
- Complete backend workspace: **4508 passed / 1 skipped** (including N2/SDK).
  The first sandboxed run could not bind local servers or resolve the TTS host;
  rerun with the required OS/network access passed in full.
- E2E: **14 scenarios / 55 steps passed**.
- Web ESLint and `tsc -b --noEmit`; backend/CLI ruff; both changed Python files'
  pyright; actual `tank:1.1` reload log: passed.
- Docs consistency and protocol sync: passed. Protocol's uv subprocess required
  the same unrestricted macOS execution environment as the test services.
- Test environment: `UV_CACHE_DIR=/tmp/tank-uv-cache`,
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`; no production config change.

Local experimental scripts, raw requests, full screenshots and execution logs:
`/tmp/tank-m1-20260920/`. Repository artifacts contain only controlled test text,
hashes, statistics and synthetic-model replies; no clipboard contents or secrets.
