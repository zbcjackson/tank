# Native text Advisor pilot

Date: 2026-10-08. Status: fake HTTP 9/9 passed; authorized real-model batch
finished with 1 passed, 1 unknown failure and 7 not run. S4 remains open.

## Recipe and boundaries

Revision `s4-ax-advisor-1`, frozen digest
`6b991d00cec7cf65256b13fd1cdb5ef701bb248d09802b5cada3f5ae96d50202`.
The same recipe is in `fake/freeze.json` and `live/freeze.json`.

The existing nine-case native matrix now configures both core services:
Jev `jev-1.13.0` at `https://api.typesafe.ai/v1/systemone`, and text Advisor
`qwen3.7-flash-2026-07-15` at
`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`.
The latter uses the existing BAILIAN credential, a 2048-token output cap and
disabled thinking. Credentials never appear in the recipe or captured payloads.

Both services share 78 SDK-call admissions and a $0.25 estimated batch ceiling;
each task has 120 seconds and at most four Advisor calls inside its total call
allowance. Prices are inherited conservative benchmark contracts, not current
provider invoices. A full-context Qwen reservation needs about $0.165 available,
so trial reservations use the same $0.25 ceiling, still subject to the shared
batch ledger. One failed/unknown result, unknown usage or unconfirmed cleanup
stops the batch and retains all planned rows. SDK-call counts are not an
independently observed wire-request count.

## Real applications, fake HTTP

All **9/9** cases passed: three Calculator AXPress, three Calculator Quartz and
three temporary TextEdit tasks, including one moved-window case in each group.
Independent AX reads found expression `7×8`, result `56`, or the exact supplied
Unicode/newline document body. Every input cleanup, owned-process cleanup,
position restoration and foreground restoration was confirmed.

There were **33 mock HTTP requests, zero external model requests**: 21 Jev and
12 Advisor. Each Calculator trace exercises Jev escalation → Advisor's `7` →
Jev's Multiply and `8` → progress review → Advisor's Equals. This deterministic
sequence verifies wiring and execution, not real model planning competence.
TextEdit completes through Jev in one call per case.

`fake/result.json.gz` contains requests, structured responses, receipts, independent
readbacks, Advisor events and cleanup evidence. `fake/spend.jsonl.gz` is the ledger.
No historic report or failure denominator was rewritten.

Artifact SHA-256:

- `fake/result.json.gz`: `2c95dcc62f9dc518da843ea144c12b3868eda86b1e0157e7d97334e548deab39`
- `fake/spend.jsonl.gz`: `2146a2881431cbed0ef2451db44a6783afe1dad4f0452855e86d02909d27b5ff`
- Either `freeze.json`: `ef38670fb7839dc0cb188889f515ba4b5c2645fbf4f926984a0238a072706404`

## Live gate

Automatic approval review rejected the live command because AX text, candidate
actions and task goals would be sent to the new Dashscope/Qwen destination, and
prior consent did not explicitly cover that destination and payload. It rejected
process creation at that time. After the coordinator explicitly listed both
destinations, AX text/action/goal payload, existing credentials and the 78-call /
$0.25 estimated limits, the user replied “开始”. The identical frozen command then
passed approval and ran. No indirect execution or substitute endpoint was used.

## Authorized real-model result

The nine planned rows remain: **1 passed / 1 failed (unknown) / 7 not run**.
The batch stopped immediately after the second case, with no retry or replay.

First Calculator AXPress case, 16.06 seconds, eight successful model calls:

1. Jev selected `7`, `8`, `7`, leaving `787` without goal evidence.
2. Advisor selected Clear on `goal_progress_unverified`, then `7` and Multiply
   on the two `repeated_state` reviews.
3. Control returned to Jev, which selected `8` and Equals.
4. All eight local effects were verified; independent AX readback confirmed
   expression `7×8` and result `56`, with `completed / goal_verified`.

Second Calculator AXPress case (window moved before observation), 13.31 seconds:
Jev selected `7`, `8`, `7`; Advisor selected `8`; Jev selected `7`, `7`; Advisor
then selected **Close Parenthesis**. All seven calls returned and seven actions
had `sent` receipts. Only the first six effects were verified. The final click
had no verified readout change; the host returned `unknown / effect_unknown`.
Independent readback still showed `787,877`, with no expression value returned.
This is not a model-call/HTTP failure, and the evidence does not establish that
moving the window caused it. The selected planning actions did not complete the
goal; the system correctly avoided replaying an action with unverified effects.

Both tasks confirmed input cleanup, owned-process cleanup, window position and
foreground restoration. Remaining AXPress, all Quartz and all TextEdit live
rows were not run. Those routes have only this batch's fake-HTTP acceptance.

There were **15 admitted SDK calls: 10 Jev + 5 Advisor**, with known usage for
all calls: **279,079 tokens**, estimated **$0.019972257** under the frozen price
contracts, zero outstanding reservations. This is not a provider invoice or
an independent wire-request count. No model transport failures were reported.

This establishes one real Advisor correction → Jev return → verified native
goal completion. It does **not** establish stable planning or full S4 acceptance.
Next investigate the failed Advisor choices using the captured request/response
and current candidate mapping before preparing any further live batch.

Evidence: `live/result.json.gz`, `live/spend.jsonl.gz`, `live/summary.json` and
`live/started.json`, all bound to the unchanged recipe above. SHA-256:

- `live/result.json.gz`: `1cd21575708832567862fb2096f96109ae06067a30e6f6a36582ecedec25d278`
- `live/spend.jsonl.gz`: `afc94fa29102e3ff33fc873a399091b402ba161ef6556f18138fa222941d9b05`
- `live/summary.json`: `61a00b298eca0578f5adf880776c22cdfa725a078ea9e3dba9bcdec29ad046cc`

## Verification

Native tests: **53 passed**, including both SDKs, shared 70-token accounting,
Advisor→Jev return, progress review and a shared one-request cap that blocks the
Advisor before any native action. Changed-file pyright: zero errors. Backend and
CLI ruff, web lint and tsc-b, docs consistency and diff whitespace checks passed.
E2E: **18 scenarios / 71 steps passed** in 94 seconds under temporary caffeinate.
Backend full suite: **5692 passed / 1 skipped / 21 warnings** in 350.52 seconds
(`caffeinate -is uv run pytest`). Both frontend and backend tmux error queries
were empty. The protocol was unchanged.

Independent review-and-refactor round 1, baseline `5247e6c0`, found no confirmed
actionable issues and made no changes. The reviewer independently reran all 53
native tests, checked the artifact hashes, nine successful readbacks and cleanup,
and the absence of live execution. Full-suite/E2E evidence was inherited from the
coordinator's completed runs. Review stopped after that round; the coordinator
checked the final diff and this closing metadata.

For the live-result follow-up, executable code and tests are unchanged from
`d447b3a7`; the full checks above remain the implementation evidence. New work
only archives the authorized live run and updates documentation. Documentation
consistency (50 files), artifact hashes/compressed-content integrity and diff
checks passed. Separate live-result review-and-refactor round 1 against
`d447b3a7` independently reconstructed both action sequences, recomputed usage
and cost, and verified readback/cleanup evidence. No actionable issues or edits;
the review ended after that round. No additional live calls were made in review.
