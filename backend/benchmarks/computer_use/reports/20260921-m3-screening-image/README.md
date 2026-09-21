# M3 provider image-processing screening — 2026-09-21

This development batch compares one documented image setting per provider,
through the existing production `GroundingAdapter` → `LLMProfile` → LLM → SDK
path. It does not add model-specific adapter classes or change production defaults.

## Frozen comparison

Four models × four development layouts × two arms = at most 32 requests:

- Qwen3.7 Flash: thinking off; `vl_high_resolution_images=false` versus true.
- Qwen3.8 Flash: thinking on; the same high-resolution toggle.
- Qwen3.8 Max snapshot: thinking off; the same high-resolution toggle.
- DeepSeek Flash: thinking on; `image_url.detail=auto` versus low, `/beta` in both arms.

All use scalar normalized point/integer/found, no strict flag, temperature 0.1
(and DeepSeek's documented thinking-mode caveat), maximum output 16000 tokens,
90-second deadline and no automatic retries. Qwen keeps image detail auto. These
are separate provider-specific interventions, not a universal meaning of detail.
The selected thinking settings are development choices based on previous batches,
not holdout-selected or adopted production configurations. GPT controls remain
in the previous protocol report and are not repeated here.

The [manifest](manifest.json) freezes source/previous-ledger hashes, prices, order,
geometry and every setting. The [driver](runner.txt) generated 32 real-SDK fake
HTTP requests; [offline checks](offline-check.json) verify all 16 pairs differ only
in their provider image parameter. Live bodies and PNG hashes must equal the
frozen copies before dispatch. Two layouts per model run control first and two
treatment first; model order rotates. This is balanced but not randomized.

## Images and scoring

All four development seed images (201–204) are enlarged exactly 2× on each axis
with nearest-neighbor replication, identically in both arms and across models.
Uploaded sizes are 2880×1800, 2100×3360, 3072×2048 and 3360×2100 (5.18–7.06 MP).
They exceed Qwen's documented default pixel ceiling of 2621440, so the high-res
intervention has an opportunity to change encoding. Enlarging copies existing
pixels; it adds no new visual information or independent layouts. These images
are not directly compared with historical original-size scores as a single-factor
effect. The 64 reserved holdout images remain unused and hash-disjoint.

The adapter still returns uploaded-image coordinates. The scorer divides by the
known **client-side factor 2** and uses the original rounded-button mask. Saved
`point` is in uploaded-image pixels, `score_point` and `distance` are in original
layout pixels. The offline audit compares every enlarged image's pixels with
exact 2× replication of the archived original, replays raw responses, and verifies
both the inverse transform and unchanged hit/distance calculations. It does not
infer a provider's internal resize, reinterpret coordinate units, or repair arrays.

## Provider evidence and prices

Checked before execution on 2026-09-21:

- [Qwen image processing](https://www.alibabacloud.com/help/en/model-studio/vision)
  documents a default 2621440-pixel cap for these model families, and the
  `vl_high_resolution_images` request parameter. Enabling it allows a larger
  image-token budget. This is the supported control used here; generic `detail`
  semantics are not assumed to match DeepSeek's behavior.
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
  documents low detail downsampling to 512×512 and auto/high/original retaining
  the original image. Actual internal pixels are not returned by the endpoint;
  response token fields and scores are recorded as evidence, not exact geometry.
- [Qwen3.7 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash),
  [Qwen3.8 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash),
  [Qwen3.8 Max](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max):
  Beijing input/output rates 0.028/0.11, 0.113/0.382 and 1.65/4.951 USD per million.
- [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/):
  Flash uncached peak rates 0.30/1.20; actual cache/off-peak charges may be lower.

The 32-call conservative list-price estimate is $1.017584 using 10000 estimated
input plus 16000 maximum output tokens per call. Before each request, the driver
checks cumulative known use, the historical 26000-token unknown-use reservation,
and the next request's reservation against the 1000000-token stage cap. The
request count is a ceiling; a token/time limit or a new request/usage failure
stops the batch. Input reservation is estimation, not an exact tokenizer bound.

## Results and decision

All 32 attempts returned HTTP 200 with known usage, legal scalar coordinates
and no truncation. They produced **24/32 hits**. Control/treatment hits (each
setting has four responses):

- Qwen3.7 off: high-res false 4/4; true 3/4.
- Qwen3.8 Flash thinking-on: false 3/4; true 3/4.
- Qwen3.8 Max off: false 4/4; true 4/4.
- DeepSeek thinking-on: detail auto 2/4; low 1/4.

Qwen reports 2503–2562 image tokens per control image versus 5042–6932 with
high-resolution enabled. Thus the parameter changed reported encoding use, but
this sample shows no hit-count improvement. Qwen3.7 high-res has a 394.196-pixel
miss; Flash has a 459.183-pixel miss in control and 113.958-pixel miss in treatment.
All distances are in original-layout pixels after the known inverse transform.
More image tokens did not ensure correct coordinates. Four successful Max
responses per arm do not establish reliability.

DeepSeek low uses 2589 prompt tokens across four calls versus auto's 5672, but
total tokens are **32149 versus 16415**. Completion/reasoning output outweighs
the input reduction. DeepSeek does not report separate image-token counts; these
are total prompt counts. Its auto response tokens also do not prove exact internal
image geometry. Do not infer service-side transforms from these counts or add
coordinate compensation. This is a small, stochastic sample, not a general
claim that low detail always increases cost or decreases accuracy.

Keep Qwen's existing default image processing and DeepSeek auto for subsequent
screening. Do not enable high resolution globally or adopt low detail from these
results. No configuration is frozen for holdout yet. The next bounded step is
explicit status handling on present, absent and ambiguous development targets,
within the remaining request ceiling; native protocol evidence remains separate.

Batch usage is **168914 tokens**. Screening cumulative totals are **105/144
requests; 319528 known tokens + 26000 reserved for the historical unknown call**.
Conservative accounted tokens are 345528, leaving **39 request slots / 654472
tokens after reservation**. Preflight remains 16/16 and 26398 tokens. The old
reservation is not a provider-reported usage value and is not released silently.

Actual-usage uncached peak list-price estimate is **$0.123534265** for this batch,
versus the pre-call $1.017584 estimate. None of these direct-provider responses
supplies billed cost, so actual charges remain unknown. All 32 archived requests,
responses, image transforms and scores passed offline replay. Full repository
checks passed; see verification below.

## Evidence and limits

[Results](results.json) retain every attempt, HTTP body, raw compressed response,
finish reason and usage. [Summary](summary.json) separates legality, hits, original-
layout pixel distances, input/image tokens and provider/model identifiers.
[Offline audit](offline-replay.json) and [audit driver](replay.txt) check the full
request/response/scoring chain. Invalid responses remain in the denominator;
conditional distance statistics exclude them and are not substitutes for hit rate.
The old 402's actual usage stays unknown; its reservation is not labeled consumed.

Four layouts, one response per setting and one narrow visual family do not
establish general accuracy. None is an absent or ambiguous target. No native
computer/bbox API, real task loop, physical action, screenshot freshness or model
adoption is validated here. No real screenshots, holdout calls or desktop actions
occurred. Timings include local work and concurrent regression tests, so they are
not comparative latency measurements.

## Tests

Before live execution: shared grounding tests 83 passed; 32 fake SDK requests and
16 exact provider-parameter pairs passed. Full repository checks and offline
replay totals are in [verification.json](verification.json). No production Python
source or tests changed; changed-file pyright is N/A. The first offline launch
used the repository root environment and failed importing PIL before creating a
batch or sending a request; rerunning in the backend environment succeeded.
The text drivers are execution records, not new production tools or supported CLIs.
