# S3 v2 prepared — 2026-10-03

Status: offline preparation verified and independently reviewed; no paid v2 requests. Source/gold/results for v1 are
unchanged and its approved digest still validates.

[freeze.json](freeze.json) freezes 24 revised known scenarios, compact semantic
candidates and binary abstention, cold/pooled modes, provider endpoints/models,
HTTP package versions and source hashes. Historical split names are not a new blind
holdout. No threshold fitting or production change is included.

The proposed batch has at most 64 requests (32 each to Jev/Qwen), no hidden warm-up,
and a shared $0.25 conservative reservation limit. First/new connections in the
pooled arm are reported separately from observed reused connections. Timing covers
TCP (including DNS), TLS, send, response headers and body; neither exact first byte
nor pure server inference time is claimed. Reused connection timing cannot by itself
remove effects of provider caching, load, geography or network RTT.

See [protocol, scoring, ownership and commands](../../fixtures/s3-v2/README.md).
The live command requires separate approval of this digest:
`3fe09b3129f942f7d4682dc1fe26aa58f49872d53e29b8341dbc92e5e63c488b`.
There is no spend journal or real result file yet.


Preparation acceptance: backend 5531 passed / 1 skipped, E2E 17 scenarios / 67 steps,
all applicable lint/type/docs checks passed. Independent review round 1 found no
actionable issues and made no changes. The reviewer independently checked both
freezes and documentation, and reused unchanged-code full-suite evidence after
reading the logs. Implementation commit: `52dcb62c`. No paid calls were made during
implementation or review, and no new result or spend journal exists yet.
