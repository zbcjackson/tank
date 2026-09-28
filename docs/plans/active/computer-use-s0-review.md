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

第一轮评审进行中。

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
