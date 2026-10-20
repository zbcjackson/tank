> 状态：已完成（2026-10-20：无付费诊断/修复、完整验证及第1轮独立收尾审查完成；旧失败不重判，新开发配方仅prepare）。

# 同名复选框定位与标题列写入语义

## 范围与成功条件

承接用户“继续下一步”和[主计划](../active/computer-use-jev-vision.md)。基线3ecbe7f0。
旧sqlite-web实验V6/6、JT5/6及其42请求、全部失败/费用/12归档保持不变；本轮
不调用真实模型，不改变生产默认策略，不宣称修复能提高模型质量或唯一解释旧none。

1. 未修改sqlite-web0.8.1页面/JS/CSS，仍用隔离临时合成数据库，分别实际执行
   全选后改标题与仅选标题列。增加SQLite UPDATE OF列触发器，只在新夹具记录
   触及列及旧/新值，区分“其他值不变”和“仅写title列”，不按新语义重判旧任务。
2. 按TDD最小修复DOM原生同名checkbox：逐实际节点绑定checked事实/效果，
   不用同名值、序号或新节点的勾选冒充旧节点效果。有唯一原生表单name时明确
   作为字面上下文；没有可区分语义时仍判歧义/转视觉，不能把opaque绑定key当语义。
   不添加产品专用selector、人工aria标签、字段名推测或oracle路由。
3. 新无模型诊断记录修复前后候选、逐列动作/终态、HTTP/数据库列写审计、截图与
   清理。脚本实际输入/有限候选提议只作为功能准入证据，明确不是模型成功率。
   追加新目录冻结准备，不分配SDK/外部HTTP客户端，不执行收费批次。

## Tests

- 逐条red→green：同名节点实际checked读回及歧义路由、原生name上下文、重复/无名
  语义不能被运行身份伪装唯一，preventDefault、替换/导航/撤权和伪造checked事实
  不得确认效果或重放输入。保留唯一具名旧行为。
- 使用既有test_dom.py与managed Chromium E2E域，不新建同域feature；原始产品
  通过独立固定venv启用，数据/模型均不真实外发，诊断禁止SDK客户端构造。
- 真实产品两种手动路径与受控宿主提议路径：最终值相同但触及列不同；强列条件
  下全选不算完成，title-only可完成，不改变原value-only生产实验评分。
- 冻结/来源/应用环境漂移拒绝、重复目录拒绝、停止/清理回归；全部新证据独立
  重算、实际凭据扫描及旧12归档核验，报告/主计划/索引与面板更新。
- 完整验证后按agents/code-reviewer.md完成独立review-and-refactor；无确认问题
  即止，至多3轮。若源码改动导致冻结失效，保留旧目录并新冻结，不改写旧证据。

## 实施与结果（2026-10-20）

基线3ecbe7f0，计划b30d2de8，实现c76af867。[诊断报告](../../research/jev-checkbox-grounding.md)
记录两个数据顺序、before4/after8个隔离上下文，36次实际输入、44任务PNG、
0模型调用/客户端尝试，12清理。页面源不改，对应初始图字节相同；逐列候选
0→3。全选触及id/notes/title而title-only仅触及title，最终值均可通过旧条件。
受控宿主强列目标title两例goal_verified、all两例effect_unknown；all已提交
一次，不代表派发前拦截或回滚。旧V6/6、JT5/6及12归档不变。

同名checkbox的实际节点checked事实/效果和唯一原生name上下文已接通；
无名/重复语义仍转视觉，不把opaque ref当语义。11项新回归、完整后端6422
通过/1跳过、E2E21场景83步骤及其余适用静态检查通过；协议不变。
新真实开发配方仅prepare12项，digest见报告，无started/result/spend，仍为
value-only，不是新强列模型实验。独立审查与最终文档/面板检查通过，关闭本子计划；
下一真实模型对照、跨页/第二产品及独立确认继续留在主计划，不属于本子计划未完项。

## 第1轮独立收尾审查

review-and-refactor，基线3ecbe7f0，覆盖b30d2de8、c76af867及5212d0a5，未发现
源码或结果计算的确认缺陷。独立复跑11项专项通过（24.77秒）；当前源码未改，
复用6422/1跳过及E2E21/83、lint/type/dev日志检查。869成员和两阶段各自35份
源码逐字节/hash一致；before宿主对应基线且保留早期无host驱动，after对应当前
实现，不用当前哈希覆盖before。654 app文件、12 DB全行/schema/列审计、HTTP、
候选ref SHA/checked、host提议/回执和44任务图独立重算通过，4组初始图相同。
0模型/客户端尝试、36输入、12清理以及旧12归档/清单、21实际凭据扫描一致；
面板数据等于摘要、筛选/tsc通过。新12项value-only配方hash仍有效且无启动记录。

报告仅澄清逐案例freeze/source检查属于after现行驱动，before早期版仅启动时
校验/复制源；未改源码、面板、原始证据或冻结。无遗留问题，立即结束第1轮；
收尾文档由评审者自检，无后续独立复核。docs/diff通过后关档，不凑额外轮次。
下一付费实验与更广能力仍由active主计划承接，本切片无新增条件触发项。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`及改动benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 TANK_REAL_PRODUCT_PYTHON=<app-venv>/bin/python uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部改动Python>`，不得type-ignore。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与完整后端串行。
9. `python3 scripts/check_docs.py`、`git diff --check`，核验冻结/归档/旧证据；面板类型检查。
10. 仅协议/生成物变化时`python3 scripts/check_protocol_sync.py`；本切片预计无协议变更。
