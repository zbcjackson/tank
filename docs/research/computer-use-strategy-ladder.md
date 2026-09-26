> 日期：2026-09-26。结论状态：调研完成，方案与实施计划见
> [策略阶梯计划](../plans/active/computer-use-strategy-ladder.md)；
> 本页所有候选通道与决策层均未实现、未实机验证，外部机制描述不构成
> 在 Tank 上的效果承诺。

# Computer use 多策略执行阶梯与决策层调研

## 1. 问题定义：为什么继续优化"模型报数字"收益有限

当前生产基线 A（一体规划定位 + legacy 归一化坐标，qwen3.7-flash）的
全部已知证据见 [现行设计](../design/computer-use.md) 与
[M8 收口报告](../../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)。
约束它的四个事实：

1. **数值定位是主要失败源，且换协议换提示都修不掉。** M3 holdout 上
   qwen3.7 正例仅 57/96；GPT-5.5 point/bbox 正例 96/96 但同名歧义拒绝 0/16；
   M5 接口矩阵证明单位匹配模型原生习惯是关键因子，强模型使单位问题消失。
   归因止于服务输出边界（I11 保持 unknown）。
2. **全截图输入的成本与延迟是结构性负担。** 每个 observe→act 循环都上传
   整屏 PNG；单 trial 同一图像哈希累计出现 86 次；live trial wall
   20.6–126.3 s。Tank 是语音助手，用户在实时等待。
3. **AX 机制闭环成立，但选择精度是瓶颈。** M7 live3：宿主绑定→枚举→
   文本选择→派发→独立评分全部走通并拿到 strict 通过；qwen3.7-flash
   选择器在 57 行候选里反复 off-by-one / 误选 All Clear；AX 臂 token
   成本反而更高（245k vs 181k）。
4. **结构化信息一直存在于模型输入之外。** 浏览器有 DOM，原生应用有 AX
   树，屏幕文字可以用本地 OCR 读出。这些通道不依赖模型估计数字，却
   在基线 A 里完全没有被用作定位来源。

因此本调研的核心转向是：**与其让模型输出更准的坐标，不如让大多数动作
根本不经过坐标估计**。截图点击保留为最终兜底（L4），上层通道以
"元素引用 + 宿主几何计算"替代数值定位。这与
[外部实现对照](computer-use-implementation-comparison.md) 中 Peekaboo /
Cua / browser-use 的结论一致：坐标是兜底，语义引用是主路。

## 2. 策略阶梯总览

按"确定性优先、通道越具体越可信"排序，每个动作步在阶梯上自上而下
尝试，任意一层失败/不可用即降级，L4 永远可用：

| 层级 | 通道 | 定位介质 | 输入成本 | 延迟量级 | 覆盖范围 | 主要失败模式 |
|---|---|---|---|---|---|---|
| L1 | 浏览器 DOM（CDP/Playwright） | role/text 选择器、DOM 框 | 纯文本 | ~100ms 级本地 | Chromium 系浏览器内页面 | 非浏览器应用、需开调试端口、动态重渲染 |
| L2 | AX 语义寻址（复用 M7） | 编号候选 + 元素引用 | 纯文本 | ~100ms 级本地 + 一次选择调用 | 有 AX 树的原生应用 | 自绘控件、AX 缺失、选择错行 |
| L3 | OCR 文本区域 | OCR 框 + 模糊文本匹配 | 本地推理 | ~100ms–1s 本地 | 任何"可见文字"目标 | 图标类无文字、美术字、密集小字 |
| L4 | 视觉定位兜底（基线 A / 拆分 C） | 模型输出坐标 | 截图上传 | 3–30s | 一切可见目标 | 现有全部已知偏移/单位问题 |

三条硬边界沿用现有纪律：

- **兜底保证**：L1–L3 任一层 not_found/ambiguous/派发失败时才降级；
  每个动作步只走一遍降级链（对齐现有"每步至多两次重定位、一次后备
  切换"预算），避免 fallback 风暴。
- **审批与预算不变**：所有层最终派发的都是同一批 computer 类工具，
  审批策略、SubAgentContext 预算、停止/取消语义原样复用。
- **候选不泄漏真值**：OCR/AX 候选列表来自当次观察，不注入 benchmark
  答案（M7 已有同等约束）。

## 3. 通道技术评估

### 3.1 L1 浏览器 DOM（CDP + Playwright）

**机制**。Chromium 系浏览器暴露 CDP（`/json/version`、`/json/list`）；
Python Playwright `connect_over_cdp()` 即可附着已有实例并按
`getByRole` / `getByText` 语义选择器操作页面。文档：
[Playwright browsers](https://playwright.dev/python/docs/browsers)。

**关键约束（2026 年现实）**：Chrome 136 起 `--remote-debugging-port`
在默认 user-data-dir 上失效，必须搭配非默认 `--user-data-dir`
（[官方公告](https://developer.chrome.com/blog/remote-debugging-port)）。
即"附着用户日常主 profile"这条路已被上游关闭。可行形态：

1. **Tank 管理的浏览器实例**（专用 profile 目录 + 调试端口，由
   launch_app 类工具拉起）：最可控，登录态为空，适合通用浏览任务；
2. **用户显式开启的第二 profile**：需要登录态的任务由用户授权迁移；
3. **Safari**：走 safaridriver（"Allow Remote Automation"），无 CDP，
   语义选择器能力弱于 Playwright，作为条件项不进首期；
4. **Playwright 自带 chromium**：测试与 benchmark 的确定性环境，
   不依赖用户浏览器。

**窗口↔页面映射**。CDP target（url/title）与 Quartz 窗口（AX title /
CGWindow bounds）做匹配，多候选歧义时拒绝并要求澄清，不猜。

**派发选择**。DOM 解析出元素后有两种派发：

- **CDP `Input.dispatchMouseEvent`**（viewport 坐标）：无需 OS 焦点，
  不依赖 Chrome 工具栏几何换算，页面层效果与真实输入一致；
- **bounding_box → 全局坐标 → 现有 M2 Quartz 路径**：保持"所有
  computer 工具统一从 Quartz 出口"的观测/审批/回放一致性，但要解决
  窗口内容原点换算（工具栏高度不恒定）。

建议首期以 CDP Input 为主派发、DOM 读数（aria/文本/diff）为主核验，
Quartz 映射作为对照臂——两者在 S2 各留一条可测路径，用数据选型。

**收益假设**。浏览器任务是高频用户场景（benchmark 已有
03-browser-navigate、10-links-history）；DOM 通道整步无截图上传，
token 从"图像×N"降到"文本快照"，延迟从秒级降到百毫秒级。
失败分类必须单列：选择器未命中、跨域 iframe、动态重渲染、
映射歧义（[OmniParser 教训](computer-use-implementation-comparison.md)：
漏检/选错/框不可点要分别统计）。

### 3.2 L2 AX 语义寻址（复用 M7，修选择瓶颈）

M7 已交付：候选枚举（`ax_window_candidates`）、绑定帧校验、
quartz/ax_press 双派发、AX 独立评分。瓶颈只在"57 行列表里选行"。
本计划内的改进（不改变机制）：

1. **确定性预排序截断**：按 target 与 title/value/identifier 的文本
   相似度（difflib，中文按字符/bigram）排序取 top-k（如 k=12），
   唯一精确匹配直接命中。off-by-one 的主要来源是长列表 + 相邻行
   同前缀，截断后选择面缩小一个数量级。
2. **候选呈现增强**：候选附带祖先分组标签（如 "Basic → 数字区"），
   复用现有 `AXCandidate` 结构加一个 group 字段。
3. **焦点感知**：读 `AXFocusedUIElement` / `AXSelectedText`，作为
   动作前上下文与动作后核验信号（类型输入是否落到焦点元素）。
4. **选择器换执行体**：从 qwen3.7-flash 生成式调用改为
   §4 的类型化决策调用（文本进、索引+概率出），这是 M7 backlog
   触发条件中"列表呈现改进方案"的直接落点。

### 3.3 L3 OCR 文本区域

**引擎选型**。macOS 自带 Vision 框架（`VNRecognizeTextRequest`，
pyobjc 惰性加载，支持 zh-Hans/en-US，本机免费）为零依赖首选；
RapidOCR（onnxruntime 已是现有依赖，模型 ~15MB）作为跨平台/兜底。
不引入 torch 系重依赖。Vision 的 boundingBox 是归一化左下原点，
需翻转到现有图像坐标（AX 已有同类 flip 处理先例）。

**定位管线**：截图（复用 Observation 语义，含 crop/缩放元数据）→
OCR 文本框 → 与 target 描述做模糊匹配（唯一命中即取框中心，经
`map_point` 走 M2 已验证的图像像素→全局点路径）→ 多命中进入与
AX 同一套编号候选选择 → 仍歧义则降级 L4。

**AX/OCR 候选合并**：同帧内两源候选按框 IoU 去重，保留 provenance
（ax/ocr），统一进候选列表。Calculator 类纯文字按钮预期 OCR 覆盖
良好；图标按钮（无文字）预期失败——这正是要降级而不是硬点的场景。

**已知边界**：OCR 是定位器不是核验器；美术字、低对比、canvas 渲染
文字、密集小字（M3 合成图里的小目标）都会漏。S1 用 golden frame
先测召回/精度，不预设 Vision OCR 在本项目布局上的表现。

### 3.4 L4 视觉定位兜底

现有基线 A 与拆分 C 原样保留：`GroundingAdapter` 协议族、
legacy 归一化、M2 image/frame 宿主还原都已是验证过的资产。阶梯
只是把"每步必经的视觉定位"降为"前三层失败后的兜底"，并为 L4
保留全部现有证据口径（失败分类、单位习惯、批间方差记录不变）。

## 4. 决策层：Jev 类类型化决策模型

### 4.1 Jev 是什么（外部事实，带来源）

TypeSafe AI 于 2026-09-15 发布 Jev，自称 System One Model：
输入 `state`（文本/JSON，64K 上下文）+ `questions`（Choice/Score/Noul
三种类型化原语），非自回归并行采样，输出**类型确定的答案 + 每个候选
概率 + confidence**，不生成自由文本。仅托管 API
（`POST /v1/systemone`，`jev-1.13.0`/`jev-latest`），无开源权重；
定价约 $0.042/M 输入 token。来源：
[Jev API 文档](https://www.jevai.org/docs)、
[JEV 工程学](https://tonybai.com/2026/09/22/jev-engineering-the-decision-layer-for-agentic-systems/)、
[LangChain 指南](https://www.langchain.com/blog/building-a-harness-with-jev)。

与本需求直接相关的两份外部证据：

- **REFLEX**（[arXiv 2609.26532](https://arxiv.org/abs/2609.26532)）：
  agent 架构把 Jev 作为快速类型化决策层，低置信度或需生成时才调用
  强 LLM；冻结 100 任务基准上 95% 成功率、强模型调用减少 72.7%。
- **开源复现生态**：laya / kev / PlayJev 等复现可经
  [edgejev](https://pypi.org/project/edgejev/) 转 ONNX int8 本地 CPU
  部署，报告单题 15.6ms（4 vCPU），运行时仅 onnxruntime/tokenizers/
  numpy。复现与官方的等价性**未经验证**（[对照分析](https://mchromiak.github.io/articles/2026/Sep/17/Typed-Decision-Models-Jev-and-Laya-in-Agentic-AI/)）。

### 4.2 与 Tank 的契合点：五个决策位

Tank 的 computer use 回路里存在大量"闭集小判断"，现在全部由生成式
LLM 顺带完成（贵、慢、还引入 JSON 解析脆弱性）：

| 编号 | 决策位 | 原语 | 现状 | 决策层形态 |
|---|---|---|---|---|
| D1 | 本步用哪条通道（dom/ax/ocr/vision） | Choice | 无（只有一条路） | 规则可用信号（app 类型、CDP 可达、候选数、目标是否文字型）；决策层补充语义判断 |
| D2 | 候选列表选第几行 | Choice | qwen3.7-flash 生成式调用，57 行 off-by-one | top-k 后的 Choice + 概率 + 置信门控，低置信回退规划模型 |
| D3 | 动作后效果是否达成 | Noul | 模型看截图自报 | 文本态 diff（AX 值/DOM/OCR 增量）进决策层，截图核验留给规划器 |
| D4 | 当前层置信度是否够，是否降级 | Score | 无显式置信度 | 每层输出置信度，低于阈值走下一层 |
| D5 | 序列是否可 batch | Noul | 模型自行判断（M6 有 batch 对照） | 布局稳定性信号 + 决策层判断 |

**关键洞察：D2 恰好是纯文本任务**（候选列表 + 目标描述 → 索引），
是类型化决策模型的标准形状，也是 M7 的确切瓶颈。REFLEX 的
"快层判断 + 低置信回退强模型"模式正好覆盖"既要快要准"的诉求。

### 4.3 风险与替代

1. **托管 API 的隐私/可用性/区域**：state 含界面文本（AX/DOM/OCR），
   敏感度低于整屏截图（后者已外发），但仍是新增外部依赖。必须
   opt-in profile + 审批口径更新 + 失败零重试（对齐现有 live 纪律）。
2. **开源复现未验证**：edgejev 路线的中文支持、与官方行为等价性
   未知；只作为本地实验臂，不作为采用前提。
3. **决策层不是替代规划器**：Jev 类模型不做长程规划、不读图、不
   生成动作序列；本方案里它只做 D1–D5 的闭集判断，规划仍由现有
   ChatAgent/子代理承担。
4. **规则基线先行**：D1/D4/D5 的多数信号是确定性的（进程名、端口
   可达性、候选计数、文本相似度）。规则实现（纯代码）是默认臂，
   决策模型臂必须在 S5 配对试验里赢过规则臂才可能被采用——
   对齐 M8 的"候选不优于基线即保留基线"纪律。

### 4.4 接口草案

`DecisionProvider` 协议（backend 内新模块，放 computer-use 工具层）：

```
decide(state: str | dict, questions: list[Question]) -> DecisionResult
Question  = Choice(options) | Scale(levels) | Noul()
DecisionResult = 每题答案 + 概率 + confidence + provider/model + usage
实现：RulesDecisionProvider（默认）· JevProvider（opt-in）· EdgeJevProvider（实验）
```

预算与可观测：决策调用以 `decision:` 前缀 call_id 记入现有
SubAgentContext budget / observe 事件流；hosted 调用纳入 SpendLedger
口径（usage 已知/unknown 同等待遇）。

## 5. 与现有架构的接缝

- **配置面**：agent frontmatter `grounding:` 扩展 `mode: "ladder"` 与
  `decision: {provider, profile}`；definition.py 校验；默认 agent
  不动，删键即回基线（与 M2/M4/M5/M7 相同的一键回退形状）。
- **会话层**：LocateSession 家族增加 LadderSession：把"单一 locate"
  泛化为"通道注册表 + 逐层尝试"，统一产出 LocatedTarget（observation
  + 点/元素引用 + provenance），pointer 派发路径复用 M2/M7。
- **证据面**：grounding_attempt/outcome/usage 事件增加 channel、
  provenance、latency_ms、fallback_chain 字段；benchmark 报告按层
  归因（每层尝试数/命中/降级原因），失败分类沿用 M6 口径。
- **依赖面**：`playwright`（python）与 OCR 引擎都进 optional extras，
  缺失时对应层自动不可用（降级），不阻塞 backend 启动。
- **测试面**：golden frame（复用 benchmark assets + 新增标注帧）
  支撑离线 OCR/匹配/排序测试；CDP 用 Playwright 自带 chromium 的
  本地实例；live 批次维持逐批授权、串行、独立评分。

## 6. 预期收益假设与反例（均待 S5 验证）

- **准确性**：L1/L2/L3 命中时消除"数值偏移"这一整类失败（引用元素，
  几何由宿主计算）。反例风险：选择错行（D2）、OCR 漏检、DOM 选择器
  未命中仍会失败——所以失败分类必须按层统计，不能合并宣称。
- **速度**：文本态通道 ~100ms 级 + 决策 ~16ms（本地）/ 0.1–0.8s
  （hosted）对比截图上传 + LLM 3–30s；每步平均延迟预期显著下降，
  但降级链本身有成本（最坏情况比单层更慢），需要 wall time 分布
  而非均值报告。
- **成本**：浏览器/文本任务 token 从图像计费转文本计费；历史图像
  重复上传（86 次/trial）在 L1–L3 命中时直接消失。
- **隐私**：命中上层通道时不再外发截图；新增的界面文本外发（仅
  hosted 决策/规划时）需在审批口径里明示。

## 7. 验证纪律（沿用 M0–M8）

1. 每层先离线（golden frame / mock CDP / 回放 fixture），后 live；
2. live 批次冻结材料与评分标准后才开跑，逐批授权、串行、零自动重试；
3. 配对臂：A（基线）vs L（阶梯+规则）vs L+决策模型；同模型同参数，
   每次只改一个因素；按任务配对报告 strict/wall/token/错点分类；
4. 采用门槛：L 或 L+J 在宽任务集上**严格优于** A 且成本不升，才切
   默认；否则保留基线并把发现归档（M8 同款收口）。

## 8. 结论与建议顺序

1. 先落规则路由 + 本地定位器（S0–S3）：不新增外部依赖即可拿到
   L1–L3 的主要收益，且全部离线可测；
2. 决策模型作为增强臂（S4）：先本地 edgejev/规则对照，hosted Jev
   在隐私审批通过后进配对试验；D2（候选选择）是最高价值切入点；
3. live 配对验收（S5）与采用决定（S6）按 M0–M8 纪律执行；
4. 本调研不宣称任何通道在 Tank 上必然有效，全部结论以 S1/S5 实测
   为准；原生协议/UI-TARS 专用定位模型仍留在
   [backlog](../backlog.md) 原触发条件下。
