# S3 H3/J3 strategy pilot — 2026-10-04

Status: final code/data verification passed; independent review pending; no paid requests.
This is the R3 execution proposal for completing S3's bounded strategy evaluation.

Digest: `a36f7630a20e504ab795751f3afcee32d5b5e912b9e3cfeff75114c6572ad16b`.
[freeze.json](freeze.json) pins eight controlled workflow tasks, independent expected
outcomes, code/library versions, two models, generation settings, order and decision rule.
The [protocol](../../fixtures/s3-strategy/README.md) defines all measures and limitations.

- H3: host rules, then the configured generative candidate selector F.
- J3: the same rules, then Jev; a valid abstention falls back to the same F on identical
  semantic evidence and complete candidates. Hard task/transport stops do not fall back.
- Eight tasks × three repeats × two arms = **48 trials**. Two rule tasks, four clear
  semantic choices and two explicit non-action exits. Each arm has 18 completable
  and six appropriate-exit trials; they are scored separately.
- At most **54 model requests** (18 Jev, up to 36 F), **$0.25 shared reservation**.
  Independent task clients/browsers, no implicit retry or hidden warmup. F requests
  temperature 0, max_tokens 128 and enable_thinking=false. Prices are frozen historical
  conservative estimates, not actual invoice guarantees.

Elapsed time includes factory/setup, browser observation, all model/fallback calls,
UI dispatch/readback and cleanup. Shared localhost server setup and construction of
supplied structured goals are outside the measurement. These authored local pages are
workflow-inspired, not production traces; no user accounts, native AX or real payments.

The conservative predeclared pilot gate requires both arms' 24 expected outcomes,
zero unexpected actions, at least one avoided F call, and >=10% improvement in either
total time or estimated cost without regression in the other. A gain would be only a
limited pilot signal. No gain is a valid S3 conclusion and retains default-disabled.
Semantic errors on fully observed disposable pages are recorded, not retried; operational
failure stops remaining sends and preserves all 48 planned rows. Incomplete evidence
cannot produce an adoption conclusion.

After separate approval of this exact digest, from backend:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_strategy --live \
  --approved-sha256 a36f7630a20e504ab795751f3afcee32d5b5e912b9e3cfeff75114c6572ad16b \
  --output benchmarks/computer_use/reports/20261004-s3-strategy-prepared
```

The CLI validates the freeze before loading `core/.env`, then uses TYPESAFE_API_KEY
and the existing computer_use profile credential for the pinned Qwen F model. Changes
to that profile's model/endpoint are rejected. Existing execution artifacts forbid
rerun. Native reference UUIDs are generated at runtime and actual requests are captured;
this is not a prerecorded exact-byte payload experiment.

R1/R2 evidence so far: real Runner/YAML/SDK/fake HTTP/Chromium verifies both modes,
Jev abstention → F completion → rules, shared accounting, fixed non-thinking parameter,
hard-stop and strict-output handling. The paired harness passes all 48 tasks with fake
HTTP both when Jev selects directly and when every eligible case is forced to fall
back (42/54 request totals). This proves control and measurement, not actual effectiveness.

Final validation: backend **5629 passed / 1 skipped / 21 warnings** with Chromium
required (`/tmp/tank-s3-strategy-final-backend.log`), E2E **17 scenarios / 67 steps**
(`/tmp/tank-s3-strategy-e2e.log`, including 13 managed-Chromium child tests).
Applicable lint/type checks, dev-log and docs/diff checks passed. The final data's
paired/forced-fallback tests were rerun after clarifying visible task context. Code:
`f3e0e03a`; harness/catalog: `4d071c85`. No credentials or actual model calls in preparation.
