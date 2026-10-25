> 日期：2026-10-25；结论状态：open（最小实现、完整回归及原版产品离线资格通过，待独立审查；零真实模型请求。）

# 已核验返回：同一恢复额度内重新Jev准入

当前显式jev-action-vision在已核验动作后返回完整状态时，可在原有的一次恢复机会
中重新Jev准入。原版linkding同一公开只读任务的SDK假HTTP从2Jev/2图片变为
3Jev/1图片，仍4次SDK、3正确原引用点击、零POST/书签业务表变化、清理确认。
这证明路由机制和边界，尚未测量真实Jev选择或真实端到端收益；默认配置保持。

## 根因与最小修复

原像素实测的列表A→编辑B→Cancel返回A，两个动作均已核验。控制器语义状态键
刻意忽略随机观察/引用身份，以识别循环；visited[A]还保留首次访问时的已核验
动作数0，返回时当前数为2。但旧路由未使用这个差异，只要状态重现，第一次恢复
就直接图片，因此Keep这个文字可区分动作也读图。

修复保留语义键、visited和全部计数。只有显式ActionAdmissionSelector、当前状态
完整且可用、期间已核验动作数增加、本状态尚有原一次恢复额度，且ActionBuilder
原理由为jev_eligible/visual_required，才在该同一额度中重走原Jev准入；原选择失败
仍转绑定图片。computer_use_route附recovery=verified_return，原候选原因保持。

该机会立即消耗原恢复额度，不新增循环/派发/Advisor/观察额度；已核验动作不等于
目标进展。回归中的A↔B循环在无Advisor或Advisor返回unable时均仍4次派发后停止；无已核验动作的反复观察继续原图片恢复；
不完整/不可用观察、未知效果/用量、撤权和陈旧引用仍沿原拒绝。其他选择器和默认
配置不改，不通过把generation/observation_id加入状态键或重置循环记忆绕过保护。

## TDD与边界

先写真实Chromium/Controller/TaskRuntime/官方SDK假HTTP回归：实际Edit2→Cancel→
Keep三步均完成，旧代码最后请求为visual而非Jev，唯一预期差异处红灯（3.71秒）。
最小实现后同测试通过（2.55秒）；完整候选和正确实际导航均保留。

新增六情况：正常选择、Jev控制转图片、未知用量、撤权、陈旧Keep节点、Keep点击无
实际效果。6项通过（7.49秒）；后四项不再实际导航至Keep，未知效果仍pending并以
unknown/effect_unknown停止，陈旧引用在派发前stale_reference拒绝。原生恢复/混合
链路34项通过（2.23秒），包括原选择器不变和有/无Advisor的同次数循环停止。
既有chat.feature同域managed Chromium选择器加入这些DOM用例，未新建feature。

早期测试写入路径错误未创建用例，不计行为红灯；恢复后才得到有效红灯。边界测试
初稿将派发前陈旧拒绝误写为not_sent，按真实原有stale_reference语义修正；两处
既有测试中的“必须图片”预期按本次有界变化更新，派发/停止上限未减弱。类型检查
指出回调类型递归推断，加入显式httpx.Request/Response标注后通过。一次完整套件
在2445通过后为固定最终测试源而主动中断，不计完整通过；随后从最终源完整重跑。

## 验证边界

无真实模型、无旧请求重发，不改原实测或将9.042秒算作已节省。新原版产品资格
使用同一公开合成目标/原模板与新源冻结；执行入口仅prepare/fake，live立即拒绝，
实际凭据加载代码已移除。SDK假HTTP和外部socket拒绝保持。测试只证明线路和
绑定/效果/完成/循环限制，不证明真实Jev会选Keep或一定比图片更快。

## 原版产品离线复核

源码提交ad128448后，对原版linkding1.47.0同一合成预览任务重新做像素互换资格，
17完整列表候选/6编辑页候选保持；两个图分配的公开文字/几何规范化后仍相同。
没有改产品446项源/构建文件、26固定依赖、模板或可访问名称，也没有业务DB完成
补强。固定原目标：按红三角找到书签，Edit查看、Cancel、右侧Tags的Keep；完成
URL初始为假，独立审计还要求实际正确记录2编辑页和随后Cancel/Keep的来源顺序。

新冻结SHA256为9bc0ee0552f884b0c2c5f47658d1feac7d59e2d106f3f4d12f223a7947838ad6，
绑定三个脚本、354运行源/依赖和真实产品。实际路线为假Jev need_more_context→
假图片c11 Edit→假Jev c6 Cancel→假Jev c17 Keep；3次原引用动作全部核验完成。
末次route保留visual_required候选原因并附recovery=verified_return，动作级准入
accepted=true；未缩候选或复用旧动作引用/PNG派发。只有第一次有绑定1280×720
PNG，原帧/proposal/receipt关联继续严格检查，清理confirmed。

全部HTTP为GET，独立物理SQLite重读全部bookmarks业务表/列与schema一致；不
声称auth/session表或整库零SQL写入。4次假SDK、48人工usage单位，不代表真实
用量/费用或速度。live CLI被拒绝、实际凭据加载代码已移除，官方SDK假HTTP及
外部Python socket拒绝生效；没有新真实模型请求或旧未知请求重放。

## 完整验证

最终完整后端6844 passed、1 skipped、21 warnings，2036.23秒；唯一跳过为
ToolManager requires full config。E2E24场景/95步骤全通过，4m11.929s，实际本地
Sherpa/回环SDK/隔离DB；外部Python连接尝试0。finally恢复原后端health200，后端
reload错误空，前端最后50行只检查一次且为空。临时caffeinate -is，无全局设置变化。

Web lint、tsc -b --noEmit、后端/CLI ruff、全部3改动Python的pyright通过；E2E包含
改动TS和新DOM恢复矩阵。文档检查通过；协议/生成物未改，protocol-sync不适用。
354运行源及4改动Python/TS均在最终完整套件开始前固定并逐SHA复核，所有检查
用当前字节，不复用前轮全套。81历史工件及默认配置SHA保持。

## 审查与证据

当前等待项目review-and-refactor；不以未完成审查代替通过。[原始归档](artifacts/jev-verified-return-20261025.tar.xz)包含TDD/边界失败及最终完整运行日志、所有
检查/源收据、E2E生命周期、原版产品资格与完整假HTTP/执行/HTTP/业务DB/清理证据。
当前封包1728普通成员，SHA256为
de2398284071f124b2be8fb87d4fd77c5faaef156ec16acbbc0a1c5dcc5d3958。
verify.py仅离线检查，不重放任务或创建模型；可用当前项目venv的Python在解包后复核。

下一项真实净收益验证交回[主计划](../plans/active/computer-use-jev-vision.md)与
[backlog](../backlog.md)，需另冻同任务，保留失败且不凭假HTTP挑成功或宣称省时。
[实现计划](../plans/active/jev-verified-return.md)定义本片的有界改动与完整检查。
