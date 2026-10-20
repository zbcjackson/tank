> 状态：进行中（2026-10-20：开始列表定位/编辑/返回确认工作流；无模型探查完成，尚未收费调用）。

# 真实产品列表定位与编辑往返

## 目标与范围

承接用户“开始下一步”和[主计划](computer-use-jev-vision.md)。基线e00698bc。
从未修改sqlite-web0.8.1列表开始，定位指定记录、勾选标题列/填入/提交，并在
返回列表后核验真实可见内容和物理数据库。仍为单产品开发验证；不是独立holdout。
只使用新合成数据库与独立app/Chromium，不访问个人数据或更改生产默认。

无模型探查已确认Edit候选无所属行文字，上下文不足时走视觉。最小补齐原生
HTML表格行的可见文字上下文，不添加产品专用aria/selector到生产DOM通道，
不改变原页面/JS/CSS、精确PNG/ref/授权/未知效果不重放守卫。

本轮在已有真实产品benchmark增加显式workflow准备选项，保留默认原12项表单
配方。新配方为两个目标记录位置×普通/首次编辑GET503，各V/JT，共8任务；
两种条件分别平衡先后，全批首臂2:2。模型从实际列表选择Edit，不在宿主选定目标
或直接跳转目标编辑URL。故障在首次进入编辑页时注入，Retry仅重试GET。
提交后的产品原生跳转回列表可满足返回，不额外强迫点击；终态必须真实显示
目标新标题、原注释和其他记录，物理数据库恰一次正确UPDATE/POST且schema不变。

两臂共用实际mode=ro数据库回执，workflow额外读取实际DOM表头/单元格及path
作为列表回执，不读goal/oracle。另保留实际观察到的编辑器记录id历史，明确是
已观察事实而非当前页状态，为正确记录已定位提供阶段证据，不放松原无进展守卫。
强验收同时核对列表→正确编辑GET→一次POST→
返回列表的HTTP时序、可见列表与DB，不能只因DB写对或URL看似返回就成功。
仍按其他字段最终值保持，不新增SQL只能写title列条件。

沿用Jev1.14文字(api.typesafe.ai)、Gemini图片/文字(openrouter.ai)与既有
无固定批次请求/token/费用上限的record-only授权。每任务120秒、6动作、24观察，
SDK零重试；未知用量/运行/审计/清理失败停批，保留全部分母，不补跑模型错误。
冻结新8项、源码/依赖/654应用文件与预算治理后执行一次。全部14旧归档/manifest、
原评分/费用/失败均保留，不能与旧表单结果混成独立样本或从跨轮差异唯一归因。

## 步骤

1. 保存无模型探查；计划提交后按TDD补实际需要的通用行上下文，真实DOM/SDK
   公共投影验证行为，不把测试脚本选择称模型能力。修复对应现行设计/插件文档。
2. 按TDD扩展既有benchmark的workflow配方、实际DOM列表回执及路径/终态独立
   评分，复用旧run_task/run_batch生命周期。普通与故障均测试真实上游app和
   Chromium，只有外部模型HTTP为fake；旧配方/冻结拒绝和停止/清理规则保持。
3. 完整适用验证后委派独立review-and-refactor，第1轮实现审查；同一任务最多
   三轮，给真实结果审查保留轮次。通过后新目录冻结、保存源副本并执行一次真实批次。
4. 不导入宿主评分器地重算全8任务、业务/列表/HTTP轨迹、调用/接管/返回/用量、
   全部失败120秒封顶耗时。归档/实际凭据扫描/14旧归档核验，更新研究报告/
   主计划/索引/面板，再在剩余轮次内独立结果审查；无遗留即关档。

## Tests

- 在既有test_dom.py逐项red→green：表格行可见上下文能区分同名控件，行身份
  与实际引用/效果一致；过长/缺失/相同行上下文不伪造区分，行变更后拒绝旧引用。
- workflow准备不建客户端/服务器、四案例八项/先后/完整冻结、默认十二项不变；
  实际SDK/fake HTTP通过真实列表选记录、编辑、自动返回列表及GET故障恢复。
- DB正确但列表缺失/错内容/错页不得完成；错误记录写入不得完成；私有oracle
  投毒不进入观察/请求；未知用量/取消/清理失败保留八项分母且不重放POST。
- 扩展既有managed Chromium E2E的通用行上下文契约，不新建同域feature。
  原始产品资格由TANK_REAL_PRODUCT_PYTHON显式启用，本轮完整验证必须启用。
- 所有模型/GUI真实测量与fake接线证据分开；源码修改后新freeze，不修补旧目录。

## 实现与验证进展

原生行上下文只读可见文字，未修改应用；相同初始列表PNG逐字节一致，Edit从
无行语义变为携带实际记录编号/标题/注释，结构准入由visual_required变为
jev_eligible。新workflow选项保留默认12项表单配方；实际列表内容/path、实际
观察到的编辑器id历史和物理DB/HTTP共同验收，原无进展守卫未放松。

23项新增回归通过（39.49秒）；完整后端6445 passed、1 skipped、21 warnings
（645.99秒），启用固定应用环境及TANK_REQUIRE_CHROMIUM=1。web lint/tsc-b、
backend/CLI ruff、3份改动Python的pyright（0错误/警告）、dev日志空输出通过。
E2E21场景83步骤通过（158.366秒），managed Chromium为51契约。初轮E2E中
51项子测试均通过，但遗漏同步旧46数量断言；修正该断言后完整重跑通过，未放松
产品守卫或修改Python源码。协议未变。进行第1轮实现审查，未运行收费模型。

真实产品/fake HTTP完整8项已保存`/private/tmp/tank-product-workflow-fake-20261020`，
digest `d7bb8616e03d4b751c9ec6c03cb68a4418ac0458a38359f0df0f86120833dec6`。
独立重算8项全部通过、4项GET恢复、36次fake SDK调用/360假tokens、26任务PNG，
34源快照与654应用文件一致，8清理。只证明功能接线/核验，不是模型成功率。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`及全部修改benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 TANK_REAL_PRODUCT_PYTHON=<app-venv>/bin/python uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部改动Python>`，不得type-ignore。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与完整后端串行。
9. `python3 scripts/check_docs.py`、`git diff --check`、冻结/归档/旧证据核验和面板类型检查。
10. 仅协议/生成物变更时`python3 scripts/check_protocol_sync.py`，否则不适用。
