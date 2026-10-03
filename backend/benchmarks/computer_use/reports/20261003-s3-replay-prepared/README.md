# S3 frozen selector replay — 2026-10-03

Status: approved batch executed once and independently reviewed; 64 valid model responses, no unknown usage,
no outstanding reservations. The directory retains its preparation-era name to
preserve the approved path and links. Production defaults and thresholds were not changed.

The user approved this exact prepared batch with “开始”. Frozen digest:
`9bfed6bbe775859db0fd80f6d0adc91accdebd187d217b6fc8707f45d7ed327c`.

## Result and interpretation

This is a small synthetic, single-pass selector experiment, not live task completion
or a production adoption recommendation. D2 and action representations reuse the
same underlying cases, so their outcomes are correlated.

On the holdout split, each stage has 8 model-eligible cases:

- D2: Jev and Qwen each matched the strict gold label in 5/8 calls. Jev proposed
  4 actions, all correct; Qwen proposed 5 actions, including 1 incorrect proposal.
  Median call time: Jev 837.4 ms, Qwen 652.1 ms (N=8 each).
- Whole bound action: each model matched 5/8. Jev proposed 4 correct actions;
  Qwen proposed 7 actions, including 3 incorrect proposals. Median call time:
  Jev 877.4 ms, Qwen 657.6 ms (N=8 each).
- Combined over the two representations: each model matched 10/16 strict labels.
  Jev had 0 wrong action proposals out of 8 proposed actions; Qwen had 4/12.
  Median call time was 848.7 ms for Jev and 653.3 ms for Qwen (N=16 each,
  representing only 8 distinct scenarios).

All valid positive targets in the model-eligible subset were selected correctly
by both models: 16/16 across both splits and representations. Differences arose
mainly when the evidence required refusal or more information. In holdout, Qwen
selected an ambiguous address field in both representations, and selected actions
for the unspecified workspace and absent photograph in the action representation.
Jev's holdout mismatches were safe control-label mismatches (for example none vs
ambiguous, or ambiguous vs need_more_context), not wrong action proposals.
No proposed action was dispatched to a desktop or browser in this replay.

Rules-only uses exact matches and escalates the remaining eligible states. Each
split/stage has one exact rule hit and three host-blocked cases (missing input,
duplicate controls and truncation), shared by all arms. The two overflow scenarios
lose their true target at top-32; this is candidate recall failure, not model error.
The rules baseline is a selector policy, not the complete production agent A.

The evidence supports a narrower observation: Jev was more conservative on these
negative cases; Qwen was faster on these calls. It does not establish broader model
superiority, task completion efficiency, or the best production routing policy.

## Calibration boundary

Thresholds were fitted only on calibration rows, by stage/category, with the
predeclared grid and zero-observed-wrong-action rule. The locked file was written
before holdout calls. Jev made one wrong chart action proposal in each calibration
representation; the fitted complex-category threshold 0.9 rejects both.

On holdout, Jev's accepted actions equal its raw actions: 8 correct actions and
zero wrong actions across both representations. Thus the holdout safety difference
already existed in raw choices; this run does **not** demonstrate an incremental
benefit from the fitted thresholds. Sparse categories with no calibration action
use 1.01 (reject all actions). No threshold was installed into production. Qwen
was not given a fabricated confidence score or an equivalent fitted confidence gate;
use the raw-vs-raw comparison above when comparing the models.

## Usage, timing and completeness

- Jev: 32 requests, 28,670 input + 2,208 output tokens. Overall median call time
  871.9 ms (N=32). Frozen cost estimate: $0.001204140.
- Qwen: 32 requests, 15,605 input + 277 output tokens. Overall median 628.7 ms
  (N=32). Frozen upper-tier cost estimate: $0.002757645.
- Total: 46,760 tokens and $0.003961785 at the frozen conservative rates,
  below the $0.25 shared reservation limit. No retry, redirect or extra model call.
- These estimates are not invoices. Qwen was priced at its upper input-context
  tier for reservation safety; these short prompts can bill differently. Do not
  use this ledger estimate alone to rank the models' actual monetary efficiency.
- Each case/arm uses a new task/client; timings include governed call overhead
  (including audit/settlement), not desktop actions or full task wall time. Small N
  and correlated representations do not support p95 or significance claims.

All 144 scheduled rows remain: 64 returned model decisions, 44 rule decisions,
36 host blocks. There were zero invalid or not-run rows. All 64 ledger calls have
known usage, each has prepared/dispatch/finished audit records (192 total), and
remaining reserved tokens/cost are zero. Calibration row hash, thresholds, raw
rows, accepted decisions and summary were independently recomputed locally and matched.

## Evidence and reproducibility

- [freeze.json](freeze.json): immutable approved inputs, separate gold labels,
  model/endpoint/price limits and implementation hashes.
- [result.json](result.json): all raw and accepted decisions, responses, summaries and ledger.
- [rows.jsonl](rows.jsonl): durable raw row journal before threshold application.
- [thresholds.json](thresholds.json): locked thresholds and calibration-row digest.
- [audit.jsonl](audit.jsonl): metadata-only call audit; no authorization headers.
- [spend.jsonl](spend.jsonl): reservation and settlement journal.
- [Fixture protocol](../../fixtures/s3/README.md) and
  [original paid-batch proposal](../../fixtures/s3/experiment.md).
- [Harness](../../s3_replay.py): rejects reused journals; this batch must not be rerun.

Preparation acceptance was 56 focused tests, backend 5518 passed / 1 skipped,
and E2E 17 scenarios / 67 steps. Review corrected the original positive-target
position bias to 5:5 overall (calibration 3:2, holdout 2:3). This execution used
that reviewed freeze unchanged. Code was not modified for the run. Result-document
review is recorded in the active strategy-ladder plan.

Next work: obtain representative task-family evidence and recheck refusal and
calibration on another separately frozen set before adopting a policy. The current
single-milestone click/fill sample does not validate heterogeneous planning,
native desktop execution, recovery, or overall S3–S6 production readiness.


Independent result/document review completed in round 1 with no actionable findings
and no edits to evidence. The reviewer recomputed paired wire inputs, all reported
counts/medians, calibration lock, thresholds, scoring, 192 audit entries and the
final spend journal. Docs/diff checks passed. The run was not repeated and no
credentials were inspected by the reviewer. Raw evidence commit: `8640ba09`.
