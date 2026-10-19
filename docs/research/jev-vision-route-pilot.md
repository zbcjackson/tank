> 日期：2026-10-19；结论状态：开放（V/JT受控网页开发pilot完成，真实产品与独立确认待测）。

# 结构优先与视觉接管：新布局路由开发pilot

## 结论

24个预定任务，V/JT各12；包含6对正例和6对负例，3种本轮手写网页布局，
真实隔离Chromium及真实Jev1.14.0/OpenRouter Gemini3.8 Flash。V规则后由带图
Gemini选有限候选，JT适用时Jev文本，其余同一Gemini接管、后续可返回结构化。
两臂都保留相同结构观察，不是纯像素模型能力对比。

- 正例完整目标、路径约束及清理通过：V 2/6，JT 6/6。
- 负例正确退出：V 5/6，JT 6/6；目标缺失、控件替换、效果未知分别报告。
- 正例平均封顶完成耗时：V 83.545秒，JT 3.408秒，JT/V=0.041。
  正例失败一律120秒，不能靠早停获得速度优势；这是开发样本描述，非确认性效应。
- 实际模型请求：V 20（带图20），JT 20（Jev 14、带图6）。
  JT恢复到Jev路径2个任务；原始顺序与共享task_id已核验。

这测量了当前宿主中结构优先路由的增量，不将执行拒绝归为视觉模型判断错误，
也不证明一般视觉能力优劣。完整路由包含额外图片捕获和新鲜度检查；其成本及
拒绝均属于实际策略表现。仅3种手写布局、每种2个顺序，不能据此采用生产策略。

V只有2个颜色网格正例成功，两臂在这2个共同成功任务中都仅用Gemini；没有
完成的结构任务V/JT配对可用于隔离Jev速度增量。封顶耗时差被V的4个执行拒绝
显著放大，应先诊断参考路径的宿主检查，再冻结新的路由比较。

## 设计与执行边界

新布局为双字段素材表单、红蓝标记网格、多步抽屉（结构→颜色→共同规则→结构）。
表单只改Work title为Launch并保存，Archive title保持Draft；网格只选红色，
抽屉需先开始设置，再选红色、改名并保存。两种字段/颜色顺序先冻结，目标位置
不从模型结果挑选。负例各两顺序：网格无红色、首模型响应后替换控件、提交无效果。

页面和脚本均由实验编写，在真实Chromium执行；不是实际产品设置页、真实业务
后端或新的独立应用族。GoalContract提供公开目标/合法输入及所需终态，私有
oracle仅末端评分；模型只收当前DOM结构及有限候选，Gemini另附当前页PNG与
候选像素边界，Jev仅文字。没有自由Box定位、Jev图片/Box自动点击或开放规划。

V使用benchmark内最小策略子类，JT直接复用VisualSelector；ActionBuilder、
规则、Controller、TaskRuntime、动作准入、引用/图片新鲜度与效果核验完全复用。
视觉选择请求JSON-object模式，回复仍严格校验唯一choice字段及合法候选；此
一行接线修复先有失败测试，再通过完整回归，不改变生产默认配置。

每任务新建Chromium与模型客户端，同一任务的权限、期限、预算账本和task_id
不因接管/返回而重建。公共goal_id/task_id匿名，未向模型泄露positive/stale/
no_effect/absent分类或评分事件。私有标签投毒回归证明标签不能改变动作选择。

## 冻结、停止与时间口径

基线e58e6bec，实现4aca2a92，第1轮审查e6f6e1d4；真实运行前冻结33项源码、
模型/SDK版本、HTML、GoalContract、私有评分与平衡顺序：
`68faf31ed4cccf38ec0a999b4d2f9c240f3d5c1eee48217acfcb38910f78f04d`。
目录`/private/tmp/tank-vision-route-live-20261019`。DOM引用/当前截图运行时生成，
冻结的是配方及投影源码，不冒称全部请求字节预先已知。实际请求/响应/图片均保存。

沿用用户不设固定请求/token/费用批次上限的授权，record-only账本；每任务120秒、
6动作/24观察，SDK不重试。已知模型失误保留并继续；未知用量、运行/审计/清理
失败停全批，全部未运行分母保留。本轮batch completed=True，
stop_reason=None，不等同全部任务完成。无同题补跑或改阈值重判。

正例成功时间到独立终态/路径核验及模型、浏览器、服务器清理确认；失败取共同
120秒。实际失败耗时另存，负例退出时间不混入正例完成效率。每任务冷启动含
浏览器/客户端生命周期，不宣称供应商模型冷启动；路由/缓存/推理默认未固定，
不把耗时比当模型固有速度。6对正例仅3个布局族，不生成采用置信区间。

## 分层结果与失败

- V form/positive：正例0/2，4模型调用。
- V grid/positive：正例2/2，2模型调用。
- V drawer/positive：正例0/2，6模型调用。
- V grid/absent：负例2/2，2模型调用。
- V form/stale：负例2/2，2模型调用。
- V form/no_effect：负例1/2，4模型调用。
- JT form/positive：正例2/2，4模型调用。
- JT grid/positive：正例2/2，2模型调用。
- JT drawer/positive：正例2/2，6模型调用。
- JT grid/absent：负例2/2，2模型调用。
- JT form/stale：负例2/2，2模型调用。
- JT form/no_effect：负例2/2，4模型调用。

正例失败及未通过负例（全分母保留）：

- `form-positive-0-v`：partial/stale_reference；实际27.912秒；轨迹['fill:work:Launch']。
- `form-positive-1-v`：partial/not_sent；实际20.754秒；轨迹['fill:work:Launch']。
- `drawer-positive-0-v`：partial/stale_reference；实际18.833秒；轨迹['begin', 'pick:b', 'fill:work:Launch']。
- `drawer-positive-1-v`：partial/stale_reference；实际25.582秒；轨迹['begin', 'pick:a', 'fill:work:Launch']。
- `form-no_effect-0-v`：partial/stale_reference；实际7.842秒；轨迹['fill:work:Launch']。

正例stale_reference属于宿主在派发前的引用/画面检查拒绝，不能直接写成模型选错。
保留了模型输入图与终态图，但未保存该内部拒绝检查的即时截图或具体子阶段；
不能唯一归因于光标、焦点或DOM替换。主质量率保留这些任务，限制失败原因解释。

独立诊断确认4个正例失败最后都选中正确的Save work，轨迹已完成正确填入、
提交尚未派发。另一个V无效果负例也在正确选择Save work后提前拒绝，未进入
预定的无效果提交路径，因此仍记该负例未通过。五例模型输入与终态PNG的差异
均为1×23像素竖条（23个像素），形状和位置支持输入光标变化假设；这是
保存的两帧比较，不是拒绝瞬间内部截图，尚不能确认该次拒绝的唯一原因。

JT实际6次图片请求全部是visual_required直接绕过；14次Jev均选候选，真实
visual_fallback次数为0。本轮验证了绕过和返回，没有验证Jev弃权后接管的真实
模型表现（该分支仍只有fake HTTP功能证据）。

本轮恢复证据仅是视觉后返回结构路径及故障安全退出；没有已知可恢复业务故障的
恢复率。负例无效果项的正确退出保留unknown/pending_effect，不重标成任务完成。

## 用量与原始证据

- V：输入71977、输出3568 tokens，冻结费率估算USD0.074099025。
- JT：输入63317、输出1891 tokens，冻结费率估算USD0.022189749。
- jev合计：14调用，输入43247、输出966 tokens，估算USD0.001816374。
- peer合计：26调用，输入92047、输出4493 tokens，估算USD0.094472400。

总140753已知tokens，未知0，清理确认24/24。
record-only cost_status=unpriced、费用0字段不表示免费。冻结历史费率Jev
输入42/输出0、Gemini输入825/输出4125 nanoUSD/token；目录估算非账单，
Gemini输出包含推理tokens。OpenRouter原始usage另报USD0.085884000，
与目录简单乘法口径不同，不将差额归因于未验证的收费规则或宣称最终账单。

[原始归档](artifacts/jev-vision-route-pilot-20261019.tar.gz)和
[逐文件清单](artifacts/jev-vision-route-pilot-20261019-manifest.json)：
152成员、50PNG，1312407字节，SHA256：
`e473ab12b6549d7870d88f56bbdf5dcc20bb940c12a1bba4b3c553f538020bf5`。
含冻结、24任务原始调用/模型输入图/终态图/动作审计/事件/结果、总账本、独立
重算脚本与摘要和验证日志。逐成员hash/字节数、原33源hash、call_id/请求图、
调用目的/顺序/task_id、字段/事件/评分、全部分母和用量/账本末态独立重算通过。
实际配置凭据扫描无命中，旧8份归档SHA保持。

## 验证与后续

完整后端6368通过/1跳过（489.45秒），E2E21场景/83步骤（144.279秒），web/
backend/CLI lint、web类型、3个Python文件pyright、dev日志和docs/diff通过。
第1轮独立代码审查无源码修复，宿主权限9专项通过（30.56秒）。真实结果之后
只改docs/工件/面板，复用未变代码验证并执行docs/diff和面板类型检查；不声称
面板已实际渲染。第2轮独立结果审查待完成。

下一步由[主计划](../plans/active/computer-use-jev-vision.md)承接：根据本轮具体
失败先以无付费的DOM光标/新鲜度复现及拒绝阶段记录检查宿主门禁，修复后重新
冻结新路由比较；旧失败不重判。再在真实产品和新任务族比较，补已知可恢复故障，
之后冻结独立确认集。Jev图片JM/JF增量需单独对照，不能从JT推得；生产默认不变。
