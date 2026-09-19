# Grounding protocol isolation — 2026-09-19

Only generated calculator PNGs were sent to providers. Production model and
desktop tools are unchanged. These are grounding diagnostics, not completed
real-desktop agent benchmarks. Every row retains raw provider JSON and the
sanitized request; image URLs are replaced by hashes pointing to generated PNGs.

## Experiments

- [Schema preflight](../20260919-protocol-preflight/results.json): 14 calls,
  seven models, nullable integer type array with/without strict.
- [Equivalent anyOf schema](../20260919-protocol-anyof-preflight/results.json):
  8 Qwen calls, nullable points/boxes.
- [Model/protocol baseline](results.json): 84 calls, seven models × four new
  layouts × normalized point, pixel point, normalized box. Integer-only fields.
- [Isolations](../20260919-protocol-isolation/results.json): 66 calls, current
  Flash/Qwen3.8 Flash/GPT-5.5 × two layouts × eleven single changes.
- [Independent holdout](../20260919-protocol-holdout/results.json): 96 calls,
  three candidates × sixteen new positions/layout seeds × two repeats. No tuning
  on these images before this run. Same four canvas sizes, two target labels.
- [Native API replay](../20260919-protocol-native/results.json): 8 calls,
  current Flash/Qwen3.8 Flash × four baseline images. Payload hashes checked;
  the `http_verified` field here refers to pre-serialization payload verification.
- [Strict boxes / low detail](../20260919-protocol-strict-resolution/results.json):
  16 calls, four models × two images × two conditions.
- [Detail repeat](../20260919-protocol-detail-repeat/results.json): 12 calls,
  GPT-5.5 × two images × auto/low × three repeats.

All 304 requests use max output budget 4000, no retries, non-streaming responses.
Qwen/DeepSeek use temperature=0.1 and thinking enabled except explicit controls;
GPT uses reasoning effort=low, omits temperature, and pins OpenRouter to the
`openai` provider with no fallback and require_parameters=true. Returned GPT
provider is OpenAI. Cross-provider reasoning budgets and elapsed time are not
equivalent performance controls. Concurrent diagnostics are not latency benchmarks.

## Results

In the four-layout baseline, normalized-point button hits were Flash 0/4,
Plus 2/4, Qwen3.8 Flash 4/4, Qwen3.8 Max 3/4, DeepSeek Flash 4/4,
GPT Mini 4/4, GPT-5.5 4/4. All 84 calls passed the integer output contract.
Box output did not reliably improve grounding: Qwen3.8 Flash 2/4, Max 1/4,
DeepSeek 2/4. The native bbox_2d text task from the previous investigation is
a different protocol and should not be conflated with these flat tool fields.

Independent normalized-point holdout, all 32/32 valid outputs per model:

- GPT-5.5: 32/32 button hits, median center distance 1.01px, maximum 2.08px.
- GPT-5.4 Mini: 30/32 hits, median 4.77px, maximum 38.83px.
- Qwen3.8 Flash: 25/32 hits, median 5.56px, maximum 417.91px.

The schema preflight exposed a compatibility trap: all eight Qwen type-array
responses and all eight anyOf responses returned quoted coordinates. strict=true
did not enforce integer types there. Integer-only fields fixed that preflight
format issue but did not fix bad grounding. This is an issue in a newly proposed
protocol, not evidence that production previously used nullable fields.

Current Flash still missed under markers, crops, resized images, and the complete
desktop tool set. GPT-5.5 passed all present-target isolation cases and correctly
abstained on both absent targets. Two Qwen3.8 Flash no-thinking responses instead
returned arrays for integer fields. Two DeepSeek strict/detail responses exhausted
4000 reasoning tokens with finish_reason=length; those are budget truncations,
not evidence that schema-constrained decoding emitted invalid integers.

Native DashScope API point hits: current Flash 1/4 (max 281.96px), Qwen3.8 Flash
2/4 (max 533.33px). A compatibility-layer-only explanation is insufficient;
native vs compatible score differences are not attributable with four stochastic
calls. Model weights and service-side vision/inference remain inseparable here.

GPT-5.5 low-detail initially missed one of two targets by 406.94px. Additional
paired auto/low repeats hit 6/6 in each condition (low maximum 3.91px). The large
miss was not reproduced: this is a warning about a possible sensitivity, not
proof of a deterministic low-detail resize bug or the current Flash root cause.

## Reproduce

From backend, with configured BAILIAN_API_KEY, DEEPSEEK_API_KEY and
OPENROUTER_API_KEY (never paste secrets into commands):

```sh
uv run python scripts/probe_grounding_matrix.py --cases 4 --variants point bbox pixels --output /tmp/new-model-protocols
uv run python scripts/probe_grounding_matrix.py --models qwen38flash gptmini gpt55 --seed 201 --cases 16 --repeats 2 --variants point --output /tmp/new-holdout
uv run python scripts/probe_grounding_matrix.py --models flash qwen38flash gpt55 --cases 2 --variants point strict-point marked shuffled history crop resized agent full-tools absent no-thinking --output /tmp/new-isolation
```

Use --schema-style type-array/anyof for the nullable controls; default integer
requires found=false with all coordinates=0. DeepSeek strict variants explicitly
use its beta endpoint. This differs from the default endpoint and is recorded.
Every output directory must be new. Raw model calls never inject input events.

The [Calculator oracle](../20260919-calculator-oracle/results.json) is a separate
local-only check: AX button identities/positions → actual ScreenshotTool →
ClickTool → AX expression/result. Three recorded trials displayed 7×8=56; all
12 cursor positions were within one logical point of the target center. An
earlier unrecorded attempt failed a cursor assertion; its coordinates were not
saved, so its cause remains unknown. No desktop pixels are archived or uploaded.

Full-loop/history compaction and a model-driven real Calculator benchmark remain
unverified. Markers/shuffled scenes provide evidence, not access to the model's
internal recognition or coordinate representation. A 32/32 result on sixteen
related layouts is not a production reliability guarantee.
