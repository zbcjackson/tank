# S5 静态诊断总输出参数与预留：零收费验收

> 状态：2026-10-15 revision 4参数/预留修正及fake3/3完成，0新真实请求/GUI；完整验证5998/E2E18及本范围第3轮独立评审通过，0新真实请求/GUI/费用。

## 已修正的契约

上一批[新图真实结果](../20261015-s5-new-image-live/README.md)显示max_tokens=2048时
completion_tokens=3021（2952思考+69回答），触发原冻结bound_exceeded。
此前把max_tokens当总输出上限的假设有误，旧失败判分/账本原样保留。

[百炼兼容API文档](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/)
区分回答上限max_tokens和思考+回答总上限max_completion_tokens；Qwen3.5-Flash及之后
系列支持后者，且说明实际输出可能与设置值相差最多10tokens。新诊断仅发送
max_completion_tokens，预留其值+10；不同时发送两个上限字段，不改核心账本或生产profile。
精确快照/端点实际执行新参数尚未实测，fake线路通过不能取代provider验证或真实费用保证。

## 冻结与记账

签名`9a8f01e28caceeac1199be9b8c568ead2a6f488138a9cb722caf24167de5e972`，
revision=a-static-preflight-4，见[freeze.json](freeze.json)。图片/case/目标/提示/格式/
温度/思考开关/顺序/截止与上一诊断相同，仅更换共同输出上限语义及预留。
production_max_tokens_reference=40000仅记录原profile参考，不作为新输出边界。
output_contract冻结参数名、completion_tokens总量口径、10tokens余量、官方来源及未实测声明。

三组请求max_completion_tokens=40000/40000/2048，output allowance=40010/40010/2058。
沿用历史估算价格输入165/输出660nano-USD/token，输入预留991808tokens/请求，
各预留$0.190054920/$0.190054920/$0.165006600，总$0.545116440、3057502tokens，
仍在既有诊断模板$0.60/3100000tokens内。这些仅为新冻结契约估算，不是发票/真实账单上界证明。
没有本轮新live配方或预算授权，未用旧批未花额度，也未重放任何模型请求。

known最终completion_tokens在请求值+10以内即按实际计量；超过余量仍按实际known记账并
bound_exceeded停批，不能把已知超界当unknown。unknown保留完整新预留并停批，3行分母保留。
若完整回复在结算后被policy终止，保留failed和未评分默认值，不把其误称JSON非法或放行结果。

## 离线验收

[SDK+fake HTTP接线](result.json)3finished/3fake HTTP、0外部模型请求/0新GUI，
known合成7425nano-USD、reserved0、stop_reason=null。图是已见图片副本，仅检查线路，
固定fake错点不作质量统计。原图/载荷/账本/日志不提交，只跟踪此README。

新增7项回归先红后绿；含原SDK/格式/case/截止/用量及账本共289项通过。
- 实际官方SDK序列化只含max_completion_tokens，三个请求值正确，无max_tokens。
- completion位于请求值、+1、+10均已知结算；+11以实际计量bound_exceeded，reserved0。
- 缺用量保留首请求1031818tokens/$0.190054920预留，后两项not_run。
- 回放旧3021输出回执情形（合成数据），仍超2058，保留两finished/一failed及完整回复，
  实际known计量，不改判分或释放未知；改余量后旧freeze在client前拒绝。

backend/CLIruff、修改文件pyright0、web lint/tsc-b、E2E18场景/71steps及runtime error检查通过。
完整后端5998 passed/1 skipped/21 warnings（417.07s）、docs51/diff通过，
协议未改/sync不适用；本数据案例scope第3轮独立review-and-refactor通过，无actionable/unresolved finding、无代码修改；
评审重跑12项定向/docs51/diff、核对新冻结/预留/旧result哈希，立即结束，不开启第4轮，日志见[validation](validation/)。
旧解析器/旧preflight评审不重开，最后一行旧S5汇总修复的历史未复审状态不改变。

[完整性收据](budget-integrity.json)确认旧905c58ce签名被新源码拒绝、原result SHA
`d6ed1b62743be80d70b199962d93c7b9f3b077a5a52806ea0993c51d2c78c63e`保持。
这四个跟踪真实批次known$0.186779046+旧未知预留$0.380096640=$0.566875686保持；
旧thinking+max_tokens预留是假设下的旧账，不恢复成真实最坏金额保证。

## 下一步

另行预注册跨图/配对或平衡顺序的no-think候选验证，并在新冻结中明确总输出语义，
用真实请求验证参数接受/用量行为；当前不改生产默认、不声称关思考稳定改善。
S5/H1–H4、完整GUI任务和输入护栏仍未验收，不因fake通过重开150项。
