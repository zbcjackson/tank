# S5 修复后 fake：环境拒绝及汇总缺口

> 日期：2026-10-14；状态：18 finished / 1 environment_error / 131 not_run；原产物保留。

冻结签名 `b321e03e106f3de9e539b8d4939a8f70179d73e4ba653631189f254a136d3534`；
driver修复提交 `30967a9e`，不含随后发现的汇总缺省键修复。

150行全分母保留。A 0/6、H 6/6、J 6/6 strict仅为fake线路结果，85本地fake HTTP，
0外部模型请求/费用；账本334,176 nano USD是合成usage按冻结单价的模拟估算，不是收费。
已结束18项及拒绝项owned清理确认。第19项 `1-calculator-quartz-1-J` 启动前以
`Target app already running; pilot does not touch existing sessions`拒绝，
未启动该行模型或触碰现有实例，账本停批 `s5_trial_unsettled`。
随后只读NSWorkspace没有Calculator；该证据不足以归因退出通知缓存、用户操作或其他来源。

由于此前已有长任务完成并计费，长族汇总遍历尚未运行、没有spend_trial键的行，
又抛 `KeyError: spend_trial`。原[result.json](result.json)只有中间rows/spend，
没有最终summary/统计/verdict；不补写或把这份中间文件当完整结论。
回归已用真实Runner/SDK与fake桌面/HTTP复现，最小修复只把可缺省键改为get。
原准备已达三轮评审，不启动第四轮；这处最后harness修复未经再次独立复核，
此前新driver/test首轮评审结论不涵盖它。新签名另开目录，不重跑本目录。

原始[rows.jsonl](rows.jsonl)、[spend.jsonl](spend.jsonl)、[freeze.json](freeze.json)、
[audit.jsonl](audit.jsonl)保留，本地日志 `/private/tmp/tank-s5-confirmatory-v2-repaired-fake.log`。
没有确认采用结论，S5仍未验收；生产Jev默认保持禁用。
