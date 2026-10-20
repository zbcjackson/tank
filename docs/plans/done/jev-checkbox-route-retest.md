> 状态：已完成（2026-10-20：12项真实复测、归档及第1轮独立结果审查完成，V6/6、JT6/6，GET恢复各2/2；后续列表工作流由主计划承接）。

# 逐列候选修复后的真实V/JT开发复测

## 范围与成功条件

承接用户“开始下一步”、[主计划](../active/computer-use-jev-vision.md)及
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

## 执行结果

一次固定批次完成，V6/6、JT6/6、故障恢复各2/2，12清理；V均时28.771秒，
JT5.000秒。41请求、478151已知tokens，V20图片、JT20文字＋1图片；一次
Jev none→Gemini Retry→Jev编辑完成。六个编辑任务均选逐列title框，原失败
开发案例此次完成，不把跨轮变化唯一归因修复。详见[报告](../../research/jev-checkbox-route-retest.md)。
新819成员归档完成、21实际凭据扫描及13旧归档/manifest核验通过；23项既有
专项通过。源码未改，按docs-only例外收尾；独立结果审查/最终文档与面板检查通过，
本子计划关档。后续列表/跨页、第二产品与独立确认留在主计划，不属于本子计划未完项。

## 第1轮独立结果审查

review-and-refactor，基线70a0c39a，覆盖f7841a01与92615f72完整diff及外部面板。
从819成员原始归档独立核验12物理DB全行/schema/精确单写、HTTP POST/GET恢复、
41 SDK请求/回复先后、call_id/task_id/用途/用量、图片字节和候选选择对应sent/
verified步骤，全部一致。V/JT各6/6、GET恢复各2/2，均值及82.62%批内差异复算
一致，6对均更快；不从此推出独立非劣或稳定收益。唯一兜底为Jev none后同binding
Gemini Retry，再返回Jev选title框、填标题和提交，不能称视觉替选title。

34源/654 app字节、51 PNG（33任务/18资源）、六组旧V首图相同及全部六个编辑
title框选择均核验；没有_column_writes或强列目标。原13归档/清单与基线相同，
21实际凭据扫描无命中，面板嵌入的新/旧摘要与选择记录逐值一致，筛选/tsc通过。
源码未改，复用调用前23项专项及已验证6422/1跳过、E2E21/83与静态检查；本轮
按docs-only例外运行docs77及diff检查，不重复完整代码回归或真实模型调用。
无确认问题或遗留问题，立即结束第1轮；本轮仅收尾文档由评审者自检，无后续
独立复核。原始证据/源码/面板不改，生产默认保持；本切片无新增条件触发事项。

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
