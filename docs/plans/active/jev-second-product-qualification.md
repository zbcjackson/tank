> 状态：进行中（2026-10-20：无模型资格检查/任务规格冻结和归档完成，隐藏动画阻塞已定位，待独立收尾审查；未新增真实模型调用）。

# 第二真实产品资格与任务冻结

## 目标与范围

承接[主计划](computer-use-jev-vision.md)及用户“开始下一步”，基线38bc1eba。
选择与sqlite-web不同的真实产品，先验证当前观察、候选、动作和业务核验能否
覆盖新工作流，再冻结新任务。资格通过才安排V/JT真实迁移对照；若宿主存在
确定性缺口，本切片交付复现证据和精确修复入口，不花模型调用测已知阻塞。

选用官方linkding v1.47.0：Django书签管理器，使用原版列表、标签组件和编辑
表单。官方源码/锁文件安装到临时目录，官方构建前端，不修改模板、JS或CSS。
只创建隔离SQLite、合成账户和两条保留域名书签。认证是测量前设置，后台任务
通过官方配置关闭；模型接收方、原精确PNG/ref守卫和生产默认均不变。

新任务拟为从列表定位两种位置的目标书签、只改标题、保存并核验返回列表及
数据库。先记录真实控件与原生提交副作用，再冻结目标、允许的自动时间字段、
禁止改动字段及轨迹验收。旧15份archive/manifest只读，模型失误不补跑。
继续沿用record-only授权；后续真实批次仍须冻结源/依赖/应用与任务账本，不能
把本切片的无模型资格配方当成可直接执行的收费批准digest。

## 步骤

1. 固定官方源码归档hash、安装锁文件和工具版本；保存旧15归档/manifest基线。
2. 使用原版服务器及隔离Chromium逐状态检查当前ManagedChromiumChannel与
   ActionBuilder的公开输出。记录可见DOM、所有候选、准入原因、图片捕获/清理；
   脚本操作仅作产品可行性对照，不称为模型或Controller闭环成功。
3. 对两种目标位置运行原生列表→编辑→保存→返回，独立读取SQLite/HTTP/DOM，
   冻结业务条件与所有资格失败。发现确定性宿主缺口即禁止真实模型执行，并将
   最小修复和TDD验收交回主计划，不修改页面以绕过守卫。
4. 归档来源、脚本、PNG、DOM/候选、数据库及HTTP证据，扫描实际凭据；更新
   研究/主计划/索引与面板。完成独立review-and-refactor后将本资格切片关档。

## Tests

- 无模型检查真实产品，源/锁文件/构建输出前后字节核验；从公开Snapshot和
  ActionSet验证列表与编辑器是否完整、所需动作是否存在、视觉是否能合法捕获。
- 原生脚本对照两种目标位置，保存前后数据库所有书签字段、标签及关联，核对
  目标标题、未改记录、返回列表和单次保存POST；明示服务自动写入字段。
- 所有未通过的状态/上下文保留分母，独立复算报告及归档hash；零模型请求，
  不把脚本选目标或数据库真值放入待测候选。关闭全部专用进程/浏览器。
- 本切片仅新增docs和归档，不修改运行代码，无需镜像单元测试。后续行为修复
  应先在既有test_dom.py复现，再扩展既有managed Chromium E2E契约。

## 执行与验收记录

原版linkding1.47.0已安装；442原始文件匹配官方归档，4官方构建输出，446应用
文件前后不变。4原生脚本流程的实际列表/编辑器/单POST/返回列表与物理SQLite
全部bookmarks表/字段/schema独立核验通过；允许的自动变化仅目标date_modified。
32观察完整，列表16/16图片准入通过，编辑页16/16均因隐藏无限loading动画拒绝。
额外5只读归因均拒绝，5张PNG字节相同。零模型调用，非Controller闭环/模型比较。
专用浏览器/运行时/服务已关闭。早期设置/探查失败与不完整留存边界另行声明。

两任务规格/拟议4项顺序/独立业务合同已冻，digest
`6e3532ed8eea83069e7dfc09d0fdfb53ffba20e0fd7467a79a74bb01524f819e`；
这只是声明式记录，不是可执行模型批准。172成员/41PNG归档、21实际凭据扫描、
15旧档核验完成。详见[报告](../../research/jev-second-product-qualification.md)。
行为修复、真实回执/Controller配方和模型比较由主计划后续切片承接，不在发现
确定性阻塞后为凑对照追加调用。docs/diff与面板类型检查通过，待独立收尾审查。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查改动benchmark。
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <修改的Python文件>`，不使用type: ignore规避。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`；空输出通过。
8. `cd test && pnpm test`，要求已有后端/前端运行。
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`，协议或生成物变化时适用。

按项目docs-only例外，本资格切片只执行第9项及diff检查；面板另做类型检查，
实验脚本/原始证据另独立复算。若实际改运行代码，则执行全部适用项。
