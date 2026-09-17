# 插件子 Agent 与官方 N2ComputerAgent 接入设计

> 状态：设计待实施（2026-09-17）。本轮只形成设计和当前 N2 测试指南；保留现有 engine、DesktopExecutor 和 n2，新增路径完成真机对比后再决定清理。

关联：[原 computer-use / N2 计划](computer-use-improvement-and-n2-plan.md)、[当前编排设计](../../design/agent-orchestration.md)、[当前 N2 插件](../../../backend/plugins/agent-n2/README.md)、[基准指南](../../../backend/benchmarks/README.md)。

## 1. 决策与成功条件

- 新插件直接包装官方 `N2ComputerAgent`，使用 SDK computer adapter；不调用 Tank 的 `DesktopExecutor`，不再自写 N2 loop。
- 现有 `n2` / `agent-n2:agent` / `agent_engines` 完整保留，作为可回退的旧实现。
- 新增 `n2_sdk` / `agent-n2-sdk:agent`，通过通用插件子 Agent 入口运行；主 Agent 仍调用现有 `agent` 工具。
- 复用 WorkerSupervisor、Runner、Bus、任务状态与结果通知，不创建第二套调度器。
- 新入口支持本地 SDK 和远程任务型 Agent；核心不识别 Yutori 的消息、动作或 trajectory。
- 验收看任务副作用、延迟、usage、停止与清理结果，不能把 SDK 循环结束等同于任务成功。
- 修正 benchmark 的 trial 隔离后重跑旧 baseline，再比较新路径；不拿不同评分版本的历史成功率直接比较。

本轮全仓检索：只有 `backend/agents/n2.md` 使用 agent `engine`，只有 N2 插件实际消费 DesktopExecutor。Runner、派发审批、benchmark、导出和测试有配套引用。内置 computer-use 工具直接调用平台实现，不使用 DesktopExecutor。

## 2. 接入结构

```text
主 Agent → agent 工具 → WorkerSupervisor → AgentRunner
  ├─ 现有 Markdown agent → 内置 LLMAgent
  ├─ engine: agent-n2:agent → 旧 N2Agent → DesktopExecutor
  └─ extension: agent-n2-sdk:agent → SubAgent facade
                                      ↓
                              插件的 N2SdkSubAgent
                                      ↓
                              官方 N2ComputerAgent
                                      ↓
                              SDK computer adapter
```

这里仍需要 SDK 要求的 computer environment，但由插件持有。macOS 优先采用 SDK 原生 MacOSComputer；Linux 从官方 direct-X11 adapter 适配，先验收 X11。官方示例不等于已发布的稳定 API：实施前选定并固定 PyPI 版本，确认实际导出、构造参数、平台依赖和取消行为。Linux Wayland 若没有可验证的 adapter，明确返回不支持，不静默切回旧 executor。新路径首轮支持平台必须在插件描述与测试报告中注明。

如需修改 Linux 参考 adapter，代码放在新插件内，记录来源与许可证；可调用已存在的平台原语，但不经旧 DesktopExecutor，也不把 N2 适配搬进核心。SDK 原语采用像素坐标，不再额外做旧路径的归一化换算。

官方依据（2026-09-17 核对）：[N2 参考](https://docs.yutori.com/reference/n2)、[SDK loop / callbacks / resume](https://github.com/yutori-ai/yutori-sdk-python/blob/main/yutori/navigator/n2.py)、[SDK compactor](https://github.com/yutori-ai/yutori-sdk-python/blob/main/yutori/navigator/n2_compaction.py)。SDK 管历史、batch、坐标与压缩；恢复已有对话不等于跨进程持久化恢复。

## 3. 最小公共契约

新增 `agents/subagent.py`，定义有类型的 SubAgent ABC 及小 dataclass。不让插件依赖 OpenAI ChatCompletionMessageParam；供应商状态始终由插件解释。

| 对象 | 首轮字段 / 方法 | 语义 |
|---|---|---|
| SubAgentRequest | task、context（文本）、task_id | 只传完成目标所需的上下文；不默认转发主会话全部历史 |
| SubAgentContext | 授权、预算、截止时间、取消信号、可选 observer | 每次运行由 Tank 创建；授权与预算不能由插件配置覆盖 |
| SubAgent | `run(request, context) -> AsyncIterator[AgentOutput]`、`aclose()` | 复用现有事件；显式清理 SDK 和环境资源 |
| SubAgentCapabilities | cancel、pause、resume、persistent_resume | 声明支持范围；暂停声明粒度；取消区分请求与确认 |
| observer | API 调用、usage、截图/产物 | 可选的观测入口；用于预算、审计与 benchmark，不用于执行动作 |

Runner 中一个 facade 将现有 AgentState 转成任务请求，再把插件事件送回当前 AgentRunner 输出路径。facade 保留共享的预算和清理逻辑；新插件不继承或操纵内部 LLM 工具循环。SubAgentContext 中的预算是同一运行的共享账本，避免 SDK 消耗和 Runner 重复计数。

首轮 SubAgentCapabilities 只开放已通过测试的能力。N2 SDK 首轮目标为运行、事件、预算、超时与可靠取消；暂停/恢复作为后续独立步骤，不因接口声明就对用户开放按钮。

完成时复用 DONE，增加结束原因元数据：`final_answer`、`max_steps`、`budget`、`context_limit`、`error`。预算/步数上限作为未完成结果；异常、超时、取消映射到现有 failed/timeout/cancelled 状态。只有明确 final_answer 正常返回才能标记 completed，但业务成功仍由结果或 validator 判断。清理无法确认时标记 failed 并说明残留风险，不能报 cancelled 成功。

## 4. 插件注册与配置

继续复用 ExtensionRegistry；增加 `type: subagent`，验证工厂返回 SubAgent。旧 `type: agent` 仍要求现有 Agent ABC。`extension` 与 `engine` 不可同时配置。

新插件 manifest 的设计形状（尚未实现）：

```yaml
name: agent-n2-sdk
display_name: Navigator n2 SDK
extensions:
  - name: agent
    type: subagent
    factory: agent_n2_sdk:create_subagent
    permissions: [desktop, shell, filesystem, network]
```

`permissions` 是派发审批、运行环境选择与授权显示的依据，不是沙箱本身；禁止只依赖提示词实施访问控制。首轮明确为受信任插件、专用桌面任务级授权。若部署要求严格目录/网络边界，在操作系统/VM/容器落实后才能声明支持。

新 agent definition：

```yaml
name: n2_sdk
description: Desktop automation using the official N2ComputerAgent
extension: agent-n2-sdk:agent
background: true
token-budget: 300000
```

该 definition 不带 `toolset: computer_use`，也不让 Tank 的 `model` / `disallowed_tools` 冒充对 SDK 内部工具的限制。SDK 专属参数放在 `subagents.<extension>.config`；新配置不走 agent_engines：

```yaml
subagents:
  "agent-n2-sdk:agent":
    config:
      api_key: ${YUTORI_API_KEY}
      base_url: https://api.yutori.com/v1
      model: n2
      tool_set: computer_use_tools-20260830
      reasoning_effort: medium
      max_steps: 100
      environment: local
```

复用现有环境变量解析；不为新增插件强制增加 LLMProfile 依赖，其他远程任务服务不需要这种配置形状。配置和依赖在新插件中验证，核心只验证公共入口与授权。配置示例不是已可运行的安装指令。

## 5. N2 包装、控制与安全

### 5.1 SDK 包装

- 每次任务创建独立 SDK Agent 和 computer environment，结束后关闭。
- completions wrapper 在所有 API 调用边界记录耗时和 usage，包括 compaction、格式重试、截断重试；每个实际响应只记一次。默认客户端隐藏的自动重试若不能逐次观察，显式记录为一个逻辑调用，不宣称全部网络尝试可见。
- 模型请求前检查预算/截止时间；响应后计账；动作开始前再检查。预算是收到响应后的停止阈值，不能保证一个在途响应零超支。
- 不只统计 SDK actor 的 on_usage，避免遗漏压缩调用；usage 缺失时终止预算受控任务。
- 模型预测和工具执行事件转换成现有 TOKEN、TOOL_EXECUTING、TOOL_RESULT；一份 SDK tool call 只计一个执行事件，batch 成员数量另记诊断值。
- SDK 的截图观测送给 observer；不 monkey-patch DesktopExecutor。截图应保留实际 PNG/WebP MIME 和文件扩展名。
- 不通过重新实现 SDK 私有 loop 达成观测或控制；若所选版本缺乏必要 hook，明确报告限制或换版本。

### 5.2 生命周期分期

| 能力 | 实现位置 | 验收条件 |
|---|---|---|
| 取消 / 超时（首轮） | Supervisor 取消任务；插件向 SDK/environment 传递取消并关闭 | 不再开始新动作；释放按键/鼠标；自有进程退出；最后状态可解释 |
| 桌面独占（首轮） | Tank 任务运行上下文获取同一桌面资源锁 | n2 与 n2_sdk 互斥，取消/失败均释放；旧实现本身不重写 |
| 暂停（第二步） | SDK on_run_continue 等安全边界；Supervisor 持有运行 handle | 当前完整工具调用结束并释放输入状态后才确认 paused |
| 同进程恢复（第二步） | 插件保留运行实例或完整工具轮次的 trajectory | 重新观察桌面后继续；不直接执行旧截图上的剩余动作 |
| 重启恢复（后续） | 插件 snapshot + WorkerStore | 保存格式版本、SDK 版本、累计预算、cwd/环境 ID、未确认动作；重建后验证现场 |

SDK resume 是追加消息继续已有历史。首次只允许在完整工具结果边界保存并恢复；中断导致“动作可能已发生、结果未确认”时先检查结果，不自动重放。暂停期间用户接管桌面后需要重新观测；如在工具开始前已有模型计划，丢弃该计划并返回明确未执行结果，要求重新规划。

首轮不改 WebSocket 协议和 web/macOS 控件；仍通过 agent_status / agent_stop 控制任务。第二步增加 agent_pause / agent_resume、运行 handle 及状态迁移，届时再更新前端和协议（如确有新增公共消息）。waiting（等待用户答案）与 paused（主动暂停）不得混用。

安全控制采用任务审批 + SDK 支持的 hooks + 专用运行环境。插件 permissions 决定请求范围，用户授权决定本次放行；SDK 工具禁用只缩小模型工具面，不能限制 shell 经其他途径访问资源。Python 同进程插件是受信任代码；强制约束第三方插件需要独立进程和系统权限隔离。

现有旧路径取消限制保留为 baseline 的已知属性：DesktopExecutor.bash 使用 to_thread(subprocess.run)，取消 asyncio 等待不保证杀掉后台线程中的 shell。新 SDK 路径必须验证环境的真实取消能力；不能把 task.cancel 当作已清理的证据。

## 6. 文件改动清单

下表是实施范围，本轮没有实施这些逻辑。

| 文件 / 目录 | 改动 |
|---|---|
| `backend/core/src/tank_backend/agents/subagent.py`（新增） | 公共任务请求、上下文、能力、SubAgent ABC / observer |
| `agents/subagent_adapter.py`（新增） | 将 SubAgent 包装为当前 AgentRunner 可消费的 Agent facade |
| `agents/definition.py` | 新增 extension；拒绝与 engine 同时出现；旧字段保留 |
| `plugin/manifest.py`、`plugin/registry.py` | subagent 类型、permissions、返回类型验证；agent / needs 保留 |
| `plugin/manager.py` | 新类型发现及注册；通用 registry 能复用的部分不改 |
| `config/app_config.py` | subagents 配置入口解析/校验；现有 agent_engines 保留 |
| `agents/runner.py` | 新 extension 分支、facade、授权和预算上下文、桌面锁；engine 分支保留 |
| `agents/agent_tool.py` | 新入口派发审批按 permissions 判断；旧 desktop_executor 审批保留 |
| `agents/supervisor.py` | 传递稳定 task_id；正确处理新入口结束原因；复用已有取消与通知 |
| `pipeline/processors/brain.py` | 将已注册 subagent 描述合并进现有派发目录；校验名称冲突；无需新调度器 |
| `backend/plugins/agent-n2-sdk/`（新增） | SDK 固定版本、工厂、包装、平台 environment、配置和测试指南 |
| `backend/agents/n2-sdk.md`（新增） | 注册可选择的 n2_sdk；不修改 n2 的默认选择 |
| `backend/uv.lock` | 新插件及固定 SDK 依赖；backend workspace 已匹配 plugins/* |
| `benchmarks/driver.py` | 识别 extension 路径；同一 Runner 接入；新截图 observer 与计账 |
| `benchmarks/runner.py`、`pageserver.py` | 每 trial 独立提交记录；隔绝历史与迟到事件 |
| `benchmarks/trace.py`、`report.py` | MIME 正确归档；追加终止原因/原语数量等诊断，保留原字段 |
| `backend/benchmarks/computer_use/tasks/*.yaml` | 对弱 validator 分别补真实结果检查；仍使用现有任务域 |
| `docs/design/agent-orchestration.md`、后端 ARCHITECTURE / TESTING | 行为落地后更新当前架构与测试入口 |

新入口可以先由 Markdown extension 指向注册插件；目录合并只需支持统一可派发描述，不在插件中另维护一份和 Markdown 可能冲突的名称。首轮保持现有命名和优先级，重复的插件 ID 或不明确入口报错。

保留且首轮不改：旧 N2 插件 loop/protocol、DesktopExecutor 实现、原 engine 工厂分支、原 n2 定义、agent_engines 配置。只在共享任务外层补必要授权/锁，不改旧 N2 的模型与动作语义。后续清理条件为真机效果与控制验收通过、用户采用新路径、全仓无旧业务调用；届时单独开清理子任务并再次检索引用。

## 7. 当前已实现 N2：用户测试指南

### 7.1 准备与离线确认

在测试机更新到同一已提交 revision。运行真实任务会调用付费 N2 API，并操控实际桌面、上传全屏截图；按现有 suite 要求使用专用 macOS 账户或 Linux GUI VM，固定单屏、分辨率与输入法。以下命令均从仓库根目录进入 backend/core：

```bash
cd backend/core
uv sync --package agent-n2 --group dev
uv run --package agent-n2 python -c "import agent_n2; print('agent-n2 import OK')"
uv run --package agent-n2 pytest ../plugins/agent-n2/tests -q
uv run --package tank-backend tank-backend --check-computer-use
```

doctor 不注入输入，但结果仍需人工配合检查系统授权；macOS 给启动 backend 的 Terminal/Python 必要屏幕录制、辅助功能权限。Linux 按 doctor 检查截图路径、ydotool/X11 等依赖；启动进程须继承 GUI 会话环境。Mock 单测不证明真机任务成功。

合并 `backend/plugins/agent-n2/config.example.yaml` 到 `backend/core/config.yaml`，保持现有 llm.default 等配置；在 backend/core/.env 设置 `YUTORI_API_KEY`，或在启动 backend 和 benchmark 的各自 shell 中 export。不要打印或提交 key。配置的名称必须对应：

```yaml
llm:
  n2:
    api_key: ${YUTORI_API_KEY}
    model: n2
    base_url: https://api.yutori.com/v1
agent_engines:
  "agent-n2:agent":
    llm_profile: n2
    tool_set: computer_use_tools-20260830
    reasoning_effort: medium
    max_steps: 100
```

确认 agents.dirs 包含 `../agents`，确认用户目录没有意外的同名定义；现行 loader 是列表中先出现者优先。确认生成的 backend/core/plugins.yaml 中 agent-n2 和 agent 扩展均启用。重启 backend 后再测试，新的插件 manifest 不一定由 Python reload 自动加载。

检查配置和可派发名称（无桌面动作、无付费模型请求）：

```bash
uv run --package agent-n2 python - <<'PY'
from tank_backend.benchmarks.driver import SubAgentDriver
d = SubAgentDriver.create("n2")
print("n2 configuration and plugin factory registration OK")
PY
```

这只验证 driver 组装与注册；不实例化并运行真实 N2 Agent，不验证 key 是否有效。没有默认 LLM profile、agent 定义路径错误或插件无法发现时会明确报错。

### 7.2 Tank 完整派发链路

启动 backend/core 下的 `uv run --package agent-n2 tank-backend --reload`，另一个终端在 web 下执行 `pnpm dev`。已有 dev 会话时直接使用它，避免启动重复服务。通过 Tank 文本聊天先测试，再测试语音：

1. 输入：“使用 n2 子 Agent，在后台打开系统计算器，用 GUI 计算 7×8，确认显示 56。返回 task_id。”核对主 Agent 实际调用 `agent(subagent_type="n2", ...)`。
2. 核对任务级审批出现在第一项桌面动作之前；批准后看工具活动、截图驱动行为、完成通知。人工确认屏幕上是 56；仅报告 completed 不证明结果。
3. 输入：“使用 n2 子 Agent，在后台打开浏览器，搜索 Yutori Navigator n2，确认结果页已经显示。”核对导航与最终页面。此项使用外网，单独记录，不混入零外网 benchmark。
4. 输入：“使用 n2 子 Agent，在后台用文本编辑器创建 ~/bench-work/n2-manual.txt，内容为 Tank N2 测试 / hello-123，保存并确认内容。”先创建专用测试目录，事后通过文件读取核对文字，不仅看模型描述。
5. 停止测试：“使用 n2 子 Agent，在后台只用 GUI，打开计算器，重复输入 1+1、确认、清空，每轮等待 2 秒，共 30 轮；不要使用 shell。”取得 task_id 后，任务仍 running 时在同一 Tank 会话输入：“调用 agent_stop，停止任务 <task_id>。”

对应工具调用示例：

```json
{"subagent_type":"n2","prompt":"打开系统计算器，用 GUI 计算 7×8，确认显示 56。","run_in_background":true,"description":"N2 calculator smoke test"}
```

停止后调用 agent_status 确认状态，观察至少 10 秒无新动作，检查鼠标及 Ctrl/Shift 等没有保持按下。模型不一定产生 mouse_down，普通循环停止测试不能代替拖拽中取消验收。拖拽/按键保持取消需在专门任务中观察到对应动作，记录时间点再停止；已有单测覆盖不等于真机覆盖。

任务查询 REST（实际健康路由为 /api/health；没有 REST stop 接口）：

```bash
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/api/agents/<task_id>
```

记录 git revision、OS/display backend、屏幕尺寸、任务原文、task_id、是否审批、结果、终止原因和日志。旧实现不支持主动暂停/N2 专属恢复；不要用 agent_reply 冒充 N2 恢复。

### 7.3 当前 benchmark 命令

仍在 backend/core，先确认 CLI，再做单任务诊断：

```bash
uv run --package agent-n2 python -m tank_backend.benchmarks --help
uv run --package agent-n2 python -m tank_backend.benchmarks \
  --suite ../benchmarks/computer_use --agent n2 \
  --tasks '^calc-open$' --trials 1 --label n2-current-debug
```

全套单轮冒烟，然后全套三轮探索性 baseline：

```bash
uv run --package agent-n2 python -m tank_backend.benchmarks \
  --suite ../benchmarks/computer_use --agent n2 \
  --trials 1 --label n2-current-smoke
uv run --package agent-n2 python -m tank_backend.benchmarks \
  --suite ../benchmarks/computer_use --agent n2 \
  --trials 3 --label n2-current-baseline
```

自动识别 macos/linux，不用强行覆盖平台；配置非默认位置时传 `--config /绝对路径/config.yaml`。benchmark 自己组装 Runner 和本地页面服务，不要求 backend/web 服务运行；停止同桌面其他 agent/定时 GUI 任务，跑批不碰键鼠。需要有可解析的默认 LLM profile；driver 目前仍构建默认 LLM 和 ToolManager，实际 N2 API 调用使用 agent_engines 指定的 n2 profile。

报告位置：`backend/benchmarks/computer_use/reports/<UTC时间戳>-<label>/`。查看 report.md / report.json，以及 trials/<任务>/<轮次>/ 的 result.json、trace.jsonl、screenshots/。当前套件有 14 个任务，三轮通常为 42 次 trial，以实际平台匹配数为准。正式比较须先修正第 8 节问题并重测两组；上述当前报告适合先查连通性、任务失败与明显瓶颈。

## 8. benchmark 能评估什么，以及必须先修正什么

当前 driver 已识别 engine，注册 N2 工厂、包装 USAGE 统计和 executor 截图，所以能评估当前 N2。它测任务副作用、tool call 数、总耗时、tokens、截图和调用延迟；不测 Supervisor、审批 UI、通知、持久化或语音链路。

已确认的限制：

1. `runner.run_suite` 只在套件启动时清空 page_capture.jsonl，页面事件后续持续追加；表单等 validator 搜索全文件，前一轮成功可以让后一轮误判成功。必须每 trial 记录独立 capture，并用 trial 标识拒绝旧页面/迟到请求；只清空共享文件不能隔绝迟到事件。修改前的历史报告不能当严格 baseline。
2. calc-open 的 validator 只检查计算器进程，没有检查 56；terminal-write 只检查文件，N2 可以直接 bash 完成而未打开 Terminal。应分别补可机器读取的真实结果/状态检查；暂时无法可靠验证的任务降为 smoke 并人工复核，不把它的得分当完整任务成功。
3. 一步是 TOOL_EXECUTING，即一个 tool call；computer_batch 可包含多个原语，不能把 steps 称为鼠标动作数。比较保留该口径，并追加原语数、模型轮数作诊断；SDK max_steps（模型轮数）与 benchmark max_steps（tool call 上限）分别记录。
4. 当前 driver 在下一条 TOOL_EXECUTING 使 steps 超限后、实际执行前停止，报告可能包含一份未执行请求；迁移前修正成明确“开始执行”计数，新旧两组使用同版本。
5. N2 不流式，当前统计把完整响应时间写作 TTFT；报告应明确为非流式 RTT，不能解释成首 token 延迟。当前 N2 缺少返回 usage 的在途取消调用不会进入完整调用统计。
6. 旧 bash 取消后可能仍在执行；如果发生，先人工确认并清理残留再继续，不能让下一 trial 与它并行。新 driver 在清理未确认时应停止整个 suite。
7. 新 adapter 不使用 DesktopExecutor 后，旧截图 monkey-patch 无法归档新路径。通过公共 observer 收集截图，按 MIME 写文件；否则会出现有动作无截图的误导性报告。
8. 现有 tasks 的 setup/validator/localhost:8901 均运行在本机；首轮 SDK A/B 使用同一桌面本地 adapter。若换远程 VM，setup/validator 和页面可达性也必须迁移，不能直接复用本地路径宣称同环境比较。

因此迁移后能继续使用相同 suite 和 validator，但必须增加 extension driver 接入与观测，修正测量问题后同尺重跑。不用新建一个“N2 专用 benchmark”。

### 8.1 对比实验

- 三组：computer_use（通用路线）、n2（自写 loop）、n2_sdk（官方 SDK loop）。主要迁移判断比较后两组。
- 同机器、桌面、分辨率、任务/评分 revision、时间/预算/tool call 上限、model=n2、tool_set=20260830、reasoning=medium；记录 SDK 版本、环境 adapter、采样/输出上限/压缩/重试差异。
- n2 是服务端 latest stable 别名，不是冻结权重；新旧组在短时间内交替运行，记录运行日期和供应商可取得的版本信息。
- 对齐相同可控的参数；无法对齐的 SDK 默认行为写入报告。替换 loop 和 adapter 一起比较得到的是整条新路径的效果，不能仅归因于 SDK loop。
- 全能力模式允许 bash/file，用来测最终任务能力；纯 GUI 实验另行通过双方一致的工具禁用配置开展。当前旧 N2 未实现 disable_tools，不能只禁 SDK 一侧后比较；提示“只用 GUI”不是强制工具禁用。
- 每任务先 3 trial，边界差异再扩展到 5–10 trial；不用子集 debug 报告声称全套改进。优先看逐任务成功率/置信区间与失败原因，随后看耗时、实际 tokens/API 调用、清理可靠性。
- 补长任务与生命周期测试：现有短套件很少触发 compaction，不能证明压缩/恢复改进；审批、暂停、取消、通知另走完整派发验收。

新路径落地后的命令（目前不可执行）：

```bash
uv run --package agent-n2-sdk python -m tank_backend.benchmarks \
  --suite ../benchmarks/computer_use --agent n2_sdk \
  --trials 3 --label n2-sdk-baseline
```

采用门槛：同尺数据无明显任务成功率回退；预算、停止及清理验收通过；截图/usage 完整；用户认为平台支持与耗时可接受。未通过时保留 n2 并根据 trace 修复新插件，不删除旧实现。

## 9. Tests

实施按 TDD，每个步骤先写失败测试，再提交实现：

- 入口：extension / engine 互斥、subagent 类型与工厂验证、名称发现、旧 n2 完整回归。
- 授权：desktop 插件派发审批先于工厂启动/第一动作；取消授权后禁止新动作；配置不能伪造运行上下文；旧审批继续通过。
- 资源：旧 n2 与 n2_sdk 同桌面互斥；失败、取消和初始化异常释放锁。
- 预算/结果：SDK 重试及压缩每份 usage 只记一次；缺失 usage 停止；预算越界后无新动作；max_steps/context_limit 不报告成功完成。
- 生命周期：模型请求、batch、按键保持、shell 中取消；确认 SDK close/environment 清理完成；同进程暂停恢复新增时分别验收。
- 观测：SDK WebP 与 PNG 归档格式正确；实际 API/工具调用计数；observer 不使生产运行依赖 benchmark。
- benchmark：前 trial 成功、后 trial 不提交时后者必须失败；旧页面/迟到请求不能污染下一 trial；步数边界不计未执行请求；清理失败停止 suite。
- 真机：第 7 节任务与 A17 三组实测；新平台 adapter 人工金标与 validator 先行。
- E2E：在现有 `test/features/chat.feature` 增加插件派发/状态/停止/结果通知场景，mock SDK 和环境，保证无付费 API、无真实宿主机输入；真机控制单独验收。后续新增暂停/恢复同样扩展现有 domain feature。

## 10. 实施步骤与最终 Verification Checklist

1. 修正 benchmark trial 隔离与计数、标注/补强 validator；提交独立修复；用户重跑旧 n2 baseline。
2. 实现最小 SubAgent 契约、插件入口、授权与 facade；先用 fake 插件验证完整派发；提交。
3. 新增 agent-n2-sdk 和平台环境、usage/截图观测、可靠取消；旧路径保留；提交。
4. 用户执行真机派发与同环境 A17 对比；记录发现，修复后重测。通过后再开展暂停/恢复；旧代码清理另行决定。
5. 更新现行架构/测试文档，计划所有项完成或移交后移动到 done 并更新索引；阶段完成分别提交。
6. 最终执行完整验证清单，失败不忽略；真实 GUI 和付费测试由用户在测试环境执行：

   1. `cd web && pnpm lint`。
   2. `cd web && npx tsc -b --noEmit`。
   3. `cd backend && uv run --package tank-backend ruff check core/src/ core/tests/ contracts/ plugins/`（原清单 src/tests 已迁至 workspace，使用实际路径）。
   4. `cd backend && uv run --package tank-backend pytest`（全部 workspace 测试）。
   5. `cd backend && uv run --package tank-backend pyright <本轮修改的 Python 文件>`；只改文档时 N/A；禁止以 type: ignore 掩盖错误。
   6. `cd cli && uv run ruff check src/ tests/`。
   7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`；无匹配为通过；有匹配检查具体 backend/web pane 与当前运行状态，报告并处理错误，不以单元测试替代。
   8. `cd test && pnpm test`；backend/frontend 必须已运行。
   9. `python3 scripts/check_docs.py`。
   10. `python3 scripts/check_protocol_sync.py`。

本轮文档与命令核对的验证结果另在任务回复中报告；不将设计写成已实现行为。
