# S5 修复后真实确认批次：冻结执行预览

> 日期：2026-10-14；状态：已冻结，未执行；等待新收费批次预算授权。

源码基线`bbce7748`（driver修复`30967a9e`及一行长任务停批汇总修复）；
冻结签名`60fb55424f6caec77a9bee806df1a66d3837f16de1ff6586cdf3683dd023e2ea`。
本目录只有配方/预览，没有execution-started、行件或收费请求。

## 为什么需要新的批次

[原真实批次](../20261014-s5-confirmatory-v2-live/README.md)已按unknown_usage终止，
6 finished /144 not_run，原分母、旧失败与未知预留保留。驱动源码已修复，
原签名不能承载新源码，已启动目录的一次执行规则不允许补跑；本批是独立的新150项，
不是对旧批次覆盖或补齐，也不混合不同驱动版本作配对推断。
原授权针对旧冻结150项及按冻结单价估算的4美元；本批另需新增预算授权。

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
同签名的新[fake验收](../20261014-s5-confirmatory-v2-repaired-fake-2/README.md)结果另记，
fake只证明线路，真实确认H1–H4仍未判定。

[冻结配方](freeze.json)；执行命令仅在新预算授权后使用：

```bash
cd backend
UV_CACHE_DIR=/private/tmp/tank-s5-uv-cache uv run --no-sync python -m benchmarks.computer_use.s5_paired \
  --output benchmarks/computer_use/reports/20261014-s5-confirmatory-v2-repaired-live \
  --run live --approved-sha256 60fb55424f6caec77a9bee806df1a66d3837f16de1ff6586cdf3683dd023e2ea
```
