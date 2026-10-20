> 状态：进行中（2026-10-20：用户授权开始修复后真实模型复测，冻结预检通过，尚未调用）。

# 逐列候选修复后的真实V/JT开发复测

## 范围与成功条件

承接用户“开始下一步”、[主计划](computer-use-jev-vision.md)及
[候选诊断](../../research/jev-checkbox-grounding.md)。基线70a0c39a，复用已经独立
审查的c76af867实现；本切片不计划修改执行源码、产品页面或生产默认。

执行已准备且未启动的`/private/tmp/tank-checkbox-route-ready-20261020`，digest
`8b36857c1ab5dd0fed263e410a833cfe849fa6ce69633fc9aabc2df7ea8b90b7`。
34份执行源码、654项固定sqlite-web0.8.1环境文件、依赖与6案例×V/JT共12项
均已核验。只使用新合成SQLite数据库和各任务独立app/Chromium，全部13份旧
归档/manifest保持；不修改已启动记录、不补跑模型错误。

V为Gemini图片选择；JT为Jev-1.14文字优先，弃权/结构不足时同一Gemini图片
接管。接收方沿用api.typesafe.ai与openrouter.ai，模型配置与固定先后顺序不改。
覆盖创建/编辑各两种数据顺序，以及各一例首次GET503已知恢复；不重放未知POST。
没有Jev图片/Box、开放规划、列表入口、第二产品或独立holdout。

沿用用户先前无固定批次请求/token/费用上限的record-only授权。每任务120秒、
6动作、24观察、SDK零重试，未知用量/运行/审计/清理失败停批，保留全部计划分母。
“保持其他字段”仍按最终值验收，不额外加入只能写title列的强条件。两臂共用
只读实际数据库回执，末端另核全行/schema/恰一次正确写入与POST及清理。

成功条件是按冻结执行并完整留证、独立重算和审查，不以必须得到正向模型结果
为完成条件。重点报告编辑时选择全选还是逐列、原失败开发案例表现、Jev控制回复/
图片接管/返回路径。新结果与旧V6/6、JT5/6分开；不能把非随机跨轮变化唯一归因
于候选修复，不能以少图替代质量或将已知开发案例称作独立采用确认。

## 步骤

1. 核验freeze/源码/app环境、凭据存在、未启动及13旧归档；保存34执行源快照。
2. 运行既有真实Chromium/fake-HTTP产品与checkbox相关专项，零付费检查；源码
   未改则复用前轮完整后端6422/1跳过、E2E21/83及静态检查，不无意义重跑。
3. 签名提交计划后，按固定digest执行一次批次。逐项监看进度，保留请求/回复/
   PNG、动作/路由/用量、HTTP/SQLite物理文件和资源清理，触发停止即保留余下行。
4. 不导入宿主评分器地重算全部业务结果、候选选择、接管与返回、用量及失败120秒
   封顶耗时。费用仅用历史冻结估算，服务报告费用另列，不能称账单。
5. 新归档逐项核验、实际凭据扫描、13旧归档核验；更新研究报告/主计划/索引及
   面板。适用验证后按agents/code-reviewer.md完成最多三轮review-and-refactor，
   无可操作或遗留问题即止；子计划完成移done，后续能力由主计划承接。

## Tests

本切片没有新执行行为，不新增镜像测试或新同域feature。执行现有test_dom.py
的real_product及同名checkbox/name相关回归：固定原始app、实际SDK/fake HTTP、
两臂创建/编辑/GET恢复、冻结/取消/清理/分母，以及实际节点checked与语义歧义。
零模型专项结果与真实模型结果分开。若确认需要改源码，先用现有域红测复现再
最小修复，执行全部适用检查并另建冻结，保留已发生证据，不修补本次freeze。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`，仅docs变化则按项目例外不适用。
2. `cd web && npx tsc -b --noEmit`，仅docs变化则不适用。
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`及改动benchmark；仅docs则不适用。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 TANK_REAL_PRODUCT_PYTHON=<app-venv>/bin/python uv run --no-sync pytest`；仅docs则不适用。
5. `cd backend && uv run --no-sync pyright <全部改动Python>`，无Python变化则不适用，不得type-ignore。
6. `cd cli && uv run --no-sync ruff check src/ tests/`，仅docs则不适用。
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`；空输出通过，仅docs则不适用。
8. `cd test && pnpm test`，与完整后端串行；仅docs则不适用。
9. `python3 scripts/check_docs.py`、`git diff --check`、归档/冻结/旧证据核验及面板类型检查。
10. 仅协议/生成物变化时`python3 scripts/check_protocol_sync.py`，否则不适用。
