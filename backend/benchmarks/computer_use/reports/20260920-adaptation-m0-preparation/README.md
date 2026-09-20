# M0 offline preparation — 2026-09-20

Offline preparation is complete. No model requests, desktop actions or desktop
captures were made. Current endpoint availability and response model/provider
identity remain unverified; M0's live preflight checkbox remains open.

## Frozen artifacts

- [Manifest](manifest.json): baseline/current revision, source hashes, comparison
  factors, frozen M8 criteria, request/token/time ceilings and outstanding gates.
- [Snapshot](snapshot.json) and [current request](current-request.json): current
  configured profiles, application versions, primary-display geometry and final
  system/12 tool schemas serialized by AgentRunner → LLMAgent → OpenAI SDK.
  HTTP was replaced by an in-process final-text response; no tool ran. Credentials
  and headers are excluded; home/username are redacted. This request has no image.
  Its task is a snapshot task, not a comparable new benchmark trial.
- [Historical trials](historical-trials.json): all 126 trial results and hashed
  source report/trace references, including 80 original failures and 46 original
  successes. Preserve N2 33/42, SDK strict 4/36 plus smoke 2/6, and Part A 7/42;
  successful timeouts and smoke remain visible, not promoted to current strict.
- [Failure corpus](failure-corpus.json): all 38 failures from the named static
  source batches, with original outcomes and hashed request/response/image
  references. This is a selected development corpus, not a representative score.
- [Offline replay](offline-replay.json): all 26 matrix responses replayed from raw
  archived JSON through the current `decode_location`/`score_location`; schema
  validity and hit outcomes match their original records. The other 12 failures
  use the M1 legacy production protocol and are indexed separately, not claimed
  to have passed through the matrix decoder. Nothing executes archived actions.
- [Holdout inputs](holdout/inputs.json), [isolated truth](holdout/truth/labels.json)
  and [generation record](holdout/generation.json): 64 new independent layouts;
  48 present targets, 8 missing targets and 8 ambiguous duplicate targets.
  [Dataset verification](dataset-verification.json) records zero image-hash
  overlap with historical PNGs. No holdout image has been submitted to a model.

The unsandboxed read-only geometry check found display ID 5, logical 1920×1080,
backing 3840×2160 and available screen-recording/input-control permissions.
The sandbox initially returned display ID 0, zero dimensions and false permission
flags; that was not treated as the host's actual geometry or a request to regrant
permissions. Display IDs and process permissions must be rechecked for live work.

## Holdout use and reconstruction

From `backend/`, generate into a **new** directory:

```sh
uv run --no-sync python scripts/prepare_grounding_holdout.py --output /tmp/tank-holdout-new
uv run --no-sync pytest core/tests/test_grounding_probe.py -k holdout_export
```

The generator uses the Pillow version/bundled font recorded in `generation.json`.
Tests regenerate twice and compare every byte, require 64 unique images, verify
truth separation, mask/center consistency and refuse overwriting a frozen set.
The committed image bytes and hashes are authoritative if render libraries change.

Eight strata contain eight layouts each: dense, sparse, small targets, typography
sizes, UI scale, partial occlusion, duplicate labels and absent labels. Portrait
and landscape images use non-even dimensions; positions and labels are shuffled.
Coverage is synthetic keypads with one bundled font family and limited occlusion,
not broad application or font-family coverage. M5 must report those limits and
add a separately frozen batch if broader coverage is required; do not silently
replace these images after looking at model outcomes.

A future M3 adapter consumes only the image, size and semantic target from
`inputs.json`. It must not send `truth/`, seed, stratum, target center, bounds or
mask. The existing matrix CLI generates its own images; invoking it with a new
seed does **not** evaluate this frozen set. Wiring the frozen input set into the
production-shared adapter is M3 work, not claimed implemented here.

Only present-target masks contain executable pixels; ambiguous and missing cases
have empty masks and null centers. Occlusion is subtracted from the mask. Count
all requests including malformed output, truncation and timeout; score positive
hits using the visible mask, center error separately, and absent/ambiguous refusals
separately. Group repetitions by layout. Three candidates × 64 layouts × two
repetitions yields at most 384 requests, not 384 independent layouts.

## Reusing historical traces (R)

The index retains source paths/hashes instead of copying real screenshots. Review
and replay are local only. A few concrete references guide the next work:

- N2 calc-open trial 2 (original success) used `command+space`, observation, then
  a short mouse/wait batch. Trial 1 (original failure) instead tried Linux-style
  `super`, `ctrl+u` and `gnome-calculator`. These traces distinguish environment
  selection from coordinate failure. Both timed out; the historical success
  flag is not proof of current strict correctness or new cleanup acceptance.
- SDK calc-open trial 2 contains explicit `model_action` signature errors for
  keypress, click and type, with batch feedback reporting zero completed actions.
  This is useful historical adapter/error-feedback evidence, not a new current
  SDK defect claim and not grounds for repeating all N2 benchmarks.
- Part A browser-navigate trial 1 alternated bbox, singleton-list/string points
  and unsupported `bbox` arguments; later mouse_down/up hit the historical
  `CGEventRef.getLocation` error. Parser/driver failures must be separated from
  visual model error. The historical failure remains even where code was fixed.

Keep batch feedback and renewed observation, validate protocol/host contracts
before attributing residual errors to model weights, and never infer a universal
coordinate correction from these mixed historical failures. M1 input fixes and
local pixel review remain separate from future real-model closed-loop evidence.

## Budgets and remaining live work

This batch: 0 requests, 0 model tokens, $0. No current-price lookup is required
for zero paid calls. Future costs remain **unknown**, not zero.

The manifest sets planning ceilings of 16 preflight + 144 screening + 384 holdout
requests. Exact model/profile, adapter, image/detail/thinking settings, serialized
requests and current route prices must be frozen in a new live-batch manifest
before calls. Those stages have conservative token stops and 90 seconds/request;
failed calls consume the cap, with no automatic retries. Existing M1 prompt A/B
(12 requests, 73,940 tokens) remains charged to its original completed batch.
No real screenshot transfer authorization is expanded by this preparation.

M2's Observation/new coordinate interface and B/C/D modes are still planned,
not enabled configuration switches. Next: M2 offline TDD, then M3 actual endpoint
preflight and a priced live manifest. The original M8 adoption thresholds are
copied unchanged; defaults and legacy coordinates remain unchanged.

## Tests and verification

The holdout test first failed because the generator did not exist, then passed.
A full-suite run exposed a manual-scheduler test racing its every-minute cron
schedule (two records instead of one). Its job now disables periodic scheduling
while retaining the real manual-trigger path; no production scheduler changed.
Sandbox port/Chromium failures were retained as failed attempts and rerun with
appropriate execution access. Final checklist results are recorded in
[verification.json](verification.json).
