> 状态：已完成（2026-10-19：机制与修复验证、完整回归、归档及第1轮独立审查通过；旧V/JT保持）。

# DOM视觉新鲜度与输入光标

## 目标与范围

用户要求开始下一步，优先无付费复现并修复路由pilot中的视觉执行拒绝。旧五个
正确Save work后拒绝只支持光标假设；本轮保存实际is_current检查图片和首拒绝
阶段，确认机制后再修复。使用旧配方的手写实验网页、隔离Chromium，不调用模型
或使用用户浏览器，不重判旧结果，不放宽DOM身份/导航/权限/真实像素变化检查。

## Tests

1. TDD在现有test_dom.py覆盖新鲜度首拒绝阶段、图片hash关联及观察者失败不改变
   拒绝；事件仅含关联元数据，不含图片或正文。无客户端/模型的独立诊断配方保存
   每次capture/is_current即时PNG，对照caret initial/hide与自然等待，DOMView需
   不变。保存所有轮次，不挑成功图；记录browser版本、源码、用时及清理。
2. 确认后统一截图政策隐藏原生输入光标；保持逐字节图片检查，回归真实颜色变化、
   输入值变化、同外观节点替换、导航/引用、撤权与派发前复查。有限改动既有通道，
   不引入图片容差或任意忽略区域。复用原V/JT fake HTTP流程核对正负路径。
3. 完整适用回归、独立review-and-refactor、独立重算归档/研究报告/主计划与面板。
   本轮以无付费诊断和修复验收；修复后真实路由比较及弃权后接管另按主计划冻结，
   不将无模型结果冒称真实模型质量或新V/JT成绩。

## 当前结果

真实Chromium145.0.7632.6，修复前通道16检查中6次frame_scene拒绝；修复后
16/16通过，DOMView相等。每次真正参与检查的PNG已保留，拒绝图差均为1×23
竖条、23像素；旧保留光标对照修复后仍7/16拒绝，隐藏对照前后均16/16通过。
96检查、108PNG、12上下文清理、模型调用/任务输入均0；旧五例不追认或重判。
统一constructable stylesheet隐藏光标，避免Playwright caret=hide临时改style触发
修订检查；严格PNG、值、节点、导航、引用、权限和输入门保持。

21专项通过（含12新回归与9旧路由矩阵），ruff/pyright/web类型和lint/CLI lint通过，
dev日志为空。完整回归前两次分别有3和2个页面加载/观察阶段失败，未改超时或
断言；逐项复跑及146次导航诊断均通过，保留全部日志，原因未唯一确定。
当前源码固定，最终完整回归6380通过/1跳过（517.40秒）；原日志保留。签名恢复，
计划54ddfb47、修复c70bc305已提交。串行E2E21场景/83步骤通过（150.021秒）。
146成员/108PNG归档、独立图差/hash/阶段重算及凭据扫描通过，旧9归档不变。
详见[研究记录](../../research/dom-visual-freshness.md)，面板类型及docs/diff通过。
首次加载若再出现超时的调查触发项交接backlog；新真实模型比较由主计划推进。
第1轮独立review-and-refactor覆盖3ee33eb4起完整源码、测试、文档、归档和面板，
无确认缺陷或遗留问题，未改源码。独立逐成员核验146文件/108PNG、96检查、
19个首拒绝事件、12清理、两版freeze源码、旧9归档及面板数据一致；12项新增
Chromium回归通过（24.86秒）。复用未变化源码的完整回归，不作重复审查。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`，另查诊断benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部修改Python文件>`，不以type-ignore绕过。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与完整后端串行，复用既有managed Chromium场景。
9. `python3 scripts/check_docs.py`和`git diff --check`，核验全部归档与旧9份证据。
10. 仅协议/生成物变更时`python3 scripts/check_protocol_sync.py`；本片无协议变更。
