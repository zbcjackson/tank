# Tank 文档索引

`docs/` 按文档类型分目录存放。目录职责与生命周期规则见根目录
[CLAUDE.md](../CLAUDE.md#documentation-docs) 的 Documentation 章节。

| 路径 | 类型 | 状态 | 简介 |
|---|---|---|---|
| [plans/done/computer-use-multi-display.md](plans/done/computer-use-multi-display.md) | 计划 | 已完成 | Computer-use 多显示器支持:按屏截图/坐标、跨屏拖拽、benchmark min_displays 与 multi-display-calc;双屏/单屏/LLM smoke 实机验收完成 |
| [plans/done/macos-coordinate-chain-tests.md](plans/done/macos-coordinate-chain-tests.md) | 计划 | 已完成 | macOS 坐标修复、HTTP 链路测试、合成模型隔离与真机校准 |
| [research/macos-coordinate-chain.md](research/macos-coordinate-chain.md) | 调研 | 主屏校准通过、模型偏差复现 | 尺寸坐标链路、真实证据与验收边界 |
| [research/jev-computer-use-comparison.md](research/jev-computer-use-comparison.md) | 调研 | 源码对比完成，改进待验证 | 三个 Jev 开源项目的职责、观察、历史与规划交接；对照 Tank S4 原生失败和后续验证优先级 |
| [design/computer-use.md](design/computer-use.md) | 设计 | 现行与验证边界 | macOS 坐标链、全部验证结论、模型协议与预算对照、闭环判定 |
| [backlog.md](backlog.md) | 登记 | 持续维护 | 条件触发的后续工作登记表:计划关档时移交的暂缓/触发式条目 |
| [plans/done/computer-use-benchmark-fixes.md](plans/done/computer-use-benchmark-fixes.md) | 计划 | 已完成 | SDK 签名、Quartz、图像反馈与 GUI 评分修复；复用已有 benchmark，后续聚焦效果改进 |
| [plans/done/backend-unit-test-fixes.md](plans/done/backend-unit-test-fixes.md) | 计划 | 单测修复完成 | 后端 workspace 测试收集与单元测试修复；运行日志验证限制见结果 |
| [design/pipeline-architecture.md](design/pipeline-architecture.md) | 设计 | 现行 | 三层音频管线:GStreamer 风格 processor 链、有界队列与背压、双向事件 |
| [design/agent-orchestration.md](design/agent-orchestration.md) | 设计 | 现行 | 主 agent + 子 agent 编排:`agent` 工具、WorkerSupervisor、审批继承、Bus 流式输出 |
| [design/agent-security.md](design/agent-security.md) | 设计 | 现行 | 五层纵深防御:命令/文件/网络策略、沙箱、审批 |
| [design/conversation-gate.md](design/conversation-gate.md) | 设计 | 现行 | 音频门控状态机、静默计时器与 wake/idle/disconnect 信号协议 |
| [design/skills.md](design/skills.md) | 设计 | 现行 | Skill 系统:SKILL.md 解析、注册去重、安全评审、技能工具 |
| [design/agentic-harness-features.md](design/agentic-harness-features.md) | 设计 | 现行 | agentic harness 基础设施参考:工具元数据、条件注册、hooks 协议 |
| [design/vad-smart-turn-design.md](design/vad-smart-turn-design.md) | 设计 | 现行 | VAD / Smart Turn 端点检测 / speculative reopen 的当前实现与设计取舍 |
| [plans/done/computer-use-improvement-and-n2-plan.md](plans/done/computer-use-improvement-and-n2-plan.md) | 计划 | 实现已完成 | Part A/A17 与 N2 引入历史；N2 于 2026-10-02 退役 |
| [plans/done/plugin-subagents-and-n2-sdk.md](plans/done/plugin-subagents-and-n2-sdk.md) | 计划 | 已完成 | 通用派发/SDK 历史与 benchmark；SDK 于 2026-10-02 退役，保留 Computer Use 所需运行时 |
| [plans/done/n2-macos-config-and-reasoning.md](plans/done/n2-macos-config-and-reasoning.md) | 计划 | 代码与回归完成 | N2 profile 精确查找、模型校验与 DeepSeek 通知思考字段回传；运行日志限制及实机复测见结果 |
| [plans/done/n2-runtime-config.md](plans/done/n2-runtime-config.md) | 计划 | 配置与回归完成 | 补齐主配置中的 N2 profile 与插件引擎映射；运行日志限制见结果 |
| [plans/done/n2-notification-and-tracing-fixes.md](plans/done/n2-notification-and-tracing-fixes.md) | 计划 | 代码与回归完成 | N2 完成通知的旧思考历史兼容、Langfuse 重复追踪和 ping/pong 元数据警告；运行检查限制见结果 |
| [plans/done/protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) | 计划 | 已完成 | 私有协议演进:契约包/认证/握手/Opus/热配置全部落地;触发式条目移交 backlog |
| [plans/done/memory-context-improvements.md](plans/done/memory-context-improvements.md) | 计划 | 已完成 | 对标四个 harness 的记忆/上下文五模式改进;Phase A/B/C 全部落地 |
| [plans/done/agentic-harness-patterns-analysis.md](plans/done/agentic-harness-patterns-analysis.md) | 计划 | 已完成 | 对标 OpenClaw/Hermes/OpenCode 的四种 harness 模式;四阶段全部落地 |
| [plans/done/s2s-comparison-and-improvement-plan.md](plans/done/s2s-comparison-and-improvement-plan.md) | 计划 | 已完成 | 对比 HF speech-to-speech 的改进计划;句级流式 TTS(P0-5)与 Smart Turn 端点检测(P1)均已落地 |
| [research/audio-noise-investigation.md](research/audio-noise-investigation.md) | 调研 | 未解决 | TTS 播放噪声排查:已排除的环节与证据,供下次排查起点 |
| [research/claude-code-learnings.md](research/claude-code-learnings.md) | 调研 | 参考 | Claude Code 架构中可借鉴到 Tank 的模式分析 |
| [history/architecture-evolution.md](history/architecture-evolution.md) | 历史 | 持续追加 | 从单文件脚本到多 connector agentic 平台的架构演进史(按时代划分) |

`superpowers/` 由 superpowers 插件自管(plans/specs),不套用上述规范。

- [plans/done/macos-grounding-contract.md](plans/done/macos-grounding-contract.md)：模型坐标参照系隔离与计算器结果验收（已完成）。
- [plans/done/macos-grounding-ablation.md](plans/done/macos-grounding-ablation.md)：100 次合成请求隔离提示/参数/输出格式及真实 SSE 回放（已完成）。
- [plans/done/macos-grounding-model-comparison.md](plans/done/macos-grounding-model-comparison.md)：同一提供方的 80 次固定图模型/生产 schema 对照（已完成）。
- [plans/done/macos-grounding-protocol-isolation.md](plans/done/macos-grounding-protocol-isolation.md)：304 次跨提供方模型/严格协议隔离与真实 Calculator 坐标 oracle（已完成）。
- [plans/done/deepseek-grounding-budget.md](plans/done/deepseek-grounding-budget.md)：112 次 DeepSeek 输出预算与关闭思考的配对隔离复测（已完成）。
- [plans/done/gpt55-computer-use-loop.md](plans/done/gpt55-computer-use-loop.md)：验证结论汇总、GPT-5.5 实机 calc-open 2/3 严格通过与 temperature 接入修复（已完成）。
- [research/computer-use-implementation-comparison.md](research/computer-use-implementation-comparison.md)：模型与宿主责任边界、其它实现的坐标/AX/定位器/反馈设计及实验优先级。
- [plans/done/computer-use-implementation-research.md](plans/done/computer-use-implementation-research.md)：公开实现对照与改进方案调研（已完成）。
- [research/computer-use-strategy-ladder.md](research/computer-use-strategy-ladder.md)：策略阶梯调研与复核：DOM/AX/OCR/视觉、M8 证据边界、Jev 官方协议与动作选择、按需 LLM 协作；收益均待验证。
- [plans/done/model-call-naming.md](plans/done/model-call-naming.md)：通用模型调用/流式命名收敛，Jev 客户端创建与关闭交还官方 SDK，采用默认环境代理/证书行为；不涉及 S4。
- [plans/done/model-call-simplification.md](plans/done/model-call-simplification.md)：已完成独立 DecisionModel 与任务薄包装，清理 Jev/普通聊天的 Route/Transport，采用 SDK 调用级记账及可选 Langfuse；API 3，后端 5579 通过、E2E 17 场景通过，S4 未启动。
- [plans/done/computer-use-goal-contract-unification.md](plans/done/computer-use-goal-contract-unification.md)：已统一目标驱动 GoalContract，移除 v1/里程碑兼容路径并迁移调用、测试及可执行 benchmark；评审修复 submit 自动执行与观察恢复判断，后端 5608 通过、E2E 17 场景通过。
- [plans/active/computer-use-strategy-ladder.md](plans/active/computer-use-strategy-ladder.md)：Computer Use 宿主循环与策略阶梯。S0–S3 按各自范围完成；S3 同候选回退与 48 次 H3/J3 对照均已验收：结果相同，Jev 省费 39.6% 但耗时增加 22.1%，未证明净收益，保持默认禁用。歧义冲突历史证据保留并纠偏；S3-M 核心 Jev SDK 管理迁移验收完成（移除 model_route 插件扩展），S4 已启动显式 v2 目标契约、DOM 混合 click/fill 候选及逐步核验首批实现；S4-AX 原生实现与评审完成，真实 Calculator/TextEdit 的 fake-HTTP 矩阵 9/9 通过；真实 Jev 超长请求拒绝已定位并压缩；后续 12 次模型选择/AXPress 成功，但反复输入数字、未完成算式，到限停批（0/1/8），清理确认；旧失败记录保留，原生整体验收未通过；S4-R4 文本 Advisor 与目标进展复核离线验证通过，双模型原生实机 fake-HTTP 矩阵 9/9 通过（后端 5692、E2E 18 场景，独立评审完成）；获准真实批次 1 成功 / 1 未知失败 / 7 未运行：首项 Advisor 纠偏后交回 Jev 完成 7×8=56，次项选择右括号后 effect_unknown 停批，清理确认。真实规划稳定性、同进程恢复及视觉尚未验收。系统比较与生产采用仍属 S5–S6。 2026-10-09 语义执行记录与独立模型视图首片离线验收及评审完成：最近十条动作/观察变化供 Jev 和 Advisor 共用，真实重测留待后续。 短动作别名与共享读数视图离线验收及评审完成；S5 已纳入 DOM、Cua Driver、AX/OCR 融合及观察稳定性的受控比较。 动态 focus 生命周期离线验收与评审完成；诊断回放与正式 S5 的前置条件已分层。 四状态、四组无桌面诊断执行器已通过离线验证与评审；配方已冻结，真实调用因本批数据导出授权被自动审批拒绝，0 请求、48 行未运行，待明确确认。 计划 §0 已补充 DeepSeek Harness 接续交接、代码入口、验证结果与冻结执行命令。 经用户明确授权后该诊断 48/48 行完成（51 次调用、约 $0.0455、0 桌面操作）：当前紧凑输入+语义历史 12/12、旧输入 6/12、Advisor 组 11/12、明确按钮定位 12/12，仅为冻结状态选择判定。 排期调整（用户确认）：先做真实 native 矩阵与按证据修复，S4-G3 移至正式 S5 之前完成，仍是 S4 出口门槛。 native 矩阵第七批：停批改为已知失败计入分母并继续，配方已冻结，真实应用 fake HTTP 9/9 通过；经授权真实批次 9/9 通过（34 次调用、约 $0.026），Jev 在 2/6 例跳过运算符后自行 Clear 并经 Advisor 纠偏完成。 修复评估后两项暂不修（候选修法依赖 Calculator 专用启发式）。 再调整：S4-G3 移至 S6 交付前；下一步为按请求打开/复用任意 App 并绑定窗口（S4-B）、AX 快照通用完成核验（S4-V）、自然语言→GoalContract 与“一句话→完成任务”端到端验收。
- [plans/done/computer-use-s0-review.md](plans/done/computer-use-s0-review.md)：S0 通用任务契约三轮评审与两轮重构已完成：修复清理取消/证据丢失/错误完成文案，合并重复序列化；后端 5220 passed、E2E 18 场景通过，最终复审无新增问题。
- [plans/done/portable-code-reviewer.md](plans/done/portable-code-reviewer.md)：通用评审角色已完成：工具无关 Markdown、24 项固定 Code Smell、权限与独立性分离、无问题即停止/最多三轮及项目测试/提交约定。
- [plans/done/shared-agent-sync.md](plans/done/shared-agent-sync.md)：多 Agent 同步工具已完成：递归发现、格式校验、配置保护、--check；29 项工具回归和完整项目验证通过。
- [design/shared-agent-definitions.md](design/shared-agent-definitions.md)：通用 Agent 定义格式、批量同步命令、覆盖保护与生成物检查规则。
- [plans/done/post-task-code-review.md](plans/done/post-task-code-review.md)：任务收尾评审规则已生效：验证通过后委派 code-reviewer 自主评审/必要重构，无问题即停止、最多三轮，已完成首次复核。
- [plans/done/computer-use-adaptation-and-grounding.md](plans/done/computer-use-adaptation-and-grounding.md)：macOS 适配与定位效果改进计划（M0–M8 已完成，2026-09-25 关档）：保留生产基线 A（一体 legacy 归一化，默认全程未切换）；静态首轮门槛无候选通过；calc-open 拆分显著优于适配一体+宿主还原（p=0.011）但宽任务集 A 10/36 > C 5/36 且 C 耗 1.7–2× token；AX 条件性暂缓；点击大偏移根因未解决（归因止于服务输出边界）；全计划 ≈35.4M tokens（unpriced）。收口汇总见 [M8 收口报告](../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)，触发式后续工作在 [backlog.md](backlog.md)。
- [plans/done/token-accounting-boundaries.md](plans/done/token-accounting-boundaries.md)：统一生产 token 用量记录，移回 benchmark trial/费用/预留策略；默认仅统计，修复显式零额度覆盖语义（2026-09-29 完成，第 1 轮独立评审通过）。

- [plans/done/remove-n2.md](plans/done/remove-n2.md)：N2 与 SDK 及专用扩展已移除，SubAgent 按当前 Computer Use 精简；完整验证通过，第 1 轮独立评审无可操作问题（2026-10-02 完成）。
