# S5 A-control 单击短任务：冻结配方与真实结果

> 状态：2026-10-16 已冻结，同签名fake实机通过；完整验证6043/E2E18及lint/type/docs通过，第1轮独立评审通过，无可操作问题或源码修复；12项针对性离线回归复核通过，结论补记由评审者自检。用户明确确认后原签名已执行：1请求、窗口外点被护栏拦截、0模型点击派发，passed=false；清理全部确认，估算$0.000400620，无未知用量。禁止重跑本目录。

签名 **47d5e4f540a1858375b555f186bbd73e239d43b9efefdcd2024cc9bdd32efc4b**，见[freeze.json](freeze.json)；
[fake验收](../20261016-s5-owned-seven-v2-fake/README.md)与[主计划](../../../../../docs/plans/done/computer-use-strategy-ladder.md)。
独立实验名 **A-control-owned-seven**，不替换原生产A或旧150项批次。

## 具体执行与数据范围

1. 仅在Calculator未运行时新建owned实例；若已存在则停止，不关闭或复用用户实例。
   在主屏完整可见的基本模式窗口中，必要时移动、隐藏侧栏并AX清零，确认读数0。
2. 采集新的1920×1080主屏全屏截图，记录图片摘要/frame/窗口身份与几何。
   全屏可能包含其他可见应用内容。将该PNG、固定定位提示及“Calculator button 7”
   发送到 `dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，模型为
   `qwen3.7-flash-2026-07-15`（以freeze中的精确值为准）；不发送AX标注/评分真值，不调用Jev。
   freeze固定的是源码和采集协议，未来新图的像素在执行时生成并归档，非复用旧静态图。
3. 最多一次模型请求：enable_thinking=false、temperature=0.1、图片high、stream/include_usage，
   max_completion_tokens=2048、计量余量2058、SDK重试0、单请求180s、业务任务deadline240s。
4. 只有schema合法且非弃权时，护栏验证最新frame、进程/窗口/前台/几何/窗口内画面、
   窗口内点、遮挡及输入空闲后，最多单击一次左键。AX标注不作为动作过滤条件；
   因而模型仍可能点击窗口内错误控件，必须以独立AX读回判定。
5. 点击后至多5次、间隔0.1s独立读回，初值0未变时只等待读取，不重发点击。
   result=7且输入/应用清理确认才通过。输入、窗口位置/侧栏和前台尽量恢复，关闭新建实例。
   取消/错误也先join原生工作、完成输入和应用清理再释放lease；清理不确认则隔离资源。

模型最多一个点击不包含上述setup/cleanup的真实GUI操作。操作期间需保持桌面空闲；
同进程lease不能阻止其它进程或用户同时操作。OS检查与输入派发不是原子操作。
不支持拖动、文本输入、快捷键或连续任务；本配方不向模型暴露Enter入口。

## 预算、停止与结论边界

本批获准 **$0.20 / 1100000tokens / 1请求**。冻结输入上限991808tokens×165nano，
输出2058tokens×660nano，单次预留 **$0.165006600 / 993866tokens**。
这些为历史冻结单价/输入假设下的契约估算，不是实际发票或真实最坏费用保证。
执行前历史真实known+held **$0.571101006**（其中旧unknown预留$0.380096640保持），
新增$0.20批准时账本口径累计上限 **$0.771101006**；不挪用旧未花额度。

未知用量保留预留、停止；无目标/格式失败/旧帧/失焦/遮挡/窗口外点均不点击；
派发回执不明不重放。每个输出目录有exclusive started标记，源码/配置漂移拒绝执行，
不覆盖旧结果。账本关闭失败会降为失败并尽力保留result，存储整体失效不能保证落盘。

即使通过，也只证明这一受控单击链路可行；不代表完整任务成功率、长期稳定性或Jev净收益，
H1–H4和G3/S6仍未完成。下一步按此证据决定后续多步任务，再回H/J长任务比较。

## 已执行命令（仅供审计，禁止重跑）

完整验证及评审通过，用户对本配方新预算、全屏截图至Qwen及受控单击范围明确回复“确认”后，已从backend运行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.a_gui_smoke run \
  --output benchmarks/computer_use/reports/20261016-s5-owned-seven-v2-live \
  --mode live \
  --approved-sha256 47d5e4f540a1858375b555f186bbd73e239d43b9efefdcd2024cc9bdd32efc4b
```

凭据仅用既有core/.env的BAILIAN_API_KEY，不写入日志/报告。现已生成started/result/账本，禁止复用此目录。


## 2026-10-16 真实结果：护栏拒绝，候选未通过

执行前后 load_freeze 均匹配原签名；1次外部模型请求、0 fake HTTP，SDK无重试。
CLI正常退出仅表示报告落盘；任务status=error、passed=false、verdict=not_passed。

模型1.901s返回schema合法的回复：coordinate_space=normalized_1000，image_size=
[1920,1080]，x=273、y=365，finish_reason=stop。依冻结协议映射为(524,394)，距本地
AX按钮中心(274,371) **251.056px**，不在20px标注范围，并落在owned Calculator窗口外。
root目视核对本次截图，目标7与AX标注一致，模型映射点位于窗口右侧背景。

护栏在原生点击前抛出 `Point is outside the owned window`，所以 **0模型点击派发**。
report.click_attempted=true指进入护栏调用，不代表Quartz已收到点击；click_returned=false，
独立完成读回未执行。真实GUI仅有新建、移动/清零setup与清理，不能说整批0 GUI。
input_cleanup.confirmed、application_cleanup.confirmed、position_restored及frontmost_restored
均为true；没有失败后重试，也没有补发其它输入。

后验线索：若把原始(273,365)当像素解读，距目标约6.083px，提示可能存在单位误标。
这不是本批允许的解释：回复明确声明normalized_1000，**不改分、不猜测转换、不补点**。
不能据此断言供应商内部原因；原2图静态门通过仍保留，不能保证新画面的单击成功。

用量全部known：输入2176、输出63，共2239tokens；按冻结价格估算 **$0.000400620**，
reserved=0、stop_reason=null。stop_reason仅为模型账本，不能掩盖GUI护栏失败。
历史unknown预留$0.380096640保持，新增本批后真实known+held累计 **$0.571501626**；
不释放历史未知预留，不将未花预算转用。以上是契约估算，不是实际发票。

结论：**本候选不进入多步A-control实机比较**。不追加同图调参、猜测单位或筛成功图，
结束当前no-think视觉候选分支，保留原生产A和所有失败证据。下一步准备独立H/J长任务
配对方案，分别冻结样本、分母、预算与停止规则；不拼接或补判旧150项实验/原A/H4。
本次N=1不是广泛失败率，亦未测试Jev，不产生Jev胜负或H1–H4通过结论。
Jev图片/Box试验仍在计划后期，G3/S6仍未完成。

证据：[result.json](result.json) SHA256
`120e6bd5a6a0d83867b226904b5564af4a4833dbae62ae99c5cd968bb776653d`；
截图SHA256 `1c74a4ee1a5030c63004678ae1742e0df51f8bc6b2de19454420a51acca61fbd`。
请求摘要与图片哈希一致，逐行usage/费用/清理字段已核对。本次无源码或配置变更，
不重复完整代码测试；仅文档归档检查与本结果范围独立评审，见主计划接续记录。
