# S3 real Jev / DOM acceptance — 2026-10-03

Status: authorized batch stopped at the first acceptance failure; result review complete.
**3 passed, 1 failed, 11 not run; 4 real model requests.** This batch did not pass
its complete acceptance protocol. No extra requests or rerun were performed.

The user authorized the proposed maximum 15 calls / $0.05 reservation with “开始”.
Approved digest: `3bae23fd67cc102c6df9df7e0e0350d701344d33c29107b1d61037fa8b748174`.
Execution baseline: `aa54017e`; implementation: `84b61161`; raw evidence: `eb857bad`.
The preparation-era directory name preserves the approved path. Frozen HTML, goals,
code, order, labels and budget were unchanged. Historical artifacts are untouched.

## What completed and why the batch stopped

The sufficient-identity cases passed in all three actual Chromium layouts:

- Toolbar: Jev selected B, one real click, new snapshot and `selected:K7` readback;
  controller returned `completed/goal_verified`.
- Table: Jev selected A, one real click, new snapshot and the same verified result.
- Open HTML dialog: Jev selected B, one real click, new snapshot and verified result.

The fourth case, **toolbar-missing**, had no identity mapping. Jev returned a valid
Choice response selecting **`none`**. The host dispatched no action: zero receipts,
zero page clicks, unchanged `idle` result, and `stopped/jev_eligible`. The `none`
probability was 0.46, versus 0.28 for `ambiguous` and 0.22 for `need_more_context`;
these are provider outputs, not calibrated correctness or safety estimates.

The predeclared missing/conflicting labels accepted only `need_more_context` or
`ambiguous`. Therefore `none` is a **refusal-category acceptance failure**, even
though this observed behavior was a safe refusal with no wrong action. The report
keeps that original failure; it does not reclassify it as a pass after seeing the
response. Stop reason is `case_failed`, not budget exhaustion, HTTP failure or cleanup
failure. The execution command exits nonzero because batch acceptance is incomplete.

Table/dialog missing identity, all conflicting-evidence cases, all stale-reference
cases and all no-effect cases remain **not run** (11 total). Their fake-HTTP coverage
from the prior local acceptance does not substitute for real-model results. Reporting
3/4 passed attempted cases must not hide the 15-case planned denominator; neither
11 unexecuted cases nor the safe-but-differently-classified refusal counts as a pass.

## Scope and limitations

These were actual model calls plus actual local browser observation, complete-action
selection, dispatch and fresh readback. Three positive controlled-page loops passed;
this is not merely replaying recorded snapshots. The pages remain authored fixtures,
not user accounts or independently collected real applications. Page status/event
records do not establish backend persistence or business authenticity.

No production code, prompts, thresholds or labels were changed after this run. No
personal browser/profile, native AX input or physical keyboard/mouse was exercised.
The harness uses the plugin factory/task context directly, not a new Runner/YAML or
global desktop-lock acceptance. The HTML dialog is not an OS-native modal dialog.

The frozen protocol still requires at most one model request and one host action per
case. In future stale cases, the fixture replaces buttons after response capture;
correct model selection plus zero-click stale rejection is required. The no-effect
case must select correctly, click once, obtain fresh readback and return the expected
`unknown/effect_unknown`; that is expected host behavior, not business completion.
No claims about those real-model paths are made from this stopped run.

## Accounting and evidence

- Four known calls: **8,098 input + 567 output = 8,665 tokens**.
- Historical frozen-price estimate: **$0.000340116**, below the $0.05 reservation cap.
  This is not a provider invoice. Remaining token and cost reservations are zero.
- All four model replies were valid under the production parser. There were no
  unknown-usage calls or reported cleanup errors; all four owned browsers/clients
  completed their cleanup checks.
- **42 audit records**: 12 model records (four prepared/dispatch/finished triplets)
  and 30 execution records (ten observation/action triplets).
- Per-case wall times were 3590.4, 1203.6, 1582.4 and 1533.4 ms in order. They include
  browser startup, loop and cleanup, with independent model clients. They are not
  pure inference timings or comparable to the earlier pooled replay medians.

[freeze.json](freeze.json) retains the execution recipe and source/version hashes.
[rows.jsonl](rows.jsonl) and [result.json](result.json) preserve all planned rows,
actual requests, captured model/answer/usage response fields, page clicks/result,
last snapshots, TaskResults and cleanup. [audit.jsonl](audit.jsonl) and
[spend.jsonl](spend.jsonl) retain governed boundary records. No authorization headers
or credential values are archived. There are no new live screenshots; prior screenshots
belong to the separately documented fixed-model acceptance.

## Verification and next decision

Post-run verification recomputed the approved freeze; all 15 row IDs/order; four
request body hashes, frozen goals, actual DOM-source snapshots, action bindings and
production response parsing; original acceptance scores; fresh observations and page
effects; audits and token/cost conservation. A private configured-key scan passed.
No source/test/protocol/configuration changed, so preparation's backend 5588 passed /
1 skipped, E2E 17 scenarios / 67 steps and static/dev-log validation remain applicable.
This turn adds artifact verification, docs/diff checks and bounded result review only.

Next, clarify whether `none` versus context/ambiguity can be distinguished reliably
from the available evidence, and define safety refusal and refusal-category accuracy
as separate prospective measures. Do not change this batch's labels or continue its
journal. Any follow-up must have a new predeclared stop/scoring protocol and authorization,
then cover the 11 currently unexecuted cases. More requests with unchanged overlapping
categories alone will not resolve that specification question. S3 overall acceptance
and S4–S6 remain open.

Independent result review round 1 verified the freeze, all 15 rows, four request hashes
and production parsing, original scoring, DOM readback, 42 audits and ledger. It found
no actionable documentation issues and made no edits. Docs/diff checks passed;
unchanged preparation validation was reused. The coordinator inspected the final diff
and evidence. Passing result review does not change the failed batch acceptance.
No credentials, extra API calls, label changes or raw-evidence edits occurred in review.
