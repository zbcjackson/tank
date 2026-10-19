> 状态：进行中（2026-10-19：修复后36项真实实验及原始归档完成，两臂正例10/10、负例8/8；真实弃权兜底6/6，第2轮结果审查待完成）。

# 修复后路由与真实弃权接管开发对照

## 范围与设计

用户要求继续下一步。沿用修复后的ManagedChromiumChannel、Controller及V/JT，
重新冻结原12场景/24任务，再加入6个颜色语义缺失场景×两臂=12任务，共36任务。
新增：网格/多步抽屉有红色目标各两个顺序、网格无红色两个顺序。颜色按钮改为
中性唯一Option A/B标签，ActionBuilder自然判jev_eligible，结构不含颜色；不得
脚本强制真实Jev弃权、按评分答案路由或从旧结果挑题。仍是手写页面/已见布局的
开发复测，非独立确认集、真实产品或开放规划。

目标/路径/清理完成单列goal_completed，与弃权兜底证据分别评分；新JT语义缺失题
的strict_completed/negative_passed另需兜底证据，保留原始exit_correct与物理终态。预声明新语义缺失题中，JT只有在
对应调色阶段先收到Jev合法非candidate控制，再同一binding以visual_fallback
请求Gemini，才算兜底分支实际执行；完整目标/安全退出另验。猜选即使碰巧完成，
也不计兜底验证成功；错误目标、猜选、错误拒绝和全部未运行项保留分母。记录
直接视觉绕过、弃权兜底、后续返回Jev及全部额外调用/捕获/清理开销。

模型沿用Jev1.14.0文本与OpenRouter Gemini3.8 Flash图片，图片只含实验合成页面，
不发送个人界面/文档/工作区文件。无固定批次请求/token/费用上限，record-only；
120秒/6动作/24观察、SDK无重试，未知用量、运行/审计/清理失败停全批。
新目录/新hash，旧10归档及所有失败/费用不改；准备阶段不分配SDK或浏览器。

## Tests

1. 按TDD扩展既有jev_vision_route.py的显式followup配方，不复制执行器或改生产路由。
   在test_dom.py验证离线36项冻结、旧24默认保留、唯一中性标签先Jev、实际SDK
   fake HTTP弃权→图片→返回与同binding、标签隔离；未知用量时零视觉/后续输入。
   验证允许模型猜选并保留该事实，不能在执行器修复成弃权。扩展现有E2E场景。
2. 完成完整适用回归与第1轮独立review-and-refactor后执行真实模型，逐次保存
   SDK请求响应/输入图、DOM事件/字段/动作审计/终态与清理，保留首次加载异常。
3. 独立重算配对/分层质量与路由，正例失败取共同120秒封顶完成时间，负例退出
   分列。原24复测、新12扩展分开，不将更多同图题当独立布局。归档/凭据扫描/
   旧证据核验，更新报告/主计划/索引/面板，第2轮结果审查后关档。

## 实现与准备

实现6e28a019；6项新增回归与9项既有route共15专项通过（53.56秒）。包含36任务/
66 fake SDK请求、同binding及回复先于视觉请求、猜中却缺证据与未知用量停止。
旧12场景的HTML/goal/oracle及24项顺序与原归档逐值一致，新12项为标签语义变体，
不算独立布局。运行器没有脚本改写Jev回复；palette_evidence仅末端派生评分。

初始准备目录`/private/tmp/tank-route-followup-live-20261019`，36任务、33源hash，摘要：
`8324aba74907e0a9e785defbfb62e07dc445341961fa56377a3a08f6e59512e7`。
真实模型0调用。独立重算脚本在fake矩阵跑通。完整后端6386通过/1跳过（534.16秒），
web lint/类型、backend/CLI lint、两个改动Python文件pyright、dev日志均通过；
串行E2E21场景/83步骤通过（153.230秒）；此为审查前验证，见下节修复后重冻要求。无新协议或生产路由修改。

## 第1轮独立审查

基线ce76f7cd，review-and-refactor，覆盖f3aa2acd、6e28a019及本计划的准备验证记录。
修复提交e7e6dc86。确认并最小修复R1-01：fallback_absent页面的CSS两项均蓝，但JS颜色表仍有一项红，
误点后可能显示selected:red；原负例因非空trail仍会失败，但终态不真实。真实Chromium/
fake HTTP新增回归先复现该错误，再统一JS条件排除fallback_absent，确保误点后显示
selected:blue、保留猜选记录且安全退出失败。原24任务与生产路由不变。

修复后16项route专项通过（54.49秒），完整后端6387通过/1跳过/21警告（536.56秒）；
backend/CLI lint、两个Python文件pyright、web lint/tsc、实际dev日志检查通过。
后端结束后串行E2E21场景/83步骤通过（152.421秒），docs70项与diff检查通过。
本轮仅此一个确认问题，修复已自行复查，无遗留问题；未执行真实模型质量验证。
上述初始摘要因源修复已失效，load_freeze独立确认拒绝；原目录保留且未启动，
必须在本轮验证结束后重新准备新目录/新摘要，真实模型仍为0调用。

## 真实执行与结果归档

第1轮签名修复e7e6dc86、记录03133ada后重新prepare，新目录
`/private/tmp/tank-route-followup-live-reviewed-20261019`，36任务、33源，摘要：
`4b2a12b6fa5be1ec6895764c6377ee911f2e67a0175e1d288f537e87821876ec`。
原24项HTML/goal/oracle/顺序逐值不变。真实36项均运行，66请求（24 Jev/42 Gemini）、
229395已知tokens，无未知/重试/批次停止，36清理确认。

两臂各正例10/10、负例8/8；原24项全部通过，新JT6/6实际控制回复先于同binding
visual_fallback请求，0猜选；直接绕过6次，返回Jev4任务。V/JT正例封顶均值
18.528/6.950秒，为已见手写开发布局中的描述差异，非模型固有速度或采用结论。
[报告](../../research/jev-vision-route-followup.md)及原始255成员/78PNG归档已写，
逐成员/33源/请求图/账本用量/路由先后/评分独立重算通过，21实际凭据值无命中，
旧10归档及清单不变。源码维持第1轮审查后的字节，复用完整回归结果；本次结果
仅docs/工件/外部面板增量，执行docs/diff与面板类型检查，第2轮独立结果审查待完成。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`，另查改动benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部修改Python文件>`，不以type-ignore绕过。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与完整后端串行，复用现有managed Chromium场景。
9. `python3 scripts/check_docs.py`及`git diff --check`，核验冻结/归档/旧证据。
10. 仅协议/生成物变化时`python3 scripts/check_protocol_sync.py`；本片无协议变更。
