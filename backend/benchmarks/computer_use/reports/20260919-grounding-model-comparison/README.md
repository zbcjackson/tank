# Same-provider grounding model comparison — 2026-09-19

80 requests; only generated calibration images were sent to DashScope. No desktop capture,
mouse input or production model switch occurred. Every streaming request's
image hash, model, temperature and enable_thinking were checked at the HTTP
boundary. The PNGs are reused from [the preceding experiment](../20260919-grounding-ablation/images/).

All groups use the same agent prompt, temperature=0.1, enable_thinking=true,
max_tokens=4000, SDK/LLM path, PNGs and scoring. Fixed models:

- qwen3.7-flash-2026-07-15 (current production model)
- qwen3.7-plus-2026-05-26
- qwen3-vl-plus-2025-12-19

Point-only schema: each model gets 8 hard trials (four images, target 7, two
repeats), plus 8 holdout trials (four images, AC/7, one repeat). Production-schema
confirmation compares Flash and Plus with the actual click schema including
bbox/oneOf, on the same 16 cases. Only click is advertised in either schema
condition; this is not an entire computer-use agent benchmark with all tools.

The holdout cases were defined in the previous investigation. They are held out
from the older hard set, but not a new unbiased model-selection benchmark.
Trials are serial within each group and concurrent across models; raw responses
are buffered before SDK parsing. Durations are descriptive, not controlled
latency benchmarks. Low-temperature generations remain nondeterministic.

Each group retains results.json. Raw SSE is stored losslessly as
`GROUP/<responses.file>.gz`; decompress to replay. summary.json scores each
request once and retains errors. The diagnostic measures Euclidean distance to
the known button center, not actual button hit rate. These small samples cannot
guarantee real GUI success or establish model-versus-hosting implementation causes.

## Reproduce

From backend, with authorized synthetic-image network access, use fresh output
directories and replace MODEL with one of the snapshots above:

```sh
uv run python scripts/probe_grounding_contract.py --model MODEL --thinking on --point-only --case-set hard --repeats 2 --output /tmp/new-model-hard
uv run python scripts/probe_grounding_contract.py --model MODEL --thinking on --point-only --case-set holdout --repeats 1 --output /tmp/new-model-holdout
```

Omit `--point-only` to run the production click schema. The model override uses
the configured provider and credentials but does not edit configuration files.
The investigation includes the [interpretation and remaining causes](../../../../../docs/research/macos-coordinate-chain.md).
