# S5 A 静态诊断格式兼容：零收费验收

> 状态：2026-10-15 revision 2离线接线3/3，0外部模型请求/0新GUI；完整验证5974/E2E18及本范围第3轮独立评审通过，0新增真实请求/费用。

## 修改范围

生产GroundingAdapter的工具参数一直严格JSON；容忍完整json围栏的是既有静态探针
text_response_point。本片仅抽取其已有逻辑为unwrap_json_fence，供原探针和a_preflight
诊断共用。接受纯JSON或恰好一层完整json+LF代码围栏（允许外围空白）；不处理带外
说明、多段/嵌套/缺闭合围栏、其他语言/无标签围栏，不修复坏JSON或重试模型。

拆包装后预检仍执行严格JSON唯一字段、整数坐标、声明单位/图尺寸、完整stop及
无tool request校验；弃权只能null/null。格式可解析不代表定位正确或可以执行输入。
生产工具协议、原预检的图片/提示/温度/模型/三个因素以及治理/停止规则均未变，
没有线上坐标缩放或宽松类型转换。下一次真实定位需要独立的新目标图片和预注册，
本报告没有真实执行预览或待运行live目录。

## 新冻结与fake接线

签名`b61c9e219a910be0c72c8985993dba4ddebccfd2a54307bc298c8a7408892a02`，
revision=a-static-preflight-2，格式契约pure-json-or-single-json-lf-fence，新增共享
源文件hash。源码变化后不能用旧59f44c签名或补跑旧目录。
[freeze.json](freeze.json)和[既存原图副本](frame.png)仅用于fake接线，没有截图外发。
执行新目录，3行finished/3次fake HTTP/0外部模型请求/0新GUI，最终usage已知、
合成known7425nano-USD、reserved0、stop_reason=null；合成计量不是实际收费。
[完整结果](result.json)、[执行日志](execution.log)、[账本](spend.jsonl)在本地保留。
SDK回归分别覆盖纯JSON与完整围栏回复，三组请求体和图片不受评分格式变化影响。
fake固定回复命中只验证接线与评分，不证明模型质量、延迟或完整S5效果。

## 旧真实回复的事后回放

仅对[上一批](../20261015-s5-a-static-preflight-live/README.md)已存回复调用新score，
无模型/GUI；[回放收据](format-replay.json)显示schema_valid=true但within_annotation=false，
(88,356)仍按声明0–1000映射(168,384)，距人工中心151.855px。
没有把错点判命中，也没有覆盖上一批1 failed/2 not_run或因invalid_reply停批的结论。

上一批原result SHA256
`46b233e03d9caccee5eb5d4d7608540d0324316d18d25d1a184f9248e0edd41b`保持，
费用估算$0.002340690和新未知0保持；全部旧批累计估算/预留$0.561901266，
旧未知预留$0.380096640保持。本轮0新增真实请求/费用，不使用未花的旧预算。

## Tests与验证

先红5项（含真实SDK围栏接线/可解析错点/弃权/冻结版本），其余40项原有/拒绝校验通过；
实现后预检+grounding_probe+模型治理共202项通过，新增30项回归（含参数化）。
覆盖重复/多余/缺字段、错误单位/图尺寸、bool/string/float、越界/NaN、单边null、
截断/工具请求、包装缺失/多重/带外文本等；原探针现有回归保持通过。
backend/CLI ruff、修改文件pyright0、web lint/tsc-b、E2E18场景/71steps通过，
开发服务器error/traceback/exception检查为空。完整后端5974 passed/1 skipped/21 warnings
（425.87秒）、docs51/diff通过；协议未变，sync不适用。第3轮独立review-and-refactor通过，无actionable/unresolved finding、无代码修复；
评审重跑202项/docs51/diff并复核新旧冻结与原结果hash，立即结束，本范围不进入第4轮。
日志见[validation](validation/)；原始图片、JSON载荷、账本与日志不提交，只跟踪此README。

## 下一步

先另选并预先标注目标图片，再独立冻结真实单因素定位配方；共同解析格式固定后再
测关思考/输出上限效果。当前只通过零收费格式/接线验收，未进行新的模型定位试验，
不能将新schema可解析当作旧A质量修复或直接重开150项。真实GUI输入仍须另外验证
frame绑定、逐点owned窗口及键盘前台等护栏，S5/H1–H4/生产采用结论保持未完成。
