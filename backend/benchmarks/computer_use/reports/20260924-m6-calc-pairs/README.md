# M6 第 2 项：A/B/C/D calc-open 三轮（300000 共享预算强制，2026-09-24 22:38–23:12）

用户单独授权后执行（截图范围 = 受控 Calculator 桌面 + 黑背景 + 菜单栏，端点 DashScope
qwen3.7-flash / qwen3.8-max，12 trial / 声明 ≤282 请求）。发送前程序化复核
`initial.png`：仅 Calculator 可见、窗口 (600,100) 674×408、AX 显示 `0`、底部纯黑。
批由 `execute_m6_calc_trials` 串行执行，`agent_budget_enforced=true` 记录进每份报告。

## 结果（12 轮，按配对轮转顺序）

| trial | 结果 | 请求(规划/定位) | 规划 tokens | 定位 tokens | 末帧显示 | 失败分类 |
|---|---|---|---|---|---|---|
| pair-1-a | FAIL | 16 / 0 | 128142 | 0 | `78` | 输入语义（运算符被忽略） |
| pair-1-b-combined | **PASS** | 9 / 0 | 134457 | 0 | `7×8`/`56` | — |
| pair-1-c | **PASS** | 11 / 5 | 113580 | 12778 | `7×8`/`56` | — |
| pair-1-d | FAIL | 15 / 5 | 186722 | 13200 | `56`（无表达式行） | 输入路径（粘贴求值但不留表达式） |
| pair-2-b-combined | FAIL | 16 / 0 | 285140 | 0 | `7` | 流程未走完（步数耗尽） |
| pair-2-c | FAIL | 16 / 5 | 167182 | 11684 | `7×` | 流程未走完（步数耗尽） |
| pair-2-d | FAIL | 16 / 3 | 162616 | 7915 | `7` | 流程未走完（步数耗尽） |
| pair-2-a | **PASS** | 10 / 0 | 106357 | 0 | `7×8`/`56` | — |
| pair-3-c | FAIL | 16 / 3 | 139441 | 7656 | `0` | 流程未走完（步数耗尽） |
| pair-3-d | **PASS** | 11 / 4 | 108745 | 10562 | `7×8`/`56` | — |
| pair-3-a | FAIL | 16 / 0 | 226204 | 0 | `7×8`（未按 =） | 流程未走完（步数耗尽） |
| pair-3-b-combined | **PASS** | 6 / 0 | 67462 | 0 | `7×8`/`56` | — |

按臂：**A 1/3**（均值 153,567 tok）、**B-combined 2/3**（162,353）、**C 1/3**（150,773）、
**D 1/3**（163,253）。总计 **5/12**、**1,889,843 tokens**、183 次请求（远低于 282 声明上限），
全部 HTTP 200、usage 已知、无余额错误，费用未核价（record-only）。

## 与 M5（无预算强制的每臂 6 轮）的诚实对比

- 通过率 5/12 vs M5 合并 11/24：同一契约下批间方差依旧很大。**B-combined 本批 2/3**
  （M5 六轮 0/6）且出现其首批两次通过；A 本批 1/3（M5 3/6）。每臂 n=3，不构成任何
  优劣结论或对 M5 配对结论的翻案，只再次印证"单批均值不能直接归因架构"。
- **预算强制本身零干扰**：单轮最高 285,140（pair-2-b-combined，步数耗尽停止），
  无一轮触发 300000 停止（stop_reason 全部为空，未出现 `budget`）；C/D 定位请求
  最多 5 次（≤15 上限），定位用量单轮 7.6k–13.2k tokens，均已按请求拆分记录
  （`analysis.json` 的 `per_request`：role/model/图片数/输入/输出）。

## 本批失败结构（与 M5 的关键差异）

- **零坐标/定位错误**：M5 归因脚本曾给出"B-combined 0 命中/23 窗内空点（纯落点问题）"；
  本批 12 轮没有任何一轮因点错键/空点失败——失败全部是流程未走完（5）、输入语义
  （运算符被忽略 → `78`，1）、粘贴路径无表达式行（1）。
- 门禁拦下 **7 次窗外点击**（pair-1-a ×2、pair-1-b ×2、pair-2-a ×1、pair-2-b ×2），
  零派发、零单位消歧（归一化契约下不触发）；遮罩陷阱一次未发生。
- 一次生产护栏触发：`Guardrail BLOCK: click total failures=6`（重复失败保护，
  对应 pair-2-b-combined 的失败派发累计），trial 仍正常收尾。

## 验收项核对（M6 第 2 项要求）

- 每轮重置：12/12 `reset_verified=true`；新图：每轮独立截图（hash 见各 trace）；
  独立真值/validator：`calc-evidence-v1` strict（当轮 AX 显示）。
- 120 秒 / 15 步：全部在限内停止（多为 15 步上限）；定位调用 ≤15：实际 ≤5。
- 共享 300000 token 上限（含定位）：已强制并记录（`agent_budget_enforced=true`、
  `token_budget=300000` 进每份报告 metadata）；本轮未触顶。
- 按请求规划/定位用量：`analysis.json` 逐请求记录（role/model/images/in/out），
  非仅顶层工具计数。
- 清理：12/12 `cleanup=confirmed`；launcher cleanup 全过（Calculator 关闭、按键/
  鼠标空、背景关闭、应用/剪贴板/光标恢复）；外层恢复 `confirmed=true`
  （`outer-recovery.json`）。

## 边界

- 单任务 calc-open、单布局、每臂 3 轮；`pixels=unknown`（无自动像素评分，以 AX 为准）。
- 判定为 strict（需屏幕同时有 `7×8` 与 `56`）：pair-3-a 输入了表达式但未按 `=`、
  pair-1-d 结果对但走粘贴路径，均按既定口径计失败（用户 2026-09-24 已确认粘贴路径
  是合法能力信号而非干扰项）。
- 下一项（第 3 项）按计划应"留下基线和至多一个候选"再跑 14 任务 × 3 轮；
  本批数据不足以在 A 与 C/D 间做候选取舍（1/3 vs 1/3，M5 合并亦不可区分 p=0.43），
  候选选择需结合 M5 合并证据与延迟/成本（见 README 底部）。

## 原始证据

`trials/<key>/`：batch-plan/spend.jsonl、逐 trial report.md/json、trace.jsonl
（http_request/spend_settled/desktop_dispatch/grounding_*）、responses/*.bin、
screenshots/、validator 评估；`initial.png`、`ready.json`、`cleanup.json`（含
gate_blocked 7 条）、`supervise.log`、`outer-recovery.json`。私有桌面基线
（baseline.json）保留在 /tmp，未归档。
