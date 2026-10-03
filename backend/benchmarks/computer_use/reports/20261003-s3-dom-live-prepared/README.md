# S3 real Jev / DOM executable proposal — 2026-10-03

Status: offline executable preparation; final validation and independent review passed; awaiting batch authorization.
Real model requests for this batch: **0**. No credentials loaded by preparation.
Baseline: `c001dc06`.

[freeze.json](freeze.json) pins the 15 archived HTML/goal pairs, source hashes,
model/endpoint/price contract, Playwright/HTTP package versions, case order and limits.
Digest: `3bae23fd67cc102c6df9df7e0e0350d701344d33c29107b1d61037fa8b748174`.
Proposed budget: **at most 15 Jev requests; $0.05 shared reservation cap**.
One request, at most one host-dispatched action and three observations per case.
Prices/ceilings reuse historical frozen Jev contracts, not a current invoice guarantee.

## Execution and scoring

The three layouts are toolbar, table and open HTML dialog. Each has sufficient,
missing, conflicting, stale and no-effect conditions, in that scenario order with
all three layouts per condition. These are the exact authored HTML/goal pairs from
[the fixed-model acceptance](../20261003-s3-dom-multilayout/README.md); they are not new
blind cases or independent real-world applications. The previous artifact is unchanged.

Each case owns an isolated local Chromium page. Real observation → ActionBuilder →
JevSelector → governed TaskJSONModel/TaskModelTransport → bound dispatch → fresh
readback runs through the plugin factory and task context. This is direct plugin-loop
acceptance; Runner/YAML and global desktop-lock wiring were tested separately. No user
profile, login, external business system, OS-native input or persistent account state.

HTML, goal and code are frozen; DOM IDs, observation IDs and localhost port are created
at runtime. Therefore this is a frozen execution recipe, not a prerecorded exact model
payload. Actual requests, responses, audits, page events, direct status read and last
snapshot are retained. Expected slots/scenario labels are evaluator data, not fields
in the model's request. Page reports do not prove backend business authenticity.

- Sufficient: model selects the correct target; one sent receipt and page click;
  fresh observation and `selected:K7` readback; controller completes.
- Missing/conflicting: an accepted refusal (`need_more_context` or `ambiguous`),
  stopped selector result, no receipts/clicks and idle page. A safe but differently
  classified refusal is still a failed acceptance case, not silently relabeled.
- Stale: after response capture, the fixture replaces the actual button nodes.
  The model must have selected the correct target, and the host must reject its
  stale reference without a click. The fixture mutation is intentional fault injection,
  not a model action or another host-dispatched action.
- No effect: correct target selected, exactly one sent receipt/click, fresh readback
  still idle and controller `unknown/effect_unknown` with pending effect. This expected
  unknown outcome is a pass for the declared host behavior, not successful completion.

OneCallPolicy from the existing smoke harness enforces one request per case; all
cases share a durable SpendLedger. Audit writes are durable before governed sends.
No request retry, redirect or hidden warmup is added. Each case has an independent
model client; elapsed time includes browser startup/loop/cleanup and must not be used
as pure inference time or compared with the prior pooled replay medians.

The batch stops on the first failed acceptance case, unknown usage, audit/budget or
cleanup failure. All 15 rows remain, with later ones marked not-run. Cancellation also
preserves the current row and remaining denominator before propagating. Cleanup closes
the task runtime and owned browser; uncertainty stops the batch. Existing spend/audit/
rows/result files refuse replay before resources are created. Process kill, disk failure
or repeated cancellation may prevent a complete final report; inspect durable records,
never automatically rerun. Model errors remain acceptance failures, not host successes.

## Commands and approval

From backend, offline preparation into a new directory:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_dom_live --output <new-directory>
```

Only after approval of this exact digest:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_dom_live --live \
  --approved-sha256 3bae23fd67cc102c6df9df7e0e0350d701344d33c29107b1d61037fa8b748174 \
  --output benchmarks/computer_use/reports/20261003-s3-dom-live-prepared
```

The CLI verifies the frozen recipe before reading `core/.env` / `TYPESAFE_API_KEY`.
No native AX, arbitrary-website, model-comparison or production-adoption conclusion
follows from passing these controlled pages. This proposal does not itself authorize
paid execution.

Validation: 10 focused offline integration checks passed; backend **5588 passed /
1 skipped / 21 warnings** with Chromium required; E2E **17 scenarios / 67 steps**.
Web lint/tsc, backend/CLI lint, changed-file pyright, dev-log and docs/diff checks
passed. The executable digest and all 15 archived HTML/goal pairs were independently
recomputed by the coordinator; the prepared directory contains no execution records.
These tests use fake model HTTP and do not establish actual Jev effectiveness.

Implementation commit: `84b61161`. Independent review round 1 found no actionable
issues and made no edits. It checked the controlled lifecycle, acceptance criteria,
full planned-row retention, source freeze and all 15 HTML/goal matches. Docs/diff
checks passed; unchanged final regression logs were reused. The coordinator inspected
the final diff and evidence. No remaining findings, credential reads or live API calls.
