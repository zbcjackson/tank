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
It does not rescore old reports. Integrated B adaptation, split batch primitive
reporting, raw locator failure attribution and paired A/B/C/D execution still
require work before the M5 effect comparison. No new model results are implied.
