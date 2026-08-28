# Computer Use 改进与 Navigator n2 接入方案

> 状态:调研完成,待评审
> 日期:2026-08-28
> 关联:Yutori [Navigator n2 发布博客](https://yutori.com/blog/introducing-n2) · [API 参考](https://docs.yutori.com/reference/n2) · [Python SDK](https://github.com/yutori-ai/yutori-sdk-python) · Anthropic [computer-use-demo](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo)

## 0. 结论摘要

1. **n2 是"引擎",不是"大脑"。** 它只通过 Yutori API 提供(无开源权重),自带 5 个固定工具(`computer_batch`/`bash`/`read`/`write`/`edit`),由模型返回 `tool_calls`、**我们的客户端在真实桌面上执行**。它不消费我们的工具 schema,也不能当通用对话模型。
2. **执行器(控制电脑的代码)无论如何都要自研**——官方生态没有任何 Linux 实现:Yutori 只有 macOS 闭源驱动 CuaDriver.app;Anthropic demo 只有 Docker 里的 X11。我们仓库已有 Linux + macOS 双平台实现,起点反而领先。
3. **Part A(computer-use 工具改进)与 Part B(n2 接入)互相独立。** Part A 全部是通用改进,今天 gpt-5.4-mini 走现有工具路线就受益;Part B 依赖 Part A 产出的执行器接口,反之不成立。放弃 n2 对 Part A 零损失。
4. **推荐路径 A**:先做 Part A(通用),n2 引擎作为后续可插拔决定,零返工。
5. **设计原则已裁决**:凡行业收敛的正确设计(归一化坐标、batch 首错即停、reasoning 回放、截图经济学)吸收进核心;凡 n2 协议特例(`tool_set`、禁参、tool 消息图片装填)封进引擎适配器。核心代码零 n2 痕迹。

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

- 适用于:"帮我操作电脑做 X"类任务,作为 ChatAgent 手下的专项执行引擎;
- 不适用于:替换对话主模型;无头服务器;不接受截图上云的场景(全屏截图会上传 Yutori)。

---

## 2. 我方现状盘点

### 2.1 已有能力

- **桌面原语工具**(`tools/computer_use.py` Linux、`tools/computer_use_macos.py` macOS):screenshot、click、type_text、key_press、scroll、mouse_move(macOS 另有 launch_app);
- Linux 截图:XDG Portal(busctl)→ mss 回退;输入:ydotool(/dev/uinput,Wayland 可用)→ pyautogui 回退;
- macOS:screencapture + Quartz CGEvent,**已用归一化 0-1000 坐标**,已处理 Retina 缩放;
- **多模态链路完整**:ImageBlock → `image_url` 消息部分;工具结果可带图回模型(`llm/llm.py` tool stub + 后跟 user 消息);模态能力注册表。

### 2.2 已知缺口与风险

- **7 个 computer-use 工具全部 `category="general"`** → 走 `approval.py` 兜底分支**无条件自动放行**,而它们在宿主机裸奔(输入注入+截图);
- Linux/macOS 两套工具**坐标体系不一致**(详见 §8 A1);
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

## 4. 通用性设计:防绑死分层

```
ChatAgent(脑:编排、总结、播报)
   └─ computer_task 工具(通用:任务级审批、进度流、打断取消)
        └─ ComputerUseEngine 契约(通用:contracts 定义一次)
             ├─ engine-n2 插件(n2 专属:n2 循环 + tool_calls→规范动作映射)
             ├─ engine-anthropic-cua(将来)
             └─ engine-generic-vision(将来:我们的工具 + 任意视觉模型,走 LLMClient)
        └─ DesktopExecutor(通用:唯一"控制这台电脑"实现,双平台)
```

| 代码 | 属性 | 换模型时 |
|---|---|---|
| DesktopExecutor(原语/截图/bash/文件) | **通用** | 原样复用 |
| computer_task(审批/进度/打断) | **通用** | 原样复用 |
| ComputerUseEngine 契约 | **通用** | 定义一次 |
| 归一化 1000×1000 坐标约定 | **通用** | Anthropic 同款约定,主流兼容 |
| plugins/engine-n2(engine.py + actions.py) | **n2 专属** | 随 n2 退役 |
| yutori base_url/key/tool_set 配置 | **n2 专属** | 换新家的配置段 |

检验:第二个引擎(如 Anthropic CUA)只需新写 `plugins/engine-*/` 两个文件,executor/computer_task/契约一行不动——边界成立。

## 5. LLM 配置复用结论

- **调用层不复用**:n2 引擎自建 `AsyncOpenAI`(max_tokens 422、tool_set、reasoning 回显、tool 消息图片——塞进通用 LLMClient 会污染所有模型共用的传输层)。
- **配置层复用凭据**:`llm:` 段加 `n2` profile 仅作端点+凭据名片,引擎配置 `computer_use.engines.n2` 用 `llm_profile: n2` 引用,并持有引擎特有字段(tool_set、max_steps、reasoning_effort)。
- **插件不注册 LLM**:端点条目是静态 config,加一段即可;把 n2 包装成"新 LLM 传输实现"会诱导误配成 default,概念有害。
- 反例验证:将来 generic-vision 引擎(标准协议)**应当**走 LLMClient + profiles——引擎接口两种用法都兼容。

## 6. 平衡点裁决:吸收 vs 隔离

**✅ 吸收进核心**(去 n2 语境依然正确,行业收敛):

| 做法 | 对 n2 之外的价值 |
|---|---|
| 工具结果可带图 | 已有,保持 |
| batch 工具 + 首错即停 + 批前坐标 | Anthropic/n2 语义一致,行业共识;我方 LLM 调 CUA 工具省 N 倍往返 |
| 归一化 1000×1000 坐标 | 换屏/换模型坐标可移植 |
| **reasoning 轨迹原样回放** | Anthropic thinking 签名与 n2 reasoning_content 是同一件事;核查 `llm/llm.py` 是否保留 reasoning_content——DeepSeek R1/Qwen thinking 等多家返回,纯通用改进 |
| 截图缩放 + 保留经济学 | 任何视觉调用受益;n2 缓存价 $0.05/M,全量历史回传实际很便宜 |

**❌ 隔离在引擎适配器**:`tool_set` 参数、拒绝 max_tokens、tool 消息图片装填格式、多 tool_calls 政策、`reasoning_content` 字段名差异、服务端图片保留规则。

## 7. 引入路径决策

| 选项 | 内容 | 评估 |
|---|---|---|
| **A(推荐)** | 先做 Part A(通用改进),n2 后续可插拔 | 零风险验证接口缝;桌面能力立刻有;接 n2 零返工 |
| B | 核心 + n2 第一个引擎 | 能力直达 SOTA 性价比;引入新供应商 |
| C | 不引入 n2 | 最简;桌面能力停留在通用模型水平 |

安全红线(无论哪个选项):全屏截图上传云端需告知用户;真机 GUI+shell 控制必须任务级审批;不给 sudo;bash 输出截断。

---

## 8. Part A:computer-use 工具独立改进计划(不依赖 n2)

> 全部条目对现有 ChatAgent 路线(gpt-5.4-mini 调我们的工具)直接生效;参照实现:Anthropic computer-use-demo(开源、实证)、CuaDriver(闭源,借鉴其架构模式:setup/doctor/smoke 自检流程、前台单任务约束、OS 权限引导)。

### P0 — 正确性

| # | 问题 | 现状证据 | 参照做法 | 改进 |
|---|---|---|---|---|
| A1 | **Linux/macOS 坐标体系不一致**:Linux 用裸像素且模型不知道屏幕分辨率;macOS 已是归一化 0-1000 | `computer_use.py:293`("X coordinate (pixels)");`computer_use_macos.py:310-319` 已有 `_normalized_to_pixel` | Anthropic 按纵横比缩到标准小分辨率后按比例换算;n2/Anthropic 均为相对坐标 | Linux 对齐 macOS:归一化 0-1000;截图结果文本回报实际宽高;屏幕尺寸进程内缓存 |
| A2 | **中文/Unicode 输入大概率损坏**:ydotool `type` 走 uinput 键码,非 ASCII 不可靠;Tank 是双语助手 | `computer_use.py:189-192` | — | 非 ASCII 走剪贴板粘贴路径(wl-copy/xclip + ctrl+v),粘贴前保存并恢复剪贴板;ASCII 直打;加自检用例 |
| A3 | **缺修饰键和弦/drag/hold_key/mouse_down-up**:修修饰键的点击会退化成普通点击 | Linux 无 down/up 分离;`computer_use.py:175-186` 仅 click | Anthropic 20250124 起支持 left_mouse_down/up、hold_key、drag;和弦 = keydown→动作→keyup;n2"整手势,退化比报错更糟" | 补 4 个原语:mouse_down/mouse_up(支撑 drag)、hold_key(keydown/sleep/keyup)、修饰键和弦包装 |
| A4 | **key 名翻译表过窄**:`cmd→"command"` 不是 Linux X keysym(应为 super/meta),`cmd+space` 静默错误;无标点词形映射 | `computer_use.py:406-407` | n2 词形规范(slash/comma…);Anthropic key 表 | 规范 key 名 → 各后端翻译表(X keysyms / pyautogui / AppleScript key codes);含 repeat 与连续按键 |
| A5 | **审批闸门缺失**:7 个工具 `category="general"` 全自动放行 | `computer_use.py:231,282,332,379,426,484`;`approval.py:109-113` 兜底 ALLOW | — | 新增 `computer` 类别 → 审批策略(默认 require_approval;可在 config 降级) |

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

### Part A Tests

- 归一化↔像素映射(0-1000 边界、纵横比)、屏幕尺寸缓存失效
- key 翻译表:cmd→super、标点词形、repeat、逐键序列
- 剪贴板输入路径:非 ASCII 走 wl-copy(xclip),ASCII 直打,剪贴板恢复(mock subprocess)
- batch 执行器:顺序执行、首错即停、剩余动作回合成失败、单截图、批前坐标
- scroll clamp;wait 上限
- portal/mss 后端选择与失败报告(mock subprocess)
- 审批:computer 类别工具默认走 require_approval
- doctor:能力报告结构(mock 环境)
- 现有 `tests/test_computer_use.py` 全量回归

### Part A 验收

- [ ] Linux/macOS 工具 schema 一致(归一化坐标)
- [ ] 中文输入在 GNOME Wayland 实测可用
- [ ] 修饰键点击(ctrl+click)不退化为普通点击
- [ ] 截图延迟(Wayland 主路径)< 500ms
- [ ] computer 类别工具未经批准不执行
- [ ] `--check-computer-use` 能在不启动会话的情况下报告环境能力

---

## 9. Part B:n2 引擎接入计划(依赖 Part A 的执行器接口)

> 前置:Part A 的 A1/A3/A5/A10(坐标、原语、审批、batch 语义)构成执行器骨架;Part A 完成前 Part B 不开工。放弃 Part B 不影响 Part A 任何代码。

### B1 — 执行器模块(Part A 产物的收拢)

`backend/core/src/tank_backend/computer/`:`executor.py`(DesktopExecutor 协议 + 双平台实现,复用 Part A 改进后的原语)、`engine.py`(按配置选引擎、运行、转发进度/取消)。host bash(持久 cwd)+ file read/write/edit(read-before-edit 强制)在此层。

### B2 — n2 引擎插件

`backend/plugins/engine-n2/`(`[tool.tank]` manifest;AppConfig 增加 `computer_use` slot 类型):

- `engine.py`:裸调 AsyncOpenAI(llm_profile: n2)——`tool_set` 经 extra_body、不发 max_tokens/temperature、assistant 消息含 reasoning_content 原样回显、多 tool_calls 每份独立结果、全量历史回传、步数/预算上限回调、取消令牌;
- `actions.py`:n2 tool_calls(15 原语、1000×1000 坐标恒等映射)→ DesktopExecutor 调用。

### B3 — computer_task 工具与语音整合

`tools/computer_task.py`:BaseTool,`computer` 类别走任务级审批;进度经 update/THOUGHT 事件流到 UI;VAD 打断 → 取消令牌终止引擎;结果文本回对话由大脑总结播报。config:`computer_use.engine` slot + `engines.n2`(llm_profile、tool_set 钉死、max_steps、reasoning_effort)。

### Part B Tests

- n2 引擎循环(mock completions):单/多 tool_calls 回合、reasoning_content 回显、max_tokens 不出现于请求、首错即停透传、循环终止条件(纯 content 无 tool_calls)
- actions 映射:15 原语 → executor 方法;错误动作 → 合成失败结果
- computer_task:审批闸门(computer 类别)、打断取消、进度事件序列
- 配置:slot 校验、llm_profile 引用缺失报错
- 端到端(mock 引擎):语音输入 → 审批 → 执行 → TTS 播报

### Part B 验收

- [ ] 删除 `plugins/engine-n2/` 后 Part A 与核心全部测试通过(零耦合证明)
- [ ] 手工跑通 3 个真实桌面任务(打开应用/改设置/浏览器搜索)
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
- 本仓库:`backend/core/src/tank_backend/tools/computer_use.py`、`computer_use_macos.py`、`tools/groups.py`、`agents/approval.py`
