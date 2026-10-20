> 状态：进行中（2026-10-20：第二产品原版安装完成，尚待无模型资格检查；未新增真实模型调用）。

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
