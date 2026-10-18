# S5 DOM track：当前宿主 H/J 配对 pilot（live，2026-10-13）

计划：[策略阶梯 S5](../../../../../docs/plans/done/computer-use-strategy-ladder.md)。
Harness：`benchmarks/computer_use/s5_dom.py`，冻结 digest
`a80e043a369128512ffddaee2f6601da52b9a66493a5ca9d510d999cfad168b6`。

## 问题

S3 的 48 例 H3/J3 配对（2026-10-04）结论为 no-net-gain（质量相同、省费 −39.6%、
耗时 +22.1%）。S4 为宿主加入了文本 Advisor、语义执行历史、紧凑候选视图与动态
focus。本批在**同一 8 任务族**（`fixtures/s3-strategy/cases.json`）上用当前宿主
重测 H/J，回答“S4 改进是否改变该结论”。

## 设计

- **H** = `selector: llm` + `advisor: llm`；**J** = `selector: jev-fallback` +
  同 Advisor。唯一变量是选择器。3 repeats × 8 cases × 2 臂 = 48 trials，
  轮换先手；共享 SpendLedger；评分沿用 S3 的独立页面事件核对。
- 预声明门槛（S3 血统，策略级非采用）：双臂 24/24、零意外动作、J 确实减少
  selector-F 调用，且时间或费用改善 ≥10% 而**另一项不退化**。

## 结果（48/48，60 次请求，$0.0137）

| 臂 | accepted | selector-F | Jev | 费用 | 总耗时 |
|----|----------|-----------|-----|------|--------|
| H | 24/24（18 完成 + 6 合理退出） | 27 | 0 | $0.0090 | 31.4s |
| J | 24/24（同） | 6 | 27 | $0.0047 | 45.3s |

Advisor 两臂均未触发（0 次，干净单步页）。规则步 3、eligible 27 两臂一致；
J 的 6 次 selector-F 全部来自 2 个 exit 任务的合理弃权回退。

**结论：`no_net_gain_demonstrated_keep_disabled`**——J 路由有效（省下 21/27 次
F 调用、费用 −47%），但耗时 +44%（S3 为 +22.1%），未满足“另一项不退化”。
S4 宿主改进未改变 S3 结论；生产默认保持禁用。

## 限制

- 同 S3：作者构造的工作流切片与结构化目标（非自然语言任务、无 intake），
  n=3/repeat 的 pilot；策略级证据，非采用证据。
- 耗时含本地 Chromium 与网络往返；不能把总耗时差解释为纯推理速度差。
- 本批每任务仅 1-2 个决策，Jev 每决策的串行往返在短任务上占比更大；
  多决策长任务的耗时差未测。
