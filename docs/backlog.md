# Backlog — 条件触发的后续工作

> 生命周期：**持续维护的登记表**，不是一次性计划。计划文档关档移入 `plans/done/` 前，其中"暂缓 / 按触发条件立项 / 非目标但将来可能做"的条目移交到这里；调研文档与代码注释产生的同类条目也登记于此。

## 登记规则

- 每条必填：**触发条件**（什么事实发生时立项）、**背景/前置**（一两句）、**来源**（文档链接）。
- 只有"带前置或触发条件的将来工作"进本表；确定要做的近期待办直接进 `plans/active/` 写计划。
- 条目被触发立项（新建 `plans/active/` 计划）或被明确放弃时，**从本表删除**——历史由新计划文档与 git 承担，本表只保留尚未启动的项。
- 前置条件已满足、随时可立项的条目照常保留，在触发条件栏注明。

## 条目

2026-09-19：提示冲突、输入/评分、截图像素证据、frame/宿主还原、模型适配、
规划定位分离、AX/定位器与跨应用/长历史工作已立项，统一移入
[macOS 适配与定位计划](plans/active/computer-use-adaptation-and-grounding.md)。
移出本表表示已有执行计划，不表示问题已修复；完整历史核对见该计划 §2。

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

| N2 SDK Linux adapter 与平台验收 | 产品需要 Linux，且有专用 X11/Wayland 实机环境 | 原 M4/M6 未完成：X11 adapter、来源/许可证、中文/修饰键、截图光标/时延与真实取消/清理分别验收；未通过保持 unsupported，不能套用 macOS 结果 | [SDK 原 M4/M6](plans/done/plugin-subagents-and-n2-sdk.md)、[统一计划 §2.3](plans/active/computer-use-adaptation-and-grounding.md) |
| N2 SDK 采用后同进程暂停与恢复 | 产品使用 SDK 且需要暂停/接管/恢复 | 原 M7 未触发：pause_pending/paused、运行实例/trajectory、恢复重新截图/授权/预算/桌面锁、状态与协议展示及停止/过期边界；暂停计入时限，跨重启恢复另立项 | [SDK 原 M7](plans/done/plugin-subagents-and-n2-sdk.md)、[统一计划范围](plans/active/computer-use-adaptation-and-grounding.md) |
| N2/SDK 特定控制与集成补验 | 修改 SDK/共享派发控制、升级 driver，或出现新的 WS/通知/输入释放/进程清理问题 | N2 已有真实 benchmark，SDK 42 个 trial cleanup=confirmed；普通报告不证明每种中途停止与完整主会话 WS。仅针对受影响 seam/动作补验，保留原 M4/M6 细则，不将全套重验设为效果改进前置 | [SDK 原清单](plans/done/plugin-subagents-and-n2-sdk.md)、[效果改进范围](plans/active/computer-use-adaptation-and-grounding.md) |

| Computer-use 原生协议与专用定位模型探索 | 明确需要该路线，取得可用端点/部署、协议与授权，并批准独立实验预算 | M3 已完成自定义 point/pixels/bbox 适配；原生点框、Responses computer、UI-TARS 未测试，不能由自定义工具结果推断支持性或收益 | [M3 收尾](plans/active/computer-use-adaptation-and-grounding.md#m3--具体模型的适配器与独立定位基线) |
| Computer-use 静态候选采用复验 | 决定重新考虑候选/提示配置，且准备新预算与未使用的独立 holdout | 首轮 544 次额度已用完；旧 holdout 歧义拒绝失败，唯一匹配修正仅三次开发 smoke。新冻结需覆盖正例和负例，不能复用旧数据宣称独立验收；既定 M4–M8 集成/真实任务验收仍留 active 计划 | [M3 收尾](plans/active/computer-use-adaptation-and-grounding.md#m3--具体模型的适配器与独立定位基线) |
