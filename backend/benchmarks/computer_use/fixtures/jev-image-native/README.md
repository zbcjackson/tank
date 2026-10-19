# Real Calculator Jev image pilot

This recipe uses the installed macOS Calculator, not a handmade web page or a
synthetic picture. It tests the explicit finite-candidate image path, with full
AX labels still present; it does not isolate the image increment or open planning.
Qwen is not a dependency. Production defaults stay unchanged.

From backend, prepare a new directory without applications, clients or credentials:

```sh
uv run --no-sync python -m benchmarks.computer_use.jev_image_native --output /tmp/native-image-new
```

Inspect `freeze.json`: pinned Calculator/macOS version, source/SDK/Pillow hashes,
7×8=56 and 12+34=46 goal contracts, the Jev recipient and budgets. Each task allows
12 image choices/reviews plus one read-only final-frame Box: at most 26 requests,
USD0.10 conservative reservation, 120 seconds per task. Jev uses `jev-1.14.0`,
explicit image opt-in, original task scope/ledger and zero retries. Input pricing
and context bounds are pinned from [the provider](https://docs.typesafe.ai/models).
Estimated cost is not the provider invoice; unknown usage retains its reservation.

Execution requires the exact reviewed digest. Fake mode still operates the real
application, replacing only the SDK HTTP boundary; its tokens/results are simulated
and **not** evidence of real model quality. Use separate newly prepared directories:

```sh
uv run --no-sync python -m benchmarks.computer_use.jev_image_native --output /tmp/native-image-fake --run fake --approved-sha256 <digest>
uv run --no-sync python -m benchmarks.computer_use.jev_image_native --output /tmp/native-image-live --run live --approved-sha256 <digest>
```

Live mode loads only `TYPESAFE_API_KEY`, checks accessibility/screen-capture access
without prompting, and refuses an already-running Calculator. The owner creates a
new process/window, resets its own display, optionally varies window position,
and restores/terminates only that verified process. No personal documents, account
settings or existing Calculator sessions are borrowed. The process-local desktop
lease is not an OS sandbox or cross-process exclusion mechanism.
The desktop must remain unlocked: a locked macOS session can return application
placeholders in AXWindows even with both permissions granted, so strict window
binding refuses before any model request.

The plugin uses `selector: jev-image` and bounded `advisor: jev-image`. Non-rule
steps submit normalized bound-window PNGs with explicitly mapped candidate bounds.
Two matching captures, at most three total with 100ms spacing, are required before
the request; the original executor still rechecks source scene and references before
input. Rotated source images are refused by this execution path. Candidate review
shares the same selector, original task and four-review cap; it cannot generate
inputs, add actions or invent planning focus. Raw confidence is recorded, not an
authorization or a calibrated production gate.

`actions.jsonl` witnesses the actual native AXPress target PID and fresh AX label
around the real function. Strict acceptance requires the full expected button
sequence, separately read AX expression/result, controller goal verification and
task/application cleanup. The result explicitly separates processed batch status,
per-task success and read-only Box calibration. Setup, unknown-effect/usage,
operational or cleanup failures stop the batch; all two planned rows survive stops.

After a successful task, the same runtime captures the final bound frame and asks
Box for the Equals button. Its normalized point is mapped to source screen space,
compared with a fresh independent AX rectangle inset by 10% of its shorter side,
and recorded with source mapping/cardinality/confidence. This is read-only even at
high confidence: it has no coordinate executor and must add zero native actions.
Two samples do not calibrate confidence or justify automatic Box clicks.

`calls.jsonl` records actual admitted parameters, purpose, file hashes and parsed
responses; `images/` retains exact sent PNGs plus final bound-window evidence.
`audit.jsonl`, `actions.jsonl`, `spend.jsonl` and `result.json` retain task continuity,
native effects, cleanup, all denominators and known/unknown usage. Credentials and
authorization headers are never journaled. Old started directories and stale
source freezes cannot be resumed, edited or silently relabeled.
