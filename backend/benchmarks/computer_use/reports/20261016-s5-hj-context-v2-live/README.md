# S5 完整生产上下文 GUI：冻结执行预览

> 状态：2026-10-16 用户明确批准后同签名真实4/4项完成，H 1/2、J 2/2 strict/passed，未通过全4门；46请求全部known、估算$0.031331709，清理全确认。本结果范围第1轮独立评审无可操作问题、无事实修复即结束，docs51/diff通过（评审状态补记由评审者自检）；以下执行预览保留为执行前记录，禁止重跑此目录。

签名 **3e15225394068660f76ed7a0728bae82c44f5d6a5e0522cac9411259daf7ab58**，见[freeze.json](freeze.json)、
[fake验收](../20261016-s5-hj-context-v2-fake/README.md)、[主计划](../../../../../docs/plans/done/computer-use-strategy-ladder.md)。
track=hj-context，revision=s5-hj-context-1。它验证新版入口在原生产上下文中的端到端可行性，
不把此前简化上下文的6/6直接推广到原40项。

## 任务与完整上下文

固定4项：AXPress H→J，Quartz J→H；每项均为`12×3-8+5=33`，H/J各2项，repeat=0。
只在Calculator未运行时创建owned实例，确认基本模式、必要时移动/隐藏侧栏并清零；
模型在该窗口操作，AX独立读回表达式和结果，最后确认输入及应用/位置/前台清理。
已有实例则停止，不复用或关闭用户实例；运行时保持桌面空闲。同进程资源管理不等于
跨进程或用户输入互斥。原生产A和视觉候选不参与。

复用原H/J的AgentRunner上下文构造：应用约束、Clarification、安全规则与ENVIRONMENT。
完整context含平台、用户名及主目录路径字符串，**不读取这些目录中的私人文件**。
本机生成的context与原40项记录逐字一致，1426 UTF-8 bytes，SHA256为
`b466ab7aac448b0d633249305c067876ae14625ccd396bfad0d0f85dfa992238`；当前intake system
使用新版提示，schema/解析器为当前实现。每任务首个模型请求必须是逐字匹配冻结
intake messages的文本请求；不符则在SDK发送前以intake_context_mismatch停止。
base规则/平台上下文/源码或依赖版本漂移也会使freeze不匹配，不能直接运行。

发送任务文本、完整context、AX控件/状态及动作历史至
`api.typesafe.ai/v1/systemone`（jev-1.13.0）及
`dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`（qwen3.7-flash-2026-07-15）。
无截图上传，不使用Jev图片/Box。H为规则+Qwen选择器/Advisor；J同宿主同候选、Jev优先，
其余intake/Advisor相同；Qwen显式不思考、max_tokens=2048，Jev/SDK版本在freeze固定。

## 通过门与停止规则

仅完整4项均strict/passed、每项有模型选中且执行的动作、0规则违规及清理确认，
才给prepare_hj_long_confirmation，允许准备新的完整长任务比较；否则为
context_smoke_not_qualified。未知/operational停批则incomplete，不产生完整配对。
fake永不产生后续采用/完整实验准入结论。L1–L3/H4均null，统计检验为空；只记录
原始耗时/调用/费用和2对结果，不用N=4判断稳定性、速度或费用优势。

已知且独立读回解决的失败保留并继续，未知用量/回执、环境错误、取消、清理不确认
或上下文校验失败停批，保留全部4分母。账本关闭失败降incomplete并尽力保留记录；
整个存储失败时不能保证落盘。每目录exclusive started禁止重跑，源码改变须新目录。
历史40/150项、原A及H4不拼接、不重新判分。

## 预算与命令（执行前冻结记录，现已执行）

新增冻结估算 **$0.50 / 8000000tokens / 最多140请求**，4项串行。
单任务240s、400万tokens/$0.25，H最多25文本请求，J最多20Jev+25文本请求，SDK重试0。
沿用冻结保守token/价格合同：Jev预留65536输入+65536输出，单价42/0nano；Qwen
预留991808输入+2048输出，单价165/660nano。实际用量超界/未知则停批；这些是准入
估算，不是发票或真实最坏费用保证，不能保证所有任务都能在预算内完成。

执行前真实known+held **$0.624645324**，其中旧unknown预留$0.380096640不变；
新增$0.50获准后账本口径累计上限 **$1.124645324**。不转用旧剩余额度，不将fake费用
计入真实费用。执行前live只有freeze和说明，无started/result/spend。

完整验证及独立评审通过，并明确确认本配方新增预算、完整context外发及GUI范围后，
从backend执行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.s5_paired \
  --track hj-context \
  --output benchmarks/computer_use/reports/20261016-s5-hj-context-v2-live \
  --run live \
  --approved-sha256 3e15225394068660f76ed7a0728bae82c44f5d6a5e0522cac9411259daf7ab58
```

凭据仅用现有core/.env的TYPESAFE_API_KEY、BAILIAN_API_KEY，不输出到日志。

## 真实结果与结论

用户对上述明确范围回复“批准”后，按原签名执行一次，4项均finished、无not_run。
AXPress：H失败，J成功；Quartz：J、H均成功。H strict/passed=1/2，J=2/2；
三个成功项独立AX均读回expression=`12×3-8+5`、result=`33`。四项均有模型动作
实际执行，输入及应用/位置/前台清理全确认，0规则违规、0截图。

四项首个实际intake messages均逐字等于冻结消息，intake均生成inputs=[]、
completion present=33；本批没有重现旧40项共同入口失败。它说明这4次完整生产
context入口可用，不能据此证明提示修复的因果效果或长期可靠性。

H的AXPress失败发生在动作选择阶段：共14条派发回执、16次文本请求（intake 1、
selector 11、Advisor 4）。第5步Subtract后显示`12×3-`，第6步selector直接选Add，
显示变成`12×3+`，跳过8；Advisor选5后Equals得到41。随后All Clear，恢复中
Advisor从2开始，selector输入减号、8，之后Clear/All Clear又归零，最终
partial/advisor_limit；独立读回result=0。没有将这个已知失败抹除、重跑或改判。
这些记录支持“动作规划/恢复失误”，尚未建立通用宿主缺陷或AXPress通道故障。

总46请求（32文本+14Jev），265363 known tokens、估算 **$0.031331709**，
reserved=0、stop_reason=null、0新unknown；H $0.022557810/42.154s，
J $0.008773899/33.310s，只作描述。旧unknown预留$0.380096640保持，
累计known估算 **$0.275880393**，known+held **$0.655977033**。
未花预算不自动转用；金额沿用冻结单价估算，不是发票。

冻结全4门未通过，结论为 **context_smoke_not_qualified**；本批不准入新的完整
长任务确认。2个原始配对保留，推断统计为空，L1–L3/H4均null。J 2/2不能证明
Jev稳定性、准确率或净收益，也不与旧40/150项拼接比较。

[result.json](result.json) SHA256：
`7608d1dd4dc2ff3078d9972028fdd98227117d81aef7788b718a775bf4f002ff`。
原始消息、回执、账本及结果仅本地保留。本次没有源码修改，沿用未变源码已通过的
完整6087/E2E18验证；本结果范围执行docs检查与独立评审。

下一步先零收费离线回放H失败链，核对selector/Advisor当时的任务、候选和语义历史，
确定是否有通用且可复现的信息缺口，再决定最小修复或按能力边界收口。
不提高Advisor上限来掩盖失败，不直接扩大真实样本；Jev图片仍后置，G3/S6未完成。

## 2026-10-17 零收费离线诊断

仅读取原结果并检查现行序列化/解析及控制流，没有新模型请求、GUI动作或费用，
原result SHA与费用不变。4条intake实际消息再次匹配冻结；其余28条文本请求
（18 selector、10 Advisor）的回复按生产JSON解析路径校验，均属于当时提供的
选项或合法AdviceReply，且每条goal.intent均保持完整任务。14条Jev请求未在本次
文本回复校验中重放；本次也没有重新执行控制器或重新抽样模型。

**选择失误的输入证据**：H第6步选Add时，payload含完整原算式及第1–5步
`1 → 2 → Multiply → Advisor:3 → Subtract`和对应已核验读数变化；当前读数
`12×3-`。同一问题明确提供c6=8、c16=Add，模型实际返回c16。未发现该步缺少
目标、近期历史、8候选或别名映射错误，不能用“再补上这些信息”作为已证实修法。

**恢复边界**：第四次Advisor给出focus，要求读数0、表达式为空。selector先选Clear、
再选All Clear，两步后focus_history确实记为completed/focus_verified。focus完成
不等于原算式完成；返回初始0状态后触发repeated_state，下一次规划复核在发送前
命中advisor_limit。不是focus丢失、未被读取或错误宣告任务成功。
这与现行[设计](../../../../../docs/design/computer-use.md)的“重访状态请求有界修复、
最多4次Advisor、focus不重置原任务计数”一致。它揭示清零恢复仍受原额度约束的
能力边界，但不证明应放行重复状态、清零预算或增加额度；也不证明放行后会成功。

现有test_ladder.py的focus/有界规划回归 **12 passed、82 deselected**（2.24s），
覆盖focus完成、三动作过期、重复状态失效及Advisor额度不重置；它们不是本条真实
动作链的控制器逐步重放。日志`/private/tmp/tank-hj-offline-recovery-tests.log`；
原始请求/回复核对摘要`/private/tmp/tank-hj-offline-diagnosis.json`，均仅本地保留。
临时校验最初误用严格Python对象校验导致list/tuple错误，已改为与生产相同的
model_validate_json并通过；该探针错误不属于生产缺陷。

本片不改源码/提示/上限或成功标准，不发新的收费批次；S5全4门失败保持，现有证据
不足以采用Jev。下一步准备原计划G3第一片：同一挂起任务等待用户输入后继续，
保持授权、累计费用/动作/观察/回执和期限。已核对当前SubAgentContext无等待原语，
Supervisor仍拒绝插件resume，控制器缺值仍返回needs_input终态；focus恢复不替代G3。
等待期间桌面锁、原期限和单字段回填三项设计取舍仍需在实施准备中处理；本片没有
实施它们，也未将S5或G3/S6标为完成。诊断文档docs51/diff通过；本报告新增诊断第2轮独立评审未发现可操作问题，无事实修复即结束（评审状态补记由评审者自检）。
