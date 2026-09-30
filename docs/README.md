# Tank 文档索引

`docs/` 按文档类型分目录存放。目录职责与生命周期规则见根目录
[CLAUDE.md](../CLAUDE.md#documentation-docs) 的 Documentation 章节。

| 路径 | 类型 | 状态 | 简介 |
|---|---|---|---|
| [plans/done/computer-use-multi-display.md](plans/done/computer-use-multi-display.md) | 计划 | 已完成 | Computer-use 多显示器支持:按屏截图/坐标、跨屏拖拽、benchmark min_displays 与 multi-display-calc;双屏/单屏/LLM smoke 实机验收完成 |
| [plans/done/macos-coordinate-chain-tests.md](plans/done/macos-coordinate-chain-tests.md) | 计划 | 已完成 | macOS 坐标修复、HTTP 链路测试、合成模型隔离与真机校准 |
| [research/macos-coordinate-chain.md](research/macos-coordinate-chain.md) | 调研 | 主屏校准通过、模型偏差复现 | 尺寸坐标链路、真实证据与验收边界 |
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
| [plans/done/computer-use-improvement-and-n2-plan.md](plans/done/computer-use-improvement-and-n2-plan.md) | 计划 | 实现已完成 | Part A、A17 harness 与现有 N2 插件已落地；完整 A/B 和真机控制验收移交 SDK 计划，处置见 §18 |
| [plans/done/plugin-subagents-and-n2-sdk.md](plans/done/plugin-subagents-and-n2-sdk.md) | 计划 | 已完成 | 通用派发/SDK 已实现并有真实 benchmark；条件性专项移交 backlog，不重复接入验收 |
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
- [plans/active/computer-use-strategy-ladder.md](plans/active/computer-use-strategy-ladder.md)：Computer Use 目标级宿主循环与策略阶梯；S0 已完成，G1/G2 核心治理、N2/N2 SDK/LLMAgent 兼容迁移和跨调用方离线公共验收通过；S1 AX/OCR 与冻结合成验收已实现、待最终评审；真实通道、Jev、恢复及 S2–S6 待验收，生产默认不变。
- [plans/done/computer-use-s0-review.md](plans/done/computer-use-s0-review.md)：S0 通用任务契约三轮评审与两轮重构已完成：修复清理取消/证据丢失/错误完成文案，合并重复序列化；后端 5220 passed、E2E 18 场景通过，最终复审无新增问题。
- [plans/done/portable-code-reviewer.md](plans/done/portable-code-reviewer.md)：通用评审角色已完成：工具无关 Markdown、24 项固定 Code Smell、权限与独立性分离、无问题即停止/最多三轮及项目测试/提交约定。
- [plans/done/shared-agent-sync.md](plans/done/shared-agent-sync.md)：多 Agent 同步工具已完成：递归发现、格式校验、配置保护、--check；29 项工具回归和完整项目验证通过。
- [design/shared-agent-definitions.md](design/shared-agent-definitions.md)：通用 Agent 定义格式、批量同步命令、覆盖保护与生成物检查规则。
- [plans/done/post-task-code-review.md](plans/done/post-task-code-review.md)：任务收尾评审规则已生效：验证通过后委派 code-reviewer 自主评审/必要重构，无问题即停止、最多三轮，已完成首次复核。
- [plans/done/computer-use-adaptation-and-grounding.md](plans/done/computer-use-adaptation-and-grounding.md)：macOS 适配与定位效果改进计划（M0–M8 已完成，2026-09-25 关档）：保留生产基线 A（一体 legacy 归一化，默认全程未切换）；静态首轮门槛无候选通过；calc-open 拆分显著优于适配一体+宿主还原（p=0.011）但宽任务集 A 10/36 > C 5/36 且 C 耗 1.7–2× token；AX 条件性暂缓；点击大偏移根因未解决（归因止于服务输出边界）；全计划 ≈35.4M tokens（unpriced）。收口汇总见 [M8 收口报告](../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)，触发式后续工作在 [backlog.md](backlog.md)。
- [plans/done/token-accounting-boundaries.md](plans/done/token-accounting-boundaries.md)：统一生产 token 用量记录，移回 benchmark trial/费用/预留策略；默认仅统计，修复显式零额度覆盖语义（2026-09-29 完成，第 1 轮独立评审通过）。
