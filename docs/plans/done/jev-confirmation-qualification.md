> 状态：已完成（2026-10-22：资格调查第1轮独立审查无可操作或遗留问题；原生96/96通过，模拟第2项停批/190未运行，Controller资格未通过；一次假凭据认证失败外发及未知用量保留；观察一致性修复交回主计划，正式N仍未准入）。

# V/JT新任务库与执行器资格

## 目标和边界

承接[主计划](../active/computer-use-jev-vision.md)与[离线设计](../../research/jev-confirmation-design.md)，
基线5b5dc713。验证已冻结新库能否用于原版应用和现有Controller/SDK，不将无模型
资格计入校准或正式确认，不依据资格结果调整提示/路由或挑换任务。无真实模型调用。
本任务只新增研究脚本/工件和文档；若发现运行时代码缺陷，保留证据后另立修复范围。
原保留库、旧freeze/归档和两个应用源码均不覆盖；正式N保持null。

## 步骤和验收

1. 校验设计归档、库及36运行源，逐份解析24576目标。按既定前缀规则固定40正例
   +8负例seed（每正例层rank0–3、每负例层rank0–1），冷/预热共96份目标；原先
   预定arm顺序不变，fake矩阵192次。全部身份在运行前冻结，失败保留，不替换。
2. 原版sqlite-web0.8.1/linkding1.47.0及隔离合成DB/Chromium：96份目标验证真实
   列表→编辑→保存→返回、完整记录及单业务POST、GET故障/Retry、缺目标、撤权
   守卫、候选与原始PNG、清理。冷/预热定义与旧校准一致；脚本成功不称模型成功。
3. 真实Controller和官方SDK，仅模型外部HTTP模拟，顺序执行192次；假答案仅由
   公开goal/候选决定，私有oracle不进入HTTP。保留每行、SDK调用/图片、业务DB/
   HTTP、撤权与清理；未知用量/非法选择/异常停止另作有限回归。执行入口只提供
   fake模式，不配置真实凭据，不生成正式或补充校准执行许可。
4. 独立脚本核物理前后DB、HTTP、PNG、候选、身份/顺序和全部分母；形成报告、
   面板、逐成员归档及凭据扫描，旧档hash不变。全库静态验证和96目标原生资格
   分开报告，不把有限前缀推广为全库24576目标的原生通过。
5. 完成适用验证后按[code-reviewer](../../../agents/code-reviewer.md)做本任务第1轮
   review-and-refactor（最多三轮，无遗留即停）。后续统计评分器接线及补充校准
   预注册仍由主计划承接；可选760+152信息目标继续在backlog，不自动执行。

## Tests

- 按TDD逐项验证：固定平衡前缀及arm顺序；库/源/任务篡改拒绝；非fake入口拒绝。
- fake答案能适用于hold-v2身份，不依赖旧cal-前缀或私有oracle；非法选项不执行。
- 全96原生目标与192 fake任务，含两产品/冷暖/目标1和4/全部正负场景。
- 未知用量、非法选择、早停保留未运行分母；业务成功与缺目标/撤权退出分列。
- 独立物理/PNG/HTTP核验；归档成员/实际凭据值扫描、旧档hash、面板tsc。

## 当前结果及范围处置

全库24576目标结构、96原生业务/清理及416张PNG通过；不推广为全库原生通过。
最终显式MockTransport批次192行保留，V首项成功，JT第二项Retry后无动作退出，
190未运行。两次固定跟踪一次成功、一次复现旧Retry节点/新URL与编辑器投影
混合；诊断不计入主矩阵，不重试补过门。因此本轮未达Controller资格，剩余
执行暂停，确定性TDD修复及新冻结完整资格交回主计划，不在本研究切片改运行时。

原零外部请求目标有一项偏离：早期fake驱动遗漏pytest autouse的SDK客户端
接线，产生1次假凭据Jev调用认证拒绝，未收到真实模型输出。原unknown_usage
及错误计数单独勘误保留。显式MockTransport、独立进程SDK及外联拒绝回归已补；
8项研究测试、原生独立物理审计、最终两行/190未运行审计、面板tsc通过。
原生前后驱动及输入哈希相同，显式fake接线改动后复用原生证据，不重新选样。

[完整结果](../../research/jev-confirmation-qualification.md)及归档2759成员、16940164
字节，SHA256 `8007375903989adbba9ab39b3dcfbb1c0a9c7b09de549afeb1e5012d7655559c`。
71份逐trial应用源核hash后去重，21实际凭据值零命中，旧44工件保持。正式N
及真实模型执行仍未准入。

第1轮独立review-and-refactor核验完整任务diff、2759归档成员、44旧文件及基线
Git blob、5个freeze、36源、24576目标、416PNG完整解码及71应用源去重哈希；
8项研究测试重跑通过，原生/fake物理审计逐字段重放一致，面板数据和tsc通过。
未发现可操作或遗留问题，按规则停止，不修运行时、不追加资格批次。观察一致性
TDD修复、新冻结完整资格及统计后续保留在主计划；可选信息目标已在backlog。
本次结案状态与链接收尾由评审者自检，未另作独立验收，不改变资格未通过结论。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`（不改web，不适用）。
2. `cd web && npx tsc -b --noEmit`（不改web，不适用；研究面板另作tsc）。
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`（无产品源码修改，不适用）。
4. `cd backend && uv run pytest`（研究工件/docs-only，不重跑未变全套；运行本轮研究测试及原生/fake资格）。
5. `cd backend && uv run pyright <改动Python>`（无产品Python修改，不适用）。
6. `cd cli && uv run ruff check src/ tests/`（不改CLI，不适用）。
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`（无热重载变更，不适用）。
8. `cd test && pnpm test`（docs-only例外，不适用）。
9. `python3 scripts/check_docs.py`（必须通过）；另跑研究测试/独立核验/面板tsc与`git diff --check`。
10. `python3 scripts/check_protocol_sync.py`（协议无变更，不适用）。
