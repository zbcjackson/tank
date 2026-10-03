# S3 held-out selector results — 2026-10-03

Status: user-approved batch executed once; all 48 responses valid. Result review complete.
The directory keeps its preparation-era name to preserve the approved path.

The user authorized the exact 48-request / $0.25-reservation batch with “开始”.
Executable digest: `2db565e335907efdedbd276d4b82b6e7060534c7b155782fc394516f007ca192`.
Execution baseline: `4ac25eaf`; raw evidence commit: `3650f376`.
Inputs, labels, prompts, source and frozen prices were not changed after approval.
No retries, extra warmups, threshold fitting, desktop action or additional batches.

## Outcome

**Both legacy and contract achieved 24/24 correct under the predeclared labels.**
Each arm has six correct intended actions with sufficient evidence, six correct
intended actions despite page-instruction injection, six correct missing-identity
refusals and six correct conflicting-evidence refusals. Both have zero wrong targets,
negative actions or positive refusals. All predeclared paired count deltas are zero.
There are no invalid, cancelled, unknown-usage or not-run rows; cleanup reported no errors.

The only decision-category difference is on all six conflicting-evidence cases:
legacy returns `need_more_context`, contract returns `ambiguous`. Both were accepted
by the frozen labels; this is not a post-hoc reclassification or an accuracy gain.
Both return `need_more_context` on all six missing-identity cases.

This run establishes no measured correctness advantage for the added contract.
Both arms receive the same goal text explicitly requiring unique, consistent identity
and refusal on missing/conflicting identity, which may already be sufficient here.
The six new domains share one two-row template, and labels/facts were authored; each
cell has only one response. Perfect performance on this limited set is a ceiling
result, not proof of broad application generalization, prompt-injection immunity,
business authenticity or successful native execution. These observed cases must not
be tuned on while continuing to call them unseen holdout cases.

## Timing and token overhead

One initial legacy/h01 call opened a connection; all other 47 calls reused it.
Across observed reused calls, legacy median was 471.1 ms (N=23), contract 526.4 ms
(N=24). For a matched comparison, exclude h01 from both arms: the same 23 cases have
legacy/contract medians **471.1/508.9 ms**, and the median per-case contract-minus-legacy
difference is **+23.9 ms**. A median of differences is not the difference of medians.

The new contract was modestly slower in this run and used exactly **279 extra input
tokens per request** (6,696 across 24 calls). Output tokens were unchanged in aggregate.
The measured timings mix network, provider load/queueing, inference and governed
client work; one run does not isolate pure inference or establish a stable latency
penalty. This is a Jev prompt comparison, not a new Jev-versus-Qwen comparison.

- Legacy: 24 calls, 28,272 input + 1,668 output tokens; frozen estimate $0.001187424.
- Contract: 24 calls, 34,968 input + 1,668 output tokens; frozen estimate $0.001468656.
- Total: **66,576 tokens; $0.002656080**, within the unchanged $0.25 reservation cap.
  These are historical frozen contract-price estimates, not a provider invoice.
- 48 known calls, 144 prepared/dispatch/finished audit records; reservations zero,
  no stop reason and no reported cleanup errors.

## Evidence and verification

[freeze.json](freeze.json) retains all paired requests, labels, order, model/budget and
source/version pins. [rows.jsonl](rows.jsonl) preserves actual requests, responses,
scores and timings; [result.json](result.json) includes all summaries, contrasts and
spend. [audit.jsonl](audit.jsonl) and [spend.jsonl](spend.jsonl) preserve boundary records.
See the [measurement protocol](../../fixtures/s3-holdout/README.md).

Post-run checks recomputed the preparation and executable freezes; all 48 payloads,
parsed choices, bound action scores and execution order; summaries/contrasts; all
144 audits; token/cost conservation and zero reservations. A private configured-key
scan found no credential value in the archived artifacts. Matched timing calculations
used only cases where both arms actually reused the connection.

No source/test/protocol/configuration changed. Preparation's backend 5563 passed /
1 skipped, E2E 17 scenarios / 67 steps and static/dev-log checks remain applicable.
This turn checks the live artifacts plus docs/diff consistency and bounded independent
result review; it does not rerun the paid batch. Earlier preparation and v1/v2/v3 raw
artifacts remain untouched.

## Next work

Do not infer that the new wording improves model accuracy, or enlarge this simple
synthetic set merely to obtain a positive prompt result. Keep its responsibility
semantics distinct from unproven performance claims. The next acceptance work should
use actual managed-page/AX observations, more than one interaction layout and effect
readback, with explicit missing/conflicting evidence cases. Business facts still need
real provenance. This batch alone does not complete S3 representative acceptance or
approve production adoption, native input/resume or S4–S6.

Independent result review recomputed both freezes, all payloads/choices/scores/order,
summaries/contrasts, audit/ledger conservation and matched timings; report values
agreed. Round 1 corrected the plan's top-level status omission; round 2 self-check
found no remaining issues. That single documentation edit was self-reviewed.
Docs/diff checks passed; no raw evidence or source was changed, no credentials read
and no model calls made in review. The coordinator inspected the final diff/evidence.
