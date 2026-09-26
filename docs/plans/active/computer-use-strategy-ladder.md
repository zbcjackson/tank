> 状态：进行中（2026-09-26 立项，S0–S6 见 §4，尚未开工）。生产默认 agent
> 全程不动；所有新能力均为 frontmatter 显式 opt-in，删键即回基线。

# 计划：computer-use 策略阶梯与决策层（S0–S6）

## 1. 目标与范围

把桌面操作从"每步截图 + 模型报坐标"的单通道，改造为
**DOM → AX → OCR → 视觉兜底**的策略阶梯，并引入 Jev 类类型化决策层
做通道选择、候选选择、效果核验与降级控制，提升有效性、准确性与速度。
截图点击降为最终兜底。技术论证见
[策略阶梯调研](../../research/computer-use-strategy-ladder.md)。

**目标**：

1. L1–L3 三条结构化通道可独立离线测试，live 下经独立评分验收；
2. 阶梯路由（规则基线）端到端可用，降级链有步数预算与完整归因；
3. 决策层（规则/Jev hosted/edgejev 本地）接口统一，预算与观测接入；
4. 配对 benchmark 给出 A vs L vs L+D 的采用决定，口径对齐 M6/M8。

**非目标**（维持 backlog 触发条件，不在本计划内做）：

- 原生协议（Responses computer、UI-TARS 专用定位模型）；
- Linux X11/Wayland adapter、动态几何/高频压测扩展验收；
- N2/SDK 路径改动；子代理链路历史压缩（独立 backlog 条目）；
- Safari safaridriver 通道（首期仅记录接口调研结论）。

**硬约束**：生产默认 `computer_use` agent 与基线 A 的提示、工具面、
评分 revision 全程不变；新能力全部经 `grounding.mode: "ladder"` 类
frontmatter 显式启用。

## 2. 触发的 backlog 条目与历史核对

本计划由用户 2026-09-26 直接要求立项，触发并收编以下 backlog 条目
（已从 [backlog](../../backlog.md) 移出）：

- **OCR/控件检测 + 编号方案预检**（原触发：AX 不满足需求或纯视觉在
  密集小目标场景成为主要失败源）→ S1 落地 OCR 候选 + 编号选择。
- **AX 语义寻址选择模型复验**（原触发：更强选择模型或列表呈现改进
  方案 + 新实验预算）→ S1 落地列表预排序/呈现改进，S4 落地类型化
  决策选择器，S5 提供新实验预算框架（逐批授权）。

依赖的既有资产与结论（不重做）：

- M2 Observation/image 坐标与宿主逆映射（`map_point` 路径）；
- M7 AX 枚举/绑定/派发与独立评分（`computer_ax.py`）；
- M3 GroundingAdapter 协议族与失败分类口径；
- M6 停止/取消/清理验收框架与 benchmark 配对纪律；
- SpendLedger 预算与 SubAgentContext 观测事件流。

## 3. 架构设计

### 3.1 模块布局（backend/core/src/tank_backend/）

```
tools/computer_ladder.py     # LadderSession：通道注册表 + 降级链 + 统一 LocatedTarget
tools/computer_ocr.py        # Vision/RapidOCR 包装 + 文本匹配 + 候选框
tools/computer_dom.py        # CDP 附着/窗口映射/DOM 定位器/派发/读数
decision/provider.py         # DecisionProvider 协议 + Question/DecisionResult 类型
decision/rules.py            # RulesDecisionProvider（默认，纯代码）
decision/jev.py              # JevProvider（hosted，opt-in）/ EdgeJevProvider（实验）
```

AX 预排序与候选合并不新开模块：扩展 `computer_ax.py`（排序/分组）与
`computer_ocr.py`（合并去重、provenance）。

### 3.2 配置面

`GroundingConfig` 扩展（`agents/definition.py`）：

```yaml
grounding:
  mode: ladder            # 新增枚举值；校验规则与 split/ax 并列
  decision:
    provider: rules       # rules | jev | edgejev
    profile: jev-profile  # provider=jev 时的决策 profile 名（新配置节）
  ladder:                 # 可选覆盖，默认全开
    channels: [dom, ax, ocr, vision]
```

约束：`decision.provider` 非 `rules` 时要求 profile 存在；mode=ladder
要求 macOS screenshot 工具在 toolset 内（与 split 同款校验）。

### 3.3 执行语义

- **通道接口**：每个通道实现
  `locate(observation, target) -> ChannelResult(found|not_found|ambiguous,
  candidates?, point?, provenance, confidence)`；
  L1 额外自带派发与核验（CDP），L2/L3 产出图像点走 M2 派发，
  L4 复用 GroundingAdapter。
- **降级链**：D1 选起点（默认顺序 dom→ax→ocr→vision）；单层
  not_found/ambiguous/派发错误/核验失败 → 记录原因 → 下一层；
  每动作步至多一遍链 + 至多两次同层重试（复用现有 attempts 语义），
  超出即停止并报告，不盲目重放。
- **决策位接入**：D1 起点/跳层、D2 候选选择、D3 文本态效果核验、
  D4 置信门控、D5 batch 判断（§4 S0 定义问题 schema）。规则 provider
  的置信度来自确定性信号；模型 provider 低置信 → 回退规划模型决策，
  对齐 REFLEX 门控形态。
- **观测/预算**：`decision:*` call_id 计入 budget；grounding 事件增加
  channel/provenance/latency_ms/fallback_chain/verification 字段；
  hosted 决策调用 usage unknown 时按现有 unknown 口径停批。

### 3.4 安全与依赖

- `playwright`、OCR 引擎进 `backend/core` optional extras；缺失时对应
  通道报不可用并降级，不影响启动；
- CDP 附着仅限 localhost 显式配置端口；Tank 管理实例使用独立
  user-data-dir（Chrome ≥136 约束）；不读取浏览器凭据/cookie 存储，
  不注入脚本到页面（只读快照 + Input 派发 + 元素操作）；
- 浏览器通道动作沿用 computer 工具类别的审批策略；hosted 决策 API
  外发界面文本需在审批口径中明示并默认关闭。

## 4. 里程碑

每个里程碑"先测试后实现"（TDD），完成即提交；live 批次独立于里程碑
代码完成度，按 §8 授权节奏执行。

### S0 决策接口与规则基线（纯代码，无模型调用）

- 定义 Question/DecisionResult 类型与 DecisionProvider 协议；
- RulesDecisionProvider 实现 D1/D4/D5 的确定性信号版（D2 规则 =
  唯一匹配直取、多匹配置 ambiguous）；
- 事件/预算接线（decision:* call_id）与配置面校验（mode=ladder）；
- **验证**：单测覆盖 schema 校验、规则路由真值表、预算记账；
  `uv run pytest`、ruff、pyright 全绿。

### S1 本地定位器：OCR + AX 候选改进（离线，无桌面动作、无模型调用）

- `computer_ocr.py`：Vision（pyobjc 惰性加载，zh+en）与 RapidOCR
  双后端；归一化框→图像坐标翻转；difflib 文本匹配（中文字符级）；
  top-k 候选 + provenance；AX/OCR 候选 IoU 合并；
- `computer_ax.py`：候选预排序（top-k）+ 祖先分组标签 + 焦点读取
  （AXFocusedUIElement）；
- 标注 golden frame 集（复用 benchmark assets + 新增含中文/密集小字/
  图标混合帧，人工标注文本框与目标）；
- **验证**：离线指标——OCR 召回/精度（按帧分组报告）、匹配 top-k
  命中率、AX 排序后目标进入 top-k 的比率；阈值先冻结后看结果
  （M0 纪律）。全部为本地推理，不产生 API 费用。

### S2 浏览器通道（本地确定性环境）

- `computer_dom.py`：CDP 探测/附着（connect_over_cdp）、窗口↔target
  映射（title/url 匹配，歧义拒绝）、getByRole/getByText 定位、
  bounding_box 读取；
- 派发双路径：CDP Input（默认）与 box→全局坐标→M2 Quartz（对照），
  可配置切换；
- 效果核验：DOM/aria 读数 diff（文本态）；页面快照文本给规划器
  （替代截图的消息形态）；
- **验证**：Playwright 自带 chromium 本地实例的集成测试（点击/填写/
  导航/读数/跨域 iframe 拒绝/端口不可达降级）；CDP mock 单测；
  不触碰用户日常浏览器 profile。

### S3 阶梯执行引擎（路由 v1 = 规则决策）

- `computer_ladder.py`：LadderSession + 通道注册表 + 降级链 + 统一
  LocatedTarget；runner 接线（mode=ladder 时替换会话类，复用 M4 生命
  周期/取消/反馈框架）；缺通道自动降级；
- 停止/取消/预算复用现有 SubAgentContext 与 stop-acceptance 用例；
- **验证**：mock 通道的降级链单测（每层失败组合、步数预算、事件字段
  完整性）；全量 backend 测试回归；dev server 冒烟无错。

### S4 决策模型臂

- JevProvider（hosted `/v1/systemone`，opt-in profile，零自动重试，
  usage 记账）与 EdgeJevProvider（本地 ONNX，实验 extras）；
- D2 候选选择接入（top-k 列表 → Choice）；D1/D3/D4/D5 问题 schema
  固化；低置信回退规划模型；
- 离线回放：用 S1–S3 遥测构造决策数据集（候选列表 + 事后独立评分
  真值），先离线测决策准确率再上 live；
- **验证**：fake provider 单测（协议解析/错误分类/预算）；隐私与
  审批口径更新评审通过后才允许 hosted live。

### S5 live 配对 benchmark

- suite 扩展任务：浏览器任务（本地 chromium 固定页 + 需登录态的
  Tank 管理 profile 任务单列授权）、文本密集任务、图标-only
  强制降级任务、中文界面任务；
- 臂：A（基线）/ L（阶梯+规则）/ L+D（阶梯+决策模型）；同模型同参数，
  轮转先手，每任务 n≥3；独立 validator（AX/DOM/文件系统证据）；
- 报告：strict 通过率、wall 分布（p50/p95）、token、逐层归因
  （尝试数/命中/降级原因/核验结果）、错点分类（沿用 M6 口径）；
- **验证**：批次冻结链（材料预检→授权→串行执行→报告归档），
  零自动重试，清理失败分母明示。

### S6 采用决定与关档

- 若 L 或 L+D 在宽任务集严格优于 A 且成本不升：切默认（frontmatter
  一处改动）并保留一键回退；否则保留基线、归档发现；
- 更新 [design/computer-use.md](../../design/computer-use.md)（新增
  阶梯章节）、本计划状态行、README 索引；未决项移交 backlog。

## 5. Tests

新增测试（`backend/core/tests/`）：

- `test_decision_provider.py`：Question schema 校验、规则真值表
  （D1/D2/D4/D5 各信号组合）、DecisionResult 解析与拒收、预算记账、
  fake hosted provider 的协议/错误/usage-unknown 路径；
- `test_computer_ocr.py`：golden frame 召回/精度（按帧分组断言阈值）、
  坐标翻转、匹配唯一/多义/未命中、AX+OCR 合并去重、provenance；
- `test_computer_ax.py` 扩展：预排序 top-k、分组标签、焦点读取、
  排序不泄漏评分真值；
- `test_computer_dom.py`：CDP mock（附着/映射/歧义拒绝/不可达降级）、
  Playwright chromium 集成（标记 skip-if-no-playwright）、双派发路径
  落点一致性；
- `test_computer_ladder.py`：降级链组合矩阵、步数预算、LocatedTarget
  统一性、事件字段完整性、取消/停止复用用例；
- 配置面：`grounding.mode=ladder` 校验、缺 decision profile 拒绝、
  删键回退；
- E2E：`test/` 增加一个阶梯模式浏览器场景（backend+frontend 起服后
  可跑，不依赖用户桌面）。

既有测试全部保持绿色；legacy A 路径的字节级兼容用例不修改。

## 6. 验证清单（最终步骤，逐项执行）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check src/ tests/`
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <改动文件>`（禁止 `# type: ignore`）
6. `cd cli && uv run ruff check src/ tests/`
7. dev server 检查：`tmux capture-pane -t tank -p -S -50 | grep -i
   "error\|traceback\|exception"`（空输出即通过，不重试）
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`

本立项为纯文档变更，仅执行第 9 项；S0 起每个代码里程碑执行全部
适用项。

## 7. 风险与回退

| 风险 | 缓解 |
|---|---|
| Chrome ≥136 禁止默认 profile CDP | Tank 管理实例 + 独立 user-data-dir；登录态任务单独授权通道 |
| OCR 在密集小字/美术字召回不足 | S1 golden frame 先冻结阈值；不达标则 ocr 层仅作辅助候选源，不阻塞阶梯 |
| AX 预排序把目标挤出 top-k | k 可配 + 精确匹配直通 + 排序命中率进 S1 指标；失败样本归档 |
| 决策层引入新外部依赖与隐私面 | 规则 provider 为默认；hosted 默认关闭、审批明示、零重试、usage 记账 |
| 降级链最坏情况比单通道更慢 | 每步一遍链上限；wall 分布（非均值）进 S5 报告；per-layer 超时 |
| 阶梯与既有 split/ax 模式状态纠缠 | LadderSession 独立会话类；M2/M7 路径不动，回归全量跑 |
| benchmark 候选泄漏真值 | 候选仅来自当次观察；材料冻结链与 M7 同款审查 |

回退：生产默认 agent 无 `grounding:` 键，行为与今日完全一致；任何
opt-in 配置删 `grounding` 键即回基线 A（与 M2/M4/M5/M7 同形状）。

## 8. 预算与授权边界

- S0–S4 以离线测试与本地推理为主，API 费用为零；hosted Jev 仅在
  S4 隐私评审通过后、以独立 profile 进入；
- S5 live 批次沿用现行纪律：材料冻结 → 用户逐批授权（含 initial
  状态复核）→ 串行执行 → 零自动重试 → record-only 计价入报告；
- 决策调用与定位调用同口径计入 trial 预算；usage unknown 停批规则
  不变；总消耗在 S6 收口报告中按批列出。
