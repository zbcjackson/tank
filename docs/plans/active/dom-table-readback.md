> 状态：进行中（2026-10-24：显式表格GET读回已实现；定向24项、后端6793项/1跳过、E2E24场景/95步骤及静态检查通过，待独立审查；默认不变，无真实模型调用。）

# 原始DOM表格业务结果读回

## 目标与范围

承接[主计划](computer-use-jev-vision.md)与[资格阻塞研究](../../research/jev-runtime-acceptance.md)。
用通用可见DOM表格事实接通已有GoalContract、submit效果、进展与完成核验；不改
Controller/选择策略，不读取数据库或提供benchmark完成补强，不放宽URL/编辑框判据。

最小实现只在可信浏览器配置readback_tables: true时启用，默认false。对指定URL上
有唯一表头签名的简单HTML表格，读出全部可见命名列/正文行，形成有界status事实；
调用者以同一公开结构声明完整期望值（含需保留的字段/行），复用已有严格事实等值。
新事实生成前强制一次只读GET重新加载页面；不重发POST。表单含启用的可编辑文本字段时不刷新/
不提供表格保存证据；该模式以GET响应替换结果页的临时状态。
缺表/重复表头或表签名、合并单元格、隐藏/可编辑数据、超限、不完整或陈旧观察均不
形成可匹配事实；新命名空间不能由页面自报status冒充。事实只证明声明页的DOM结果，
不声称未显示的页、列或数据库状态。原字段/模型权限、候选32上限、时限和清理保持。

## 步骤

1. 在既有test_dom.py逐个红绿验证简单表格事实、限定URL/范围和公开helper；实现
   只读GET刷新后再观测，不把临时编辑/乐观显示当保存。保持默认观察不变。
2. 同一文件增加反例：未保存、只导航、错误行、保护字段/其他行改变、同名/结构歧义、
   隐藏/合并/可编辑/超限、伪造status、读回失败/变更与原绑定守卫。
3. 使用原版sqlite-web、真实Runner及现有双SDK假HTTP，复现原三步正确保存并确认
   由effect_unknown变为goal_verified；独立DB仅用于测试后核验。增加改错/未保存反例。
4. 更新插件README、后端开发/测试和现行设计、主计划与索引。既有chat.feature加入
   同域回归，不新建feature。通过全部适用验证及最多3轮独立审查后结案。
   六任务真实模型验收仍按backlog条件另行资格/冻结，本片不追加收费调用。

## Tests

使用TDD逐个行为切片。已有test_dom.py覆盖真实Chromium及Runner，不替换Controller、
执行器或生产选择器，只替换外部模型HTTP。真实产品原始模板/JS/CSS不改。新事实必须
与同一完整当前DOM读绑定，并经新GET读回；完整表格等值检查同时拒绝错行/保护值变化。
保留原观察、图片、候选、权限、未知效果/用量和清理边界。旧工件和历史结论不追改。

TDD记录含首个接口缺失、合并/隐藏表头、重复/忙碌/透明/嵌套，以及可编辑表单保护
的失败后通过。最终定向24项通过，310项未选；原版产品保存正常时三次文字SDK和
三次派发完成，其他五种场景不完成。生产源码仅DOM通道变化；Controller、GoalContract
及策略不改。后端ruff与两改动Python的pyright通过。

## 验证记录

- 完整后端6793通过、1跳过、21 warnings，2041.57秒；启用既有Chromium和两产品
  环境，实际使用uv run --no-sync pytest -q -x，无真实模型调用。
- E2E全部24场景/95步骤通过，本地Sherpa/回环模型/隔离DB，finally恢复原后端。
  新通用用例进入现有场景，保持零跳过与子进程成功要求，不再硬编码pytest通过数量。
  前后端最后50行reload检查均无错误，未因空重复检查。
- web lint、tsc -b --noEmit、后端/CLI ruff、两改动Python的pyright通过；文档与
  完整diff检查通过。协议及生成物未改，protocol-sync不适用。
- 默认config及原76工件SHA不变；不修改旧诊断、原始实测或追认历史成绩。
  功能b578afc6、E2E e2734499签名提交。六任务真实模型验收仍未启动，未宣称模型质量。
- 独立review-and-refactor待完成。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest（启用Chromium及既有两产品资格环境）。
5. cd backend && uv run pyright <全部改动Python>，不加type-ignore。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出通过，不因空重复检查。
8. cd test && pnpm test；本地Sherpa/回环模型/隔离DB，finally恢复原服务。
9. python3 scripts/check_docs.py、git diff --check；旧工件/默认配置SHA、真实产品
   资格、审查及签名记录核对。浏览器重型批处理与E2E按后端要求串行运行。
10. python3 scripts/check_protocol_sync.py；协议及生成物未改则不适用。
