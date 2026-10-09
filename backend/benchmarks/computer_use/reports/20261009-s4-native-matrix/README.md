# Native matrix with history, compact view and focus

Date: 2026-10-09. Status: fake HTTP 9/9 passed on real applications; the live
real-model batch is frozen and awaits explicit authorization (0 external calls).

## Recipe and boundaries

Runner `benchmarks/computer_use/s4_ax.py`, revision `s4-ax-focus-1`, frozen digest
`5da381139cfa1f4d0653206bec2a7a7ea668977e2d1cdf063c3de80ea1a2ef8f`. The identical
recipe is in `fake/freeze.json` and `live/freeze.json` (file SHA-256
`20e1e4d6dad4565cf42400ccdae77cf00e926da396839639843a4df5b7408e79`). It pins the
current production selector/Advisor/model-view sources, including semantic
history, compact candidates and bounded focus, plus the continue policy below.

Nine cases, unchanged from the [previous pilot](../20261008-s4-native-advisor/README.md):
Calculator `7×8` via AXPress ×3 and Quartz ×3, and TextEdit body fill ×3, with one
moved window per group. Jev `jev-1.13.0` at `https://api.typesafe.ai/v1/systemone`
and text Advisor `qwen3.7-flash-2026-07-15` at
`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` (2048-token
output cap, thinking disabled) share 78 SDK-call admissions and a $0.25 ceiling
at frozen conservative prices; 120 seconds and at most 12 (Calculator) or 2
(TextEdit) calls per case, at most four Advisor calls. Payloads contain owned
Calculator/TextEdit AX text and geometry, goals, candidates and verified history;
no screenshots. Credentials are not in the recipe.

**Stop policy (changed, user-selected option B):** a case that fails in a known,
settled state — finished with independent readback, result not `unknown`, reason
not `backend_error`/`cancelled`, no `unknown` receipt, plugin and application
cleanup confirmed, no ledger stop — stays in the denominator and the batch moves
on to the next fresh process. Errors, unknown effects/receipts/usage, cancellation
or unconfirmed cleanup stop the batch and keep remaining rows `not_run`. A per-case
call cap no longer latches the batch ledger. Implemented in `3c2c9dd2`, refactor
`b3642f30`, review fix `049ee914`.

## Real applications, fake HTTP

**9/9 passed** in 32.6 seconds of case time (sum of row `elapsed_ms`). Independent AX reads found expression `7×8` and
result `56` for all six Calculator cases, and the exact Unicode/newline body for all
three TextEdit cases; every result was `completed / goal_verified`. Window moves ran
in the three `-1` cases. All process, position and foreground cleanups confirmed.
33 mock HTTP requests (5 per Calculator case, 1 per TextEdit case), 0 external model
requests, no ledger stop. The deterministic fake responses verify wiring and native
execution under the frozen sources, not real-model planning.

Artifacts: `fake/result.json.gz`
(`3489aa763ab1ce4723e0bb08429f88709d2bbb7d1ebaea26fbe0c1d91435a81e`),
`fake/spend.jsonl.gz`
(`2918e9afe1e3dc29f62abdd000b859e975caef4e7c4f4a4abdf78014609fd34d`),
`fake/started.json`. Run log: `/tmp/tank-s4-native-matrix-fake.log`.

## Live gate

Not run. After explicit confirmation of the data, both destinations, 78 calls and
the $0.25 ceiling, and with the desktop left idle, the unchanged recipe runs once:

```bash
cd backend
caffeinate -is uv run python -m benchmarks.computer_use.s4_ax \
  --output benchmarks/computer_use/reports/20261009-s4-native-matrix/live \
  --run live --approved-sha256 5da381139cfa1f4d0653206bec2a7a7ea668977e2d1cdf063c3de80ea1a2ef8f
```

## Tests and verification

New tests in `plugins/agent-computer-use/tests/test_native.py`: a table of settled
versus unsettled rows for the continue predicate, and a two-case batch where a
call-capped first case fails without latching the ledger and the second completes.
`test_native.py` 73 passed. Full backend **5767 passed / 1 skipped / 21 warnings**
(370.56 s, `TANK_REQUIRE_CHROMIUM=1`); E2E **18 scenarios / 71 steps**. pyright on
changed files 0 errors; ruff (backend core, plugins, benchmarks, CLI), web lint and
`tsc -b --noEmit`, docs and protocol checks passed; dev-server error query empty.
Logs: `/tmp/tank-s4-continue-backend.log`, `/tmp/tank-s4-continue-e2e.log`.
Independent review-and-refactor round 1 against `945e9505` found no gaps in the
predicate (timeouts with an in-flight action become `unknown`; unsent model errors
release reservations; sent ones with unknown usage latch the ledger) and corrected
one test row's reason to the real `model_error`; no further findings.
