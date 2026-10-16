# S5 两图候选门：冻结配方与真实结果

> 状态：2026-10-16 用户明确确认截图外发及新增 $0.70 估算预算后，原签名真实四请求完成；no-think 2/2 命中，候选门通过，仅进入 owned GUI 短任务准备。估算费用 $0.004225320，0 未知预留、0 GUI 操作；不可重跑本目录。

总目标为回到S5 A/H/J完整任务取舍、Jev长任务摊薄确认，本批只回答no-think候选在
受限资源下能否跨两个位置定位。不是生产采用实验，也不修改原H1–H4。
[计划与收敛路径](../../../../../docs/plans/active/computer-use-strategy-ladder.md)。

## 固定数据与四请求

使用[来源与清理记录](../20261015-s5-cross-image-source/README.md)的两张新图，
预先同步AX+目视标注，均1920×1080、Calculator按钮7、20px半径：
[图1](image-1/frame.png)中心(214,371)，[图2](image-2/frame.png)中心(1434,811)。
两图SHA分别为
`7b9c5d15c7af0d1c78cc29d8fa83a47dbc3c6e385b34047da05bd61e221590f1`、
`cb4dc27c36a3bc719775a4e30a554875576741de1c09cd211e3243acf063ae8a`。
图中含其他可见应用的会话正文/侧栏；执行将整图、目标文本和共同提示送至既有
`dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，标注/AX真值不送模型。
准备阶段未发送图片；2026-10-16 用户明确确认本批整图外发及预算后执行。原始图/载荷本地保留不提交。

签名 **e8de037d329dc7631ce2d76130d4b5e8e9073456d969809574b7147cd94c8dae**，
[freeze.json](freeze.json)，revision=a-cross-image-1。固定顺序：

1. 图1 default（省略enable_thinking，观察实际reasoning）。
2. 图1 no-think（enable_thinking=false）。
3. 图2 no-think。
4. 图2 default。

Qwen3.7-Flash-2026-07-15、temperature0.1、stream/include_usage、图片high及共同提示
保持；总输出均max_completion_tokens=2048、allowance2058，不发送max_tokens。
[官方参数依据](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/)
支持总输出语义及10token余量，但精确端点/快照实际执行仍需观察；低于上限正常返回
只证明请求被接受，不能声称已触发/验证截断上限。记录原始SDK参数、parsed chunks、
finish_reason、reasoning、最终usage及坐标误差。没有输入工具，不创建应用或新抓图。

## 停止、候选门与回归主线

四项共享一个持久账本，SDK重试0，单请求180s，最多4次。
unknown、网络/截止/超余量/持久化等operational错误立即停全批；当结果路径仍可写时，即使账本关闭失败也保留四行incomplete报告并继续抛错，
未知预留不释放（若整个存储不可写则不能保证报告落盘），
无完整pairs/候选结论。完整known回复的错点、弃权、格式失败和length作为本行失败继续，
因为本批不派发输入；这仅是本新配方预声明，不修改旧批停批或判分。

completed指四项都attempted且settled known、没有operational stop，不代表四项都命中。
只有完整批且no-think两图都schema合法/命中，才给advance_to_owned_gui_smoke_preparation；
它仅允许准备一次受控GUI短任务，需先验证frame/owned点/键盘前台护栏，不自动执行输入。
完整批未满足门槛则candidate_not_qualified；中断incomplete。fake永不生成候选建议。

N=2图/单次、同应用近似背景，仅平衡先后，不足以证明稳定延迟/质量、泛化或Jev净收益；
时间/冻结费用作图内成对差描述，无显著性采用检验。总输出2048是本批资源条件，
不能将default截断说成其无预算下的质量缺陷。无需四项都格式正确才完成观测。
**本批之后不追加同图调参或同类静态筛选**：门槛通过转护栏/GUI短任务，再回长任务/配对
确认；未通过结束no-think静态候选支线，保留原A和失败证据，继续H/J长任务主问题。
生产默认/原S5统计不变，最终可能采用或不采用Jev。

## 新预算与验收

已批准本批冻结估算上限 **$0.70 / 4000000tokens**，最多4请求。按历史估算输入
991808tokens×165nano、输出2058×660nano，每请求预留$0.165006600，四项合计
$0.660026400 / 3975464tokens；预留/价格为契约估算，不是当前发票或真实最坏金额证明。
旧四批账本known+unknown预留占用$0.566875686保持，新$0.70批准后按账本口径累计
上限$1.266875686；不转用旧未花额度，不释放未知/重放旧请求。

同签名[fake验收](../20261015-s5-cross-image-v2-fake/README.md)4/4、0external/新GUI，
原单请求路径共用且旧invalid_reply规则回归通过。相关302项、lint/type/web、
E2E18/71与runtime检查通过；完整后端6013 passed/1 skipped/21 warnings（421.99s）、docs51/diff通过，
协议未改/sync不适用，本新跨图调度R1修复完整验证通过、第2轮复核通过（无新增/遗留问题，立即结束）。
准备时本目录无 started/result/账本；现已生成，真实结果见下节，不应将 fake 当真实模型结果。

以下为已执行命令，仅供审计；本目录已启动，禁止再次运行：

```bash
uv run --no-sync python -m benchmarks.computer_use.a_cross_image run \
  --output benchmarks/computer_use/reports/20261015-s5-cross-image-v2-live \
  --mode live \
  --approved-sha256 e8de037d329dc7631ce2d76130d4b5e8e9073456d969809574b7147cd94c8dae
```

凭据只用既有core/.env BAILIAN_API_KEY，标记文件禁止重复执行，源码/图片/case变化须新目录。

## R1收尾修复与版本归档

第1轮评审发现原finally先ledger.close，持续journal fsync失败会跳过四行报告保存；
新增故障回归先红后绿，ca30d4e2仅修新调度finally与2项回归：settlement故障或4项完成后
close故障，结果路径可写时仍保存四行、completed=false/incomplete并继续抛错。
原4e5379配方目录/raw保留但source_changed，不补改旧freeze；当前v2以同两图重新prepare，
没有新GUI/模型请求，不改旧数据结果或输出预留。第2轮独立复核待完成。

第2轮实际复跑15项定向/docs51/diff并核对新旧冻结/原始来源，未再改源码。
R1由修复作者再次自检，root另行核对diff和完整6013/E2E18证据；不称为修复作者对自己修改的独立评审。
本新scope本轮结束，不自动第3轮；旧封顶scope未重开。该准备阶段尚未执行真实请求、预算待授权；后续授权与执行见下节。


## 2026-10-16 真实执行与结论

首次对“继续”的执行申请被自动审批拒绝，确认当时无 started/result/账本、0 请求；
用户随后对具体两图外发至 Qwen、最多四请求和新增 $0.70 估算预算明确回复“确认”。
原签名通过 load_freeze 校验后执行一次，退出码 0，未改源码、图片、参数、评分或停止规则。

[result.json](result.json) 为完整四分母：2 finished / 2 failed / 0 not_run，
completed=true、4 external requests、0 fake HTTP、0 新 GUI 操作，stop_reason=null。
“完成”表示四项用量均已知且已结算，不表示四项都成功：

- 图1 default：24.008s，输入2174/输出2049tokens，finish_reason=length，回答为空，
  schema失败，无可评分坐标；估算 $0.001711050。
- 图1 no-think：3.017s，输入2176/输出67tokens，finish_reason=stop，schema合法，
  点(216,372)，距标注2.236px，命中20px半径；估算 $0.000403260。
- 图2 no-think：1.689s，输入2176/输出62tokens，finish_reason=stop，schema合法，
  点(1430,810)，距标注4.123px，命中20px半径；估算 $0.000399960。
- 图2 default：23.348s，输入2174/输出2049tokens，finish_reason=length，回答为空，
  schema失败，无可评分坐标；估算 $0.001711050。

图1/图2 no-think 相对 default 分别少20.990s/21.659s、少 $0.001307790/$0.001311090；
仅为本批固定总输出额度下的成对描述，不是默认思考在充足额度下的质量结论。
两次 default 的 completion_tokens=2049，落在2048+10的冻结余量内；本次观察到 length
截断，没有 bound_exceeded，不能由两次观察推断供应商对所有请求的硬上限保证。

账本核对：12927 known tokens，已知估算 **$0.004225320**，reserved=0，无 unknown。
旧账本占用 $0.566875686 保留，加本批后 known+held 共 **$0.571101006**；
其中历史未知预留仍为 $0.380096640，不释放、不重放。以上均为冻结价格的契约估算，
不是实际发票金额。未花预算不自动授权下一批。

候选结论为 **advance_to_owned_gui_smoke_preparation**：全四项已结算、无 operational
stop，且 no-think 2/2 合法并命中。结束静态筛选，下一片准备 frame/owned窗口落点/
键盘前台护栏与一次受控 GUI 短任务；先离线验证错误窗口、旧帧、失焦时零派发，再冻结
真实短任务。原生产 A 不替换；若以该候选参与后续任务，单独命名 A-control，保留原 A
统计边界。短任务之后回到 H/J 长任务及配对确认，H1–H4 本次仍未判定，G3/S6 未完成。
Jev 图片/Box 试验保持后置。本批 N=2 同应用位置，不能推断广泛准确率或稳定性。

证据校验：逐行状态/known usage、四请求账本费用和 token 求和一致；
result SHA256：`be3155cdc8ae531b894c4d3149b8c39aea3380c3cb50534d5924b92f5ec98e52`。
冻结/源码与此前验收版本不变，未重跑完整代码测试；本次仅真实执行与文档归档，
文档一致性与本结果归档范围评审见计划记录。
