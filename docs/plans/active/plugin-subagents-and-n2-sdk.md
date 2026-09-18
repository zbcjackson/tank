# 插件子 Agent 与官方 N2ComputerAgent 实施计划

> 状态：SDK 插件与通用派发已实现，自动化验证通过，实机验收待完成（2026-09-17）。保留旧 n2/engine/executor；Linux adapter、M1 真机 baseline、M6 实机 A/B 与采用结论尚未完成，M7 未触发。

关联：[已归档 computer-use / N2 计划](../done/computer-use-improvement-and-n2-plan.md)、[当前编排设计](../../design/agent-orchestration.md)、[当前 N2 插件](../../../backend/plugins/agent-n2/README.md)、[基准指南](../../../backend/benchmarks/README.md)。

## 1. 决策与成功条件

- 新插件直接包装官方 `N2ComputerAgent`，使用 SDK computer adapter；不调用 Tank 的 `DesktopExecutor`，不再自写 N2 loop。
- 现有 `n2` / `agent-n2:agent` / `agent_engines` 完整保留，作为可回退的旧实现。
- 新增 `n2_sdk` / `agent-n2-sdk:agent`，通过通用插件子 Agent 入口运行；主 Agent 仍调用现有 `agent` 工具。
- 复用 WorkerSupervisor、Runner、Bus、任务状态与结果通知，不创建第二套调度器。
- 新入口支持本地 SDK 和远程任务型 Agent；核心不识别 Yutori 的消息、动作或 trajectory。
- 验收看任务副作用、延迟、usage、停止与清理结果，不能把 SDK 循环结束等同于任务成功。
- 修正 benchmark 的 trial 隔离后重跑旧 baseline，再比较新路径；不拿不同评分版本的历史成功率直接比较。

2026-09-17 核对：只有 `backend/agents/n2.md` 使用 agent `engine`，只有 N2 插件实际消费 DesktopExecutor。Runner、派发审批、benchmark、导出和测试有配套引用。内置 computer-use 工具直接调用平台实现，不使用 DesktopExecutor。现有主配置已配置正确 N2 profile；用户确认 macOS 计算器操作正常。完整 N2 baseline、其余桌面任务、批中停止和旧会话完成通知复测从原计划移交到 M1/M6；这些结果尚未取得。

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

版本候选已核对 [PyPI yutori 0.9.29](https://pypi.org/project/yutori/0.9.29/) 的
实际 wheel，而非仅参考 main 示例：包含 N2ComputerAgent、MacOSComputer、
callbacks、trajectory/resume 和 compactor；macos extra 固定 cua-driver 0.23.2。
M0 先验证这些公共接口和依赖可用于 Tank，再在新插件固定
`yutori[macos]==0.9.29`，SDK 升级另行回归。首个可运行里程碑优先 macOS；
Linux direct-X11 在 M4 单独验收，Wayland 不在首轮 SDK 支持承诺内。

## 3. 最小公共契约

新增 `agents/subagent.py`，定义有类型的 SubAgent ABC 及小 dataclass。不让插件依赖 OpenAI ChatCompletionMessageParam；供应商状态始终由插件解释。

| 对象 | 首轮字段 / 方法 | 语义 |
|---|---|---|
| SubAgentRequest | task、context（文本）、task_id | 只传完成目标所需的上下文；不默认转发主会话全部历史 |
| SubAgentContext | 授权、预算、截止时间、取消信号、可选 observer | 每次运行由 Tank 创建；预算计账不依赖可选 observer；授权与预算不能由插件配置覆盖 |
| SubAgent | `run(request, context) -> AsyncIterator[AgentOutput]`、`aclose()` | 复用现有事件；显式清理 SDK 和环境资源 |
| SubAgentCapabilities | cancel、pause、resume、persistent_resume | 声明支持范围；暂停声明粒度；取消区分请求与确认 |
| observer | API 调用、usage、截图/产物 | 可选的观测入口；用于审计与 benchmark，预算账本独立工作，不用于执行动作 |

Runner 中一个 facade 将现有 AgentState 转成任务请求，再把插件事件送回当前 AgentRunner 输出路径。facade 保留共享的预算和清理逻辑；新插件不继承或操纵内部 LLM 工具循环。SubAgentContext 中的预算是同一运行的共享账本，避免 SDK 消耗和 Runner 重复计数。

首轮 SubAgentCapabilities 只开放已通过测试的能力。N2 SDK 首轮目标为运行、事件、预算、超时与可靠取消；暂停/恢复作为后续独立步骤，不因接口声明就对用户开放按钮。

完成时复用 DONE，增加结束原因元数据：`final_answer`、`max_steps`、`budget`、`context_limit`、`error`。预算/步数上限作为未完成结果；异常、超时、取消映射到现有 failed/timeout/cancelled 状态。只有明确 final_answer 正常返回才能标记 completed，但业务成功仍由结果或 validator 判断。清理无法确认时标记 failed 并说明残留风险，不能报 cancelled 成功。

## 4. 插件注册与配置

继续复用 ExtensionRegistry；增加 `type: subagent`，验证工厂返回 SubAgent。旧 `type: agent` 仍要求现有 Agent ABC。`extension` 与 `engine` 不可同时配置。

新插件 manifest：

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

复用现有环境变量解析；不为新增插件强制增加 LLMProfile 依赖，其他远程任务服务不需要这种配置形状。配置和依赖在新插件中验证，核心只验证公共入口与授权。主配置已加入这一独立入口；安装与平台边界见新插件 README。

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
| 桌面独占（首轮） | Tank 任务运行上下文获取同一桌面资源锁 | 同进程 computer_use/n2/n2_sdk 任务互斥，取消/失败正常清理后释放；清理未确认则隔离资源 |
| 暂停（第二步） | SDK on_run_continue 等安全边界；Supervisor 持有运行 handle | 当前完整工具调用结束并释放输入状态后才确认 paused |
| 同进程恢复（第二步） | 插件保留运行实例或完整工具轮次的 trajectory | 重新观察桌面后继续；不直接执行旧截图上的剩余动作 |
| 重启恢复（后续） | 插件 snapshot + WorkerStore | 保存格式版本、SDK 版本、累计预算、cwd/环境 ID、未确认动作；重建后验证现场 |

SDK resume 是追加消息继续已有历史。首次只允许在完整工具结果边界保存并恢复；中断导致“动作可能已发生、结果未确认”时先检查结果，不自动重放。暂停期间用户接管桌面后需要重新观测；如在工具开始前已有模型计划，丢弃该计划并返回明确未执行结果，要求重新规划。

首轮不改 WebSocket 协议和 web/macOS 控件；仍通过 agent_status / agent_stop 控制任务。第二步增加 agent_pause / agent_resume、运行 handle 及状态迁移，届时再更新前端和协议（如确有新增公共消息）。waiting（等待用户答案）与 paused（主动暂停）不得混用。

安全控制采用任务审批 + SDK 支持的 hooks + 专用运行环境。插件 permissions 决定请求范围，用户授权决定本次放行；SDK 工具禁用只缩小模型工具面，不能限制 shell 经其他途径访问资源。Python 同进程插件是受信任代码；强制约束第三方插件需要独立进程和系统权限隔离。

现有旧路径取消限制保留为 baseline 的已知属性：DesktopExecutor.bash 使用 to_thread(subprocess.run)，取消 asyncio 等待不保证杀掉后台线程中的 shell。新 SDK 路径必须验证环境的真实取消能力；不能把 task.cancel 当作已清理的证据。

## 6. 文件改动清单

下表是实施范围，已落地项和剩余验收见 §10 与 §13。现有文件优先局部扩展；新文件
仅用于公共契约、facade、共享桌面资源锁和新 SDK 插件。

| 文件 / 目录 | 改动 |
|---|---|
| `backend/core/src/tank_backend/agents/subagent.py`（新增） | 公共任务请求、上下文、能力、SubAgent ABC / observer |
| `agents/subagent_adapter.py`（新增） | 将 SubAgent 包装为当前 AgentRunner 可消费的 Agent facade |
| `agents/resources.py`（新增） | 同进程共享桌面资源锁、清理失败时隔离资源；内置 computer_use/旧 n2/新 n2_sdk 都复用 |
| `agents/definition.py` | 新增 extension；拒绝与 engine 同时出现；旧字段保留 |
| `plugin/manifest.py`、`plugin/registry.py` | subagent 类型、permissions、返回类型验证；agent / needs 保留 |
| `plugin/manager.py` | 新类型发现及注册；通用 registry 能复用的部分不改 |
| `config/app_config.py` | subagents 配置入口解析/校验；现有 agent_engines 保留 |
| `agents/runner.py` | 新 extension 分支、facade、授权和预算上下文、桌面锁；engine 分支保留 |
| `agents/agent_tool.py`、`agents/approval.py`、`tools/confirm_action.py` | 按 permissions 派发审批；确认回调激活凭据，拒绝/扩大范围失效；旧 desktop_executor 审批保留 |
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

仓库 `backend/core/config.yaml` 已配置下面的旧 N2 profile 和 engine；测试机
先核对，不要重复合并。新增 SDK 配置将独立放入同一主配置的 subagents
段，插件 config.example.yaml 只是示例，不会自动合并。在 backend/core/.env
设置 `YUTORI_API_KEY`，或在启动 backend 和 benchmark 的各自 shell 中
export。不要打印或提交 key。旧配置的名称必须对应：

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

用户已确认 macOS 计算器操作正常。完成通知曾因复用旧 DeepSeek 会话缺少
reasoning_content 失败；[兼容修复](../done/n2-notification-and-tracing-fixes.md)
已提交，真实 DeepSeek 请求通过，但 macOS 完整通知仍需 M6 复测。
独立的 Langfuse 连接失败不作为桌面操作失败评分。

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

## 10. 分阶段实施与验收

首轮交付范围为 M0–M6：可选择的官方 SDK 插件、通用派发入口、授权、
预算/停止/清理、可比较的 benchmark 与实机验收。M7 在采用新路径后实施，
不阻塞首轮试用。跨重启恢复、第三方服务插件和删除旧 engine/executor
都不在首轮实现范围内。每个里程碑先失败测试再实现，独立提交。

执行依赖：M0 → M2 → M3 → M4 → M5 → M6；M1 可在 M0 后先完成，
其修正代码及真实 baseline 必须在 M6 对比前到位。M7 仅在 M6 采用后
触发。首轮不等待旧 baseline 才能开发 SDK 插件，但不能跳过 baseline
就声明改进。每阶段失败先修复并重测，再更新该阶段勾选与提交。

### M0 — 固定 SDK 与运行环境边界

- [x] 在新插件 pyproject 中固定候选 `yutori[macos]==0.9.29`，更新 uv.lock；
  新插件内部验证配置，公共核心不导入 yutori。
- [x] 用无网络的实际 SDK + fake completions/computer 验证 run 输出、
  callback 顺序、stopped_by、compaction 调用路径和 aclose 所有权。
- [x] 明确 MacOSComputer 的 cua-driver 启动/授权需求和 CancellationLatch
  传递方式；SDK Agent 的 aclose 只关闭自有 client，插件还必须关闭
  environment 与自行注入的 completions client。
- [x] 编写能力矩阵：macOS 可实施、Linux X11 待 M4 验收、Wayland 明确
  unsupported。不支持平台在模型请求和动作开始前报错。

验证：现有 `backend/plugins/agent-n2/tests/test_n2.py` 不变并通过；新增
`agent-n2-sdk/tests/test_sdk_contract.py` 使用实际固定版本，无付费 API、
无宿主机输入。若必要控制 hook 无法使用，先更新本计划的版本/边界，
不自写替代 SDK loop 来绕过限制。产出 SDK 契约测试、版本与环境说明。

### M1 — 修正评测口径与旧 baseline

- [x] pageserver/runner 每 trial 建立独立 capture 和随机 trial token；
  BENCH_ASSETS_URL 包含本 trial 路径，页面提交携带 token；关闭 trial 后
  拒绝旧 token/迟到提交，validator 只读该 trial 文件。
- [x] 修改现有 assets 与受影响任务 setup/validator，不只清空共享文件；
  新评分 revision 写入报告。无法完整自动验证的任务标记 smoke，并在
  报告单独统计，不混入严格成功率分母。
- [x] driver 在工具开始前检查 max_steps，到边界不执行、不计额外一次；
  保留 steps=已开始的 tool call，batch 原语数与模型轮数另记。
- [x] 报告明确 agent_name、engine/extension、git/task/scoring revision、
  配置摘要、平台/显示尺寸、SDK 版本、终止原因和清理状态；不存凭据。
  流式 TTFT 与非流式 RTT 分列，保留旧字段的兼容读取并标明旧报告口径。
- [ ] 修正后在同一测试机重跑 computer_use 和 n2 的 baseline；暂未拿到
  真实报告不阻塞 M2–M5 开发，但阻塞 M6 的“效果改善/采用”结论。

验证：扩展现有 test_bench_pageserver/test_bench_runner/test_bench_report；
前 trial 成功、后 trial 无提交必须失败；异步迟到请求、旧标签页、步数
边界都覆盖。旧报告仍可读，不能换算为新评分。产出独立 benchmark 修复
提交与新 baseline 报告；用户负责真实桌面跑批。

### M2 — 最小公共契约与插件入口

- [x] 实现 §3 的 request/context/capabilities/SubAgent 与 facade；
  observer 可选，但运行账本和取消/截止时间必传，工厂只接收插件配置。
- [x] definition 新增 extension，与 engine 互斥；manifest 新增 subagent
  类型与 permissions；registry 验证返回类型和明确的重复入口错误。
- [x] AppConfig 解析主配置 subagents 段，Runner 新 extension 分支复用
  当前 definitions/agent 工具目录。先检查目录是否已自动覆盖 Markdown
  新定义；若已覆盖，不为此修改 Brain 的目录生成逻辑。
- [x] 注册一个仅测试用 fake subagent，经过完整工具→Supervisor→Runner
  路径输出活动、usage、DONE；不新增生产 fake 插件或第二套调度器。

验证：扩展 test_plugin_manifest、test_agent_engine_seam 与新公共契约测试，
覆盖格式错误、类型错误、缺失插件和关闭异常；核心测试环境不安装 N2
插件仍通过，旧 engine 配置/派发不变。产出可被其他插件复用的入口提交。

### M3 — 授权、结果与桌面资源控制

- [x] AgentTool 根据 manifest permissions 触发审批；把本次授权作为
  运行上下文显式传给 Supervisor/Runner，不能仅用工厂 config 字段代替。
  无授权/已撤销时禁止 environment 启动和新动作。shell/filesystem/network
  的权限展示和策略接线独立于 desktop，不默认绕过已有相应审批。
- [x] Supervisor 传递持久 worker task_id；Runner 保留内部 agent_id，
  不混用。facade 将 DONE 结束原因送回 Supervisor：final_answer 正常
 结束才 completed；budget/max_steps/context_limit 为 failed 并注明原因，
  SDK timeout 为 timeout；工具可恢复错误不等同于整个任务失败。
- [x] 新路径不得落入 Runner 当前“捕获异常后只 yield TOOL_RESULT”的
  成功路径；通过明确 terminal outcome 传递错误，避免流结束即 completed。
  无 DONE、未知 stopped_by 或清理失败必须显式失败。
- [x] resources 在同进程内共享桌面锁，内置 computer_use、旧 n2、新
  n2_sdk 的任务外层使用同一资源 ID；先获授权再取锁，再创建环境。
  锁等待计入截止时间且可取消，取消/初始化失败正常释放。
- [x] 清理无法确认时隔离该资源并拒绝下一桌面任务，直到人工核实后
  显式解除。锁不自动保护主会话直连工具或独立 benchmark 进程，实机
  A/B 仍须停止其它桌面任务并串行执行，不宣称跨进程排他。

验证：扩展 test_computer_approval、test_agent_tool_supervisor 与 worker
supervisor 测试；用 fake 工厂断言未批准零启动，三组互斥、等锁超时、
结果错误不会 completed。产出通用控制提交；旧 N2 loop/executor 不重写。

### M4 — 官方 Agent 插件与平台环境

- [x] 新增 agent_n2_sdk/{agent,config,environment,callbacks}.py 及 manifest、
  config.example.yaml、README；每个任务创建官方 N2ComputerAgent，
  通过 SDK 的公共 run/callback 接口转换现有 AgentOutput。
- [x] 插件拥有一个 SDK 运行 task，callbacks 经有界队列向 facade 输出
  事件；工具开始事件取自开始 callback，不能等工具完成后才回放为
  executing。SDK yield 用于轨迹/结果核对，不再重复生成同一调用事件。
  消费者退出时取消并等待 producer，再关闭资源，避免遗留后台循环。
- [ ] macOS 首先接入原生 MacOSComputer，明确单屏全桌面 scope；modifiers
  能力按实际 environment 声明。Linux 从 direct-X11 示例适配，保存
  来源/许可证；独立验收，失败保持该平台 unsupported。
- [x] 增加 n2-sdk.md，name=n2_sdk、extension=agent-n2-sdk:agent；在主
  config.yaml 增加独立 subagents 配置。保持原 n2 名称与配置，不自动
  把“使用 N2”的请求切换到 SDK；试用明确指定 n2_sdk。
- [ ] environment 每次动作/原语前检查授权、取消、预算与截止时间；
  shell 管理自有进程/进程组，取消后等待退出；输入状态在 finally 释放。
  SDK 关闭、environment 关闭与外部 client 关闭均幂等并有清理期限。

验证：新插件用实际 SDK + fake environment/completions 测试多 tool call、
batch 首错即停、modifiers、原始 reasoning/图片轨迹与每个 stopped_by；
模型请求/拖拽/hold_key/bash/环境初始化中取消，以及事件消费者提前关闭
和队列背压都覆盖。可靠取消未通过的平台不声明 cancel=true，也不进入
正式评测。产出可派发插件提交。

### M5 — 预算与 benchmark 新路径接入

- [x] completions wrapper 给每次实际返回建立 call_id，响应一次计账；
  actor callbacks 只转发事件，不能重复计账。compaction/retry 的调用
  使用相同 wrapper；隐藏的传输重试注明 logical call 口径。
- [x] request 前、响应后及动作前检查同一账本。Runner 对 extension
  只读取共享总量，不再累加 USAGE 一遍；旧路径计数继续沿用现有方式。
  usage 缺失终止；缺失 token 与明确零 token 不混用。在途取消无 usage
  记录 unknown，不报告为已知零成本或精确用量。
- [x] observer 收集完整 API 时序、调用类型、工具状态、PNG/WebP 截图；
  driver extension 路径无需旧 executor monkey-patch。生产无 observer
  仍可正常运行并执行预算约束。
- [x] benchmark 同一个 Runner 接入 n2_sdk；清理结束后才执行 validator
  和 teardown，清理失败保存 trace 并停止 suite，不能继续下一 trial。

验证：新增 fake compaction/retry/budget 测试，并扩展现有 benchmark 测试。
预算耗尽后零新动作，USAGE 唯一、无 observer 正常、截图 MIME 正确、
取消调用 unknown 和清理失败停批均验收。产出计账/评测接入提交。

### M6 — 完整链路与同环境采用决策

- [ ] 扩展现有 test/features/chat.feature，SDK 与环境使用测试进程的
  fake 注入，覆盖审批拒绝/批准、后台派发、活动/状态、停止、失败和
  完成通知；现有 WS frame 转换器在同一进程验证，真实客户端传输由
  既有 E2E 单独覆盖，无付费 API 与宿主机输入。该组合尚不等同于
  在完整主会话 WebSocket 中注入 SDK 的端到端验收。
- [ ] 用户分别实测旧 n2 与 n2_sdk：§7 的计算器、浏览器、文件任务，
  加一项专用环境中的系统设置修改后恢复；复测旧 DeepSeek 会话通知。
  记录结果证据，不把 bash 文件写入当作纯 GUI 完成。
- [ ] 分别在模型请求、batch、拖拽/按键保持、shell 中停止；观察 10 秒
  无新动作、输入释放、自有进程退出；再派发新任务确认正常资源释放。
  Linux 中文输入/修饰键/截图时延和 X11 adapter 分平台记录；截图含光标
  行为用实际图像核对，不以 doctor 截图成功代替。旧计划 <500ms 的截图
  目标记录是否达到，不用放宽 doctor 阈值冒充已通过性能验收。
- [ ] 按 §8.1 在 M1 修正后的同一版本交替跑三组，每任务先 3 trial；
  明确 smoke 分数、失败原因和无法对齐参数，保存 report/trace/截图。
  补长任务触发 compaction，短套件不能证明长任务改进。
- [ ] 采用门槛：严格任务成功率无明显回退，控制/预算/清理验收全部通过，
  观测完整且耗时/平台能力可接受。结论不明确则扩大边界任务样本；
  未通过保留 n2 继续修复，不清理旧路径。
- [ ] 每个行为里程碑更新现行架构和测试文档；M6 写入实际结果和采用
  决定。M0–M6 完成后，如 M7 尚未满足触发条件，将其移交 backlog，
  再归档本计划，不能静默标记暂停/恢复已完成。

产出首轮实机验收与 A/B 报告提交。原计划待验收项由本阶段追踪，不再
回写为原计划实现未完成。真正删除 engine/executor 必须另开清理计划。

### M7 — 采用后同进程暂停与恢复

触发条件：M6 确认采用 SDK 路径，且需要主动暂停/接管/恢复。

- [ ] 扩展 capabilities 与 Supervisor 运行 handle；新增 agent_pause /
  agent_resume。暂停请求阻止后续新工具调用，当前调用在完整结果与输入
  释放边界才确认 paused；pause_pending/paused 与 waiting 分开表达。
- [ ] 保留活实例/完整 trajectory，同进程恢复先重新截图，丢弃旧计划，
  通过 SDK resume 追加现场变化与新任务说明；授权和累计预算不重置。
  暂停释放桌面锁，恢复重新申请锁；暂停期间 stop 仍可清理终止。
  首版暂停时间计入原截止时间，不无限延长任务；过期后恢复返回 timeout。
- [ ] 更新 worker 状态模型、store/REST、通知与现有客户端状态展示；
  只有新增公共消息时才扩展协议并生成同步 artifacts。
- [ ] 验证重复暂停/恢复、正在暂停时停止、用户改动桌面、授权撤销、
  已耗尽预算、已关闭实例与恢复失败；扩展同一 chat.feature。

跨进程/重启恢复另行立项，需要 trajectory 格式版本、SDK 版本、环境
身份和未确认副作用校验，不以同进程 resume 测试证明。

## 11. 本轮计划更新验证

本轮仅更新计划/归档与索引，不实施上述代码、不调用 N2 API 或操作桌面。
官方 SDK 检查只下载候选 wheel 到临时目录读取源码，不安装依赖。
静态检查、全量回归、E2E 和运行日志核对结果在提交前记录；改动 Python
类型检查为 N/A。既有运行检查限制保留，不以文档关档隐藏错误。

- web lint/TypeScript、backend/CLI ruff、文档一致性、协议同步与
  git diff --check 通过；仅文档修改，pyright 为 N/A。
- E2E 10 场景、39 步骤通过。开发后端 `/api/health` 正常，后端日志最后
  50 行无错误；Vite pane 仍有 WebSocket 断开错误，运行日志检查未全绿。
- 首次全量回归一项真实 Edge TTS 测试遭遇服务端 503；单项重跑通过，
  全量复测 4276 passed、2 skipped、16 warnings（157.60s）。单项重跑
  退出时仍有异步生成器任务清理错误，不修改与此次文档工作无关的 TTS
  实现，也不据测试断言通过宣称运行检查全绿。

## 12. 最终 Verification Checklist（每个实现里程碑的最后一步）

1. `cd web && pnpm lint`。
2. `cd web && npx tsc -b --noEmit`。
3. `cd backend && uv run --package tank-backend ruff check core/src/ core/tests/ contracts/ plugins/`。
4. `cd backend && uv run --package tank-backend pytest`（全部 workspace 测试）。
5. `cd backend && uv run --package tank-backend pyright <本轮修改的 Python 文件>`；只改文档时 N/A；禁止以 type: ignore 掩盖错误。
6. `cd cli && uv run ruff check src/ tests/`。
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`；无匹配为通过；有匹配检查具体 backend/web pane 与当前运行状态，报告并处理错误。
8. `cd test && pnpm test`；backend/frontend 必须已运行。
9. `python3 scripts/check_docs.py`。
10. `python3 scripts/check_protocol_sync.py`。

## 13. 实现记录（2026-09-17）

已提交固定 SDK 契约、通用 SubAgent 与授权/桌面资源控制、官方 SDK 插件。
评测新路径、trial 隔离和自动化派发测试已落地。Markdown loader 已覆盖
n2_sdk，所以无需修改 Brain 的目录生成；旧 n2 定义/配置/loop/executor
保留。工厂只收插件 config，授权/共享预算/截止时间由 Runner 创建。

M4 当前可实施平台为 macOS 原生 MacOSComputer；Linux X11 没有启用
adapter，Wayland 明确 unsupported，在 driver/模型启动前失败。候选
固定版本的原生 adapter 用原子手势模拟 mouse/key held 状态，modified
scroll 不支持；已在插件 README 写明，不把这一能力当作持续物理按住。
M4 的 Linux/真实输入/进程清理项与 M6 的物理停止验收仍保持未完成。
SDK 自有 client、插件注入 client 与 environment 的关闭所有权已确认；
插件等待 producer 后分别清理，失败进入资源 quarantine。

自动化证据包括实际固定 SDK + fake completions/computer，覆盖 callback
事件、retry/compaction 唯一计账、预算后零动作、模型/初始化/动作取消、
消费者提前关闭与背压、缺失 usage、平台拒绝及关闭异常。公共 seam 测试
覆盖无授权零启动、确认后才激活凭据、拒绝/权限扩大失效、绑定任务
审批、稳定 task_id、三路径桌面互斥、等锁
超时、结束原因与清理失败。SDK benchmark 经过实际 Driver.create/Runner
入口，计账与截图走 observer，未注入 DesktopExecutor。

评测评分 revision 为 trial-token-v2；每 trial 独立 capture/随机 URL token，
结束 driver 后关闭 token，再运行 validator；迟到/旧标签页返回 410。
进程存在型 calculator/settings 为 smoke，排除严格分母；文件保存/复制/
拖拽 validator 加强内容核对。历史报告字段兼容保留，不能等同新评分。
没有真实 baseline/A-B 报告，不宣称效果改善或已采用；由用户按 §7/§8
在同一专用 macOS 桌面跑旧 n2 和明确指定的新 n2_sdk。此计划继续 active，
不归档，也不启用暂停/恢复。

新增 chat.feature 的四个隔离进程场景验证实际 AgentTool/ConfirmActionTool
→ Supervisor → Runner → 官方 SDK → WorkerStore/status/stop/NotificationHub
以及现有 WS frame 转换器。其与既有 live client E2E 分开覆盖；尚未在
完整主会话 WS 内做 SDK fake 注入，M6 第一项保留待验收。

最终自动化验证：

- 全量 backend pytest：4330 passed、2 skipped、16 warnings（167.38s）。
- E2E：14 scenarios / 55 steps 全部通过；test TypeScript 检查通过。
- web lint 与 `tsc -b --noEmit`、backend/CLI ruff，以及全部本轮修改
  Python 文件的 pyright 通过（0 errors、0 warnings）。
- 文档一致性、协议同步与 `git diff --check` 通过。
- 运行后端 health 正常、后端最近 50 行无异常；Vite pane 仍有既有
  WebSocket 关闭 EPIPE/ECONNRESET 日志，运行日志检查未全绿。

未修改前端/协议控件，也未调用付费 N2 或注入宿主机输入；上述自动化
结果不代替尚未完成的完整 SDK 主会话 WS 注入与实机验收。

## 14. macOS driver 启动失败排查（2026-09-17）

用户实测已通过审批和后台派发，在 MacOSComputer 进入环境时 MCP 子进程
退出 1，尚无模型 token。日志没有 driver 的具体拒绝原因，不能仅凭退出码
认定为权限问题。固定 SDK 会丢弃 stderr，插件保留最后 8192 bytes，并将
启动失败详情与 doctor 检查提示带入 worker 错误。实际 Mac 的 doctor 输出
和修复后计算器结果仍待确认。

补齐同版本 CuaDriver.app 的安装、启动与权限检查说明；默认 MCP 是独立
app daemon 的代理，worker 拥有代理/会话，不拥有可能共享的 daemon。
去掉审批 update 中协议未声明且客户端未使用的 permissions metadata；
权限范围仍完整保留在审批正文，运行凭据范围校验不变。

### Tests

- 实际 SDK transport 启动会退出 1 的测试子进程，验证 stderr 保留、
  大量输出有界、空输出时 doctor 指引以及子进程退出。
- 现有审批 seam 测试验证权限正文完整且 update metadata 遵守现有协议。
- 最后执行 §12 完整 Verification Checklist，并记录本轮结果。

验证结果：backend 全量 4333 passed、2 skipped、16 warnings（169.48s）；
E2E 14 场景 / 55 步骤通过；web lint/TypeScript、backend/CLI ruff、改动
Python 文件 pyright（0 errors、0 warnings）、文档/协议同步及 diff 检查
通过。后端 health 正常且最近 50 行无异常；Vite 仍有 WebSocket 关闭
ECONNRESET 日志，运行日志检查未全绿。以上只证明诊断补丁与回归通过，
不证明用户 Mac 的 driver 启动问题已经解决。

## 15. 首次截图超时与重连错误（2026-09-17）

用户后续日志明确显示 app daemon 与 Python wheel 的 contract 0.8.0/0.7.0
不匹配；当前官方 SDK 固定组合继续使用 cua-driver 0.23.2，不跳过契约检查。
降级后握手/start_session 已通过，但首次 get_desktop_state 在 30s 超时。
SDK 默认 read-only 重连会关闭旧 MCP lease，结束 task session，随后重试
同一 session 得到 session ended，掩盖最初的超时。

插件的 session-bound tool RPC 单次执行，不自动重连或重放。连接失败
保留工具名称/原始错误/stderr；不确定的修改动作不重试。失败连接禁止
开始后续动作，仅允许在尚存连接上执行 end_session；清理失败继续按
既有 quarantine 处理。不改模型 API retry/compaction 或 SDK Agent loop。

用户随后执行 permissions grant，确认辅助功能、屏幕录制与 Direct Capture
均已授权。此前 status 的 Direct Capture 为 not checked；直接截图授权
就绪与首次截图超时现象一致，但尚未取得计算器结果，不认定为实机任务
完成。安装说明补上停止旧 daemon、核对 app 版本、实际 capture 授权，并
说明 macOS doctor 不能证明运行权限。

### Tests

- 实际 SDK transport + 测试 MCP 子进程，复现 read-only 截图超时与
  修改动作确认丢失；断言初始化一次、动作一次、不重连/重放、只允许
  后续会话清理，并保留失败类别和工具名称。
- 最后执行 §12 完整 Verification Checklist，记录全量回归结果。

验证结果：backend 全量 4335 passed、2 skipped、16 warnings（169.33s）；
相关 SDK/seam 54 测试与 E2E 14 场景 / 55 步骤通过。web lint/TypeScript、
backend/CLI ruff、改动 Python 文件 pyright（0 errors、0 warnings）、
文档/协议同步与 diff 检查通过。后端 health 正常，最近 50 行无异常；
Vite 仍有 WebSocket 关闭错误，运行日志检查未全绿。macOS Direct Capture
授权输出已取得，计算器任务的实际完成证据仍待确认。

## 16. 空闲 Brain 队列阻塞后台图片读取（2026-09-18）

用户在实际 Mac 上验证同一个 CheckedTransport MCP session：文件截图
0.207s、内联截图 0.185s，内联 base64 长度 1,329,092。该测试证明当前
driver 的 MCP/session 截图链路可以成功，不证明 Tank 内部的运行环境相同。

ThreadedQueue 在消费线程的 asyncio loop 内同步执行 queue.get(timeout=0.1)。
Brain turn 返回后，后台 worker 和 SDK 子进程读取仍共享该 loop；空闲队列
会反复阻塞其 I/O。Linux 对照实验读取同等大小的子进程响应：独立 loop
0.012s，加入原空闲等待逻辑后 3.791s。实际队列消费路径的回归测试在旧
代码上发生读取超时。将阻塞输入等待移到 executor，保留 bounded queue、
停止轮询和既有背压行为；不修改 SDK 图片格式、RPC 超时或模型 loop。
修复后经过实际队列消费路径读取同等大小响应为 0.011s。

这处阻塞已本地复现，尚不能认定为 Mac 30s 超时的全部原因。修复后仍需
在 Mac 重跑完整计算器任务，取得实际模型调用和计算器结果。

### Tests

- 实际 ThreadedQueue async 消费路径与实际子进程管道并行，验证空闲时
  仍能在 1s 内读取 1,329,092 字符的图片响应；旧代码先失败。
- 现有队列停止/背压/不丢消息、后台 worker 与 SDK 回归测试。
- 最后执行 §12 完整 Verification Checklist，记录全量回归结果。

验证结果：队列/后台 worker/SDK 相关 60 测试通过；backend 全量
4336 passed、2 skipped、16 warnings（168.60s）；E2E 14 场景 / 55 步骤
通过（55.135s）。web lint/TypeScript、backend/CLI ruff、修改 Python
文件 pyright（0 errors、0 warnings）、文档/协议同步与 diff 检查通过。
后端 /api/health 正常且最近 50 行无异常；Vite 仍有 WebSocket 关闭
错误，运行日志检查未全绿。Mac 计算器任务仍待修复后的完整实测。
