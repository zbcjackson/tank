# Tank 文档索引

`docs/` 按文档类型分目录存放。目录职责与生命周期规则见根目录
[CLAUDE.md](../CLAUDE.md#documentation-docs) 的 Documentation 章节。

| 路径 | 类型 | 状态 | 简介 |
|---|---|---|---|
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
- [plans/active/computer-use-adaptation-and-grounding.md](plans/active/computer-use-adaptation-and-grounding.md)：效果改进计划（执行中：M1 输入/本地图像验收及首步提示 A/B 完成，未观察到定位收益；M0 离线失败集/64 布局 holdout/manifest 已补齐，M2 frame/宿主还原及主屏九点验收已完成，M3 十六次合成图端点/协议预检已记录，strict 未保证 Qwen3.8 Flash 格式，生产共用协议/LLM 单次调用接口已实现，首批四十次多布局点/框筛选完成，未决定采用，后续分因素调参与模型效果验证）；复用 N2 benchmark，覆盖已知问题、模型适配、规划定位分离、四组对照与真实效果验收。
