# S3 H3/J3 strategy pilot — 2026-10-04

Status: executed 2026-10-04; all 48 trials finished; no net gain demonstrated.
This records the R3/R4 bounded strategy evaluation. The protocol below was frozen before execution.

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

Executed once under the user’s instruction to complete S3 and existing paid-test authorization, from backend (do not rerun this directory):

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


## Executed result and routing decision

The unchanged freeze passed validation. [result.json](result.json) contains all 48
trials and 24 paired differences; [rows.jsonl](rows.jsonl), [audit.jsonl](audit.jsonl)
and [spend.jsonl](spend.jsonl) preserve actual requests/responses, effects and accounting.
All trials finished and cleaned up; failed, unknown and not-run counts are zero.
All 42 admitted requests have known usage; no remaining reservations or stop reason.
Total frozen-price estimate: **$0.007331175**, below the $0.25 reservation ceiling.
This is a contract estimate using frozen historical prices, not a provider invoice.

- **H3 (rules → F):** 18/18 completable tasks completed, 6/6 appropriate exits,
  zero unexpected actions; 18 F calls; total 24.143 s; estimated $0.004570335.
- **J3 (rules → Jev → F):** the same task outcomes, zero unexpected actions;
  18 Jev calls plus 6 F calls; total 29.479 s; estimated $0.002760840.
- Each arm has 12 rule steps and 18 eligible decisions. J3 routes 18/30 decisions
  (60%) to Jev; 12/18 select directly, 6/18 abstain and fall back to F. All six
  fallbacks are the two explicit-exit tasks, three repeats each. The four semantic
  action tasks select correctly in all 12 Jev trials. Rules make no model calls.
- J3 avoids **12/18 F calls (66.7%)**, but makes 24 total model calls versus H3's 18.
  Estimated cost falls **39.6%**, while total task time rises **22.1%** (5.336 s).
  Median of the 24 paired J3-minus-H3 time differences is +18.136 ms; this differs
  from total time because the six serial-fallback trials contribute most of the delay.
- Across the four semantic action tasks (12 trials/arm), H3/J3 total 15.393/15.709 s,
  estimated $0.003296040/$0.001064154. Across the two exit tasks (6 trials/arm),
  H3/J3 total 5.830/10.880 s, estimated $0.001274295/$0.001696686. These are descriptive
  slices of the frozen batch, not newly selected success criteria.

The predeclared conclusion is **no_net_gain_demonstrated_keep_disabled**: quality
passed, but cost improvement came with a time regression. This is not evidence of
weaker Jev judgment or pure inference speed; times include remote suppliers, transport,
local browser work and cleanup. No run was repeated or relabeled to improve this result.

For this bounded strategy, keep deterministic steps on rules; use direct F as the
comparison path for semantic decisions and return/seek information when evidence is
insufficient. Keep Jev opt-in for experiments; do not promote any task family by default
from three authored repetitions. Explicit-exit tasks show the cost of consulting F even
after valid Jev abstention. Removing that consultation is a different routing policy,
not a change to make retroactively to this experiment. Full planning, evidence gathering,
visual recovery and native workflows remain S4–S6. This completes S3's revised R1–R4
scope with a negative net-benefit result, not full production adoption.

Implementation/preparation independent review round 1 passed without fixes. Result
and final documentation review is recorded in the active plan. No code changed after
final full backend/E2E verification; final result changes require docs/diff checks only.
