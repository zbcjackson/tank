# S5 A 单目标静态定位预检：执行预览

> 状态：2026-10-15 配方已冻结，离线验收3/3；完整验证及第1轮独立评审通过，真实请求未执行；待新估算预算授权。

本批是独立诊断，不是旧150项补跑，也不替换生产A。只读取已有截图，不创建应用、
不截图、不点击或输入；只有Qwen服务，没有Jev、Advisor或工具循环。

## 冻结配方与数据

- 执行器：[a_preflight.py](../../a_preflight.py)，预注册见
  [主计划](../../../../../docs/plans/active/computer-use-strategy-ladder.md)。
- 签名：`59f44c3b28bd327a0d11c372b6c7a402178bd91a0b0c42a5aacee7f7fc8cad4c`。
  [freeze.json](freeze.json)包含图片、人工标注、共同提示、顺序、源码/SDK版本和预算。
- 图片：[原始既存截图](../20261014-s5-confirmatory-v2-repaired-live/trials/0-calculator-ax_press-0-A/screenshots/shot_001.png)，
  1920×1080，SHA256 `3755bd479f7b71abee464e591fea9b58f30ad6462ac5b56ac93dbc794be1eb6f`。
  [frame.png](frame.png)为原样副本。可见Calculator及其他应用中的既存会话内容；
  将整张原图、共同提示及目标文本发至`dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`。
  沿用此前已允许的截图数据范围及Qwen目的地，不发送API凭据到报告。
- 唯一目标：Calculator按钮7。人工查看固定图，预先标注中心(316,418)、半径20px；
  这是静态图片的人工近似标注，非同步AX或真实输入验证，标注值不放进模型请求。
- 模型固定`qwen3.7-flash-2026-07-15`；三组均temperature0.1、stream=true、
  include_usage=true、high原图；每组单目标/单请求，不重复或根据回复调提示。
- 固定顺序：A-control-locate-usage-only（40k、思考缺省）；
  A-control-locate-no-think（只增加enable_thinking=false）；
  A-control-locate-output-cap（相对usage-only只改max_tokens=2048，思考仍缺省）。
  不运行组合组。三组共用新的只定位JSON提示，无工具注册；因此不能归因于原生产
  Agent全过程，也不能把本组结果合并旧S5。其余共同因素保持一致。

[官方思考文档](https://www.alibabacloud.com/help/zh/model-studio/deep-thinking)确认该快照
默认启用思考，enable_thinking=false关闭；
[官方流式文档](https://help.aliyun.com/en/model-studio/stream)说明include_usage选项。
这些参数是否改善此次定位/延迟仍待真实结果；usage选项不保证被中断流的用量回执。

## 预算与停止

新估算预算拟定上限 **$0.60**，不是从旧两批的未使用额度转用；真实执行尚未获得本配方的新预算授权。
按既有冻结保守价格估算：输入165nano-USD/token、输出660nano-USD/token，
各请求完整输入预留991808tokens；两项40k各预留$0.190048320，一项2048预留$0.165000000，
三项合计最坏冻结估算 **$0.545096640 / 3057472tokens**，账本上限$0.60 / 3100000tokens。
沿用历史价格/上下文估算契约，不将其描述为当前provider报价或实际账单保证。
实际回执超冻结用量即bound_exceeded停批，仍计真实用量；未知保留完整预留，不补造发票。

旧两批已知估算+未知预留占用$0.559560576；批准新增$0.60后累计最坏估算/预留上限
$1.159560576。旧未知请求原封保留、不重放、不释放；旧授权未用部分不代表本配方可用预算。

- 每请求180秒，official SDK重试0，最多3次串行；统一SDK-call治理和持久账本。
- 未知用量、请求错误/截止、非法或截断回复即停，保留所有3行及未运行行；不自动重开。
- 完整回复的有效但错误定位或弃权保留如实分数，不借此重复同图挑成功。
- 标记文件独占创建，重复执行拒绝；每次发请求前重新校验冻结和图SHA。
- 模型输出不能调用任何工具；没有GUI输入，所以本预检不验收owned窗口/前台护栏。

## 记录与判读

保存脱敏SDK请求（图片只留SHA，无header/凭据）、SDK解析的原始chunks、
reasoning_content/content、finish_reason、最终usage、用时、声明单位/尺寸及坐标误差。
缺失用量保持unknown；只接受完整stop回复、唯一字段JSON、正确尺寸及整数0–1000，
合法null/null为弃权。按生产归一化映射取整后计算与人工中心的距离，半径20px内记
within_annotation，非真实点击成功。不按1280像素假设修坐标，其他单位直接无效。

completed仅表示三项都获得合法完整回复，不等于三项定位正确；N=1/组仅作配置诊断，
不能推断质量不劣、延迟稳定性、原150项任务成功率或Jev净收益。原H1–H4不评估。
若定位仍失败，应另立新图片/单位控制并重新冻结，不在本批反复调参；若进一步输入，
另验证frame/逐点owned窗口/键盘前台等门槛后再准备实机配方。

## 验收与执行

相同签名[离线配方](../20261015-s5-a-static-preflight-fake/README.md)已通过3次fake HTTP，
0外部请求/0新GUI操作；回复预设，只证明接线、冻结和账本，不证明Qwen定位正确。
回归先红15项再绿；含既有S5/模型调用治理共69项通过，lint/pyright/web检查通过，
E2E18场景/71steps通过；完整后端5944 passed / 1 skipped / 21 warnings，
运行时error/traceback/exception检查为空，docs51/diff通过。协议未改，sync不适用。
完整测试首次因词表缓存清空收集失败；补齐公开词表后沙箱运行因本地端口限制失败，
在允许本地端口/受控Chromium的环境重跑已全过。
新增片第1轮独立review-and-refactor无actionable/unresolved finding，未改代码、立即结束；
评审重跑定向69项/docs51/diff并重新验证freeze，核对完整日志。旧范围的评审不重开。

授权且签名保持一致后，从backend执行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.a_preflight run \
  --output benchmarks/computer_use/reports/20261015-s5-a-static-preflight-live \
  --mode live \
  --approved-sha256 59f44c3b28bd327a0d11c372b6c7a402178bd91a0b0c42a5aacee7f7fc8cad4c
```

凭据只从已有core/.env的BAILIAN_API_KEY读取；原始图片/请求/chunks/账本本地保留、不提交。
本目录目前没有started/result/账本，不应把离线结果称作真实成功。
