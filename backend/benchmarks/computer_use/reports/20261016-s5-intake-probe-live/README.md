# S5 intake 提示探针：冻结配方与真实结果

> 状态：2026-10-16 已冻结，同签名12/12 fake接线通过；完整6077/E2E18及lint/type/docs通过，第1轮独立评审未发现可操作问题，复跑62项相关测试通过。用户明确确认后原签名12请求完成：新提示6/6、旧提示4/6，达到准备GUI验证门槛；无GUI/新unknown，估算$0.002957790。禁止重跑本目录。

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

本批获准冻结估算 **$0.25 / 12000000tokens / 最多12请求**，每请求独立trial上限
$0.20/1100000tokens，共享持久账本。Qwen输入保守上限991808tokens，输出预留2058
（请求2048，留10余量），冻结单价输入165/输出660nano，单次预留$0.165006600。
预算是准入估算，可能先于12请求耗尽，不保证完成，也不是供应商发票或实际最坏金额保证。

执行前历史真实known+held **$0.621687534**（含旧unknown预留$0.380096640）保持；
新增$0.25获准时按账本口径累计上限 **$0.871687534**。不挪用旧批次未花额度，
fake合成费用不加入真实账目。现有started/result/spend均保留，禁止重用本目录。

以下为已执行命令，仅供审计，禁止重跑。用户对本配方预算及文本外发范围明确回复“确认”后，从backend执行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.intake_probe run \
  --output benchmarks/computer_use/reports/20261016-s5-intake-probe-live \
  --mode live \
  --approved-sha256 7db134946fab4722c65203f8517e8cf3513f17faba254b4fa852172dd7424fe3
```

凭据仅使用既有core/.env的BAILIAN_API_KEY，不写入日志。源码/数据/配置/SDK版本漂移
拒绝执行；exclusive started标记禁止重复运行。原40项评分及原始产物不改。

第1轮review-and-refactor未修改源码或测试，无问题即结束；上述评审状态补记由评审者自检。


## 2026-10-16 真实探针结果

用户先回复“下一步”时执行被自动审批拒绝，已核对0请求/无started；随后对具体
$0.25、12请求及文本/schema至Qwen范围明确回复“确认”，原签名执行一次。
执行前后源码/冻结一致；12/12 finished、completed=true、全known，0 fake HTTP/GUI。

冻结严格判定结果：

- legacy：Calculator 3/3，literal-text 1/3，合计4/6。
- revised：Calculator 3/3，literal-text 3/3，合计6/6。
- verdict=**prepare_gui_validation**，仅允许准备新的GUI验证，不代表修复已全面验证。

两个legacy失败均为literal-text的repeat 0/2：**inputs.value本身已保留正确的末尾换行**，
只是completion.present输出`*3 +5=`，少了最后的LF；预注册要求输入和完成条件都精确
等于`*3 +5=`加一个LF，因此仍判失败。不能将它解释成已经观察到TextEdit正文丢换行，
本试验没有操作任何编辑器。新提示三次的输入和完成条件均逐字符匹配。

Calculator两臂均生成inputs=[]、present=33，均3/3。**本批没有复现原40项中的
Calculator入口失败，也没有显示该题新提示优于旧提示。** context已简化、两臂都使用
当前解析器、每题样本仅3次，不能把旧批到本批的差异归因于prompt修复。两臂都没有
JSON围栏回复，所以本批也不单独验证真实模型的围栏兼容收益。

每条实际messages与对应冻结消息完全一致。legacy六请求合计13.748s、估算$0.001409595；
revised合计14.681s、估算$0.001548195，仅作记录，不作速度/费用优势推断。
总12352 known tokens、估算 **$0.002957790**，reserved=0、stop_reason=null，
无重试或额外请求。旧unknown预留$0.380096640保持；加本批后历史真实known+held
合计 **$0.624645324**（known估算$0.244548684），不将未花额度转用。
费用均为冻结单价的契约估算，不是实际发票。

[result.json](result.json) SHA256：
`dc6fe2c97a4291f19a03c87b9ac558bc066369e2682a9fac9e7c0529ecf34e7f`。
12分母、请求参数/消息、评分、逐trial费用与总账求和已复核。原始产物保持，旧40项
评分不改；本次无源码/配置改动，仅归档结果并进行文档检查及结果范围评审。

下一步准备小规模端到端GUI验证：恢复原H/J的完整生产上下文（而非本探针的简化context），
覆盖AX/Quartz，验证新版入口能否正确交给选择器并完成原长算式及清理。保留原入口失败
与H动作阶段反例；先明确新小批次的样本、验收和预算再执行。只有这一步通过，才考虑
新的完整长任务配对。当前不作Jev净收益或稳定性结论，Jev图片仍后置，G3/S6仍未完成。
