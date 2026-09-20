# M3 endpoint preflight — 2026-09-20

Initial preflight completed; M3 production adapters, strict/native protocols and
configuration selection remain open. No production code, profile, default model,
desktop state or holdout was changed. All images are generated development images.

## Evidence and reproduction

- [Point manifest](manifest.json), [pixel manifest](pixels/manifest.json) freeze
  revision, source hashes, endpoints, settings, prices and budgets before calls.
- [Point results](results.json), [pixel results](pixels/results.json),
  [summary](summary.json), [offline replay](offline-replay.json).
- Each directory retains the actual SDK HTTP request with image bytes replaced by
  SHA-256, the corresponding generated PNG, and compressed raw provider response.
  Request headers and credentials are never saved. HTTP hooks checked PNG hashes.
- [Point driver](point-runner.txt) and [pixel driver](pixels-runner.txt) are exact
  one-off execution records. To reproduce, use a NEW output directory, the recorded
  revision and backend environment, and recheck prices. They import existing
  `probe_grounding_matrix.run_trial`; do not execute them in the archived directory.
- Replay decoded all ten raw argument strings using the unchanged decoder and
  rounded-button mask scorer. Three array-valued responses were rejected unchanged.
  The raw response arguments/model were also checked against the recorded rows.

## Results and decision

One shared 1440×900 layout, seed 101, target AC; five models × two protocols.
These are paired development preflights, not ten independent layouts, a quality
ranking, production-loop evidence, or M8 acceptance. All ten returned HTTP 200,
usage and tool calls; seven met the schema, four hit the mask, none truncated.

- Qwen3.7 Flash: normalized point hit, 3.54 px error; pixel point missed, 287.37 px.
- Qwen3.8 Flash: both responses used arrays in scalar integer fields; rejected.
- Qwen3.8 Max: normalized point used arrays and was rejected; pixel point was
  legal but missed by 287.57 px. Requested `qwen3.8-max-2026-09-02`, returned
  `qwen3.8-max-0902`, consistent with the documented snapshot alias.
- DeepSeek Flash: normalized point hit the large button but error was 27.58 px;
  pixel point missed by 51.01 px. Returned model is only `deepseek-flash`:
  V4.1 attribution comes from current official documentation, not a returned
  immutable weight revision. Provider field was absent.
- GPT-5.5 via OpenRouter: both hit, errors 1.97/1.00 px; returned provider OpenAI.
  Qwen provider fields were absent too; a direct endpoint is not a response field.

Retain the baseline. Do not coerce arrays, guess coordinate units, infer a server
resize compensation, or select a production adapter from one successful layout.
Next: shared production/probe adapter with explicit units and fail-closed decoding;
then separately test native point/box, strict, image/detail and thinking settings
on development layouts before freezing candidates for the untouched holdout.

## Contracts checked

All calls used Chat Completions, base64 PNG in user `image_url`, detail `auto`,
custom `click` function (diagnostic only), scalar integer schema and no strict flag.
Normalized axes are 0..1000; pixel axes are 0..1439 and 0..899. These are explicit
probe contracts, not claims that providers guarantee native coordinate units.
No Responses computer-specific fields or OS actions were sent.

Qwen received `enable_thinking=false` and temperature 0.1; DeepSeek received
`thinking.type=disabled` and temperature 0.1; OpenRouter received reasoning `none`,
no temperature and OpenAI-only routing with fallbacks disabled. All output limits
were 8000, retries zero, timeout 90 seconds. Strict schema support and thinking-on
behavior were not tested in this batch; native bounding boxes remain untested.

Official sources checked on 2026-09-20:

- [Qwen3.7 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash),
  [Qwen3.8 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash),
  [Qwen3.8 Max](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max):
  list image input/function calling and pricing; Max documents the snapshot alias.
- [Qwen function calling](https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling):
  OpenAI-compatible function tool calls and `enable_thinking=false` example.
  Capability listings alone do not establish strict schema enforcement.
- [DeepSeek vision](https://api-docs.deepseek.com/guides/vision/): `deepseek-flash`
  supports user-message inline PNG and `auto` detail; documented image resizing
  does not justify an inferred inverse coordinate correction.
- [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/):
  `deepseek-flash` serves V4.1 Flash; Pro has no vision. No invented V4.1 model ID.
- [OpenRouter official model catalog](https://openrouter.ai/api/v1/models):
  `openai/gpt-5.5` lists image input, tools, structured outputs and reasoning;
  input/output list prices are $5/$30 per million tokens at this request size.

## Budget and limitations

Ten calls of the M0 16-call preflight ceiling have been consumed; six remain.
Each five-call batch estimated 10000 input + 8000 output tokens per request,
about $0.364 USD (uncached/peak list rates, no discounts). This is an estimate,
not a guaranteed input cap. Actual total usage was 16730 tokens; list-price
usage estimate is $0.026680, while only OpenRouter reported billed cost ($0.01902
for its two calls). Other actual billed costs remain unknown; never recorded as zero.
The DeepSeek peak price makes this a conservative estimate for the Sunday batch.

Each batch had a 100000-token stop and stops when usage is unavailable; no retries.
All usage was known. Point manifest wording also says stop on request failure:
HTTP requests all succeeded; parsing failures were retained and the batch continued.
Here “request failure” meant transport/API failure, not invalid model arguments;
pixel manifest makes that distinction explicit. Future drivers should encode
this distinction directly, persist a stop reason, and enforce the shared ledger.

A first local launch failed before writing the manifest because its output directory
was missing (zero model requests). The directory was corrected before the live run.
A sandboxed public catalog lookup failed DNS; the authorized network lookup passed.
No real screenshots were captured or sent. No model API requests ran in pytest.

## Tests

The unchanged probe suite passed 49 tests before live calls; ten saved responses
replayed offline. Full repository verification is recorded in verification.json.
Python changed-file pyright is N/A: no Python source or tests were modified.
