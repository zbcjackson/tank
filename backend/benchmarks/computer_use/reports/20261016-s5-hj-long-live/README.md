# S5 独立 H/J 长任务：冻结配方与真实结果

> 状态：2026-10-16 新配方已冻结；157项相关回归通过，40项fake实机全部通过（H/J各20/20、420本地HTTP、0外部调用），完整6053/E2E18及lint/type/docs通过，第1轮独立评审无可操作问题、无源码修复即结束，10项针对性回归复核通过（评审状态补记由评审者自检）。用户回复“开始”后原签名真实40项已结束，H 1/20、J 4/20 strict，L2未通过；97请求全known，估算$0.050185908，清理全确认。禁止重跑本目录。

签名 **c8a4ae42d113035c6b42c5c7b9256e12cffdb0ca5c9684c5bbd922a68ca05e5b**，见[freeze.json](freeze.json)、
[fake验收](../20261016-s5-hj-long-fake/README.md)、[主计划](../../../../../docs/plans/done/computer-use-strategy-ladder.md)。
使用 `s5_paired --track hj-long`，revision=s5-hj-long-1。

## 样本与公平对照

固定Calculator `12×3-8+5=33`，AXPress与Quartz各10次，每次H/J相邻配对，共40项，
H/J各20项。按重复编号和通道交替先手，每通道H/J各先手5次；repeat=1按原策略移窗。
H为规则+Qwen选择器/Advisor；J同宿主、相同候选/规则/目标和intake/Advisor，选择器为
Jev优先、同候选Qwen回退。模型固定 `jev-1.13.0` 与 `qwen3.7-flash-2026-07-15`，
Qwen显式enable_thinking=false、max_tokens=2048，单任务最多20次决策。

每项新建owned Calculator，确认基本模式并清零，只操作该实例，独立AX读回必须同时
匹配表达式与结果；结束时确认应用、输入清理。已有Calculator实例则停止，不复用或关闭。
操作期间需保持桌面空闲；本机Runner资源锁不宣称跨进程或用户输入互斥。
无A调度或A驱动，不进行视觉定位、截图上传。共享freeze中保留的A配置仅为原harness
参照，不产生A分母或比较；历史原A/150项和H4不拼接、不追认通过。

发送任务文本、AX控件/状态、动作历史及intake/Advisor结构化消息至既有
`api.typesafe.ai/v1/systemone`（Jev）和
`dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`（Qwen）。
不发送截图，fake仅替换模型HTTP；本配方不测试Jev图片/Box能力。

## 独立门槛 L1–L3

仅完整40项已知结算并清理确认后评估：

- L1：J/H总任务耗时≤1.10；总耗时包含应用setup、执行及cleanup。
- L2：H与J均至少18/20次strict成功，J≥H−1，且两臂无规则违规。
- L3：J的全部模型估算费用<H，包括intake、选择器和Advisor。

三项全过为long_task_point_gates_passed；质量与费用过、耗时不过为long_task_cost_only；
其余为long_task_no_joint_gain。H4=null，不提供旧H1–H4结论；fake的L1–L3均为null。
每通道报告10对；时间/费用跨通道按repeat均值形成10个block，质量使用精确配对描述，
给出原有区间与差值。相同算式重复不是20种独立任务，也不证明统计非劣或总体泛化；
达到点门槛只支持该受控场景后续试用建议，不自动切换生产配置。

## 预算与停止规则

本批获准冻结估算上限 **$1.00 / 30000000tokens / 最多1400请求**，40项串行执行。
每任务240s、4000000tokens/$0.25；H最多25次文本请求，J最多20次Jev+25次文本请求。
SDK重试关闭。1400为所有任务的请求准入总上限，不是承诺发送数量；共享预算可能先耗尽。
Jev单次保守输入/输出预留65536/65536tokens，输入42nano、输出0；Qwen预留输入
991808/输出2048tokens，单价165/660nano。价格与输入上限继承历史冻结假设，
实际用量超界则停批；不把max_tokens假设或这些单价称为真实发票/最坏费用保证。

执行前历史真实known+held为 **$0.571501626**，其中unknown预留$0.380096640保持；
本新增$1.00获准时账本口径累计上限 **$1.571501626**。不转用旧未花额度，fake合成
费用不加入真实总额。预算是准入估算，不保证完成40项。

已知且经独立读回解决的任务失败保留分母继续；unknown用量/回执、环境错误、取消、
清理不确认则停止，保留全部40行和未运行项。中断不输出完整配对或L1–L3通过结论。
新增track在账本关闭失败时也降completed=false并尽力写出全分母结果，不宣称整盘
不可写时仍可落盘。每个目录有exclusive started标记，源码/配置/签名漂移拒绝运行；
不复用旧批次目录。共享源码扩展后旧签名仅保留历史证据，不改旧freeze或补跑旧结果。

## 已执行命令（仅供审计，禁止重跑）

完整验证、fake实机与独立评审通过，用户对本配方新增预算及上述数据/GUI范围回复
“开始”后，已从backend执行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.s5_paired \
  --track hj-long \
  --output benchmarks/computer_use/reports/20261016-s5-hj-long-live \
  --run live \
  --approved-sha256 c8a4ae42d113035c6b42c5c7b9256e12cffdb0ca5c9684c5bbd922a68ca05e5b
```

凭据仅用现有core/.env的TYPESAFE_API_KEY、BAILIAN_API_KEY，不输出到日志/报告。
现有started/result/账本均保留，不复用此目录或剩余额度。


## 2026-10-16 真实结果：质量门槛未通过

执行前后freeze/source匹配原签名。40/40行为finished、completed=true表示全部记录
已知结算并清理，不表示任务均成功。H strict/passed=1/20（5%），J=4/20（20%），
无规则违规；40项输入/owned应用清理均确认。无A行，H4=null，旧150项不拼接补判。

原冻结门槛的机械判定：

- L1=true：H总任务150.996s，J153.958s，J/H=1.019615（J慢约1.96%），在1.10内。
- L2=false：每臂至少18/20的门槛均未达到，虽然J≥H−1且两臂均无规则违规。
- L3=true：H估算$0.026457420，J估算$0.023728488，J少约10.31%。
- 总结论 **long_task_no_joint_gain**，不能给出Jev采用建议。

完整20对和10个repeat block已按冻结方法保存，但**双方均strict成功的配对为0**。
34项在共同intake阶段就结束，只有6项进入动作阶段；总耗时/费用包含大量提前结束
任务及setup/cleanup，不能把L1/L3通过当成成功长任务中的速度/成本优势，更不能把
1/20与4/20当作模型自身准确率或稳定性。两臂共同intake都是Qwen，并非Jev在该阶段决策。

### 失败分布与可复核原因

H：18项needs_input/ungrounded_input、1项goal_verified成功、1项partial/
focus_already_satisfied（独立读回result=12×3-8，尚未完成）。
J：15项needs_input/ungrounded_input、4项goal_verified成功、1项stopped/invalid_intake。
33+1项intake失败均只有一次文本调用，零模型动作，receipt为空；不属于桌面派发失败。

已将33份原始brief按当前recover_inputs/grounded离线复核：模型把计算器按键动作放入
inputs，而宿主要求inputs.value能在用户原文中找到。未绑定值的组合分别为：
`('*', '=')` 15项、`('*3', '=')` 9项、`('*3', '+5=')` 9项。
原文使用乘号×，且没有这些完整字符串，因此来源校验按现有契约拒绝。
这说明动作与用户填充值的边界有问题，不应通过放松任意输入的原文校验掩盖。

1份invalid_intake为完整JSON围栏回复；仅离线剥离围栏后，它仍含未绑定的`*3`/`+5=`，
会被grounded拒绝。此为诊断，未重新判分；单独兼容围栏不足以解决主因。
`summary.intake_calls`为成功产出brief的任务数（H2/J4），不是实际intake HTTP次数；
本批每项均发起一次intake，共40次，调用与费用以97份capture及共享账本为准。

### 费用、证据与后续

共97次真实模型请求：H 41文本；J 28文本+28Jev；实际调用记录image_url/assets字段为0。
425531 known tokens，已知估算
**$0.050185908**，reserved=0、stop_reason=null、无新unknown或重试。
历史unknown预留$0.380096640保持；加本批后真实known+held累计 **$0.621687534**，
其中known估算$0.241590894。以上为冻结价格的契约估算，不是供应商发票金额。
未花额度不转用，不在本目录改提示/源码后补跑。

[result.json](result.json) SHA256：
`98e46670f9bc2b989b681c9e3dd5837a3588a38181633aea252f18b6f9dbbd0f`。
40分母、20配对、用量/逐臂费用求和、所有清理字段与freeze已核对。原始请求、回复、
rows/audit/spend在本目录本地保留；源码/配置未改，本次仅结果归档，不重复完整代码测试。

下一步：先修共同intake的动作/按键与用户填充值区分，保留真实填充值的来源约束；
用这些已归档失败样本做离线回归，评估JSON围栏问题，并保留那1项H动作阶段失败作为
独立反例。验证入口稳定后另冻结新的诊断/配对批次；不剔除本批失败来重算采用结论。
Jev图片/Box仍后置，G3/S6仍未完成。本结果归档检查与评审记录见主计划。
