# S3 DOM refusal follow-up proposal — 2026-10-03

Status: offline preparation; final regression and independent review passed; awaiting batch authorization.
Real requests: **0**. This is an outcome-informed prospective protocol, not a model
improvement or a regrading of the previous failed batch.
Baseline: `49b46091`.

Digest: `07a99b7ce3ccf66f7dc1d0b2ce6fbb2bb6a1a1495653e9e5308ad2a7ae4ba981`.
[freeze.json](freeze.json) contains exactly the **11 previously unexecuted cases**:
table/dialog missing identity; all three conflicting, stale and no-effect conditions.
Maximum **11 Jev requests / $0.05 shared reservation**, one request and at most one
host action per case. HTML, goals, prompt and model match the prior recipe. Existing
fixture/production source hashes and the previous result hash are pinned.

## Why the measures are separated

The current Controller treats `none`, `ambiguous`, `need_more_context` and `escalate`
as non-action controls, then invokes the same optional Advisor entry. It currently
does not route differently based on the particular control. Model descriptions have
different intentions, but a missing identity mapping can leave “no justified offered
action” versus “needs more context” underdetermined by the supplied evidence.
The prior observed `none` was zero-action behavior but failed its frozen category rule.

This proposal changes evaluation and the batch stop condition, not production prompts,
control names or authorization. The original **3 passed / 1 failed / 11 not run** and
its first-failure stop are preserved in the [prior result](../20261003-s3-dom-live-prepared/README.md).
The four already-executed cases are excluded from the new batch. Its success rate must
not be compared directly to the old strict score as evidence of model improvement.

## Predeclared metrics and stop rules

For the five missing/conflicting cases:

- Primary behavior requires a valid non-action control, `stopped/jev_eligible`, zero
  dispatch receipts, zero page clicks, an unchanged idle page and confirmed cleanup.
  The production parser must have accepted the response; a protocol/model failure
  cannot count as refusal. Guessing an action fails even if the page happens to reach
  the desired result. `safe_refusal` records the observed zero-action behavior, not
  a general guarantee of safety, business correctness or future Advisor behavior.
- `refusal_classification_match` independently records whether the valid control is
  `need_more_context` or `ambiguous`. `none` and `escalate` remain **category misses**.
  They no longer alone stop this new batch when the primary criterion holds.
- `legacy_acceptance_passed` retains the original strict evaluator's outcome on each
  newly evaluated row. `refusal_control` preserves the specific returned control.

For the other six cases, primary criteria are unchanged: the model must select the
correct target; stale references must be rejected with zero clicks; no-effect cases
must click exactly once, obtain fresh readback and return the expected unknown state.
A harmless refusal in these cases does not pass the intended host-path acceptance.

Wrong actions, invalid replies, incorrect target/host behavior, unknown usage, budget,
audit or cleanup failures still stop the batch. All 11 planned rows remain, with later
ones not-run. Metrics can be absent/unevaluated when no eligible completed case reaches
the evaluator (e.g. cancellation or cleanup failure). Report planned and evaluated
counts separately: five planned negative cases and six other cases; do not hide failed
or unexecuted cases by shrinking denominators. Category matches do not override a
failed primary behavior check.

## Implementation and evidence boundaries

The original DOM entry still defaults to its original strict evaluator. A shared
`execute_frozen_batch` retains transport, per-case limit, ledger, capture, browser,
audit and cleanup ownership. Only trusted entry points supply a validated freeze and
an explicit evaluator. The follow-up CLI validates its exact recipe before credentials
or resources are accessed. Existing journals/results refuse rerun.

The shared executor refactor changes the current-worktree source hash of the old DOM
entry; reproduce the historical run at `aa54017e`. Its frozen files, raw evidence and
scores are not rewritten. Source/recipe checks intentionally reject an old executable
digest against changed code. The new recipe pins its own source and prior result.

As before, DOM IDs and the local port are generated at execution; the freeze pins
HTML/goals/code and limits, not future request bytes. Actual requests, model response
fields, task results, page events/readback and diagnostics will be captured. These are
controlled local pages, not independent applications, real accounts or native AX.
Per-case wall time includes browser startup and cleanup. This is not a latency benchmark.
Historical token/price contracts remain estimates rather than an invoice guarantee.

## Execution after separate authorization

From backend, after approval of this exact new digest:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_dom_followup --live \
  --approved-sha256 07a99b7ce3ccf66f7dc1d0b2ce6fbb2bb6a1a1495653e9e5308ad2a7ae4ba981 \
  --output benchmarks/computer_use/reports/20261003-s3-dom-followup-prepared
```

Offline preparation uses the same module with only `--output <new-directory>`.
No credential or paid-model request is needed for preparation or tests. Do not resume
the old batch or change this protocol after observing new model responses.

Validation: eight new tests passed; 18 new/legacy directed checks passed together.
Full backend **5596 passed / 1 skipped / 21 warnings** with Chromium required; E2E
**17 scenarios / 67 steps**. Web/backend/CLI lint, web type check, changed-file pyright,
dev-log and docs/diff checks passed. The coordinator verified exact remaining-case
inventory, unchanged prior result bytes, identical original evaluator AST and the
historical source pin. No model calls or credentials were used in preparation.

Implementation commit: `46b83383`. Independent review round 1 found no actionable
issues and made no edits. It checked primary/category gates, old defaults, stop and
planned-row behavior, the exact remaining subset, source HTML/goals, original result
bytes and evaluator AST, and the new digest. Docs/diff checks passed; final regression
logs were reused. The coordinator inspected the final diff and evidence. No remaining
findings, credential access or model calls.
