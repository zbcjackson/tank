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
[macOS 适配与定位计划](plans/done/computer-use-adaptation-and-grounding.md)。
移出本表表示已有执行计划，不表示问题已修复；完整历史核对见该计划 §2。
2026-09-25：该计划已关档（M0–M8 完成或明确处置，结论 = 保留生产基线，
见 [M8 收口报告](../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)）；
其条件性条目继续留在本表按触发条件运作。

2026-09-26：Computer-use 多显示器支持已立项（本机具备双屏验收环境，生产/测试/benchmark 三线并行），移入
[多显示器支持计划](plans/done/computer-use-multi-display.md)。
2026-09-26：用户直接立项[策略阶梯与决策层计划](plans/done/computer-use-strategy-ladder.md)；
“AX 语义寻址选择模型复验”（列表呈现改进 + 类型化决策选择器现归 S1/S3）与
“OCR/控件检测 + 编号方案预检”（OCR 候选 + 编号选择归 S1）两宗条目被触发移入，
live 新实验预算按该计划 §8 逐批授权执行。
2026-09-28：该计划扩展为目标级宿主循环与 Jev 下一动作选择，LLM 按需介入；
原 D2 复验保留为阶段验证，未实现能力仍不视为已交付。

2026-10-18：[策略阶梯计划](plans/done/computer-use-strategy-ladder.md)的S5当前配置按不采用/证据不足收口；原确认试验仍未完成。以下接收其条件性后续，S6已按现行范围交付并完成评审归档。Jev图片需求保留，主线结论前置已满足，但尚无可归因于缺图的当前失败样本。

2026-10-18用户目标复审：已就「适用时Jev、视觉兜底」开启[混合计划](plans/active/computer-use-jev-vision.md)，
当前J的F/Advisor均为文本，旧结果未评估该目标。该计划负责混合路由与新评估；下表
长任务采用复验仍须先满足离线/开发准入，不因此启动收费确认。随后用户明确将
最新Jev视觉能力纳入该计划，图片Choice/状态判断、Box定位、同版有图/无图及
广泛Jev优先策略均已迁入，下表原图片/Box条目移除，尚未实现或授权新收费批次。
视觉完成核验和强OCR等独立条件项继续保留，不与视觉操作接管混同。

2026-10-22：V/JT补充校准的0.5%信息目标已被
[预注册](research/jev-supplemental-calibration-registration.md)选定并迁入当前设计。
760正例/152负例为本队列固定规模，新库资格与对应执行条件由
[主计划](plans/active/computer-use-jev-vision.md)承接；本次尚未开始模型测量。

| 项目 | 触发条件 | 背景/前置 | 来源 |
|---|---|---|---|
| ElevenLabs原配置语音E2E复测 | 明确授权将测试WAV音频及认证信息发送至ElevenLabs，再单独冻结可审阅的请求和配置范围 | 观察一致性修复时原配置语音commit超时，隔离远端复测被自动审批拒绝且未绕过。相同E2E在真实本地Sherpa/回环LLM/隔离DB下21场景83步通过，仅认证离线配置；不证明远端ASR健康。保留失败、拒绝及早期临时配置草案勘误，不改生产ASR代码 | [修复结案](plans/done/jev-navigation-observation.md)、[验证限制与证据](research/jev-navigation-observation.md) |
| Chromium首次导航间歇超时调查 | 隔离Chromium在首次观察返回前再次出现Page.goto超时或其后TargetClosedError | DOM光标修复的前两轮全回归出现3/2例加载失败，未改超时/断言；专项146次导航及最终6380后端/E2E21通过，未确定该加载波动原因。再现时保留导航请求/响应/load与现场状态，不默认归因光标或增加重试 | [DOM新鲜度记录](research/dom-visual-freshness.md) |
| Linkding恢复导航及回执诊断 | 后续独立批次再次出现恢复导航后effect_unknown、外层current=true后not_sent，或就绪修复后再次Save前dom_state/stale_reference拒绝 | cf402第152槽未知效果及Edit/Title not_sent的历史原因未定。执行准备另保全一次填Title后Save前dom_state拒绝；控制诊断独立证实的busy/CSS就绪缺口已修，当前完整96/原生96/假HTTP192通过，但不反推该历史Save因果。再现即停批，保留expected/current DOMView及精确差值、MutationObserver、HTTP/CSS/Turbo时间线、派发原因和物理读回；不重放、续跑、挑绿或补零消除未知 | [资格结案](plans/done/jev-supplemental-calibration-qualification.md)、[旧失败与新冻结](research/jev-supplemental-calibration-qualification.md)、[执行准备与历史Save证据](research/jev-supplemental-calibration-execution.md) |
| 多浏览器可见启动与现有会话接管 | **需求已确认**（2026-09-30 用户要求，允许后续实现）；待后续排期，确定逐浏览器接入及会话身份方案后立项 | 分别支持启动可见浏览器和接管用户正在使用的浏览器，授权范围内复用页签/登录态；不局限于 Headless Chromium。评估 Chrome、Edge、Firefox、Safari 等的实际支持范围与接入方式；验收身份绑定、用户操作冲突、撤权/取消、断连及清理所有权，原有浏览器仅解除附着。尚未实现，不改变已验收的S2及该S0–S6计划范围 | [策略阶梯计划 §9](plans/done/computer-use-strategy-ladder.md#9-还需依据实际执行调整的点)；2026-09-30 用户后续需求 |
| 客户端 token 携带（web/cli/device 连接时发 `?token=`） | 远程部署启动 | P0-2 只落地了服务端校验，三端客户端从未实现携带；需与 token 分发方式一并设计 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) P0-2 |
| 认证 token 分发方式定案 | 远程部署设计时 | 配置文件 vs 首次配对流程，计划 §11.2 未决问题 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §11 |
| Resume（断线续传） | 远程部署实测断线频繁到影响体验 | 现靠 session_id 恢复会话历史，在途 turn 状态全丢；需 text/audio 帧序号 + 重连 replay 窗口 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| WebRTC 传输 | 远程实测 Opus-over-TCP 仍因队头阻塞卡顿 | Opus-over-WS 已拿 80% 收益；届时 WebRTC 仅作传输层挂入，私有消息集原样复用（JSON 走 data channel） | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| Realtime 端点（`/v1/realtime`） | 第一个第三方客户端/机器人接入需求确认 | 作为边缘网关建立在演进后的私有栈之上（同一管线池 + 同一认证） | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| LLM Proxy | 出现需要借用服务端凭据的外部旁路任务 | tank 的摘要在服务端内部直调 LLM client，当前无旁路需求 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| LiteLLM / LangChain 模型调用层替换研究 | **需求已确认**（2026-10-04 用户要求登记）；待安排独立研究，不阻塞 Jev 核心 SDK 迁移 | 比较 LiteLLM SDK/可选网关与 LangChain 模型层能否替换自研供应商适配、消息/流式聚合、工具 schema、结构化输出、token 汇总及费用估算；不迁移 Agent 循环。用同一 Qwen 普通/流式工具调用、Jev Choice、取消/失败/未知用量样例，核对重试实际发送数、缓存/推理 token、首 token 延迟、依赖和可删除代码量。区分供应商 usage、本地估算与账单费用；保留 Tank 任务归属和停止语义，不保留重复客户端/重复记账。Jev 原生决策支持单独验证，不假设聊天接口等价；默认无额外网关服务 | 2026-09-29、2026-10-04 用户讨论；[策略阶梯计划](plans/done/computer-use-strategy-ladder.md#s3-mjev-核心-sdk-迁移2026-10-04-验收完成)、[现行 LLM 层](design/pipeline-architecture.md#llm-transport-layer-3)、[LiteLLM 文档](https://docs.litellm.ai/docs/)、[LangChain 模型文档](https://docs.langchain.com/oss/python/langchain/models) |
| Computer Use OCR/视觉完成核验后备 | 真实任务或新验收暴露 AX 值/标题不足以核验完成（缺标签画布、纯图像语义条件等），且批准独立实现切片 | S4-V 默认 AX 全窗口匹配；NL live 3/3 与原生矩阵未证明需要 OCR/视觉确认。原属 S4“选定视觉/通道”，2026-10-10 收口移交 | [策略阶梯计划 S4-V / S4 收口](plans/done/computer-use-strategy-ladder.md)；2026-10-10 用户确认方案 A |
| Computer Use S4-N 第二片（绑定后快照再写完成条件） | 端到端或真实任务证明仅靠 intake 预先写的 present/absent/title 不够（须对照初始快照收紧或改写完成条件） | S4-N 第一片 + live 3/3 已通过；第二片原按证据决定，无缺口故不阻塞 S4 | [策略阶梯计划 S4-N / S4 收口](plans/done/computer-use-strategy-ladder.md)；2026-10-10 用户确认方案 A |
| Computer Use 任务内切换 App | 端到端验收或真实任务证明“父代理拆成单 App 子任务、经结果与输入传值”不够用（如需在两个 App 间多次往返） | S4-B 一个任务只绑定一个 App 并可跟随同进程新窗口；任务内切换需多 App 授权、绑定生命周期与跨 App 候选设计 | [策略阶梯计划 S4-B](plans/done/computer-use-strategy-ladder.md#s4-b按请求打开复用-app-并绑定窗口2026-10-09设计已确认实施中)；2026-10-09 用户确认 |
| memory `pinned_soft_cap_kb` 软上限告警 | **前置已满足**（IMP-1 Dream Consolidation 已落地，默认关闭），可随时立项 | 12 KB pinned 软告警当初因无收敛路径而暂缓；现在 consolidator 可收敛超限 pinned 集，告警有意义了 | [memory-context-improvements.md](plans/done/memory-context-improvements.md) §0 |

| macOS 动态几何与高频输入验收 | 产品需要截图后切换主屏/分辨率或无截图高频连点，或这些条件下再次报告错点 | 当前静态主屏九点验收通过；默认尺寸/截图缓存不追踪动态几何，首次校准存在未确定原因的事件缺失；多屏支持见 [多显示器支持计划](plans/done/computer-use-multi-display.md) | [macos-coordinate-chain.md](research/macos-coordinate-chain.md) |


| Computer-use 原生协议与专用定位模型探索 | 明确需要该路线，取得可用端点/部署、协议与授权，并批准独立实验预算 | M3 已完成自定义 point/pixels/bbox 适配；原生点框、Responses computer、UI-TARS 未测试，不能由自定义工具结果推断支持性或收益 | [M3 收尾](plans/done/computer-use-adaptation-and-grounding.md#m3--具体模型的适配器与独立定位基线) |
| Computer-use 静态候选采用复验 | 决定重新考虑候选/提示配置，且准备新预算与未使用的独立 holdout | 首轮 544 次额度已用完；旧 holdout 歧义拒绝失败，唯一匹配修正仅三次开发 smoke。新冻结需覆盖正例和负例，不能复用旧数据宣称独立验收；M4–M8 集成/真实任务验收已在原计划完成（保留基线结论） | [M3 收尾](plans/done/computer-use-adaptation-and-grounding.md#m3--具体模型的适配器与独立定位基线) |
| Computer Use OCR 可点候选（强版融合） | 真实任务或新验收暴露 AX/DOM 完全缺失但屏幕有可点文字的界面（canvas 自绘 UI、地图标注、PDF 内链等），且批准独立实验切片 | 用户原始想法＝OCR 识别截屏文字位置找可交互元素（typesafe-computer-use/OmniParser 路线：OCR 框→编号候选→Jev 选→点框内中心）。保守版 context-only 融合契约已实现（fusion.py，2026-10-13）；强版需坐标基归一（AX 屏幕全局点 vs OCR 截图像素）、"文字≠控件"误操作入分母、框中心点空三个失败模式分别统计；样本可用合成 canvas 页起步。2026-10-13 用户确认挂起 | [策略阶梯计划 S5-App 线 3](plans/done/computer-use-strategy-ladder.md)；[调研 L3 档](research/computer-use-strategy-ladder.md#33-l3-ocr-文本区域)；[typesafe-computer-use 感知](research/jev-computer-use-comparison.md) |
| Computer Use AX/OCR只读融合接线 | 冻结AX缺标签/正文不可读的真实样本与AX完整负对照，证明OCR提供足以抵消误候选/延迟的补充信息 | fusion.py保守context-only契约已实现，工厂未接线；先统一AX屏幕全局点与OCR图像像素坐标基，保留来源/完整性与只读门控，再比较AX/OCR/融合。OCR不因此变成可执行控件，强版可点候选仍按既有用户挂起条目处理 | [策略阶梯计划S5-App线3](plans/done/computer-use-strategy-ladder.md) |
| Computer Use 长任务策略采用复验 | 取得可解释当前失败的新通用修复、模型/策略配置或独立任务族依据，并先通过离线/小规模完整context准入门；再立新计划/新冻结 | 当前DOM无净收益、独立长任务L2未过、完整context四项未过全4门；原150项确认均未完成、H1–H4未判定。停止同配置追加，不补跑旧目录、不复用已见holdout宣称独立确认，不以费用或时间单项达标替代成功质量 | [策略阶梯计划S5正式处置](plans/done/computer-use-strategy-ladder.md)、[补充真实校准未知回执](research/jev-supplemental-calibration-live.md) |
| Computer Use DOM视图与观察稳定性受控优化 | 真实任务暴露文本/同名区分/滚动或延迟状态覆盖缺口，或既有计时事件证明观察开销是主要瓶颈 | DOM原子读取已具备；S5-App线1无活跃新臂，线4尚无unknown/误判证据触发。先做同一driver contract，再单变量比较视图/有界等待/事件或操作覆盖，不凭微基准启用，不重放未知副作用 | [策略阶梯计划S5-App](plans/done/computer-use-strategy-ladder.md) |
| Computer Use Cua Driver可选后端 | 现有直接AX/Quartz后端出现可复现契约/能力缺口，且选定可验证的替代驱动、安装与权限方案 | 依赖已移除、S5-App线2暂缓；先验证窗口/元素身份、新鲜度、派发回执、取消和清理，再同任务独立读回对照。executed不等于业务完成，不因登记而安装驱动 | [策略阶梯计划S5-App与正式处置](plans/done/computer-use-strategy-ladder.md) |
| Computer Use 视觉Advisor | 可复现任务证明AX/DOM/OCR文字与候选不足以补齐业务条件或规划，且冻结视觉语义样本及文字已足够的负对照 | 当前Advisor仅文本；视觉请求需独立的宿主图片准入、范围/尺寸/预算与数据预览，不能给模型自由工具循环或放宽GoalPatch/完成条件。先比较文字/有图的增量价值，独立完成核验保持，不以图片判断替代实际效果证据 | [策略阶梯计划S4范围与S6交付](plans/done/computer-use-strategy-ladder.md) |
| Computer Use RapidOCR第二观察后端 | 本地Vision在独立冻结样本上失败，且第二后端有可验证改善 | Vision合成样本验收不证明通用识别率；先保留几何/来源与只读边界，再比较召回/误匹配/开销，不自动生成可点控件 | [策略阶梯计划§9](plans/done/computer-use-strategy-ladder.md) |
| Computer Use 确定性规则的模型替代 | D1/D3/D4/D5规则出现可归因瓶颈，且潜在任务收益能覆盖额外模型开销 | 默认确定性可判不强加模型；做单变量、有独立验收的比较，不把已实现Jev下一动作选择再算新实验 | [策略阶梯计划§9](plans/done/computer-use-strategy-ladder.md) |
| Computer Use AX副屏任务验收 | 需要在副屏执行真实AX任务，且具备受控窗口/输入清理与独立读回环境 | 几何/多显示器坐标支持不等于AX副屏效果已验收；单列新鲜引用、窗口/屏幕绑定、移窗/布局变化和误动作验证，不由主屏9/9外推 | [策略阶梯计划§9与S6范围](plans/done/computer-use-strategy-ladder.md) |
| Task跨进程恢复与崩溃资源回收 | 明确需要跨宿主重启继续任务，并能先定义持久授权/账本/未决回执与外部资源归属契约 | 当前仅同进程原协程恢复；跨进程需独立运行时/恢复设计，原生引用必须作废重观察，未知副作用不重放，不能当新预算重跑或擅自关闭借用应用 | [策略阶梯计划§2.6与S6范围](plans/done/computer-use-strategy-ladder.md) |
| Task审计存储容量与保留策略 | 实际审计体量、存储预算或部署保留期限需要运营政策 | 本期验证逐动作持久审计及失败关闭，不提供全局数据库容量/自动清理；后续需明确保留/归档/删除及失败处置，不能因存储满而把必需审计改为普通遥测或删除unknown对账证据 | [策略阶梯计划S0范围与S6交付](plans/done/computer-use-strategy-ladder.md) |
| Computer Use 旧unknown用量对账 | 取得原请求可关联的提供方usage或实际账单证据 | 最近确认/诊断链旧预留$0.380096640继续保留；研究结束和未运行trial终止不等于已发送未知请求免费。不重发原请求来猜旧用量，不将该链known+held当作全部S5/开发服务账单。2026-10-23补充真实校准另有视觉调用db3b8e82c7c24a2da86d6a31f21bbbff用量未知，已知156643 tokens不含该未知部分；本轮unpriced/零数字预留不等于未知免费，不与旧美元预留混算 | [策略阶梯计划S5正式处置](plans/done/computer-use-strategy-ladder.md) |
| 受控遮罩误点后盖住目标窗口 | pair-1/2/3 配对 core trial 开跑前，或再次观察到“窗口消失/全黑”导致的 `launch_app` 重试 | A-control 单轮首次批量点击落到始终置顶的受控黑背景（归一化 x≈850 → 屏幕 x≈1632，窗口右缘约 1270），随后目标窗口被遮罩盖住，模型需 3 次 `launch_app` 才恢复；材料层已加派发前窗口门禁（窗外点击零派发并记 `gate_blocked`），后续 M5 core/M6/M7 各批遮罩陷阱未再发生；但门禁属 launcher 材料而非生产代码，移除材料或生产环境复现时仍需对策 | [A-control 单轮证据](../backend/benchmarks/computer_use/reports/20260924-m5-a-control-pumped-pilot/README.md)、[门禁材料](../backend/benchmarks/computer_use/reports/20260924-m5-pixels-unified-ready/README.md) |
| 子代理链路历史压缩机制 | 长任务 routinely 触顶 token 预算（M6 长历史两轮均 300k 处受控停止，27/17 步远未到步数/时限上限），且需要子代理完成更长流程 | M6 第 4 项发现：ContextManager/Compactor 只存在于主助手语音路径，自研子代理链路（SubAgentDriver → AgentRunner → LLMAgent → chat_stream）无压缩；长历史行为验收（当前图引用/失败恢复）已通过，机制引入未做 | [M6 长历史报告](../backend/benchmarks/computer_use/reports/20260924-m6-longhistory/README.md) |

### 原始DOM闭环实测与中性命名拒绝边界

- **触发条件**：生产具备公开DOM可验证的目标/字段业务谓词及保存后效果/完成读回，
  并通过正确保存、只填未保存、只回列表、错误行及保护字段等资格后，按实际证据分片；
  自然视觉需求先资格，不强迫Jev弃权。准备扩大真实用户写入前也必须完成该验证。
- **背景/前置**：六项真实实测0/6；原版sqlite-web参考保存已成功，但生产DOM仅URL
  有受支持status事实，真实Runner正确保存后仍effect_unknown，textbox条件被拒绝。
  旧24次边界负例含Absent/Shared提示，本片中性名称及误导词存在目标仍未实测，
  不能据此作拒绝泛化或真实写入认证。生产核验能力的修复应先于该收费实测。
  2026-10-25[显式表格GET读回](plans/done/dom-table-readback.md)已完成并通过最小
  真产品/假HTTP核验；2026-10-25两个正例已移交[真实模型试跑](plans/done/jev-runtime-smoke.md)。
  本条仅保留中性命名拒绝、歧义/缺参和自然视觉需求；不得用初始已成立的完成条件
  充当模型拒绝。它们需单独资格，不阻塞两个正例，也不机械补齐旧六任务。
- **来源**：[原始DOM资格研究](research/jev-runtime-acceptance.md)、
  [主计划](plans/active/computer-use-jev-vision.md)。剩余条件触发进入新计划时移除此条。
