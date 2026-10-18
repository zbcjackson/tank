# Jev image capability development preparation

This is a new synthetic development recipe, separate from every S3–S5 freeze,
holdout and remaining historical allowance. It has no live model/GUI executor.
The separate `jev_image_eval` entry below adds opt-in model execution, without GUI access.

From `backend/`, prepare a fresh directory:

```sh
uv run --no-sync python -m benchmarks.computer_use.jev_image_dev /tmp/tank-image-dev-new
```

The recipe writes 36 task specifications (nine families × two instruction
languages × two layout clusters), their stage PNGs, `public.json`, independent
`labels.json` and a source/file/version freeze. Families include full structure,
missing structure, text→image→text, recovery after a known not-sent action,
settings/name/save workflow, absent/multiple targets, missing user data and stale
frames. Workflow/recovery stages are controlled component fixtures, not completed
GUI workflows or evidence of planning quality. Instructions are English/Chinese;
the synthetic app controls use English labels. There are only two layout clusters:
36 rows are not 36 independent application/layout samples.

`requests(stage, png)` builds previews with the production image-request builder:
Jev 1.13 text, 1.14 text, same-version image Choice and cardinality+Box. They share
public state, candidate options and target intent. An absent AX tree cannot gain
executable candidates through an image Choice. Missing user input and stale-frame
stages have zero request previews. Family names, scoring labels and expected
regions are never passed to the model; changing labels cannot change requests.
Multipart previews contain references, file byte sizes/hashes and the experimental
header. The PNG files supply the exact bytes; previews do not invoke an SDK.

`load_freeze(output, digest)` checks every file, source pin and SDK/Pillow version.
Existing output directories are refused. Reprepare into a new directory after
source changes; never repair an earlier freeze or relabel historical results.

All samples are development-only. Confidence gates, cost/request allowances and
confirmatory samples are **not frozen**. Independent application/template/layout
families must be reserved before confirmation. V/JT/JM/JF are future routing
comparisons; this recipe does not execute those policies or estimate quality,
speed, recovery rates or adoption. Same compliant PNGs can later be used for
Qwen/Jev localization comparisons; optimized product settings are a separate test.

The SDK is pinned to 0.7.5, with an explicit 1.14.0 image/Box protocol. Services
disable compression for deterministic preparation; a fake-HTTP regression checks
official SDK default compression and actual multipart bytes separately. The
SDK default is environment-dependent (zstd when its optional compressor exists).
The host admits compact parameter JSON plus exact image file bytes, not HTTP
framing/compression or provider re-encoding. There are no paid API calls here.

## Read-only executable comparison

From backend, prepare a **new** executable directory; this creates its own fresh
development data and never modifies an earlier freeze:

```sh
uv run --no-sync python -m benchmarks.computer_use.jev_image_eval --output /tmp/tank-image-eval-new
```

Preparation reads no credentials and constructs no clients. Inspect `freeze.json`,
`previews.json` and `data/`: 300 planned rows, 40 excluded for missing user input or
stale frames, at most 260 requests. The five arms are Jev 1.13 text, 1.14 text,
1.14 image Choice, 1.14 cardinality+Box, and Qwen image localization using the
same PNG/state/target. Arms rotate per stage; tasks and clients are fresh per row,
with no warmups or retries. Stages are independent fixed observations, not a
closed-loop GUI workflow. The missing-structure Choice arm can only abstain;
its score measures candidate selection, whereas Box measures localization.

The fixed Qwen model is `qwen3.7-flash-2026-07-15` at the Beijing compatible
endpoint. Price/context evidence is recorded in the freeze, checked on 2026-10-18:
[Jev](https://docs.typesafe.ai/models),
[Qwen](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash).
Qwen uses the highest uncached input price tier for conservative reservations;
Jev reserves the full default context and charges inputs only. The batch ceiling
is **USD 10**, 100 million tokens, one request per row and 60 seconds per row.
This is a reservation ceiling, **not an expected bill** or an approval to spend.
The ledger retains unknown-usage reservations and stops on operational errors,
unknown usage, audit/capture failure, cancellation or unconfirmed cleanup.
Known-usage malformed answers remain failures in the denominator.

After separately reviewing the exact digest, data recipients and budget, execution
requires explicit environment credentials (`TYPESAFE_API_KEY`, `BAILIAN_API_KEY`):

```sh
uv run --no-sync python -m benchmarks.computer_use.jev_image_eval --output /tmp/tank-image-eval-new --run --approved-sha256 <reviewed-digest>
```

The executable rechecks dataset/source/version/preview hashes before running and
before each row, and checks actual model-call parameters against frozen previews.
Existing run artifacts are refused: interrupted runs are never silently resumed.
`calls.jsonl`, `audit.jsonl`, `spend.jsonl` and `result.json` retain attempted calls,
answers, usage, wall/model-call latency, cleanup and all planned/unrun/excluded rows.
Only synthetic content is recorded, never credentials. Labels are loaded separately
for scoring and never enter a model request. Choice correctness, cardinality,
center-point hit inside independent clickable interiors and false uniqueness are
distinct metrics; no score is a dispatched action or an independently verified
GUI effect. Raw confidence is retained without automatic thresholds. These are
development observations, not independent confirmation or production-adoption evidence.
