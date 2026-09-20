# M3 strict-flag preflight — 2026-09-20

Completed six requests through the production `GroundingAdapter.request()` →
`LLM.complete_response()` → OpenAI SDK path. This exhausts the M0/M3 preflight
ceiling: previous 10 + current 6 = 16. No default model or production code changed.

## Experiment

Qwen3.8 Flash, Qwen3.8 Max and DeepSeek Flash each received a control and a
`strict=true` request. Within each pair, the only serialized request difference
is `tools[0].function.strict` (absent versus true). DeepSeek uses the same `/beta`
endpoint for BOTH calls, avoiding an endpoint confound. This is not a comparison
with its earlier non-beta result.

All calls use development seed 101, the same 1440×900 synthetic AC-button image,
normalized integer point schema, `detail=auto`, temperature 0.1, thinking disabled,
8000 maximum output tokens, no retries and 90-second deadline. Responses are
location reports, never executed clicks. There is one independent layout and no
repetition within a setting; this cannot establish general accuracy or a causal
strict-mode quality improvement. Order is control then strict, not randomized.
Raw elapsed times include HTTP capture and local work, not a latency benchmark.

[Manifest](manifest.json) freezes source hashes, models, endpoints, image, request
caps, token reservation and prices. [Frozen-request check](offline-check.json)
used actual SDK fake HTTP before the paid calls and proves pair equivalence.
Every live request matched its frozen JSON and image hash before network dispatch.
The [exact driver](runner.txt) refuses a second live run in this directory. To
repeat, use a new directory and recheck the authorized stage budget and prices.
Credentials were read from the existing configuration/environment; none are saved.

## Results

[Results](results.json), [summary](summary.json) and [offline replay](offline-replay.json)
retain all attempts, raw arguments, model/provider, usage and failures. Each request
has its sanitized HTTP body, gzip-compressed original response and SDK-parsed response.
All six returned HTTP 200 and known usage; none timed out or truncated.

- Qwen3.8 Flash: control and strict both returned arrays in scalar integer fields.
  Both were rejected, so 0/2 hits. An accepted strict flag did not guarantee schema
  compliance on this route. This does not establish whether the provider ignored
  the flag or failed to enforce it internally.
- Qwen3.8 Max: both returned `(649,312)`, both hit, center error 1.278 px. Previous
  preflight array failures remain valid; this pair does not demonstrate stability.
- DeepSeek Flash: control returned `(700,314)`, missed by 73.002 px; strict returned
  `(649,318)`, hit with 4.223 px error. Both were legal integers. One stochastic
  pair is insufficient to attribute the improvement to strict or select a model.

Overall, four schema-valid outputs and three hits among six attempts. Every response
replays through the shared parser with unchanged outcomes. No arrays were repaired,
no coordinate units guessed, no absent-target or native bbox capability inferred.
Qwen Max returned `qwen3.8-max-0902`; the others returned their request model aliases.
No provider field was returned by these direct endpoints; immutable weight identity
remains unverified for aliases.

## Budget and evidence limits

This batch used 9668 tokens; cumulative preflight usage is 26398. The initial
uncached/peak-price estimate was $0.145788, using 10000 estimated input plus 8000
maximum output tokens per request. Actual-usage list-price estimate is $0.007535496.
No provider supplied billed cost; actual charged amounts remain unknown.
The prior preflight README estimate was corrected from $0.335 to $0.364 to match
its unchanged manifest ($0.364054); no prior responses or scores changed.
The input reservation is conservative estimation, not an exact tokenizer bound.
The driver stops before an under-reserved call, on excessive observed input usage,
on missing usage, request failure or exhaustion of the shared 300000-token cap.
Parser failures with known usage remain in the denominator and do not trigger retries.

Official sources checked before execution:

- [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/) documents
  strict mode on `/beta`, required properties, `additionalProperties=false` and
  integer minimum/maximum support.
- [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) gives Flash
  peak uncached input/output $0.30/$1.20 per million tokens; Sunday off-peak billing
  may be lower. We used peak rates for a conservative estimate.
- [Qwen3.8 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash)
  lists Beijing input/output $0.113/$0.382 per million tokens.
- [Qwen3.8 Max](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max)
  lists Beijing snapshot input/output $1.65/$4.951 per million tokens.
  General structured-output capability is not proof of strict tool enforcement.

This batch sent only generated PNG bytes, performed zero desktop actions and
made zero holdout requests. GPT and the current Qwen3.7 baseline were not repeated;
their existing results and provider settings remain preserved in the prior report.

## Decision and next batch

Keep the production baseline. Do not use Qwen strict as a substitute for local
validation. Retain DeepSeek strict as an experimental candidate, without declaring
it better. Do not freeze a holdout candidate from these single-layout results.

The next work is the M3 development screening phase, under the separately planned
144-request / 1000000-token ceiling. Before any calls, freeze the exact shared-adapter
requests, price estimate, selected layouts and one-factor pairs. Compare schema,
image/detail and thinking settings separately; native point/box behavior and the
new explicit status schema still need their own evidence. Keep the 64-layout M0
holdout untouched until configurations are selected and frozen. Preflight requests
must not be silently reset or extended.

## Tests

Before paid calls: shared grounding suite 83 passed; six fake SDK requests and
three exact strict-only pairs passed. Afterwards: six archived response/request
replays passed. Full repository verification is in [verification.json](verification.json).
No Python source or tests changed; changed-file pyright is N/A. The driver is an
execution record, not a new production tool or public CLI.
