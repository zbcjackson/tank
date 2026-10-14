# S5 修复后真实确认批次：按未知用量停批

> 日期：2026-10-14；状态：经明确授权执行；6 finished / 144 not_run，unknown_usage停批，确认未完成。

源码基线`bbce7748`（driver修复`30967a9e`及一行长任务停批汇总修复）；
冻结签名`60fb55424f6caec77a9bee806df1a66d3837f16de1ff6586cdf3683dd023e2ea`。
授权前本目录只有配方/预览，没有execution-started、行件或收费请求；
获准后同签名命令执行一次并按规则停批；完整行件和账本保留，没有重放未知请求或补跑目录。
2026-10-14用户明确回复“允许新增4美元预算并执行”，授权覆盖本预览的新150项，
数据范围沿用原明确授权；累计冻结估算/预留最坏约4.288129786美元。

## 本次执行结果

- 150项全分母保留：6 finished / 144 not_run；仅首重复两个短计算任务。
  A 0/2、H 2/2、J 2/2 strict；TextEdit与长任务未执行。
- 48外部请求（Qwen42/Jev6），47条usage已知、1条未知；已知468,736 tokens。
  6项App清理及2项A输入清理确认，窗口位置/前台恢复确认。
- 新批已知冻结估算$0.081382470，未知仍预留1,031,808 tokens/$0.190048320，
  合计占用$0.271430790。旧批占用$0.288129786保持；两批合计$0.559560576，
  其中已知估算$0.179463936、未知预留$0.380096640，均不是供应商实际账单。
- 停止原因unknown_usage，不是预算耗尽或第三次A timeout；本批A仅1次timeout。
  结论incomplete_no_confirmatory_conclusion，配对统计为空，H1–H4未判定；
  JSON中的false是incomplete分支占位，不能解释为四个假设被否定。

## 修复生效与仍存的阻断

首个A已完成15个工具、15次模型请求，138.434s后max_steps停止，未再发第16次请求，
unknown_calls=0、清理确认、独立读回0。新收尾修复已在真实执行中生效。

第二个A只执行12个工具、13次模型请求；第12次模型调用耗时132.800s、输出6,809 tokens，
在189.131s结算为known。下一请求`2162771f13db4f4e981bc41fa89ead5e`于189.284s发起，
约50.717s后被240s总截止取消，最终input/output usage均缺失。SDK finished=unknown、
driver timed_out=true/unknown_calls=1与账本一致，清理确认，独立读回0。
这次未知发生在步数上限之前，不能再归因于旧“15步后多发请求”的缺陷；修复没有承诺
阻止所有在途流超时。也没有证据据此断言供应商漏计费，完整合同预留继续保留。

当前两项短任务H/J均完成7×8=56；J已知费用更低、总时延相近，仅为小样本观察。
长任务时延摊薄与总体非劣/净收益未测，不切换生产默认、不拼接不同源码版本作正式配对。
下一步先做不收费的A长推理/定位及请求截止配置审计，再定义新的冻结控制方案；
不直接原样重付费，不放宽unknown门、不擦除预留，也不删除A失败或事后改H1–H4。

原始[result.json](result.json)、[rows.jsonl](rows.jsonl)、[spend.jsonl](spend.jsonl)、
[audit.jsonl](audit.jsonl)、[freeze.json](freeze.json)及trials保留；原始截图/模型载荷不提交。
日志`/private/tmp/tank-s5-confirmatory-v2-repaired-live.log`。

## 为什么需要新的批次

[原真实批次](../20261014-s5-confirmatory-v2-live/README.md)已按unknown_usage终止，
6 finished /144 not_run，原分母、旧失败与未知预留保留。驱动源码已修复，
原签名不能承载新源码，已启动目录的一次执行规则不允许补跑；本批是独立的新150项，
不是对旧批次覆盖或补齐，也不混合不同驱动版本作配对推断。
原授权针对旧冻结150项及按冻结单价估算的4美元；本批新增预算已于2026-10-14获用户明确授权。

## 收费范围

- 新批次按冻结单价估算上限4美元、30M tokens、3660请求；每trial上限0.25美元/4M tokens，
  240秒，A最多15个工具；最后工具返回后不再发下一轮模型。
- 旧批已知估算0.098081466美元、未知预留0.190048320美元，合计仍占用0.288129786美元。
  批准新增4美元意味着累计冻结估算/预留最坏约4.288129786美元；不把未知预留当退款，
  不把这些合同估算当供应商实际账单。
- 未知usage、未确认清理、取消、未解决执行状态即停；第三次A timeout停批。
  隔离门、成功标准、H1–H4及失败分母不放宽。

## 试验与既有数据授权

五任务×十重复×A/H/J，共150：短算式7×8=56的AXPress/Quartz、临时TextEdit正文替换、
长算式12×3-8+5=33的AXPress/Quartz。仅新建owned Calculator/临时TextEdit，
保留完整清理与独立读回。Jev生产默认仍禁用，本批不自动更改默认。

数据范围沿用已明确授权的范围：任务文本、AX控件/状态/操作历史发送到
`https://api.typesafe.ai/v1/systemone`（jev-1.13.0）及
`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`
（qwen3.7-flash-2026-07-15）；A还发送可能包含其他可见应用内容的桌面截图至Qwen。
凭据沿用本地环境，不进入配方或报告；不向其他目的地导出。

## 验证与限制

完整后端5929 passed/1 skipped、E2E18场景/71步、改动文件pyright/lint及docs检查通过。
新driver/test独立评审首轮无问题；原S5准备已完成三轮，随后一行汇总缺省键修复
先红后绿并通过完整验证，未再次独立复核，不宣称有第四轮。
零模型实机预检从AX取得正确位置，经生产坐标工具计算7×8=56，清理确认，
仅证明坐标链，不作为视觉模型成功或Jev收益样本。
同签名的新[fake验收](../20261014-s5-confirmatory-v2-repaired-fake-2/README.md)150/150通过，
fake只证明线路，真实确认H1–H4仍未判定。

[冻结配方](freeze.json)；以下为已执行一次的原冻结命令；目录已经终止，不再执行：

```bash
cd backend
UV_CACHE_DIR=/private/tmp/tank-s5-uv-cache uv run --no-sync python -m benchmarks.computer_use.s5_paired \
  --output benchmarks/computer_use/reports/20261014-s5-confirmatory-v2-repaired-live \
  --run live --approved-sha256 60fb55424f6caec77a9bee806df1a66d3837f16de1ff6586cdf3683dd023e2ea
```
