# M5 corrected-contract single-pilot preparation

> 状态：2026-09-24，离线材料准备完成，等待新的单轮截图外发授权；真实请求为 0。

The proposed next run repeats one A-control trial after correcting its tool
instructions. Endpoint: https://dashscope.aliyuncs.com/compatible-mode/v1;
model: qwen3.7-flash-2026-07-15. Scope: controlled main-display Calculator,
black background and menu bar, including initial and feedback screenshots.
Limits: 1 trial, at most 16 HTTP requests, 120 agent seconds and 15 tool steps;
zero retries, token/cost record-only, automatic input cleanup enabled, stop on
insufficient balance, no automatic follow-on. Cleanup can extend return time
while already-started native work finishes.

review.json binds the proposed scope and refreshed runtime/proposal.
request-diff.json records the offline comparison: A/C/D unchanged; the same
instruction/description correction applies to all four integrated variants.
Models, structural schemas, images and generation fields did not change.
This repeat is diagnostic; it does not retroactively change either failed pilot.

launcher.py.txt is the previously executed controlled-desktop harness with only
the new freeze/proposal and fresh output paths substituted. Syntax compilation
passed. Default execution is preview-only; --live requires explicit user consent,
checks the frozen proposal, prepares the controlled desktop, then waits for a go
file after a fresh visual review before loading credentials/sending requests.
Outputs must be new directories:
/tmp/tank-m5-a-control-20260924-contract-preview and
/tmp/tank-m5-a-control-20260924-contract-live.

The reference preview is ../20260924-m5-a-control-pilot/live/initial.png. It is
historical scope evidence, not a new capture: this preparation performed no
physical desktop operation. A fresh screenshot must be checked immediately
before the next live run. The previous one-trial authorization was consumed by
the archived 20260924 pilot; it does not authorize this new trial.

Invocation from backend after the appropriate review:
uv run --no-sync python benchmarks/computer_use/reports/20260924-m5-contract-ready/launcher.py.txt
Add --live only for the newly authorized single trial. The launcher restores its
controlled windows, clipboard, cursor and hidden apps afterward. Scope guards
check visible apps/background presence; they are not a general privacy filter.
The execution API remains fixed to A-control and cannot start the remaining batch.

Validation: backend **5010 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, development-server log, docs and protocol
checks passed. No production Python changed; changed-file pyright N/A.
