# S1 AX / Vision observation acceptance

Date: 2026-09-30. Local, synthetic acceptance; no desktop capture, native input,
paid model calls or production default changes. Full verification/review status
is tracked in the [active plan](../../../../../docs/plans/active/computer-use-strategy-ladder.md).

## Frozen evidence

The [revision-1 manifest](../../fixtures/s1/manifest.json) pins 14 PNGs by SHA-256,
font identity, truth boxes, target labels, split/family and predeclared thresholds.
Calibration uses a form/menu layout; holdout uses a toolbar/panel layout. Each
split covers Chinese, 11px text, an isolated digit, duplicate labels, parent/child
semantics, an unlabeled icon and an absent target. The images were rendered locally
with Pillow and PingFang; they contain no user data. Truth is only imported by the
acceptance harness and tests, never by candidate construction or an observation source.

[Raw Vision results](vision.json) record every returned region, one-to-one exact
text/box matches and the manifest hash. macOS 26.6.2, PyObjC Vision 12.2, request
revision 3, accurate, zh-Hans/en-US, language correction off. Both splits matched
7/7 text instances with zero unmatched output regions; every matched center lies
inside its truth glyph box. Maximum center deviation from the truth box center is
1.12 image pixels in calibration and 2.50 in holdout. These are OCR localization
errors, distinct from M2 coordinate conversion error (the crop/negative-display
unit fixture maps the text center exactly to the expected global point).

`test_frozen_ax_golden_cases` passes all 14 synthetic native-boundary cases through
AXObservationSource and ActionBuilder: 10/10 unambiguous actionable targets produce
the correct complete click candidate; two duplicate-label and two absent-target
cases produce no actions. Parent text is retained separately and is not an extra
click target. These are candidate decisions, not observed physical click outcomes.
Additional unit cases verify known-value fill, native handle identity across
reordering, changed focus/value, disappeared handle retirement, ambiguous window
binding, depth/children/node/text caps, top-32 selection after whole-scope ambiguity
checks, and exact targets beyond the initial 32 rows. Wrong candidate proposals in
these fixtures: zero; physical mis-action rate: unmeasured.

The real controller/runtime tests reject zero read allowance, revoked reads and
incomplete observations without dispatch. A real TaskModel / OpenAI SDK with fake
HTTP sends two current AX semantic views: no image parts, image data URLs, native
handles or previous observation id; usage shares the task ledger. This is not an
implementation/acceptance of the S3 Jev or S4 live Advisor.

## Reproduce

From `backend/`, with workspace packages installed:

```sh
uv sync --all-packages --all-groups --extra vision
uv run --no-sync pytest core/tests/test_computer_ax.py plugins/agent-computer-use/tests -q
uv run --no-sync python -m benchmarks.computer_use.s1_acceptance
```

Vision requires macOS plus the optional `pyobjc-framework-Vision` dependency.
The sandboxed OS call returned `(False, None)`; local acceptance ran outside the
filesystem sandbox on the same frozen PNGs. No fallback recognizer was used.

## Decision and limits

OCR remains **auxiliary only**: `text_region`, no actions; the measured sample is
small and synthetic and does not establish real-app coverage. AX and OCR remain
separate observations. The default plugin factory still refuses live configuration;
these sources are constructor-injected read adapters. S2–S4 supply later channel,
model, execution and recovery integration. The AX source binds a host-supplied M2
window/display frame; future dispatch must still refresh geometry/native identity.
No native AX application capture, live action accuracy, latency improvement,
production adoption, or recovery acceptance is claimed here.
