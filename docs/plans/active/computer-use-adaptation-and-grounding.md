> 状态：执行中，2026-09-20。M0 离线基线与采用门槛已冻结；M1 输入矩阵、本地图像证据和提示单因素首步 A/B 已验收，未观察到定位收益，通用自动像素评分仍为 unknown。M0 离线失败集、64 布局 holdout 和 dry-run manifest 已补齐，实际端点首批预检见 M3；M2 显式 frame/宿主坐标还原及主屏九点验收完成，M3 十六次预检及四十次点/框筛选已记录，thinking 中止后已在余额恢复时补跑 26 次、完成 32 设置对照（历史 402 保留），共用适配与生产 LLM 单次调用接口已实现，其余模型验收待完成；M4–M8 待完成。N2 复用既有 benchmark。

# macOS Computer use：模型适配、规划定位分离与完整验收

## 1. 目标与范围

以自研 computer_use 路径为主，回答三个可分离的问题：当前大偏移有多少来自
模型接口适配、规划与定位混合、定位模型本身；同时修复已经确认的宿主缺陷。
目标是得到可回退、可追溯且经独立评分验证的方案，不预设换模型一定最好。

- 本轮执行范围是稳定 macOS 主屏；实现截图身份/几何检查，但不承诺多屏支持。
- 模型适配与规划定位分离是核心里程碑，不依赖 AX 完成；AX/视觉解析为独立
  实验分支。统一内部坐标与保留各模型外部协议可以并存。
- 复用 AgentRunner、LLM profile、ToolManager、现有 benchmark/validator。
  不另造 Supervisor，不把定位服务实现为第二套后台代理调度。
- N2 已验证，优先复用既有 benchmark。当前目标是改进定位与任务效果，
  不把 N2/SDK 接入重验、完整 WS 专项或全套三路重跑作为前置或关档门槛。
  涉及共享代码的必要回归仍执行；新定位架构不重写 SDK。
- 默认模型、旧接口及历史分数保留，候选使用独立 profile/模式。完成比较后
  明确采用决定，不能因某次合成图全中就自动切生产。
- 真实动作串行执行；2026-09-19 用户已要求开始执行。真实图外发仍遵循 §6 的范围确认。

依据：[现行行为与验证边界](../../design/computer-use.md)、
[逐轮证据](../../research/macos-coordinate-chain.md)、
[外部实现对照](../../research/computer-use-implementation-comparison.md)。

## 2. 历史完成核对

“专项计划完成”表示其中规定的实现/实验与归档完成，不等于模型偏差已经
消失或所有发现都修复。以下状态以 2026-09-19 仓库证据为准。

### 2.1 已完成的工作与明确边界

- [静态坐标链计划](../done/macos-coordinate-chain-tests.md)：主屏截取、Retina
  尺寸检查、边界/非法值、鼠标位置读取修复；真实 Pillow、SDK HTTP、SSE、
  ToolManager 到 Quartz 参数回归；九点最终多轮每轴误差 ≤1 point。
  不等于多屏/动态/高频验收，也未解释最初的事件缺失和回读异常。
- [坐标协议与评分](../done/macos-grounding-contract.md)：固定图坐标假设和
  point-only 对照、Calculator 当轮表达式/结果 validator 已落地；证明统一
  倍率不是普适修复。没有完成截图像素自动评分和所有合法输入路径的定义。
- [100 次消融](../done/macos-grounding-ablation.md)、
  [80 次同提供方对照](../done/macos-grounding-model-comparison.md)、
  [304 次协议/模型隔离](../done/macos-grounding-protocol-isolation.md)：
  原始响应前已有错点、格式约束不足、原生 API 也错等结论有记录。
  GPT-5.5 32/32 来自 16 布局同一归一化点协议各重复两次，非 32 独立布局。
  Calculator 真值点击 3/3、12 次光标误差 ≤1 point，验证执行而非模型识别。
- [DeepSeek 112 次复测](../done/deepseek-grounding-budget.md)：探针支持独立
  thinking/预算开关；4000 是诊断默认值；关闭思考减少输出，未解决定位。
  未据此修改生产预算或宣称 DeepSeek 实机闭环通过。
- [GPT-5.5 闭环](../done/gpt55-computer-use-loop.md)：真实 calc-open 三轮
  严格 2/3，含两段鼠标成功与一次反馈恢复；失败轮是粘贴后的表达式缺失，
  不是一次错点。temperature 路由拒绝已修复并覆盖实际 HTTP。
  不是全套任务、Supervisor/语音入口或长期可靠率验收。
- **N2 与 SDK 均有真实 benchmark，不能再写成未运行。**
  [旧 N2](../../../backend/benchmarks/computer_use/reports/20260917-092518-n2-current-baseline/report.md)
  为 33/42（报告 79%，465 次 API 调用）；
  [N2 SDK](../../../backend/benchmarks/computer_use/reports/20260918-014936-n2-sdk-baseline/report.md)
  为 strict 4/36、smoke 2/6（548 次 API 调用），记录 macOS、SDK 0.9.29、
  trial-token-v2，42 个 trial 的 cleanup 字段均为 confirmed。
  [自研 Part A](../../../backend/benchmarks/computer_use/reports/20260916-031026-partA-macos/report.md)
  为 7/42。用户再次确认 N2 之前已验证；这些结果是现成参考和失败样本来源。
  三份报告评分/版本不同，按各自口径保留，不直接计算统一严格成功率提升；
  评分不同不构成否定已经测试或强制重跑全部 N2 的理由。
- [外部实现调研](../done/computer-use-implementation-research.md)：官方源码/
  文档核对和方案归档完成；模型 adapter、独立 grounder、AX/OmniParser
  候选尚未生产实现，也未验证这些项目在本机一定更可靠。

### 2.2 未完成问题与唯一追踪位置

- **I01 提示职责冲突**：M1 已修复并通过离线 HTTP 回归；小样本首步 A/B
  两组均 0/6 命中，未观察到定位收益，完整任务效果仍由 M5/M6 验证。
- **I02 输入语义与评分**：粘贴/逐键行为差异已复现，工具契约和业务评分
  已增加显式粘贴与分轨证据，实机矩阵完成并修复 IME/Shift 输入问题；
  旧 strict 结果不追改 → M1。
- **I03 截图像素与当轮结果证据**：M1 已完成受控图像独立核验和实际 SDK
  本地回放；通用自动像素评分仍 unknown，真实模型闭环与新鲜度 → M6。
- **I04 全局尺寸缓存、crop 依赖模型还原**：代码确认，静态公式有测试，
  M2 已增加显式 image/frame 绑定与宿主逆变换；默认 legacy 保留。
- **I05 模型适配**：探针有多种协议，不等于生产已有版本化 adapter → M3。
- **I06 规划定位分离**：只有建议，尚无独立定位服务及端到端对照 → M4/M5。
- **I07 AX/视觉解析辅助**：AX oracle 已有，通用候选发现、AXPress、专用
  定位器及结构化编号方案未验收 → M7。
- **I08 效果验证、长历史、跨应用、资源清理**：已有截图反馈和部分自动化，
  未完成更广泛实机验收；GPT trial 的 cleanup=unknown 不能算已确认清理
  → 改动后的自研路径 M4/M6。N2 SDK 已有 trial cleanup=confirmed 记录；
  本次无需为 N2 重新建立整套接入/控制验收。
- **I09 早期真实校准异常**：后续通过但初次事件丢失/回读不一致原因未知，
  首次 Calculator 光标断言缺少坐标归档 → M6 补可复现证据；不补写根因。
- **I10 多屏、动态分辨率、无截图高频压测**：尚未完整验收，当前静态错点
  不依赖这些条件。M2 测几何失效拒绝；扩大硬件/压力支持仍在
  [backlog](../../backlog.md)，不阻塞纯视觉主线。
- **I11 服务端预处理或模型权重的独立归因**：证据仅到服务输出边界；
  跨同权重部署需要可用的等价端点。M3/M5 记录可识别的差异，不能以本计划
  收敛为由声称已知道私有服务内部机制。

### 2.3 旧计划完成与本次效果改进的边界

两份旧计划保持 done。根据用户确认和本次读取的真实报告，N2 已有完整
benchmark，不能仅因历史清单未勾选就写成“还未验证”。

- [benchmark 修复](../done/computer-use-benchmark-fixes.md) 与
  [插件/N2 SDK](../done/plugin-subagents-and-n2-sdk.md) 保留实现、修复和实验
  历史；原报告中的失败用于改进定位和执行效果，不重新开一轮接入验收。
- 本次必做项是 M0–M8：已知问题修复、截图与坐标契约、模型适配、规划定位
  分离、因果对照、真实任务效果与采用结论。N2 只作为已有参照；需要新同尺
  数据时按 R 补必要任务，不要求先全套三路重跑。
- 旧完整 WS/通知、独立 SDK 停止压力/特定平台能力未被普通 benchmark 全部
  证明，但不属于本次效果改进的必做项；发生相关变更/新问题时按
  [backlog](../../backlog.md) 定向验证。不能把退出本轮范围写成已实测通过。
- Linux、多屏、高频压力、采用后暂停/恢复维持条件触发；不阻塞当前 macOS
  效果改进。旧计划的历史描述以当前范围决定为准，不再产生重复待办。

## 3. 目标调用链与接口约束

一体模式继续可运行；分离模式按以下链路接入：

```text
截图 → 不可变 Observation → 规划器决定目标/动作
                              ↓ locate(frame_id, target, window)
                        定位器 + 对应模型适配器
                              ↓ GroundingResult
                       宿主转换/检查 → Quartz 动作
                              ↓ 新截图/应用效果
                           规划器继续或结束
```

- Observation 保存会话/frame 身份、主屏/窗口身份、实际上传 image_size、
  对应的屏幕逻辑矩形、实际裁剪边界/轴向缩放变换及图片 hash。使用实际整数
  裁剪结果，不用理想化比例替代舍入后尺寸；不共享可覆盖的模块级状态。
- 模型适配器负责具体模型/端点的图片、参数、schema 和响应解析，返回统一
  的图片内点/框。逆映射只在宿主执行，Retina 不重复相乘，不按数值猜单位。
- 定位器只看绑定的当前帧、目标描述和必要窗口约束；不给旧点击坐标暗示、
  整段聊天历史、benchmark 真值或执行工具。返回 found/not_found/ambiguous，
  使用原生点/框解析后的内部类型，不强制模型原生 API 支持同一种 JSON。
- 主代理仍可看截图理解任务，但只选目标和动作，不计算坐标。定位结果
  绑定调用时 frame，执行层校验；模型自报 frame_id 不能覆盖宿主的绑定。
- 新观察/布局失效后重新定位；frame_id 并不能检测所有同窗口内容变化。
  执行返回派发状态、是否有独立效果证据和观察引用，不把“已派发”当“已完成”。
- 定位调用沿用任务预算、取消与截止时间，计账一次、可追踪；不递归委派。

## 4. 分阶段执行

### M0 — 冻结基线与实验清单

- [ ] 记录工作树/git、macOS 主屏逻辑/backing 尺寸、应用版本、端点实际模型/
  provider、最终 system、工具定义、thinking/detail/预算及 validator revision。
- [x] 复用现有 probe 和 benchmark，新输出目录；保存历史失败作为回归集合，
  另生成未用于调参的 holdout。历史结果按原口径保留。
- [x] 明确模式开关与每个实验仅变化的因素；产生 dry-run manifest，列出请求
  数、最大 token/时间、图片来源和出站端点。先完成离线验证再调用模型。
- [x] 在看 holdout 结果前冻结 M8 的采用门槛、评分分母与失败分类；若调整，
  新开实验批次，不在结果出来后改变阈值挑选赢家。

验收：可从 manifest 重建请求和评分；不依赖会话记忆、临时配置或未归档真值。

2026-09-20 离线补齐见 [M0 准备报告](../../../backend/benchmarks/computer_use/reports/20260920-adaptation-m0-preparation/README.md)。
当前配置、最终 SDK 请求与本机环境已记录；第一项因实际响应 model/provider
尚未预检而不勾选。B/C/D 是待实现的实验模式，尚无生产开关；未来付费批次
仍需冻结实际 adapter、请求和现价费用。holdout 范围及字体/遮挡限制见报告。

### M1 — 修复确定的提示、输入与评分问题

- [x] TDD 分离主代理调度规则与共享安全规则；最终 HTTP 不再要求桌面代理
  委托自己。按可用工具注入说明，检查 ask_user 等引导是否也存在能力不匹配。
- [x] 明确文本插入、剪贴板粘贴和按键语义。优先在现有输入工具增加最小明确
  模式或准确描述，再决定是否拆工具；旧调用兼容，不能丢失原 IME 修复。
- [x] 评分分开：历史 strict 表达式口径、当轮业务任务完成、鼠标定位诊断。
  鼠标诊断必须使用鼠标；粘贴可接受的业务轨道也要核对当轮输入与结果，
  不能只读取一个 56。保留旧失败，不追改旧成功率。
- [x] 记录最终截图 hash/时序及实际回流。为受控 Calculator 建立独立本地
  像素/可见结果核验；不能仅检查“存在截图”，也不能让同一动作模型自评分。
  无法可靠自动判定时报告 unknown 并保留人工核验，禁止冒充像素评分通过。

验收：冲突复现用例先失败再通过；Calculator、TextEdit 的字母数字、标点、
中文、Enter 与粘贴分别实测。提示修复先单独 A/B，再作为后续共同基线。

### M2 — 截图引用与宿主坐标还原

- [x] 引入最小 Observation/变换记录；截图到 HTTP 的实际图像与该记录一致。
  全图、窗口区域、crop/放大共享明确契约，取整规则统一并测试。
- [x] 增加显式新坐标接口，旧 normalized 接口通过 legacy adapter 保留。
  新接口没有有效 frame、引用错会话/窗口、越界或几何失效时拒绝输入并重观察；
  不使用截图前 1920×1080 默认值作为新接口的隐式依据。
- [x] 点、框中心、drag 起终点及带坐标的 scroll/mouse_move 一致映射；无坐标
  的动作不引入虚构参考系。batch 的各目标绑定同一可用观察，变化后不沿用。
- [x] 将 crop→全屏→Quartz 的计算移到代码；定位器输出所见图片内位置即可。
  legacy 与新接口作为独立因素对照，不和模型替换一起归因。

验收：真实图像/SDK/工具链回归；边缘、非整除尺寸、1x/1.5x/2x、2x/3x crop、
窗口原点、负的外部屏幕坐标或非主屏明确拒绝、旧帧和双会话隔离均有用例。
实际主屏 oracle 再验证落点 ≤1 point/轴；不声明已支持多显示器。

### M3 — 具体模型的适配器与独立定位基线

首批 [M3 端点预检](../../../backend/benchmarks/computer_use/reports/20260920-m3-preflight/README.md)
首批五模型 × 两协议十次调用，加本批
[strict 配对预检](../../../backend/benchmarks/computer_use/reports/20260920-m3-strict/README.md)
六次，共 16/16 次；预检额度已用完，不重置预检额度。独立调参筛选已完成
[首批四十次点/框对照](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-protocol/README.md)，
使用 79357 tokens；后续 [thinking 批](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking/README.md)
第七次因 DeepSeek HTTP 402 余额不足停止；余额恢复后的
[26 次续跑](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking-resume/README.md)
已补齐 32 设置。筛选累计 73/144 次、150614 已知 tokens；历史未知用量保留，
按完整请求估算预留 26000 tokens，剩余 71 次 / 823386 tokens（扣预留后）。
具体可用型号、请求/响应型号、参数、用量与失败已记录；共用生产 adapter
的离线实现见下；strict 小样本结果已记录，原生框实测、配置冻结与模型效果验收尚未完成。

- [ ] 使用当前已配置的 Qwen/DeepSeek/OpenRouter profile，保留现有 Qwen
  基线和 GPT-5.5 对照，补 Qwen3.8 与 DeepSeek V4.1 候选；具体 ID/可用性
  在执行时核实，不凭系列名假定视觉、工具、原生 computer 或 schema 能力。
- [ ] 为每个候选记录官方契约和实际预检：图片参数、坐标参照系、原生点/框、
  strict 支持、thinking/temperature/预算、失败响应。OpenRouter 自定义工具
  不等于 Responses computer；没有支持证据不发送后者的专用字段。
- [x] 从已有 probe 提取最小可复用契约，接到生产调用路径，避免复制一套
  与生产不同的探针适配逻辑。模型外部协议可不同，内部图片点/框类型统一。
- [ ] 在调参集分别改变 schema、图片/detail、提示和思考设置，选定配置后
  冻结 adapter 再跑 holdout。来源不明的服务端缩图不进入补偿公式。
- [ ] DeepSeek 关闭思考、合理预算为显式候选；保留截断和无响应失败，不从
  命中率分母移除。先前关闭思考省 token 不等于定位问题已解决。

验收：实际 SDK HTTP 与原始响应回放验证模型/参数/图片/解析/映射；按模型
报告合法率、命中率、误差和截断。适配无收益也是有效结果，不自动加入复杂
变体。UI-TARS 等专用模型需先确认可用部署/授权，否则明确记为未测试。

### M4 — 分离规划与定位，保持可对照

- [ ] 在现有工具链增加最小 locate 能力，输入目标描述、frame 与窗口约束。
  定位服务独立配置 profile，但默认可用同一个模型以隔离“拆分”的影响。
- [ ] 一体与分离模式共用 M2/M3 转换和驱动；同模型分离先测，再替换定位模型。
  规划器接收定位失败/歧义，可以补描述、重截图或结束，不能伪造成功坐标。
- [ ] 共享计账/取消/超时，定位失败零点击；任务停止后无新请求或动作。
  截图引用过期、定位途中 UI 变化时回到观察。限制重定位为每步最多两次，
  更换定位后端为最多一次，均计入总任务上限，防止无限重试。
- [ ] 保留现有反馈；页面/菜单变化后观察再定位，固定按钮可短 batch。
  执行错误与界面无预期效果分别报告，失败后不盲目重放同一批动作。

验收：真实 Runner/ToolManager/LLM seam、实际序列化和取消/预算回归通过；
定位器收到指定当前图且无完整任务历史，主代理拿到新反馈；没有第二次计账。

### M5 — 四组核心因果对照

全部组在同一 M1 基线上运行、采用相同任务/评分；先记录历史原始基线，
再执行以下比较，不能与旧 revision 分数直接相减。

- **A**：当前模型、一体规划定位、legacy 接口。
- **B**：同模型、一体规划定位、适配接口。M2 宿主还原和 M3 协议变化先各自
  单因素测试，再测试组合，避免把两个改动的总收益归给某一个。
- **C**：同模型、分离规划定位、沿用 B 的适配。B→C 测任务拆分的收益/代价。
- **D**：固定 C 的规划模型，仅替换定位模型及其匹配的 adapter。
  C→D 测“定位模型与适配组合”，不是无混杂的纯权重比较。

- [ ] 静态定位与真实任务分别评测：给定正确目标描述的定位分数不包含规划
  错误；完整闭环使用规划器实际目标描述，区分选错目标与定位错目标位置。
- [ ] 首轮请求上限：预检 16；适配筛选 144；冻结后最多 3 个定位候选 ×
  64 个新布局 × 2 次 = 384 次 holdout。合计最多 544 次静态请求，不含后续
  闭环；超出作为新批次列明理由/预算，不悄悄扩大搜索。
- [ ] 新布局覆盖多个标签、密集/稀疏、小目标、字体/缩放、窗口位置、横竖图、
  遮挡、同名候选和目标不存在。正确拒绝单列，失败/截断/无输出全保留。
- [ ] 统计按独立布局分组，重复次数不充当独立样本；记录部署差异。定位模型
  看不到评分 mask/目标中心；语义描述若由真值提供，仅用于静态定位赛道。

验收：产出配对结果与失败分类，能够区分适配、拆分、定位模型组合的效果。
不以最优个例或筛选集成绩选型；证据不明确时报告不确定并保留基线。

### M6 — 真实闭环、长历史与清理验收

- [ ] 先在本地九点及 Calculator oracle 重验 M2 驱动。异常时同时保存事件
  down/up、光标回读、时间戳、目标边界和 frame；复现失败先排执行链。
  未再复现 I09 只能说明这批通过，不得把历史异常解释为已解决。
- [ ] A/B/C/D 各跑 calc-open 三轮；每轮重置，新图、独立真值/validator。
  每轮总时限 120 秒、顶层工具调用上限 15；额外定位调用最多 15 次并计入
  共享 300000 token 上限。按请求报告规划/定位用量，不能只数顶层工具。
- [ ] 首轮留下基线和至多一个候选，再对现有 14 任务中适用于 macOS 的任务
  各跑三轮；不适用/不可验证任务单列，smoke 不进入严格分母。GUI 轨道继续
  禁止 shell/file 绕路。真实桌面操作串行，记录位置/环境变化。
- [ ] 覆盖计算器、文本编辑、浏览器/文件界面等；语义轨道与纯视觉分开。
  长任务实际跨越配置的历史压缩阈值；核对压缩前后当前图引用、目标和失败
  恢复，不以附加一张历史图代替 compaction 验收。
  长历史专项单独列 manifest：每组先一轮，最多 600 秒/60 次顶层工具/
  60 次定位调用/300000 token；报告压缩是否实际触发，未触发不算验收通过。
- [ ] 检查自研完整派发路径中的预算、停止、通知；在模型等待、定位等待、
  batch/拖拽/按键保持中停止，观察至少 10 秒无新动作、按键释放、资源可再次
  使用。cleanup=unknown 必须独立核实，不得作为已确认清理通过继续连跑。
- [ ] 将任务业务失败、识别/定位错、变换错、投递无效、输入语义、陈旧观察、
  截断/超时和清理失败分开归档；不允许模型自报成功替代应用结果。

验收：真实鼠标路径与输入路径分别有证据；跨应用/长历史/停止通过才能宣称
候选具备相应能力。两者成功率相近时以延迟、成本、复杂度和失败严重度决定。
N2 既有结果按 R 复用；M6 验证本轮改动后的自研效果，不扩为 SDK 迁移验收。

### M7 — AX 与视觉解析的独立分支

- [ ] 在固定规划器条件下依次比较纯截图、AX 候选 + Quartz 点击、AX 候选 +
  AXPress；候选由本次真实观察发现，不写死 Calculator 按钮，不泄漏评分真值。
- [ ] 验证同名/缺失 AX、自绘控件、旧引用、窗口不匹配和回退；明确每条分支
  的覆盖率。AX 自动获得边界不等于模型能选对目标。
- [ ] 若 AX 覆盖不足或纯视觉仍需提升，预检专用 grounding 模型、OCR/控件
  检测 + 编号方案；有新部署/凭据前置时明确记录。先测解析质量，再与规划器
  组合，不一次引入多个检测器或通用编排框架。
- [ ] 语义辅助成绩单列，不能替代纯视觉 A/B/C/D。若本阶段不采用某分支，
  记录实测或条件判断及原因；未做实验写“未测试”，不能写“无收益”。

验收：明确采用、否定或条件性暂缓；未执行的触发项移回 backlog，不假装实现。
本分支不阻塞 M3/M4 主线，主线结论与混合方案结论分别交付。

### R — 复用 N2 benchmark，按需补效果对照

- [x] 读取 §2.1 三份现有 benchmark；旧 N2 33/42、SDK strict 4/36 和自研
  7/42 分别保留原评分，作为现状参考，不能声称 N2 没有实测。
- [x] M0 归档实验 manifest 时引用既有报告/任务明细，优先分析成功操作与
  失败 trace，借鉴定位、输入、反馈和 batch 行为。只在本机读取真实截图，
  不因复用报告而扩大外发授权。
- [ ] 新自研方案以 A/B/C/D 同尺比较为主。只有需要直接证明相对 N2 的改善，
  或本轮变更影响其共享依赖时，才补相关 N2 任务/回归；优先复用同口径结果，
  不默认完整三路重跑，不重新要求安装、权限、SDK 接入或迁移采用验收。

验收：新方案的效果结论有可比证据，历史 N2 的参考价值与版本差异均说明。
N2 专项重验不是 M3/M4、M6 或本计划关档的前置。

### M8 — 采用决定、回退与关档

- [ ] 固定报告包含：版本/manifest、测试与请求总数、失败分母、按布局/任务
  的配对结果、未知项、成本/延迟及所有失败原始记录。
- [ ] 采用前必须通过确定性转换/协议/取消/预算/清理测试。首轮候选筛选门槛：
  holdout 有目标样本命中 ≥95%、中心误差 p95 ≤15 px、无 >50 px 大偏移；
  无目标样本不得误报可执行点。小目标仍按实际可点击 mask 判定，不能因中心
  误差小于 15 px 就算命中。这些是拟定筛选标准，不是生产准确率保证。
- [ ] 真实严格任务总通过数不低于配对基线，无新增清理失败或停止后动作；
  每个退化任务单独审查。报告按布局/任务配对的区间，证据不足不宣称更优；
  用量/延迟与质量一起展示，不仅用合法 JSON 比例作采用依据。此门槛用于
  模型/模式切换，不阻止已确认正确性修复的独立提交。
- [ ] 全部候选劣于或不优于基线也可完成调查，但结论必须是保留基线及未解
  问题，不能宣称点击根因已解决。只有通过验收并明确决定后才切默认模式。
- [ ] 按逻辑子任务提交；保留旧模式一键回退，更新 design/benchmark/Tests
  文档。研究结论与生产已实现行为分开写。
- [ ] 逐条对照 I01–I11；已实现/已验证/未知/移交分别标记。未完成项不得打勾；
  同时核对 §2.3 与 R 的既有证据复用。条件性暂缓必须移交 backlog；
  旧归档计划不再产生额外关档条件。必做项完成或明确处置后才能移至 done。

## 5. Tests

执行时遵循 TDD：先补能复现问题的失败断言，再最小实现，最后跨层验证。
优先扩展以下现有文件；只有独立生产模块确有需要才新增对应测试文件。

- `test_computer_use_macos.py` / `test_computer_use_common.py`：真实像素经
  裁剪/缩放、frame 和逆变换到 OS 边界，尺寸不符/旧帧/非法值零输入。
- `test_grounding_probe.py` / `test_llm_profile.py`：生产共用 adapter、
  实际 SDK HTTP 图片/模型/参数、原始点/框解析、拒绝歧义/截断；不是只断言
  mock 返回值。新版 schema 与旧协议分别回归。
- `test_subagent.py` 及现有 runner/LLM 测试：最终提示无委托冲突、能力引导
  与工具匹配；实际 locate→LLM→解析→ToolManager→执行/反馈串联。
- `test_computer_batch.py` / `test_computer_approval.py`：首错即停、截图回流、
  定位取消/预算后零动作、陈旧引用、输入释放和共享预算一次计账。
- `test_calc_validator.py` / `test_bench_task.py` / `test_bench_runner.py` /
  `test_bench_report.py`：当轮隔离、像素未知不报成功、粘贴/鼠标分轨、失败与
  缺失结果保留、cleanup 未确认停批、真实输出模型/provider/hash 可追踪。
- 在现有 `test/features/chat.feature` 扩展必要的派发/停止场景，不新建同域
  feature；用 fake 模型/OS 验证本轮新增的定位编排，真实桌面验收独立进行。
  不将独立 SDK 完整 WS 专项扩为本轮必做项。影响 SDK 时回归其实际固定
  SDK + fake transport/completions，并保留旧 `agent-n2/tests` 回归。
- 实际模型调用不进入 pytest；pytest 全绿不证明模型准确或真机事件可靠。
  校准、固定图定位、完整闭环三个层次分别报告覆盖与限制。

## 6. 执行前置、数据与预算

- 先读 M0 manifest 和当时工作树；沿用 backend 自己的环境和当前实际配置。
  使用新输出目录，真实图保存在本机，仓库只收脱敏轨迹/统计；不得提交凭据。
- 已允许向现有端点发送合成校准图。上次允许清理后的真实截图是 GPT-5.5
  那次闭环的授权，不能外推到后续新提供方/新内容；需要时在真实阶段前说明
  具体图片范围、端点与轮数再确认。离线实现和合成范围内工作不反复询问。
- 运行前检查当前执行进程屏幕录制/辅助功能权限；历史 Paseo 授权成功不保证
  新进程仍可用。仅当前不可用时处理，不能提前假定用户需要重授。
- 按阶段先小样本预检，网络调用无无限重试；请求失败计入上限。除阶段显式
  对照外固定推理设置；不同模型内部预算不等价，报告实际 usage 和推理截断。
- 每批生成预计请求数和基于当时端点价格的费用估算。实际用量缺失记 unknown，
  不能按零计账；达到 token/时间/请求上限停止并保存证据，扩样另记批次。
- M6 首轮最多 12 个 calc trial；扩展阶段最多两组 × 14 任务 × 3 轮，
  每轮沿用上述上限。不要在模型请求和桌面动作并发时比较时序/延迟。
- R 默认复用本地报告，不增加 N2 请求；确需补同尺对照时在 manifest 单列
  选定任务、差异因素和必要试次，沿用 M6 上限，不自动增加一轮三路全套。

## 7. 本次计划编制的核对结果

- [x] 核对历史专项、两份已归档实施计划、真实 benchmark 及 backlog。
- [x] 明确模型适配和规划定位分离为独立主线，补四组对照、Tests 与验收条件。
- [x] 将已立项条目从 backlog 移入本计划，保留多屏/压力等条件触发项。
- [x] 两份旧实施计划保持归档；按用户明确的效果改进目标，引用 N2 真实
  benchmark，撤回重复的 S1–S4 接入验收与三路全量前置。相关非目标专项
  条件性登记 backlog，不误标已完成。
- [x] 本次仅文档变更：backend 4484 passed / 1 skipped；E2E 14 场景 / 55 步
  通过；web lint/TypeScript、backend/CLI ruff、后端日志、协议和文档检查
  通过（37 个文档）。Python 定向 pyright 不适用。未执行 M0–M8 的新实验。

## 8. 执行记录（2026-09-19）

- M0 首批离线快照见 [manifest 与请求](../../../backend/benchmarks/computer_use/reports/20260919-adaptation-m0/README.md)。
  冻结 revision、主屏几何、权限、应用版本、配置模型/端点、实际 SDK 序列化
  的最终 system、12 个工具定义和参数；采用门槛、分母和失败分类已冻结。
  本批真实模型请求为 0，费用为 0；实际响应 model/provider 尚未预检。
  未生成完整新 holdout 或失败回放集，所以 M0 前三项仍保持未完成。
- M1/I01：先在真实 Runner→LLMAgent→SDK HTTP 复现自我委托冲突，再把主代理
  调度说明移至 orchestration.md，共享安全与环境说明保留在 base.md。
  ask_user 引导只在注册工具经过 allowlist、命名 toolset 和 disallowed 过滤后
  仍可用时注入；缺少能力则要求结束并说明缺失信息。
- 原始与修正请求逐字段核对：只改变最终 system，工具定义、用户任务、模型和
  请求参数完全相同。离线正确性修复不等于模型效果 A/B；后者尚未执行。
  主代理仍保留委托规则，旧 N2/SDK 回归纳入完整测试。
- 后续 M1 输入/评分代码：macOS type_text 增加兼容默认 auto 与显式 paste，
  非法模式零输入；工具说明区分文本、粘贴、按键和应用效果。评分新增
  calc-evidence-v1，严格表达式、当轮业务、鼠标输入与 unknown 像素证据分开；
  原 strict 总分保持。实际 SDK 图片 hash 与截图捕获时间可关联，并拒绝
  沿用旧轮输入和未完成动作的成功结果。
- 实机输入预检在 TextEdit 前台校验时停止，未派发测试输入、未调用模型或
  外发图片。TextEdit AppleEvent 后续超时（-1712），辅助 UI 通道权限未就绪。
  本地诊断在 `/tmp/tank-m1-input-a4878883/`；不把本次尝试当作实机通过。
  按临时文档绝对路径关闭也超时，cleanup=unknown；未强制退出 TextEdit，
  未继续连跑桌面试次。诊断脚本 finally 执行剪贴板恢复并请求恢复原前台，
  UI 状态未独立核实。
  像素自动评分仍为 unknown，提示单因素 A/B 及 Calculator/TextEdit 真机矩阵
  待环境恢复后执行；本批不重试权限申请，不扩大截图外发范围。
- M1 的实机验收和截图像素核验、M2–M8 的实现/新实验尚未完成；未切换
  默认模型或坐标接口。
- 首批完整验证：backend **4490 passed / 1 skipped**（含旧 N2 与 SDK）；
  E2E **14 场景 / 55 步通过**；web lint、`tsc -b --noEmit`、backend/CLI
  ruff、四个修改 Python 文件的 pyright、`tank:1.1` 后端日志、协议及文档
  检查通过。后端测试需在当前进程设置
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` 以定位已安装的 Opus；
  `UV_CACHE_DIR=/tmp/tank-uv-cache` 仅用于执行环境，不更改生产配置。

- M1 后续批完整验证：backend **4502 passed / 1 skipped**；E2E **14 场景 /
  55 步通过**；web lint/TypeScript、backend/CLI ruff、九个修改 Python 文件
  的 pyright、后端实际 pane 日志、文档及协议检查通过。使用与首批相同的
  临时 uv 缓存及 Opus 动态库路径。真实输入矩阵仍未通过，不能以此关档 M1。
- 本批前两次 Git commit 曾返回 `1Password: agent returned an error`。
  按用户要求重试后，输入契约提交为 `80bb5ea`，分轨证据提交为 `4a3ea91`；
  保留原有 SSH 签名配置，文档另作一个逻辑提交。
- TextEdit 超时复查：首次实机停止点是 activate 后等待 0.5 秒的前台断言，
  当时未记录实际前台名称；后续文档 AppleEvent 查询才出现 -1712。
  只读复查时前台为 Paseo，版本查询 0.08 秒成功，文档数量查询一次超过
  6 秒，下一次成功；窗口查询也成功。两次线程采样均显示主线程处于正常
  事件等待，未采到死锁或模态调用栈。现有证据只能确定文档查询间歇性
  无响应，不能确定底层原因，也不能将辅助 UI 通道的权限等待等同于
  TextEdit AppleEvent 超时原因。未执行新的输入试次或关闭用户文档；
  实机矩阵与原临时文档 cleanup 的验收状态仍未确认。

### 2026-09-20 — M1 剩余验收

- [验收报告与原始记录](../../../backend/benchmarks/computer_use/reports/20260920-m1-acceptance/README.md)：
  上次 TextEdit 临时文档仍打开且未修改，现已按确切路径关闭并独立确认不存在。
  上次剪贴板快照只在内存，无法追溯比对；不能把历史 unknown 追改为已恢复。
- 本批前台预检失败时零输入并清理。原生激活与 AppKit 状态刷新后进入矩阵。
  复现 ASCII 字母被 IME 改写、`shift+8` 实际输入 `8`；两项均先写失败测试，
  再最小修复。`auto` 在非 ASCII 输入源下粘贴，英文输入源保留旧路径；
  带 Shift 的映射键使用物理 key code。代码与测试提交 `dac426f`。
- 最终 TextEdit 六项通过；Calculator 八项记录数字、字母/中文拒绝、标点、
  粘贴、独立 Enter，逐键得到 `7×8 = 56`。副屏批截图不计像素证据；最终批
  把受控窗口移至主屏，结束后确认窗口位置、剪贴板、前台恢复及临时文档关闭。
- 主屏八张 Calculator 显示裁剪图由本助手独立视觉复核，结果符合当轮输入；
  本地 Vision OCR 对孤立数字有误识别，保留原始结果并将歧义视为 unknown，
  不将通用 benchmark 的 `pixels` 改成通过，也不冒充人工签字验收。
  14 张真实捕获图经生产 follow-up builder 和实际 SDK 的本地假 HTTP 回放，
  hash 全部相同；这不代表远端收到真实截图或完成真实模型闭环。
- 提示单因素 A/B 使用原 M0 两份请求、三个合成布局各两次，共 12 次，
  只在配对内改变 system；两组共同启用 usage 回报。实际用量 73940 tokens，
  旧/新均 0/6 命中，新提示出现 5 次非法 bbox，全部计入失败。没有观察到
  定位收益；保留提示正确性修复，默认模型和坐标接口不变，后续 M3/M5/M6
  继续适配及完整任务对照。本批没有向 Qwen 端点发送真实截图。
- 全量 backend **4508 passed / 1 skipped**；E2E **14 场景 / 55 步通过**；
  web lint/TypeScript、backend/CLI ruff、两个修改 Python 文件 pyright、
  后端日志、文档及协议检查通过。沙箱不允许测试服务器绑定端口和 TTS DNS，
  在具备权限的环境重跑完整测试通过，不将环境失败忽略或冒充通过。
- M1 在上述明确范围内完成；M0 失败回放集/holdout 等准备及 M2–M8 仍未完成。
  M1 的首步 A/B 与本地序列化证据不替代 M6 的真实模型任务、停止与清理验收。

### 2026-09-20 — M0 离线准备补齐

- 新目录 [M0 准备报告](../../../backend/benchmarks/computer_use/reports/20260920-adaptation-m0-preparation/README.md)
  保存本批 manifest、当前 profile/主屏/应用版本、最终 system 与 12 个工具
  的实际 SDK 假 HTTP 请求，附源码/评分 revision 与 hash；未执行桌面动作。
- 三份历史 benchmark 的 126 个 trial 全量索引（80 个原失败、46 个原成功），
  保留原评分、smoke/timeout/cleanup；归集 38 个静态失败，26 个矩阵原始
  响应离线解码/评分与原记录一致，另 12 个 M1 legacy 样本不冒充矩阵回放。
  R 补充 N2 成败操作、SDK 历史签名错误与 Part A 协议/驱动失败的区分。
- 新生成 64 个布局（48 有目标、8 不存在、8 同名歧义），图片与真值/mask
  分离；历史图片 hash 无重合，尚未调用模型。固定字体大小、密度、缩放、
  位置、横竖图与部分遮挡；单字体家族及有限遮挡的限制明确保留给 M5。
- 本批模型请求/token/费用均为 0；544 次静态请求规划上限与各阶段预算已
  列明，未来付费批次现价估算仍为 unknown。M0 实际 model/provider 预检
  保留未完成，M2–M8 未实施，不切默认模型，也不扩大真实图外发授权。
- 生成器先红后绿；完整测试发现调度测试手动触发撞上每分钟 cron 的竞态，
  最小修复仅关闭该用例的定时触发，保留实际手动触发链。最终全量验证见
  准备报告 verification.json；历史沙箱失败与首次竞态失败均保留为失败尝试。

### 2026-09-20 — M2 截图引用与宿主还原

- [实现、实机记录及验证报告](../../../backend/benchmarks/computer_use/reports/20260920-m2-observation/README.md)：
  显式 `coordinate_space="image"` 使用会话/frame、主屏/窗口几何、实际图片
  尺寸、裁剪边界和 hash；新坐标统一由宿主还原。默认 legacy 及原模型保持。
- 点击、框中心、拖拽、移动、定位滚动共享转换；batch 绑定当前观察，逐步
  验证、首错即停。非法值、旧/跨会话/错窗口引用、几何及可见区域像素变化
  零输入。无坐标动作保留原输入语义；不宣称已支持多显示器。
- 真实 SDK 假 HTTP 验证图片 hash、工具 schema、碎片参数与 Quartz 落点；
  覆盖 1x/1.5x/2x、2x/3x crop、非整尺寸、窗口原点、边界及拒绝路径。
  取消期间的捕获错误曾覆盖取消信号，先失败后修复；不替代 M6 物理停止验收。
- 首次全屏校准因画面不一致在点击前拒绝，原因未细分，保留失败记录。
  裁剪帧原先比较全屏像素，追加回归后改为只比较实际观察区域，仍检查几何。
  随后窗口九点 **9/9 命中，每轴误差 0 point**，down/up 完整；窗口关闭和
  光标恢复已独立确认。前台恢复仅请求，未独立记录；不追改为完整 cleanup 验收。
- 无新增 grounding 模型请求或真实截图外发。像素复核会增加每步截图成本，
  动画/闪烁仍可拒绝执行；无法排除检查后瞬间变化。I09 原因仍未知，M3–M8
  及 Calculator/跨应用/长历史验收待后续阶段。

- 最终完整 backend **4561 passed / 1 skipped**；E2E **14 场景 / 55 步通过**；
  web lint/TypeScript、backend/CLI ruff、8 个 Python 文件 pyright、后端实际
  pane 日志、文档与协议检查通过。首次全量发现数组 schema 缺少 `items`，
  修复后定向 247 项及完整套件通过；中间一次测试整理缩进错误也已修复并重跑。
  默认模型未切换；下一步 M3 实际端点预检和生产共用模型适配。

### 2026-09-20 — M3 首批端点预检

- 五个模型均返回 HTTP 200：现有 Qwen3.7、Qwen3.8 Flash/Max、DeepSeek
  Flash（官方版本 V4.1）与 OpenRouter GPT-5.5。请求和响应型号分别归档；
  仅 OpenRouter 返回 provider=OpenAI，其余响应未提供 provider 字段。
- 同一开发合成图比较 normalized point 与 pixel point，关闭思考、每次
  8000 输出 token、零重试，共十次 / 16730 tokens。全部保存实际 SDK 请求、
  图片 hash、原始响应和离线回放。无真实截图外发、桌面动作或 holdout 调用。
- Qwen3.8 三次数组坐标被拒绝；七次 schema 合法但仅四次命中。
  pixel 协议下 Qwen3.7/Max 约 287 px 偏移，DeepSeek 51 px；GPT 两次命中。
  单布局不能作模型排名或采用结论；不猜测单位、不修补数组，不切默认模型。
- 费用按实际用量及保守标价估算 $0.026680；OpenRouter 报价 $0.01902，
  其他提供方实际账单 unknown。请求/费用预算和首次本地目录错误均见报告。
- 完整验证：backend **4561 passed / 1 skipped**；E2E **14 场景 / 55 步**；
  web lint/TypeScript、backend/CLI ruff、运行日志、文档及协议通过。无 Python
  源码改动，定向 pyright 不适用；已有 probe 49 测试与十条离线回放通过。
- 本步完成 M3 初始可用性预检；下一步提取生产/probe 共用协议与严格解析，
  分因素测试 native/strict/detail/thinking，冻结后才运行 holdout。M3 不关档。

### 2026-09-20 — M3 共用协议与生产 LLM 单次调用

- 按已确认的分层实现 `tools/computer_grounding.py`：profile 管模型/端点/参数，
  共用 adapter 管图片、schema、严格点框解析；没有型号专属类和坐标猜测。
  M2 的 Observation/宿主转换保持不变。实现边界见
  [现行设计](../../design/computer-use.md#共用定位适配器m3-实现尚未启用-locate)。
- 通用 `LLM.complete_response()` 保留工具调用、结束原因、型号与 usage；
  原 `complete()` 仍返回文本。adapter 的单次请求先检查实际 PNG/hash/尺寸，
  再使用此接口，关闭两层重试、直接传播取消。完整响应先交调用者计账和留证，
  再做定位解析，不注册动作工具、不自动重试定位。
- 旧 found schema 保留；false 的内部状态保守为 ambiguous。新显式 status
  区分 found/not_found/ambiguous；点框统一成图片内单位，非 found 无坐标。
  实際模型对新 schema/strict 的遵循程度仍未测试，不能视为收益结论。
- TDD 复现并修复 probe 把 length + 完整参数视为合法定位的问题；本批仍保留
  原始参数、finish_reason 和 usage。图片错配零 HTTP、拒绝/截断无坐标、
  三提供方 SDK 请求和十份历史响应回放均有测试，旧失败不改分。
- 这是 M3 共享协议及可调用生产接口子任务。Runner 的 locate 工具、任务/frame
  绑定、共享预算/截止时间和动作衔接仍属 M4，尚未上线；M3 模型筛选、原生
  协议/strict/detail/thinking 对照及冻结 holdout 配置仍待完成。
- 本批模型请求、桌面动作、截图外发均为 0；预检上限仍余 6 次，默认模式不变。
  不把离线实现等同于 M3 全阶段验收。
- 验证：backend **4595 passed / 1 skipped**（含旧 N2/SDK），E2E **14 场景 /
  55 步**；web lint/TypeScript、backend/CLI ruff、全部五个修改 Python 文件
  pyright、后端实际 pane 日志、文档及协议检查通过。定向集成 **198 项**通过，
  进一步收紧浮点回放误差到绝对 1e-10 后十份记录再次通过。完整测试使用
  既有临时 uv cache、Opus 动态库路径及允许本地端口/网络的执行环境。
- 首轮回放断言有约 1e-13 的浮点运算差异，改为只容许舍入误差；命中 mask
  和原始响应保持完全一致。TDD 红灯包括缺失适配器、图片错配仍发 HTTP、
  未区分结果状态、非法配置/尺寸、length 仍合法以及拒绝响应仍返回坐标，
  均在对应最小实现后转绿。本轮没有用类型忽略或坐标修补掩盖错误。

### 2026-09-20 — M3 strict 单因素预检

- [报告、manifest 与原始响应](../../../backend/benchmarks/computer_use/reports/20260920-m3-strict/README.md)：
  通过生产 GroundingAdapter → LLM → SDK 调用 Qwen3.8 Flash/Max 与 DeepSeek，
  各 control/strict 一对；实际 HTTP 仅 strict 字段不同，DeepSeek 两次都固定
  beta 端点。图片、提示、温度、关闭思考、8000 输出预算均相同，零重试。
- 六次均 HTTP 200 且 usage 已知，共 9668 tokens；累计预检 16/16 次、26398
  tokens。本批保守标价用量估算 $0.007535496，实际账单 unknown。仅合成图，
  无桌面动作/真实截图/holdout 调用。六份响应离线回放结果一致。
- Qwen3.8 Flash 开关 strict 都返回数组，被拒绝；Max 两次均命中，但保留上批
  数组失败。DeepSeek control 偏移 73.002 px、strict 命中且误差 4.223 px；
  一张图、无重复且固定顺序，不能将差异归因为 strict 收益或作采用结论。
- 继续保留默认模型与本地严格解析。预检额度归零；下一步进入 M3 调参筛选，
  沿用已规划的独立 144 请求/1000000 token 上限，先冻结新 manifest 和费用，
  分因素比较 schema、image/detail、thinking/native 协议；配置未定不跑 holdout。
  M3/M0 的其余验收仍未关档，不把本批计为完整模型适配成功。

- 验证：backend **4595 passed / 1 skipped**，E2E **14 场景 / 55 步**；
  web lint/TypeScript、backend/CLI ruff、实际后端日志、文档与协议检查通过。
  定位测试 **83 项**、六份响应离线回放及三对请求单因素检查通过。
  本轮无 Python 源码/测试改动，changed-file pyright 为 N/A。

### 2026-09-20 — M3 多布局点/框调参筛选

- [报告、冻结请求与回放](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-protocol/README.md)：
  五模型 × 四开发布局 × point/bbox 共 40 次，生产共享调用路径；20 对请求仅
  改坐标 schema 与配套中心点/紧框说明。固定图片、关闭思考、detail=auto、
  strict 缺省和 8000 输出预算；模型顺序轮换，每模型两对点先、两对框先。
- 点/框命中：Qwen3.7 为 3/4、2/4；Qwen3.8 Flash 为 0/4、2/4；Max 为
  3/4、4/4；DeepSeek 为 3/4、1/4；GPT-5.5 均 4/4。合法 33/40、命中
  26/40；六次数组和一次非法 JSON 保留为失败，不修补坐标。Qwen3.7 有
  合法但超过 600 px 的偏移，不能用格式合法率替代命中率。
- 全部 HTTP 200、usage 已知，无截断/超时；79357 tokens。预估 $2.912432，
  实际用量标价估算 $0.127608331；OpenRouter 回报 $0.09118，其余实际费用
  unknown。筛选剩余 104/144 次、920643/1000000 tokens；预检仍为 16/16。
- 四布局、每设置单次，无统计采用结论；横竖与目标未正交，不归因具体尺寸。
  此处为自定义函数 bbox，不冒充原生协议验收。holdout hash 无重合且零调用；
  没有真实截图外发/桌面动作。40 份响应离线重算与原始记录完全一致。
- 默认模型不变；Max bbox/GPT 保留为开发候选，不冻结 holdout。下一步分开
  对照 thinking 或图像设置，并累计筛选预算；status/缺失/歧义与 native 协议
  仍待验证，M3 及后续阶段不关档。
- 验证：backend **4595 passed / 1 skipped**，E2E **14 场景 / 55 步**；
  web lint/TypeScript、backend/CLI ruff、后端实际 pane 日志、文档及协议检查
  通过。定向定位 **83 项**、40 份 SDK 假请求与真实响应回放通过；本轮无
  Python 源码/测试改动，changed-file pyright 为 N/A。回放脚本首次使用了
  错误距离字段名，已改为既有 distance 字段后重跑；未改变原始数据或评分。

### 2026-09-20 — M3 thinking 配对批中止

- [冻结计划、响应与回放](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking/README.md)：
  计划四模型 × 四开发布局 × thinking off/on 共 32 次，固定 point、图片、
  detail 与 16000 输出上限，16 对实际 SDK 假请求仅思考开关不同。重新请求
  off 控制，不把上一批 8000 预算的结果当作配对控制。
- 第七次 DeepSeek off 返回 **HTTP 402 / Insufficient Balance**，无 usage。
  按冻结规则整批停止、零重试；后续 25 次未发送。仅完成 seed 201 的三对
  Qwen，实际顺序均 off 在先；不能宣称四布局或平衡顺序已完成。
- Qwen3.7 off 命中、on 偏 65.077 px；Qwen3.8 Flash off 数组非法、on 命中；
  Max off 命中、on 偏 189.882 px。六次 HTTP 200 无截断，三个 on 均有
  reasoning 内容与 token 计数。总七次尝试中合法 5、命中 3，余额错误单列，
  未发送项不计成功/失败。DeepSeek 没有新的模型能力结果。
- 本批 11655 已知 tokens 加一次未知；筛选累计 **47/144 次、91012 已知 tokens
  加一次未知**，余 97 个请求槽。908988 仅为尚未扣未知用量的算术余量，
  不当作可用余额。预估 $1.017584，六份已知响应标价估算 $0.007764192，
  总实际账单 unknown。预检保持 16/16 次，不重置任何额度。
- 继续 DeepSeek 前需恢复账户余额；更多付费调用前须核对缺失 usage 或明确
  记录预算内的保守计账方案。另建批次、保留本次失败，重复控制也累计计账。
  默认模型不变；单布局结果不作采用结论，holdout/真实截图/桌面动作均为 0。
- 软件验证：backend **4595 passed / 1 skipped**，E2E **14 场景 / 55 步**；
  web lint/TypeScript、backend/CLI ruff、文档、协议检查通过；定位测试 83 项、
  六份完成响应及一份 402 回放通过。无 Python 源码改动，pyright 为 N/A。
  **真实后端日志检查未通过**：tank:1.1 的 Brain 也记录 DeepSeek 402 余额错误；
  需恢复账户后重新验收，不能以 E2E 通过将本批或全清单标为完成。

### 2026-09-20 — M3 thinking 恢复与完整配对

- 用户确认余额恢复后，新建 [续跑报告](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking-resume/README.md)，
  发送原 25 个未发请求加一次明确重试，共 26 次；与原冻结请求逐字段一致，
  未重跑原六份完成响应。旧 402 及其 usage unknown 原样保留；为它预留完整
  10000 输入估算 + 16000 输出 = 26000 tokens，作为预算扣留而非实际消费。
- 26 次均 HTTP 200、usage 已知，32 个配对设置已补齐；完整 33 次尝试均回放
  一致（含旧 402）。完成响应 off/on 命中：Qwen3.7 3/4、0/4；Qwen3.8 Flash
  0/4、4/4；Max 4/4、3/4；DeepSeek 2/4、3/4。含余额失败的 DeepSeek off
  分母为 5、命中 2；全部尝试合法 27/33、命中 19/33，不以恢复后数据覆盖失败。
- Flash off 四次数组被拒绝；DeepSeek off 一次没有函数调用，被保留为格式
  失败。32 份完成响应无截断，16 个 on 均有 reasoning 内容/计数。Flash on
  保留为后续候选，四布局不作采用结论，thinking 不宣称为通用改善。
- 本批 59602 tokens，筛选累计 150614 已知 + 26000 预留，计账 176614；
  余 **71/144 次 / 823386 tokens**（扣预留后）。本批预估 $0.807588，已知
  实际用量标价估算 $0.042842553；实际账单及旧失败实际用量仍 unknown。
  不重置预检额度，也不把预算预留冒充已消费。
- 默认模型不变；下一步隔离图像/detail 与 status 缺失/歧义，选定配置后才跑
  holdout，native 协议仍待验证。无真实截图外发、桌面动作或 holdout 调用。
- 验证：backend **4595 passed / 1 skipped**，E2E **14 场景 / 55 步**；
  web lint/TypeScript、backend/CLI ruff、文档、协议及 **真实后端日志** 均通过，
  上批运行时余额阻塞已解除。定位测试 83 项、26 份 SDK 假请求及完整 33 次
  尝试回放通过；无 Python 源码/测试改动，changed-file pyright 为 N/A。

## 9. 最终 Verification Checklist

每个实现里程碑结束及最终交付前执行；本次计划文档也执行适用检查。

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/`；改动插件亦加入检查。
4. `cd backend && uv run pytest`（完整 workspace）
5. `cd backend && uv run pyright <本轮所有修改的 Python 文件>`；无改动则 N/A，
   禁止用 `type: ignore` 掩盖错误。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | rg -i 'error|traceback|exception'`；
   核对实际后端 pane（当前 `tank:1.1`）。无匹配是通过，不重试；错误须处理。
8. `cd test && pnpm test`（backend/frontend 正在运行）
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`
