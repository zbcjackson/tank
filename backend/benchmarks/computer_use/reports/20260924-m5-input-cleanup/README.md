# M5 automatic input cleanup

> 状态：2026-09-24，清理接线、确定性回归与四类本机输入释放验证完成；无模型请求。

Built-in macOS benchmarks can explicitly enable `input_cleanup=True` through
SubAgentDriver/create or run_batch. The setting is recorded in runtime metadata
and the batch plan. It defaults off; default/SDK/engine cleanup is not relabelled.
The factory rejects this option for non-macOS or plugin-driven agents.

Runner executes the hook under its desktop lock. Preflight refuses a desktop
with already-held keys/buttons, without releasing those user inputs. On normal
exit, exception, timeout, step stop or cancellation, it first closes the producer
and joins in-flight native operations, then releases currently-held keys/buttons
and reads their physical state after event delivery. Only explicit success yields
`cleanup=confirmed`. Residual inputs or cleanup errors yield unconfirmed and
quarantine the same-process desktop; batch's existing stop gate remains intact.
External cancellation still propagates after cleanup, with evidence in the trace.

Native macOS tool awaits now shield and join their worker even on repeated
cancellation. Frame and grounding cancellation also retain ownership while
joining. A timeout stops new actions but can exceed its nominal wall time while
an already-running native operation finishes. A permanently stuck native call
cannot be killed safely here; no instantaneous/hard process termination claim.

Native evidence uses the real driver, Runner lock, native worker and cleanup,
with a deterministic producer instead of an LLM. Four cases physically press
Command (55) and the left mouse button over a controlled black background:
normal completion, injected error, 1-second timeout during a 1.5-second native
operation, and repeated external cancellation during that operation. Every case
records keys_before=[55], buttons_before=[0], empty keys/buttons afterwards,
and confirms the native operation finished. No model client/request or screenshot
capture was used. The external harness also restored cursor, clipboard and apps.

Scope: confirmed means native work quiesced and keys/buttons released. The hook
keeps application output intact for the validator. Application teardown, clipboard,
cursor and environment restoration remain the trial/harness responsibility.
The operator must keep this controlled desktop idle: this is not cross-process
ownership, general pause/resume, or the entire M6 physical acceptance matrix.
Old failed pilot and frozen inputs remain immutable; next refresh source pins
and the executable phase schedule before resuming paid trials.

Regression coverage includes release success/stuck state, refusing pre-existing
held input, repeated cancellation joining, real Runner/driver exit paths, cleanup
exceptions/quarantine and serial batch option forwarding. One focused run failed
because the sandbox denied a local HTTP listener; the escalated rerun exposed a
new fixture expectation missing the added option, which was corrected. Evidence
of actual model quality is still limited to the earlier failed pilot.

Validation: backend **4999 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, pyright on all 11 changed Python files,
running backend log, docs and protocol synchronization passed. Code: `7cfcf9c`.
