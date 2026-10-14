# S5 修复后 fake：150项线路验收通过

> 日期：2026-10-14；状态：150/150 finished，0外部请求/费用。

源码基线`bbce7748`；冻结签名
`60fb55424f6caec77a9bee806df1a66d3837f16de1ff6586cdf3683dd023e2ea`。
包含driver工具上限收尾/流式未知用量/计时修复，以及长任务后停批汇总缺省键修复。

- 150项完整完成，A/H/J各50项，H/J各50/50 strict和passed，0规则违规。
- 730本地fake HTTP全部已知usage，0外部请求；模拟账本不是供应商费用。
- 150项owned应用清理确认，50项A输入清理确认；账本stop_reason=None。
- A的fake模型只回复done，不调用GUI工具/截图，A 0/50不代表真实视觉模型质量。
  owned启动、初始化/移窗、读回和清理仍真实执行。
- verdict为fake_wiring_only_no_adoption_conclusion；H1–H4未用fake作确认判定。
  本批只证明线路/调度/清理，不能外推模型成功率或Jev净收益。

[前次fake失败](../20261014-s5-confirmatory-v2-repaired-fake/README.md)完整保留，
未重跑或覆盖；本批没有放宽已有应用/遮挡隔离门，没有把失败混入新的成功统计。
原真实批次6/144及未知预留也继续保留。

验证：完整后端5929 passed/1 skipped/21 warnings、E2E18场景/71步、改动文件
pyright/lint及docs通过。新driver/test独立评审首轮无问题；原确认准备三轮已结束，
最后一行harness缺省键修复先红后绿并完整验证，未经再次独立复核，不增第四轮。

[同签名新真实执行预览](../20261014-s5-confirmatory-v2-repaired-live/README.md)，
尚未执行收费批次；需要独立的新预算授权，不将旧未知预留视为退款。
本地[result.json](result.json)、[rows.jsonl](rows.jsonl)、[spend.jsonl](spend.jsonl)、
[audit.jsonl](audit.jsonl)、[freeze.json](freeze.json)及trials保留；不提交原始桌面数据/凭据。
日志`/private/tmp/tank-s5-confirmatory-v2-repaired-fake-2.log`。
