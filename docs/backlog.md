# Backlog — 条件触发的后续工作

> 生命周期：**持续维护的登记表**，不是一次性计划。计划文档关档移入 `plans/done/` 前，其中"暂缓 / 按触发条件立项 / 非目标但将来可能做"的条目移交到这里；调研文档与代码注释产生的同类条目也登记于此。

## 登记规则

- 每条必填：**触发条件**（什么事实发生时立项）、**背景/前置**（一两句）、**来源**（文档链接）。
- 只有"带前置或触发条件的将来工作"进本表；确定要做的近期待办直接进 `plans/active/` 写计划。
- 条目被触发立项（新建 `plans/active/` 计划）或被明确放弃时，**从本表删除**——历史由新计划文档与 git 承担，本表只保留尚未启动的项。
- 前置条件已满足、随时可立项的条目照常保留，在触发条件栏注明。

## 条目

| 项目 | 触发条件 | 背景/前置 | 来源 |
|---|---|---|---|
| Computer-use 多显示器支持 | 单屏限制阻碍实际桌面任务，且可准备多显示器验收环境 | 现有平台原语和 N2 benchmark 固定单屏；需统一截图布局、显示器身份与坐标变换 | [computer-use-improvement-and-n2-plan.md](plans/done/computer-use-improvement-and-n2-plan.md) A16 / §18 |
| 旧 DesktopExecutor 动作 hooks / guardrails | SDK 迁移后仍保留旧 N2，且需要对旧 executor 提供逐动作策略或 hooks | 现有旧插件绕过 ToolManager 管线；若旧路径已退役则删除此条，不为退役实现扩建控制层 | [computer-use-improvement-and-n2-plan.md](plans/done/computer-use-improvement-and-n2-plan.md) B4 / §18 |
| 客户端 token 携带（web/cli/device 连接时发 `?token=`） | 远程部署启动 | P0-2 只落地了服务端校验，三端客户端从未实现携带；需与 token 分发方式一并设计 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) P0-2 |
| 认证 token 分发方式定案 | 远程部署设计时 | 配置文件 vs 首次配对流程，计划 §11.2 未决问题 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §11 |
| Resume（断线续传） | 远程部署实测断线频繁到影响体验 | 现靠 session_id 恢复会话历史，在途 turn 状态全丢；需 text/audio 帧序号 + 重连 replay 窗口 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| WebRTC 传输 | 远程实测 Opus-over-TCP 仍因队头阻塞卡顿 | Opus-over-WS 已拿 80% 收益；届时 WebRTC 仅作传输层挂入，私有消息集原样复用（JSON 走 data channel） | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| Realtime 端点（`/v1/realtime`） | 第一个第三方客户端/机器人接入需求确认 | 作为边缘网关建立在演进后的私有栈之上（同一管线池 + 同一认证） | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| LLM Proxy | 出现需要借用服务端凭据的外部旁路任务 | tank 的摘要在服务端内部直调 LLM client，当前无旁路需求 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| memory `pinned_soft_cap_kb` 软上限告警 | **前置已满足**（IMP-1 Dream Consolidation 已落地，默认关闭），可随时立项 | 12 KB pinned 软告警当初因无收敛路径而暂缓；现在 consolidator 可收敛超限 pinned 集，告警有意义了 | [memory-context-improvements.md](plans/done/memory-context-improvements.md) §0 |

| macOS 动态几何与高频输入验收 | 产品需要截图后切换主屏/分辨率或无截图高频连点，或这些条件下再次报告错点 | 当前静态主屏九点验收通过；默认尺寸/截图缓存不追踪动态几何，首次校准存在未确定原因的事件缺失；多屏支持沿用上方条目 | [macos-coordinate-chain.md](research/macos-coordinate-chain.md) |

| calc-open 截图像素验收 | 需要把“截图确实展示 56”纳入评分或支持其他 macOS 控件结构 | 当前读取前台 Calculator 的 AX 表达式/结果，拒绝不可读状态；尚未对屏幕遮挡、截图存在与像素做判定 | [macos-grounding-contract.md](plans/done/macos-grounding-contract.md) |
| 定位候选的跨应用与长历史验收 | 准备将 GPT-5.5 等用于更广泛生产桌面任务，且具备获准外发的隔离环境 | GPT-5.5 合成图 32/32；真实 calc-open 已跑三轮严格 2/3，含两段鼠标序列和一次反馈恢复。尚缺全 14 任务、长历史/compaction、多种按钮尺寸；新严格协议仅在探针中，生产默认未切换 | [完整闭环](plans/done/gpt55-computer-use-loop.md)、[统一结论](design/computer-use.md) |
| 桌面子代理的 base 委托提示冲突 | 下一次优化或评估子代理提示、准备正式生产选型 | 实际 HTTP 同时包含直接操作桌面的专家指令与 base.md 的“必须委托 computer_use”；工具集无 agent，模型明确提及冲突。需分离主代理调度规则与共享安全规则，补提示/HTTP 回归并独立复测，尚未测量因果影响 | [完整闭环](plans/done/gpt55-computer-use-loop.md) |
| calc-open 合法粘贴路径与评分约定 | 需要将真实显示 56 的粘贴计算路径计入成功率 | 本地重置后粘贴 7*8 直接显示 56 但无表达式，严格 AX validator 拒绝；7*8= 仍为 0。需明确表达式证据如何验证，不能直接放宽为只读 56 或把这类失败算作错点 | [统一结论](design/computer-use.md) |

| Computer-use 截图引用与宿主坐标还原 | 下一轮定位接口优化立项；当前 crop 要求模型自行还原的前置问题已确认 | 将 frame/窗口/实际尺寸/裁剪变换绑定为不可变观察，按具体模型适配输入输出，宿主还原到 Quartz；保留纯视觉 holdout 对照，不猜测服务端倍率 | [实现对照 P1](research/computer-use-implementation-comparison.md#p1把空间计算从模型移到宿主) |
| macOS AX 候选与专用定位器对照 | 准备优化同一规划模型的桌面成功率，并可提供隔离验收环境 | 先比较纯截图、AX 候选加 Quartz、AXPress，再决定视觉检测器；纯视觉与混合成绩分开，候选不能泄漏 benchmark 真值 | [实现对照 P2](research/computer-use-implementation-comparison.md#p2比较语义辅助和专用定位器) |
| Computer-use 输入契约与效果检查 | 下一轮桌面闭环改进立项；输入模式差异已有本机复现 | 明确粘贴/字符/按键语义；状态变化步骤独立检查效果，稳定 batch 单独对照；关联现有 calc-open 评分条目，不追改旧结果 | [实现对照 P0/P3](research/computer-use-implementation-comparison.md#p0先修复已确认问题建立公平对照) |
