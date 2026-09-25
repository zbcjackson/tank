# M6 第 3 项：A 基线 + C 候选 × 13 任务 × 3 轮（2026-09-25 10:04–13:20）

按第 2 项后的候选取舍（用户采纳建议：A 基线 + C 候选，D 与 C 不可区分且多一个模型），
对 13 个 macOS 适用任务各跑 3 轮 × 两臂（轮内交替、轮间换先手）。calc-open 复用第 2 项
的 A/C 各 3 轮（同冻结同契约同代码），不重复消耗。

- 夹具：每任务独立受控桌面（仅目标任务应用允许可见 + 黑背景 + 门禁绑定任务窗口）；
  每任务发送前程序化复核 initial.png 后放行。
- 上限沿用：任务声明时限（120–180s）/ 15 步 / C 定位 ≤15 / 共享 300000 token 预算
  （强制，`agent_budget_enforced=true`）。
- 源码 revision：前 5 个任务（open-settings…file-ops）用 09-24 冻结；terminal-write
  第 2 轮后遭遇 Carbon TIS 工作线程 SIGTRAP（与 M5 IME 崩溃同型），修复
  （ASCII 输入源查询移入子进程，`96217cf` 系列提交）后重跑整个任务并以
  09-25 新冻结完成其余 8 个任务——契约字节一致，仅 2 个源码文件差异。
- 总消耗 **11,749,659 tokens / 1,082 请求**（费用未核价）；门禁拦 28 次窗外点击。

## 结果（strict 分母不含 smoke）

| 任务 | A | C | A 均值 tok | C 均值 tok | 主要失败（合计两臂） |
|---|---|---|---|---|---|
| open-settings (smoke) | 3/3 | 3/3 | 20,869 | 10,199 | — |
| browser-navigate | 1/3 | 0/3 | 78,835 | 42,582 | 流程未走完 ×5 |
| local-form | **3/3** | 0/3 | 137,267 | 271,505 | 流程 ×2、预算停 ×1 |
| typing-fidelity | 0/3 | 1/3 | 111,059 | 223,489 | 流程 ×4、预算停 ×1 |
| file-ops | 0/3 | 0/3 | 133,487 | 247,005 | 流程 ×5、窗外点击 ×1 |
| terminal-write | 3/3 | 3/3 | 72,746 | 119,330 | — |
| settings-toggle | **3/3** | 1/3 | 59,768 | 243,772 | 流程 ×1、启动失败 ×1 |
| editor-save | 0/3 | 0/3 | 150,248 | 237,356 | 流程 ×4、窗外点击 ×2 |
| links-history | 0/3 | 0/3 | 154,219 | 246,913 | 流程 ×5、预算停 ×1 |
| multi-select-copy | 0/3 | 0/3 | 143,158 | 242,767 | 流程 ×5、窗外点击 ×1 |
| drag-file | 0/3 | 0/3 | 99,630 | 231,244 | 流程 ×5、窗外点击 ×1 |
| small-text-code | 0/3 | 0/3 | 77,647 | 182,159 | 流程 ×6 |
| window-copy | 0/3 | 0/3 | 135,128 | 244,162 | 流程 ×6 |

**strict 合计（不含 smoke）：A 10/36，C 5/36**；含 smoke A 13/39、C 8/39。
并入 calc-open（各 1/3）：A 11/39、C 6/39（Fisher 单侧 p≈0.19，提示性不显著）。

## 诚实结论

1. **本扩展上基线 A 优于候选 C**：差异由 local-form（3/3 vs 0/3）与 settings-toggle
   （3/3 vs 1/3）驱动；C 每任务平均消耗约 **1.7–2× token**（定位请求 + 更长流程），
   且 3 次 `budget` 停止全在 C 臂。M5"拆分 ≥ 一体"的配对结论**未在宽任务集上复现**——
   它只在 calc-open 单任务上成立。
2. 每任务每臂 n=3，任务是异质的；本结果不构成显著性结论，但方向与成本共同指向
   **M8 保留生产基线 A**（拆分架构的采用价值未获支持，作为调查结论归档）。
3. 失败分类（第 6 项口径）：流程未走完 48、预算停止 3、窗外点击（门禁拦截）5、
   应用启动失败 1、超时 0、清理失败 0——识别/定位错以门禁拦截形式出现且零派发，
   无变换错、无陈旧观察逃逸、无清理失败。

## 边界

- GUI 轨道全程禁 shell/file 绕路（gui_only 默认 true）；浏览器任务仅访问本地
  pageserver（回环），无外网浏览。
- terminal-write 首次运行的第 1 轮两臂证据保留于 `terminal-write-aborted1/`
  （SIGTRAP 中止，零清理缺失）；该任务完整 6 轮为修复后代码。
- 两次外层恢复 `applications_restored=false`（multi-select-copy、drag-file：
  任务 teardown killall Finder 自愈重启导致身份核对失败）——launcher 级清理与
  事后人工核对均确认桌面完整恢复；orchestrator 已加任务后恢复层。
- 编辑器/文件/拖拽类任务全败是能力现状的如实记录（难度 2–3），不因低分调整口径。

## 原始证据

`<task>-trials/`（每 trial report/trace/spend）、`<task>-meta/`（initial.png、
ready/cleanup）、`analysis.json`（逐 trial 分类与逐请求用量）、orchestrator 日志、
`terminal-write-aborted1/`。截图与原始 HTTP 响应二进制仅本地保留（同 M5 core-pairs
先例），文本证据全部入库。
