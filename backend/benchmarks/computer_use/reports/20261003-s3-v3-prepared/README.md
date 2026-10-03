# S3 v3 prepared — 2026-10-03

Status: offline preparation verified and independently reviewed; no paid v3 requests.

[freeze.json](freeze.json) contains twelve known diagnostic scenarios, five paired
conditions (original v2 anchor plus a 2x2 instruction/business-evidence block),
independent labels, explicit comparison definitions, models and source hashes.
Candidates/objectives remain unchanged across conditions. The four factorial cells
share the same host proposal-authorization declaration; the legacy anchor omits it.

Proposed cap: **120 requests**, Jev and Qwen 60 each; **$0.25 shared conservative
reservation limit**. All calls use pooled HTTP with actual connection tracing and
no extra warm-up/retry. No native action or threshold fitting occurs.

Primary outcomes are intended-target action coverage, wrong targets and negative
control actions. Minimal-information refusal is not automatically incorrect.
Evidence-acceptable counts are secondary and cannot be compared as one accuracy
ranking across differently informed conditions. Facts are synthetic declarations;
they do not imply Tank currently verifies those facts in production.

See [the complete protocol and execution command](../../fixtures/s3-v3/README.md).
New live execution requires separate approval of this exact digest:
`66e3ac7c14f1d42b0fffb95bb17eef379d5e684bab34e9b82c0d9c791fb73ef1`.
V1/v2 evidence and source hashes remain unchanged. No spend journal or live result
exists for v3. Results would be a targeted diagnostic, not new blind validation.


Preparation validation: backend 5543 passed / 1 skipped; E2E 17 scenarios / 67 steps;
applicable lint, type, dev-log and docs checks passed. Independent review round 1
found no actionable issues, made no edits, and independently checked factor isolation,
scoring limits, model order, all three freezes and documentation. Unchanged-code full
validation logs were reused. Implementation commit: `0aba7ee1`. No keys were read or
paid calls made by the reviewer. This remains a synthetic targeted diagnostic.
