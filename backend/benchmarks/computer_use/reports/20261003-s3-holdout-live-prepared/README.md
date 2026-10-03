# S3 executable holdout proposal — 2026-10-03

Status: offline executable preparation; final regression and independent review passed; awaiting batch authorization.
Real requests: **0**. No credentials have been loaded for this batch.

[freeze.json](freeze.json) pins 24 scenarios, independent labels, 48 exact paired
requests, the production request/parser source, governed execution source and reused
HTTP trace helper, HTTP library versions, order and budget. It retains the original
preparation digest `1daf61ad4e337dba196fb38ce5077a995db678ca0bfdb763c5a607ab9b160ac7`.
Neither the previous preparation artifact nor v1/v2/v3 paid evidence was rewritten.

Executable digest:
`2db565e335907efdedbd276d4b82b6e7060534c7b155782fc394516f007ca192`.
Proposed batch: **48 Jev requests** (24 legacy + 24 contract), **$0.25 shared
reservation cap**. One repetition, one provider pool, no extra warmups/retries/redirects.
Four production control outputs are retained. No physical action or threshold fitting.

This is six synthetic domains sharing a single two-row matching pattern, not six
independent layouts. Facts are authored channel reports, not validated business state.
All planned rows remain in denominators; unknown usage/audit failure/budget/cancellation
stop remaining sends. Known-usage malformed replies remain invalid and may continue.
`completed` indicates schedule completion, not accuracy. Cleanup failure remains explicit.
The [protocol](../../fixtures/s3-holdout/README.md) defines provenance, scores and limitations.

After separate approval of the executable digest, from backend:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_holdout_live --live \
  --approved-sha256 2db565e335907efdedbd276d4b82b6e7060534c7b155782fc394516f007ca192 \
  --output benchmarks/computer_use/reports/20261003-s3-holdout-live-prepared
```

The CLI validates the frozen recipe before loading `core/.env` / `TYPESAFE_API_KEY`.
Existing execution artifacts refuse rerun before clients are created. Results retain
raw request/response pairs, scores, connection trace, usage and audit/spend journals.
The frozen price/ceiling values are historical contract estimates, not an invoice
or current price guarantee. No outcome-based prompt or label changes are authorized.

Validation: 11 focused fake-HTTP tests; final backend 5563 passed / 1 skipped;
E2E 17 scenarios / 67 steps. Applicable web/backend/CLI lint, changed-file pyright,
dev-log and docs/diff checks passed. The final full run followed the additional
frozen-label regression. The old preparation digest still validates, and payloads,
labels and schedule match it exactly. No credentials or real API requests were used.

Implementation commit: `5f13f7a3`. Independent review round 1 found no actionable
issues and made no edits. It checked lifecycle/stop paths, all frozen request/label/
order/model/budget equivalence, action/binding reconstruction and both freeze digests.
Docs/diff checks passed; unchanged final regression logs were reused. The coordinator
inspected the final diff and verification evidence. No remaining findings.
