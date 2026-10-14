# S5 确认实验：真实批次按未知用量停批

> 日期：2026-10-14；状态：用户已明确授权并执行；6 finished / 144 not_run，按 unknown_usage 停批，确认未完成。

源码基线 `f3cd259f`；冻结签名 `108591b0ffb568cbe9b8430bdd02442d678fe4b7c64089124f3c3fe3abee3b12`，与已验收的 fake 完全一致。
首次准备后执行被自动审批拒绝，当时进程未启动、0 live 操作/请求/费用。2026-10-14 用户明确允许上述数据导出及150项收费批次；随后按同一签名启动并按停止规则终止；原始行件和账本保留，未重放请求或重跑目录。

## 执行结果（2026-10-14）

- 150 项全分母保留：6 finished / 144 not_run；只覆盖第一个 repeat 的两个短计算任务。
- A 0/2 strict，H 0/2，J 2/2；TextEdit、calc-long 及其余重复均未执行。零规则违规，六项 App 清理确认，两个 A 驱动 cleanup=confirmed。
- 52 次模型请求：46 次 Qwen、6 次 Jev；51 条用量已知，1 条用量未知。
- 已确认用量 575,796 tokens，按冻结单价估算 $0.098081；
  未知请求仍预留 1,031,808 tokens / $0.190048，
  合计账本占用 $0.288130。这不是供应商账单，未知预留不得当作已确认支出或退款。
- 停批原因 `unknown_usage`，不是 $4 预算耗尽，也不是第三次 A timeout；A 本批仅一次 timeout。
- A 第二项于 240s 超时，最后一条流式请求 `665b29b2d2c14b719f61654be29711b8` 的最终 input/output usage 缺失。
  该调用的 trace 显示 finished/unknown（约15.974s），随后 driver_done=timeout、desktop_cleanup=confirmed、spend_budget=unknown_usage。
  这是超时尾部调用的未知用量证据，不能据此断言供应商漏计费。没有重放该请求，完整合同预留保持不动。

结论为 `incomplete_no_confirmatory_conclusion`；H1–H4 **均未判定**，JSON 中 false 是 incomplete 分支输出，不代表四个假设被实验否定。
配对统计为空，长任务的时延摊薄未测，不能按前六项选择采用策略或推广成功率；生产默认维持现状。

## 有限失败观察与后续停点

- A 第一项 15 步触顶，第二项 240s 超时，独立读回均为 0；A 文本多次自述窗口被遮挡；本地查看 Quartz 项第一张既存截图，Calculator 已在前台清楚可见，Paseo 位于背景，至少该帧不支持“窗口整体被遮挡”的叙述。不能据单帧排除后续具体点位遮挡，也不能仅凭模型叙述归因于 OS。该核对只读本地既存截图，没有新增 GUI/模型请求。
- H 两项均读回 `78×`：AXPress 以 invalid_advice 结束，Quartz 的 effect_unknown 被独立最终读回和已确认清理消解为已知失败，未重放动作。这与历史运算符顺序问题同类，当前数据不用于事后改成功标准。
- J 两项独立读回 `7×8` / `56`，仅证明本批两项完成，不构成确认采用证据。
- 如继续确认，先针对 A 停止/遮挡证据做不收费的诊断，明确原冻结生产基线是否保持，再另开计划中的新冻结批次。
  原目录不可复用，未知预留不可抹掉；任何新实验须保留本次停止记录及原预声明门槛，不能把重跑当补齐原始结果。
- 代码已达三轮评审上限；本次只更新执行证据和文档，docs/diff 检查，不增加第4轮或宣称最后文档独立复核。没有本次执行后的代码改动。

本地产物：[result.json](result.json)、[rows.jsonl](rows.jsonl)、[spend.jsonl](spend.jsonl)、[audit.jsonl](audit.jsonl)、[freeze.json](freeze.json)，
原始 HTTP/截图在 trials 下保留，按既有策略不提交原始桌面数据或凭据；控制台日志 `/tmp/tank-s5-confirmatory-v2-live.log`。

## 执行范围

- 150 trials：calc-short AXPress/Quartz、TextEdit 正文替换、calc-long AXPress/Quartz，共五任务×十重复×A/H/J。
- 只使用新 owned Calculator 与临时 TextEdit 文档，结束后确认清理；共享任务、初始状态、评分与资源限制。
- A 保留生产截图驱动器；其整屏/区域截图可能包含其他可见应用内容。H/J 使用原生 AX 控件标签、值、窗口层级、候选动作及最近操作历史。
- 固定任务文本：计算 7×8=56、12×3-8+5=33，或向临时 TextEdit 文档写入冻结的中英文字样。

## 数据目的地

- Jev `jev-1.13.0`：`https://api.typesafe.ai/v1/systemone`，接收结构化目标、AX 界面状态、动作候选及历史。
- Qwen `qwen3.7-flash-2026-07-15`：`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，接收任务/AX 状态/历史；A 基线还发送桌面截图。
- 凭据沿用既有环境配置，未写入配方、报告或审批问题。

## 冻结限制与验收

- 共享账本按冻结保守单价估算：预算上限 4 美元、最多 3660 请求，30M tokens；不是供应商账单承诺。
- 每 trial 240 秒，A max_steps=15；第三次 A timeout 停批。未知用量、未确认清理、取消、未解决的执行状态停批。
- 已知失败留在分母，初始模式/遮挡问题在模型前作为 environment_error 停批；所有 150 行保留。
- 预声明 H1–H4、固定任务配对统计与区间不变；不观察结果后改门槛，不自动切换生产默认。
- 同一输出目录仅允许执行一次；不覆盖历史失败产物。

## 授权与执行记录

自动审批拒绝了真实批次，理由是 150 次 GUI 试验将发送可能敏感的桌面派生数据到外部模型服务并产生费用，
而当前会话仅广义要求继续工作，未明确授权本批载荷和目的地。计划中的一般模型调用授权未被审批判定为足够。
2026-10-14 用户明确回复“允许上述数据导出并执行此150项批次”，覆盖以上数据（含整屏截图可能显示的其他内容）、两个服务和冻结收费范围，原审批阻塞解除。
未绕过拒绝、未换入口执行、未删 A 臂或放宽安全门。

[已验收的 fake](../20261014-s5-confirmatory-v2-fake-2/README.md)；[本地冻结配方](freeze.json)。
