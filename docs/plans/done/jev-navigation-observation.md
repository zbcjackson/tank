> 状态：已完成（2026-10-22：两层TDD修复及96原生/192模拟通过，第1轮独立审查无可操作或遗留问题；后端6537和本地ASR配置E2E21/83通过。原ElevenLabs复测限制已移交backlog）。

# Retry导航后的观察一致性

## 目标和范围

承接[主计划](../active/computer-use-jev-vision.md)及[资格失败证据](../../research/jev-confirmation-qualification.md)。
修复新URL/编辑器事实与旧Retry节点混合，确保DOM、URL、投影、候选和图片绑定
同一就绪文档。仅最小修改DOM通道和必要产品投影；不改模型、提示、阈值或原版
应用。旧证据、认证失败unknown_usage及外发记录保持。真实模型调用不在本轮范围。

## 步骤与验收

1. 在现有test_dom.py用受控真实导航/响应写确定性红测试：新文档就绪前不能发布
   可用旧节点；覆盖Retry恢复及同URL重载。确定实际失效边界后最小修复。
2. 验证观察、投影、capture及dispatch在导航/撤权/取消下拒绝旧文档；正常同文档
   动作、导航和两产品恢复通过。SDK测试使用显式MockTransport，先独立探针后
   执行资格，保留所有失败/未运行分母，不重试到通过。
3. 在新目录冻结新执行源、原48组seed/96目标和192行顺序，重跑96原生及192
   fake资格并独立核物理DB/HTTP/PNG、清理和用量。原保留库及旧freeze不覆盖。
   这些仍是执行资格，不计模型表现或确认样本量。
4. 更新设计/测试说明、结果证据、索引及主计划，适用验证全部通过后委托
   code-reviewer做本任务第1轮review-and-refactor，最多三轮，无遗留即停。

## Tests

- 真实Chromium的受控响应/导航，确定性复现旧Retry混合；新文档Title候选/URL
  与就绪状态一致，旧绑定不可capture/dispatch。同URL重载不复用旧节点。
- 导航等待期间撤权/取消及超时均受原任务约束，清理确认；不引入固定sleep、
  页面特判、放宽freshness或重新发送业务POST。
- 原DOM/产品/SDK回归、完整96原生/192 fake矩阵，真实SDK但无外部模型HTTP。
- 现有chat.feature的managed Chromium合同包含新增泛化回归，不新建feature文件。

## 当前结果

就绪等待的首片8fc7305a通过受控导航回归，但首次资格仍首项失败（191未运行）；
随后三条业务投影的同代次DOM变化红测试全部复现。816d9865以统一DOM重读校验
修复，六组合通过。最终同一48簇/96目标/192顺序在新freeze下96原生、160正例/
32负例模拟全通过。源中仅DOM和三份产品投影改动，旧失败、源及46旧工件保留。

完整后端6537/1skip/21warnings、static检查及本地ASR配置E2E21场景83步通过。
E2E计数82→88修复已提交；原配置ElevenLabs语音commit超时保留，其外部单独
复测被自动审批拒绝（外发WAV/认证信息）；未绕过拒绝。用真实本地Sherpa及回环
LLM fixture、隔离DB完成同套E2E，实际配置断言/外联审计保留，原服务已恢复。
本地通过不证明远端链路健康；这一限制须在最终交接及后续登记明确。
第1轮独立review-and-refactor已完成，无可操作或遗留问题，按规则停止；未改运行源/测试。
审查员独立重跑28项导航/投影/多布局及8项研究/SDK测试，准确范围ruff和五文件
pyright通过；物理审计与原96/192结果一致，归档6836成员/1601 PNG、21凭据
零命中、46旧文件与基线Git blob及36源逐项核对通过。结案文案为审查员自检。
统计评分器及补充校准准备留在主计划；原ElevenLabs链路复测须明确授权外发测试
WAV和认证信息，已移交[backlog](../../backlog.md)，不是本次离线修复的通过声明。
归档6836成员、52694856字节，SHA256
`47cb50e9ae696951d1832bb44f5dc012df32ad7fc36cf67daa897165e0aa84cb`；
21实际凭据零命中、旧46工件不变，193份应用源去重。独立审查补充证据见[报告](../../research/jev-navigation-observation.md)。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`。
2. `cd web && npx tsc -b --noEmit`。
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`。
4. `cd backend && uv run pytest`；设TANK_REQUIRE_CHROMIUM=1、TANK_REAL_PRODUCT_PYTHON及TANK_LINKDING_ROOT要求原版应用测试。
5. `cd backend && uv run pyright <改动Python>`，禁止type-ignore掩盖。
6. `cd cli && uv run ruff check src/ tests/`。
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`，并检查实际backend/web pane。
8. `cd test && pnpm test`，服务必须运行。
9. `python3 scripts/check_docs.py`；另核研究工件/旧档hash/凭据、面板如有改动则tsc、`git diff --check`。
10. `python3 scripts/check_protocol_sync.py`（无协议变更则不适用）。
