> 状态：进行中（2026-10-19：准备光标修复后V/JT复测及真实弃权后视觉接管，模型尚未运行）。

# 修复后路由与真实弃权接管开发对照

## 范围与设计

用户要求继续下一步。沿用修复后的ManagedChromiumChannel、Controller及V/JT，
重新冻结原12场景/24任务，再加入6个颜色语义缺失场景×两臂=12任务，共36任务。
新增：网格/多步抽屉有红色目标各两个顺序、网格无红色两个顺序。颜色按钮改为
中性唯一Option A/B标签，ActionBuilder自然判jev_eligible，结构不含颜色；不得
脚本强制真实Jev弃权、按评分答案路由或从旧结果挑题。仍是手写页面/已见布局的
开发复测，非独立确认集、真实产品或开放规划。

目标/路径/清理完成与弃权兜底证据分别评分。预声明新语义缺失题中，JT只有在
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
