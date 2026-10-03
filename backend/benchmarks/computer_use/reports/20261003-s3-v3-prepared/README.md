# S3 v3 refusal diagnostics — 2026-10-03

Status: user-approved batch executed once; all 120 responses valid. Result review complete.
The preparation-era directory name preserves the approved path. Production settings,
source code and v1/v2 evidence remain unchanged; no native action executed.

Approved digest: `66e3ac7c14f1d42b0fffb95bb17eef379d5e684bab34e9b82c0d9c791fb73ef1`.
The user authorized execution with “开始执行，预算上限可以提升”. The original 120-request,
$0.25 shared reservation cap was sufficient and was not raised. No extra warmups,
retries, threshold fitting or additional batches were performed.

## Action and refusal outcomes

Each condition/model has eight intended-action cases and four negative controls.
In condition order legacy, broad_minimal, scoped_minimal, broad_enriched,
scoped_enriched:

- Jev intended-target actions: **4/8, 3/8, 5/8, 7/8, 8/8**. Positive abstentions:
  4, 5, 3, 1, 0. Wrong targets and negative-control actions: zero in every condition.
- Qwen intended-target actions: **8/8 in every condition**, with no wrong positive
  target. Negative-control actions: **2/4, 1/4, 0/4, 0/4, 0/4** respectively.
- All 120 responses parsed correctly. There were no invalid, unknown-usage,
  cancelled or not-run rows, and no reported cleanup errors.

The matched, predeclared positive-action count contrasts for Jev are: host contract
−1; scoped instruction under minimal/enriched facts +2/+1; business facts under
broad/scoped instructions +4/+3; interaction −1. Negative actions and wrong targets
have zero deltas. Thus supplying business facts produced a larger observed coverage
increase than instruction scoping in this selected set. The authorization declaration
alone did not improve Jev coverage. This is a descriptive paired result, not a
significance test or a claim about all possible prompts.

Qwen positive-action contrasts are all zero. Its negative-action contrasts are:
host contract −1; scoped instruction under minimal/enriched facts −1/0; facts under
broad/scoped instructions −1/0; interaction +1. The positive interaction here reflects
overlapping removal of the same negative error, not a new error in scoped_enriched.

Jev invoice and booking cases still abstain with scoped instructions and minimal
facts, then select the intended target once facts are added under either instruction.
Printing and file discard also improve. Subscription pause is the one enriched
case still refused with broad instructions (abstain probability 0.53); scoped_enriched
selects the intended action (abstain probability 0.17). Qwen's legacy negative errors
are contact-email and delivery-address; broad_minimal retains only delivery-address.
All other conditions correctly abstain on those cases.

Minimal-information refusals are not automatically wrong: the frozen secondary
`evidence_acceptable` definition permits them. Its criterion changes with information
level, so it is not a cross-condition accuracy ranking. Both models achieve eight
intended actions and four negative abstentions under scoped_enriched, but only on
these twelve selected synthetic scenarios, with one response per cell. No new blind
holdout or production business validation is established. Added control semantics
intentionally make matching easier; they do not demonstrate new model intelligence.

## Timing and accounting

Each provider opened one initial connection and reused it for 59 calls. The first
legacy/editor-save call for each provider is excluded from reused medians. Across
all conditions the reused-call governed total median was **430.5 ms Jev vs 456.6 ms
Qwen** (N=59 each). By condition, reused medians were:

- Jev: 420.0, 439.1, 550.6, 396.5, 463.2 ms (N=11,12,12,12,12).
- Qwen: 461.2, 454.2, 451.8, 460.8, 485.4 ms (same N).

Jev was modestly faster in this aggregate; condition-level rankings vary. These are
end-to-end calls, mixing network, queueing, inference and governed-client work.
One run cannot prove a stable provider speed ranking or isolate pure inference.
Connection/load/order/cache effects remain; there were no hidden warmups.

- Jev: 60 calls, 41,463 input + 3,633 output tokens; frozen estimate $0.001741446.
- Qwen: 60 calls, 21,399 input + 412 output tokens; frozen conservative estimate
  $0.003802755.
- Total: **66,907 tokens; $0.005544201**, below the unchanged $0.25 reservation cap.
  This is a frozen contract-price estimate, not the provider invoice or actual
  billing-price comparison. All reservations settled to zero.
- 120 known calls and 360 prepared/dispatch/finished audit records were retained.

## Evidence, verification and next step

[freeze.json](freeze.json) preserves inputs, gold, versions, prices and source hashes.
[rows.jsonl](rows.jsonl) preserves actual request/response pairs and timing;
[result.json](result.json) contains scores, summaries, predeclared contrasts and spend;
[audit.jsonl](audit.jsonl) and [spend.jsonl](spend.jsonl) retain the boundary records.
See the [frozen measurement protocol](../../fixtures/s3-v3/README.md).
Raw evidence commit: `7d1ebfa7`; execution baseline: `5fbcfc94`.

Post-run verification recomputed v1/v2/v3 freezes, all 120 paired payloads/responses,
row scores, summaries/contrasts, schedule, 360 audit records, usage/cost conservation
and zero reservations. A private credential-value scan found no configured keys in
the archived artifacts. Source/tests/protocol/configuration did not change; preparation
validation (backend 5543 passed / 1 skipped, E2E 17 scenarios / 67 steps and applicable
lint/type/dev-log checks) remains applicable without rerunning paid requests.
Docs/diff checks and bounded independent result review complete the handoff gate.

The next implementation should formalize the selector's responsibility and the
provenance of supplied business facts, preserving abstention when required identity
or evidence is missing. Then validate a new held-out set before changing production
adoption or thresholds. Never treat synthetic authorization/business declarations as
facts verified by Tank. More spending on repeats of these twelve known cases alone
would not resolve the representativeness gap.

Independent review round 1 recomputed all freezes, requests/responses, scores,
contrasts, schedule, audits, ledger and timings; the report numbers matched.
The reviewer corrected two plan descriptions (top-level v3 status and the scope of
identical host declarations). Round 2 self-check found no remaining issues; those
two edits were self-reviewed, not independently re-reviewed. Docs/diff checks pass.
No model calls, key reads, source edits or raw-evidence edits occurred in review.
The coordinator inspected the final diff and verification evidence.
