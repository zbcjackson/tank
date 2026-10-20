> 状态：进行中（2026-10-20：20专项、全后端6489/1跳过及E2E21/83通过；fake四项完整保存，待本轮第1次独立实现审查，真实四项对照未开始）。

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

## 实现与资格进展

动画实现7d51772a已通过完整后端6469/1跳过和E2E21/83。新目录v2重验digest
`884e6f9b833afbca8229379be6e60bf7e7cd04a7284137d73b47eb3b0eab2488`：4原生
脚本流程/业务/清理通过，32完整观察/32图片准入，编辑页0/16→16/16；5动画
归因也通过，全部32配对PNG与旧图字节相同。16旧archive/manifest保持。
v1驱动在首个页面请求前因初始HTTP日志未建而停止，4计划未运行/0观察；保留
该设置失败及保守cleanup=false原记录，不把它改成成功或删去。另一次准备工作
目录错误没有创建新冻结，日志保留。修正驱动后新目录/新digest，未重写旧文件。

准备子任务a430b36c、共享生命周期6f02740b。同一run_task/run_batch复用模型、
捕获、账本、预算、未知停止和关闭；新适配器仅承担产品fixture/原生服务/实际
观察与独立业务评分。每项复制446未改源/构建，运行官方迁移并初始化首次列表
默认设置后才记录初态；原版工作目录保证正确版本资源。物理before/after SQLite
通过只读backup保存，重复取消仍等待已有复制/关闭完成，不在取消后继续模型。

20专项真实产品/Chromium/SDK/fake HTTP通过（112.85秒）；四正例各3 SDK调用，
V为图片×3，JT为列表图片→Jev文字×2；没有收费选择/视觉API调用。这些不是
模型准确率。错误记录、私有oracle投毒、真实终态DOM故障、非法已知回复、未知
用量和取消/审计/关闭/fixture IO停批均有回归，全部四项分母保持。旧产品恢复/
重复取消的6专项亦通过。4份改动Python pyright0错误/警告，相关ruff通过。
完整新代码后端6489 passed、1 skipped、21 warnings（768.97秒），同时强制两
原版产品fixture及Chromium；E2E21场景/83步骤全部通过（177.583秒），含75项
Chromium契约。web lint/tsc-b、backend/CLI ruff及改动benchmark、4份Python
pyright0错误/警告、前后端重载日志空输出、docs83/diff通过。协议未变。

独立保留的fake-v2四项4/4、12模拟SDK调用（8图片/4Jev文字）、120假tokens，
35执行源/446产品源构建/4687环境文件固定，4清理。runtime digest
`2b5d47b74bcc5c5e543a8e176a5568177b4fbf1a94ff7b5118359d46ed5394e2`。
独立脚本未导入宿主评分器，物理before/after DB、全部表/schema、实际列表/
编辑器URL历史、SDK实际事实/输入图片/合法choice/用量/账本逐项一致。

fake-v1独立脚本漏装pytest自动提供的TypeSafe SDK HTTP边界：首V完成，首JT
在Jev阶段记unknown，立即停批，保留4分母（2运行/2未运行）、5 SDK尝试及
1 unknown。只传占位凭据，但不能把未拦截的未知尝试冒称为零网络或模型失败；
没有真实有效凭据对照。已核对无代理变量；修正独立脚本复用sdk_http测试边界，
另冻边界源hash/新目录fake-v2，不修改生产SDK默认HTTP行为或旧失败记录。
fake结果与真实模型质量/速度分列，本轮真实四项对照仍待审查后新冻结执行。

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
