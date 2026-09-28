> 状态：进行中（2026-09-28）。评审 S0 通用任务契约，最多三轮评审—重构—验证。

# S0 通用任务契约评审与重构

范围：`cb841910` 的通用任务输入/结果及相关调用链；`031c9ce5` 为设计说明。
不推进尚未实现的 Computer Use 插件或宿主循环。

## 评审方法

使用项目子 Agent `task-contract-reviewer` 独立评审，主 Agent 核实、复现并修改。
先检查重复代码/结构、散落的状态与不变量、基本类型滥用、可变状态共享、长方法与
参数列、过度耦合、无意义转发、不必要抽象和实现耦合测试；再以实际证据评价
SOLID、Design by Contract、德米特法则、DRY、KISS、YAGNI。

1. 第一轮：列出有证据的问题和最小重构方案；行为缺陷先补失败测试再修复。
2. 第二轮：复核修复及其调用链；发现问题则重构并验证。
3. 第三轮（若需要）：最终复审；最多三轮，明确记录残余问题。
4. 汇总每轮问题、处置及验证，完成后关档并更新索引。

## 问题与处置

第一轮确认四项：

- R1（P1）：Adapter 清理期间取消/超时会中断 aclose，丢弃已收到的 TaskResult 并释放
  未确认清理的桌面。将清理放入有界独立 task，shield 后持续 join；保留取消/超时
  的现有生命周期语义以及已收到的结果；清理失败优先返回 unknown 并隔离。
- R2（P2）：run 抛出的 SubAgentCleanupError 携带结果，aclose 再失败时结果被覆盖。
  保留原结果，将清理降级规则集中到结果/异常契约，避免 Adapter/Supervisor 同步维护。
- R3（P2）：旧 runner 入口收到空摘要的不完整结果，message 仍回退为 completed。
  使用实际终态生成缺省文案，覆盖五种状态。
- R4（设计）：REST 与 worker tools 的公开序列化字段和 include_output 分支完全重复。
  用一个小型共享函数替换两份实现，以现有两端行为测试验证一致性。

不扩大重构：多个公开入口的输入校验保留；不合并已应用的数据库迁移；未证实浅冻结
导致正常调用链跨边界别名问题，也未找到需单独修复的 SOLID/德米特法则违反。

第一轮实施：R1–R4 已修改，聚焦 `test_subagent.py` 的 84 项通过。
R1 新增 timeout / stop / repeat_stop × 成功 / 失败 / 主动取消清理的九个用例；
R2 覆盖 completed/partial 原结果与第二次清理失败；R3 覆盖五种状态与空/非空摘要；
R4 在重构前后运行相同的 API/工具测试，并将原测试对私有序列化函数的依赖改为
调用公开 API handler。清理失败不变量由 TaskResult.with_cleanup 与
SubAgentCleanupError 统一处理，REST/工具共同使用 WorkerRun 公开视图函数。
第一轮完整回归：后端 5212 passed / 1 skipped；E2E 18 场景 / 71 步全过。
web lint/typecheck、backend/CLI ruff、改动文件 pyright、reload 日志、docs check
及 diff 检查均通过。进入第二轮独立复审。

## Tests

- 逻辑缺陷以公开入口的失败用例复现；保留旧插件、内建 agent 和审批契约。
- 重构验证覆盖 SubAgent、Supervisor、WorkerStore、状态查询、通知与清理。
- 各轮运行全量后端测试；修改了相关行为时运行既有 Cucumber 场景。
- 最后一次修改后执行下面全部适用检查，不能用 mock 通过宣称实机能力通过。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/`
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <所有改动的 Python 文件>`，不新增类型错误抑制。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`；空输出即通过。
8. `cd test && pnpm test`；backend/frontend 必须运行。
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`；协议或生成产物变更时执行。
