# S3 new synthetic holdout — prepared 2026-10-03

Status: offline preparation; verification and independent review passed. No real model calls.

[freeze.json](freeze.json) contains 24 scenarios (six domains, four conditions),
separate gold, 48 exact paired Jev requests, order, model/budget recipe and source
hashes. Current contract requests use the production selector's payload builder.
The legacy arm changes only the contract field and selector instruction. There are
12 positive and 12 negative cases, target positions balanced 6:6; each condition
assigns three first positions to each arm. No model outputs have been observed.

Digest: `1daf61ad4e337dba196fb38ce5077a995db678ca0bfdb763c5a607ab9b160ac7`.
Preparation baseline: `645cdb5d`. See the
[measurement and provenance protocol](../../fixtures/s3-holdout/README.md).

This is a new synthetic domain set, not a new collection of independent layouts:
all six domains share a two-row identity-matching pattern. Authored observation facts
are not authoritative business evidence. Results must remain separate from the known
v1/v2/v3 diagnostic cases and cannot be used for prompt tuning while retaining the
holdout claim. Invalid/failed/not-run responses remain in planned denominators.

The planned 48 requests / $0.25 reservation cap is **not an executable paid batch**.
There is no live entry point, HTTP client, credential loading, spend journal or result
file. A subsequent implementation must connect the governed executor and re-freeze
its final source before requesting execution authorization. Historical paid evidence
is unchanged; this preparation is not a request to spend now.

Verification: seven focused offline checks passed; backend 5552 passed / 1 skipped;
E2E 17 scenarios / 67 steps; applicable web/backend/CLI lint, changed-file type checks,
dev-server log scan and docs/diff checks passed. Legacy instruction was checked against
commit `48167005`. No model or credential access occurred during preparation.

Implementation commit: `293c41a7`. Independent review round 1 found no actionable
issues and made no edits. The reviewer checked AST equivalence of the extracted
production builder, all identity mappings/labels, paired request differences, target
positions and order balance, freeze digest and scoring denominators. Docs/diff checks
passed; unchanged-code full regression logs above were reused. The coordinator
inspected the final diff and verification evidence. No remaining findings.
