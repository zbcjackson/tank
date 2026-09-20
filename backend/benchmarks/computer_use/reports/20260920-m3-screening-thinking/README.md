# M3 development screening 2: thinking — 2026-09-20

**Stopped after 7 of 32 planned requests.** DeepSeek returned HTTP 402
`Insufficient Balance` on the seventh request, with no usage. The frozen stop
policy halted the entire batch without retry; 25 requests were not sent. This is
an incomplete experiment, not a completed four-layout thinking comparison.

## Planned comparison and request checks

The [manifest](manifest.json) freezes Qwen3.7 Flash, Qwen3.8 Flash/Max and DeepSeek
Flash, each with thinking off/on on the four existing development layouts
(seeds 201–204). All use the existing scalar normalized point adapter, `found`,
integer zero abstention, `detail=auto`, no strict flag, and temperature 0.1.
Both arms use 16000 maximum output tokens, a 90-second deadline and zero retries.
This fits the existing stage ceiling; previous calls are carried forward rather
than resetting it. The production model and adapter remain unchanged.

The budget is larger than batch 1's 8000 in BOTH arms. Fresh off controls were
therefore included; the old responses are not substituted as paired controls.
Within each pair, the only serialized difference is `enable_thinking` false/true
(Qwen) or `thinking.type` disabled/enabled (DeepSeek). DeepSeek keeps `/beta` in
both arms and leaves effort at its documented default. GPT is not repeated in
this batch; the earlier protocol controls remain separate historical evidence.

[Driver](runner.txt), [offline checks](offline-check.json), frozen bodies and PNGs
were saved before execution. Thirty-two fake SDK calls verified all 16 pairs
through the production `GroundingAdapter` → `LLM` → SDK path. The live request
hook verified every exact body, endpoint and image hash before dispatch. The
exclusive start marker prevents rerunning this directory. Images match batch 1
and do not overlap the 64 reserved holdout images. No holdout image/label was used.

The plan balances two off-first and two on-first pairs per model, with rotated
model order. The early stop means only seed 201 was attempted: all three completed
Qwen pairs were off-first, so the realized sample is not order-balanced. There is
one layout and one response per setting, with no basis for a reliability estimate.

Official contract checks:

- [Qwen thinking](https://www.alibabacloud.com/help/en/model-studio/deep-thinking)
  documents `enable_thinking`, reasoning output, hybrid modes for these commercial
  families, and non-streaming support. Actual response behavior remains measured.
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
  documents the enabled/disabled toggle and default high effort. Temperature has
  no effect in thinking mode. Identical submitted temperature therefore does not
  imply identical effective sampling; this compares service modes, not an isolated
  internal reasoning mechanism. The 402 gives no new model-capability evidence.

## Observed results and failure

[Results](results.json) retain all seven attempts and [summary](summary.json)
separates known usage, unknown usage and unexecuted settings. Completed pairs:

- Qwen3.7: off legal and hit (2.807 px center error); on legal but miss (65.077 px).
- Qwen3.8 Flash: off returns illegal arrays; on legal and hit (4.981 px).
- Qwen3.8 Max: off legal and hit (2.860 px); on legal but miss (189.882 px).
- DeepSeek: off returns HTTP 402, no completion or usage; on was not sent.

Across seven attempted requests: five legal location outputs, three hits, one
invalid coordinate response and one endpoint failure. Among the six HTTP 200
responses, none truncated. The three on responses include reasoning content and
report 752, 143 and 191 reasoning tokens respectively. Off responses contain no
reasoning content and do not provide reasoning token counts; absence of a count
is not converted into a provider-reported zero.

The DeepSeek failure is an account/endpoint availability failure, not a model
localization result. It remains in the attempted-request denominator and request
budget, separately classified. The 25 unsent requests are neither successes nor
failures. Raw gzip bodies and sanitized requests are preserved; the
[offline audit](offline-replay.json) verifies all seven requests, all six
completion/parser/score results and the exact 402 error. [Audit driver](replay.txt)
uses the existing parser and rounded-button hit scorer without unit guessing or
coordinate repairs. Distances are conditional on legal coordinates. Durations
include local capture and concurrent tests and are not latency benchmarks.

## Budget and restart boundary

Batch known usage: **11655 tokens plus one unknown-usage request**. Screening
cumulative usage: **47/144 requests; 91012 known tokens plus unknown usage**.
There are **97 request slots** left. Arithmetic capacity before the unknown call
is 908988 tokens, but this is **not an established spendable token balance**.
Do not silently book the failed call as zero or restart the stage ledger. Preflight
stays unchanged at 16 requests / 26398 tokens.

The frozen 32-call uncached peak-price estimate was $1.017584, reserving 10000
estimated input plus 16000 output tokens per call. The six known responses have
an actual-usage list-price estimate of $0.007764192; total actual billing and the
failed call's usage are unknown. No response supplies a billed-cost field.
Same-day prices used in this session were Beijing Qwen3.7 0.028/0.11, Qwen3.8
Flash 0.113/0.382, Qwen3.8 Max snapshot 1.65/4.951 and DeepSeek peak uncached
0.30/1.20 USD per million input/output tokens. Sources are linked in the manifest
and the [prior batch](../20260920-m3-screening-protocol/README.md). Qwen pages were
reopened for this batch; DeepSeek pricing-page reloads timed out, so its same-day
previously fetched price evidence was retained rather than inventing a new quote.

Before more paid calls, resolve the missing usage with provider billing evidence
or an explicitly recorded conservative accounting treatment within the stage cap.
Continuing the DeepSeek arm also requires restoring its account balance. A future
batch must use a new manifest/directory, retain these seven attempts and account
for any repeated controls. It must not resume by overwriting this failure or
spend the 25 unsent slots as if they were already consumed.

Keep all production defaults. The single Flash success with thinking is a reason
to investigate, not an adoption decision; the two other on responses missed.
M3 thinking/detail/status/native and holdout acceptance remain open. No real
screenshots were sent, no desktop actions performed and no holdout calls made.

## Tests

Before live requests: 83 shared grounding tests and 32 fake SDK calls / 16
thinking-only pairs passed. After stopping: six raw completion replays and one
HTTP-error replay passed. Full repository checks are in
[verification.json](verification.json): backend 4595 passed / 1 skipped, E2E 14
scenarios / 55 steps passed, lint/type/docs/protocol checks passed. **The real
backend log check failed:** `tank:1.1` also reports DeepSeek HTTP 402 in Brain
stream/input processing. Account recovery and runtime revalidation remain open;
this is not an all-checks-passed acceptance. No Python source or test files changed;
changed-file pyright is N/A. The text drivers are execution records, not new
production tools. Passing software tests does not clear the account balance or
complete the stopped model experiment.
