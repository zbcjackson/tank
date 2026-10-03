# S3 v3 — refusal factors, prepared 2026-10-03

This is a targeted diagnostic on twelve already-observed v2 scenarios: eight
intended-action cases and four negative controls. Cases were selected after seeing
v2 outcomes. It is not a new blind holdout, population estimate or production
validation. No thresholds are fitted and no native actions execute.

## Frozen factors

Five conditions use exactly the same objective, declared inputs and candidates:

- legacy: original v2 question, unmodified.
- broad_minimal: legacy plus a common synthetic host proposal-authorization contract.
- scoped_minimal: the same state as broad_minimal, with responsibility-scoped instructions.
- broad_enriched: broad_minimal plus independent synthetic business facts.
- scoped_enriched: scoped_minimal plus the same business facts.

The four non-legacy cells have the identical host contract. Approval permits making
a proposal; it neither supplies business identity nor identifies a correct candidate.
The scoped instruction preserves abstention for missing required identity/visual
evidence and indistinguishable targets; it does not tell models to always act.

The legacy anchor isolates this particular authorization-contract addition.
The 2x2 block tests instruction and business-evidence effects and their interaction.
Model/endpoint/temperature/output cap/candidates remain fixed. Model request wrappers
differ by API, but the actual semantic question is identical within a paired cell.

`conditions.json` contains authored business-state facts, not gold-derived verdicts.
Examples include a selected itinerary/fare, the current subscription and pause
semantics, invoice recipient and submission behavior. Negative controls retain
unknown field/workspace identity or unavailable images. Structured oracle markers
(gold, should_act, target_ref, candidate_id) are rejected recursively; this is not
a claim that a blacklist can detect every semantic answer leak. Facts require manual
review. Explicit control semantics naturally make matching easier; measuring that
information effect is intentional, not evidence of new model intelligence.

All host/business declarations are synthetic. They do not mean Tank can currently
verify those facts in a real application. Production must obtain authoritative
observations/API evidence before making such declarations; no authorization or
business validation is bypassed by this benchmark.

## Predeclared measures and comparisons

Primary counts per cell/model: intended target selected (out of eight), abstention
on intended-action cases, wrong target, and negative-control action (out of four).
Do not claim success merely because positive action coverage increases: inspect
negative actions and wrong targets alongside it.

On positive cases with minimal evidence (including legacy), either the intended
action or abstention is evidence-acceptable. Refusal is not automatically an error
when evidence is missing. Enriched positives expect the intended action under the
synthetic full-state assumptions. Negative controls expect abstention in every cell.
`evidence_acceptable` is secondary and its criterion changes with evidence level;
it must not be treated as one comparable accuracy ranking across all conditions.
Invalid replies never count as acceptable abstention.

Predeclared paired count contrasts (after minus before):

- Host contract: broad_minimal − legacy.
- Scoped instruction: scoped_minimal − broad_minimal; scoped_enriched − broad_enriched.
- Business facts: broad_enriched − broad_minimal; scoped_enriched − scoped_minimal.
- Interaction: scoped_enriched − scoped_minimal − broad_enriched + broad_minimal.

Contrasts report deltas for intended actions, negative actions and wrong targets,
not a fitted threshold or a significance test. They are emitted only for complete,
valid matched response grids. Failures/nonexecuted rows remain in summaries/journals.
Twelve selected cases and one request per cell do not establish generalization or
reliable population effect sizes. Differences versus the old v2 run are not used
as causal comparisons; the legacy condition is rerun within this batch.

## Lifecycle, order and proposed budget

All cells use the reviewed v2 governed call and provider-owned pool implementation.
Each task still has independent authority and accounting. Conditions rotate by
case; each condition gives each model six first positions across twelve cases.
There are no hidden warmups, redirects or retries. First/new versus reused sockets
remain recorded. Provider caching/load/order effects can remain; timing is secondary
here and no pure server inference time is claimed.

At most **120 requests**, 60 per model; shared conservative reservation cap **$0.25**.
Models/endpoints/prices reuse the frozen v1/v2 recipe. The cap is not a provider
invoice guarantee. Unknown usage or audit failure stops all remaining cells; cleanup
errors and cancellation preserve evidence. Existing spend journals refuse reruns.
Credentials are loaded only for an explicitly approved live batch. V1/v2 source,
fixtures and raw results remain unchanged.

From backend:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_replay_v3 --output <new-directory>
```

After separate approval of that digest:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_replay_v3 --live \
  --approved-sha256 <approved-v3-digest> --output <prepared-directory>
```

Preparation and pytest do not make paid calls. The new frozen artifact contains
all questions, independent gold, model/HTTP settings, source hashes and contrast definitions.
