# M6 calc runtime/SDK 冻结（2026-09-24）

M6 第 2 项（calc-open 四臂 × 三轮，300000 共享 token 上限强制）的离线冻结。

- 由 `prepare_computer_comparison.py --config core/config.yaml` 生成，零模型请求、
  零桌面操作；七组 runtime（A-control/B-protocol-only/A/B-host-only/B-combined/C/D）
  供提案按臂选取，本批只用 A/B-combined/C/D。
- 与 `20260924-m5-normalized-runtime` 对比：`requests.json`、`definitions.json`、
  `profiles.json`、`toolset.json` 与全部 16 个 `runtime/*` 文件**逐字节一致**；
  变化的源码仅 `agents/runner.py`、`benchmarks/batch.py`、`benchmarks/driver.py`
  （即本轮的 agent 预算强制实现），无契约漂移。
- 299 个源码条目、模型/生成参数/坐标契约与 M5 normalized 批相同（归一化 point、
  D 为 bbox）。`live_authorized=false`：这是代表性请求契约，不是效果证据。
