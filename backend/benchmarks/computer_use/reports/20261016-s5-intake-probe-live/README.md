# S5 intake 提示探针：冻结执行预览

> 状态：2026-10-16 已冻结，同签名12/12 fake接线通过；完整6077/E2E18及lint/type/docs通过，第1轮独立评审未发现可操作问题，复跑62项相关测试通过。真实未启动，新增$0.25/12请求预算待明确确认。

签名 **7db134946fab4722c65203f8517e8cf3513f17faba254b4fa852172dd7424fe3**，见[freeze.json](freeze.json)、
[fake验收](../20261016-s5-intake-probe-fake/README.md)、[主计划](../../../../../docs/plans/active/computer-use-strategy-ladder.md)。

## 目的与控制变量

检验新提示是否让模型正确区分按键动作和文字填充值。两个任务各做旧/新提示3次，
共12次Qwen请求，按题与重复编号交换先后，总体两臂各先手3次；每题2/1先手互补。
Calculator任务文本沿用原长算式；TextEdit为合成字面文本 `*3 +5=` 加单个末尾换行，
只问模型如何构造TaskBrief，不启动或操作任何应用。

旧system提示取自原40项记录；两臂**均使用当前同一schema/解析器**，只有system不同。
上下文统一为单应用约束，没有原始安全说明/用户目录等上下文；因此不是原40项网络载荷
重放，不能与旧结果合并或据此单独判断围栏兼容的收益。消息由生产intake_messages构造，
parse_brief处理；新解析器仅接受裸JSON或单个完整json/LF围栏，来源约束不放宽。

只将这两段受控任务文本、单应用context、目标bundle ID与TaskBrief schema发送到
`dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，使用固定
`qwen3.7-flash-2026-07-15`、temperature=0、enable_thinking=false、max_tokens=2048。
不发送截图、AX信息或旧批次原始上下文，不调用Jev，不运行GUI。评分expected字段不进入
网络载荷；任务文本中用户明确给出的目标33/字面文本属于任务本身。

## 判定与停止

- Calculator：目标application正确、inputs为空、唯一completion为present=33。
- TextEdit：application正确、唯一input.value与唯一present completion均精确等于
  `*3 +5=`加一个末尾换行；原文绑定必须通过。不能省略换行、改空格或将文字当动作删除。
- 只有完整12项全部已知结算且新提示6/6严格通过，才允许准备新的GUI验证。
  旧臂也通过时不宣称有提示增量收益；每题仅3次，不能证明稳定性或直接采用。
  两臂都失败则保留诊断，不在同批调提示/阈值或追加样本。

完成的文本回复若解析或任务判定失败，记录为已知失败并继续。model_error（包括未完成
回复/拒绝/工具调用）、网络/运行时错误、取消、未知用量或超界则停批，保留12分母及
未知预留。每次最多一个SDK请求、零重试、60s截止；关闭客户端失败保留证据并结束。
完整存储失效时不能保证落盘。fake永不输出prepare_gui_validation。

## 新预算与执行

新增冻结估算 **$0.25 / 12000000tokens / 最多12请求**，每请求独立trial上限
$0.20/1100000tokens，共享持久账本。Qwen输入保守上限991808tokens，输出预留2058
（请求2048，留10余量），冻结单价输入165/输出660nano，单次预留$0.165006600。
预算是准入估算，可能先于12请求耗尽，不保证完成，也不是供应商发票或实际最坏金额保证。

历史真实known+held **$0.621687534**（含旧unknown预留$0.380096640）保持；
新增$0.25获准后按账本口径累计上限 **$0.871687534**。不挪用旧批次未花额度，
fake合成费用不加入真实账目。当前live目录无started/result/spend。

完整验证和独立评审通过，并明确确认本新配方预算和文本外发范围后，从backend运行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.intake_probe run \
  --output benchmarks/computer_use/reports/20261016-s5-intake-probe-live \
  --mode live \
  --approved-sha256 7db134946fab4722c65203f8517e8cf3513f17faba254b4fa852172dd7424fe3
```

凭据仅使用既有core/.env的BAILIAN_API_KEY，不写入日志。源码/数据/配置/SDK版本漂移
拒绝执行；exclusive started标记禁止重复运行。原40项评分及原始产物不改。

第1轮review-and-refactor未修改源码或测试，无问题即结束；上述评审状态补记由评审者自检。
