> 状态：进行中（2026-10-22：开始TDD修复Retry导航后的观察一致性，基线1ec85dae；仅离线模型资格）。

# Retry导航后的观察一致性

## 目标和范围

承接[主计划](computer-use-jev-vision.md)及[资格失败证据](../../research/jev-confirmation-qualification.md)。
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
