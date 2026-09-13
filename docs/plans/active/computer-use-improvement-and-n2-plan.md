# Computer Use 改进与 Navigator n2 接入方案

> 状态:阶段 3 实现中(2026-09-13)——设计已批准(§14):EV_ABS 自建绝对指针先行+A3 原语+A9/A8/A6+A15;阶段 2 收口(macOS T1 全绿,Linux 键盘族绿/指针移交本阶段)。执行阶段划分见 §12。
> 日期:2026-08-28(初稿)· 2026-09-08(修订:对齐 worker/subagent 现状)· 2026-09-09(执行启动+事实修订:plugin.yaml manifest、NotificationHub、A5 现状)
> 关联:Yutori [Navigator n2 发布博客](https://yutori.com/blog/introducing-n2) · [API 参考](https://docs.yutori.com/reference/n2) · [Python SDK](https://github.com/yutori-ai/yutori-sdk-python) · Anthropic [computer-use-demo](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo)

## 0. 结论摘要(第 2 版修订)

1. **n2 是"引擎",不是"大脑",且没有服务端 loop。** 它只通过 Yutori API 提供(无开源权重),自带 5 个固定工具(`computer_batch`/`bash`/`read`/`write`/`edit`),由模型返回 `tool_calls`、**我们的客户端在真实桌面上执行**。它不消费我们的工具 schema,也不能当通用对话模型。所谓"自己的 loop/消息管理"是 SDK 里的客户端循环(~几十行,可自写)加一组协议硬规则(reasoning 回显、全量历史回传、图片保留)——适配器层的翻译工作,不是架构冲突。
2. **执行器(控制电脑的代码)无论如何都要自研**——官方生态没有任何 Linux 实现:Yutori 只有 macOS 闭源驱动 CuaDriver.app;Anthropic demo 只有 Docker 里的 X11。我们仓库已有 Linux + macOS 双平台实现,起点反而领先。
3. **现状已是子代理委托,不是 ChatAgent 直调工具(初稿盘点过时)。** `agent` 工具(AgentTool)→ WorkerSupervisor(持久化、深度/并发限制、agent_status/agent_stop、后台派发 + inbox 回注)→ AgentRunner → LLMAgent;computer use 已由 `backend/agents/computer_use.md` 子代理承担(专用视觉模型 profile + toolset + `background: true` + 300k 预算),多步循环在子代理内。初稿 Part B 的 `computer_task` 工具是在给"不存在的缺口"打补丁。
4. **Part B 修订为 agent 插件架构**:删 `computer_task` 工具与 `ComputerUseEngine` 契约;改为 `AgentDefinition` 加 `engine:` 字段 + runner 工厂分支(`runner.py:177`),插件实现 Agent ABC。原则:**脑在插件(协议+循环+消息管理),手在 executor(注入的 DesktopExecutor)**——supervisor/审批/进度/取消全部复用现有机制,零新任务级入口。
5. **Part A 与 Part B 依旧互相独立。** Part A 全部是通用改进,现有 computer_use 子代理路线直接受益;Part B 依赖 Part A 产出的 DesktopExecutor,反之不成立。放弃 n2 对 Part A 零损失。
6. **n2 是否真的更好无法先验确知,基准是决策依据。** 模型差距(OSWorld-Verified 85.3% vs GPT-5.4 系 47–63%)真实,但兑现受执行器质量与任务分布折扣。A17 基准套件先量现状 baseline,Part A 后重跑,n2 插件后同尺 A/B——引入决定从信仰跳跃变为测量。
7. **设计原则已裁决**:凡行业收敛的正确设计(归一化坐标、batch 首错即停、reasoning 回放、截图经济学)吸收进核心;凡 n2 协议特例(`tool_set`、禁参、tool 消息图片装填)封进 agent-n2 插件。核心代码零 n2 痕迹。
8. **安全模型(文档化取舍)**:任务级审批在 agent 工具派发点;动作全部经注入的 DesktopExecutor(红线在此层统一生效);逐动作审批/hooks/tool_guardrails 对插件 agent 失效——GUI 循环逐动作审批本就不可用,取舍记录于 §9 B4。
9. **验证环境**:开发 VM 无图形会话(实测 `SESSION=tty`、mss 未装,Linux 工具组连注册都不会);Linux 路径验收需 GUI VM(GNOME Wayland);macOS 路径上真机;开发 VM 只承担单测与 harness 代码。

---

## 1. Navigator n2 调研

### 1.1 模型事实

| 项目 | 内容 |
|---|---|
| 形态 | 27B,Yutori API 独家托管,model id `n2`,OpenAI `chat.completions` 兼容 |
| 发布 | 2026-08-26(Linux/macOS/Windows 全桌面;n1/n1.5 仅浏览器) |
| 基准 | OSWorld-Verified 85.3%、OSWorld 2.0 65.2%($1.46/任务)、MyPCBench 82.6%、MacAgentBench 83.1% |
| 价格 | $0.50/M 输入($0.05/M 缓存),$4/M 输出 |
| 对比 | Claude Opus 5 OSWorld 2.0 70.6% 更强但贵一个数量级;GPT-5.4 系 47–63% |

### 1.2 协议契约

**内建工具集** `computer_use_tools-20260825`(顶层参数 `tool_set` 指定,不能传自己的 `tools`):

| 工具 | 行为 |
|---|---|
| `computer_batch` | GUI 唯一入口:一次调用执行 15 种原语序列,返回批后一张截图 |
| `bash` | 真机 shell,每调用独立进程,**cwd 跨调用持久**,env 不持久 |
| `read` | 文本文件,`cat -n` 格式 |
| `write` | 写文件(建/覆写),优先于 bash heredoc |
| `edit` | 精确串替换,**强制先 read 过** |

**15 种 batch 原语**:mouse_move、click、double_click、right_click、triple_click、middle_click、mouse_down、mouse_up、drag、scroll、type、key_press、hold_key、wait、screenshot。

**batch 执行语义**(执行器必须遵守):
- 动作顺序执行;**首错即停**,剩余动作跳过并在 tool result 里报告哪个动作失败;
- 所有坐标基于**批前**截图;
- 每个调用回**一个** tool result,只带**一张**批后截图。

**其它关键规则**:
- 坐标:归一化 1000×1000,原点左上;SDK 循环负责映射到截图实际分辨率;
- 截图:必须全屏(含任务栏),WebP ~80% 压缩,请求上限 10MB(413);
- **拒绝** `max_tokens`(422);`temperature: 0` 不推荐;未知参数静默剥离;`prompt_cache_key` 收下即丢;
- `parallel_tool_calls` 钉死 true——一轮回多份 tool_calls,每份都要独立结果;
- reasoning 默认开(medium),`reasoning_content` 必须原样回显(assistant 消息整体 `model_dump(exclude_none=True)` 追加);
- 历史必须全量回传;服务端保留最后 2 条带图消息(各 ≤6 图),更早的图丢弃;
- 系统提示只叠加不可覆盖;任务指令放第一条 user 消息。

### 1.3 官方生态盘点

| 组件 | 内容 | 对我们的意义 |
|---|---|---|
| Python SDK `yutori` | `N2ComputerAgent` 循环 + 编码/坐标助手 | 可选。循环 ~几十行可自写;助手函数可单独借用 |
| Daytona 示例 | ~95 行适配器,**调用 Daytona 平台自带的控制 API** | 证明适配器模式;不含底层控制实现 |
| yutori-mcp | 本地控制仅 macOS 15+(闭源 CuaDriver.app,要录屏+辅助功能权限;一次只跑一个前台任务) | 无 Linux 实现 |
| 裸调 | 文档按裸消息协议写,SDK 非必需;endpoint 大概率 `https://api.yutori.com/v1`(待控制台确认) | 可用现有 AsyncOpenAI |

**结论:底层"如何控制电脑"官方任何平台都没有现成品,执行器注定自研。** 顺带:我们已有双平台(Linux portal/ydotool + macOS Quartz/screencapture),平台覆盖超过两家官方参考。

### 1.4 定位结论

- 适用于:"帮我操作电脑做 X"类任务,作为经 agent 工具派发的插件子代理(WorkerSupervisor 调度);
- 不适用于:替换对话主模型;无头服务器;不接受截图上云的场景(全屏截图会上传 Yutori)。

---

## 2. 我方现状盘点

### 2.1 已有能力

- **桌面原语工具**(`tools/computer_use.py` Linux、`tools/computer_use_macos.py` macOS):screenshot、click、type_text、key_press、scroll、mouse_move(macOS 另有 launch_app);
- Linux 截图:XDG Portal(busctl)→ mss 回退;输入:ydotool(/dev/uinput,Wayland 可用)→ pyautogui 回退;
- macOS:screencapture + Quartz CGEvent,**已用归一化 0-1000 坐标**,已处理 Retina 缩放;
- **多模态链路完整**:ImageBlock → `image_url` 消息部分;工具结果可带图回模型(`llm/llm.py` tool stub + 后跟 user 消息);模态能力注册表。
- **子代理委托体系已存在(初稿遗漏)**:`agent` 工具(AgentTool)→ WorkerSupervisor(持久化 WorkerRunRow、深度/并发限制、agent_status/agent_stop、后台派发 + 结果回注——2026-09-09 核对:现为 NotificationHub,非早期 inbox observer)→ AgentRunner → LLMAgent;子代理 = `backend/agents/*.md` 配置(frontmatter:name/model/toolset/background/token_budget/disallowed_tools),全部经同一个内部 LLMAgent 类执行。computer use 已由 `agents/computer_use.md` 子代理承担:专用视觉模型 profile + `computer_use` toolset + `background: true` + 300k token 预算,多步 observe→plan→act→verify 循环在子代理内,主对话不背截图上下文。

### 2.2 已知缺口与风险

- **7 个 computer-use 工具全部 `category="general"`** → 走 `approval.py` 兜底分支**无条件自动放行**,而它们在宿主机裸奔(输入注入+截图);
- Linux/macOS 两套工具**坐标体系不一致**,且 `agents/computer_use.md` 系统提示已向模型承诺 0-1000 归一化坐标——Linux 工具收裸像素,提示在说谎(详见 §8 A1);
- 无 batch、无 drag/hold_key/mouse_down/up/wait、无自检命令(详见 §8)。

---

## 3. "谁不标准":图片进 tool 消息之争

| 方案 | 工具结果能否带图 | 性质 |
|---|---|---|
| 裸 OpenAI 协议 | ❌ 仅字符串 | 协议限制;OpenAI 自己的 CUA 用专用 `computer_call_output` 类型绕过 |
| 我方实现 | ✅ 语义支持,序列化用"tool 文本 stub + 后跟 user 消息" | 对裸 OpenAI 的标准 workaround,兼容面最大 |
| Anthropic | ✅ `tool_result` 原生内容块数组 | CUA 需要的"正确设计" |
| n2 | ✅ OpenAI 形状扩展,tool content 可为数组 | 实用主义扩展,方向同 Anthropic |

**裁决:三方都不算错,是协议演进灰色地带。** 我方核心保持现状(语义支持多模态工具结果,序列化细节留在 provider 边界);n2 的装填格式由引擎适配器处理,核心零改动。

---

## 4. 通用性设计:agent-seam 分层(第 2 版重设计)

> 初稿的 `computer_task` 工具 + `ComputerUseEngine` 契约写于 worker/subagent 体系落地之前,与现状重复造轮子。修订后删除两者,改为在现有 Agent seam 上扩展一个工厂分支。

**现状(代码事实)**:

```
主对话 LLMAgent(AgentRunner 驱动)
  └─ agent 工具(AgentTool)→ WorkerSupervisor → AgentRunner.run_agent
       └─ runner.py:177 无条件构造 LLMAgent —— 全仓库唯一耦合点
```

**修订后的目标分层**:

```
主对话 LLMAgent(内部实现,永远不参与插拔)
  └─ agent 工具 → WorkerSupervisor(零改动)
       └─ AgentRunner.run_agent 加一个工厂分支
            ├─ 缺省:LLMAgent(内部,吃 toolset/model 定义)
            └─ engine: plugin:agent → 插件 agent(实现 Agent ABC)
                 └─ 动作经注入的 DesktopExecutor(能力接口)
```

| 代码 | 属性 | 换模型时 |
|---|---|---|
| DesktopExecutor(原语/截图/bash/文件) | **通用** | 原样复用 |
| agent 工具 / WorkerSupervisor / 持久化 / agent_stop | **通用**(已存在) | 原样复用 |
| Agent ABC + AgentOutput 流 | **通用**(已存在) | 定义一次 |
| 归一化 1000×1000 坐标约定 | **通用** | Anthropic 同款约定,主流兼容 |
| `AgentDefinition.engine:` 字段 + runner 工厂分支 | **通用** | 机制与 n2 无关,任何外部 agent 复用 |
| plugins/agent-n2(agent.py + protocol.py) | **n2 专属** | 随 n2 退役 |
| yutori base_url/key/tool_set 配置 | **n2 专属** | 换新家的配置段 |

检验:第二个外部 agent(深度研究、浏览器代理、Anthropic CUA……)只需新写 `plugins/agent-*/` 并加一个 `.md` 定义,executor/supervisor/runner 一行不动——边界成立。

**边界约束**:

- 插件 agent 只做子代理(经 agent 工具派发);主对话 agent 永远是内部 LLMAgent,否则上下文管理/审批/checkpoint 语义全要跟着泛化;
- 插件 = 脑(LLM 客户端、协议、循环、消息管理),Tank = 手(动作执行 + 策略):n2 的 5 个工具(`computer_batch`/`bash`/`read`/`write`/`edit`)全部映射到注入的 DesktopExecutor,**不允许插件直连宿主机**;
- manifest(`plugin.yaml` 的 `extensions[]`,2026-09-09 核对:`[tool.tank]` pyproject 段说法过时)声明 `extension_type: agent` + `needs: [desktop_executor]` 能力依赖,Tank 按声明注入——没声明桌面能力的插件拿不到 executor(信任模型差异:asr/tts 插件执行"安装的代码",computer-use 插件执行"安装的代码 × 远端模型指令",爆炸半径大得多)。

## 5. LLM 配置复用结论

- **调用层不复用**:N2Agent 自建 `AsyncOpenAI`(max_tokens 422、tool_set、reasoning 回显、tool 消息图片——塞进通用 LLMClient 会污染所有模型共用的传输层)。
- **配置层复用凭据**:`llm:` 段加 `n2` profile 仅作端点+凭据名片,插件配置段用 `llm_profile: n2` 引用,并持有插件特有字段(tool_set、max_steps、reasoning_effort)。
- **插件不注册 LLM**:端点条目是静态 config,加一段即可;把 n2 包装成"新 LLM 传输实现"会诱导误配成 default,概念有害。
- 反例验证:标准协议的视觉模型路线 = 现状 `computer_use.md`(LLMAgent + 视觉 profile),不需要任何插件——agent 扩展机制只服务自带协议/循环的外部 agent。

## 6. 平衡点裁决:吸收 vs 隔离

**✅ 吸收进核心**(去 n2 语境依然正确,行业收敛):

| 做法 | 对 n2 之外的价值 |
|---|---|
| 工具结果可带图 | 已有,保持 |
| batch 工具 + 首错即停 + 批前坐标 | Anthropic/n2 语义一致,行业共识;我方 LLM 调 CUA 工具省 N 倍往返 |
| 归一化 1000×1000 坐标 | 换屏/换模型坐标可移植 |
| **reasoning 轨迹原样回放** | Anthropic thinking 签名与 n2 reasoning_content 是同一件事;核查 `llm/llm.py` 是否保留 reasoning_content——DeepSeek R1/Qwen thinking 等多家返回,纯通用改进 |
| 截图缩放 + 保留经济学 | 任何视觉调用受益;n2 缓存价 $0.05/M,全量历史回传实际很便宜 |

**❌ 隔离在 agent-n2 插件(protocol.py)**:`tool_set` 参数、拒绝 max_tokens、tool 消息图片装填格式、多 tool_calls 政策、`reasoning_content` 字段名差异、服务端图片保留规则。

## 7. 引入路径决策

| 选项 | 内容 | 评估 |
|---|---|---|
| **A(推荐)** | 先做 Part A + A17 基准,n2 后续可插拔 | 零风险验证接口缝;桌面能力立刻有;A17 产出 baseline,接 n2 零返工且可同尺 A/B |
| B | 核心 agent 扩展 + agent-n2 插件 | 能力直达 SOTA 性价比;引入新供应商;是否值得由 A17 数据裁决 |
| C | 不引入 n2 | 最简;桌面能力停留在通用视觉模型水平(computer_use.md 子代理路线) |

安全红线(无论哪个选项):全屏截图上传云端需告知用户;真机 GUI+shell 控制必须任务级审批;不给 sudo;bash 输出截断。

---

## 8. Part A:computer-use 工具独立改进计划(不依赖 n2)

> 全部条目对现有 ChatAgent 路线(gpt-5.4-mini 调我们的工具)直接生效;参照实现:Anthropic computer-use-demo(开源、实证)、CuaDriver(闭源,借鉴其架构模式:setup/doctor/smoke 自检流程、前台单任务约束、OS 权限引导)。

### P0 — 正确性

| # | 问题 | 现状证据 | 参照做法 | 改进 |
|---|---|---|---|---|
| A1 | **Linux/macOS 坐标体系不一致**:Linux 用裸像素且模型不知道屏幕分辨率;macOS 已是归一化 0-1000;`computer_use.md` 系统提示已向模型承诺 0-1000,与 Linux 工具实参矛盾(提示在说谎) | `computer_use.py:293`("X coordinate (pixels)");`computer_use_macos.py:310-319` 已有 `_normalized_to_pixel`;`agents/computer_use.md:13-18` | Anthropic 按纵横比缩到标准小分辨率后按比例换算;n2/Anthropic 均为相对坐标 | Linux 对齐 macOS:归一化 0-1000;截图结果文本回报实际宽高;屏幕尺寸进程内缓存 |
| A2 | **中文/Unicode 输入大概率损坏**:ydotool `type` 走 uinput 键码,非 ASCII 不可靠;Tank 是双语助手 | `computer_use.py:189-192` | — | 非 ASCII 走剪贴板粘贴路径(wl-copy/xclip + ctrl+v),粘贴前保存并恢复剪贴板;ASCII 直打;加自检用例 |
| A3 | **缺修饰键和弦/drag/hold_key/mouse_down-up**:修修饰键的点击会退化成普通点击 | Linux 无 down/up 分离;`computer_use.py:175-186` 仅 click | Anthropic 20250124 起支持 left_mouse_down/up、hold_key、drag;和弦 = keydown→动作→keyup;n2"整手势,退化比报错更糟" | 补 4 个原语:mouse_down/mouse_up(支撑 drag)、hold_key(keydown/sleep/keyup)、修饰键和弦包装 |
| A4 | **key 名翻译表过窄**:`cmd→"command"` 不是 Linux X keysym(应为 super/meta),`cmd+space` 静默错误;无标点词形映射 | `computer_use.py:406-407` | n2 词形规范(slash/comma…);Anthropic key 表 | 规范 key 名 → 各后端翻译表(X keysyms / pyautogui / AppleScript key codes);含 repeat 与连续按键 |
| A5 | **审批闸门缺失**:7 个工具 `category="general"` 全自动放行;任务级审批点(agent 工具派发)也无类别 | `computer_use.py:231,282,332,379,426,484`;`approval.py:109-113` 兜底 ALLOW | 行业均为任务级放行(GUI 循环逐动作审批不可用) | 新增 `computer` 类别 → 默认 require_approval。子代理路径为**任务级语义**:agent 工具派发 computer_use 定义时审批一次,循环内动作继承授权;主对话直连调用逐次审批(可在 config 降级) |

### P1 — 可靠性/成本

| # | 问题 | 现状证据 | 参照做法 | 改进 |
|---|---|---|---|---|
| A6 | **Portal 截图每次固定睡 ~3.3s**(0.3+3.0s),后台 `busctl monitor` + JSON 流解析脆弱;失败时 mss 在 Wayland 返回垃圾 | `computer_use.py:83,103` | Anthropic 用 CLI 一发即得(gnome-screenshot/scrot) | 改用正确的 portal D-Bus 调用(等待 Reply 而非睡等)或 GNOME CLI;后端探测一次并缓存;失败显式报告而非静默回退 |
| A7 | **每次移动鼠标先甩到 (-20000,-20000) 再相对移动**:两次子进程、光标横穿屏幕、首成功次失败则光标停在角落 | `computer_use.py:214-221` | Anthropic `mousemove --sync`(ydotool 无 sync) | 进程内跟踪光标位置,单次相对移动;移动后加 settle 延迟(~50ms)再点击 |
| A8 | **type 不分块无延迟**,`interval` 参数在 ydotool 路径被忽略 | `computer_use.py:189-192,363` | Anthropic:50 字符分块 + 12ms delay | 分块 + per-key delay;ydotool `--delay` 若可用则用之 |
| A9 | **scroll 无界**:amount 不钳制;滚轮格语义未定义 | `computer_use.py:205-212` | n2:1–50 格;Anthropic 按格 click | clamp + 明确"格"语义,文档化 |
| A10 | **无 batch 工具**:看一眼点一下 = 2 轮 LLM 往返 | 仅 6 个单步工具 | n2 computer_batch;Anthropic 20260801 toolset | 新增 `computer_batch` 工具:一次调用执行动作序列、首错即停+合成失败结果、坐标基于批前截图、返回一张批后截图 |
| A11 | **无 wait 原语** | — | 两家都有 | `wait` 工具/动作(asyncio.sleep,上限钳制) |
| A12 | **无自检命令**:无法在会话外验证 portal/ydotool/uinput/显示服务器 | — | CuaDriver 的 setup/doctor/smoke 模式 | `tank-backend --check-computer-use`:探测显示服务器、截图往返、输入通道、uinput 权限,输出能力报告 |

### P2 — 打磨

| # | 项 | 说明 |
|---|---|---|
| A13 | zoom 动作 | 全分辨率截图中裁剪局部再适配(小字/高清屏点击精度),Anthropic 20251124 实证 |
| A14 | ScreenshotTool 死参数 | `profile` 存而不用(`computer_use.py:227-228`),docstring 谎称调视觉 LLM(实际直接回图):删除参数或接线,修正文档 |
| A15 | 光标可见性 | n2 需要含光标截图;记录选项(show_cursor),Portal/mss 行为各不同,实测后文档化 |
| A16 | 多显示器 | 当前单屏假设;记录为 v1 限制 |

### A17 — 本地基准套件(改进是否为真、n2 是否值得引入的同一把尺子)

**目的**:给"是否真的改进"提供证据。用途链:现状 baseline(computer_use.md 子代理)→ Part A 后重跑对比 → 将来 agent-n2 插件 A/B——同一把尺子,没有它一切靠感觉。

**运行环境**(开发 VM 实测 `SESSION=tty` 无图形会话、mss 未装 → Linux 工具组在开发 VM 连注册都不会):

- 绝不在开发机裸跑(会动真实鼠标/键盘);
- Linux 路径:专用 GUI VM(GNOME Wayland,装 Tank backend + mss + ydotool/uinput 权限),setup 后打快照,每次 trial 前恢复(OSWorld 做法);
- macOS 路径:真机/独立环境跑;
- 任务定义按平台参数化,一套 harness 双平台复用。

**任务格式**(每任务一个 YAML,放 `backend/benchmarks/computer_use/tasks/`):

```yaml
id: local-form-submit
category: form            # app / settings / file / form / browser / typing / multi-window
difficulty: 2             # 1-3
platforms: [linux, macos]
instruction: "打开表单页,填入姓名和邮箱并提交"
setup: |                  # 每 trial 前执行,保证确定初态;重置上次任务改过的状态
  rm -rf ~/bench-work && mkdir -p ~/bench-work
validator:                # 只断言副作用,绝不 diff 截图
  kind: shell
  command: test -f ~/bench-work/submitted.json && jq -e '.name=="张三"' ~/bench-work/submitted.json
timeout_s: 180
max_steps: 30
```

**可靠性八条**:

1. **确定性 setup/teardown**——每 trial 从脚本化已知状态开始;VM 快照恢复优先,脚本重置兜底;
2. **validator 只查副作用**(文件、gsettings/defaults 值、浏览器历史 SQLite、pgrep)——像素比对是最大噪声源,禁用;
3. **零外网**——浏览器/表单任务用 `file://` 或 harness 起的本地 http server;依赖外网的任务不进套件;
4. **每任务 3–5 次 trial**——报成功率 + 二项置信区间;步数/耗时/token/成本报中位数(LLM+GUI 都随机,单次无意义);
5. **环境钉死**——分辨率、缩放、locale、主题固定;关通知/自动更新(抢焦点);开"减少动画"让截图更快稳定;
6. **全量 trace**——每 trial 存工具调用 JSONL + 每步截图 + validator 输出,失败可离线诊断;
7. **硬超时 + 步数上限**——卡死快速判负,不拖垮整轮;
8. **任务准入**——每个任务先人肉金标跑一次、validator 通过才入套(先验证 validator 本身)。

**套件构成**:12–15 任务 × 难度 1–3:启动应用、改系统设置、GUI 文件操作、表单填写(本地页)、本地浏览器导航、中英文输入、多窗口切换。

**驱动方式**:harness 进程内直调 WorkerSupervisor 派发 computer_use 子代理(不经 WS/语音),消除 ASR/TTS 变量。指标:成功率(主)、步数、耗时、token/成本、截图数。

**环境分工**:开发 VM 写 harness/任务/validator 代码 + 全部单测(跑不了 GUI);Linux 验收在 GUI VM;macOS 验收上真机。

### Part A Tests

- 归一化↔像素映射(0-1000 边界、纵横比)、屏幕尺寸缓存失效
- key 翻译表:cmd→super、标点词形、repeat、逐键序列
- 剪贴板输入路径:非 ASCII 走 wl-copy(xclip),ASCII 直打,剪贴板恢复(mock subprocess)
- batch 执行器:顺序执行、首错即停、剩余动作回合成失败、单截图、批前坐标
- scroll clamp;wait 上限
- portal/mss 后端选择与失败报告(mock subprocess)
- 审批:computer 类别工具默认走 require_approval
- doctor:能力报告结构(mock 环境)
- A17 harness:任务 YAML 解析、setup/validator 执行、trace 落盘、trial 聚合(mock subprocess)
- 现有 `tests/test_computer_use.py` 全量回归

### Part A 验收

- [ ] Linux/macOS 工具 schema 一致(归一化坐标)
- [ ] 中文输入在 GNOME Wayland 实测可用
- [ ] 修饰键点击(ctrl+click)不退化为普通点击
- [ ] 截图延迟(Wayland 主路径)< 500ms
- [ ] computer 类别工具未经批准不执行
- [ ] `--check-computer-use` 能在不启动会话的情况下报告环境能力
- [ ] A17 基准套件在 GUI VM 跑通,产出现状(computer_use.md 子代理)baseline 报告

---

## 9. Part B:n2 插件 agent 接入计划(依赖 Part A 的 DesktopExecutor)

> 前置:Part A 的 A1/A3/A5/A10/A11(坐标、原语、审批、batch 语义、wait)构成 DesktopExecutor 骨架;Part A 完成前 Part B 不开工。放弃 Part B 不影响 Part A 任何代码。
>
> 第 2 版重设计:初稿的 `computer_task` 工具、`ComputerUseEngine` 契约、`plugins/engine-n2` 全部废弃,改为下述 agent-seam 方案——复用现有 agent 工具/WorkerSupervisor/AgentRunner 体系,核心新增只有一个工厂分支。

### B1 — DesktopExecutor(Part A 产物的收拢,能力接口)

`backend/core/src/tank_backend/computer/executor.py`:DesktopExecutor 协议 + 双平台实现(复用 Part A 改进后的原语)。host bash(持久 cwd、禁 sudo、输出截断)+ file read/write/edit(read-before-edit 强制)+ batch(首错即停、批前坐标、单批后截图)在此层。§7 安全红线全部实现在这里——**对所有引擎(含 LLMAgent 直调路线)统一生效**,这是"手在 executor"的原因。

### B2 — 核心扩展点(Agent seam,通用机制)

- `AgentDefinition` 加可选 `engine:` 字段(缺省 = 内部 LLMAgent;`toolset`/`model` 字段对插件 agent 无意义,忽略);
- `AgentRunner.run_agent`(runner.py:177)加工厂分支:definition 声明 engine → 从 ExtensionRegistry 构造插件 agent;
- registry 增加 `agent` 扩展类型:`plugin.yaml` manifest 声明 `extension_type: agent` + `needs: [desktop_executor]` 能力依赖,Tank 按声明注入(registry 本身类型无关,只需校验器);
- 契约:插件实现 `Agent.run(state) → AsyncIterator[AgentOutput]`;**必须周期性 yield USAGE**(否则 token_budget 失效);进度经 TOKEN/TOOL_EXECUTING 事件流入现有 worker.* bus 通道;
- WorkerSupervisor / AgentTool / 持久化 / agent_stop / 后台派发:零改动。

### B3 — n2 插件与任务级整合

`backend/plugins/agent-n2/`(manifest:extension_type=agent,needs=[desktop_executor]):

- `agent.py`:`N2Agent(Agent)`——自建 AsyncOpenAI(llm_profile: n2)、自有消息历史管理、循环(max_steps/预算上限/取消令牌),tool_calls → executor 方法调用,结果(含批后截图)按 n2 协议装填回历史;
- `protocol.py`:n2 协议特例全部封在此——`tool_set` 经 extra_body、不发 max_tokens/temperature、reasoning_content 原样回显、多 tool_calls 每份独立结果、tool 消息图片装填格式、全量历史回传;
- `backend/agents/computer_use_n2.md`:`engine: agent-n2:agent` 的子代理定义。

任务级整合(全部复用现有机制,替代初稿 computer_task):审批在 agent 工具派发点(A5 `computer` 类别,一次放行整任务;2026-09-09 核对:AgentTool 派发点现无审批钩子,此为 A5 净新增接线);进度 = worker.* bus 事件 → UI;打断 = `agent_stop` → asyncio 取消 → 引擎取消令牌;语音 UX = `background: true` 派发后继续对话,结果经 NotificationHub 回注(2026-09-09 核对:早期 WorkerInboxObserver 已被 NotificationHub 取代)。

### B4 — 安全控制矩阵(文档化取舍)

| 控制层 | 实现位置 | 插件 agent 下 |
|---|---|---|
| 调度/取消/超时/持久化/并发深度/后台 | WorkerSupervisor(派发缝) | ✅ 自动有效,与 agent 内部实现无关 |
| 进度可观测、token 预算 | AgentOutput 流(USAGE 事件) | ✅ 有效(契约要求 yield USAGE) |
| 任务级审批 | agent 工具派发点(computer 类别,A5) | ✅ 自动有效 |
| 执行红线(禁 sudo/输出截断/文件/网络策略) | DesktopExecutor(注入物) | ✅ 有效——动作经 executor |
| 逐动作审批、pre/post hooks、tool_guardrails、沙箱路由 | AgentRunner→ToolManager 工具执行管线 | ❌ 失效——文档化取舍 |

- 逐动作审批在 GUI 循环(30+ 步)本就不可用,行业(Anthropic demo、n2 协议)均为任务级放行;
- hooks/guardrails 失效记录在案;将来若需覆盖,hook 挂在 executor 动作通道(`action.*` bus 事件)而非 agent 层——对所有引擎统一生效;
- 插件不许直连宿主机(§4 边界约束),n2 的 bash/read/write/edit 同样走 executor。

### Part B Tests

- N2Agent 循环(mock completions):单/多 tool_calls 回合、reasoning_content 回显、max_tokens 不出现于请求、首错即停透传、循环终止条件(纯 content 无 tool_calls)、取消令牌中途生效、USAGE 事件流出
- tool_calls → executor 映射:15 原语 + bash/read/write/edit → executor 方法(1000×1000 坐标恒等映射);错误动作 → 合成失败结果
- Agent seam:`engine:` 字段解析、runner 工厂分支、registry 校验(needs 声明缺失报错)、computer_use_n2.md 经 agent 工具派发全链(mock 引擎)
- 任务级审批:computer 类别派发未经批准不执行;批准后循环内动作不再逐个审批
- 配置:插件配置段校验、llm_profile 引用缺失报错
- 端到端(mock 引擎):语音输入 → 审批 → 派发 → 执行 → inbox 回注 → TTS 播报

### Part B 验收

- [ ] 删除 `plugins/agent-n2/` 后 Part A 与核心全部测试通过(零耦合证明)
- [ ] A17 基准上 agent-n2 与现状 computer_use 子代理同尺 A/B,数据支持引入决定
- [ ] 手工跑通 3 个真实桌面任务(打开应用/改设置/浏览器搜索)
- [ ] agent_stop 在批中途生效(取消令牌实测)
- [ ] 全程无 `# type: ignore`

---

## 10. 验证清单(实施时任一 Part 完成后必须全绿)

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check src/ tests/`
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <改动文件>`
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
8. `cd test && pnpm test`

## 11. 参考资料

- [Navigator n2 产品页](https://yutori.com/n2) · [发布博客](https://yutori.com/blog/introducing-n2) · [API 参考](https://docs.yutori.com/reference/n2)
- [yutori-sdk-python](https://github.com/yutori-ai/yutori-sdk-python)(Daytona 适配器示例)· [yutori-mcp](https://github.com/yutori-ai/yutori-mcp)(CuaDriver 仅 macOS)
- [Anthropic computer-use-demo](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo)(loop.py / tools/computer.py:缩放、xdotool、首错即停、缓存经济学)
- 本仓库工具:`backend/core/src/tank_backend/tools/computer_use.py`、`computer_use_macos.py`、`tools/groups.py`、`agents/approval.py`
- 本仓库子代理体系(第 2 版设计依据):`agents/agent_tool.py`、`agents/supervisor.py`、`agents/runner.py`(`run_agent`:177 工厂分支点)、`agents/definition.py`、`backend/agents/computer_use.md`

## 12. 执行阶段(2026-09-09 批准)

约束:A17 baseline 必须测在 Part A 改动**之前**(harness 先行);每阶段先经用户设计评审再实现;Part B(n2)在决策门之后且需用户明确同意;Linux 实测在用户的 GUI VM,macOS 实测由用户 push/pull 执行,每轮测试前代码全部提交并附测试指南。

```
阶段 0   依赖/配置/文档修正(mss/pyautogui 声明、launch_app 平台注释、提示词去 macOS 风味、macOS 模块单测、本文档事实修订)
阶段 1   A17 基准套件 ──[设计评审]──► 单测 ► T0(macOS baseline,用户)
阶段 2   坐标+按键+中文(A1+A4+A2)─[设计评审]► T1(GUI VM + macOS)
阶段 3   原语+输入修正+截图(A3+A7-A9+A11+A6+A15)─[设计评审]► T2
阶段 4a  审批闸门(A5)─[设计评审·安全]
阶段 4b  batch 工具(A10)─[设计评审]            ► T3(GUI VM + macOS)
阶段 4c  doctor 自检(A12)─[设计评审]
阶段 5   A17 重跑对比 + P2 打磨(A13/A14/A16)+ Part A 验收 ► T4
══════ 决策门:Part A 验收全绿 + baseline/对比数据 + 用户同意 ══════
阶段 6   Part B 核心扩展点(B1+B2)─[设计评审·架构]
阶段 7   agent-n2 插件(B3)─[设计评审]► A17 同尺 A/B ► T5(真机,用户)
```

## 13. 阶段 2 设计定稿(2026-09-13 用户批准)

Baseline 已入档:6/42=14%(label=baseline-macos);terminal-write 0/3 两种死因(key_press 双重编码、幻觉越权工具调用)均为本阶段修复对象。三项裁决:E1 扩展到 scroll/mouse_move(同一 normalize 函数)、E3 拦截层放 agent 层 wrapper(不动 ToolManager,主对话零影响)、A2 不保存/恢复剪贴板(与 macOS pbcopy+cmd+v 现状对齐)。

- **A1 坐标统一**:Linux `computer_use.py` click/scroll/mouse_move 的 x/y 改 0-1000 归一化,`round(n*(size-1)/1000)`、clamp;mss 截图取宽高缓存并每次刷新;截图结果追加 macOS 同款 dimension_note;双平台 schema 参数描述逐字一致(一致性断言单测)。
- **A4 按键翻译**:规范名=schema 声明集(单键 enter/tab/escape/backspace/delete/space/arrows/home/end/pageup/pagedown/f1-f12;修饰 cmd/ctrl/alt/shift;`+` 组合;`repeat` 1-20 clamp);enter↔return 同义;三张翻译表单点定义+全键覆盖单测(macOS AppleScript key codes 补齐、Linux pyautogui 键名、cmd→win 修饰映射)。
- **A2 中文输入(Linux)**:type_text 非 ASCII → wl-copy(Wayland)/xclip(X11)+ctrl+v;工具缺失返回带安装指引的 error;不恢复剪贴板;ASCII 直打。
- **E1 bbox 兼容(Qwen)**:click/scroll/mouse_move 统一 normalize——`x:[x1,y1,x2,y2]` 取中心 `((x1+x2)//2,(y1+y2)//2)`,`x:int,y:int` 不变,其它形态参数 error;schema 描述补"或传 bbox 数组取中心"。
- **E2 key_press 容错**:工具入口规范化(双平台共用):strip 后匹配 `^[[].*[]]$` → json.loads(`["return"]`→`return`、`["cmd","c"]`→`cmd+c`);return→enter 同义;未知键名 error 列出合法键名(可自纠)。
- **E3 executor 工具集强制(安全)**:LLMAgent 的 executor 外包 allowlist gate(`tool_filter ∖ exclude` 之外 → ToolResult error "tool not available to this agent",不执行;无 filter 全放行)。证据:baseline trial 3 幻觉调用 run_command(沙箱执行)/file_write/agent 越过 `toolset: computer_use`(llm_agent.py:80-82 只过滤 schema)。
- **本轮不做**:hold_key/mouse_down/drag(阶段 3)、batch(4b)、审批(4a)、macOS 剪贴板扩展到特殊字符 ASCII。
- **测试**:翻译表全键×双平台/归一化边界/bbox 三形态/keys 三种容错/executor 拦截放行/剪贴板 mock subprocess/schema 一致性;每子项一 commit;T1 测试轮(GUI VM:gedit 中文、归一化点击、cmd→super;macOS:回归+bbox 抽测)需用户执行。

## 14. 阶段 3 设计定稿(2026-09-13 用户批准)

三项裁决:① Linux 指针通道**先 A(EV_ABS 自建 uinput 绝对指针,触屏风格 ABS_X/Y+BTN_TOUCH)后 B(EIS/libei)**,失败自动退 B;② `drag` 做**独立原语**(move→down→分步 move(20ms 步进)→up),不靠模型组合 mouse_down/up;③ A8 只改 Linux(长文本 100ms 块间),macOS 保持整串 keystroke。

- **EV_ABS 设备**:`/dev/uinput` 直开(免 daemon,已在 input 组),固定量程 0..10000 映射全屏,归一化输入×10;udev 规则补 tank 设备名;键盘/和弦/滚轮保留 ydotoold socket 通道。
- **A3 原语**:`mouse_down/mouse_up(button)`、`hold_key(keys,duration_s=1.0,上限10s)`、`drag(x1,y1,x2,y2)`;macOS CGEvent、Linux 双通道(ABS 指针+socket 键盘)。
- **A9 scroll clamp**:±50 超限报错;**A8** Linux 长文本 50 字符块+100ms 块间;**A6** portal 截图改等 Response D-Bus 信号(2s 超时)替代 sleep(3),单次 <1s;**A15** 光标可见性记入 A12 doctor 检查项。
- 单测:原语时序(mock)、clamp、drag 轨迹、portal 等待;T2:macOS drag/hold_key/长文本,Linux(若 ABS 成)绝对点击/拖拽/复跑。
