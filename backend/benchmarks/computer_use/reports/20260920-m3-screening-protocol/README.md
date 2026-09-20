# M3 development screening 1: point versus bbox — 2026-09-20

Completed 40 synthetic-image requests through the production
`GroundingAdapter.request()` → `LLM.complete_response()` → SDK path. This is the
first development screening batch, separate from the exhausted 16-call preflight.
No production configuration, adapter, default model or desktop behavior changed.

## Frozen experiment

Five routes, four development layouts (seeds 201–204), two protocols per layout:
normalized scalar integer center point versus normalized scalar integer bounding
box. The host takes the box center using the existing parser. Both protocols
use 0–1000 per axis, `found`, integer zero abstention, `strict` absent and
`detail=auto`. This is a custom function protocol comparison, **not** evidence
of any provider's native computer/bbox API support or box-overlap quality.

The [manifest](manifest.json) fixes exact models, endpoints, source revision/hashes,
image hashes, geometry, target masks, budget, prices and sequence before live calls.
The [driver](runner.txt) made 40 fake SDK requests first; its
[offline check](offline-check.json) verifies all 20 pairs differ only in the
coordinate schema and corresponding center/tight-box instruction. The actual
requests matched the frozen bodies and PNG bytes at the HTTP boundary.

Each model has two point-first and two bbox-first pairs, with model order rotated
between layouts. This balances first/second position, but is not randomization.
Each setting has only one response per layout. Four layouts include portrait and
landscape images and AC/7 targets, with varied positions; target and aspect ratio
are not independently crossed. Font, button size and visual family remain narrow.
Image hashes do not overlap the 64 reserved holdout images. Only the holdout input
hash list was read for this check; no holdout image or label was used for tuning.

Thinking is disabled; Qwen and DeepSeek temperature is 0.1, while the OpenRouter
GPT route omits temperature as in preflight. All requests have an 8000-output-token
budget, 90-second deadline and zero retries. DeepSeek uses `/beta` for both
protocols. OpenRouter pins provider `openai`, disallows fallbacks and requires
parameter support. These settings are fixed within each model's pairs; model
comparisons also include provider/adapter differences. Responses never dispatch
clicks. The 3600-second batch deadline is enforced between and during requests.

## Results

[Raw results](results.json) retain all 40 attempts; [summary](summary.json) includes
counts, conditional distance statistics, tokens, model and provider identity.
For each setting the denominator is four attempts, including malformed outputs:

- Qwen3.7 Flash: point legal 4/4, hit 3/4; bbox legal 4/4, hit 2/4.
- Qwen3.8 Flash: point legal 0/4, hit 0/4; bbox legal 2/4, hit 2/4.
- Qwen3.8 Max: point legal 3/4, hit 3/4; bbox legal 4/4, hit 4/4.
- DeepSeek Flash: point legal 4/4, hit 3/4; bbox legal 4/4, hit 1/4.
- GPT-5.5: point and bbox both legal 4/4, hit 4/4.

Overall: 33/40 legal, 26/40 hits. Every call returned HTTP 200 with known usage;
none truncated or timed out. Six Qwen3.8 Flash outputs contain arrays instead of
scalar coordinates. One Qwen3.8 Max point output is malformed JSON. All seven
remain failures without repair. Legal Qwen3.7 portrait responses miss by more
than 600 pixels; DeepSeek bbox misses reach 361.82 pixels. Format validity is
not evidence of correct grounding, and apparent coordinate patterns are not
used to infer units or add correction factors.

Distances in the summary are pixels from the predicted point/box center to the
true center, conditional on a legal coordinate being returned; they exclude
invalid responses and must be read beside the full-denominator counts. Hits use
the rendered rounded-button mask, not a distance threshold or bounding-box IoU.
The four-per-setting observations do not establish general accuracy, reliability,
or a causal benefit across layouts. Runtime durations include capture/local work
and concurrent regression tests; they are not comparative latency measurements.

All eight GPT responses identify provider `OpenAI`; direct providers supply no
provider field. Qwen Max returns `qwen3.8-max-0902`; other returned model identifiers
match their requested aliases. Immutable served weight identity remains unverified.

## Accounting and decision

This batch used 79357 tokens, leaving **104 requests / 920643 known tokens** under
the screening stage's 144-request / 1000000-token ceiling. Preflight remains
16/16 requests and 26398 tokens; its count is neither reset nor merged into the
screening allocation. The next batch must carry forward this screening usage.

The pre-call uncached peak-price estimate was $2.912432, based on 10000 estimated
input plus 8000 maximum output tokens per call. The actual-usage list-price
estimate is $0.127608331. OpenRouter reports $0.09118 across its eight calls;
direct-provider charged amounts remain unknown, so the total bill is unknown.
The driver stops on API/timeout/missing usage or excess input reservation. Input
reservation is conservative estimation, not an exact tokenizer or billing cap.

Prices checked before execution, in USD per million input/output tokens:

- [Qwen3.7 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash): Beijing snapshot, input <=32k, 0.028/0.11.
- [Qwen3.8 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash): Beijing, 0.113/0.382.
- [Qwen3.8 Max](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max): Beijing snapshot, 1.65/4.951.
- [DeepSeek Flash](https://api-docs.deepseek.com/quick_start/pricing/): uncached peak, 0.30/1.20; actual cache/off-peak charges may be lower.
- [OpenRouter GPT-5.5](https://openrouter.ai/openai/gpt-5.5): pinned OpenAI provider, 5/30.

Keep the existing production baseline. Retain Qwen Max bbox and GPT point/bbox
as development candidates, but do not freeze adoption from four layouts. Bbox
is not a universal fix: it did not eliminate Flash array outputs and DeepSeek
bbox hit fewer targets than point in this sample. Next, isolate thinking or image
settings in a separately frozen batch, carrying forward the remaining budget;
explicit status/absent/ambiguous handling and native protocols still need evidence.
No holdout calls, real screenshots or desktop actions occurred. M3 remains open.

## Tests

Shared grounding tests: 83 passed. All 40 request/raw-response/parser/score replays
passed; [audit results](offline-replay.json) and [audit driver](replay.txt) are saved.
The first audit script used the wrong distance field name; corrected to the
existing `distance` key and rerun without changing requests, responses or scores.
Full repository checks are recorded in [verification.json](verification.json).
No Python source or test files changed; changed-file pyright is N/A. Both `.txt`
drivers are execution records, not new production tools or supported CLIs.
