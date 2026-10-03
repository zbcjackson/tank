# S3 configured Jev smoke — 2026-10-03

Three frozen synthetic tasks passed through the real Runner, Computer Use plugin,
managed headless Chromium and TypeSafe HTTPS service. The unused parent LLM and
tool manager were test doubles; no parent LLM or personal desktop/browser was used.
This is integration evidence only, not a calibration or comparative benchmark.

- English “Store document”: selected Save; DOM readback confirmed saved; 2703 ms total.
- Chinese “保存文档”: selected 保存; DOM readback confirmed saved; 1458 ms total.
- No target (“Save document” with Cancel/Delete): selected none; no action; 1204 ms total.
- Each case confirmed cleanup and made exactly one HTTP request, without retry.
- Usage: 4235 input + 413 output = 4648 tokens. No unknown usage or outstanding reservation.
- Estimated cost: $0.000177870 using the frozen $0.042/M input-token rate and free output.
  This is an estimate from provider-reported usage, not a billing statement.

Model `jev-1.13.0`, endpoint `https://api.typesafe.ai/v1/systemone`. Host resolved
`TYPESAFE_API_KEY` from `backend/core/.env`. No credential value was recorded.
The batch had a three-request limit and $0.01 reservation limit; each case had
one request maximum. Pricing/context assumptions came from the
[official model documentation](https://docs.typesafe.ai/models).

Evidence:

- [freeze.json](freeze.json): cases, expected outcomes, limits and pre-request harness hash.
- [result.json](result.json): synthetic request/response JSON, request hashes, audit records,
  TaskResult evidence and timing. Request headers were not captured.
- [spend.jsonl](spend.jsonl): reservation/settlement journal.
- [Harness](../../jev_smoke.py): requires `--live` and a fresh output directory.

From backend, explicitly authorized repetitions can use:

```bash
uv run --no-sync python benchmarks/computer_use/jev_smoke.py --live --output <new-directory>
```

The original three-case dataset and pass criteria were frozen before sending.
A no-target pass requires the valid none choice, stopped outcome and zero action
receipts; malformed model replies do not count as correct refusal. Positive cases
require actual page postconditions and confirmed cleanup. Tests run this harness
with fake HTTP, including bad-reply scoring and the per-case request cap.

Not measured: representative task accuracy, confidence calibration, D2 vs full
ActionSet replay, cheap generative selector comparison, p95 latency, native desktop,
user browser attachment or recovery. S3 remains active; production defaults remain unchanged.
