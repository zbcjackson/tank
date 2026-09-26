> 日期：2026-09-26（同日复核修订）。结论状态：调研完成，收益仍待验证；方案与实施计划见
> [策略阶梯计划](../plans/active/computer-use-strategy-ladder.md)；
> 新增阶梯、DOM/OCR 与决策模型方案均未实现、未实机验证；既有 AX 等资产另有历史证据。
> 外部机制描述不构成在 Tank 上的效果承诺。

# Computer use 多策略执行阶梯与决策层调研

本轮复核将“固定四层降级 + 全量决策模型”收敛为“按能力与动作路由 + 规则先行 +
条件性 D2 实验”。以下同步修正证据和技术边界；详细数据契约、UML、恢复规则、
预算与阶段退出条件以[修订计划](../plans/active/computer-use-strategy-ladder.md)为准。

## 1. 问题定义：为什么继续优化"模型报数字"收益有限

当前生产基线 A（一体规划定位 + legacy 归一化坐标，qwen3.7-flash）的
全部已知证据见 [现行设计](../design/computer-use.md) 与
[M8 收口报告](../../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)。
约束它的四个事实：

1. **数值定位与歧义拒绝是已确认问题，但不能解释全部任务失败。** M3 holdout 上
   qwen3.7 正例仅 57/96；GPT-5.5 point/bbox 正例 96/96 但同名歧义拒绝 0/16；
   M5 接口矩阵证明单位匹配模型原生习惯是关键因子，强模型使单位问题消失。
   归因止于服务输出边界（I11 保持 unknown）。M6 宽任务集仍有流程未完成与预算失败，
   不能把定位精度提升直接等同于任务成功率提升。
2. **全截图输入的成本与延迟是结构性负担。** 每个 observe→act 循环都上传
   整屏 PNG；单 trial 的 11 个图像哈希累计出现 86 次；live trial wall
   20.6–126.3 s。Tank 是语音助手，用户在实时等待。
3. **AX 机制闭环成立，但选择精度是瓶颈。** M7 live3：宿主绑定→枚举→
   文本选择→派发→独立评分全部走通并拿到 strict 通过；qwen3.7-flash
   选择器在 57 行候选里反复 off-by-one / 误选 All Clear；AX 臂 token
   成本反而更高（245k vs 181k）。
4. **结构化信息一直存在于模型输入之外。** 浏览器有 DOM，原生应用有 AX
   树，屏幕文字可以用本地 OCR 读出。这些通道不依赖模型估计数字，却
   在基线 A 里完全没有被用作定位来源。

因此本调研的核心转向是：**与其让模型输出更准的坐标，不如让大多数动作
根本不经过模型坐标估计**。截图点击保留为视觉通道（L4），上层通道以
"元素引用 + 宿主几何计算"替代数值定位。这与
[外部实现对照](computer-use-implementation-comparison.md) 中 Peekaboo /
Cua / browser-use 的结论一致：坐标是兜底，语义引用是主路。

## 2. 策略阶梯总览

按能力、目标类型和动作选择通道；DOM/AX 的语义引用通常优先，但结构化结果也可能
选错目标。无文字图标可直接视觉定位，已确认焦点的输入可直接走键盘工具。
下列成本/速度是机制假设，不是 Tank 实测保证：

| 层级 | 通道 | 定位介质 | 输入成本 | 延迟量级 | 覆盖范围 | 主要失败模式 |
|---|---|---|---|---|---|---|
| L1 | 浏览器 DOM（Playwright） | role/text locator、原生引用 | 文本观察 | 待 S2/S5 实测 | 首期 Tank 管理 Chromium | 目标多义、动态重渲染、遮挡 |
| L2 | AX 语义寻址（复用 M7） | 稳定 id + 元素引用 | 文本观察 | 本地枚举；选择调用可省 | 有 AX 树的原生应用 | 自绘控件、AX 缺失、选择错误 |
| L3 | OCR 文本区域 | OCR 框 + 文本上下文 | 本地图像推理 | 待 Mac golden set 实测 | 文字目标的候选来源 | 孤立数字/小字漏检、文字不等于控件 |
| L4 | 视觉定位（GroundingAdapter 接缝） | 模型输出图像点 | 按需上传图像 | 取决于 provider 与请求 | 其它可见目标，效果待验收 | 坐标、歧义、权限与预算 |

三条硬边界沿用现有纪律：

- **恢复有条件**：未派发的 not_found/unavailable 可换通道；歧义先补证据，
  过期引用重观察，可能已派发的未知结果只读核实。视觉不是保证成功/可用的兜底。
  通道尝试与全步重定位共享预算，四通道访问不能等同于旧模式一次后备切换。
- **统一执行约束**：DOM 语义动作和 Quartz/AX 走不同执行后端，但都须接入同一套
  授权、预算、停止/取消和清理约束；不能声称现有机制无需改动就已覆盖。
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
这限制了默认 profile 的调试端口路线，不代表所有浏览器集成路线都被禁止。
可行形态及首期边界：

1. **Tank 管理的浏览器实例**：由 Playwright 创建并持有 page/context 身份，
   与用户 profile 隔离；首期从本地确定性任务开始，登录态不会自动继承；
2. **已有浏览器/第二 profile 附着**：有明确需求与授权连接时再做；当前登录态
   无 DOM 接口时保留 AX/OCR/视觉，不默默迁移任务；
3. **Safari**：其 safaridriver 是另一条自动化路径，需要独立调研与授权配置，
   不套用本计划的 Chromium 设计，不进首期；
4. **Playwright 自带 chromium**：测试与 benchmark 的确定性环境，
   不依赖用户浏览器。

**页面身份**。首期依赖创建时的 browser/context/page/frame 身份，不靠 url/title
猜测窗口归属。同 URL 多标签页、导航代次和 frame 作用域均需测试；用户窗口
附着后置，不能把可连接当作已授权。

**派发选择**。首期只用 `locator.click/fill` 等语义操作，保留 Playwright 的
唯一性、可见性、稳定性及动作适用检查（具体检查依动作而异，见
[actionability](https://playwright.dev/python/docs/actionability)）。不先退化为
CDP Input 坐标或引入第二条 Quartz 映射；将来有已归因需求再比较。
动作成功返回仍不等于业务效果达成，需要独立读回后置条件。

**收益假设**。浏览器任务是高频用户场景（benchmark 已有
03-browser-navigate、10-links-history，但有 Safari 环境假设，需另建 Chromium revision）；
只有规划、反馈和历史序列化都采用文本观察时，才可能减少整步图像上传。
本地 locator 速度不能代表含规划/等待/核验的完整步骤延迟。
失败分类必须单列：选择器未命中、跨域 iframe、动态重渲染、
映射歧义（[OmniParser 教训](computer-use-implementation-comparison.md)：
漏检/选错/框不可点要分别统计）。

### 3.2 L2 AX 语义寻址（复用 M7，修选择瓶颈）

M7 已交付：候选枚举（`ax_window_candidates`）、绑定帧校验、
quartz/ax_press 双派发、AX 独立评分。已观察到的选择瓶颈是"57 行列表里选行"，
不能据此排除枚举覆盖、歧义、引用新鲜度及长任务规划问题。
本计划内的改进（不改变机制）：

1. **确定性预排序截断**：按 target 与 title/value/identifier 的文本
   相似度（difflib，中文按字符/bigram）排序取 top-k（如 k=12），
   唯一精确匹配须在原作用域内确认并保留截断信息；top-k 唯一不能代替原集合唯一。
   用稳定 id 代替可变行号；列表缩短是否改善选择须独立测量。
2. **候选呈现增强**：候选附带祖先分组标签（如 "Basic → 数字区"），
   复用现有 `AXCandidate` 结构加一个 group 字段。
3. **焦点感知**：读 `AXFocusedUIElement` / `AXSelectedText`，作为
   动作前上下文与动作后核验信号（类型输入是否落到焦点元素）。
4. **选择器换执行体**：从 qwen3.7-flash 生成式调用改为
   §4 的条件性类型化决策调用（文本进、稳定 id/none/ambiguous 出）；是否替换以对照结果为准。这是 M7 backlog
   触发条件中"列表呈现改进方案"的直接落点。

### 3.3 L3 OCR 文本区域

**引擎选型**。macOS 自带 Vision 框架（`VNRecognizeTextRequest`，
pyobjc 惰性加载，候选语言 zh-Hans/en-US）为首期唯一预检后端；绑定仍是依赖，
语言可用性和中文效果须在目标 macOS 验证。RapidOCR 仅在 Vision 不达标且有
明确补益时再做。Vision 的 boundingBox 是归一化左下原点，
需翻转到现有图像坐标（AX 已有同类 flip 处理先例）。

**定位管线**：截图（复用 Observation 语义，含 crop/缩放元数据）→
OCR 文本框 → 与 target 描述/上下文匹配 → 验证文字与可执行目标的关系 →
确定目标后经 `map_point` 走 M2 图像像素→全局点路径。多命中进入候选消歧；
视觉可补证据，但不能直接忽略 OCR 已揭示的歧义。

**AX/OCR 候选关系**：首期分别保留 provenance，不按 IoU 直接合并控件和文字。
孤立数字已有 OCR 失败观察，Calculator 覆盖不能预设为良好；须进入 golden set。
图标无文字时可直接视觉定位，不必为验证已知限制浪费一遍 OCR。

**已知边界**：OCR 文本本身不是业务效果证据；美术字、低对比、canvas 渲染
文字、密集小字（M3 合成图里的小目标）可能漏检。S1 用 golden frame
先测召回/精度，不预设 Vision OCR 在本项目布局上的表现。

### 3.4 L4 视觉定位兜底

基线 A 保持独立且不变；阶梯 L4 从 `GroundingAdapter`/拆分定位接缝复用能力，
不能把完整的一体 agent A 当作一个定位函数嵌套。统一内部 image/frame 与模型
外部协议继续分离。L4 可以是适用的起点，也可以是未派发前的备选；其失败分类、
单位习惯与预算仍需观测，不能承诺覆盖所有可见目标。

## 4. 决策层：Jev 类类型化决策模型

### 4.1 Jev 是什么（外部事实，带来源）

截至本次调研，TypeSafe AI 的 Jev 提供 `state` + `questions` 映射的类型化决策 API，
原语为 Choice/Score/Noul。官方端点是 `https://api.typesafe.ai/v1/systemone`；
实验须固定模型版本，不能使用滚动 `latest` 作为可复现标识。来源以
[官方 API](https://docs.typesafe.ai/api) 为准；
[jevai.org](https://www.jevai.org/docs) 是社区包装文档，不可把它的 `/api/v1/decisions`
误当官方协议。

[confidence 文档](https://docs.typesafe.ai/confidence)描述的是模型分布统计，
不能直接解释为 Tank 候选选择正确率；Noul 没有单独 confidence。类型合法不代表
答案正确，也不能过滤所有恶意界面指令；还须遵守
[官方能力边界](https://docs.typesafe.ai/model-jaggedness/jev-1.13)。
价格、可用区域与部署细节在实际启用 S4 前重新核对，本页不作为预算报价。

与本需求直接相关的两份外部证据：

- **REFLEX**（[arXiv 2609.26532](https://arxiv.org/abs/2609.26532)）：
  agent 架构把 Jev 作为快速类型化决策层，低置信度或需生成时才调用
  强 LLM；冻结 100 任务基准上 95% 成功率、强模型调用减少 72.7%。这些结果不是
  Tank 桌面任务证据；对外部评测中的便宜生成式级联，其优势有限，不能跳过同候选集对照。
- **开源复现生态**：laya / kev / PlayJev 等复现可经
  [edgejev](https://pypi.org/project/edgejev/) 使用不同运行时；不能全部概括为 ONNX，
  PlayJev 有 PyTorch 路径。其 15.6ms 报告来自 Intel Xeon/AVX512-VNNI 环境，
  不是 Apple Silicon 实测。复现与官方的等价性、中文表现及 Mac 冷/热延迟均待验证。

### 4.2 与 Tank 的契合点：五个决策位

computer use 有若干闭集判断，部分可由规则解决，部分值得模型实验：

| 编号 | 决策位 | 原语 | 现状 | 决策层形态 |
|---|---|---|---|---|
| D1 | 本步用哪条通道 | 可表达为 Choice | 尚无多通道路由 | 能力/动作规则先行；模型化延期 |
| D2 | 候选稳定 id / none / ambiguous | Choice | M7 已观察到选择错行 | 同 shortlist 对照，单独校准拒绝阈值 |
| D3 | 动作后效果是否达成 | 三态结果，不能只用二值 | 模型反馈与独立评分不同 | 确定性后置条件先行，不确定时才辅助解释 |
| D4 | 是否继续/补证据/停止 | 规则状态机 | 旧模式已有尝试与后备上限 | 按结果类型和预算恢复，不以跨层 confidence 统一阈值替代 |
| D5 | 序列是否可 batch | 规则门控 | M6 已有 batch 对照 | 每项检查和回执，副作用/布局变化边界拆开 |

**关键洞察：D2 可以是纯文本任务**（候选列表 + 目标描述 → 稳定 id），
与 M7 已观察到的瓶颈直接相关。只有候选已包含目标而选择仍困难时，才值得启动
类型化 selector 对照；低置信回规划器也有成本，须计入共享预算。

### 4.3 风险与替代

1. **托管 API 的隐私/可用性/区域**：state 含界面文本（AX/DOM/OCR），
   不天然比截图低敏感，也不因已有 provider 接收截图而自动允许新 provider 接收文本。
   必须 opt-in profile、明确目的地/数据范围、失败零重试（对齐现有 live 纪律）。
2. **开源复现未验证**：edgejev 路线的中文支持、与官方行为等价性
   未知；只作为本地实验臂，不作为采用前提。
3. **决策层不是替代规划器**：Jev 类模型不做长程规划、不读图、不
   生成动作序列；首期实验只做 D2，规划仍由现有 agent/子代理承担。
4. **规则基线先行**：D1/D4/D5 的多数信号是确定性的（进程名、端口
   可达性、候选计数、文本相似度）。规则实现（纯代码）是默认臂，
   决策模型臂必须在 S5 配对试验里赢过规则臂才可能被采用——
   对齐 M8 的"候选不优于基线即保留基线"纪律。

### 4.4 接口与记账边界

S0 先定义候选选择结果，不提前交付通用 D1–D5 Question 框架：

```
select(target, scoped_candidates) -> candidate_id | none | ambiguous
元数据：scope/version/completeness、provider/model、可选且按类型定义的统计量、usage
默认规则；只有 S4 触发时增加 hosted 或一个本地 selector
```

`decision:` call_id 是关联标识，不等于已实现计费。Jev 的请求/usage 与现有
Chat Completions 不同，须补真实 HTTP allowlist、input/output token 适配、
reserve/settle 与 unknown 保留预留/停批；所有规划/定位/决策调用共享任务上限。

## 5. 与现有架构的接缝

- **配置面**：agent frontmatter opt-in `mode: "ladder"`，默认规则、hosted 关闭；
  definition.py 按能力校验。删配置仅对新会话生效，须先停止并清理旧会话。
- **会话层**：LocateSession 家族增加 LadderSession：把"单一 locate"
  泛化为能力路由与恢复状态机；typed refs 保留 DOM/AX/图像的不同身份，
  定位、派发和核验分离，pointer 路径复用 M2/M7。
- **证据面**：grounding_attempt/outcome/usage 事件增加 channel、
  provenance、latency_ms、fallback_chain 字段；benchmark 报告按层
  归因（每层尝试数/命中/降级原因），失败分类沿用 M6 口径。
- **观察面**：文本反馈与本地图像留档分开；按需上传视觉证据，并测试 SDK 历史中的图像，
  避免上层命中却仍被固定截图反馈抵消收益。
- **依赖面**：`playwright`（python）与 OCR 绑定都进 optional extras，
  缺失时对应层自动不可用（降级），不阻塞 backend 启动。
- **测试面**：golden frame（复用 benchmark assets + 新增标注帧）
  支撑离线 OCR/匹配/排序测试；CDP 用 Playwright 自带 chromium 的
  本地实例；live 批次维持逐批授权、串行、独立评分。

## 6. 预期收益假设与反例（均待 S5 验证）

- **准确性**：减少模型坐标估计，但错误候选、陈旧引用、OCR 文字与控件不一致、
  规划失败仍可能造成误操作。分别报告定位、选择、执行和任务完成。
- **速度**：可能省视觉调用，也可能因多通道尝试和核验更慢；测完整 wall、阶段耗时、
  请求数和冷/热启动，不把单题 CPU benchmark 当作端到端指标。
- **成本**：文本观察与历史策略可能减少图像请求；只有真实 SDK 请求验证后才能声称
  重复图像减少。token、请求数与货币费用分开报告，未计价部分不可宣称费用下降。
- **隐私**：按需减少截图外发是设计目标；文本外发仍按接收方和内容单独界定范围。

## 7. 验证纪律（沿用 M0–M8）

1. 每层先离线（golden frame / mock CDP / 回放 fixture），后 live；
2. live 批次冻结材料与评分标准后才开跑，逐批授权、串行、零自动重试；
3. 配对臂：A（冻结基线）、V（新阶梯仅视觉）、L（规则阶梯）、L+D（只换 D2）。
   A vs L 是系统比较，不能声称只有 selector 一个因素；跨浏览器先统一 suite revision；
4. n≥3 只是 pilot。确认性指标、样本/区间方法和采用界限先冻结；独立 validator
   评分，全部失败/unknown/清理异常进入分母；可逐场景采用，不强求全局优胜；
5. 本计划给采用建议，生产默认保持不变。实际切换由后续明确变更实施。

## 8. 结论与建议顺序

1. S0–S3 先冻结契约和 SDK 观察链，再做 AX/单一 OCR、受控 Chromium 和规则阶梯；
   本地机制可离线验证，真实任务收益与停止效果仍需授权 pilot，不能预设；
2. S4 仅在候选选择有已归因瓶颈时触发，同 shortlist 比规则、生成式小模型及一个
   hosted 或本地 selector；新模型不优于便宜基线就不采用；
3. live 配对验收（S5）与采用决定（S6）按 M0–M8 纪律执行；
4. 本调研不宣称任何通道在 Tank 上必然有效，全部结论以 S1/S5 实测
   为准；原生协议/UI-TARS 专用定位模型仍留在
   [backlog](../backlog.md) 原触发条件下。
