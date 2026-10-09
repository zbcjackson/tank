# Frozen native decision diagnostic

Date: 2026-10-09. Status: executor verified and reviewed; live execution blocked
before process creation by automatic approval review. **0 external calls, 0 desktop
operations, all 48 planned rows not run.** This is not a failed model response.

## Frozen recipe

Implementation: `8a10ab28`. Revision `s4-frozen-diagnostic-1`, digest
`e8d3b1c7ef987c2366c86b144d787667641a6cde30e6ac30f71596eb3958eab0`.
The exact recipe is [live/freeze.json](live/freeze.json); its file SHA-256 is
`b2c1e475f2b769e277ee70231a5c8fd4818794900cb479c1ca7b8dc1de1a69f6`.
It pins 33 source files and installed SDK versions. The archived Calculator
source is the unchanged [prior live result](../20261008-s4-native-advisor/live/result.json.gz),
SHA-256 `1cd21575708832567862fb2096f96109ae06067a30e6f6a36582ecedec25d278`.

Four previously observed states, retaining all 44 actions:

- `7`: nominate Multiply; source first AXPress task, call 2.
- `7×`: nominate `8`; source first AXPress task, call 7.
- `7×8`: nominate Equals; source first AXPress task, call 8.
- `787`: nominate Clear, with Delete separately scored as a repair alternative;
  source failed moved-window AXPress task, call 4. This was an Advisor observation;
  the archived Jev question is explicitly derived using that batch's selector
  instructions, not claimed to be an actual historical Jev request.

Each state has three repetitions of each of four arms: explicit-button grounding,
archived whole-goal input, current compact view with verified semantic history,
and production Advisor candidate selection or validated focus followed by Jev.
Ordering rotates; fresh tasks and lazy clients are used per row, without warmups
or SDK retries. Prior receipts establish the focus's real historical action
offset. No desktop observer or executor is connected, and both UI quotas are zero.

The grounding arm changes the task to the nominated button, so it probes locating
capability rather than same-task planning efficiency. History comes only from
earlier verified action/readback pairs. Preferred labels are not supplied as
answers to the whole-goal arms. Current-versus-archived changes several presentation
factors together; this comparison cannot isolate which individual change matters.
The Advisor is free to select a candidate instead of focus. A focus uses the same
frozen snapshot here, not the production loop's fresh read. Preferred selections
do not establish UI effects, task completion, stable planning or G3 resumption.

## Requested live scope and approval stop

The frozen batch would use the existing credential for each destination:

- Jev `jev-1.13.0`: `https://api.typesafe.ai/v1/systemone`, TYPESAFE_API_KEY.
- Advisor `qwen3.7-flash-2026-07-15`:
  `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`, BAILIAN_API_KEY.
  Temperature 0, thinking disabled, output cap 2048 tokens.

Payloads contain the archived owned Calculator AX text/geometry, task goal,
candidate actions and verified action history, with the arm-specific projection.
No screenshots, current desktop reads or other application data are requested.
Credentials are not present in the recipe. Shared ceilings: **60 SDK calls and
$0.25 under frozen conservative prices**, at most 1/2 calls and 60 seconds per
row. The monetary figure is an estimate, not an invoice guarantee. Known semantic
misses remain in the denominator; provider/usage/budget/audit/capture/cancellation/
cleanup failures stop the batch. SDK counts do not independently count wire requests.

Automatic approval review rejected the execution command because it considered
the current instruction to continue insufficiently explicit for exporting these
AX states, goals, candidates and history to both destinations. The live process
was not created; only offline preparation ran. No retry, indirect execution or
substitute endpoint followed. There is no `started.json`, live model result or
spend journal for this batch. [preparation.json](preparation.json) records this
state separately, without fabricating model results.

After explicit confirmation of this scope, the unchanged recipe can be run once:

```bash
cd backend
caffeinate -is uv run python -m benchmarks.computer_use.s4_replay \
  --output benchmarks/computer_use/reports/20261009-s4-decision-diagnostic/live \
  --run --approved-sha256 e8d3b1c7ef987c2366c86b144d787667641a6cde30e6ac30f71596eb3958eab0
```

## Tests and verification

15 new offline/fake-HTTP tests passed, including production SDK paths for all
arms, candidate and focus advice, historical offset, existing-output refusal,
mid-batch freeze tampering, semantic misses, unknown usage, provider/budget/
capture/cleanup errors and cancellation during cleanup. These test model I/O
and host boundaries; they are not measurements of real model competence.

Full backend: **5753 passed / 1 skipped / 21 warnings**, 386.80 seconds with
`TANK_REQUIRE_CHROMIUM=1`. E2E: **18 scenarios / 71 steps**, 94.88 seconds.
Changed-file pyright, backend/CLI ruff, web lint and `tsc -b --noEmit`, docs
consistency and diff checks passed. Frontend/backend dev error queries were
empty; no protocol artifacts changed. Logs: `/tmp/tank-s4-replay-targeted.log`,
`/tmp/tank-s4-replay-backend.log`, `/tmp/tank-s4-replay-e2e.log`.

Independent review-and-refactor round 1 against `e5fee950` covered all five
implementation/documentation files, found no actionable issues and made no
changes. The reviewer independently reran 15 tests (30.84 seconds), docs/diff
checks and inspected full-suite logs. Real calls remain pending. S4 still needs
native acceptance, G3 recovery and the selected goal-generation/visual capabilities;
this diagnostic neither closes S4 nor constitutes S5 system evaluation.

Round 2 reviewed only the frozen recipe and final preparation records, found no
actionable issues and made no changes. It independently verified the canonical
digest, file/source/archive hashes, 48-row schedule, 44 candidates per state,
absence of live artifacts and credential fields, and docs/diff checks. The
coordinator inspected the evidence and final diff; no source changes or new calls
were made after the implementation review.
