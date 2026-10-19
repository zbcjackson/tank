> 日期：2026-10-19；结论状态：已解决（组件光标机制已复现并修复，真实模型路由收益仍待新冻结）。

# DOM原生光标与视觉新鲜度拒绝

## 结论

在真实Chromium145.0.7632.6、两个字段顺序的同类实验表单中，无模型复现了
输入光标闪烁触发PNG严格比较拒绝的机制。每次拒绝保存的是实际参与is_current
的即时图片，阶段均为frame_scene；DOMView比较不变，图差仅1×23竖条、23像素。

- 修复前通道策略：16检查，10通过、6拒绝。
- 修复后通道策略：16检查全部通过；仍逐字节比较PNG哈希，没有像素容差。
- 隐藏光标对照：前后各16检查全部通过。保留光标的旧策略前后分别6/16、7/16
  拒绝；闪烁相位未固定，不把6与7的差别解释为版本效应。

总96检查、108即时PNG、12上下文清理确认，模型调用0、任务输入0。真实像素、
输入值、节点替换、导航、旧引用、非法动作与撤权仍被拒绝，未放宽原输入门。
这是组件机制和修复证据，不是新的真实模型完成率或一般浏览器稳定率。

## 复现与证据范围

复用前轮手写素材表单，两个字段顺序；HTML中预置Work title为Launch，Archive
保持Draft，在观测前聚焦Work并置光标到末尾。这些是新拥有网页的setup，不经过
业务点击/fill派发。随后只采集一次基准图，按0.05/0.25/0.55/0.85/1.1/1.4/1.7/
2.0秒计划日程调用is_current；实际时间另存，不按是否拒绝追加或删除检查。

每版6个全新隔离Chromium上下文（2顺序×3策略），每上下文8检查。initial是
保留原生光标的旧方式，hide是样式表隐藏对照，production是实际通道helper，
不代表更改生产默认selector。诊断子类仅记录每次visual_png返回的真实PNG，
同一PNG进入通道比较；事件current_sha256逐一匹配对应文件，不使用事后终态图
代替拒绝时截图。DOM不变是当次实际DOMView相等比较结果；未逐次保存完整
DOMView原文，保留基准Snapshot和全部图/事件/布尔见证及执行源码。

[旧路由pilot](jev-vision-route-pilot.md)五次拒绝没有内部即时帧。本轮确认组件中
确有相同形状的光标机制，但不能追认为每一个旧事件的唯一原因；旧V2/6、JT6/6
以及所有旧失败/费用均保持。修复后的V/JT真实模型比较仍需新冻结，不复用旧目录。

## 修复与保留的检查

截图与派发前复查统一调用ManagedChromiumChannel.visual_png。通过constructable
stylesheet将普通原生输入光标设为透明，不修改输入框DOM属性或修订号；仍保留
输入值、焦点和选择高亮，其余画面逐字节比较原PNG。当前动作域为有限click/fill，
没有基于插入光标位置的逐字键入动作，也没有任意忽略区域、模糊hash或图片容差。

安装版本Playwright截图实现的caret="hide"会临时修改input/textarea/contenteditable
的style属性；这会影响当前DOM修订守卫，因此未采用这个参数。样式表对照与
通道统一使用同一种不改DOM属性的办法，截图参数保留initial以避免额外临时样式。
该证据来自安装版本截图源码检查和本轮实际DOMView相等回归，不外推所有网页。

is_current失败事件computer_use_freshness只记录首个拒绝检查：binding、navigation、
selected_action、frame_identity、frame_scene或dom_state；capture另记capture_precheck/
capture_state检查组。关联observation_id/action_id和必要两图hash，不在普通事件
携带PNG或正文。观察者抛错仍保持拒绝；capture中途内容改变继续停止。

## 验证与限制

TDD先证明旧截图在自然闪烁后拒绝，再实现统一政策。21项专项通过，包含12项
新回归与旧9项V/JT矩阵；7种真实变化/权限情况仍零派发，捕获竞争和观察者失败
保留拒绝。旧fake模型矩阵是接线证据，不计真实模型质量。

完整回归前两轮分别3失败/6377通过、2失败/6378通过，均1跳过；涉及既有smoke、
策略批次、路由矩阵或本诊断的首次页面加载/观察。失败具体上下文在模型调用及
业务派发前停止，记录Page.goto超时/TargetClosedError；浏览器退出码为0，不能
写成已确认进程崩溃。没有改超时、断言或删除用例；逐项复跑及额外6用例/146次
导航追踪通过。保留两轮失败与全部复跑日志，原因未唯一确定，不宣称光标修复
消除了该加载现象。

最终完整后端6380通过/1跳过（517.40秒），串行E2E21场景/83步骤通过
（150.021秒）；ruff/pyright三个修改Python文件、web lint/类型、CLI lint、dev
日志、docs/diff与面板类型检查通过。面板未作宿主实际渲染验收，独立审查待完成。

## 原始工件

[归档](artifacts/dom-visual-freshness-20261019.tar.gz)与
[逐文件清单](artifacts/dom-visual-freshness-20261019-manifest.json)：
146成员、108PNG，422343字节，SHA256：
`6d95842fad20635f6d7082229fbefc86bb998ebe025e8c178cac405b1ab79b0f`。
包含before/after原始freeze/检查图片/首拒绝事件/快照/结果、两版完整源码快照、
独立图差/hash/阶段/分母重算脚本与摘要、所有TDD及回归日志。修复前源码副本
逐字节匹配当次freeze哈希，修复后同样核验；基线3ee33eb4。逐成员字节数与hash
核验、实际配置凭据字节扫描无命中、旧9归档与基线manifest SHA保持。

后续由[主计划](../plans/active/computer-use-jev-vision.md)继续：新冻结重跑V/JT，
分别测可靠参考路径与Jev弃权后的真实视觉接管；再推进真实产品与已知可恢复
故障。本轮不追加付费请求，不将组件验证改写为采用结论。
