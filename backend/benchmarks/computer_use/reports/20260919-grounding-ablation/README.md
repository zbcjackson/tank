# Synthetic grounding ablation — 2026-09-19

100 diagnostic requests to the configured DashScope qwen3.7-flash-2026-07-15,
temperature 0.1. No desktop screenshot was sent, no returned action executed.
This is a small, deliberately difficult diagnostic set, not a GUI success benchmark.

`images/` contains the eight distinct generated PNGs. Each variant's results.json
refers to those images by basename and SHA256. `summary.json` gives per-case
center distances and distinguishes malformed answers from scored coordinates.
15 px is a center-precision threshold, not a measured button hit rate.
The diagnostic uses x*width/1000, y*height/1000; production maps endpoints to
width-1/height-1 and rounds. That sub-two-pixel distinction cannot explain the
large observed errors.

Raw responses captured after adding the response hook are stored losslessly as
`VARIANT/<responses.file>.gz`. Decompress before replaying. They are original
provider SSE, including reasoning, not reserialized SDK objects. Earlier groups
have no raw SSE; their results contain the LLM-assembled function arguments.
The response hook buffers the body before SDK parsing; elapsed times are therefore
not comparable as streaming latency measurements. The first 56-call groups ran
two independent variants concurrently; requests within each variant were serial.

The `prompt` field retains the original agent template. Actual minimal/formula/
bbox system text is `Locate the requested UI element in the image.`; the
per-row `question`, `options`, coordinate note and schema specify each request.
No tools were sent for minimal-json or native-bbox despite the reference schema
being retained in their metadata. HTTP request hooks verified the exact image
hash and actual provider parameters on all streaming probes.

Minimal-json was collected before fenced-JSON decoding was added. Its raw results
remain unchanged; summary.json decodes whole JSON fences for scoring (two point
objects), but does not repair malformed JSON or count bbox arrays as point objects.
One HTTP 400 and one timeout remain failed attempts. Native-bbox requests explicitly
ask for a single bbox_2d array; all 16 answers use JSON fences, decoded explicitly.

## Reproduction

From backend, with the existing configured credentials and authorization to send
synthetic images, use a fresh output path for every invocation:

```sh
uv run python scripts/probe_grounding_contract.py --point-only --case-set hard --repeats 2 --output /tmp/new-agent
uv run python scripts/probe_grounding_contract.py --point-only --case-set hard --repeats 2 --thinking off --output /tmp/new-agent-off
uv run python scripts/probe_grounding_contract.py --point-only --case-set hard --repeats 2 --prompt-style minimal --output /tmp/new-minimal
uv run python scripts/probe_grounding_contract.py --point-only --case-set hard --repeats 2 --prompt-style minimal --thinking off --output /tmp/new-minimal-off
uv run python scripts/probe_grounding_contract.py --point-only --case-set hard --repeats 2 --prompt-style formula --output /tmp/new-formula
uv run python scripts/probe_grounding_contract.py --point-only --case-set hard --repeats 2 --prompt-style minimal --high-resolution --output /tmp/new-highres
uv run python scripts/probe_grounding_contract.py --point-only --case-set hard --repeats 2 --prompt-style minimal --plain-json --output /tmp/new-json
uv run python scripts/probe_grounding_contract.py --prompt-style bbox --case-set hard --repeats 2 --output /tmp/new-bbox
uv run python scripts/probe_grounding_contract.py --prompt-style bbox --case-set holdout --repeats 1 --output /tmp/new-bbox-holdout
```

holdout-agent/highres use the corresponding flags above with `--case-set holdout
--repeats 1`. minimal-off-wire uses minimal-off with one repeat after adding raw
response capture. nonstream-off reconstructs minimal-off's identical generated
PNG/hash, messages, point-only schema, temperature 0.1, max_tokens=4000 and
enable_thinking=false, then directly calls the same profile's SDK client with
stream=false. It retains the complete SDK response including image token usage.
No screenshot/input tools participate in any variant. Small samples and repeated
model generation do not establish a guaranteed production fix.

Detailed conclusions and limitations are in the repository's
[investigation](../../../../../docs/research/macos-coordinate-chain.md).
