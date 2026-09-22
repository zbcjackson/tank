# M5 17-trial proposal

> 状态：2026-09-22，离线一致性检查通过；live_ready=false，未执行模型/桌面对照。

`proposal.json` fixes the previously proposed five pilot trials and twelve core
trials, phase/order, Calculator task, seven runtime configs and all proposed limits.
It saves 340 file hashes relative to the backend root. `preflight.json` records
consistency checks and unresolved execution blockers; neither file grants live
permission or certifies provider prices. The JSON proposal itself is reviewable
versioned input, not a signed authorization or executable run_batch configuration.

Pilot order: A-control → B-protocol-only → A → B-host-only → B-combined.
Core rounds: A/B-combined/C/D; B-combined/C/D/A; C/D/A/B-combined.
Core must await pilot acceptance; no phase transition is implemented here.

Totals: 17 trials, 272 planner + 90 locator requests (45 Max), 362 HTTP,
5,100,000 tokens, 2,040 task seconds, proposed 8 USD. Each trial is limited to
120 task seconds, 15 top-level tools and 300,000 shared tokens. These are proposed
limits, not observed usage; setup/validation/cleanup time is separate.

The real offline ledger refuses the recorded 999,808-token first reservation.
Zero prices isolate token admission only. A usable input bound, account prices,
independent scoring, real environment/physical cleanup, pilot acceptance and
live budget/endpoint/image-scope approval remain unresolved.

Use the [benchmark guide](../../../README.md#offline-17-trial-proposal-preflight)
for generation/recheck commands. Recheck reads saved inputs without refreshing
hashes or constructing a driver. Older freeze directories are unchanged.
