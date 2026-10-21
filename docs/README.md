# Tank 文档索引

`docs/` 按文档类型分目录存放。目录职责与生命周期规则见根目录
[CLAUDE.md](../CLAUDE.md#documentation-docs) 的 Documentation 章节。

| 路径 | 类型 | 状态 | 简介 |
|---|---|---|---|
| [plans/done/computer-use-multi-display.md](plans/done/computer-use-multi-display.md) | 计划 | 已完成 | Computer-use 多显示器支持:按屏截图/坐标、跨屏拖拽、benchmark min_displays 与 multi-display-calc;双屏/单屏/LLM smoke 实机验收完成 |
| [plans/done/macos-coordinate-chain-tests.md](plans/done/macos-coordinate-chain-tests.md) | 计划 | 已完成 | macOS 坐标修复、HTTP 链路测试、合成模型隔离与真机校准 |
| [research/macos-coordinate-chain.md](research/macos-coordinate-chain.md) | 调研 | 主屏校准通过、模型偏差复现 | 尺寸坐标链路、真实证据与验收边界 |
| [research/jev-computer-use-comparison.md](research/jev-computer-use-comparison.md) | 调研 | 源码对比完成，改进待验证 | 三个 Jev 开源项目的职责、观察、历史与规划交接；对照 Tank S4 原生失败和后续验证优先级 |
| [research/computer-use-hybrid-review.md](research/computer-use-hybrid-review.md) | 调研 | 复审完成，收益待验证 | 当前J/F无视觉兜底；评估对象/数据/标准复审，追加最新图片与Box能力边界及三级对照 |
| [research/jev-image-capability-pilot.md](research/jev-image-capability-pilot.md) | 调研 | 首轮完成，结论开放 | 260次真实请求；Jev图片Choice/Box各52/52，Qwen契约失败需修正；仅两种合成布局，未判采用 |
| [research/jev-image-capability-v2-pilot.md](research/jev-image-capability-v2-pilot.md) | 调研 | v2重测完成，结论开放 | 260次请求；Qwen26/52严格合格、22/52通过，含重复键/额外字段及单位混用线索；Jev图片路径各52/52 |
| [research/jev-image-native-pilot.md](research/jev-image-native-pilot.md) | 调研 | 真实计算器小样本完成 | Jev图片闭环2/2、只读Box中心2/2；12次请求，完整AX仍在，图片增量与跨应用能力待验证 |
| [research/jev-image-real-app-ablation.md](research/jev-image-real-app-ablation.md) | 调研 | TextEdit小样本完成 | 图片选择3/3正确、闭环2/4；文本3次调用均弃权；Box3/6数量判断通过、3项帧拒绝，下一步诊断稳定性 |
| [plans/done/jev-image-real-app-ablation.md](plans/done/jev-image-real-app-ablation.md) | 计划 | 已完成 | 第二真实应用文本/图片对照与只读Box已运行，196项原始工件归档，拒绝与未完成保留分母 |
| [research/jev-frame-freshness-diagnostics.md](research/jev-frame-freshness-diagnostics.md) | 调研 | 机制已复现 | 确认整屏缩小再裁剪可引入窗口外像素；18次只读检查中5次像素拒绝，未改生产或旧评分 |
| [plans/done/jev-frame-freshness-diagnostics.md](plans/done/jev-frame-freshness-diagnostics.md) | 计划 | 已完成 | 无模型TextEdit新鲜度诊断，8上下文清理通过，97项证据及独立审查完成，后续捕获修复由主计划承接 |
| [plans/done/jev-bound-frame-capture.md](plans/done/jev-bound-frame-capture.md) | 计划 | 已完成 | 绑定窗口先裁剪backing像素再缩放；完整回归、24次只读检查与独立审查通过 |
| [research/jev-post-crop-live-validation.md](research/jev-post-crop-live-validation.md) | 调研 | 真实复测完成 | 颜色图片4/4完成；指定行两臂模型各4/4正确，文本1次frame_scene拒绝；小Box中心0/2、数量6/6 |
| [plans/done/jev-post-crop-live-validation.md](plans/done/jev-post-crop-live-validation.md) | 计划 | 已完成 | 无固定请求/费用上限的22次真实判断已归档，两轮独立审查完成，含文字充分对照及精确拒绝阶段 |
| [plans/done/jev-box-crop-comparison.md](plans/done/jev-box-crop-comparison.md) | 计划 | 已完成 | 70请求与归档完成，两轮独立审查通过；Jev/Gemini中心与数量分别报告 |
| [research/jev-box-crop-comparison.md](research/jev-box-crop-comparison.md) | 调研 | 真实开发对照完成 | Jev中心5/8→8/8；Gemini7/8→8/8但裁剪一次误报唯一；无重试或点击 |
| [plans/done/jev-vision-route-pilot.md](plans/done/jev-vision-route-pilot.md) | 计划 | 已完成 | 24任务/40调用及两轮独立审查完成；JT正例6/6、V2/6，执行拒绝和全部失败保留 |
| [research/jev-vision-route-pilot.md](research/jev-vision-route-pilot.md) | 调研 | 真实开发对照完成 | V四个正确保存选择后被执行门拒绝；JT往返完成，参考路径需新鲜度诊断 |
| [plans/done/dom-visual-freshness.md](plans/done/dom-visual-freshness.md) | 计划 | 已完成 | 光标机制、完整回归、归档及第1轮独立审查通过，旧失败保持 |
| [research/dom-visual-freshness.md](research/dom-visual-freshness.md) | 调研 | 组件机制已解决 | 96次无模型检查、108即时PNG；通道拒绝6/16→0/16，其他守卫保持；首次加载波动未确定原因 |
| [plans/done/jev-vision-route-followup.md](plans/done/jev-vision-route-followup.md) | 计划 | 已完成 | 修复后36任务/66调用，第2轮独立结果审查通过；两臂正例10/10、负例8/8，真实弃权兜底6/6，旧结果不重判 |
| [research/jev-vision-route-followup.md](research/jev-vision-route-followup.md) | 调研 | 真实开发复测完成 | 原24项均通过；新增JT六项先弃权后同绑定图片接管，无猜选；三种已见手写布局非确认集 |
| [plans/done/jev-real-product-route.md](plans/done/jev-real-product-route.md) | 计划 | 已完成 | 真实sqlite-web12项及第2轮独立结果审查完成，V6/6、JT5/6，GET恢复各2/2；未建立净收益，失败与旧证据保留 |
| [research/jev-real-product-route.md](research/jev-real-product-route.md) | 调研 | 真实单产品开发实验已执行 | JT少图但质量较低，封顶均值未提速；同图不同输出和逐列checkbox缺候选分别记录，未测列表/确认 |
| [plans/done/jev-checkbox-grounding.md](plans/done/jev-checkbox-grounding.md) | 计划 | 已完成 | 第1轮独立审查通过；同页逐列候选0→3，12上下文36输入0模型，强列回执区分已写集合；新开发配方仅prepare |
| [research/jev-checkbox-grounding.md](research/jev-checkbox-grounding.md) | 调研 | 无模型诊断完成 | 全选触及三列、仅选title触及一列；修复候选遗漏，不重判旧模型失败或推断模型收益 |
| [plans/done/jev-checkbox-route-retest.md](plans/done/jev-checkbox-route-retest.md) | 计划 | 已完成 | 第1轮独立结果审查通过；V6/6、JT6/6，均时28.771/5.000秒，图片20/1；一次实际弃权接管并返回，保留13旧归档 |
| [research/jev-checkbox-route-retest.md](research/jev-checkbox-route-retest.md) | 调研 | 修复后真实开发复测完成 | 原失败此次选逐列title并完成；本批质量齐平且JT更快少图，单产品已知案例非独立采用确认 |
| [plans/done/jev-product-list-workflow.md](plans/done/jev-product-list-workflow.md) | 计划 | 已完成 | 第2轮独立结果审查通过；V/JT各4/4，编辑GET恢复各2/2，均时46.258/6.736秒，图片18/1；旧14归档保持 |
| [research/jev-product-list-workflow.md](research/jev-product-list-workflow.md) | 调研 | 真实列表工作流开发实验完成 | 自主选记录、编辑并核验返回内容；一次图片接管再返回Jev，固定两行/次序非独立确认 |
| [plans/done/jev-second-product-qualification.md](plans/done/jev-second-product-qualification.md) | 计划 | 已完成 | 第1轮独立审查通过；原版linkding原生脚本4/4，视觉资格仍被隐藏动画阻塞，声明式任务冻结/零模型 |
| [research/jev-second-product-qualification.md](research/jev-second-product-qualification.md) | 调研 | 宿主阻塞已定位 | 32完整观察，列表16/16可读图、编辑页16/16拒绝；隐藏无限动画/5张同字节PNG，不是模型比较 |
| [plans/done/dom-hidden-animation.md](plans/done/dom-hidden-animation.md) | 计划 | 已完成 | 隐藏伪元素双重定义检查；资格32/32及5归因通过，同轮两次独立审查完成 |
| [plans/done/jev-linkding-route.md](plans/done/jev-linkding-route.md) | 计划 | 已完成 | 同轮两次独立审查通过；真实V/JT各2/2，均时34.614/12.047秒，9741成员核验一致 |
| [research/jev-linkding-route.md](research/jev-linkding-route.md) | 调研 | 两臂成功、本批JT更快少图 | 原版第二产品四项、12 SDK、107904已知tokens、4清理；非独立采用确认 |
| [plans/done/jev-confirmation-preparation.md](plans/done/jev-confirmation-preparation.md) | 计划 | 已完成 | 两轮审查通过；24业务/104图通过，候选资格0/24，正式N与收费未准入 |
| [research/jev-confirmation-preparation.md](research/jev-confirmation-preparation.md) | 调研 | 新列表容量阻塞 | sqlite-web37–38候选超32；linkding聚合值截断/不完整；正式N与收费未准入 |
| [plans/active/computer-use-jev-vision.md](plans/active/computer-use-jev-vision.md) | 计划 | 确认准备审查通过 | 下一步修容量/完成事实及验收后再校准确认；生产默认不变；[真实配方](../backend/benchmarks/computer_use/fixtures/jev-image-native/README.md) |
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
- [research/computer-use-strategy-ladder.md](research/computer-use-strategy-ladder.md)：策略阶梯机制调研；后续S0–S6实现与研究已按范围收口，已测Jev＋文本回退未形成稳定净收益采用证据，历史机制与当时未实现状态保留；Jev＋视觉协作另见复审。
- [plans/done/model-call-naming.md](plans/done/model-call-naming.md)：通用模型调用/流式命名收敛，Jev 客户端创建与关闭交还官方 SDK，采用默认环境代理/证书行为；不涉及 S4。
- [plans/done/model-call-simplification.md](plans/done/model-call-simplification.md)：已完成独立 DecisionModel 与任务薄包装，清理 Jev/普通聊天的 Route/Transport，采用 SDK 调用级记账及可选 Langfuse；API 3，后端 5579 通过、E2E 17 场景通过，S4 未启动。
- [plans/done/computer-use-goal-contract-unification.md](plans/done/computer-use-goal-contract-unification.md)：已统一目标驱动 GoalContract，移除 v1/里程碑兼容路径并迁移调用、测试及可执行 benchmark；评审修复 submit 自动执行与观察恢复判断，后端 5608 通过、E2E 17 场景通过。
- [plans/done/computer-use-strategy-ladder.md](plans/done/computer-use-strategy-ladder.md)：Computer Use策略阶梯S0–S6交付归档完成（2026-10-18）。S0–S4及G1–G3按各自范围验收，S5当前配置按不采用/证据不足结案；两个150项仍各6完成/144未运行，H1–H4未判定。默认保持不变，后续图片/Box等条件项交接backlog，旧unknown预留保留。S6最终后端6149/E2E20回归、导航及138个原始工件核验通过；第1轮独立评审修正pilot调用数包含关系，第2轮评审者自检无遗留即结束，归档状态补记由评审者自检。
- [plans/done/computer-use-s0-review.md](plans/done/computer-use-s0-review.md)：S0 通用任务契约三轮评审与两轮重构已完成：修复清理取消/证据丢失/错误完成文案，合并重复序列化；后端 5220 passed、E2E 18 场景通过，最终复审无新增问题。
- [plans/done/portable-code-reviewer.md](plans/done/portable-code-reviewer.md)：通用评审角色已完成：工具无关 Markdown、24 项固定 Code Smell、权限与独立性分离、无问题即停止/最多三轮及项目测试/提交约定。
- [plans/done/shared-agent-sync.md](plans/done/shared-agent-sync.md)：多 Agent 同步工具已完成：递归发现、格式校验、配置保护、--check；29 项工具回归和完整项目验证通过。
- [design/shared-agent-definitions.md](design/shared-agent-definitions.md)：通用 Agent 定义格式、批量同步命令、覆盖保护与生成物检查规则。
- [plans/done/post-task-code-review.md](plans/done/post-task-code-review.md)：任务收尾评审规则已生效：验证通过后委派 code-reviewer 自主评审/必要重构，无问题即停止、最多三轮，已完成首次复核。
- [plans/done/computer-use-adaptation-and-grounding.md](plans/done/computer-use-adaptation-and-grounding.md)：macOS 适配与定位效果改进计划（M0–M8 已完成，2026-09-25 关档）：保留生产基线 A（一体 legacy 归一化，默认全程未切换）；静态首轮门槛无候选通过；calc-open 拆分显著优于适配一体+宿主还原（p=0.011）但宽任务集 A 10/36 > C 5/36 且 C 耗 1.7–2× token；AX 条件性暂缓；点击大偏移根因未解决（归因止于服务输出边界）；全计划 ≈35.4M tokens（unpriced）。收口汇总见 [M8 收口报告](../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)，触发式后续工作在 [backlog.md](backlog.md)。
- [plans/done/token-accounting-boundaries.md](plans/done/token-accounting-boundaries.md)：统一生产 token 用量记录，移回 benchmark trial/费用/预留策略；默认仅统计，修复显式零额度覆盖语义（2026-09-29 完成，第 1 轮独立评审通过）。

- [plans/done/remove-n2.md](plans/done/remove-n2.md)：N2 与 SDK 及专用扩展已移除，SubAgent 按当前 Computer Use 精简；完整验证通过，第 1 轮独立评审无可操作问题（2026-10-02 完成）。
