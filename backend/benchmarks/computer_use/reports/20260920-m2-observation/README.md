# M2 screenshot observations — 2026-09-20

The opt-in macOS image-coordinate interface binds actual PNG bytes to a session,
frame, main-display geometry and optional window bounds. Host code reverses the
actual rounded crop and resize. The legacy normalized interface remains the
default; no model/profile switch or new grounding-model request was made.

[Manifest and source hashes](manifest.json) freeze the tested implementation.

## Implementation and limits

Call `screenshot(coordinate_space="image")`, optionally with `region` and
`window_id`. The returned metadata includes `frame_id`, actual `image_size`,
`crop`, display/window identity and image hash. Use `coordinate_space="image"`
and that frame for click/move/positioned scroll/drag. Points are zero-based image
pixels; finite fractional values are accepted, strings/bools/out-of-range values
are rejected. Ordered bbox centers are computed before mapping. Round half up
once at Quartz, bounding the rounded result to the final source pixel.

ToolManager supplies session identity, never model arguments. A new observation
replaces the previous one in the tool group. Missing/old/foreign references,
changed display/window geometry and changed observed pixels reject input.
Window crops must lie wholly on the main display; this is not multi-display
support. Window IDs are optional host constraints, not a new AX discovery tool.

Before each image-coordinate action, capture without the cursor and compare
pixels in the observed crop plus display/window geometry. This is intentionally
conservative: animation/blinking can reject useful actions and each action adds
a capture. It cannot eliminate changes between validation and event delivery.
Unpositioned scroll/key/text actions retain their existing semantics and need
no invented coordinate frame. An image-mode batch binds all coordinate actions
to one frame, validates each step, stops on failure and returns a new screenshot.

## Tests and physical evidence

- Actual SDK HTTP / fragmented SSE / ToolManager / Quartz seam checks full and
  cropped image hashes, schemas and event coordinates without paid model calls.
- Tests cover non-even dimensions, 1x/1.5x/2x backing scales, 2x/3x zoom, edges,
  window offsets/movement/non-main rejection, invalid points/boxes/crops,
  session/old-frame rejection, shared batch mapping and cancellation while
  validating. Existing legacy, executor, N2 and SDK tests remain in the suite.
- [First full-screen attempt](full-screen-attempt.json) stopped before input on
  a scene mismatch. The changing pixels were not localized; it is not counted as
  a successful calibration. [Cleanup](full-screen-cleanup.json) confirms the
  calibration window closed and the cursor was restored.
- [Window-bound nine-point run](window-results.json): **9/9 hits**, maximum error
  **0 points on both axes**, all mouse down/up events received. Main screen was
  [1920x1080 points / 3840x2160 backing pixels](window-geometry.json); an 800x528
  window crop was enlarged to an actual 1920x1267 PNG. This exercises unequal
  rounded axis scales, host window offsets and real Quartz delivery.
- [Window-run cleanup](window-cleanup.json) confirms window closure and cursor
  restoration. Foreground restoration was requested but not independently
  recorded. Real PNGs remain only in the two local `/tmp/tank-m2-*` directories;
  no real desktop image was sent to a model or committed.

These results verify the M2 host transform on a static main-display test window.
They do not measure model grounding quality, fix historical I09 event anomalies,
or replace M6 Calculator/long-task/stop/cleanup acceptance. Physical drag/scroll
and moving-interface success are not claimed by the nine-point click run.

Reproduce locally from `backend/` (new output directory required):

```sh
uv run --no-sync python scripts/calibrate_macos_coordinates.py \
  --coordinate-space image --window --output /tmp/tank-m2-window-new
```

## Verification

See [verification record](verification.json) for the final mandatory checks and
retained failed attempts. The new tests first failed for absent/incorrect
behavior before implementation; a complete-suite schema failure exposed missing
array `items`, which was repaired. No test failures are waived.
