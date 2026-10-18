# S5 原生 track 三臂配对 pilot（live，2026-10-13）

计划：[策略阶梯 S5](../../../../../docs/plans/done/computer-use-strategy-ladder.md)（§S5 第一片）。
Harness：`benchmarks/computer_use/s5_paired.py`，冻结 digest
`283073cf20a7ff5e955ac8019feedb7729783929566de2584942c40f1088bf99`。

## 范围与三臂

原生 macOS track（A 臂截图 grounding 只能操作可见应用，无头 Chromium 无法三臂同任务配对；
DOM track H/J 配对属后续批次）。三臂同一条中文自然语言指令（s4_nl live 验证过的 prompt），
H/J 经插件内 intake 转契约（调用计入成本）。3 任务（Calculator 7×8 ax_press/quartz、
TextEdit 正文替换）× 3 repeats（repeat 1 移窗）× 3 臂轮换先手 = 27 trials。

- **A**：冻结生产基线——内置 `computer_use` agent（截图+grounding 工具链、
  qwen3.7-flash@DashScope、max_steps 15/240s 生产默认）。
- **H**：插件宿主 `selector: llm`（规则+F 文本选择器）+ Advisor + intake。
- **J**：插件宿主 `selector: jev-fallback`（Jev 优先，有效弃权回退同一 F）+ 同 Advisor + intake。

评分：`OwnedApplication` 独立新鲜 AX 遍历（strict/partial/violation），不读模型自评；
已知失败留分母继续，unknown usage/取消/清理未确认停批；trial 间隔离，读回消解的
effect_unknown 按已知失败结算（前两次尝试的停批与修复见计划记录）。

## 结果（27/27 finished，195 请求，2,311,203 已知 tokens，$0.3485）

| 臂 | strict | 模型调用 | 费用 | 总耗时 |
|----|--------|----------|------|--------|
| A | 0/9 | 106 文本（53 截图上传） | $0.2708 | 819.7s（均 91.1s） |
| H | 6/9 | 36 文本（含 9 intake） | $0.0402 | 86.6s（均 9.6s） |
| J | 8/9 | 33 Jev + 20 文本（含 9 intake） | $0.0376 | 112.1s（均 12.5s） |

配对明细见 `result.json` 的 `paired`。逐对方向：J/H 成本与时间均低于 A；
J 相对 H：质量 8 vs 6、费用 −6%、时间 +29%（与 S3 J3 +22% 的方向一致）。

## 逐失败归因（独立读回）

- H/J 全部 4 个失败同签名：选择器顺序错误（按 7、8 后才按 ×，读回 `78×`）——
  S4 矩阵已知的运算符顺序残余（第七批评估暂不修），本轮 F 选择器亦出现。
- A 的 6 个 Calculator 失败：15 步生产上限内未按完（终态 `7×`、`78` 等），
  与 M5 A-control 历史一致；3 个 TextEdit 失败为近失——正文正确但缺尾随换行
  （`Tank NL / 中文验收` 少最后的 `\n`）。
- 零 rule_violation（无人直接输入 56）、零 partial、全部清理确认（App 终止、
  窗口位置/前台还原、输入键释放）。

## 限制（预声明）

- n=3/任务的描述性 pilot；结论 `pilot_descriptive_only_needs_confirmatory_freeze`，
  不构成采用证据——采用判定需另行冻结任务族/重复数/统计方法/最小实际收益的确认实验。
- A 的 0/9 部分反映生产默认 max_steps=15 与本任务集的匹配度，是该基线的真实行为而非
  harness 缺陷；生产默认与基线 A 不变。
- 前两次 live 尝试（读回前台不变量、effect_unknown 停批）保留于
  `../20261013-s5-paired-live/`、`../20261013-s5-paired-live-2/`。
