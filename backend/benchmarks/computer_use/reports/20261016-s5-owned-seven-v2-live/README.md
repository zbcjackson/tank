# S5 A-control 单击短任务：冻结执行预览

> 状态：2026-10-16 已冻结，同签名fake实机通过；完整验证6043/E2E18及lint/type/docs通过，第1轮独立评审通过，无可操作问题或源码修复；12项针对性离线回归复核通过，结论补记由评审者自检。真实模型未执行，待新增$0.20估算预算及本配方明确确认。

签名 **47d5e4f540a1858375b555f186bbd73e239d43b9efefdcd2024cc9bdd32efc4b**，见[freeze.json](freeze.json)；
[fake验收](../20261016-s5-owned-seven-v2-fake/README.md)与[主计划](../../../../../docs/plans/active/computer-use-strategy-ladder.md)。
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

拟新增 **$0.20 / 1100000tokens / 1请求**。冻结输入上限991808tokens×165nano，
输出2058tokens×660nano，单次预留 **$0.165006600 / 993866tokens**。
这些为历史冻结单价/输入假设下的契约估算，不是实际发票或真实最坏费用保证。
历史真实known+held **$0.571101006**（其中旧unknown预留$0.380096640保持），
新增$0.20批准后账本口径累计上限 **$0.771101006**；不挪用旧未花额度。

未知用量保留预留、停止；无目标/格式失败/旧帧/失焦/遮挡/窗口外点均不点击；
派发回执不明不重放。每个输出目录有exclusive started标记，源码/配置漂移拒绝执行，
不覆盖旧结果。账本关闭失败会降为失败并尽力保留result，存储整体失效不能保证落盘。

即使通过，也只证明这一受控单击链路可行；不代表完整任务成功率、长期稳定性或Jev净收益，
H1–H4和G3/S6仍未完成。下一步按此证据决定后续多步任务，再回H/J长任务比较。

## 执行命令（尚未执行）

完整验证及评审通过，并明确确认本配方的新预算/数据范围后，才从backend运行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.a_gui_smoke run \
  --output benchmarks/computer_use/reports/20261016-s5-owned-seven-v2-live \
  --mode live \
  --approved-sha256 47d5e4f540a1858375b555f186bbd73e239d43b9efefdcd2024cc9bdd32efc4b
```

凭据仅用既有core/.env的BAILIAN_API_KEY，不写入日志/报告。当前无started/result/账本。
