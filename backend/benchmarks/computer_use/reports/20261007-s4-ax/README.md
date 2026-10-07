# S4-AX native execution evidence

2026-10-07. Implementation and controlled native-app validation passed. After specific
user continuation, the frozen real Jev batch ran and **stopped on its first case**:
0 passed, 1 failed, 8 not run. A second user-requested batch reproduced the model-call
failure, with all cleanup checks confirmed this time. S4-AX acceptance remains incomplete.

## Frozen final recipe

- Source: implementation `2477cbf8`, review fixes `81539acb`.
- Digest: `d51fe70491947f1b56d8aaaedf3f1ea15953dfd021c0cdadcb2956b44752662c`.
- Nine cases: Calculator AXPress ×3, Calculator Quartz ×3, TextEdit AXValue fill ×3.
  Each group includes a moved window. Calculator must independently read `7×8` and `56`;
  TextEdit must exactly match the supplied Unicode/newline text. Saving is not claimed.
- At most 78 model decisions; batch 12,000,000 token allowance and $0.25 estimated-cost
  ceiling, per trial 120 seconds and $0.10 ceiling. Stop at first failed/unknown case,
  unknown usage, exhausted budget or unconfirmed cleanup, retaining all planned rows.
- Real destination: `https://api.typesafe.ai/v1/systemone`, model `jev-1.13.0`.
  The configured `TYPESAFE_API_KEY` is used only in live mode. The request contains the
  goal and supplied temporary text, current bound AX snapshot (roles, labels, values,
  bounds and references), structured candidate actions, observation binding and progress.
  This is application UI data sent to an external service; the user subsequently
  authorized continuation of the real test.
- Scope: newly owned Calculator and temporary TextEdit documents, foreground primary
  display only. Existing target-app processes are refused. No screenshots or other-app
  documents are model inputs. Production channels borrow an explicit window; only the
  benchmark owns launch/termination and temporary-file cleanup.

## Evidence

[Final fake result](fake/result.json) contains **9/9 passes**, 27 mock HTTP requests,
zero external requests. All independent values and owned-application cleanup checks pass.
The real SDK/Runner/native AX and dispatch execute; only the SDK HTTP boundary is replaced.
The fake sequence proves wiring, not Jev's planning or selection capability. Synthetic
usage/cost in fake ledgers is test data, not actual provider spend.

[Final freeze](fake/freeze.json) and [prepared live freeze](live-prepared/freeze.json)
are identical. [Approval block](live-prepared/approval-block.json) records the not-started
historical pre-execution status: no started marker, no loaded live credential, no requests
at the time of rejection. The later authorized run is recorded separately under `live/`.

Development attempts remain under `development/`, losslessly gzip-compressed:

- dev1: 0/9 passed, 1 startup error, 8 not run. New window opened on a secondary display;
  adapter correctly refused; setup was then changed to move owned windows to primary.
- dev2: excluded from offline/network-isolation evidence. Wrong `httpx` patch missed the
  installed SDK's `httpx2` client. One pilot call and one diagnostic may have attempted real
  network access with a dummy credential; no real key was loaded and no successful model
  choice/native action resulted. Its original `external_model_requests: 0` is **not verified**;
  the accompanying development-note is authoritative. Replaced with `httpx2.MockTransport`,
  `.invalid` endpoint and disabled environment proxies, plus a DNS/proxy regression.
- dev3: prepared only, no execution.
- dev4: 8/9 passed; final TextEdit stopped on `process_changed`. Replaced stale AppKit
  launch metadata with kernel process birth identity and bundle verification.
- dev5 and dev6: each 0/9 passed, 1 independent-validator error, 8 not run. The goal reached
  the correct Calculator display, but validation incorrectly required exactly one AXWindow;
  auxiliary AX windows existed. Independent validation now binds exact Quartz geometry.
- dev7: 9/9 passed before review. The final review run is a separate 9/9 after fixes.

These development rows are not erased or pooled into a reliability claim. Every executed
attempt confirmed cleanup. Per-run JSON retains planned-but-not-run rows.
`artifact-sha256.json` checksums raw/compressed evidence, including verification logs.

## Verification and review

Backend **5658 passed, 1 skipped, 21 warnings**, with real Chromium enabled;
E2E **18 scenarios, 71 steps** passed. Compressed full logs are `backend.log.gz` and
`e2e.log.gz`. Backend/CLI ruff, changed-file pyright, web lint and `tsc -b`, test tsc,
docs/diff checks passed; dev-server error query was empty. Protocol artifacts unchanged.

Review-and-refactor round 1 fixed owned-process cleanup before window binding and correct
`not_sent` classification for known dispatch-before-send refusal. Regressions ran red then
green. Round 2 was the reviewer's self-check, with no unresolved finding. The coordinator
checked the final diff and verification evidence. Round 3 reviewed the final documents and
evidence: all 34 artifact hashes, frozen current-source hashes, recipe digest, original
development/final-run copies and verification logs matched. No credential/header material
or undisclosed development failure was found; no actionable finding remains in this review
scope. This concluding documentation update was self-checked, not independently reviewed
again. At that review, real-model execution was still awaiting authorization. The later
authorized execution and its failed acceptance result are recorded below.

## Authorized real batch: stopped, acceptance failed

The user's subsequent “继续真实测试” authorized the previously described destination, data,
credential use and limits. The same frozen code/recipe was verified before execution;
no code, prompt, candidate set or quota was tuned during the batch.

[Live result](live/result.json) retains all nine planned cases: **0 passed / 1 failed /
8 not run**. `calculator-ax_press-0` stopped with `backend_error` at its first model call.
There is one admitted/captured SDK call, no successful response and no task-action receipt;
Calculator independently read `0`. Benchmark setup did operate the owned application.
The raw `external_model_requests: 1` counts model-call captures, not independently verified
wire sends or provider receipts. It cannot establish whether the service received the request.

Usage is unknown, so the frozen ledger stopped at `unknown_usage`, retaining a conservative
131,072-token / **$0.002752512** reservation. This is not known usage or actual provider spend.
No diagnostic model call, retry or remaining trial was executed.

Runtime cleanup was `confirmed`; application cleanup was **unconfirmed** because foreground
restoration readback was false. Window position restoration was true; a later read-only PID
check confirmed the owned Calculator process was gone. That later check does not turn the
original foreground-restoration failure into a pass. No other application was activated
as a diagnostic workaround.

[Execution note](live/execution-note.json) records these limits. Capture retains request
parameters but not the original exception, HTTP status or error body, so the available
record does not identify SDK setup, transport, provider or accounting as the root cause.
Foreground restoration likewise needs diagnosis; the single failed readback cannot establish
whether it was timing, focus competition or another issue. Before another real batch,
retain the original failure and add useful error/cleanup evidence, then freeze a new recipe.

Execution and record updates change no source or test logic. Prior code-suite results remain
applicable; this live batch is a failed acceptance experiment, not a green unit-test run.
Execution-record review-and-refactor round 1 verified all 39 artifact hashes, 23 frozen
source hashes, the recipe digest, and byte-for-byte equality of the four original live-run
artifacts. Counts, unknown usage and cleanup limitations match the raw evidence; no
credential/header fields or bearer material were found in the new artifacts. The review
clarified the prior approval block as historical; no unresolved record finding remains.
This concluding documentation edit was self-checked. Docs consistency and diff checks
passed. No implementation-review round is reopened, and real-model acceptance remains
incomplete.

## Second authorized real batch

The user explicitly requested another run. [Second result](live-r2/result.json) uses the
same frozen recipe/source digest, in a separate directory; the first batch is unchanged.
Again **0 passed / 1 failed / 8 not run**: the first Calculator AXPress case stopped at
`backend_error`, with one admitted/captured model call, no successful response and no
task-action receipt. Independent Calculator result remained `0`. Wire sends/provider
receipt count and root cause remain unestablished by the available capture.

This time runtime and application cleanup both confirmed: window position and original
foreground restored, and a subsequent read-only PID check found the owned process gone.
This does not retroactively change the first batch's unconfirmed foreground restoration.

The ledger again stopped at `unknown_usage`, retaining 131,072 tokens / $0.002752512
as the conservative reservation for this batch. Actual provider usage/cost is unknown;
across both batches the retained reservations total $0.005505024, not known spend.
No further trial or diagnostic model request was run. Source, prompts and limits were
unchanged; full code checks are reused from the implementation.

Second-batch record review (round 1, review-and-refactor) found no actionable issue.
All 43 artifact hashes and the four second-batch raw copies were verified, together
with the failed/not-run denominator, unknown-cost reservation and cleanup results.
A credential-pattern scan found no matches in the new raw artifacts. No source or
raw evidence was changed. This closing review note was self-checked; docs consistency
and diff checks passed. Real-model acceptance remains incomplete.


## Error diagnosis and compact native model view

The user asked which model failed and to proceed with diagnosis. It was the Jev
`jev-1.13.0` next-action choice. An offline 401 regression reproduced how unknown-usage
policy checks mask the decision exception behind `backend_error`. The fix records safe
SDK error type, HTTP status and direct cause type before that check; it neither overrides
the policy nor logs raw bodies/headers. Transport and pilot capture regressions also pass.

[Diagnostic run](diagnostic/result.json), revision `s4-ax-2`, froze digest
`9080c26d9ebe913482640b159aa94b297b6af1f441687c2b93d4f9cceb7e2e76`.
It stopped on one HTTP 400 `TypeSafeBadRequestError`, 0/1/8, cleanup confirmed. A separate
[one-request read-only probe](error-probe/result.json), capped at one request/$0.003,
replayed the already authorized synthetic AX payload and captured only its credential-redacted
body (no headers): `{"detail":{"error_type":"max_tokens_exceeded"}}`. Probe script and
request/script hashes are archived. Both calls have unknown usage and retain reservations;
they are not assumed free. The diagnostic freeze's two subsequently changed source files
are preserved byte-for-byte under `diagnostic/source/`; other hashed source files match
this implementation. Earlier two runs did not capture provider detail, so their exact
HTTP causes cannot be established retrospectively.

The [official limits](https://docs.typesafe.ai/models) allow 32k tokens for state plus the
longest question; [Choice permits 255 options](https://docs.typesafe.ai/api). The captured
request had only 48 options (44 actions and four controls). A local cl100k estimate of
22,241 tokens was not a Jev count and did not predict its actual overflow.

The all-AX model view now uses short question-local element references, explicitly declared
element defaults, and reads candidate role/ancestors/current value through target_ref.
All actions/control options remain; action IDs returned by the model, execution references,
input strings and observed values remain unchanged. No top-k filter or predefined button
sequence was introduced. On the recorded first request, JSON size fell 58,575→37,210 bytes;
cl100k estimate fell 22,241→12,980. A 54-control regression verifies candidate completeness,
reference consistency, values/defaults, original-snapshot immutability and size reduction.
DOM/fixture representations remain unchanged.

[Compact live result](compact-live/result.json), revision `s4-ax-3`, froze digest
`90a13ac45106850bd57d22d31f9dba589b15a25eef1fec7010a8b987268e833b`.
It obtained **12 successful model replies and 12 AXPress receipts**, each with changed AX
readback. The first successful call reported 18,866 input tokens. However, Jev selected
`7, 8, 7, 8, 7, 8, 7, 7, 7, 7, 7, 7`; independent Calculator result was
`787,878,777,777`, not the required expression/result. The batch stopped at
`trial_call_limit`, still **0 passed / 1 failed / 8 not run**. TaskResult's generic
`backend_error` here comes from the budget-stop exception, not another failed HTTP call.
This establishes successful real Jev→AXPress execution, not successful multi-step planning,
Quartz/TextEdit acceptance, or an improvement against an uncompressed successful baseline.

[Summary](compact-live/summary.json): known usage 235,443 input / 19,193 output tokens;
frozen-contract estimate $0.009888606, not a provider invoice. All application/position/
foreground cleanup checks passed. Earlier failures and unknown usage remain in their
original files. No further paid prompt tuning was performed. Validation: **5662 backend tests passed / 1 skipped / 21 warnings**, real Chromium enabled;
**18 E2E scenarios / 71 steps** passed. Backend/CLI ruff, all changed-file pyright, web lint/tsc-b,
docs and diff checks passed; dev-server error query was empty. Protocol artifacts unchanged.
Full logs are `diagnostic-backend.log.gz` and `diagnostic-e2e.log.gz`.

Independent review-and-refactor round 1 checked the complete change against `591d6ead`,
including compact references/defaults/progress, error accounting boundaries and archived
failed-task evidence. No actionable code findings remained, so review stopped at round 1.
The reviewer reran the 58 decision/native tests successfully and verified all 60 artifact
hashes plus both 23-file source freezes (using the archived diagnostic sources where needed).
Full-suite results above were reused because implementation `28740280` was unchanged.
Only this closing review record and plan status were updated and self-checked; no paid model
or desktop operation was performed during review. Full native acceptance remains incomplete.
