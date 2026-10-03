# S3 v2 — rubric and connection diagnostics

2026-10-03. Original frozen protocol; the user subsequently approved its one execution.
See [the execution record](../../reports/20261003-s3-v2-prepared/README.md).
The protocol below was not changed after results were observed.

This revises the 24 previously observed synthetic scenarios. The calibration/holdout
names are historical strata, **not a new blind holdout**. No thresholds are fitted
or installed. This measures selection/refusal behavior and transport effects under
a clearer contract; it cannot establish generalization or causal improvement over v1,
because both prompts and fixtures changed. V1 sources, gold and results remain untouched.

Each model receives the same compact question: objective, declared inputs, current
facts and self-contained operation/role/label/value/ancestor candidates. Native refs,
binding versions and bookkeeping IDs stay in the host. A single `abstain` option
replaces overlapping refusal labels. Jev still reports a full probability vector;
Qwen emits a choice only, thinking disabled, max output 128 and temperature 0.

Primary scores separate actionability, selected-target correctness, wrong actions,
and false refusals. Invalid responses cannot count as correct abstention. Host gates
and recall misses remain separate. Chart/photo cases explicitly lack required data;
choosing an evidence-gathering step is prohibited, and Open chart is no longer an
option. Positive cases add semantic near-misses (save in place vs copy, whole-file
print vs selection, product search vs order search, pause vs cancel). Positive
positions span all four slots, with counts 3/3/2/2 across ten positives; candidate
order remains case-hash-based and never reads gold.

## Transport comparison

The single whole-action question runs in two modes, cold and pooled. Mode and model
order alternate by case. Every eligible case is sent once per mode/model: at most
64 requests, Jev and Qwen 32 each. Rules and shared host gates still occupy rows but
send no requests. There are no hidden warm-up requests. A pooled arm's first request
is normally cold and is **not** counted as observed reuse. Servers may close a socket;
new connections in the pooled arm remain visible rather than being called warm.
Provider prompt caching, load and time/order effects remain possible even with
alternating order; observed pool reuse is not proof that every latency difference
is due to connection setup.

Each task has its own authority, governed TaskModelTransport, audit and budget state;
only the underlying provider HTTP pool is shared. The experiment owns pool closure.
All calls use the shared strict SpendLedger; unknown usage, audit failure or uncertain
cleanup stops the batch. Partial/cancelled call evidence is journaled. No native UI
action is executed. Existing journals reject reruns.

Trace uses the [httpcore request trace extension](https://www.encode.io/httpcore/extensions/)
with HTTP/1.1, zero retries, one connection per provider and 60-second keep-alive.
HTTPX/httpcore versions are frozen. Only event names and elapsed times are stored;
trace info objects can contain headers/secrets and are discarded.

Reported phases: TCP connect (including DNS work), TLS, request headers/body send,
response-header wait and completion, response-body receive and completion. Missing
start/end events produce null, not zero. These are client-side boundaries:

- Header completion is not exact first byte (TTFB).
- Header wait still mixes network RTT, server queueing and inference.
- DNS is not measured independently; OS DNS caches are not cleared.
- Pure server inference time is unavailable and is never inferred by subtraction.
- Pool setup has its own timing; governed total starts afterward and includes client,
  audit, HTTP and response validation. Socket-close time is outside that total.
- Summaries report valid-return counts and observed-reuse counts alongside medians;
  per-row phases retain failed/missing measurements. Small N supports no p95 claims.

## Frozen proposal

Reuse the reviewed v1 endpoints/model versions and conservative prices:
`jev-1.13.0` at TypeSafe, `qwen3.7-flash-2026-07-15` at DashScope. Total request cap 64,
shared reservation cap $0.25; not a provider-invoice guarantee. Qwen upper-tier
pricing deliberately overestimates short input. See the
[v1 price evidence](../s3/experiment.md). Credentials remain host-resolved from
TYPESAFE_API_KEY and the existing computer_use profile, and are loaded only by --live.

From backend:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_replay_v2 --output <new-directory>
```

After separate approval of that new v2 digest:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_replay_v2 --live \
  --approved-sha256 <approved-v2-digest> --output <prepared-directory>
```

Preparation is offline. The actual revised questions, separate gold, limits, source
hashes and HTTP versions are saved before authorization. Any change requires a new
freeze; previous paid-batch approval is not reused.
