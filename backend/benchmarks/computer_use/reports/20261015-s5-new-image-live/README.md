# S5 新图片独立定位：冻结执行预览

> 状态：2026-10-15 revision 3新图片配方已冻结，同签名fake3/3；完整验证5991/E2E18通过、数据接线第1轮独立评审通过，用户对具体新增$0.60/最多3次请求预览回复“继续”，原签名执行后bound_exceeded停批（2 finished/1 failed、3请求全已返回）；禁止重复启动。

## 真实执行结果（2026-10-15）

用户在明确新增$0.60/最多3次请求预览后回复“继续”，原目录/原签名执行一次并正常退出。
3次Qwen请求均已返回最终已知用量，0 fake HTTP、0新GUI、0新增unknown reserve；
completed=false，2 finished / 1 failed，stop_reason=bound_exceeded，非超时/unknown/预算耗尽。
没有补跑、重复采样或改原判分。以下是同一图片每配置1次的描述性观察：

- usage-only：28.932s，finish=stop，schema合法，(596,431)映射(1144,465)，
  距预标注中心47.074px，超20px半径；prompt2174/completion2822，其中思考2753、回答69，
  冻结估算$0.002221230。call_id=7377d20828e44e24b1b90817b119058e。
- no-think：1.742s，finish=stop，schema合法，(590,472)映射(1132,509)，
  距中心2.828px，位于20px半径内；prompt2176/completion63（回答63），无reasoning_content，
  冻结估算$0.000400620。call_id=a8031a7e29fa4f7f988556437712d4c8。
- output-cap：31.106s，finish=stop，prompt2174/completion3021（思考2952+回答69），
  超出本行冻结输出allowance2048，账本记录known用量及bound_exceeded后停止。
  冻结估算$0.002352570。call_id=1182979d6c5946739f9c49e126337014。
  该行failed，schema_valid=false/within_annotation=false为未进入正常评分的默认值，
  不能据此声称模型JSON格式非法或回答被截断。

三项归档SDK请求的messages逐字一致、图SHA保持；no-think的provider prompt计量多2tokens，
不据此称宿主提示不同。记录为SDK调用参数和SDK解析chunks，未另行捕获原始HTTP字节。
第三项另存[事后复核](posthoc-bound-review.json)：原result字节/hash保持，
完整回复本身schema可解析；(596,431)仍映射(1144,465)，距中心47.074px，未命中。
它仅为诊断，不把failed改为finished或加入原正常评分结果。

**预算契约纠偏**：此前将max_tokens当作思考+回答总输出上限，是本配方的错误假设。
[百炼OpenAI兼容API文档](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/)
说明Qwen的max_tokens限制回答，不含思维链；max_completion_tokens才限制两者总和，
适用于Qwen3.5-Flash及之后系列，且文档注明最多10tokens误差。本次第三项2952+69的回执
与该语义一致，不能称provider违反2048总输出硬上限或以修改旧allowance抹掉bound_exceeded。
未来需使用总输出参数并计入误差余量、逐项验证；本轮没有改源码/默认或重开旧配方。

本批known12430tokens、冻结估算 **$0.004974420**，未知预留0；原跟踪三批加本批累计
已知估算$0.186779046 + 旧未知预留$0.380096640 = **$0.566875686**。
这些是按原冻结契约的账本占用，不是发票或可信的真实最坏账单上界：旧thinking+
max_tokens配方的输出预留也受同一语义假设限制。旧unknown原账继续保留，不释放/补造账单。

**当前结论**：关闭思考在这张图的一次请求中更快且点落入标注，值得作为候选控制；
不能据N=1/固定顺序/单图声称稳定改进、因果质量优势、任务成功率或原生产A被修复。
max_tokens=2048没有限制整体推理输出，本批总输出预算契约需要纠正。S5/H1–H4与输入护栏
仍未验收，Jev默认不改。

**下一步**：先零收费修正实验的总输出参数/预留契约，真实SDK+fake HTTP验证只发
max_completion_tokens、避免与max_tokens同时发送，输出allowance包含文档误差余量，
上界内/外/unknown仍正确结算/保留/停批。再单独预注册跨图、配对或平衡顺序的no-think
候选验证；此图不用于反复调参挑成功，不直接重开150项或改生产默认。

[result.json](result.json)、[spend.jsonl](spend.jsonl)、[execution.log](execution.log)、
请求参数和chunks本地保留，不提交原始图/载荷；本次仅更新精选文档并做零收费事后诊断。数据案例scope第2轮独立结果文档复核通过，
无actionable/unresolved finding、无修改；实际核对result/chunks/消息/用量算数及官方API语义，
docs51/diff通过。源码未变，按文档例外不重复5991/E2E；S5仍未验收。

## 任务与数据

目标是在另一张固定图中定位Calculator按钮7，只有一个目标，每配置一次请求；
不点击、输入、建应用或抓图。图片来自一次零模型owned-app采集，setup及清理记录见
[来源](../20261015-s5-new-image-source/README.md)。这不是上一批原图复测，也不是完整GUI任务。

[frame.png](frame.png)为1920×1080完整主屏图，SHA256
`95713a7b61fd046c2bf330044daa5aa840484796311c7b6b78b63a737748820e`。
Calculator位于右侧；其他可见应用中的会话正文/侧栏也在图中。执行时会将整图、
定位目标文本和共同提示发送至既有`dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`。
数据范围/服务沿用原有授权；准备阶段未外发；获授权执行后该图已发送至上述Qwen服务。API凭据不写入报告。

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

新冻结估算上限 **$0.60 / 3100000tokens**。2026-10-15用户在明确预算/最多3次
Qwen请求的执行询问后回复“继续”，据此授权本配方；不转用已停批预检的剩余额度。
沿用历史保守契约：输入上界991808tokens、165nano-USD/token，输出660nano-USD/token；
两项40k各最坏估算$0.190048320，一项2048为$0.165，合计$0.545096640。
这些是冻结估算，不是当前报价或发票；回执超界则bound_exceeded停批并保留实际计量。

旧三批已知+未知预留占用$0.561901266，其中旧未知$0.380096640保持。
批准时按原冻结假设预览的累计最坏估算/预留为$1.161901266；实际占用与该假设
纠偏见上文，不再将此数当作真实最坏账单上界；旧请求不重放/释放/补账。
本目录started标记和持久账本已创建；独占标记防止重复启动，源码或case改动需新目录/签名。

## 离线验收与执行

同签名[fake验收](../20261015-s5-new-image-fake/README.md)已完成3次HTTP/0外部/0新GUI。
fake固定错点与独立SDK正确点回归共同证明新标注接线生效，不证明Qwen能定位新图。
相关219项、lint/pyright/web检查、E2E18/71和runtime检查通过；完整后端5991 passed/1 skipped/21 warnings（422.27秒）及docs51/diff通过，
协议未改，sync不适用；本数据接线第1轮独立review-and-refactor通过，无actionable/unresolved finding、无代码修改；
评审重跑17项独立case回归/docs51/diff，核对新旧原始证据和完整日志，立即结束。
旧解析器/旧preflight三轮评审已结束，本片是新case数据接线和采集证据的独立评审范围。

下列为获授权后已执行一次的历史命令；目录已停批，禁止再次执行：

```bash
uv run --no-sync python -m benchmarks.computer_use.a_preflight run \
  --output benchmarks/computer_use/reports/20261015-s5-new-image-live \
  --mode live \
  --approved-sha256 905c58ce3e652984708ef4af13224e385853417b17362f84b35e087e0e1c67b4
```

凭据沿用已有core/.env BAILIAN_API_KEY；真实单图结果及限制见上文，不宣称控制普遍有效。
所有原始图/请求/chunks/账本留本地，仅精选README与非敏感case标注提交。
