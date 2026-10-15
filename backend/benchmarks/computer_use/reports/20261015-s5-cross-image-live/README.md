# S5 两图候选门：冻结执行预览

> 状态：2026-10-15 source_changed：R1收尾修复后本冻结失效；未曾执行，禁止运行/补改旧目录，使用新v2配方。

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

签名 **4e5379e3695c394b2be8869b1fe830ff4a72a2f928544f94f32429b874f320fc**，
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
unknown、网络/截止/超余量/持久化等operational错误立即停全批，四行分母/未知预留保留，
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

同签名[fake验收](../20261015-s5-cross-image-fake/README.md)4/4、0external/新GUI，
原单请求路径共用且旧invalid_reply规则回归通过。相关302项、lint/type/web、
E2E18/71与runtime检查通过；完整后端6011 passed/1 skipped/21 warnings（421.29s）、docs51/diff通过，
协议未改/sync不适用，本新跨图调度评审待完成。
本目录无started/result/账本，不应将fake当真实模型结果。

以下为旧配方历史命令，因source_changed禁止执行；有效预览见v2链接：

```bash
uv run --no-sync python -m benchmarks.computer_use.a_cross_image run \
  --output benchmarks/computer_use/reports/20261015-s5-cross-image-live \
  --mode live \
  --approved-sha256 4e5379e3695c394b2be8869b1fe830ff4a72a2f928544f94f32429b874f320fc
```

凭据只用既有core/.env BAILIAN_API_KEY，标记文件禁止重复执行，源码/图片/case变化须新目录。

有效新版本：[v2执行预览](../20261015-s5-cross-image-v2-live/README.md)。旧raw/分母/账本保持，源码修复未覆盖旧结果。
