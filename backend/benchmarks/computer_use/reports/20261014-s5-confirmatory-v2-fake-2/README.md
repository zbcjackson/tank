# S5 确认实验：revision 2 桌面 fake 验收

> 日期：2026-10-14；状态：fake 全量完成，不构成模型采用证据。

源码基线 `f3cd259f`；冻结签名 `108591b0ffb568cbe9b8430bdd02442d678fe4b7c64089124f3c3fe3abee3b12`。三族五任务，每任务十次重复，
A/H/J 各 50 项，按配对轮转先手。A 为冻结生产驱动器，H 为规则+LLM，J 为 Jev 优先并保留同一 Advisor。

- 150/150 finished；H/J 各 50/50 strict、50/50 passed；零规则违规，所有 App 清理确认。
- A 0/50：fake A 只回一次 SSE 文本、无模型派发桌面动作、无截图（启动/清理仍执行），仅验证驱动器与账本接线，不能评价真实基线。
- 730 次本地 fake HTTP；外部模型请求 0。虚拟用量/金额仅用于账本断言，不是实际费用。
- 结论为 `fake_wiring_only_no_adoption_conclusion`，H1–H4 不因 fake 成功而成立。
- 本轮实际使用新 owned Calculator 和临时 TextEdit 文档，通过 AX/Quartz 操作及独立 AX 读回核验。

原 `20261014-s5-confirmatory-v2-fake/` 保留：3 finished / 1 environment_error / 146 not_run，
完整 150 分母，0 外部请求。Quartz 预检误漏 AX description/value，已在第 3 轮修复，
保持遮挡拒绝门；此目录以新源码、新签名运行，不覆盖原停批产物。

代码验证：后端 5924 passed / 1 skipped / 21 warnings，定向 120 passed，E2E 18 场景/71 步，
修改 Python pyright、lint、服务日志、docs/diff 检查通过。第 1 轮独立评审并修复 R1–R3，
第 2 轮自检；第 3 轮修复实机 R4，最后修复未额外独立复核，按三轮上限停止。

本地产物：[freeze.json](freeze.json)、[result.json](result.json)、[rows.jsonl](rows.jsonl)，
原始日志 `/tmp/tank-s5-confirmatory-v2-fake-2.log`。原始 JSON/日志按已有策略本地保留。
真实批次的配方与审批阻塞见 [live 预览](../20261014-s5-confirmatory-v2-live/README.md)。
