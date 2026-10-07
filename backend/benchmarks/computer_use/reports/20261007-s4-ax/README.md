# S4-AX native execution evidence

2026-10-07. Implementation and controlled native-app validation passed. Real Jev validation
is **not started**: automatic approval rejected external AX data transmission before the
live process was created. S4-AX acceptance remains incomplete.

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
  This is application UI data sent to an external service; specific approval is pending.
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
live status: no started marker, no loaded live credential, no requests. There is no live
result to interpret as either a pass or a model failure.

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
again. Real-model acceptance remains blocked as stated above; this report authorizes no
new real-model run.
