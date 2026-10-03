# S3 real DOM multilayout acceptance — 2026-10-03

Status: 15 focused cases and full validation passed; evidence collected and independent review complete.
Baseline: `7d65d058`. No production behavior or model prompt change; no paid model calls.

## What actually runs

Each case starts a real isolated headless Chromium against an ephemeral local HTTP
server. Three authored layouts use a flex toolbar, a two-row table and an open HTML
dialog. The existing DOM channel generates the actual semantic snapshot, candidates
are produced by ActionBuilder, and JevSelector sends that state through the real
TaskModelTransport. Only model HTTP is replaced with a fixed fixture response.
Actions execute real page click handlers; fresh channel observations verify outcomes.
A separate page event log and direct DOM read check clicks/results independently of
the model's reply. Browser disconnection and model-client closure are asserted.

Each layout covers five scenarios:

- Sufficient identity: select the intended offered action, click exactly once, obtain
  a new observation and verify `status:Result = selected:K7`; controller completes.
- Missing identity: the fake model returns `need_more_context`; no action is dispatched.
- Conflicting identity reports for the same slot: the fake model returns `ambiguous`;
  no action is dispatched. These two cases do not prove the host independently detects
  missing/conflicting evidence, or that an actual model would refuse.
- Stale selected node: replace the actual button after the model request captures it
  but before the response returns. The host rejects `stale_reference`, with zero clicks.
- Unverified effect: click handler records one click without updating the postcondition.
  Bounded readback leaves `unknown/effect_unknown` and `pending_effect=true`; no retry.

This is three controlled DOM layouts, not arbitrary website or native AX acceptance.
No user browser/profile, account, physical keyboard/mouse or external model endpoint
is used. Real page observations are still page reports, not verified backend business
facts. An open HTML dialog is not an OS-native modal dialog. The scripted selection
is a test fixture; its perfect outcomes are not a model-performance measurement.

## Evidence and reproduction

`raw/` contains one JSON per layout/scenario: source HTML, actual model payload/fixed
reply, final channel snapshot, audit, TaskResult, direct page read and click log.
Three `*-sufficient.png` images show the actual rendered pages after successful input.
A manifest records source/artifact hashes after the collection run.

From backend, use a new artifact directory:

```bash
TANK_REQUIRE_CHROMIUM=1 TANK_DOM_EVIDENCE_DIR=<new-directory> \
  uv run --no-sync pytest plugins/agent-computer-use/tests/test_dom.py \
  -k real_dom_multilayout -q
```

The required-Chromium flag forbids skipping when the optional dependency or executable
is missing. Existing artifact filenames refuse overwrite. No credential is loaded by
these tests, and all model responses use a fake endpoint/credential. Existing unrelated
backend tests retain their usual test isolation.

The initial fixture test failed before its helper existed. The first full 15-case run
reached the intended control outcomes but failed an incorrect cleanup assertion that
required the Python Browser object to be cleared. It was corrected to assert actual
connection disconnection. Production cleanup behavior was not changed.

Next work can add explicitly bounded real-model selection on these captured/controlled
pages and then more representative applications; it must not relabel this mocked-model
integration evidence as model acceptance. S3 representative validation and S4–S6 remain open.

Final verification: backend **5578 passed / 1 skipped / 21 warnings** with Chromium
required (`/tmp/tank-s3-dom-multilayout-backend.log`); E2E **17 scenarios / 67 steps**
(`/tmp/tank-s3-dom-multilayout-e2e.log`). Web lint/tsc, backend/CLI lint, changed-test
pyright, dev-server log and docs/diff checks passed. Protocol artifacts did not change.
The 15 new Chromium cases ran, none skipped. Collected records show 3 completed,
9 stopped, 3 unknown and six actual page clicks across those 15 cases; all browsers
were disconnected and each fake-model client closed. Source/artifact hashes and mock
model accounting were checked. The three screenshots were visually inspected.

See [manifest.json](manifest.json), [toolbar](raw/toolbar-sufficient.png),
[table](raw/table-sufficient.png) and [dialog](raw/dialog-sufficient.png).

Test implementation commit: `ac1597e7`; raw evidence commit: `e41a9ebc`.
Independent review checked all source/artifact hashes, 15 records, model-call audit,
DOM origin, effects and connection closure. Round 1 corrected stale README/plan status
text; round 2 self-check found no remaining issues. Those documentation corrections
were self-reviewed. Tests, production code and raw evidence were unchanged in review.
Docs/diff checks passed; final full regression logs were reused. The coordinator
inspected the final diff and evidence. No paid API calls or credential reads occurred.
