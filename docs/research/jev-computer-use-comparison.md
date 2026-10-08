# Jev 开源 Computer Use 方案与 Tank S4 对比

> 日期：2026-10-08。状态：源码对比完成；改进假设待对照实验验证。

## 范围与结论

用户要求研究三个指定项目，解释其 Jev 操作机制，并诊断 Tank 当前原生任务的阻塞。
本次只下载公开源码、阅读代码和已提交的证据，未安装或执行这些项目，未操作桌面、
未调用付费模型。Tank 对比对象是 `agent-computer-use` 的 S4 宿主循环，而非所有旧版
computer-use 工具。未修改生产代码或已有试验结果。

固定源码版本：

- [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast/tree/1231850a0bf1a0c0341fe408ef1668dbbfdfac46)：`1231850a0bf1a0c0341fe408ef1668dbbfdfac46`。
- [stoopid-computers/jev-bot](https://github.com/stoopid-computers/jev-bot/tree/d4be4a3bffe22704a1a9adc49ac044c61e9ee673)：`d4be4a3bffe22704a1a9adc49ac044c61e9ee673`。
- [awlevin/typesafe-computer-use](https://github.com/awlevin/typesafe-computer-use/tree/44ca11f0935b021b73020825da054b5c92cc1288)：`44ca11f0935b021b73020825da054b5c92cc1288`。
- Tank：本次研究起点 `7fa3784f`，依据 [S4 原生双模型实测](../../backend/benchmarks/computer_use/reports/20261008-s4-native-advisor/README.md)。

三者共享“确定性观察 → 有限选项 → Jev 分类 → 确定性执行 → 新观察”的基础，
但规划责任不同。并非所有成功方案都先让大模型规划：ultrafast 的 Jev 直接接整体目标；
jev-bot 通常由外层代理给出明确操作或有界小任务；awlevin 的 Jev 接整体目标，停止后
由更强模型提供下一步 focus，再交回 Jev。不能把这三种路径混为“Jev 只做定位”。

对 Tank，最明确的设计缺口是**可读动作历史、可持续的规划指导，以及不确定性到规划层的
交接**。模型视图中的重复执行元数据也值得压缩。它们是有源码依据的改进方向，尚不是
第二次 Calculator 失败的已证实根因；不能声称照搬就能通过。

## 1. jev-ultrafast：Jev 直接推进整体网页目标

`Agent` 每轮读取浏览器状态，调用 `choose(page, goal, history)`，执行后再次观察。
Jev 选择操作类型和目标；额外文本模型只在 TYPE_TEXT 时为已选字段生成文字，不负责
每一步规划。循环记录动作名称、类型、输入文字及页面是否变化，模型读取最近十条。
见 [agent.py](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/agent.py#L70)。

核心区别在模型接口：一个请求包含 `operation`，以及按能力生成的 `click_target`、
`type_text_target`、`select_target` 等多个 Choice。它们共享观察，目标问题是条件式的
预测；只有所选操作对应的目标答案可执行，并非先收到操作答案再发第二次请求。
目标以短数字索引表示，宿主映射回实际 DOM 动作。模型状态主要是页面 URL、标题、
可见文本、精简元素表和近期历史，不发送原始 DOM。
见 [model.py](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/model.py#L44)。

提示明确指导“推进整个目标”、利用当前值和历史、不要重复已满足步骤、输入后还需选择
自动完成建议、全部需求有可见证据才 DONE。它承担的是下一步选择，不只是字符串匹配。
见 [questions.py](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/questions.py#L3)。

观察通过一次浏览器调用生成元素与可见文本，最多保留约 6000 字符的页面文本。
执行前检查当前文档、控件语义与附近上下文，再解析当前位置并检查遮挡；输入后有短暂
稳定等待。默认模型不收截图。
见 [snapshot.js](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/snapshot.js)、
[browser.py](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/browser.py#L88)。

证据边界：其报告是同一 Flights 任务的三对交替试验，两组各 3/3；另有 Wikipedia 和
本地 fixture smoke。库内 DONE 仍是模型判断，示例另外独立验收。它不证明任意网页、
macOS 原生或我们的算式任务已解决。
见 [performance.md](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/docs/performance.md)。

## 2. jev-bot：外层代理规划，Jev 做有界原生操作

这是带持久 JavaScript 会话的 MCP 工具层。外层 Codex/ChatGPT 代理发现应用、检查 AX
或截图，并决定调用什么。`app.click(编号)` 不调用 Jev；`app.click("Submit button")`
将描述包装为明确点击目标，只允许 click、最多一步。字符串 `setValue` 同样限定一步，
文字由调用者提供。`app.act(goal, options)` 才进入多步小循环，默认四步、范围 1–8。
见 [repl.ts](https://github.com/stoopid-computers/jev-bot/blob/d4be4a3bffe22704a1a9adc49ac044c61e9ee673/src/repl.ts#L450)。

候选用 `action_1` 等本轮短 ID，对应完整 NativeAction。只提供支持且启用的原生操作，
排除安全字段和 web 内容；另有 reobserve、handoff、done。宿主默认置信度门槛 0.7，
不足时交还外层，默认值本身不构成准确率保证。每次尝试后重读，执行未知不重复，
无可见变化交还外层。只有显式 `expect` 命中才返回 verified，模型 done 返回 handoff。
见 [engine.ts](https://github.com/stoopid-computers/jev-bot/blob/d4be4a3bffe22704a1a9adc49ac044c61e9ee673/src/engine.ts#L199)。

发给 Jev 的是 goal、应用/窗口、元素 index/role/label/value/enabled/actions，以及最近
八条本次 run 记录。注意，这里的历史记录主要是 step、snapshotId、selectedId、kind、
outcome 和 receipt，**不能描述成完善的语义动作历史**；跨工具调用的任务记忆主要仍由
外层代理承担。Jev 默认版本也是 `jev-1.13.0`，模型请求不接截图。
见 [provider.ts](https://github.com/stoopid-computers/jev-bot/blob/d4be4a3bffe22704a1a9adc49ac044c61e9ee673/src/provider.ts#L21)。

输入通过 Cua Driver 的窗口/元素 token 契约执行。它有应用和窗口发现，但不等于内部
模型自己完成应用路由；README 明确不支持浏览器标签、坐标点击、滚动、应用启动等。
更重要的是，该版本自报原生 smoke 在权限检查处停止，真实输入/点击/截图尚未验证。
因此可借鉴分工与边界，不能用它证明原生 Jev 比 Tank 更可靠。
见 [driver.ts](https://github.com/stoopid-computers/jev-bot/blob/d4be4a3bffe22704a1a9adc49ac044c61e9ee673/src/driver.ts#L485)、
[README 验证记录](https://github.com/stoopid-computers/jev-bot/blob/d4be4a3bffe22704a1a9adc49ac044c61e9ee673/README.md#L479)。

## 3. typesafe-computer-use：语义状态、动作记忆与 reviewer focus

桌面路径把 OCR 文本和 AX 控件合并为编号列表，标记来源、角色、粗略位置。重名元素补
同一行邻居，日期计算成相对时间，聚焦字段单列。代码尽量提供已知事实，避免让分类器
从底层数据重新推理。OCR/AX 覆盖各有局限，合并不等于完整理解任意应用。
见 [perception.py](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/typesafe_computer_use/perception.py)、
[观察说明](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/docs/how-a-step-works.md)。

一个 Jev 请求包含 kind、item、site，必要时加 offscreen 的 Choice。编号短且描述简洁；
state 包括整体目标、当前 focus、用户补充、前台应用、URL、聚焦字段、最近八条动作，
以及 `already_tried_on_this_screen`。后者将“在同一状态做过但又回到此处”显式告知模型，
而非只有进展计数。kind 与所用目标答案共同决定置信度。
见 [decide.py](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/typesafe_computer_use/decide.py#L130)。

每次执行返回可读的历史描述，例如按了哪个控件、采用什么执行方式、是否被拒绝。
见 [actions.py](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/typesafe_computer_use/actions.py#L1)。

低置信度、停滞、找不到动作或模型 done 等会进入 reviewer。reviewer 接收当前画面/
文本、完整动作历史、早先页面和以前的失败 focus，返回回答、下一步 focus 或问题。
focus 作为运行状态保留，后续模型调用都能看到；达到总目标才是 done。它不是完整
多步计划，也不是直接执行一长串操作。
见 [runner.py](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/typesafe_computer_use/runner.py#L157)、
[models.py](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/typesafe_computer_use/models.py#L52)。

该项目还区分短文本生成模型与停止后读屏的 answer 模型，后者可用视觉。提示要求 focus
是当前屏幕上的一个可执行下一步，并避免重复无效 focus；默认 handoff 上限十次，停滞
另有界限。不能直接与 Tank 最多四次 Advisor 的成本或通过率相比较。
见 [writer.py](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/typesafe_computer_use/writer.py#L332)、
[config.py](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/typesafe_computer_use/config.py#L10)。

它另有 CDP/DOM browser backend，需显式用另一个入口；并非根据任意目标自动选择 AX 或
DOM。OSWorld 有真实逐任务记录，但来自不同版本、设置和任务；还包含更强 writer，不能
当作“纯 Jev”成功率，更不能与 Tank 两次 Calculator 直接排名。
见 [browser backend](https://github.com/awlevin/typesafe-computer-use/blob/44ca11f0935b021b73020825da054b5c92cc1288/docs/browser-backend.md)、
[OSWorld 记录](https://github.com/awlevin/typesafe-computer-use/tree/44ca11f0935b021b73020825da054b5c92cc1288/benchmarks/osworld)。

## 4. Tank 卡在哪里：事实与假设分开

### 已确认的模型输入/交接缺口

1. **历史不可读。** [GoalProgress](../../backend/plugins/agent-computer-use/src/agent_computer_use/contracts.py)
   只有最近完整动作、更早的 verified ID 列表和计数。旧 ID 已不在本轮候选中；没有
   “点击 8，读数 7→78”这样的记录。宿主知道局部结果，却没有把可读轨迹给 Jev/Advisor。
   ultrafast 与 awlevin 提供语义历史，但也不是都提供完整 before/after；后者是 Tank 可做的增强。
2. **Advisor 没有留下规划指导。** [AdviceReply](../../backend/plugins/agent-computer-use/src/agent_computer_use/advisor.py)
   仅允许单候选、补生成输入、补观察或退出，没有 focus。一次纠偏后原目标不变，Jev
   仍需自行决定下一步。我们的成功依赖 Clear、7 两次重复状态又触发 Advisor，让它碰巧
   继续选到 Multiply；这种控制流不是稳定的子目标交接。
3. **不确定性没有用于此原生循环的路由。** 当前 [JevSelector](../../backend/plugins/agent-computer-use/src/agent_computer_use/jev.py)
   接收模型 Choice 后主要检查控制选项与候选成员，未据 confidence 决定是否交给 Advisor。
   实测中错误数字动作置信度为 0.63、0.43、0.56、0.44、0.55、0.24；第一步正确 7
   为 0.93/0.92，后续正确 8 为 0.79，正确 Equals 也只有 0.65。直接抄 0.7 会同时
   拦住错误和正确动作，必须按任务族留出校准；不能用这十条已知答案拟合生产阈值。
4. **模型视图接近执行契约，语义浓度不足。** [compact_model_view](../../backend/plugins/agent-computer-use/src/agent_computer_use/jev.py)
   缩短了元素引用，但动作仍是随机 UUID；保留大量祖先、坐标、绑定和反复出现的读数变化
   基线。单次本批 Jev 输入为 18,864–19,553 tokens。对一个 44 按钮任务，这为精简视图
   提供动机，但不能仅凭长度证明质量下降。目标本身确实在请求中，Clear/Multiply 也未缺失。

### 当前状态与效果表达的限制

我们名为 `ax:value:result` 的区域在输入阶段实际承载 `7`、`78`、`7×`、`7×8`；
名为 expression 的区域在计算前为空，Equals 后才成为 `7×8`。模型必须自行理解这些
区域的 UI 含义。可改进为忠实呈现“当前输入显示”和“已计算表达式”的语义，不应让宿主
伪造理想算式或按测试答案硬编码下一步。

[effect_achieved](../../backend/plugins/agent-computer-use/src/agent_computer_use/controller.py)
对本次 click 只检查绑定读数有变化：7→78 也算局部效果成立。三步无新增完成证据后触发
review，是保险性的复核策略，不是目标距离或规划。有效的长任务也可能触发它。应将
“发生了什么”与“当前子目标是否推进”分别表达，而不是放宽最终成功条件。

### 本次没有证实的归因

原始记录已排除候选缺失、输出 ID 映射错、HTTP 失败这些具体解释；一项曾真实完成
7×8=56，另一项在 Advisor 选择 Close Parenthesis 后 effect_unknown 停批。首次两个
Advisor 输入归一化 ID/坐标后相同，实际请求仍不同。因此不能判定坐标、UUID、提示、
模型容量或推理波动中的哪一项是根因，也不能推断 Jev 的明确目标定位任务同样失败。

多 Choice 分解在混合 click/fill/scroll 时有价值，但本次 44 个候选全是 click，
加 operation head 并不会自动知道应先乘后输入 8。短 ID 与相对坐标应做单因素试验，
优先级不应高于补齐可读历史和明确规划交接的研究。

## 5. 建议的验证顺序

这部分是建议，不是已实施方案，也不是实测通过声明。

1. **先拆开测定位与规划。** 同一份真实 AX 状态分别测试“点击 Multiply”与“完成 7×8”。
   前者测明确目标到元素选择，后者测从状态推导下一步。加入状态已是 `7×`、`7×8`、
   错误输入 `787` 的样本，不只测试一个理想路径。
2. **补充有界语义历史，保持其它因素不变做回放。** 记录操作、目标标签/角色、输入值、
   前后观察差异、sent/verified/unknown、选自 Jev 或 Advisor。模型只读最近若干条，旧
   元素绑定不能成为可复用句柄。历史均来自宿主真实证据，不由模型追认。
3. **单独验证动态 focus。** Advisor 给当前下一步目标及可核验预期，宿主验证范围后
   持续提供给 Jev；完成/失效再更新。总目标、用户输入、权限和预算保持原契约。focus
   不能伪装成观察事实，也不能被当作整个任务已完成。避免重新引入测试预排 milestones。
4. **单独比较紧凑决策视图与当前视图。** 本轮短动作别名映射回原 binding；保留全部
   候选，抽出共享读数，删除仅执行器需要的重复字段，保留同名控件所需上下文。原始证据
   仍在宿主。若只做一次同时修改所有字段的试验，将无法区分哪个因素有效。
5. **再校准提前交接策略。** 除停滞外，评估低 confidence、分布接近、缺下一步目标时
   的 Advisor 路由；在独立 calibration/holdout 上冻结规则，统计正确率、覆盖、总调用、
   延迟与费用。confidence 不是正确性证明，不能跨任务/通道直接共用固定阈值。
6. **最后回到真实矩阵。** 无桌面回放只证明冻结状态上的选择，不能替代多步真实闭环。
   通过后重跑 Calculator/移窗/Quartz/TextEdit，保留先前 1/1/7 和未知效果停批规则。

本轮只研究，无新增收费实验。后续每个行为改动需在现有测试文件做 TDD；Tests 应覆盖
轨迹与观察一致、旧引用不可派发、focus 不弱化目标、全候选保留、共享预算以及未知结果
零重放。最后执行[现行计划的完整验证清单](../plans/active/computer-use-strategy-ladder.md)
全部适用项及最多三轮独立评审。

## 6. 应保留的 Tank 能力与不能照搬的行为

Tank 已有进程实例/窗口绑定、执行前刷新、全候选/完整范围约束、明确的输入与最终完成
谓词、共享预算和独立读回；这些在本次定位/执行链和清理中发挥了作用。
不能为了“像 demo 一样一直跑”而把没有变化改成成功、无界重试或用模型 done 代替核验。

awlevin 的桌面动作实现有 AXPress 不成功后转坐标点击、填值后转按键的 fallback；这与
Tank 当前未知效果不重放的边界不同，应保留“明确未发送才可换通道”的要求。
它的 reviewer `achieved` 也是模型判断，不能替代 Tank 的独立完成条件。
ultrafast 的多目标预测只执行一个对应目标，并非并行执行多个 UI 操作。

三个项目也没有共同解决任意应用的自动通道选择：ultrafast 是明确 URL 的浏览器；
jev-bot 由外层选择应用/窗口；awlevin 有前台桌面与独立 browser 入口。Tank 的应用发现、
绑定与能力路由仍是另外一项工作，不应归因到这次 Calculator 的规划失败。

## 本轮验证

已固定三个仓库 commit，逐项阅读循环、提示、候选、执行、历史及报告源码，并与 Tank
实际请求/回复及代码核对。没有运行第三方测试或复现其性能数字。只修改本文和索引；
`python3 scripts/check_docs.py`（51 files）和 `git diff --check` 通过。
独立 review-and-refactor 第 1 轮以 `7fa3784f` 为基线，复核三份固定源码、Tank 的
十次 Jev 置信度/输入 tokens 和 Advisor 轨迹；未发现可操作问题，无修改，立即结束。
本轮纯文档，未重复运行生产测试。协调者核对最终差异及此收尾元数据。
