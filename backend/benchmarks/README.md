# Tank Benchmarks

本地基准套件：量化子代理完成真实任务的能力，用副作用判定成败（绝不比对像素）。

## 测什么 / 不测什么

**测**：一个子代理（定义提示词 × 模型 profile × 工具集）在真实桌面/文件系统上完成任务的
成功率、工具调用数、完成的动作数、模型轮次、耗时、token、截图数。
首个套件 `computer_use`（桌面 GUI 任务）。

macOS 截图到点击的转换、测试范围、真实校准、跨模型与输出协议实验、
DeepSeek 预算复测及未排除项统一见
[Computer use 验证结论](../../docs/design/computer-use.md)。

**不测**（刻意绕开，是 A/B 对比中的恒定量）：WorkerSupervisor 调度/持久化/回注、审批 UI、
ASR/TTS/语音链路。驱动器直连 `AgentRunner.run_agent`（见 `tank_backend/benchmarks/driver.py`）。

## 用法

三种典型跑法（命令都从 `backend/core` 执行）：

**1. 单任务调试**（几分钟，定位环境/权限问题）：

```bash
uv run python -m tank_backend.benchmarks \
    --suite ../benchmarks/computer_use \
    --tasks calc-open --trials 1 --label debug
```

`--tasks` 是任务 id 的正则（如 `--tasks "form|typing"` 跑多任务）。只用于诊断，
**不要**当对比报告。

**2. 全量冒烟**（约 15–20 分钟，跑前 1 个 trial 验证环境与链路）：

```bash
uv run python -m tank_backend.benchmarks \
    --suite ../benchmarks/computer_use \
    --agent computer_use --trials 1 --label smoke-macos
```

**3. 正式 baseline**（约 1 小时，不需要人守着，放着别碰键鼠即可）：

```bash
uv run python -m tank_backend.benchmarks \
    --suite ../benchmarks/computer_use \
    --agent computer_use --trials 3 --label baseline-macos
```

通用说明：

- 报告与逐 trial trace（JSONL + 每步截图）落在 `benchmarks/<suite>/reports/<时间戳>-<label>/`
- **绝不在开发机裸跑**（会动真实鼠标键盘）：Linux 在 GUI VM，macOS 在真机/独立环境
- 跑批期间不动键鼠；环境钉死与安全清单见任务套件目录下 suite.yaml 注释
  （单显示器、专用账户、关闭敏感 App——agent 会真实操控键鼠且截图上云）
- 为什么这么慢：串行「截图→视觉 LLM→动作」× 每任务多步 × 多 trial，失败 trial 烧满
  超时；并行化/降分辨率/batch 属于被测对象，中途改会让前后数据不可比

## 指标（含 LLM 延迟）

每个 trial 记录：成败（副作用判定）、步数、总耗时、token、截图数，以及 **LLM 延迟**——
按**模型往返（一次 API 调用）**计的 ttft（首 token 延迟）与总时长（一次 `chat_stream`
内部跑整个工具循环，含 N 次往返，以 USAGE 边界切分；超时被取消的在途往返也计入）。
三个地方可看：

- **控制台**：每次调用实时打印 `LLM call N: ttft=X.XXs total=Y.YYs`；每 trial 结束打印
  `llm=Ncalls ttft=…/call=…/total=…`（换 provider 前后直接对比这两行）
- **trace.jsonl**：每条 `llm_call` 事件（call/ttft_s/total_s）；`driver_done` 汇总
- **report.md / report.json**：主表（成功率/步数/耗时/token）+ "LLM latency (per call)"
  表（每任务调用次数中位、ttft 中位、单调用时长中位、LLM 总时长）+ 套件级
  `API calls total / mean s per call / median ttft / LLM total`——耗时与 LLM 延迟
  都是正式对比指标

## 结构与演进

```
benchmarks/
├── README.md                  ← 本文件
└── computer_use/              ← 套件 = suite.yaml + tasks/*.yaml + assets/ + reports/
    ├── suite.yaml             默认 agent / trials / 端口
    ├── tasks/*.yaml           每任务：instruction + setup + validator + teardown
    └── assets/                零外网页面（本地 http server 服务，副作用回传 capture 文件）
```

框架代码在 `backend/core/src/tank_backend/benchmarks/`（task / shell / pageserver /
trace / driver / runner / report / __main__），套件无关。

**演进路径**（加东西不改机制）：

1. 更多子代理套件：新增 `benchmarks/<name>/`（suite.yaml + tasks），`--agent <definition>` 换被测对象
2. 测调度/持久化：新增 driver（实现 `BenchmarkDriver` 协议，如 SupervisorDriver）
3. 测整 Tank（语音→回复全链路）：新增 driver 驱动 WS 客户端 + 新套件任务集
4. 更多 validator kind：目前只有 `shell`（只查副作用原则在此强制）

## 可靠性规则（沿用方案 §A17 八条）

确定性 setup/teardown；validator 只查副作用；零外网；每任务多 trial 报成功率+置信区间；
环境钉死；全量 trace；硬超时+步数上限；任务先人工金标跑一次、validator 过了才入套。

## SDK path and scoring revision

Select `n2_sdk` explicitly to measure the new plugin through the same Runner.
Its observer archives screenshots and every logical API response (including
compaction/retries) without patching DesktopExecutor. Reports separate streamed
TTFT from non-streaming RTT and record incomplete endings/unknown usage/cleanup.
Unconfirmed cleanup skips validation/teardown and stops the suite with its trace
preserved; verify and reset the desktop before continuing.

Scoring revision `trial-token-v2` uses a fresh capture file and unpredictable URL
prefix per trial. Asset pages submit relative to that URL; closed/stale tokens
return 410. Instruction `${BENCH_ASSETS_URL}` is expanded by the runner. Validators
see only their trial's BENCH_CAPTURE. Process-only calculator/settings validators
are smoke tasks, excluded from the strict score; file validators verify complete
contents/copies. Historical reports cannot be compared as equivalent scoring.
Reuse existing computer_use and n2 reports as historical references. New claims
of improvement require comparable tasks and scoring; rerun the affected comparison
only when existing data cannot support that claim. A full N2 rerun is not a
prerequisite for the current
[effectiveness improvement plan](../../docs/plans/active/computer-use-adaptation-and-grounding.md).

Scoring revision `trial-token-gui-v3` retains that isolation and also
checks execution paths. The computer_use suite defaults to `gui_only: true`;
strict trials that attempt tools other than desktop actions, screenshot,
launch_app or computer_batch fail even if their side-effect validator passes.
The two smoke tasks opt out. Agents receive the GUI requirement in the task;
shell/file tools remain available to normal Tank tasks. This is a scoring check,
not a shell sandbox: attempted non-GUI calls are recorded in result.json.

`steps` counts tool calls; `primitives` counts confirmed completed GUI members
(including explicit wait/screenshot, excluding automatic post-batch captures).
Failed/skipped members are excluded. Actions cancelled without a result cannot
be confirmed. `model_turns` counts actor model rounds; SDK compaction/retry API
calls are separately included in `llm_calls`. Reports show the effective per-task
tool-call limit (currently 15), independently of the SDK's model-turn limit 100.
Non-streaming TTFT is null in JSON and N/A in Markdown; use RTT for those calls.
Run metadata includes the model/config, prompt hash, task hash, git revision and
effective limits. Old scores and latency fields must not be treated as equivalent.

Current scoring revision `trial-token-gui-calc-v4` strengthens macOS calc-open:
setup opens Calculator, clears restored state and reads back zero; validation
requires the foreground, non-minimized Calculator display to contain expression
`7×8` and result `56`. It reads the `StandardResultView` / `StandardInputView`
Accessibility identifiers locally, never asks an LLM to judge screenshots.
Unsupported UI structure, missing permission or unreadable state fails closed.
macOS calc-open is now strict and GUI-only; Linux calc-open remains smoke.
Task YAML supports `scoring_macos` / `gui_only_macos` platform overrides.

This checks Calculator's accessibility display, not screenshot pixels or all
possible overlays. A reset is required before every trial to avoid accepting
a result restored from the previous run. The task instruction still asks the
agent to take a screenshot, but that screenshot requirement is not scored.


Calculator `calc-evidence-v1` adds a separate `assessment` to trial results and
report outcomes while keeping the existing strict score and its denominator.
It records `business`, `mouse_only`, `strict_expression`, `pixels` and the last
screenshot hash/capture/HTTP serialization timestamps. Null business/mouse
values mean insufficient current-trial evidence; `pixels: unknown` requires
independent manual verification. A pasted expression can pass business while
failing historical strict, but pasting the answer alone cannot pass business.
GUI-only violations invalidate business and mouse evidence too. Do not merge
these tracks or rewrite historical reports. The validator reads only the
current trace segment after the last `trial_start`, using `BENCH_TRIAL_DIR`
provided by the runner; setup emits a verified reset record before input.


### Split grounding measurement (M5 preparation)

Built-in agent definitions with `grounding` now work through `SubAgentDriver`:
profile-created planner/locator clients share one benchmark counter and actual
SDK request image-hash tracing. Initial observations and post-action feedback
are archived through the task observer. Locator failures or missing usage retain
an unknown-call count; non-streaming calls have no TTFT, and nested locator RTT
is subtracted from planner intervals. Planner intervals can still include local
tool overhead, so these are not pure HTTP latency measurements.

Scoring revision `trial-token-gui-grounding-v5` allows `locate` as GUI observation
without counting it as an input primitive, and preserves Runner terminal errors.
It does not rescore old reports. Integrated B adaptation and split/integrated batch primitive reporting are now
implemented; raw locator failure attribution and paired A/B/C/D execution still
require work before the M5 effect comparison. No new model results are implied.


For B experiments, use a separate agent definition with `grounding.mode: integrated`,
`protocol: legacy|point|pixels|bbox`, and `host_restore: true|false`. Keep the model,
base prompt, toolset, status/sentinel settings and detail fixed across paired groups.
The same-framework legacy/no-restoration A-control separates frame/feedback/tool
wrapping changes from the two-factor comparison; original A remains unchanged.
See [integrated configuration](../../docs/design/computer-use.md#一体适配实验m5-b).
These are executable configuration options, not a frozen or authorized live batch.

### Raw HTTP response evidence (M5)

Built-in `SubAgentDriver.create` clients now archive planner and locator responses
under each trial's `responses/<request_id>.bin`. The `http_request` event records
the attempt ID, model, stream flag and input image hashes; `http_response` links
the body file, byte count, SHA-256, HTTP status and body read state. SDK parsing
errors, non-2xx bodies and partial streams retain their received bytes. Request
headers and complete response headers are not exported; only response content
type/encoding accompany the body. Plugin-owned transports remain outside this hook.

Capture tees chunks as the consumer reads them, without prefetching the response.
Local archive writes add overhead, so this is still not pure provider latency.
`body_representation=httpx_raw` means bytes before HTTPX content decoding (apply
`content_encoding` when reading compressed files); `httpx_decoded` identifies an
already-consumed transport body, as commonly returned by in-memory test transports.
Neither representation rewrites JSON, tool arguments or SSE content.

Body states are `complete`, `read_error`, `cancelled`, `closed_early`, `trace_closed`
and `no_response`. `complete` means HTTP body iteration finished, not valid JSON,
complete model output, known usage or task success. SDK early closure may leave
`closed_early` even when a valid final model message was received. `no_response`
means no response hook completed before trace closure; it does not prove zero cost
or classify the cause of a pre-header failure. Error messages are not copied into
transport metadata; the exception type is retained for stream read errors.

Responses remain bound to the requesting trace even if another trial has started.
Closing a trace finalizes partial archives and missing-response entries; late bytes
or headers cannot mutate the closed trial or write into the next one. This is trace
lifecycle handling, not evidence that model work or physical input has stopped.
Semantic failure attribution, paired scheduling, token/cost reservations and
verified desktop cleanup remain prerequisites for live M5 runs. Historical request
freezes remain unchanged; freeze the final executor revision again before live work.

### Split-location outcome attribution (M5)

Each call entering `LocateSession.locate` emits `grounding_attempt` followed by
`grounding_outcome`. The shared `call_id` also appears in `grounding_usage` and in
the locator's HTTP request as `grounding_call_id`; join that request's `request_id`
to its raw HTTP response archive. The task-local association is reset after the
locator request, including failures, so later planner requests are not mislabeled.
Calls rejected by an outer tool/context gate before entering the session retain
the existing tool/Runner error trace rather than a fabricated locator attempt.

Outcomes retain the planner's target description, requested frame/backend/protocol,
and, when available, image hash/size, requested and returned models, provider
response ID, finish reason, known-usage flag and parsed image point/box. The stages
are `preflight`, `observation_before`, `request`, `accounting`, `parse`,
`observation_after`, `postcheck` and `resolved`. The last reached stage localizes
failure without guessing its cause from a free-text exception message.

Response rejection codes are `invalid_response`, `incomplete_response`,
`refused_response`, `invalid_tool_call` and `invalid_location`. Other errors retain
`stage_failed` plus the exception type; controlled budget stops retain their stop
reason and cancellation is propagated. A request-stage error may originate from
payload validation, transport or SDK parsing, so it is not automatically labeled
as a network/model failure. Timeout-driven cancellation may be observed as
`cancelled` inside the locator; the outer tool/Runner trace retains the deadline.

`found`, `not_found` and `ambiguous` describe the accepted model response, not its
correctness. A legacy `found=false` still maps to `ambiguous`; this cannot establish
whether the target is absent or duplicated. Parsed coordinates are diagnostic
evidence and do not bypass the reference-only planner interface. Distinguishing
wrong target selection from a coordinate miss still requires independent truth
and task validation. Integrated A/B and post-dispatch effect attribution are not
covered by these split-locator events. No new model scores are implied.

### Per-trial HTTP admission limits (M5)

Built-in drivers can explicitly enable request admission limits through the Python API:

```python
from tank_backend.benchmarks.driver import SubAgentDriver
from tank_backend.benchmarks.request_budget import RequestLimits

driver = SubAgentDriver.create(
    "computer-use", request_limits=RequestLimits(planner=16, locator=15, total=31)
)
```

Use the actual frozen agent name and config path for the experiment. The default
`request_limits=None` preserves existing behavior; there is no CLI switch yet.
Engine/extension transports reject this option because their requests bypass the
built-in hook. Enabling limits disables both application and SDK retries on the
driver's LLM calls, including separately configured planner/locator clients.

The HTTPX request hook charges each admitted attempt before transport and never
refunds failures. This is a conservative admission count, not proof of wire delivery
or provider billing. Grounding calls charge the locator allowance; other calls,
including planner compaction, charge the planner allowance. Both share the total.
Zero forbids a role. A refusal latches the trial closed to further model requests.
The denied attempt emits `request_blocked`, but no `http_request` or response archive;
the final `request_budget` trace event and driver metadata retain counts and limits.
Limit stops retain `stop_reason=request_limit` without claiming confirmed cleanup.

Each serial `run` gets a new allowance. Overlapping runs and requests from inactive
or previous trial contexts are rejected. The last admitted response may still
dispatch tools; admission limits do not establish physical input cessation.
Optional token/cost reservations are described below; usable tighter input bounds,
batch request scheduling and verified cleanup remain pending. Existing task token
accounting occurs after responses and is not a hard token/cost reservation. These
offline controls do not authorize a live M5 batch or reset historical allowances.

### Token/cost reservation ledger (M5)

`tank_backend.benchmarks.spend_ledger.SpendLedger` provides in-memory arithmetic
for one serial batch. The optional HTTP integration below now uses this ledger;
the arithmetic module itself does not estimate tokens, load prices or restore
state across process restarts. Default benchmark runs do not enable it.

Create it with a batch `SpendLimit(tokens, nano_usd)`, then call
`start_trial(trial_id, trial_limit)`. Before each request, call
`reserve(request_id, TokenAllowance(input_tokens, output_tokens,
input_nano_usd, output_nano_usd))`. Allowance tokens must be independently verified
upper bounds for the final payload and output; prices are upper rates in integer
nano-USD per token (one USD is 1,000,000,000 nano-USD). Round fractional nano-USD
rates upward before constructing an allowance. Rates must cover the applicable
endpoint, pricing tier, reasoning and other billed tokens. No model prices or
tokenizer assumptions are embedded here.

Reservation checks both trial and batch totals before changing either. A failed
admission latches the entire batch stopped, even if a smaller request could fit.
`settle(request_id, input_tokens=..., output_tokens=...)` replaces the reservation
with complete validated usage at the reserved rates, releasing only the unused
portion. Known cost is a calculation at these rates, not an account invoice.
Missing/partial/invalid usage retains the full allowance and stops admission;
valid partial counts above the allowance increase the retained amount. Complete
usage above either declared bound is recorded without clamping and stops the
batch as `bound_exceeded`, even if total tokens remain below the combined bound.
An observed bound violation is a failed precondition, not successful enforcement.

Only one trial and one unsettled request may be active. IDs cannot be reused,
settlement cannot be repeated, and a new trial does not reset batch spending.
Call `finish_trial()` in the executor's `finally` path: unsettled requests become
unknown without releasing their allowance. Later settlement cannot reopen them.
`snapshot()` returns a detached, JSON-compatible report of limits, known and
reserved amounts, per-request allowances/status and the first stop reason.
The caller must still stop dispatch on settlement failure, save reports, verify
complete usage including reasoning, and bind allowances to actual HTTP requests.
Reliable request bounds, scheduling, recovery and physical
cleanup remain prerequisites for live M5 budget enforcement.

### Context-ceiling HTTP spend gate (M5)

Pass `spend=SpendControl(ledger, trial_limit, contracts)` alongside explicit
`request_limits` to `SubAgentDriver.create`. Each `ContextWindowContract` binds an
exact HTTPS completion URL and model to a `TokenAllowance` and a public evidence
description. The input allowance must cover the provider's full accepted input
ceiling, including messages, images, tool definitions and provider framing; the
output allowance and prices must cover that endpoint's non-thinking generation.
The caller must independently review these numbers and their applicability.
An evidence string is recorded, not automatically verified. No live defaults,
token estimates or CLI switch are supplied.

Before transport, the gate requires POST, matching URL/model, explicit
`enable_thinking=false`, bounded positive integer `max_tokens` and, for streams,
`include_usage=true`. Unsupported top-level parameters (including extra generations
and provider search) and malformed/duplicate-key JSON are refused. Every admitted
request reserves the full contract allowance and records its body hash, evidence
and the same request ID used by HTTP response archives. The count gate runs first;
a subsequent spend rejection can consume a count slot without sending HTTP.

Ordinary responses and fragmented SSE are copied as read, with a 2 MB audit-body
limit; this does not prefetch or delay chunks until completion. The gate requests
`Accept-Encoding: identity`; compressed responses are retained as unknown usage.
Settlement occurs after the SDK response/stream completes and before model tools
execute. It independently parses raw usage because the SDK can coerce illegal
values such as booleans. Input/output/total must be nonnegative integers with a
consistent sum; SSE requires exactly one usage record and a `[DONE]` marker.
Missing, malformed or inconsistent evidence retains the full reservation and
stops further admission; valid bound overruns remain unclamped. Text/tool-call
deltas can already have been emitted, and earlier physical actions are not undone.

Separately configured locator clients share the ledger. Serial driver runs use
distinct trial-directory IDs; failure/cancellation finalization retains pending
reservations. `spend_reserved`, `spend_settled`, `spend_blocked` and `spend_budget`
events carry the evidence and cumulative totals; post-run driver metadata includes
the ledger snapshot. Error/request-limit stops do not certify physical cleanup.

This conservative mode does **not make the proposed live batch runnable**. On
2026-09-22 the [Flash snapshot documentation](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash)
lists a non-thinking input ceiling of 991,808 tokens: reserving that plus 8,000
output tokens exceeds the proposed 300,000-token trial limit before the first
request. A tighter independently justified bound is still required; do not lower
the declared ceiling or increase approved budgets merely to pass admission.
Price/region review, complete billing semantics, paired scheduling, durable
recovery, real environment and physical cleanup remain live-run prerequisites.

### Serial batches and durable spend evidence (M5)

`benchmarks.batch.run_batch` accepts an ordered tuple of
`BatchTrial(key, suite_dir, task_id, agent_name, config_path, platform)`, plus an
unused `out_dir`, explicit batch/trial `SpendLimit`, per-trial `RequestLimits`,
`ContextWindowContract` tuple, `batch_request_limit` and `frozen_inputs`.
It creates each built-in `SubAgentDriver`
with the same `SpendControl` and runs exactly one matching task via `run_suite`.
Keys must be unique lowercase letters/digits/hyphens. All entries are checked
for a unique task/platform match before any driver starts. The caller supplies
the pairing/order; the API does not randomize or infer a paired experiment.

The output contains `batch-plan.json` (ordered inputs and limits),
`batch-events.jsonl` (started/finished entries), `spend.jsonl` (cumulative
snapshots), `batch-result.json` (finished entries and final accounting), and
each entry's existing suite report/trial artifacts under its key. `completed`
means the suite invocation returned, including failed trials; it does not mean
task success or confirmed cleanup. Budget stops and any cleanup other than
`confirmed` prevent starting the next entry. Exceptions/cancellation stop the
batch and are re-raised after accounting finalization.

`SpendLedger(limit, journal=path)` also enables persistence independently of the
batch API; callers must `close()` it in a finally block. Each mutation appends
a full JSON snapshot, flushes and fsyncs before returning, so an HTTP reservation
is persisted before transport and settlement before subsequent tool dispatch.
Journal creation is exclusive and its directory is synced. Sync/write failures
stop admission; driver request/spend contexts still close if finalization fails.
The default ledger remains in-memory. No prompts, credentials or screenshots
are added to the spend journal.

Existing journals and batch directories are refused, including cleanly completed
batches. There is **no automatic resume or ledger restore API**. After process
death, retain the journal and review its complete records; a pending reservation
remains fully charged. A partial trailing record cannot authorize releasing an
earlier reservation. The process-exit test verifies an acknowledged reservation
survives exit without Python cleanup; it does not test machine power loss.
Directory identity prevents replay within that output location, not globally
across copied/deleted artifacts or a different batch directory.

This API has no live defaults or CLI entry point. Tighter input bounds, resolved
runtime configuration checks, price review and verified physical cleanup remain required before the
proposed live experiment. Built-in cleanup currently remains unknown, so this
scheduler conservatively stops after that trial.

### Batch request ceiling and pinned input preflight (M5)

`run_batch` requires an explicit nonnegative integer `batch_request_limit`.
`SpendLedger(..., request_limit=...)` also supports this independently; omitting
it preserves the previous ledger behavior. Each admitted reservation consumes
one slot, shared by all trials and planner/locator clients. Zero-token usage,
HTTP failure or unknown usage never refunds a slot. Rejection happens before
transport; after the last slot the scheduler cannot start another entry. The
final admitted response may still dispatch tools. This counts admitted requests,
not proof of provider receipt or billing. Contract/token rejection may occur
before batch admission; a journal failure after reservation can consume a slot
without sending. Snapshots persist `limit_requests` and `admitted_requests`.

Supply `FrozenInputs(files=(FrozenFile(path, reviewed_sha256), ...), trees=(...))`
with previously reviewed hashes, preferably using absolute paths. No hashes are
updated or inferred by admission. Files must be unique, present, and match their
SHA-256. Every declared directory must have exactly the listed file inventory.
The scheduler additionally requires pins for each selected config, an existing
adjacent `.env`, suite YAML, all task YAMLs and the suite's asset files. It checks
all declared pins before creating the batch output, before each driver creation,
and again after driver creation before entering `run_suite`. Drift stops the
batch with `frozen_inputs`; zero HTTP allowance skips driver creation entirely.
The pinned files/directories and batch limit are saved in `batch-plan.json`.

Caller-supplied source, agent definition, validator and frozen-artifact files are
checked too, but dependency discovery outside the mandatory files is not automatic.
Declare directories when newly added files must also be detected. These are file
preflight checks, not a filesystem lock or a proof about already imported modules,
environment-variable expansion, dynamic inputs or the final live HTTP body.
Without an explicit comparison contract, they do not compare resolved profiles,
agent definitions or toolsets with the frozen experiment variants. They do not
authorize a live batch. Historical freeze artifacts remain
unchanged; source drift requires a separately reviewed new freeze.


### Resolved comparison configuration (offline M5)

`prepare_computer_comparison.py` also exports `runtime/<variant>/config.yaml`
and `agents/computer-use.md` for A, A-control, B-host-only, B-protocol-only,
B-combined, C and D. Historical `original` remains an archived definition/request,
not an eighth runnable experiment. Each generated config uses the environment
reference `${M5_DASHSCOPE_API_KEY}`; no credential is exported. The exporter
round-trips each config and definition through the production parsers before
capturing synthetic SDK requests. The manifest covers all 19 generated artifacts.

Pass `comparison=ComparisonContract(freeze_dir, variant)` to
`SubAgentDriver.create` or `BatchTrial` to opt into runtime verification. Before
constructing LLM clients or ToolManager, the driver compares the resolved agent
(including prompt/grounding), default/planner/locator profiles (except API keys
and profile names), agent search configuration and declared tool list against
frozen JSON. Mismatch raises without printing resolved values. Batch admission
also requires frozen pins for the comparison manifest, definitions, profiles,
toolset and local agent Markdown files. Pin source dependencies separately.

The [runtime export](computer_use/reports/20260922-m5-runtime-config/README.md)
is a new offline snapshot; older freezes are unchanged. Seven real driver/SDK
regressions compare the first serialized request's model, tools and generation
settings with the frozen requests. This does not verify credentials, provider
availability, full live message history, physical cleanup or model effectiveness.
The proposed paid batch remains unexecuted.


### Offline 17-trial proposal preflight

The current M5 proposal follows the user's 2026-09-22 instruction to collect
actual usage before enforcing token/cost budgets. From `backend/`:

```bash
uv run --no-sync python scripts/prepare_computer_batch.py --freeze benchmarks/computer_use/reports/20260922-m5-record-only-runtime --output /tmp/m5-proposal-new
uv run --no-sync python scripts/prepare_computer_batch.py --freeze benchmarks/computer_use/reports/20260922-m5-record-only-runtime --check /tmp/m5-proposal-new/proposal.json
```

The [current proposal](computer_use/reports/20260922-m5-record-only-proposal/README.md)
uses schema v2 and `record_only: true`. The historical 300,000/trial, 5.1M/batch
and 8 USD figures are retained as reference values, **not enforced caps**. The
old proposal and runtime freeze are unchanged and are historical snapshots.

It still fixes five pilots followed by three four-variant core rounds, the
Calculator task/config paths, per-trial planner/locator request limits, 120 seconds,
15 top-level tools and 362 total HTTP requests. Paths are relative to the backend
root. The 2,040-second sum excludes setup, validation and cleanup. Preflight
checks saved hashes, source/artifact hashes, runtime inventory, parsed configs
and strict GUI task limits. It never refreshes saved pins or runs a driver.

### Recording usage without token/cost admission

Pass `record_only=True` to `run_batch`; it persists the selection in the batch
plan and constructs a record-only ledger. For direct driver use, pass a
`SpendControl` whose `SpendLedger(..., record_only=True)` has explicit request
limits; no provider context/price contracts are needed in this mode. Defaults
remain strict for existing callers.

Recording mode skips token/cost reservation admission and bound-exceeded stops.
After verifying any comparison contract, the benchmark driver replaces only its
in-memory agent definition's token budget with zero. It records both configured
and effective budgets. Tank's production `agents/computer_use.md` is unchanged.
The output `max_tokens` remains 8,000 in M5 configs; retries remain disabled.

Actual input/output usage, request counts and raw response evidence are retained.
Snapshots mark `record_only=true` and `cost_status=unpriced`; zero monetary fields
are placeholders, **not zero charges or proof of an 8 USD cap**. Unknown or invalid
usage remains unknown and stops the batch. HTTP failures (including insufficient
balance) retain error responses and stop without retry. Request ceilings,
timeouts, tool steps, frozen-input checks and unconfirmed-cleanup stops remain.

This removes the full-context token reservation as an M5 execution prerequisite.
Preflight still reports `live_ready=false` for the outstanding independent
scoring, real environment/physical cleanup, pilot acceptance and live endpoint/
image-scope conditions. The proposal is not a phase-aware executor; no automatic
pilot-to-core transition is implemented. No paid requests occur during preflight.


### Fixed single-pilot execution entries

`prepare_computer_batch.py` keeps its CLI offline. Schema v3 proposals pin
`input_cleanup: true`. After explicit screenshot/endpoint consent and controlled
local desktop preparation, its `execute_a_control(freeze, proposal_path, output,
live_authorized=True)` API runs only the first A-control pilot.
`execute_b_protocol_only` has the same signature and runs only the scheduled
B-protocol-only row. Both fixed entries enforce at most 16 requests,
120 agent seconds and 15 steps, with record-only token/cost accounting and native
input cleanup. It verifies the proposal and source/config/runtime pins before
constructing the batch, and cannot automatically enter another pilot or core.
The caller supplies credentials and screenshot scope guards; the API does not
obtain consent or restore the desktop environment. See the
[B-protocol-only preparation](computer_use/reports/20260924-m5-b-protocol-ready/README.md).


### Adoption decision and closeout (M8, 2026-09-25)

The adaptation-and-grounding plan (M0–M8) is closed. The production baseline
stays unchanged: the default `computer_use` agent has no `grounding`
frontmatter (integrated planning/locating, legacy normalized coordinates,
qwen3.7-flash). M2 image coordinates, the M4 split locator, M5 integrated
adaptation variants and the M7 AX branch all remain explicit opt-in; deleting
the `grounding:` key restores the original mode.

Evidence layers: no static candidate passed the frozen first-round screen
(M3 holdout: Max bbox / GPT point hit 96/96 positives but same-name ambiguity
rejection was 0/16 with executable false positives); real paired tasks kept
the baseline ahead on the wide set (M6: strict A 10/36 vs split C 5/36, C at
1.7–2× tokens) while B-combined was the worst arm on calc-open (0/6 merged);
the AX branch is conditionally deferred (selector precision is the bottleneck).
The click-offset root cause is **not** claimed solved; attribution stops at the
service output boundary. Full aggregation (versions, manifests, request/token
totals, denominators, paired results, unknowns, cost/latency, failure indexes):
[M8 closeout report](computer_use/reports/20260925-m8-closeout/README.md).
Condition-triggered follow-ups live in `docs/backlog.md`.
