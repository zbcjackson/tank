> 2026-10-07：当前可执行输入已迁移到单一目标契约（schema_version=2），使用新的
> goal-contract revision；下文旧批次数字/协议为历史记录，不能用当前输入原样复现。
> 已归档 reports 未改，新批次须重新冻结请求、候选与预算后按授权执行。

# S3 bounded strategy pilot — 2026-10-04

Status: implementation/verification in progress; no paid model outcomes observed.

The question is whether adding Jev improves a bounded task strategy, not whether Jev
is generally more intelligent. H3 uses the host's rules then F; J3 uses identical rules,
observations/candidates and F, with Jev attempted before F on eligible decisions.
Only a valid non-action Jev reply permits F. Invalid replies, unknown usage, cancellation,
revocation, budget and audit stops cannot be treated as ordinary abstention.

## Tasks and ground truth

`cases.json` contains eight authored, workflow-inspired local pages. These are not
independently collected production traces. A structured goal is supplied to both arms;
goal construction and broader planning are outside this pilot's measured scope.

- profile-name: exact named input and Save; fill Ada and save. Rules only, two actions.
- compact-view: exact Compact label; switch view. Rules only, one action.
- appearance-preferences: open display/appearance settings, not login/security.
- save-draft: save progress without publishing.
- marketing-preferences: disable marketing, preserve security alerts, then apply.
  One semantic choice followed by an exact rule action verifies return to host routing.
- view-receipt: show the receipt, not request a refund. No real financial service exists.
- missing-record-name: names are absent; task explicitly forbids opening unknown records
  to investigate and requests more information instead. Any valid non-action is accepted.
- unavailable-pdf: no offered PDF action; task explicitly forbids trying other controls
  to search for it. Any valid non-action is accepted.

Expected outcomes/rationales are evaluator data, never model inputs. Models receive the
same production semantic question, with only provider-specific request/output wrapping.
Expected action UUIDs are never supplied; live DOM IDs are generated at observation.
Inputs and goals contain the actual task constraints; there are no hidden contradictory
identity rules. Both arms use the same postcondition and independent page-event checks.

Six tasks are completable and two require a legitimate exit; report them separately.
A click receipt alone is not completion. Page state is a local UI outcome, not backend
persistence. Semantic refusal on a completable task is a failure, not a free speed gain.
Wrong clicks count even when they happen to achieve an expected display value.

## Frozen design

Eight tasks × three repetitions × two arms = 48 planned trials (24 per arm).
Order alternates by task plus repetition: 12 pairs start with each arm globally;
each task's three repetitions have a 2:1 or 1:2 first-position split. Repetitions of a
shared template are not independent application samples. No threshold tuning on results.

Each case has at most one semantic decision: H3 permits one F request; J3 permits
one Jev plus one F. Rule tasks make zero calls. Maximum batch count is **54 requests**
(18 Jev + up to 36 F), with **$0.25** shared conservative reservation. Models reuse
historical frozen Jev and Qwen versions/prices/ceilings; cost is an estimate, not invoice
pricing. F requests temperature 0, max_tokens 128 and enable_thinking=false. No implicit
retry, extra warmup or fallback to a different vendor. All calls share the trial context
and batch accounting. Keys remain host-owned.

Each trial starts an isolated Chromium page and fresh lazy task-owned clients. Time
starts before factory/context assembly and ends after model/browser cleanup. All model
and fallback time is included; this is not pure inference latency. The localhost server
is shared batch infrastructure outside trial timing. Fresh-browser overhead and hosted
provider geography/load are real limitations of this short-task pilot.

## Measures and interpretation

Report all planned rows, completed-goal counts, correct exits, unexpected actions,
model attempts by provider, rule/eligible steps, fallback count, total wall time and
known cost. Finished paired rows retain H/J times, differences, costs and outcomes;
failed semantic trials are included, never only successful paths. Incomplete batches
retain denominators and cannot produce an adoption conclusion. Capture counts describe
request attempts; audit/spend records distinguish sent, unsent and unknown on failures.

Before seeing paid outcomes, the conservative descriptive decision rule is fixed:
both arms must satisfy all 24 predeclared outcomes, neither may have unexpected actions,
J3 must avoid at least one F call, and either total time or contract-estimated cost must
improve by at least 10% without regression in the other. Even meeting this rule yields
only a limited pilot signal, not production adoption. A negative result is a valid S3
outcome; no thresholds, tasks or labels are adjusted to obtain a Jev win.

Operational failure (including malformed model response, unknown usage, cancellation,
audit/budget or unconfirmed cleanup) stops the batch. Known semantic errors on fully
observed disposable fixtures are recorded and the next independent case may run. This
never retries an unresolved action, weakens host guards or authorizes such continuation
in a real business application. Existing execution artifacts forbid rerun.

## Execution

From backend, preparation is offline and reads no credentials:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_strategy --output <new-directory>
```

After batch-specific approval of the final source/input digest:

```bash
uv run --no-sync python -m benchmarks.computer_use.s3_strategy --live \
  --approved-sha256 <approved-digest> --output <prepared-directory>
```

The live CLI validates the recipe before reading `core/.env`, uses TYPESAFE_API_KEY
and the computer_use profile's F credential, and rejects profile model/endpoint drift.
No personal browser, real account, native AX or unbounded planner is involved.
