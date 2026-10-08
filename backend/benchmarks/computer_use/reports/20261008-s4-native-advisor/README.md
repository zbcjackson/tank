# Native text Advisor pilot

Date: 2026-10-08. Status: real applications with fake HTTP passed; paid execution
blocked before process creation by automatic approval review. S4 remains open.

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
process creation: there is no `live/started.json`, live desktop action or paid
model request from this batch. The prepared recipe remains available for explicit
approval. No indirect execution or substitute endpoint was attempted.

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

The previous real Jev arithmetic failure remains unresolved until live Advisor
execution is authorized and independent final readback passes.
