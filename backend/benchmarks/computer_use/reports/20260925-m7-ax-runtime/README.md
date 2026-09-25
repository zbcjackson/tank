# M7 三臂对比 runtime 冻结（2026-09-25）

由 `prepare_computer_comparison.py --config core/config.yaml` 生成，零模型请求、
零桌面动作。相对 M6 calc 冻结新增 `AX-quartz`/`AX-press` 两变体（`grounding.mode:
ax`，同一 planner `qwen3.7-flash`）；其余七变体字节不变（除源码 pin 因
computer_frame 接缝修复与本批脚本更新而变化）。

AX 变体的代表性 SDK 请求为 4 步：绑定窗口截图 → `locate` → **纯文本 select
请求（无 image_url，含编号候选列表）** → done；选择器响应为脚本化弃权
（`not_found`/`index 0`），只验证请求形态与解析，不派发输入。

下游：`../20260925-m7-ax-proposal/`（9 trial 固定日程）、
`../20260925-m7-ax-ready/`（launcher/门禁/预览证据）。
