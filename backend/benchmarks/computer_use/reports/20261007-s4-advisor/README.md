# S4-R4 text Advisor: offline acceptance

2026-10-07. The first text-Advisor slice is implemented and offline tests pass. No new paid
model call or personal desktop operation ran. This does not close S4-AX or prove that a real
Advisor solves the previous Calculator failure. Independent review completed on 2026-10-08.

## Behavior and evidence

- `advisor: llm` opts into the existing core task text model. One strict structured reply
  can choose a current candidate, supplement declared missing generated inputs, request
  observation, request user input, or report unable. The host owns dispatch and verification.
- Three locally verified actions without new declared goal evidence trigger planning review
  before another ordinary selector call. Genuine new completion/outcome conditions or
  exactly filled bound inputs reset the progress counter once per distinct evidence item.
  This is a bounded review heuristic, not a semantic proof that an action is wrong.
- Advice permits a bounded new interval but never resets the task budget or four-call cap.
  Action-induced repeated states can request repair; unchanged reobservation stops. Unknown
  effects do not cause another planning/dispatch attempt. Missing user values are not guessed.
- `prior-trace-analysis.json` summarizes the unchanged prior live record. Multiply and Equals
  were offered throughout all twelve choices; the expression stayed empty as digits grew.
  Analysis used saved evidence only. The original real-model failure remains in its report.
- Tests use real core SDKs with fake external HTTP, native OS fixtures, and real isolated
  Chromium/Runner across two layouts and an intermediate page. Advisor→Jev recovery verifies
  the server-side name Ada and unchanged email. Native recovery verifies the same binding,
  accounting and stop boundaries. Scripted HTTP replies prove wiring, not model capability.
- Current smoke/DOM/followup/strategy executors now recognize explicit control stop reasons;
  their prospective goal revisions are 3. Zero actions, independent readback, valid control
  classification and cleanup checks are retained. Archived S3 reports are not rescored.

## Verification

Backend: **5690 passed / 1 skipped / 21 warnings**, real Chromium required. E2E:
**18 scenarios / 71 steps passed**; the managed Chromium step now includes all three new
Advisor cases (19 selected tests). Backend/CLI ruff, all changed-file pyright, web lint and
`tsc -b`, test tsc, docs consistency and diff checks passed. Both backend and frontend dev
pane error queries were empty. Protocol artifacts unchanged, so sync is inapplicable.

Initial full pytest exposed five old benchmark reason checks; after migration, 21 targeted
benchmark cases and the whole backend suite passed. Initial logs are retained. Two E2E runs
hit timing failures; read-only `pmset` logs showed repeated macOS maintenance sleeps lasting
7–9 minutes during the runs. The single failed page-opening scenario passed independently.
The final entire E2E suite passed in 85 seconds under temporary `caffeinate -is pnpm test`;
no system preference, timeout or assertion was relaxed. The sleep assertion ended with the
command. Compressed logs and their hashes are archived here.

## Remaining scope

This slice supports text and one action proposal/input supplement, not arbitrary subgoal
patching, visual advice, natural-language GoalContract generation, automatic application/
channel discovery, or same-process resume. A fresh frozen two-model native pilot is still
needed to test actual planning quality and the Calculator/Quartz/TextEdit acceptance cases.


## Independent review

Review-and-refactor round 1 covered `ea4246ab` through the full task diff. No confirmed
correctness/design finding remained, so review stopped without a second round. The reviewer
independently ran 271 ladder/Jev/native/plugin tests, all passing, and inspected the complete
5690-test backend and 18-scenario E2E logs. No source, original evidence or execution state
was changed during review. The coordinator checked the final diff and evidence; this closing
record was self-checked. An initial commit attempt failed at the existing 1Password signing
agent; a post-review retry with the unchanged signing configuration failed with the same
error. On 2026-10-08, the user requested another attempt and implementation commit
`3603c5d8` succeeded with the original signing configuration. Signing was never disabled
to bypass the failure.
