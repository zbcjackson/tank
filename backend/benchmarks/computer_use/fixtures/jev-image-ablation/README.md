# Real TextEdit image ablation

## Post-crop validation options

Preparation accepts `--record-only --text-controls`. The reviewed freeze then has
no batch request/token/cost admission limit; usage is still journaled, unknown
usage/effects stop, and each microtask retains one decision/one fill and a 120s
deadline. The original limited mode below remains the default. `record_only`
reports unpriced usage; any historical-rate estimate is calculated separately.
Execution reads the flags from the approved freeze rather than accepting overrides.

Text controls add eight trials (North/South named explicitly, two positions, both
arms). They retain both replacement alternatives and omit private completion;
the task and GoalContract share the named instruction. Together with the original
eight color trials and six Box questions this gives 22 planned judgments, not a
new billing cap. All captures are saved under `frames`, including Box before/after
captures even when the response is rejected. Native `computer_use_freshness`
events identify the exact refusing stage without changing dispatch outcomes.

## Original comparison protocol

This uses the installed TextEdit with seeded temporary RTF documents, not a handmade
UI. Current plain AX observations expose the body and toolbar but not per-character
body colors. Both arms retain actual AX descriptions, including the incomplete
flag caused by TextEdit's failing TextArea AXDescription. Native execution keeps
the existing identifier profile and its strict completeness/reference/effect gates.
No global AX error handling or production configuration changes.

The task replaces only the red North/South line with DONE, choosing one of two
known full-body replacement inputs. Formatting preservation is outside the task.
Two color assignments and two window positions yield four paired tasks per arm.
Arm order alternates; input alternative order reverses with position. Each task
permits one model decision and at most one native AXSetValue, plus its bind.
Fixture setup selects only the black title, with AXSelectedText readback and the
unchanged body verified. This stops the insertion-caret animation without hiding
the red/blue target lines or relaxing exact frame checks; it is recorded separately
from model-selected task input. The same setup applies to both arms and Box windows.

The benchmark-only selector uses the same question builder, actual full AX view,
image metadata, mapped candidate bounds and instructions in both arms. It captures
the same kind of frame even for text, then sends PNG bytes only in the image arm.
Fresh processes require new references and opaque temporary names; these may vary
between paired trials. No labels are removed to create a visual advantage.

Private RTF seeds and labels are separate from public intent/alternatives. The
controller retains the exact expected body for verification; the selector removes
private completion from its public model projection. This removal is identical in
both arms. No private color assignment, RTF bytes or oracle label enters a request.
The runtime still authorizes only the two original bound fill actions. Poisoning
the private completion must leave the public question unchanged.

Two additional fresh original RTF windows support six read-only Box requests:
small italic button, absent Export CSV button, and several alignment buttons,
at two positions. An independent AX traversal reads control labels/rectangles
without querying the optional TextArea description. Unique-target centers use a
10% interior inset; absent/multiple cases score cardinality separately. Box never
dispatches input. Center hits do not certify IoU or calibrate confidence.

From backend, prepare a fresh directory offline:

```sh
uv run --no-sync python -m benchmarks.computer_use.jev_image_ablation --output /tmp/ablation-new
```

Inspect `freeze.json`, `public.json`, `private/labels.json`, and both RTF seeds.
Limits: 14 total requests, USD0.10 conservative reservation, 120 seconds per trial,
Jev1.14.0, no retries. Per-context limits are one task choice or three Box calls;
text must send no image, image/Box exactly one. Pricing/context ceilings reuse the
[previous frozen protocol](../jev-image-native/README.md), not a provider invoice.
All source and input/label hashes must match the reviewed digest before execution.

Run separately prepared directories, never resume or overwrite a started one:

```sh
uv run --no-sync python -m benchmarks.computer_use.jev_image_ablation --output /tmp/ablation-fake --run fake --approved-sha256 <digest>
uv run --no-sync python -m benchmarks.computer_use.jev_image_ablation --output /tmp/ablation-live --run live --approved-sha256 <digest>
```

Fake mode operates real TextEdit and mocks only SDK HTTP; its responses/usage are
simulated and do not measure Jev. Live requires an unlocked desktop, pre-existing
Accessibility/screen-capture grants, TYPESAFE_API_KEY, and no running TextEdit.
Only the new owned process/document may be used; no personal session is borrowed.

All eight task and six Box denominators survive stops. Report model correctness,
abstention/wrong candidates and actual goal completion separately. An image choice
may be correct while native dispatch is refused (e.g. caret pixels changed); the
original frame check stays strict. Known stale/unstable/no-progress refusals with
settled usage/effects remain in the denominator and do not trigger retries.
Unknown usage/effects, unexpected operational errors or cleanup failure stop the
batch; cleanup failure quarantines the process-local desktop lease. CLI success
means the batch processed safely, not that every model answer or task passed.

`calls/audit/actions/spend.jsonl`, exact sent images and source/prepared task frames,
results, inputs and freeze retain evidence. Text source frames are archived but
not sent. Independent fresh body readback, witnessed owned AXSetValue and matched
proposal/sent receipt are required for task success. Box windows must retain the
initial body and add no actions. All resources, owned processes and temporary
files must be cleaned; credentials/authorization headers are never journaled.

Only two RTF templates are used. Results concern this current observation package,
not the AX platform's ability to expose attributed strings or general GUI planning.
Formatting fields may reveal other state; keep them in both arms and inspect all
actual requests. Do not infer cross-application reliability or enable production
Box clicks from this small development comparison.
