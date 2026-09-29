> 状态：实现与验证通过，待独立代码评审（2026-09-29）。

# Token 用量记录与实验策略边界清理

用户要求 core 只记录 token 消耗，避免 benchmark 的 trial、batch、价格、journal
和累计额度侵入生产。上次 S0 第三批整份下沉 SpendLedger 的边界不成立，本计划纠正。

## 发现与范围

- SubAgentBudget 已有任务用量记录；Runner 在无 context 时另行累加并判断上限。
- TokenUsageObserver 是独立会话聚合器，目前未发现生产实例化；只有告警，不负责停机。
- Graph 原先把流式文本片段数记成 token；改为同一用量记录的日志投影。
- TaskModelTransport 又创建了 SpendLedger，并把 task_id 当作 trial；它尚未接入生产。
- benchmark 的 SpendLedger、RequestBudget、HoldoutBudget 管理实验预留、调用次数及
  回放停止条件；这些策略保留在 benchmarks。
- ContextBudget 与单次 max_tokens 管理上下文容量/输出长度，不能当作累计消耗合并。

## 实施步骤

1. 引入无策略 TokenUsageLedger，统一按调用 ID 去重、已知/估算/未知用量的累加；
   SubAgentBudget 仅保留显式旧限额的兼容包装，Runner/Observer 复用同一统计实现。
2. 将 SpendLedger 完整移回 benchmarks；生产 HTTP 入口直接记录 context 中的用量，
   不创建第二份账本，不要求价格/累计限额/trial。实验准入通过小型可选策略接口注入，
   benchmark 适配器持有实验额度和生命周期，核心不反向导入 benchmarks。
3. 生产默认纯统计：移除内置 Agent 默认 token-budget，保留显式配置兼容；修正 0
   override 被 `or` 覆盖的问题。用户已确认保留显式配置兼容并移除内置默认上限。
4. 更新当前设计、S0 计划和索引，记录边界及验收。完成后移动此计划至 done。

## Tests

按 TDD 增量覆盖：默认大量累计消耗不停止；重复调用只计一次；估算/未知不伪装已知；
多个模型客户端共享同一任务计数；显式旧限额与 0 override；生产无 trial/batch/价格；
benchmark 注入零额度零发送、未知预留保留、并发守恒和既有 journal/SDK/取消回归。
复用既有测试文件与 chat.feature，不为相同领域新增 feature 文件。

## 实施与验证记录

- core 仅保留 TokenUsageLedger 的去重、已知/估算/未知计数；Runner、Graph、Observer、
  task context/HTTP transport 复用它，任务不再创建第二份实验账本。
- SubAgentBudget 仅保留显式限额兼容检查；7 个内置 Agent 移除 token-budget，0 override
  正确覆盖原配置。相同 call_id 不重复累加；无法提供 ID 的旧事件只按事件生成本地 ID。
- SpendLedger 的 trial/batch、费用、journal、预留均回到 benchmarks；BenchmarkModelPolicy
  通过核心小接口注入，实验生命周期不会被 transport.close 关闭。Core 不导入 benchmark。
- 旧实验导出器隐含继承生产 300000 默认值的问题通过全量回归暴露（50 项失败）；
  已让导出器显式冻结实验预算，相关 213 项回归通过，未降低原实验验收标准。
- 原始 Chat Completions usage 校验已复用，流式实验和非流式任务不再各写一份解析逻辑。
- 最终后端全量 5363 passed / 1 skipped（21 条既有警告），无未处理后台异常；
  E2E 20 场景 / 79 步通过；web lint/tsc、backend/CLI ruff、18 个改动 Python 文件
  pyright、开发服务 reload 日志、docs check、diff check 通过。协议未改。
- 新 HTTP transport 仍未接入生产 Runner/plugin 工厂；这次只清理统计/策略边界，
  不宣告 S0 G1/G2 完成，不扩展 GUI 通道或进行真实桌面实验。

## 验证清单（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/`，补涉及的插件路径。
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <全部改动 Python 文件>`，不新增 type ignore。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`，空输出通过。
8. `cd test && pnpm test`，backend/frontend 必须运行。
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`，仅协议或生成物变更时适用。

上述适用检查通过后，委派 code-reviewer 完成最多三轮 review-and-refactor；无问题即停止。
