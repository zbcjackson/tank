> 状态：进行中（2026-10-20：隐藏动画修复已通过完整验证；开始第二产品Controller配方，尚未新增Jev/Gemini实验调用）。

# linkding真实Controller与V/JT迁移对照

## 目标与范围

继续用户“开始”授权的修复→重验→V/JT对照，承接
[主计划](computer-use-jev-vision.md)、[动画修复](dom-hidden-animation.md)和
[第二产品规格](../../research/jev-second-product-qualification.md)。完整任务基线
21786a87，动画实现7d51772a；同轮独立审查累计最多三轮，不因拆子计划重置。

沿用已声明的原版linkding1.47.0、两条合成书签和两种目标位置，V/JT各2项、
共4项，先后1:1平衡；不添加模型结果后挑选的任务。列表由模型自行选择Edit，
只改标题，原生Save返回列表。认证是测量前设置，完整计时仍包含任务fixture/
启动/关闭。不修改产品模板/JS/CSS、不添加生产专用标签、不改变默认策略。

观察提供实际只读书签投影、实际当前列表和已观察编辑器历史；不比较私有oracle
或将期望值当实际事实。完成同时要求当前正确列表与实际数据；独立评分再核全部
10个bookmarks表/字段/schema、正确编辑路径与单POST302/返回HTTP。仅允许
目标标题及自动date_modified增加，其他字段/关联不变；不声称恰一次SQL写。
这是有业务回执的两任务开发对照，不是纯像素能力排名或独立采用确认。

## 步骤

1. 完成动画修复及新目录4流程/32观察/5动画样本重验，保持旧16归档只读。
2. TDD扩展既有真实产品benchmark的任务生命周期，以最小产品适配接入linkding；
   复用模型/记录/期限/配额/取消/关闭与批次停止，原sqlite-web默认配方不变。
   本地按官方锁文件安装的应用仅作为外部fixture，不添加项目依赖。
3. 新配方prepare只冻结源码/依赖/应用/种子/目标/顺序，不读取凭据或建客户端。
   真实产品/Chromium/SDK与fake外部HTTP验证四项、业务/DOM/HTTP和停止分母。
4. 全部适用验证通过后做第1轮review-and-refactor，覆盖21786a87以来完整任务：
   动画修复、无模型资格、Controller配方与fake证据。修复后新的源变化必须新冻。
5. 经审查后全新可执行freeze，只执行一次实际4项，不补跑模型失误。沿用Jev
   1.14文字到TypeSafe和Gemini图片/文字到OpenRouter、record-only既有授权；
   每项120秒/6动作/24观察、SDK零重试。未知用量/运行/审计/清理失败停批，
   保留全部4项分母和未运行项，不借另一模型绕过硬停止或重放未知POST。
6. 不导入宿主评分器地重算全部物理DB/当前列表/实际编辑器历史/HTTP、调用/
   接管/返回/用量/费用与完整耗时。归档、真实凭据扫描与旧16档核验后，用剩余
   审查轮次复核实现修复和真实结果；无遗留即关档，主计划继续保留采用门。

## Tests

- 在既有test_dom.py按vertical red→green验证准备不分配客户端/服务器、两例
  四项/顺序/冻结篡改与旧默认12项/8项workflow保持。
- 真实未修改应用/Chromium和真实SDK/fake HTTP完成列表→编辑→保存→返回；
  观察与请求不含oracle，投毒私有oracle不改变动作。错误记录或缺/错列表不成功。
- 全部书签字段/标签/其他表/schema核验与单POST，复制应用源及原安装保持；
  未知用量/非法回复/取消/审计/关闭失败保留四项分母、不重放POST。
- 复用既有managed Chromium E2E对通用动画/引用/图片守卫的75项契约；不新建
  同域feature。外部产品测试通过TANK_LINKDING_ROOT显式要求，完整验证启用。
- fake、无模型与真实SDK测量分列；原始协议/结果不可修改，源码变化新freeze。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查全部改动benchmark。
4. `cd backend && uv run pytest`，强制Chromium、sqlite-web及linkding外部fixture。
5. `cd backend && uv run pyright <全部修改的Python文件>`，不使用type: ignore规避。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`；空输出通过。
8. `cd test && pnpm test`，在完整后端测试后、后端/前端运行时执行。
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`，协议或生成物变化时适用。

代码/测试稳定后全套适用检查及最多三轮独立审查；每逻辑子任务签名提交，不推送。
