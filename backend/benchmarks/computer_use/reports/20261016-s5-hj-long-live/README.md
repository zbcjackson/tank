# S5 独立 H/J 长任务：冻结执行预览

> 状态：2026-10-16 新配方已冻结；157项相关回归通过，40项fake实机全部通过（H/J各20/20、420本地HTTP、0外部调用），完整6053/E2E18及lint/type/docs通过，第1轮独立评审无可操作问题、无源码修复即结束，10项针对性回归复核通过（评审状态补记由评审者自检）。真实未启动，新增$1.00估算预算待明确确认。

签名 **c8a4ae42d113035c6b42c5c7b9256e12cffdb0ca5c9684c5bbd922a68ca05e5b**，见[freeze.json](freeze.json)、
[fake验收](../20261016-s5-hj-long-fake/README.md)、[主计划](../../../../../docs/plans/active/computer-use-strategy-ladder.md)。
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

新增冻结估算上限 **$1.00 / 30000000tokens / 最多1400请求**，40项串行执行。
每任务240s、4000000tokens/$0.25；H最多25次文本请求，J最多20次Jev+25次文本请求。
SDK重试关闭。1400为所有任务的请求准入总上限，不是承诺发送数量；共享预算可能先耗尽。
Jev单次保守输入/输出预留65536/65536tokens，输入42nano、输出0；Qwen预留输入
991808/输出2048tokens，单价165/660nano。价格与输入上限继承历史冻结假设，
实际用量超界则停批；不把max_tokens假设或这些单价称为真实发票/最坏费用保证。

执行前历史真实known+held为 **$0.571501626**，其中unknown预留$0.380096640保持；
本新增$1.00获准后账本口径累计上限 **$1.571501626**。不转用旧未花额度，fake合成
费用不加入真实总额。预算是准入估算，不保证完成40项。

已知且经独立读回解决的任务失败保留分母继续；unknown用量/回执、环境错误、取消、
清理不确认则停止，保留全部40行和未运行项。中断不输出完整配对或L1–L3通过结论。
新增track在账本关闭失败时也降completed=false并尽力写出全分母结果，不宣称整盘
不可写时仍可落盘。每个目录有exclusive started标记，源码/配置/签名漂移拒绝运行；
不复用旧批次目录。共享源码扩展后旧签名仅保留历史证据，不改旧freeze或补跑旧结果。

## 命令（尚未执行）

完整验证、fake实机与独立评审通过，并明确确认本配方新增预算及上述数据/GUI范围后，
从backend执行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.s5_paired \
  --track hj-long \
  --output benchmarks/computer_use/reports/20261016-s5-hj-long-live \
  --run live \
  --approved-sha256 c8a4ae42d113035c6b42c5c7b9256e12cffdb0ca5c9684c5bbd922a68ca05e5b
```

凭据仅用现有core/.env的TYPESAFE_API_KEY、BAILIAN_API_KEY，不输出到日志/报告。
当前无started/result/账本，不含新的收费请求。
