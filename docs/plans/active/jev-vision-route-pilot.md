> 状态：进行中（2026-10-19：开始新布局的V/JT完整路由开发对照，真实模型尚未运行）。

# Jev结构优先与视觉接管路由开发对照

## 范围与假设

用户要求继续Box比较后的下一步。复用现有Controller、ManagedChromiumChannel、
VisualSelector和TaskRuntime，比较V（共同规则后总用Gemini视觉）及JT（适用时
Jev文本，其余同一Gemini视觉，后续可返回Jev）。这是主计划第二级机制开发，
不包含开放自然语言规划或Jev图片/Box自动派发，不据此采用生产策略。

新建实验专用手写网页，真实隔离Chromium执行，无用户浏览器/真实业务数据。
三个新布局：双字段素材表单、颜色标记网格、结构→颜色→表单的多步抽屉。各两种
顺序；另有网格红色目标不存在、表单控件在模型响应后被替换、提交无可见效果，
各两种顺序。共12个新场景×2臂=24任务，是预定开发问题数，不是费用上限。
页面是受控夹具，不是实际产品设置页或独立真实应用确认集。

V只在benchmark内将语义选择委派给现有VisualSelector；JT直接使用既有实现，
共同动作构造/执行/核验/规则不变。Jev1.14.0文本、同一Gemini3.8 Flash图片，
模型/提示/代码/HTML/任务/私有评分先冻结，不按答案改变路由。不对模型强制弃权
来演示视觉接管，不用评分标签选择路径。图片只有合成网页内容发往OpenRouter，
Jev收到页面结构文字；不发送个人界面、AX或工作区文件。

## 步骤及Tests

1. TDD在现有test_dom.py添加离线准备与标签隔离测试，新增最小benchmark配方。
2. 真实Chromium+真实SDK、只替换外部HTTP，验证V/JT相同任务，结构→视觉→结构
   和共享规则、按需截图、独立输入/事件/终态、全部24分母、未知用量/清理停止、
   过期控件零派发、效果未知不重放、无模型重试、冻结变更及目录复用拒绝。
3. 通过完整适用回归和首轮独立review-and-refactor后执行授权真实模型。每任务
   120秒，最多6动作/24观察，账本record-only无固定批次请求/token/费用上限。
   已知模型误判保留失败并继续；未知用量、运行异常/审计/清理失败停全批。
4. 独立评分所有任务：正例完整目标+路径约束+清理通过，负例正确退出分别报告。
   保留全部失败；正例失败封顶完成耗时取120秒，实际失败耗时另报，冷启动含
   浏览器/客户端创建与关闭；不把早停算更快。记录路由用途/返回、所有请求/图片/
   用量和费用口径。归档hash/凭据扫描、更新主计划/索引/面板，第2轮结果审查。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`，另查新benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部修改Python文件>`，不以type-ignore绕过。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与全后端串行。
9. `python3 scripts/check_docs.py`及`git diff --check`，核验冻结/归档/旧证据。
10. 仅协议/生成物变更时`python3 scripts/check_protocol_sync.py`；本片无协议变更。
