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
| 模型与边框定位候选验收 | 决定替换生产 computer_use 模型或定位路径 | Plus 在生产 click schema 对照中 16 次仍有一次约 150 px 大错；原生 bbox_2d 的留出集最高偏 41.1 px；需更多布局/按钮尺寸、局部图映射与真实离线点击校准，不可直接上线 | [模型对照](plans/done/macos-grounding-model-comparison.md)、[格式消融](plans/done/macos-grounding-ablation.md) |
