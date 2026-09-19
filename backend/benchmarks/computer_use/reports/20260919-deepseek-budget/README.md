# DeepSeek thinking and output-budget isolation — 2026-09-19

112 paid requests to the configured `https://api.deepseek.com`, requested and
returned model `deepseek-flash`. Only programmatically generated synthetic PNGs
were sent. No desktop capture, mouse action or production configuration change.
Strict-bbox explicitly uses `/beta`; all other variants use the default endpoint.

The previous 4000 cap was hardcoded in `location_request()` in
`core/src/tank_backend/benchmarks/grounding_probe.py`; it was a probe limit, not a
DeepSeek service limit. It remains the probe default but can now be overridden
with `--max-tokens`. Production default/planning profiles use 10000/20000;
the production computer_use Qwen profile uses 40000.

## Paired screening: 48 requests

Seeds 101–102, point / strict-bbox / low-detail, two repeats per case/variant.
Each of the following groups has 12 requests:

- [on / 4000](../20260919-deepseek-on-4000/results.json): 10 valid calls, 3 hits,
  2 length truncations; mean completion tokens 1301.17, reasoning 1230.50.
- [off / 4000](../20260919-deepseek-off-4000/results.json): 12 valid calls, 3 hits,
  no truncations; mean completion tokens 106.50, reasoning 0.
- [on / 16000](../20260919-deepseek-on-16000/results.json): 12 valid calls, 3 hits,
  no truncations; mean completion tokens 2023.58, reasoning 1928.17.
- [off / 16000](../20260919-deepseek-off-16000/results.json): 12 valid calls, 5 hits,
  no truncations; mean completion tokens 106.08, reasoning 0.

Point hit counts in those four groups are respectively 1/4, 3/4, 1/4, 3/4.
Strict-bbox: 2/4, 0/4, 2/4, 0/4. Low-detail: 0/4, 0/4, 0/4, 2/4.
At 4000, disabling thinking cut mean output tokens by 91.8%. Raising the cap
removed truncation in this small sample, but did not improve overall hits with
thinking enabled. Off-mode token use is far below either cap; a 3/12 versus 5/12
score is not evidence that the larger cap improves off-mode accuracy.

## Independent layout set: 64 requests

Seeds 201–216, normal auto-detail point protocol, two repeats each. These are
the same PNG layouts used for the earlier GPT/Qwen holdout, unseen in screening.

- [off / 4000](../20260919-deepseek-holdout-off-4000/results.json): 32/32 valid,
  20/32 hits (62.5%), no truncation. Mean completion tokens 103.94, reasoning 0;
  maximum error 339.33 image pixels.
- [on / 16000](../20260919-deepseek-holdout-on-16000/results.json): 31/32 valid,
  23/32 hits (71.875%), one length truncation. Mean completion tokens 736.44,
  reasoning 664.88; maximum error among returned coordinates 134.30 pixels.
  `deepseek-206-point-0` used 16000 completion tokens, all reasoning, and returned
  no click after 68.04 seconds. This was not the probe's 90-second timeout.

Off-mode uses 85.9% fewer completion tokens on this set. This is an output-token
comparison, not a claim about total input+output billing or equal inference
effort. Thinking enabled achieved three more hits, but both settings retain
substantial misses. The maximum error excludes the response with no coordinates.

## Interpretation and limits

The 4000 cap confounded previous completeness comparisons; a truncated response
is not a decoded coordinate error. Disabling thinking eliminates reasoning output
in all 56 observed off-mode responses and substantially lowers output usage.
Increasing the cap does not guarantee completion: one response exhausts 16000.
Neither adjustment establishes reliable grounding on these static synthetic UIs.

The actual SDK HTTP bodies are identical within paired trial IDs except for
`thinking` and `max_tokens`. Image hashes, detail, prompts, schema and endpoints
are held fixed within a variant. The [audit](audit.json) checks all 112 request
bindings and original response usages, finish reasons and tool arguments;
off-mode responses omit reasoning content and report no reasoning tokens.

Per the [official thinking guide](https://api-docs.deepseek.com/guides/thinking_mode/),
the OpenAI SDK switch is `extra_body={"thinking": {"type": "disabled"}}`.
Thinking defaults to high effort, and temperature is ignored when enabled.
Both conditions send temperature=0.1, so their effective sampling behavior is
not identical. Runs are stochastic and conditions are separate sequential blocks;
small score differences cannot be attributed solely to the cap or prove model
weights versus service-side preprocessing as the source. Low reasoning effort
is another available control, not tested here. Sixteen related layouts repeated
twice are not 32 independent layouts or full model-driven GUI acceptance.

## Reproduce

From `backend`, using the existing `DEEPSEEK_API_KEY` in `core/.env`:

```sh
uv run python scripts/probe_grounding_matrix.py --models deepseek --variants point strict-bbox low-detail --seed 101 --cases 2 --repeats 2 --thinking off --max-tokens 4000 --output /tmp/new-deepseek-off-4000
uv run python scripts/probe_grounding_matrix.py --models deepseek --variants point --seed 201 --cases 16 --repeats 2 --thinking on --max-tokens 16000 --output /tmp/new-deepseek-holdout-on-16000
```

Repeat screening with all four on/off × 4000/16000 combinations and holdout
with off/4000. Every output directory must be new. Full raw JSON responses are
gzip archived beside sanitized request JSON and generated PNGs. No secret headers
are archived. [Verification](verification.json): probe 48 passed, backend 4476
passed/1 skipped, E2E 14 scenarios/55 steps; required lint/types/docs/protocol and
backend reload checks passed. CLI-to-SDK tests cover knobs, defaults, unchanged
frames/schema, invalid budgets, and retaining length failures without a click.
