> 状态：执行中，2026-09-24。M1 输入/本地图像及首步提示 A/B、M2 frame/宿主还原验收完成；M0 离线基线、失败集与首轮 holdout 已冻结。M3 实现、首轮实验与证据/范围收尾完成，全部候选未通过完整采用门槛，默认不变；544 次静态请求额度已用完，未测原生协议/专用模型已明确暂缓。M4 离线定位编排及软件验收完成；M5 执行中，benchmark 分离测量与 B 组一体适配/单因素开关已实现，四组模型对照尚未运行；M6–M8 待完成，整份计划继续保持 active。

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

**2026-09-22 已完成范围收尾，不等于采用验收通过。**
[证据核对与范围决定](../../../backend/benchmarks/computer_use/reports/20260922-m3-closeout/README.md)
逐批核对 544 份原始响应及用量；本次无新增模型调用或桌面动作。

首批 [M3 端点预检](../../../backend/benchmarks/computer_use/reports/20260920-m3-preflight/README.md)
首批五模型 × 两协议十次调用，加本批
[strict 配对预检](../../../backend/benchmarks/computer_use/reports/20260920-m3-strict/README.md)
六次，共 16/16 次；预检额度已用完，不重置预检额度。独立调参筛选已完成
[首批四十次点/框对照](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-protocol/README.md)，
使用 79357 tokens；后续 [thinking 批](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking/README.md)
第七次因 DeepSeek HTTP 402 余额不足停止；余额恢复后的
[26 次续跑](../../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking-resume/README.md)
已补齐 32 设置。筛选累计 73/144 次、150614 已知 tokens；历史未知用量保留，
按完整请求估算预留 26000 tokens。后续
[图像参数 32 次对照](../../../backend/benchmarks/computer_use/reports/20260921-m3-screening-image/README.md)
已完成；再完成 [显式 status 36 次筛选](../../../backend/benchmarks/computer_use/reports/20260921-m3-screening-status/README.md)，
24 个负例中 5 次仍误报可用坐标。后续 [唯一匹配提示三次开发检查](../../../backend/benchmarks/computer_use/reports/20260922-m3-unique-match/README.md)
完成；筛选累计 **144/144 次、413208 已知 tokens + 26000 预留**，请求额度归零。
剩余 token 空间 560792（扣预留后）不自动增加请求，未改变默认模型。
具体可用型号、请求/响应型号、参数、用量与失败已记录；共用生产 adapter
的离线实现见下；strict 小样本结果已记录；[三候选及 holdout 请求已冻结](../../../backend/benchmarks/computer_use/reports/20260921-m3-holdout-freeze/README.md)，
[384 次付费执行与独立评分已完成](../../../backend/benchmarks/computer_use/reports/20260921-m3-holdout/README.md)：
Max/GPT 正例全中但三组均未满足歧义拒绝门槛，未采用。原生协议仍未验证；
该 holdout 已消耗，不再用于调参后重新宣称独立验收。

- [x] 使用当前已配置的 Qwen/DeepSeek/OpenRouter profile，保留现有 Qwen
  基线和 GPT-5.5 对照，补 Qwen3.8 与 DeepSeek V4.1 候选；具体 ID/可用性
  在执行时核实，不凭系列名假定视觉、工具、原生 computer 或 schema 能力。
- [x] 为每个候选记录官方契约和实际预检：图片参数、自定义点/框坐标参照系、
  strict 实测覆盖、thinking/temperature/预算、失败响应；原生协议明确未测试并
  暂缓到[条件触发工作](../../backlog.md)，不是证明支持或不支持。OpenRouter
  自定义工具不等于 Responses computer；不发送无支持证据的专用字段。
- [x] 从已有 probe 提取最小可复用契约，接到生产调用路径，避免复制一套
  与生产不同的探针适配逻辑。模型外部协议可不同，内部图片点/框类型统一。
- [x] 在调参集分别改变 schema、图片/detail、提示和思考设置，选定配置后
  冻结 adapter 再跑 holdout。来源不明的服务端缩图不进入补偿公式。
- [x] DeepSeek 关闭思考、合理预算为显式候选；保留截断和无响应失败，不从
  命中率分母移除。先前关闭思考省 token 不等于定位问题已解决。

收尾核对：五个实际端点与返回型号均有记录；DeepSeek 请求/响应为
`deepseek-flash`，V4.1 归属来自 2026-09-20 官方资料核对，不代表不可变权重身份。
DeepSeek 16k 预算 off/on 正例完成请求命中 2/4、3/4；计入历史 402，off
全尝试为 2/5。失败不删除，余额恢复只解除当时执行阻塞。
原生 computer/点框与 UI-TARS 等专用部署未测，按明确触发条件暂缓；
新增静态采用复验需要新预算和未使用的独立数据，见[backlog](../../backlog.md)。
M4–M8 的既定集成、对照与真实任务验收仍在本计划内，不随 M3 收尾移出。

验收：实际 SDK HTTP 与原始响应回放验证模型/参数/图片/解析/映射；按模型
报告合法率、命中率、误差和截断。适配无收益也是有效结果，不自动加入复杂
变体。UI-TARS 等专用模型需先确认可用部署/授权，否则明确记为未测试。

### M4 — 分离规划与定位，保持可对照

- [x] 在现有工具链增加最小 locate 能力，输入目标描述、frame 与窗口约束。
  定位服务独立配置 profile，但默认可用同一个模型以隔离“拆分”的影响。
- [x] 一体与分离模式共用 M2/M3 转换和驱动；同模型分离先测，再替换定位模型。
  规划器接收定位失败/歧义，可以补描述、重截图或结束，不能伪造成功坐标。
- [x] 共享计账/取消/超时，定位失败零点击；任务停止后无新请求或动作。
  截图引用过期、定位途中 UI 变化时回到观察。限制重定位为每步最多两次，
  更换定位后端为最多一次，均计入总任务上限，防止无限重试。
- [x] 保留现有反馈；页面/菜单变化后观察再定位，固定按钮可短 batch。
  执行错误与界面无预期效果分别报告，失败后不盲目重放同一批动作。

验收：真实 Runner/ToolManager/LLM seam、实际序列化和取消/预算回归通过；
定位器收到指定当前图且无完整任务历史，主代理拿到新反馈；没有第二次计账。

### M5 — 四组核心因果对照

执行拆分（2026-09-22）：

- [x] 接通既有 benchmark 的 C/D 分离模式，先用 fake HTTP/OS 验证真实
  SubAgentDriver.create → Runner → SDK → 定位 → 动作与反馈；保留独立
  profile、共享计量和截图证据。见本节对应执行记录。
- [x] 实现 B 一体适配及独立 protocol/host_restore 开关；保留原 A，增加
  A-control 共同框架控制组；补一体/分离 batch 实际成功动作计量。
- [x] 冻结七组独立实验 profile、定义和代表性最终 SDK 请求；单独归档原始
  生产 profile。仅 fake HTTP/合成图的离线契约，不是未来完整模型请求序列。
- [x] 保存 built-in benchmark 规划/定位原始 HTTP 响应，关联实际请求尝试；
  保留畸形响应、HTTP 错误和部分流，标注读取/关闭状态及无响应记录。
- [x] 分离定位尝试按阶段/协议拒绝原因归因，关联目标、帧、usage 和原始 HTTP
  响应；模型报告状态与真值正确性分开，不推断未观测到的原因。
- [x] built-in benchmark 每轮规划/定位/总 HTTP 准入限额及双层零重试；
  超额发送前拒绝，失败不退次数，旧 trial 上下文不能复用新额度。
- [x] trial/批次共享 token/费用预留账本的离线算术与生命周期验收；
  完整 usage 结算、未知预留保留及上界违例停批。
- [x] 将按端点/型号上下文上限的预留接入真实 HTTP/SDK 路径，独立核对原始
  usage 后再派发工具；fake HTTP/OS 验收，未验证可用于 live 的更紧输入上界。
- [x] 核查 DashScope 本地/远程 tokenizer 的输入上界适用性；现有公开证据
  不足以降低两种快照的多模态请求预留，记录缺口及后续接入条件。
- [x] 显式顺序的串行批次 API 与 fsync 预留日志；中断证据保留、已有目录
  拒绝重放，预算/未知清理停批。fake HTTP/OS 验收，不支持自动恢复。
- [x] 全批 HTTP 准入次数上限及声明文件的冻结预检；首轮/每轮/driver 构造后
  核对文件，超额或变化阻止后续启动。解析后的运行配置与实验契约对齐已完成。
- [ ] 补齐真实环境、语义失败归因、串行配对调度、可执行的输入上界与批次门禁和
  可验证清理，之后才做模型效果对照。A→A-control 单独量框架变化，不归因给还原。
- [ ] 基于新批次明确样本、顺序、请求/token/时间上限、端点价格和图片范围；
  既有 544 次静态额度不重置。真实图出站按 §6 确认，尚无本轮授权请求。
  已记录 5 个单因素 pilot + 原 12 个核心 trial 的待执行提案及 8 USD 预算，
  尚未授权或落实执行门禁，详见 [离线冻结及批次提案](../../../backend/benchmarks/computer_use/reports/20260922-m5-contract-freeze/README.md)。

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
  [现行设计](../../design/computer-use.md#共用定位适配器m3)。
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

### 2026-09-21 — M3 图像处理参数对照

- [报告、请求与回放](../../../backend/benchmarks/computer_use/reports/20260921-m3-screening-image/README.md)：
  四模型 × 四开发布局 × 两设置，共 32 次；Qwen 比较官方高分辨率开关，
  DeepSeek 比较 detail=auto/low，分别归因。固定配对内图片/提示/协议/思考。
  Qwen3.7/Max 关闭思考，Flash/DeepSeek 开启；未改变生产 profile。
- 图像统一精确 2 倍像素复制，5.18–7.06 MP，超过 Qwen 默认像素上限；
  已知客户端逆变换 point/2 后沿用原始圆角 mask。16 对实际 SDK 假请求
  仅图像参数不同；真实 HTTP body/hash 一致，32 份响应及逆变换回放通过。
  不从服务端用量猜测缩图尺寸，不比较旧原尺寸分数来归因图像参数收益。
- 全部合法、HTTP 200、usage 已知，无截断；命中 24/32。control/treatment：
  Qwen3.7 4/4、3/4；Flash 3/4、3/4；Max 4/4、4/4；DeepSeek 2/4、1/4。
  Qwen image tokens 从约 2500 增至 5042–6932，未见命中数改善；DeepSeek
  low 输入下降但总用量 32149，高于 auto 的 16415，不宣称 low 必然省成本。
- 本批 168914 tokens；阶段累计 **105/144 次、319528 已知 + 26000 预留**，
  余 **39 次 / 654472 tokens**（扣预留后）。本批预估 $1.017584，按实际
  用量标价估算 $0.123534265，实际账单 unknown；历史 402 未改分/未计零。
- 保留默认图像设置，四布局不作通用能力或采用结论；下一步显式 status 与
  目标存在/缺失/歧义对照，仍在剩余额度内。native 协议与 holdout 未验收；
  本批无真实截图外发、桌面动作或 holdout 请求。
- 验证：backend **4595 passed / 1 skipped**，E2E **14 场景 / 55 步**；
  web lint/TypeScript、backend/CLI ruff、真实后端日志、文档、协议通过。
  定位测试 83 项通过；无 Python 源码/测试改动，pyright 为 N/A。首次离线
  启动误用仓库根目录环境，PIL 导入失败且零请求；在 backend 环境重跑通过。

### 2026-09-21 — M3 显式 status：存在、缺失与同名歧义

- [报告与完整请求回放](../../../backend/benchmarks/computer_use/reports/20260921-m3-screening-status/README.md)：
  四模型 × 三新开发布局 × 三条件，36 次。每布局只替换按钮文字，提示和
  几何一致；9 张图视觉核对及修改区域像素校验通过。独立布局只有 3 个，
  不是 36 个独立样本；这是 status 行为筛选，不是与旧 found schema 的 A/B。
- 共用生产 adapter，point/integer、status_field=true、strict=false、detail=auto；
  Qwen3.7/Max thinking off，Flash/DeepSeek on。所有请求 HTTP 200、schema
  合法且 usage 已知，无截断/重试。36 个原始响应及实际请求、评分回放一致。
- 正例命中 / 缺失状态正确 / 歧义状态正确（各分母 3）：Qwen3.7 为 1/3、
  3/3、0/3；Flash 为 2/3、3/3、2/3；Max 为 3/3、2/3、3/3；DeepSeek
  为 2/3、3/3、3/3。总成功 27/36；24 个负例中仍有 **5 次合法 found 坐标**。
  schema 合法不保证视觉判断；不得仅凭 found 或非空坐标推断执行正确。
- 本批 86783 tokens；累计 **141/144 次、406311 已知 + 26000 预留**，余
  **3 次 / 567689 tokens**。请求前估计 $1.144782，按实际用量标价估算
  $0.059274144，实际账单 unknown。历史 402 仍未知，不计零或清空预留。
- 默认配置未改变，无 holdout 调用、真实截图或桌面动作。下一步收敛冻结
  开发候选与未测试能力边界，再跑独立 holdout；native 协议仍未验收。
- 验证：backend **4595 passed / 1 skipped**，E2E **14 场景 / 55 步**；
  web lint/TypeScript、backend/CLI ruff、真实后端日志、文档、协议通过；
  定位测试 83 项。无 Python 源码/测试改动，pyright 为 N/A。协议检查先因
  uv 缓存权限及系统配置沙箱限制失败，设置临时缓存并在授权环境重跑通过。

### 2026-09-21 — M3 holdout 候选与序列化请求冻结

- [冻结报告与 manifest](../../../backend/benchmarks/computer_use/reports/20260921-m3-holdout-freeze/README.md)：
  基线 Qwen3.7 point/off、候选 Max bbox/off、GPT-5.5 point/none；统一旧 found
  整数协议、strict=false、detail=auto、8000 输出上限。保留已有开发实测配置，
  选择依据与未入选模型/未测试能力边界逐项记录；不宣称原生 bbox 已验收。
- 使用已冻结 64 布局 × 三组 × 两次，共 384 次计划；192 份不同 SDK 请求、
  顺序及输入/源码 hash 已归档。384 次实际 SDK MockTransport 验收通过，
  图片字节/尺寸、开发请求参数/schema、重复请求一致。网络和 truth 读取受
  audit hook 阻止；本轮没有读取 holdout 真值、付费调用或模型成绩。
- 旧 found=false 无法分类缺失和歧义，拒绝率按真值分层，不虚构状态正确率。
  保持既有采用门槛，另冻结 mask 像素取整、p95 和按布局配对区间口径；
  评分实现仍须独立夹具验证。静态基线不是生产一体任务 A/B/C/D 的替代。
- 本批零请求/token/费用；筛选仍 141/144 次，不凑满余下 3 次。holdout 沿用
  384 次/3000000 tokens；发出前留 10000 输入估算 + 8000 输出，未知用量
  保留预算且停批，零自动重试。当前价格/费用将在首个付费批前核实并冻结。
- 下一步接通冻结输入驱动和独立 mask 评分，离线测试后执行 holdout；不得
  读取结果后调参。M3 与整体计划保持执行中，默认配置和真实桌面均未改变。
- 最终检查见报告 verification：全套仓库检查及定位回归，无 Python 源码/
  测试变更，changed-file pyright 为 N/A。

### 2026-09-21 — M3 冻结输入执行与独立 mask 评分实现

- 新增合成 holdout 执行脚本，复用生产 adapter/LLM；图片、源码及实际请求
  对冻结 hash/body 校验，原始 HTTP 先保存再解析。默认 fake transport，
  live 要求价格 manifest；执行进程禁止读取评分 truth，不派发桌面动作。
- 独立 mask 评分遵循冻结的最近像素取整，遮挡和 mask 外位置不算命中；
  非法响应不算正确拒绝。预算保留失败/未知用量，达到上限或接口失败停批，
  零自动重试。取消保存当前尝试再传播；截断即使 JSON 完整也保留为失败。
- TDD 红绿验证及扩展用例覆盖上述行为；384 份冻结请求通过离线执行。
  本次实现不读取真实 holdout 真值，不产生付费成绩；模型实测单独归档。

### 2026-09-21 — M3 冻结 holdout：384 次完成，保留默认

- [报告、原始响应与逐布局评分](../../../backend/benchmarks/computer_use/reports/20260921-m3-holdout/README.md)：
  三配置 × 64 布局 × 两次，全部 HTTP 200、usage 已知，无重试/截断；
  实际请求与冻结一致，完成后才读取 truth，原始响应/解析/mask 384 次回放通过。
- 正例命中：Qwen3.7 **57/96**、Max bbox **96/96**、GPT point **96/96**。
  条件于合法正例点的中心误差 p95 为 **469.68 / 2.29 / 1.82 px**；Qwen3.7
  另有 14 次正例无合法点、25 次 >50 px，失败都保留。Max/GPT 的正例配对
  提升为 +40.63 pp，按 48 布局聚类 95% 区间 [+28.13,+54.17] pp。
- 三组缺失拒绝均 **16/16**，同名歧义拒绝均 **0/16**：可执行误报分别
  **14/12/16**，其余为非法坐标失败，不能冒充正确拒绝。合法率分别
  112/128、124/128、128/128。三组完整门槛均未通过，默认不变。
- 归因限制：旧提示只有“absent or uncertain”，未明确要求多个同名目标时
  拒绝，而评分要求拒绝。组合未达标成立，不能据此单独判模型识别能力；
  也不能将另图显式 status 实验当作同图 A/B 修复证明。不改既定门槛或分数。
- 本批 **715802 tokens**；调用前保守估计 $44.450304，按实际用量标价估算
  **$1.723292706**，仅 GPT 回报 cost $1.180242；完整账单仍 unknown。
  holdout **384/384 已用完**。静态累计 **541/544 次、1148511 已知 + 26000
  预留**，剩余 3 次仅属开发筛选，不能自动扩充 holdout 或重置预算。
- 此 holdout 已用于评估，不得调参后仍当独立验收。下一步先在开发样本隔离
  唯一匹配/同名拒绝提示与 schema 因素；重新验收需新样本、新冻结和明确预算。
  原生协议、M4 locate 与真实闭环仍待完成；无真实截图外发或桌面动作。
- 验证：backend **4605 passed / 1 skipped**、E2E **14 场景 / 55 步**，
  holdout 定向 11 项及 fake SDK 384 次通过；web lint/TypeScript、backend/CLI
  ruff、三个改动 Python 文件 pyright、真实后端日志、文档和协议一致性通过。

### 2026-09-22 — 明确旧 found 协议的唯一匹配要求

- 仅更新共用 adapter 提示：只有唯一、无歧义匹配可 found=true；多个匹配、
  缺失或不确定时 found=false，并保留原零/null 哨兵。schema、坐标解析、
  模型参数、默认模型及 LLM 层均不变；这明确要求，不宣称模型已可靠遵守。
- TDD：实际 SDK 请求中的规则断言先失败，再修改提示后通过；point/pixels/
  bbox 与三种 nullable 配置均覆盖。历史原始响应的解析/评分仍一致，只允许
  已声明的提示文字差异；旧 holdout freeze 继续拒绝源码变化，不改写旧证据。
- HTTP 错误/取消等测试使用临时当前契约 freeze。定位测试 103 项、三份开发
  假请求已通过；本轮开发实测限定剩余 3 次筛选额度，另记结果，不扩充 holdout。

### 2026-09-22 — 唯一匹配开发 smoke，首轮请求额度用完

- [原始请求、响应与回放](../../../backend/benchmarks/computer_use/reports/20260922-m3-unique-match/README.md)：
  复用开发图 302-ambiguous（两个“7”），Qwen3.7 point、Max bbox、GPT point
  各一次；只改旧 found 提示，schema/profile 设置保持。三次 HTTP 200、合法、
  usage 已知，无重试；实际请求/原始响应/拒绝评分回放通过。
- Max/GPT 正确拒绝；Qwen3.7 仍 found=true 并返回坐标。单布局、无旧提示
  同步控制、无正例，不能宣称因果收益、可靠拒绝率或无退化。默认模型不变；
  已有 holdout 的歧义失败不改分，也不重用作调参后的独立验收。
- 本批 6897 tokens；筛选 **144/144 次、413208 已知 + 26000 预留**，剩余
  请求为零。首轮静态 **544/544 次、1155408 已知 + 26000 预留**。预检与
  holdout 账本不变。费用预估 $0.347268，按实际用量标价估算 $0.016570457；
  GPT 部分回报 $0.012255，整批实际账单 unknown，历史 402 未计零。
- 无真实截图、桌面动作或新 holdout 请求。新增付费实验须另列批次/理由/
  样本/预算；下一步可推进 M4 离线 locate 编排，不能放宽既定采用门槛。
- 验证：backend **4615 passed / 1 skipped**、E2E **14 场景 / 55 步**、
  定位 **103 passed**、三份 fake SDK 通过；lint/TypeScript、改动 Python
  pyright、真实后端日志、文档及协议一致性通过。代码提交 `73f6b0e`。

### 2026-09-22 — M4 可选定位编排与任务约束

- Agent frontmatter `grounding: {}` 启用分离模式，省略则保留一体模式。独立
  profile 和后备 profile 均显式解析；默认复用规划模型，没有改生产定义/模型。
  使用 M2 FrameTool/M3 GroundingAdapter，不新增代理、调度器或 SDK 路径。
- Runner 为每个任务生成独立工具/截图/引用视图；定位只接收当前 PNG、目标
  和宿主窗口约束。规划器使用 location_id，不能传坐标/ctx 或覆盖 frame。
  保留自定义 agent 要求，专用提示明确覆盖旧坐标协议，工具白名单和审批仍有效。
- 规划与定位共享账本，响应解析前保留 usage，unknown 不计零；有 token 上限
  时 unknown 停止。取消/截止时间中断请求，动作边界复检；原生键盘/启动操作
  若已开始，确认其结束后才允许任务退出和释放桌面锁，不宣称即时物理中止。
- 最多首次定位加两次重定位，重新截图不重置；后备切换最多一次。失败或新
  观察作废旧引用。短 batch 最多 8 步，预检动作白名单、逐步复核画面、首错
  即停并返回新观察；失败批次不能原样重放。派发状态与 effect=unknown 分开。
- TDD 先复现缺少 locate、取消不打断 HTTP、drag 引用丢失、批次提前输入、
  自定义提示丢失和原生输入线程未收尾，再最小修复。新增 38 项离线用例，
  真实 Runner/ToolManager/LLM/SDK 配合 fake HTTP/OS；两种模型配置和预算
  边界、图像隔离、歧义/非法/截断、窗口/场景变化、取消/超时等均覆盖。
  Cucumber 在原 chat.feature 加派发/停止契约，复用 pytest harness，不冒充
  browser/WS 派发验收。真实模型效果、物理停止时延及 M5/M6 均未提前通过。
- 本轮无新增付费定位/闭环实验、真实截图出站或桌面输入；历史 544 次额度
  保持用完。常规 E2E 仍使用现有语音/对话服务，不计作定位实验。
  整体计划保持 active，M5/M6 未执行。实现/测试提交 `d05dce6`。
- 最终验证：backend 全量 **4652 passed / 1 skipped**；定位定向 **38 passed**
  （全量收集后另扩一项原生异常取消参数，并单独通过）；E2E **16 场景 / 63 步**。
  web lint/TypeScript、backend/CLI ruff、全部六个改动 Python 文件 pyright、
  实际后端 pane、docs 和协议一致性检查通过。无新增 type-ignore。
- 验证环境记录：最初全量收集找不到 Opus；指定已安装库的 DYLD_LIBRARY_PATH
  后完整通过，未修改音频代码。一次 E2E 语音转写超时发生在持续开发重载期间；
  停止源码修改、确认重载完成后全套复跑通过，保留该次失败，不改测试等待条件。

### 2026-09-22 — M5 启动：分离模式 benchmark 测量入口

- 先核对 M0 历史基线与 M3 已用完的 544 次静态额度。发现 benchmark 的
  TracedScreenshotTool 会遮蔽 M4 FrameTool，C/D 在首请求前失败；同时缺少
  定位 profile 配置、非流式定位计量、observer 回传和 locate GUI 评分支持。
- TDD 复现后修复：通过 Runner 可注入 LLM 工厂包装本次所有命名模型，保留
  生产默认工厂；配置/adapter 记录到 describe。定位初始截图与动作反馈经
  observer 留在本轮 trace，各模型实际 SDK 请求均记录图片 hash。
- 共享 benchmark counter 记录规划和定位用量，定位未知 usage/异常/取消
  不计零；定位 RTT 单列为无 TTFT 的调用，规划区间扣除嵌套定位时间，避免
  两次累计。原有规划时序仍可能包含本地工具开销，不称纯 HTTP 延迟。
- locate 作为 GUI 观察工具，不当成输入 primitive。Runner 的无名终止错误
  现在进入 DriverResult.error；预算耗尽不再被漏记。评分 revision 更新为
  `trial-token-gui-grounding-v5`，不重写历史结果或与旧 revision 直接相减。
- 定向测试 **77 passed**：包括真实 create/Runner/SDK 的同/异模型、四种预算
  边界，初始/反馈截图、实际 HTTP 次数、token 总量、失败/取消未知用量和
  嵌套时延去重。假 OS/HTTP 不代表任何真实任务成功率或物理停止验收。
- 本轮定位/闭环付费请求 **0**，截图出站和真实桌面动作 **0**，历史额度
  不变。M5 四组对照保持未完成：B 单因素/组合接口、batch primitive 计量、
  原始响应与目标错误分类、冻结配对执行仍待补齐；本次不提前申请真实图授权。
- 代码提交 `03acaaa`。最终验证：backend **4663 passed / 1 skipped**，
  E2E **16 场景 / 63 步**；web lint/TypeScript、backend/CLI ruff、六个
  改动 Python 文件 pyright、实际后端 pane、docs 和协议一致性检查均通过。
  benchmark 回归的首次 sandbox 运行因无法绑定回环端口失败，授权环境
  重跑全部 77 项通过；保留环境失败记录，未修改测试规避断言。

### 2026-09-22 — M5 B 组一体适配与单因素开关

- `grounding.mode=integrated` 让同一规划模型直接输出 location；无 locate
  工具、无第二次定位 HTTP。默认省略 grounding 仍为原 A；已有 `grounding: {}`
  仍为 split。四个实验配置使用相同的任务局部 frame、动作反馈和预算框架：
  A-control=`legacy/false`、B-host=`legacy/true`、B-protocol=`point/false`、
  B-combined=`point/true`（依次为 protocol/host_restore）。
- 增加 A-control 是为单列新框架影响：location 包装、帧新鲜度检查、当前观察
  内的输入约束、反馈、统一取整和截断拒绝均不同于原 A。不能直接把 A 到
  B-host 的全部差异归为坐标还原。框架内 host 开关不改变工具 schema。
- B 支持 legacy、point、pixels、bbox；适配 schema/解析复用 M3。关闭宿主
  还原时模型需恢复到主屏坐标，再经相同当前帧校验执行；观察区域外不点击。
  像素 schema 在首次截图前不声明尺寸上限，解析时按当前 frame 严格检查。
  对 C 的定位请求仍带具体尺寸上限，最终冻结须保留此接口结构差异。
- 一体和分离复用短 batch、取消、共享预算与反馈。拒绝定位不能被 batch
  当作执行成功后继续输入；内部成功派发事件使 batch primitive 不再漏计。
  既有 screenshot primitive 口径保留，locate 不计输入，dispatch 不等于效果成功。
- 实验任务的流式响应先保留 usage，再拒绝不完整 finish_reason、重复 JSON
  字段及非对象参数；截断但 JSON 完整也零输入。该检查对有任务上下文的
  一体/分离模式生效，原 A 的默认流式行为不变。集成模式不支持独立定位
  profile、fallback 或 strict=true，配置错误直接拒绝，不静默忽略。
- TDD 先复现缺配置、错误映射、截断执行、拒绝后继续批次及 primitive 漏计，
  再实现。新增配置/实际 SDK/假 OS 的单动作与 batch、四协议、两种还原、
  截断/重复字段、缺失/歧义/非法坐标/陈旧帧/场景变化、schema 配对用例。
  本轮付费定位/闭环实验、真实截图外发及桌面动作均为 0；旧 544 次额度、
  默认模型不变。常规 E2E 服务调用不计作定位实验。
  A-control 只增加可选配置，不扩充 M6 的 12 个 calc trial 上限；实际
  单因素/配对批次仍须各自列明预算。
- 四组实际模型/参数及最终请求尚未冻结，未宣称效果收益；单因素实现不等于
  模型因果实测完成。实现提交 `95962a1`，嵌套 batch 重复字段补强提交
  `7804df7`。
- 最终验证：backend **4718 passed / 1 skipped**；新增 **55** 项离线用例，
  定向跨层回归 261 项通过后新增 schema 配对亦通过；补强的重复字段 16 项
  通过。E2E **16 场景 / 63 步**；web lint/TypeScript、backend/CLI ruff、
  九个改动 Python 文件 pyright、实际后端 pane、docs 和协议检查通过。
- 首次 E2E 语音转写超时（15/16 场景通过）：日志确认 WatchFiles 因
  `tests/test_computer_locate.py` 修改重载，断开 WebSocket，并在关闭 ASR
  连接时记录 ConnectionClosedError。停止所有 Python 改动、确认新进程
  启动完成后，全套 E2E 重跑通过且当前 pane 无错误；未修改等待时间或
  语音代码，保留首次失败记录。

### 2026-09-22 — M5 配置及代表性请求离线冻结

- 新增离线生成器 `prepare_computer_comparison.py`，真实 Runner/LLM/SDK
  走 screenshot → 可选 locate → done；仅 HTTP、像素和身份/时钟边界使用
  固定假数据。不执行桌面输入、任务 setup/validator 或真实模型调用。
  实现及测试提交 `6865142`。
- [冻结报告及新批次提案](../../../backend/benchmarks/computer_use/reports/20260922-m5-contract-freeze/README.md)
  保存原始 profile 与七组独立实验定义、实际 allowlist、20 个代表性 SDK
  请求、PNG、源码/产物哈希和依赖版本。原始配置关闭 usage；所有实验组
  统一开启 usage、关闭 thinking、输出上限 8000，默认配置未改动。
  D 固定 M3 的 Max+bbox 候选，status_field=false；不重开候选搜索。
- 实际 production 公开配置独立导出两次，所有生成文件逐字节相同。
  五个新增用例验证重复生成、profile/工具协议配对、locator 历史隔离、密钥
  不输出、未知 headers/body/provider 拒绝及拒绝覆盖；定向跨层共 106 项通过。
- 新批次仅提案：5 个单因素 pilot 加原定 12 个核心 calc trial，串行重置，
  明列配对顺序、≤362 HTTP、≤5.1M token、任务时间≤2040 秒及拟定 8 USD
  费用上限。现有通用 CLI 尚不能保证这些门禁；原始响应/失败归因、预算/重试、
  配对执行、可验证清理和真实环境仍待实现/冻结，再按 §6 确认 live 范围。
  M5 效果对照未运行，既有 544 次静态额度和真实图授权范围均未扩展。
- 完整验证：backend **4723 passed / 1 skipped**；E2E **16 场景 / 63 步**；
  web lint/TypeScript、backend/CLI ruff、新增脚本及测试 pyright、实际 backend
  pane、docs 与协议一致性检查通过。本轮仅新增五个离线用例，未更改生产行为。

### 2026-09-22 — M5 原始 HTTP 响应证据

- `SubAgentDriver.create` 为 built-in 原 A 和 grounded 规划/定位客户端接入
  响应 hook。每个实际 HTTP 尝试分配独立 request_id，原始响应写入 trial 的
  `responses/<request_id>.bin`，trace 保留对应模型/请求图像哈希、HTTP 状态、
  响应长度/SHA-256、编码信息及读取状态。插件自有 transport 不冒充已接入。
- 响应逐块复制后交给 SDK，不预读完整 SSE；JSON 解码失败、429/502 和部分流
  均保留已收到的字节。压缩原始字节与 HTTPX 已解码 body 分别标记，避免
  离线重复解压；不导出请求 headers、cookies 或整份响应 headers。
- `complete/read_error/cancelled/closed_early/trace_closed/no_response` 描述的是
  读取生命周期。HTTP body 完整不等于合法模型输出、已知 usage 或任务成功；
  无响应不等于零费用，也不能据此断言具体的网络失败原因。语义失败归因仍待补齐。
- trace 关闭会收尾部分文件和未收到响应的尝试；响应归属绑定发起请求的 trial，
  迟到字节/headers 不会改写已关闭记录或下一轮。该机制不证明物理输入清理完成。
  文件写入仍有本地开销，延迟数字不能宣称是纯提供方延迟。
- 新增 10 个离线测试，另加强真实 create → Runner → SDK 的同模型/独立定位
  profile 响应关联断言。全部 HTTP/OS 使用假边界，无付费定位请求或真实桌面动作。
  旧冻结证据不改写，执行器和门禁最终完成后需按最终 revision 重冻结；
  M5 效果对照、预算/重试执行、配对调度、真实环境和可验证清理仍未完成。
- 实现及测试提交 `2ca4254`。完整验证：backend **4733 passed / 1 skipped**；
  E2E **16 场景 / 63 步**；web lint/TypeScript、backend/CLI ruff、四个改动
  Python 文件 pyright、实际 backend pane、docs 和协议一致性检查全部通过。

### 2026-09-22 — M5 分离定位阶段与协议拒绝归因

- `LocateSession.locate` 记录 attempt/outcome，保留规划器目标描述、frame、
  backend/protocol；获得响应后保留模型/响应 ID、finish_reason、usage 是否
  已知及解析后的图像点/框。call_id 串起 usage 和 HTTP request，再通过
  request_id 找到上一轮实现保存的原始响应。请求关联在成功/失败后恢复，
  不给后续规划 HTTP 错标定位标签。
- 阶段覆盖 preflight、前置观察、请求、计量、解析、后置观察、最终检查和
  resolved。响应拒绝用 ValueError 子类提供稳定代码：invalid_response、
  incomplete_response、refused_response、invalid_tool_call、invalid_location；
  保留既有拒绝行为和异常文本，不修复或猜测模型参数。
- 非协议错误保留阶段及异常类型；共享预算停止保留 stop reason，取消继续
  向外传播。请求阶段可能失败于本地 payload、HTTP 或 SDK，不统一称为网络错。
  deadline 在内部可能表现为取消，应结合外层终止记录，不凭字符串猜原因。
- found/not_found/ambiguous 仅表示模型报告的结果，legacy found=false 仍映射
  ambiguous。没有独立真值时，不声称目标选对、坐标命中或正确拒绝；当前记录
  不覆盖一体 A/B 和输入派发后的效果归因。完整语义正确性评分仍是待完成项。
- 新增 6 个拒绝/请求失败用例，另将旧引用失效用例扩展为非法响应、截断和拒绝
  三种情况；原有外层 LocateTool 已会清除旧引用，补测通过后未改动该行为。
  加强既有缺失/歧义、坏帧、未知 usage、预算、取消、重定位上限及真实
  create → Runner → SDK 的关联断言。无付费定位请求或真实桌面动作；
  M5 预算/重试门禁、串行配对、真实环境、物理清理和效果对照仍未执行。
- 实现及测试提交 `93997e5`。最终完整验证：backend **4742 passed / 1 skipped**，
  E2E **16 场景 / 63 步**；web lint/TypeScript、backend/CLI ruff、四个改动
  Python 文件 pyright、实际 backend pane、docs 和协议一致性检查通过。
  首轮完整检查为 4739 项通过；补充三个旧引用失效用例后，全套复验亦通过。

### 2026-09-22 — M5 每轮 HTTP 准入限额与零重试

- `SubAgentDriver.create` 新增显式 `request_limits`，默认关闭。分别限制规划、
  定位和总次数，独立 locator profile 共用总额；engine/extension transport
  不支持此门禁，创建前拒绝。尚无 CLI 开关或批次执行器接入。
- 在 HTTPX 请求 hook 进入 transport 前计数，失败不退额；定位上下文之外的
  请求（含规划压缩）归规划。计数表示准入尝试，不等同线上送达或计费次数。
  禁用这些 LLM 实例的应用层及 SDK 重试，429/503 不自动重发。
- 超额尝试只记 `request_blocked`，不生成 HTTP 请求/响应记录；收尾保存
  `request_budget`，终止原因 `request_limit`，cleanup 仍为 unknown。
  每轮串行运行建立新额度，关闭/旧上下文不能借用下一轮额度。最后一个已准入
  响应仍可能派发动作，次数门禁不证明物理停止或输入释放。
- 新增 21 个用例：计数/参数/插件边界 7 项、双层禁重试 1 项、真实
  create → Runner → SDK 的 A/B/独立定位 13 项，含失败、上限及复用隔离。
  HTTP/OS 使用假边界；本轮付费模型请求、真实截图出站和桌面动作均为 0。
- token 输入上界与调用前预留、未知 usage 保守扣留、费用及批次总额仍待实现；
  现有任务 token 计账在返回后执行，不能称为硬预算。串行配对、真实环境、
  独立真值、物理清理与效果对照继续待办，历史 544 次额度不重置。
- 实现及测试提交 `4b1af96`。定向测试 **183 passed**；完整 backend
  **4763 passed / 1 skipped**，E2E **16 场景 / 63 步**。web lint/TypeScript、
  backend/CLI ruff、六个改动 Python 文件 pyright、实际 backend pane、docs
  和协议一致性检查全部通过。

### 2026-09-22 — M5 token/费用预留账本（离线基础）

- 新增 `SpendLedger`：调用前同时检查 trial 和批次的 token/费用额度，
  任一不足拒绝且锁住全批；完整有效 usage 按预留单价结算，只释放未用部分。
  金额使用整数 nano-USD，单价为每 token 的 nano-USD；不内嵌模型现价。
- 缺失、部分或非法 usage 不退预留并停批；部分有效计数已超过上界时，
  保留较大的观测值及其余预留。完整用量超过任一输入/输出声明上界时不截断
  数字，按观测值记账并标记 `bound_exceeded`，不能称为守住预算。
- 每批串行、每轮一个未结算请求；trial/request ID 不复用、不可重复结算。
  `finish_trial` 将未结算项转 unknown，后续结算不能释放；新 trial 保留批次
  累计。快照区分 known 与 reserved，保存各请求预留、状态及首个停止原因。
- TDD 新增 **51 项**离线账本测试，连同原请求次数测试 **58 passed**；覆盖
  双层双维度上限、缺失/非法/超额 usage、取消收尾所需 API、复用隔离和精确
  整数费用。测试没有触发真实取消或 HTTP；尚未验证实际传输接线。
- 本步仅完成内存账本。可靠的最终请求输入上界、输出/推理 token 约束、
  价格适用范围及 usage 归一化、HTTP 预留/结算接线、持久化与串行配对调度
  仍待完成；账本需要调用者在 finally 收尾并依据停止状态阻止后续派发。
  未修改生产默认配置，无付费模型请求、真实截图出站或桌面动作；M5 仍 active。
- 实现及测试提交 `bc2ba1f`。完整 backend **4814 passed / 1 skipped**，
  E2E **16 场景 / 63 步**；web lint/TypeScript、backend/CLI ruff、两个新增
  Python 文件 pyright、实际 backend pane、docs 和协议一致性检查全部通过。

### 2026-09-22 — M5 HTTP 预留/结算接线与上下文上界门禁

- `SubAgentDriver.create` 新增显式 `spend`，必须同时启用请求次数限制和零重试。
  端点 URL/型号绑定完整输入上下文上界、输出上限、价格与依据；只接受明确
  关闭思考、受限输出、流式 usage 及已知参数。未知参数或畸形/重复键 JSON
  发送前拒绝；按整个契约预留，不把字符数或 tiktoken 估算冒充上界。
- 规划、定位及非流式调用在发送前预留；与 HTTP 原始响应共用 request_id，
  记录最终请求 body hash。次数门禁在前，因此费用门禁拒绝时可能已占次数槽，
  但不生成实际 HTTP 请求记录。独立 locator profile 共用批次账本。
- 原始响应逐块复制，额外审计缓冲最多 2 MB，不预读整包。请求 identity 编码，
  压缩响应保留 unknown；原始 usage 独立检查整数类型及输入/输出/总量一致性，
  SSE 必须有唯一 usage 和 DONE。SDK 会将布尔值转成数字，新增回归已覆盖，
  不能只依据 SDK 对象释放预留。结算失败在新工具派发前抛出；此前文本可能已输出。
- 取消、读取失败或未结算请求在 trial 收尾保留预留；每轮和累计证据保存到
  trace 与 driver metadata。没有物理停止/输入释放保证，cleanup 仍 unknown。
  新增 33 个 HTTP/契约用例及 13 个 create/Runner/SDK spend 分支，均用假边界。
- [Flash 官方快照说明](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash)
  （2026-09-22 核对）列出非思考最大输入 **991808**。完整上下文预留加 8000
  输出为 **999808**，高于提案每轮 **300000**，所以该保守模式会在首请求前
  拒绝，不能据此启动 17 trial。更紧的可验证输入上界、价格/区域及完整计费
  语义、批次调度与持久化、真实环境和清理继续待办；不擅自调低上界或扩预算。
- 本轮付费请求、真实图出站和桌面动作均为 0，默认配置不变，M5 保持 active。
- 实现及测试提交 `3eb20e4`。定向 **280 passed**；完整 backend
  **4860 passed / 1 skipped**，E2E **16 场景 / 63 步**。web lint/TypeScript、
  backend/CLI ruff、七个改动 Python 文件 pyright、实际 backend pane、docs
  和协议一致性检查全部通过。定向首轮的本地套接字沙箱限制已在允许本地
  测试服务器的环境重跑验证，不修改测试逻辑绕过。

### 2026-09-22 — M5 更紧输入上界的提供方证据核查

- 结论：**尚未建立可用于 live 准入的更紧输入上界**。本步只核查公开文档
  和 SDK 源码，没有调用 tokenizer 服务或模型，也没有修改预算、生产默认值
  或冻结契约。保留完整上下文预留；本地计数结果不能用来释放预留。
- [官方 SDK 的本地型号路由](https://github.com/dashscope/dashscope-sdk-python/blob/main/dashscope/tokenizers/tokenizer.py)
  对任意 `qwen` 前缀均返回同一个 `qwen.tiktoken` 词表；接受快照名称不等于
  验证过该快照的 tokenizer。
  [编码实现](https://github.com/dashscope/dashscope-sdk-python/blob/main/dashscope/tokenizers/qwen_tokenizer.py)
  输入为文本字符串，执行 NFC 归一化及 BPE；没有完整 messages/tools 的
  模板组装或图片计数。依据这些实现，不能推导 Flash/Max 多模态请求的上界。
- [远程 Tokenization 实现](https://github.com/dashscope/dashscope-sdk-python/blob/main/dashscope/tokenizers/tokenization.py)
  接受 model、messages 和附加参数，并向服务发送请求；列出的型号没有本次
  两个快照。这既不能证明服务不支持它们，也不能证明返回计数覆盖兼容接口的
  图片、工具定义和服务端模板。源码的参数透传不构成计数一致性保证。
  以上链接为 2026-09-22 查阅的可变 main 分支，不是冻结的提供方契约。
- 同时核对[官方 DashScope 参数说明](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-dashscope)：
  `max_completion_tokens` 有实际输出可能相差最多 10 token 的说明；当前
  benchmark 使用的是 `max_tokens`，不能直接把该说明套用为已验证的输出
  上界，也不能据此默默切换字段。输出参数、思考关闭及计费计数的适用性仍需
  针对所选兼容端点核实；任何参数迁移都须重新冻结请求并覆盖预留边界测试。
- 接入更紧上界之前，证据必须明确绑定端点/区域和精确快照，覆盖最终完整
  messages、工具定义、图片处理及服务端模板，并明确计数是上界还是估计。
  若采用远程预计数，还须明确它自身的收费/次数以及被计数输入与实际发送
  输入的一致性；不能把另一个未计账 HTTP 调用藏在请求 hook 内。
- 下一实现项推进不依赖该外部证据的**串行批次调度与账本持久化**，仍以
  fake HTTP/OS 验收。输入上界这一项保持未完成；待提供方契约齐备再接入，
  不反复以本地 tokenizer 估计或少量 usage 样本代替证明。
- Tests：本步无行为改动，不新增模拟提供方保证的测试。完整 backend
  **4860 passed / 1 skipped**，E2E **16 场景 / 63 步**；web lint/TypeScript、
  backend/CLI ruff、实际 backend pane、docs 和协议一致性检查全部通过。
  没有修改 Python 文件，改动文件 pyright 为 N/A。

### 2026-09-22 — M5 串行批次与预留日志持久化

- 新增 `run_batch` / `BatchTrial`，按调用者给定顺序执行每个 task/agent 一次，
  复用 `run_suite`，所有 built-in driver 共用同一 `SpendControl`。启动前校验
  非空计划、唯一安全 key、平台和任务唯一匹配；不自行随机化或推断配对。
- 输出独立批次目录，保存计划、started/finished 事件、累计 spend 日志、
  最终摘要和各条目的原有报告。`completed` 表示调用返回，不代表任务成功；
  预算停止或 cleanup 非 confirmed 时不启动下一项，取消/异常收尾后继续抛出。
- `SpendLedger(..., journal=path)` 可选日志持久化；每次变更追加完整快照并
  flush/fsync，预留成功落盘才返回到 HTTP hook，结算成功落盘才允许后续工具。
  首次创建同步目录，关闭保留未结算请求；默认内存模式不变。
- 日志或目录已存在即拒绝。没有恢复/续跑 API；进程退出后的 pending 仍按
  完整预留处理，尾部不完整记录不能作为退额依据。只保护该输出位置，不是
  跨目录的全局预算或桌面锁，也不支持删除证据后重开额度。
- 写盘失败停批。回归发现并修复了持久化收尾异常导致 trial ContextVar 未释放
  的问题；费用 session 与次数上下文现在在 finally 中关闭。
- Tests：新增 **36 项**：账本持久化/强制进程退出 5 项，真实 SDK/HTTP 的
  持久化分支及写盘失败零发送/零动作、收尾异常上下文释放共 21 项，串行
  顺序/共享费用/取消/停批/防重放及非法计划预检 10 项。定向 **304 passed**。
  进程测试使用 `os._exit`，不声称完成机器断电验证；HTTP/OS 均为假边界。
- 本轮没有付费请求、真实截图出站或桌面动作。built-in cleanup 仍 unknown，
  因此该执行器目前会保守地在该轮后停止，不能据此运行完整 live 提案。
  下一步补**批次 HTTP 总次数上限与冻结输入一致性预检**；可执行输入上界、
  价格/区域、独立真值、真实环境和物理清理仍未完成，M5 保持 active。
- 实现及测试提交 `72f7907`。完整 backend **4896 passed / 1 skipped**，
  E2E **16 场景 / 63 步**；web lint/TypeScript、backend/CLI ruff、七个改动
  Python 文件 pyright、实际 backend pane、docs 和协议一致性检查全部通过。

### 2026-09-22 — M5 全批请求次数与冻结文件预检

- `run_batch` 必须显式传入 `batch_request_limit`；`SpendLedger` 的可选
  `request_limit` 在每次预留前检查，全批规划/定位共用次数，成功/失败/未知
  usage 或退回 token 均不退次数。快照和日志保存上限与 admitted_requests。
  零额度不构造 driver；耗尽后不启动下一项，单轮内超额在 HTTP transport 前拒绝。
  计数是准入次数，不证明线上送达；最后一个已准入响应仍可能派发工具。
- 新增 `FrozenFile` / `FrozenInputs`，只核对预先固定的 SHA-256，不自动改写。
  校验唯一文件、内容和声明目录的文件清单；批次强制覆盖配置、已有相邻
  `.env`、suite、所有 task YAML 与静态资源。首次输出前、每轮 driver 构造前后
  复查；变化锁批为 frozen_inputs，拒绝进入后续任务 setup/执行。
- 额外声明的 agent/源码/validator/冻结产物同样校验，但未自动发现全部依赖。
  文件检查不构成文件系统锁，也不证明已导入模块、环境变量解析、动态输入
  或最终 live 请求一致。下一步生成**可加载的实验配置，并核对解析后的
  profile、agent 定义和工具集与冻结契约的一致性**。
- 只读核查旧冻结：5 个 artifact 哈希均匹配；289 个原 sources 中 5 项变化：
  benchmarks/driver.py、benchmarks/trace.py、llm/llm.py、
  tools/computer_grounding.py、tools/computer_locate.py（均在 core/src/tank_backend 下）。
  历史冻结未改写，也没有把当前源码自动重新冻结为可执行批次。
- Tests：新增 **29 项**（账本 5、SDK/HTTP 4、文件预检 8、批次调度 12），
  并强化独立定位客户端共用次数的既有回归；定向 **338 passed**。
  构造期变化的首次红测漏隔离 IME，触发宿主 API 并报连接错误；已补齐
  IME/page-server/shell 假边界后重跑。该红测不算真实环境或物理清理验收。
- 没有付费模型请求或真实截图出站；可用输入上界、价格/区域、独立评分和
  物理清理仍待完成。M5 仍 active，未运行模型效果对照。
- 实现及测试提交 `56a2b85`。完整 backend **4925 passed / 1 skipped**，
  E2E **16 场景 / 63 步**；web lint/TypeScript、backend/CLI ruff、八个改动
  Python 文件 pyright、实际 backend pane、docs 和协议一致性检查全部通过。

### 2026-09-22 — M5 可加载配置与解析后的实验契约

- [x] 为七组实验生成独立 config.yaml 与 agent Markdown，使用生产解析器
  回读校验；historical original 只保留归档，不生成第八组运行配置。
- 新增显式 `ComparisonContract`：driver 构造 LLM/ToolManager 前，核对完整
  agent 定义、解析后的 default/planner/locator profile、agent 搜索设置和
  声明工具列表。比较排除 API key；错误不打印可能包含秘密的解析值。
  BatchTrial 可传入该契约，并强制冻结对应 manifest/JSON/agent 文件。
  未传契约的既有调用仍仅执行原有检查，不自动获得 M5 配置核对。
- 新增[独立离线产物](../../../backend/benchmarks/computer_use/reports/20260922-m5-runtime-config/README.md)，
  manifest 覆盖 19 个产物及当前源码；旧冻结未改写。配置仅保存
  `${M5_DASHSCOPE_API_KEY}` 引用。产物不验证账号/密钥、区域价格、完整
  live 消息历史或物理桌面效果；源码依赖仍须显式固定。
- Tests：新增 **31 项**：七组生产解析器、16 项解析漂移/密钥、构造资源前
  拒绝、七组真实 driver/Runner/SDK 首请求对照；既有导出回归验证可重复性
  和密钥不落盘。HTTP 为离线 transport，宿主截图/点击/Quartz 有拒绝护栏。
- 本轮没有付费请求、真实截图出站或桌面实验，默认配置不变。M5 保持 active。
  下一步将 17-trial 提案固化为可校验的批次清单并完成离线预检；可用输入
  上界、价格/区域、独立真值、真实环境及物理清理仍是实际执行的前置条件。

- 实现及测试提交 `046e7d9`；定向 **369 passed**，完整 backend
  **4956 passed / 1 skipped**，E2E **16 场景 / 63 步**。web lint/TypeScript、
  backend/CLI ruff、六个改动 Python 文件 pyright、开发服务日志、docs 与
  协议一致性检查全部通过。新冻结 19 个产物、295 个源码哈希均匹配。

### 2026-09-22 — M5 17-trial 提案清单与离线预检

- [x] 将既有 5 pilot + 12 核心 trial 固化为[独立提案产物](../../../backend/benchmarks/computer_use/reports/20260922-m5-batch-proposal/README.md)。
  固定诊断顺序与三轮配对顺序，B 始终为 B-combined；不根据 pilot 分数换组。
  每项记录配置/任务路径、phase、请求/token/时间/工具上限；总计规划 272、
  定位 90（Max 45）、HTTP 362、5.1M token、任务执行 2040 秒、拟定 8 USD。
- 新脚本 `prepare_computer_batch.py` 仅支持生成/复查，无执行入口。保存并核对
  340 个冻结/源码/配置/agent/suite/task/asset/脚本文件；核对 runtime 文件清单，
  生产解析后的七组契约及 macOS calc-open 的 strict/GUI/120 秒/15 步设置。
  生成时记录当前 suite 文件哈希供审查；复查不刷新哈希，清单本身不是授权凭证。
- 实际 SpendLedger 对已记录的 Flash 输入 991808 + 输出 8000 预留给出
  trial_tokens 拒绝（单轮 300000）。该隔离检查使用零价格，只验证 token
  拒绝，不验证费用；未重新查询或背书提供方上界/账号价格。
- `offline_checks_passed=true` 且 `live_ready=false`。清单不是直接可执行的
  run_batch 输入：pilot 验收后进入 core、分组限额派发、实际环境与物理清理、
  独立评分、可用输入上界及 live 预算/端点/真实图片范围仍须完成。
  本轮未构造 driver、执行 setup/validator、发送模型请求或操作桌面。
- Tests：新增 **11 项**，固定顺序/聚合预算/实际账本拒绝及十类漂移拒绝；
  复用既有 test_comparison_freeze.py，定向 **55 passed**。新目录拒绝覆盖，
  原有冻结产物保持不变。下一步补独立评分与语义失败归因，M5 仍 active。

- 实现及测试提交 `d6ac1ae`；完整 backend **4967 passed / 1 skipped**，
  E2E **16 场景 / 63 步**；web lint/TypeScript、backend/CLI ruff、两个改动
  Python 文件 pyright、实际 backend pane、docs 和协议一致性检查全部通过。

### 2026-09-22 — 按用户要求暂停 M5 token/费用预算门禁

- 用户明确要求：benchmark 先获得实际数据，暂时关闭预算门禁；若提供方额度/
  余额不足，停止并告知用户处理。本指令取代 M5 提案中 token/8 USD 硬上限
  及更紧输入上界的开跑前置要求；不修改 Tank 生产 computer-use 的 300000。
- [x] `run_batch(record_only=True)` 接入仅记录账本；忽略 token/费用准入和
  用量超出预留的停止条件，保留全批/每轮 HTTP 次数及原始 usage 校验。
  benchmark driver 验证配置后，仅在内存中将实验 agent token_budget 设为 0，
  记录配置值与有效值；默认严格模式和生产配置保持不变。
- 未知/非法 usage、HTTP 失败、冻结变化及清理未知仍停批；不重试或补跑。
  HTTP 402 回归确认错误保留、一次请求。实际额度不足须告知用户，不能归为
  模型效果失败后继续消耗。单次输出 8000、时间/工具步数限制继续保留。
- 新[record-only 配置冻结](../../../backend/benchmarks/computer_use/reports/20260922-m5-record-only-runtime/README.md)
  与[提案 v2](../../../backend/benchmarks/computer_use/reports/20260922-m5-record-only-proposal/README.md)
  独立归档；旧冻结不改写。提案的 300000/5.1M/8 USD 仅是历史参考值，
  record_only=true 明确停用；费用状态为 unpriced，金额字段 0 不代表免费。
- Tests：新增 **11 项**：账本 1、七组真实 Runner/SDK 大用量 7、HTTP 402
  失败 2、零名义预算下的串行批次 1。现有严格模式仍覆盖；均用假 HTTP/OS。
  本轮未请求付费模型或采集真实截图，尚无新的实际模型用量数据。
- M5 后续聚焦实际 pilot 的独立评分、真实环境/物理清理和分阶段执行；
  token 上界不再作为本轮仅记录模式的阻塞项，live 图像/端点范围仍需落实。

- 实现及测试提交 `24a0832`；定向 **391 passed**，完整 backend
  **4978 passed / 1 skipped**，E2E **16 场景 / 63 步**。web lint/TypeScript、
  backend/CLI ruff、八个改动 Python 文件 pyright、实际 backend pane、docs 和
  协议一致性检查全部通过；新冻结 19 个产物、295 个源码及提案 340 个文件
  哈希匹配。

### 2026-09-22 — 首个真实 A-control pilot：失败并停止后续组

- 用户在自动审批首次拒绝后明确授权本轮受控 Calculator 桌面/黑背景/菜单栏
  与后续截图发送到 DashScope，模型 Flash 快照；仅 1 trial、16 请求/120 秒，
  token/费用只记录。[完整证据与报告](../../../backend/benchmarks/computer_use/reports/20260922-m5-a-control-pilot/README.md)。
- 本机九点校准 **9/9**；Calculator oracle 的真实按键得到 **7×8=56**，
  AX 与本机截图一致。修正检查脚本的窗口 ID 类型、窗口移回主屏，背景绑定
  Quartz 主屏；保留准备失败记录。未批准范围的本机预览没有发送给模型。
- 真实 A-control：**16 HTTP（全部 200）**，输入 **293621**、输出 **1822**，
  总计 **295443 token**；agent **62.83 秒**，含 setup/validator 的 trial
  **72.19 秒**。无余额不足/未知 usage；费用 unpriced，不将 0 占位值当账单。
  11 个独立图像哈希在请求中累计出现 86 次，历史图像重复输入成本已实际观测。
- strict **失败**，最终 AX 与截图均为 **0**；达到 **15 步**停止。保留
  batch 参数拒绝、两次 scene/geometry 拒绝、legacy location 字符串拒绝，以及
  type_text 派发成功但无目标效果的证据；不把未知因果解释成已证实模型错误。
- driver cleanup=unknown，批次 stop=cleanup_unconfirmed。外部清理发现
  Command(55) 残留按下，执行显式 key-up 后按键/鼠标均为空；已恢复窗口、
  剪贴板和光标。操作员恢复不能改写原 trial 的清理失败，也不能算 M6 清理验收。
- 未启动后续 4 pilot 或 12 核心 trial。本轮单独截图授权已使用；下一步先
  确定性复现并修复 modifier/输入无效与 scene 拒绝问题，再继续效果实验。
- Tests：生产代码无修改，新增真实执行证据而非模拟回归；backend
  **4978 passed / 1 skipped**、E2E **16 场景 / 63 步**，web lint/TypeScript、
  backend/CLI ruff、实际 backend pane、docs 与协议一致性检查通过；pyright N/A。

### 2026-09-22 — 本地复现并修复粘贴后的 Command 残留

- [x] 同一 Calculator 本地脚本修复前后对比：粘贴 `56` 均显示正确，
  Command(55) 从残留按下变为无按键残留；共享 macOS 粘贴路径改为
  成对 Command/V 事件，并在异常路径释放两键。[证据报告](../../../backend/benchmarks/computer_use/reports/20260922-m5-paste-recovery/README.md)。
- [x] 修复后重放 pilot 六次文本输入，显示依次为 `7/7/78/78/0/0`，
  每步按键均释放。Calculator 忽略粘贴的运算符/表达式；不能把输入派发成功
  当作计算成功，也不能把原轮所有无效输入归因于 modifier 残留。
- [x] 原 pilot 的多余 batch 参数与字符串 location 加入回归，保持拒绝；
  未知参数报错改为列出字段，消除 integrated 被误报为 split-mode 的歧义。
- scene/geometry 拒绝保持原校验：原 trace 缺少拒绝时校验截图，无法确定是
  时钟、动画还是其他变化。下一步补本地前后帧证据，再决定稳定场景处理。
- 无新增模型请求/截图外发；旧失败 trial 与 freeze 不变。生产 token 配置不变。
  自动物理清理、更新 source pins、剩余 pilot 与核心配对实验仍待完成。
- Tests：backend **4983 passed / 1 skipped**、E2E **16 场景 / 63 步**；
  web lint/TypeScript、backend/CLI ruff、四个改动 Python 文件 pyright、
  实际 backend 日志、docs/协议一致性检查通过。实现提交 `210dd46`。

### 2026-09-22 — 场景拒绝的本地前后帧取证

- [x] 使用真实 FrameTool observation/validation 链保留成对 PNG：全屏静置
  **5/5 拒绝**，Calculator crop 像素均未变化；差异仅在菜单栏状态图标区域。
  窗口绑定静置 **3/3 通过**，窗口内输入后的旧帧 **1/1 拒绝**。
  [原始证据与边界](../../../backend/benchmarks/computer_use/reports/20260922-m5-scene-scope/README.md)。
- [x] 四个确定性回归覆盖 full/window × 内部/外部单像素变化；保持拒绝时
  零鼠标派发。不放宽 exact hash，也不自动切换范围。
- 这证明菜单栏无关变化可导致全屏拒绝，不等于确定历史 pilot 两次拒绝的原因；
  当时缺校验帧，仍保留未知。状态图标变化不能误报为已证实的时钟变化。
- 本地脚本正常结束后窗口/剪贴板/光标恢复，按键与鼠标均释放；driver 内建
  grounding 的物理 cleanup 仍 unknown。join 原生线程不等于物理释放验收，
  不能删除 cleanup_unconfirmed 停止门禁。
- 下一步：确定跨组一致的 observation 范围并更新冻结，补可复用清理接线与
  异常/超时/取消验收，再恢复 paid pilot。本轮没有模型请求或截图外发。
- Tests：backend **4987 passed / 1 skipped**、E2E **16 场景 / 63 步**；
  web lint/TypeScript、backend/CLI ruff、改动文件 pyright、实际 backend 日志、
  docs 与协议一致性全部通过。回归提交 `bd90b81`。

### 2026-09-22 — 按用户要求移除像素一致性动作门禁

- [x] 不再在定位/动作校验阶段重新截图或比对像素。允许光标闪烁、动画及无关
  应用变化；保留 frame/session/window 身份、窗口/显示几何及停止条件检查。
  哈希仅保留为观察证据，不引入相似度阈值或隐式重试。
- [x] 测试先复现旧实现三项拒绝；四个窗口内外像素变化回归改为允许输入，
  集成/分离定位回归允许完整画面变化。几何变化仍停止 batch，取消/超时/
  授权撤销仍零输入；这些测试改为在几何校验边界注入停止。
- [x] 本地菜单栏变化和 Calculator 内容变化均通过，validation 截图数为 0。
  首次 reset 失败保留记录，显式激活/定位后重试通过；两次桌面均恢复。
  [实现边界与证据](../../../backend/benchmarks/computer_use/reports/20260922-m5-pixel-tolerance/README.md)。
- 同一几何中的弹窗/按钮变化不再由像素门禁拦截，依赖规划器检查反馈并重新
  观察。此前“保持 exact hash/先切换窗口范围”的后续方向由本次用户决定取代；
  不必为菜单栏变化强制改变跨组截图范围。旧报告与冻结保留，live 前更新 source pins。
- 无模型请求/截图外发，生产 token 配置不变；自动清理接线仍是下一项。
- Tests：backend **4988 passed / 1 skipped**、E2E **16 场景 / 63 步**；
  web lint/TypeScript、backend/CLI ruff、三个改动文件 pyright、实际 backend
  日志、docs 与协议同步通过。实现提交 `978ca00`。

### 2026-09-24 — 自动输入清理接线与本机验收

- [x] built-in macOS driver/create/run_batch 新增显式 `input_cleanup=True`，
  默认不启用，记录运行 metadata 与 batch plan。Runner 在桌面锁内执行前检查
  已按下输入；原生操作结束后释放并回读按键/鼠标，仅验证成功才 confirmed。
- [x] 正常、异常、超时、取消均收尾；清理失败隔离同进程桌面，保留批次停止。
  外部取消在清理后继续传播。macOS 原生线程及 frame/grounding 收尾处理重复
  取消，不提前交还桌面。不能强杀挂死线程，实际返回时间可超过名义 timeout。
- [x] 本机四类确定性试次实际按住 Command(55)/鼠标左键，均验证原生操作
  已结束及两者已释放；无模型请求/截图外发。
  [完整证据和范围](../../../backend/benchmarks/computer_use/reports/20260924-m5-input-cleanup/README.md)。
- confirmed 仅指原生输入收尾和释放。应用输出留给 validator，窗口/剪贴板/
  光标等恢复仍由 trial/harness 承担；不等于完整 M6 或跨进程清理验收。
- 下一步更新修复后的 source/config/request 冻结及分阶段执行入口，完成本地
  preflight 后重新执行 A-control pilot；旧失败证据不可覆盖。
- Tests：backend **4999 passed / 1 skipped**、E2E **16 场景 / 63 步**；
  web lint/TypeScript、backend/CLI ruff、11 个改动 Python 文件 pyright、
  实际 backend 日志、docs 与协议同步通过。实现提交 `7cfcf9c`。

### 2026-09-24 — 更新冻结并准备 A-control 单轮执行

- [x] 生成新的[七组 runtime/SDK 冻结](../../../backend/benchmarks/computer_use/reports/20260924-m5-runtime/README.md)
  和 [schema v3 提案](../../../backend/benchmarks/computer_use/reports/20260924-m5-proposal/README.md)，
  342 个文件通过预检。保留原组别/模型/顺序，强制声明 input_cleanup=true。
- [x] `execute_a_control` API 固定只取第一项，要求显式 live 授权，再校验
  proposal/config/source 与运行目录清单；最多 16 请求、120 秒、15 步，
  token/费用仅记录，启用自动输入清理，无后续组自动派发。
- [x] [可审查启动脚本和本地预览](../../../backend/benchmarks/computer_use/reports/20260924-m5-pilot-ready/README.md)
  已保存。默认仅预览并退出，不读取模型凭据；live 模式还需复核新截图后放行。
  主屏 Calculator/黑背景/菜单栏已本地检查，桌面与输入状态恢复正常。
- 本轮真实请求为 0。之前仅 1 trial 的截图外发授权已用于旧失败 pilot；新轮
  尚待明确授权。全批次仍 live_ready=false，pilot→core 阶段自动推进未实现。
  旧失败证据和旧冻结保持不变。
- Tests：backend **5004 passed / 1 skipped**、E2E **16 场景 / 63 步**；
  web lint/TypeScript、backend/CLI ruff、两个改动 Python 文件 pyright、
  实际 backend 日志、docs 与协议同步通过。入口提交 `92070ff`。

### 2026-09-24 — 修复后 A-control 真实单轮结果

- [x] 用户明确批准新轮截图外发后，按新冻结执行 1 trial；[完整证据](../../../backend/benchmarks/computer_use/reports/20260924-m5-a-control-pilot/README.md)
  已归档，旧证据不变，未自动启动任何后续组。
- 16 HTTP 全部 200；输入 **234042**、输出 **4239**，合计 **238281 tokens**；
  agent **98.81 秒**，整轮 **107.95 秒**。因 15 步上限停止，非 token/费用或超时门禁；
  无余额不足响应，实际金额仍 unpriced。
- strict 失败：AX 与原始分辨率末帧均为 **0**。预览显示曾导致窗口不可见的误判，
  已经原图及像素核对撤回，不能归因为环境遮挡。六次工具错误包括未知参数、
  数组被字符串化和一次旧/无效 frame；无像素变化/场景几何拒绝。
- 自动输入清理 **confirmed**，按键/鼠标均空；外部窗口、应用、剪贴板和光标恢复成功。
  完成执行不代表任务成功，单轮不得用于 A/B/C/D 效果归因。
- 下一步：先对该轨迹的参数格式和 legacy 帧/坐标使用做离线重放，决定后续 pilot；
  尚余 4 个 pilot 变体、12 个 core trial、阶段推进与完整比较。
- 验证：backend **5004 passed / 1 skipped**、E2E **16 场景 / 63 步**；web lint/TS、
  backend/CLI ruff、开发服务日志、docs 与协议同步通过；无 Python 改动，pyright N/A。

### 2026-09-24 — 单轮失败的离线重放与工具说明修正

- [x] 从已归档真实轨迹提取六次失败调用，在 fake HTTP/OS 边界重放，保留精确参数及错误。
- [x] 修正 integrated batch 沿用 split location_id 的描述，明确覆盖旧 screenshot=true
  示例；不放宽参数类型或帧身份校验，不修改历史冻结或归因模型成功率。
- Tests：扩展现有 test_computer_locate.py，覆盖实际 SDK 请求中的说明与 schema、
  六次拒绝的零输入，以及重新观察后的合法调用恢复；执行下方完整 Verification Checklist。
- [离线证据](../../../backend/benchmarks/computer_use/reports/20260924-m5-argument-replay/README.md)：
  六次错误原样重现并可在新观察后恢复，相关文件 **146 passed**；零模型请求/物理输入。
  当前源代码变化使旧冻结失效；下一步生成包含说明修正的新冻结，不覆盖旧实验。
- 完整验证：backend **5010 passed / 1 skipped**、E2E **16 场景 / 63 步**；
  web lint/TS、backend/CLI ruff、改动 Python 文件 pyright、服务日志、docs 与协议同步通过。

### 2026-09-24 — 工具说明修正后的新冻结与执行材料

- [x] 生成[新七组冻结](../../../backend/benchmarks/computer_use/reports/20260924-m5-contract-runtime/README.md)
  和[新批次提案](../../../backend/benchmarks/computer_use/reports/20260924-m5-contract-proposal/README.md)，
  342 文件预检通过；旧实验、旧冻结保持不变。
- [x] 对比序列化请求：A/C/D/original 完全一致；A-control 和三个 B 组仅
  system 指令及工具描述变化，结构 schema、图片、模型与生成参数保持一致。
- [x] [新单轮启动材料](../../../backend/benchmarks/computer_use/reports/20260924-m5-contract-ready/README.md)
  指向新冻结和全新输出目录，脚本语法通过；本轮零模型请求、零桌面操作。
  历史预览仅作范围参考，实际发送前仍需新截图复核与本轮单独授权。
- Tests：无生产代码/行为新增；复用已有 5010 项 backend 回归及单轮执行入口检查，
  本轮仍执行下方完整 Verification Checklist；Python 改动类型检查 N/A。
- 下一步：获新一轮授权后重跑修正说明的 A-control；仍限 1 trial/16 请求/
  120 agent 秒/15 步，token/费用仅记录，不自动推进到其他组。
- 完整验证通过：backend **5010 passed / 1 skipped**、E2E **16 场景 / 63 步**；
  web lint/TS、backend/CLI ruff、服务日志、docs 与协议同步通过。

### 2026-09-24 — 修正工具说明后的 A-control 实测

- [x] 新轮授权及原图范围复核后运行一次；[完整证据](../../../backend/benchmarks/computer_use/reports/20260924-m5-contract-pilot/README.md)
  已归档，未追加任何 trial。
- 16 HTTP 全部 200；输入 **396213**、输出 **2689**，共 **398902 tokens**。
  超过旧 300000 参考值仍正常执行，token/费用门禁关闭生效；无余额不足错误，金额未核价。
  agent **75.33 秒**，整轮 **84.54 秒**，因 15 步上限停止。
- strict 失败，AX 与原始末帧均为 **0**。两次 batch 和截图数组已被接受；
  batch 点击位于所见 Calculator 窗口右侧，另有 1 次旧帧、1 次引号按键名、
  2 次字符串 location 错误；无像素变化拒绝。单轮不能证明提示改善或模型优劣。
- 自动输入清理与外部桌面恢复确认成功。生产代码无修改，旧失败证据保持不变。
- 下一步准备同一新冻结下的 B-protocol-only（同模型、host_restore=false）；
  当前单轮入口只支持 A-control，需补选定 pilot 的受限入口和独立授权。
  尚余 4 个 pilot 变体、12 个 core trial、阶段推进与完整比较。

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
