> 日期：2026-10-19；结论状态：开放（修复后受控网页复测完成；真实产品及独立确认待测）。

# 修复后V/JT复测与真实弃权后的视觉接管

## 结论

预先冻结36任务，18场景×V/JT两臂；原12场景/24任务逐值保留，新增6场景/12任务
只改变颜色控件的结构标签。仍是三种已见手写网页及两个位置顺序，非真实产品、
新应用族或独立确认。两臂共享结构输入、动作构造、规则、宿主守卫、效果与清理核验。
V规则后由Gemini带图选有限候选；JT适用时Jev文本，其余同一Gemini接管。

- 原24项，V：正例物理完成6/6、严格完成6/6；负例验收6/6；正例封顶均值16.432秒。
- 原24项，JT：正例物理完成6/6、严格完成6/6；负例验收6/6；正例封顶均值6.823秒。
- 新12项，V：正例物理完成4/4、严格完成4/4；负例验收2/2；正例封顶均值21.673秒。
- 新12项，JT：正例物理完成4/4、严格完成4/4；负例验收2/2；正例封顶均值7.140秒。
- 新JT的真实弃权后同binding视觉兜底证据6/6任务；
  实际调色控制为need_more_context四次、ambiguous两次，none/escalate零次；
  猜选0次，均保留原始回答及物理结果。

本轮Jev仅收文字，Gemini收PNG+同一结构观察；不是Jev图片/Box或纯像素能力对比。
成功质量、路由证据与调用开销分别报告，不能从本轮直接宣布Jev视觉更强或生产采用。
原pilot四个V正例及一个负例的执行拒绝仍保留原成绩，不用本次新结果重判旧失败。

## 新增语义缺失题与评分

网格/多步抽屉有红色目标各两顺序，网格全蓝无目标两顺序。中性唯一标签Option A/B
使ActionBuilder自然判为jev_eligible，但DOM观察不包含颜色、CSS或脚本；公开目标
“选红色”不透露哪块是红色。图片仍显示红蓝。私有oracle只作末端评分，不参与路由。

允许Jev实际选候选、弃权或出错；没有脚本改写回复、强迫弃权或按正确答案路由。
新JT只有在调色阶段实际收到合法非候选控制none/ambiguous/need_more_context/
escalate，再对同一完整state.binding以computer_use.visual_fallback请求图片，且
该任务没有调色猜选，才取得fallback_verified。独立重算还验证实际回复先于图片
请求，不能从最终结果倒推接管已经发生。

物理目标/路径/清理单列goal_completed，负例原始退出单列exit_correct；新JT的
strict_completed与negative_passed还要求上述证据。幸运猜中仍保留物理完成，但
不算严格成功；正例严格失败耗时一律120秒。V无需先Jev弃权，旧24项标准不变。
缺失目标应零点击退出；引用替换应零派发；效果未知只提交一次且保留pending_effect。

第1轮独立审查发现新fallback_absent的CSS全蓝，但JS误点后可能显示selected:red；
以真实Chromium/fake HTTP失败回归复现后，e7e6dc86最小修复，使终态为selected:blue。
原负例本已因非空trail判失败，修复保证物理记录真实；没有强迫模型弃权或改变路由。
原24项HTML/GoalContract/oracle及顺序与旧归档逐值相同。

## 冻结与执行

基线ce76f7cd，计划f3aa2acd，实现6e28a019，审查修复e7e6dc86及记录03133ada。
修复前目录`/private/tmp/tank-route-followup-live-20261019`仅prepare，0真实模型调用；
摘要8324aba74907e0a9e785defbfb62e07dc445341961fa56377a3a08f6e59512e7已失效并保留。
新目录`/private/tmp/tank-route-followup-live-reviewed-20261019`冻结36任务、33源文件：
`4b2a12b6fa5be1ec6895764c6377ee911f2e67a0175e1d288f537e87821876ec`。
冻结模型/SDK版本、合成HTML、goal、评分规则、平衡臂顺序与历史估算费率；DOM引用/
截图运行时生成，实际请求字节另存，不冒称全部预先已知。

Jev1.14.0文本接收方api.typesafe.ai，视觉为OpenRouter google/gemini-3.8-flash，
JSON-object模式，temperature0、max_tokens4096。全部为新建无头隔离Chromium及
本地合成页面，无个人应用或文档；实际发送的合成文字/图片分别原样保留。

沿用用户不设固定批次请求/token/费用上限的授权，record-only账本；每任务120秒、
6动作/24观察、SDK不重试。已知模型错误保留继续；未知用量、运行/审计/清理失败
停全批，未运行分母保留。completed=True，stop_reason=None；
批次结束不等同每任务成功。未同题补跑、改变阈值或排除失败。

## 分层结果与调用路径

- V form/positive：物理完成2/2、严格完成2/2；4模型请求。
- V grid/positive：物理完成2/2、严格完成2/2；2模型请求。
- V drawer/positive：物理完成2/2、严格完成2/2；6模型请求。
- V grid/absent：负例验收2/2；2模型请求。
- V form/stale：负例验收2/2；2模型请求。
- V form/no_effect：负例验收2/2；4模型请求。
- V grid/fallback：物理完成2/2、严格完成2/2；2模型请求。
- V drawer/fallback：物理完成2/2、严格完成2/2；6模型请求。
- V grid/fallback_absent：负例验收2/2；2模型请求。
- JT form/positive：物理完成2/2、严格完成2/2；4模型请求。
- JT grid/positive：物理完成2/2、严格完成2/2；2模型请求。
- JT drawer/positive：物理完成2/2、严格完成2/2；6模型请求。
- JT grid/absent：负例验收2/2；2模型请求。
- JT form/stale：负例验收2/2；2模型请求。
- JT form/no_effect：负例验收2/2；4模型请求。
- JT grid/fallback：物理完成2/2、严格完成2/2；4模型请求。
- JT drawer/fallback：物理完成2/2、严格完成2/2；8模型请求。
- JT grid/fallback_absent：负例验收2/2；4模型请求。

所有未通过任务（包括未运行）：

本轮全部通过各自冻结验收。

按任务保留的新增JT路由：

- `grid-fallback-0-jt`：jev → peer；停止goal_verified；同绑定兜底证据1，猜选0。
- `grid-fallback-1-jt`：jev → peer；停止goal_verified；同绑定兜底证据1，猜选0。
- `drawer-fallback-0-jt`：jev → jev → peer → jev；停止goal_verified；同绑定兜底证据1，猜选0。
- `drawer-fallback-1-jt`：jev → jev → peer → jev；停止goal_verified；同绑定兜底证据1，猜选0。
- `grid-fallback_absent-0-jt`：jev → peer；停止none；同绑定兜底证据1，猜选0。
- `grid-fallback_absent-1-jt`：jev → peer；停止none；同绑定兜底证据1，猜选0。

V：30总请求，Jev 0、Gemini图片30；JT口径的直接绕过0次，弃权兜底0次，repeated_state恢复图片0次，视觉后返回Jev 0任务；捕获30、规则动作4。

JT：36总请求，Jev 24、Gemini图片12；JT口径的直接绕过6次，弃权兜底6次，repeated_state恢复图片0次，视觉后返回Jev 4任务；捕获12、规则动作4。

直接绕过由route事件visual_required识别，弃权兜底由实际model_call目的并与原始
请求/回复匹配；返回指同任务模型顺序中peer后出现Jev。图片路由和返回不是已知
可恢复业务故障的恢复率。相同布局的两个位置不能当作两个独立应用。

## 耗时与费用

正例成功计时到独立终态/路径及客户端、浏览器、服务器清理确认；严格失败120秒。
负例退出时间分列，不混入正例完成效率。任务冷启动含宿主生命周期，不代表供应商
模型冷启动，缓存/路由/推理默认未固定；本轮描述性差异不是模型固有速度或确认性
收益。旧pilot受宿主拒绝影响的耗时不能与本轮混池或事后排除失败。

- V：输入107437、输出5327 tokens；冻结费率估算USD0.110609400。
- JT：输入112550、输出4081 tokens；冻结费率估算USD0.046218876。
- jev总计24请求，输入72303、输出1662 tokens；估算USD0.003036726。
- peer总计42请求，输入147684、输出7746 tokens；估算USD0.153791550。

已知229395 tokens，未知0请求，清理确认36/36。
record-only cost_status=unpriced，费用0字段不表示免费。Jev输入42/输出0、
Gemini输入825/输出4125 nanoUSD/token为冻结历史估算费率，不是账单；OpenRouter
原始usage另报USD0.139810500，不同口径不推断未验证收费规则。

## 归档与验证

[原始归档](artifacts/jev-vision-route-followup-20261019.tar.gz)及
[逐文件清单](artifacts/jev-vision-route-followup-20261019-manifest.json)：
255成员、78PNG，SHA256：
`aff72553760bde59dfc732c20018bfd6ace4c449b60360cf36bac5b31cf467b7`。
包含全部任务冻结、原始SDK请求/响应/输入图、终态/事件/审计/清理、账本及逐任务
评分，冻结33源字节、独立重算脚本/摘要/归档脚本和验证日志；失效prepare只作历史。
逐成员字节/hash、源码hash、call_id/用量守恒、请求图hash/实际PNG、控制回复与图片
请求顺序及完整binding、共享task_id、物理/严格评分和全部分母独立核验。
配置的21个实际凭据值扫描无命中，旧10归档及清单不变。

TDD及第1轮审查修复后的route专项16项通过（54.49秒），完整后端6387通过/1跳过
（536.56秒），串行E2E21场景/83步骤（152.421秒）。web lint/tsc-b、backend及CLI
lint、两项Python pyright、dev日志、docs与diff通过。无协议或生产默认修改。
真实调用后只有文档/工件/面板增量，复用稳定源码验证，另执行docs/diff及面板类型
检查；类型检查不冒称宿主实际渲染。

第2轮独立结果审查（基线ce76f7cd，覆盖至c10e1562）从归档重算全部任务的物理/
严格评分、DOM路径/终态/审计、66调用先后及完整binding/task_id、用量与费用，
核验255成员和全部78图、旧10归档/清单及21实际凭据值扫描。面板数据与归档
摘要逐值相等，筛选逻辑/类型检查通过；未发现新增确认问题或遗留问题，立即结束。
第1轮最小修复已自查，源码未再变动；本轮仅收尾文档由评审者自检，无后续独立复核。

## 后续

由[主计划](../plans/active/computer-use-jev-vision.md)承接真实产品/新任务族及已知
可恢复业务故障，之后冻结未见独立确认集。新JT若存在缺证据的猜选，应先定位
结构语义充分性/弃权契约并以新实验验证，不能把幸运完成当兜底成功。Jev图片Choice/
Box的JM/JF增量另立对照，不能从文本JT推得；可替换视觉模型不限定为Qwen或Gemini。
生产默认继续保持，当前手写开发题不支持广泛采用。
