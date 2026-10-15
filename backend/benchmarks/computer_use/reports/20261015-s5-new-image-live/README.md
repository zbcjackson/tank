# S5 新图片独立定位：冻结执行预览

> 状态：2026-10-15 revision 3新图片配方已冻结，同签名fake3/3；完整验证5991/E2E18通过、数据接线第1轮独立评审通过，真实未执行，待新预算授权。

## 任务与数据

目标是在另一张固定图中定位Calculator按钮7，只有一个目标，每配置一次请求；
不点击、输入、建应用或抓图。图片来自一次零模型owned-app采集，setup及清理记录见
[来源](../20261015-s5-new-image-source/README.md)。这不是上一批原图复测，也不是完整GUI任务。

[frame.png](frame.png)为1920×1080完整主屏图，SHA256
`95713a7b61fd046c2bf330044daa5aa840484796311c7b6b78b63a737748820e`。
Calculator位于右侧；其他可见应用中的会话正文/侧栏也在图中。执行时会将整图、
定位目标文本和共同提示发送至既有`dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`。
数据范围/服务沿用原有授权；本次准备尚未外发此图。API凭据不写入报告。

[case.json](case.json)副本来自
[calculator-right.json](../../fixtures/s5-static/calculator-right.json)：同期AX框
[1110,487,48,48]中心(1134,511)、20px半径，并已经固定图目视复核。
它是本地评分标注，不能随图/SDK消息外发；图SHA/标注/来源语义均进入冻结，
任一绑定数据改动即拒绝，不调用模型。仅支持固定尺寸/目标，不泛化新provider/工具。

## 冻结请求与判读

签名 **905c58ce3e652984708ef4af13224e385853417b17362f84b35e087e0e1c67b4**，
见[freeze.json](freeze.json)。源版本a-static-preflight-3，图片、case、共享解析器、
源码/SDK及生成参数/顺序/预算全部固定。

- 模型qwen3.7-flash-2026-07-15，temperature0.1，stream=true，include_usage=true，原图high。
- 固定顺序usage-only（40k、思考缺省）、no-think（仅关思考）、output-cap（仅限2048、思考缺省）。
  三组提示/图片相同，无组合组，无Jev、Advisor、工具循环或输入。
- 单请求180秒，SDK重试0；最多3次。未知用量/错误/截止/非法或截断回复停批，保留3行和未知预留。
- 仅接受纯JSON或完整一层json+LF围栏，随后严格唯一字段/整数0–1000/尺寸/单位/stop/无tool校验。
  null/null是弃权，错点保留如实分数；不调参重试或选择性删除失败。
- 依声明0–1000映射取整后按20px圆评分；标注内只指静态位置接近，非实际按钮输入成功。
  不猜1280缩放，不用模型声明成功当作评分，也不把schema可解析等同命中。

N=1/配置，仅描述新图上的可解析性、定位误差、reasoning_content、最终usage和用时；
不能推断质量不劣或稳定延迟。新图与旧图背景/窗口位置不同，不能跨图把改善归因于格式或思考。
原生产A/H1–H4/S5结论及所有旧分母不变。新旧任务文本仍是诊断提示，非完整Agent任务。

## 新预算与停止

拟申请新冻结估算上限 **$0.60 / 3100000tokens**，不转用已停批预检的剩余额度。
沿用历史保守契约：输入上界991808tokens、165nano-USD/token，输出660nano-USD/token；
两项40k各最坏估算$0.190048320，一项2048为$0.165，合计$0.545096640。
这些是冻结估算，不是当前报价或发票；回执超界则bound_exceeded停批并保留实际计量。

旧三批已知+未知预留占用$0.561901266，其中旧未知$0.380096640保持。
批准本次新增$0.60后累计最坏估算/预留上限$1.161901266；旧请求不重放/释放/补账。
本目录无started/result/账本；独占执行标记防止重复启动，源码或case改动需新目录/签名。

## 离线验收与执行

同签名[fake验收](../20261015-s5-new-image-fake/README.md)已完成3次HTTP/0外部/0新GUI。
fake固定错点与独立SDK正确点回归共同证明新标注接线生效，不证明Qwen能定位新图。
相关219项、lint/pyright/web检查、E2E18/71和runtime检查通过；完整后端5991 passed/1 skipped/21 warnings（422.27秒）及docs51/diff通过，
协议未改，sync不适用；本数据接线第1轮独立review-and-refactor通过，无actionable/unresolved finding、无代码修改；
评审重跑17项独立case回归/docs51/diff，核对新旧原始证据和完整日志，立即结束。
旧解析器/旧preflight三轮评审已结束，本片是新case数据接线和采集证据的独立评审范围。

获本配方预算授权且签名保持后，从backend执行一次：

```bash
uv run --no-sync python -m benchmarks.computer_use.a_preflight run \
  --output benchmarks/computer_use/reports/20261015-s5-new-image-live \
  --mode live \
  --approved-sha256 905c58ce3e652984708ef4af13224e385853417b17362f84b35e087e0e1c67b4
```

凭据沿用已有core/.env BAILIAN_API_KEY；没有真实请求前不宣称控制有效。
所有原始图/请求/chunks/账本留本地，仅精选README与非敏感case标注提交。
