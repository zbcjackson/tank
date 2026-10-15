# S5 两图候选门：冻结执行预览

> 状态：2026-10-15 配方已冻结，同签名fake4/4；完整验证6013/E2E18通过、第1轮R1修复验证通过、第2轮复核通过（无新增/遗留问题，立即结束），真实未执行，待新预算授权。

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
数据范围与目的地沿用此前授权，本批准备未发送图片。原始图/载荷本地保留不提交。

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

拟新增冻结估算上限 **$0.70 / 4000000tokens**，最多4请求。按历史估算输入
991808tokens×165nano、输出2058×660nano，每请求预留$0.165006600，四项合计
$0.660026400 / 3975464tokens；预留/价格为契约估算，不是当前发票或真实最坏金额证明。
旧四批账本known+unknown预留占用$0.566875686保持，新$0.70批准后按账本口径累计
上限$1.266875686；不转用旧未花额度，不释放未知/重放旧请求。

同签名[fake验收](../20261015-s5-cross-image-v2-fake/README.md)4/4、0external/新GUI，
原单请求路径共用且旧invalid_reply规则回归通过。相关302项、lint/type/web、
E2E18/71与runtime检查通过；完整后端6013 passed/1 skipped/21 warnings（421.99s）、docs51/diff通过，
协议未改/sync不适用，本新跨图调度R1修复完整验证通过、第2轮复核通过（无新增/遗留问题，立即结束）。
本目录无started/result/账本，不应将fake当真实模型结果。

批准本配方预算且签名保持后，从backend执行一次：

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
本新scope本轮结束，不自动第3轮；旧封顶scope未重开。真实请求与预算授权状态不变。
