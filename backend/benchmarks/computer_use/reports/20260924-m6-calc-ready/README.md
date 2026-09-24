# M6 calc 单批启动材料（2026-09-24）

指向 `20260924-m6-calc-runtime` 冻结与 `20260924-m6-calc-proposal` 提案的受控
launcher。默认仅本地预览；`--live` 需**本轮单独授权**（截图范围 = 受控
Calculator 桌面 + 黑背景 + 菜单栏，端点 DashScope qwen3.7-flash /
qwen3.8-max，12 trial / ≤282 请求），发送前复核 `initial.png` 后放 `go`。

与 M5 sixpair launcher 的差异：`preflight_m6_calc` + `execute_m6_calc_trials`
（12 个 m6-pair trial 串行、逐行请求上限、agent 预算强制）；门禁/单位消歧/
范围自愈/IME 隔离逻辑不变。外层恢复继续由
`scripts/supervise_computer_pilot.py` 承担（私有基线 0700/fsync，崩溃/超时后
逐项恢复，绝不归档 baseline.json）。

本地校验（0 模型请求 / 0 图像外发）：

- `gate_check.py` 11 例、`scope_check.py` 5 例通过，两者记录的 launcher
  sha256 一致；
- 预览（supervisor, timeout 300）：`initial.png` + `ready.json` 产出
  （`phase=m6-calc-pairs, enforce_agent_budget=true, trials=12`）、launcher
  cleanup 全过（Calculator 关闭、按键/鼠标空、背景关闭、应用/剪贴板/光标恢复）、
  外层恢复 7 项全 true、`confirmed=true`。

## 执行（需授权）

```bash
cd backend && uv run python scripts/supervise_computer_pilot.py \
  --state-dir /tmp/tank-m6-calc-recovery --timeout 2400 -- \
  python benchmarks/computer_use/reports/20260924-m6-calc-ready/launcher.py --live
```

授权前 `live_ready=false`。预计 12 × ~2 分钟 + setup/teardown；中断即停批，
证据保留在 `/tmp/tank-m6-calc-20260924-live/`，跑完归档到 reports。
