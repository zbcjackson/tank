# M7 批次 3：三臂对比冻结/提案/启动材料（2026-09-25）

零模型请求、零截图外发。三臂 = 纯截图基线 **A** / **AX-quartz**（AX 候选 +
Quartz 点击）/ **AX-press**（AX 候选 + AXPress），固定同一规划模型
（`qwen3.7-flash`），calc-open 任务，3 轮轮转配对（每臂先行各一次），共 9 trial。

## 材料

| 目录 | 内容 |
|---|---|
| `../20260925-m7-ax-runtime/` | 九变体 runtime/SDK 冻结（AX 快照为 4 请求：绑定窗口截图 → locate → **纯文本 select 请求（无图片）** → done） |
| `../20260925-m7-ax-proposal/` | 固定日程 9 trial / 234 HTTP / 2.7M token（声明值）；352 文件预检通过 |
| 本目录 `launcher.py` | 默认仅预览；`--live` 需 go 文件 + 新一轮单独授权；门禁/范围自愈/输入清理/外层恢复沿用 M6 链 |

- `gate_check.py` 11 例 / `scope_check.py` 5 例通过，两者记录的 launcher
  sha256 一致；受控窗口门禁与单位消歧对所有臂一致（AX 臂点击点来自 AX 帧，
  构造上在窗口内；A 臂仍受保护）。
- 本地预览实测：`initial.png`（1920×1080 受控黑背景 + 仅 Calculator）产出、
  `ready.json`（model_requests=0）、launcher 清理 7/7、外层恢复
  `confirmed=true`、零按键/鼠标残留。
- 定位预算：AX 臂 locate（select）请求计入每行 locator 限额（15），与 split
  臂同口径；record-only 账本 + 强制 agent 预算 300000 + input_cleanup。

## 实现变更（本批代码）

- M2 接缝修复：`_validate_observation` 现将省略的 `window_id` 视为"帧绑定值"
  （此前显式 None 被当作另一窗口，拒绝绑定帧上的所有 locate）；回归
  `test_locate_without_window_id_uses_bound_observation_window`。
- `prepare_computer_comparison.py`：AX 变体（mode=ax，同一 planner）；快照场景
  为绑定窗口截图 + 无图片文本选择请求。
- `ComparisonContract` 允许 `AX-quartz`/`AX-press`；`prepare_computer_batch.py`
  新增 `_m7_ax_spec`/`preflight_m7_ax`/`prepare_m7_ax`/`execute_m7_ax_trials`
  （授权门 + 验收决策门 + 漂移拒绝 + 逐行上限）。

## 执行前置（批次 4，live）

1. 新一轮截图外发授权（范围：受控 Calculator 桌面 → DashScope，≤234 请求）。
2. 发送前程序化复核 `initial.png` 后写 `go` 文件。
3. 串行 9 trial，逐臂报告；成绩单列，不与纯视觉 A/B/C/D 混合。
