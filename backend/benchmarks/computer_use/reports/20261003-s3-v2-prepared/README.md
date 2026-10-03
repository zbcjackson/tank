# S3 v2 diagnostics — 2026-10-03

Status: user-approved batch executed once and independently reviewed. All 64 model responses were valid; usage
is known, reservations are settled and all experiment-owned pools closed without
reported errors. No production setting or v1 artifact was changed. The directory
keeps its preparation-era name to preserve the approved path.

Approved digest: `3fe09b3129f942f7d4682dc1fe26aa58f49872d53e29b8341dbc92e5e63c488b`.
The user authorized this exact 64-request / $0.25-reservation proposal with “开始”.

## Connection timing

Each model made 16 cold and 16 pooled calls. Every cold call opened a connection.
Each pooled arm opened one initial connection and reused it for the other 15 calls;
there were no hidden warm-up requests. The first pooled case was editor-save for
both providers and is excluded from the observed-reuse medians below.

- Jev cold: median governed total 923.4 ms, TCP 6.3 ms, TLS 439.0 ms,
  response-header wait 435.6 ms (N=16 for each).
- Qwen cold: median governed total 495.9 ms, TCP 36.3 ms, TLS 38.1 ms,
  response-header wait 383.5 ms (N=16 for each).
- Jev pooled: total median 445.4 ms over all 16 calls, including its initial new
  connection; **427.1 ms over the 15 observed reused connections**.
- Qwen pooled: total median 418.3 ms over all 16 calls; **416.5 ms over the 15
  observed reused connections**.
- Matching the same 15 cases per provider: Jev cold median 920.3 ms vs reused
  427.1 ms, median per-case saving 453.6 ms. Qwen cold median 497.2 ms vs reused
  416.5 ms, median per-case saving 70.3 ms. A median of paired differences is not
  the difference of the two medians.

The main measured cold-call disparity is in the TLS phase. The providers' observed
reused-call medians differ by only 10.6 ms in this run. This supports connection
setup as a major contributor to the cold-latency gap; it does not prove Jev's
server-side inference is faster, nor establish a significant warm-call difference.

TCP time includes DNS work. Header completion is not exact TTFB; header wait still
mixes network RTT, provider queueing and inference. Pool construction is recorded
separately and is outside governed total. Audit/client/validation overhead is inside
governed total, socket closure is outside it. Provider caching, load, geography and
order effects remain possible despite alternating model/mode order. See per-row
trace phases and the [measurement contract](../../fixtures/s3-v2/README.md).

## Selection and refusal

For each model/mode there are 16 model-eligible decisions: 8 positive and 8 requiring
abstention. Both modes reuse the same cases; these are not independent new samples.

- Jev cold: 12/16 correct decisions; selected the correct target on 4/8 positive
  cases and correctly abstained on 8/8 negatives. Zero wrong actions, 4 false
  refusals relative to frozen gold.
- Jev pooled: 13/16 correct; target selection 5/8 positives, correct abstention
  8/8 negatives. Zero wrong actions, 3 false refusals.
- Qwen cold and pooled: each 14/16 correct; correct target on 8/8 positives and
  correct abstention on 6/8 negatives. Each mode has 2 wrong actions and no false
  refusals. The wrong actions select among ambiguous email/address fields.

Thus across modes Jev has 7 false refusals and no wrong actions; Qwen has 4 wrong
actions and no false refusals. This remains a coverage-versus-wrong-action tradeoff,
not a claim that either model is uniformly better.

Jev's refusals occur on whole-document print (cold only), invoice submission,
booking confirmation and subscription pause (both modes). As a supplementary
probability diagnostic, the correct action is the unique highest-probability
**action candidate** in all 16 positive Jev decisions. In the 7 refusals, abstain
outranks that action: for example invoice submission has 0.71 on abstain and 0.29
on the correct action in both modes. The cold/pooled print decision moves from
abstain 0.53 vs correct action 0.47 to abstain 0.46 vs correct action 0.54.

This diagnostic is not an alternative pass criterion and does not authorize ignoring
abstain. It locates the observed disagreement at action-versus-abstention rather
than wrong-target ranking. Overly broad refusal instructions or insufficiently
expressed business prerequisites are plausible contributors, but this batch did
not isolate their causal effects. The primary false-refusal counts remain those
of the frozen gold; the result does not prove that every gold assumption would
be justified in a real application.

All 144 rows remain: 64 returned model decisions, 44 rule decisions and 36 host
blocks. There were zero invalid, cancelled or not-run rows. Host gating and candidate
recall are not folded into model error rates. No native action was executed and
no confidence threshold was fitted or installed.

## Usage and evidence

- Jev: 32 calls, 19,000 input + 1,943 output tokens; frozen estimate $0.000798000.
- Qwen: 32 calls, 8,864 input + 205 output tokens; frozen upper-tier estimate
  $0.001597860.
- Total: **30,012 tokens; $0.002395860** under the conservative frozen prices,
  below the $0.25 reservation cap. This is not a billing statement or a comparison
  of actual invoiced unit prices. Remaining reserved tokens/cost are zero.
- There are 64 unique calls with prepared/dispatch/finished records (192 audits),
  all known usage, no reported cleanup errors, and no stop reason. All actual
  question/state/options match the approved compact question for both modes/models.

Artifacts:

- [freeze.json](freeze.json): immutable approved recipe, labels and source/HTTP hashes.
- [result.json](result.json): scored rows, timing summaries and final ledger.
- [rows.jsonl](rows.jsonl): durable row journal, including trace event names/times.
- [audit.jsonl](audit.jsonl): metadata-only model audit.
- [spend.jsonl](spend.jsonl): reservation/settlement history.
- [V2 protocol](../../fixtures/s3-v2/README.md) and [harness](../../s3_replay_v2.py).

Preparation had 5531 backend tests passed / 1 skipped, 17 E2E scenarios passed,
and a clean independent review. Execution changed no source, fixture or model
configuration. Freeze, exact wire-question parity, row scores, summaries, audit
phases, usage totals and pool outcomes were recomputed locally and matched.
Execution-result review is recorded in the active strategy-ladder plan.

These are revised, already-observed synthetic scenarios, not a fresh blind holdout.
V2 changed both prompts and fixtures, so v1-to-v2 quality/latency differences cannot
be assigned to a single cause. A next investigation should make host-verified
preconditions explicit and isolate the refusal policy, preserving action/abstention
as separate decisions. Do not bypass abstention or change production defaults from
this small diagnostic alone. This batch cannot be rerun against its existing journal.


Independent result review completed in round 1 without findings or file edits.
The reviewer recomputed request parity, scores, medians and paired differences,
usage/cost, audit counts and freeze validity; all matched. Docs/diff checks passed.
No credentials were read and no model requests were repeated during review.
Raw evidence commit: `c760b78c`. Source was unchanged, so preparation code-validation
results were reused rather than rerunning unrelated application tests.
