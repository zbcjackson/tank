> 状态：已完成（2026-10-07）。单一目标契约、调用/测试/benchmark 迁移及评审验收完成。

# Computer Use 目标契约统一

基线 `7af2802f`。本决策取代策略阶梯计划中长期保留 v1 的要求；S4-AX 仍是后续原生
通道批次，本次先消除两版契约和两套执行路径。已归档报告不重写，可执行 benchmark
使用新输入 revision，不把迁移后的结果视为原 S3 实验复现。

1. 保留目标驱动字段与 `schema_version: 2`，类名统一为 `GoalContract`；删除旧
   Milestone、v1 解析、联合类型和两版分流，不保留别名或运行时转换兼容层。
2. 候选构造与宿主循环统一；迁移现有调用、fixture、SDK 请求上下文与 benchmark。
   保持原授权/累计用量、过期引用拒绝、局部与最终核验、未知效果零重放。已有
   Advisor 注入接口迁移为补充已声明的缺失输入，不趁迁移扩展完整生产 Advisor。
3. 更新当前设计、使用说明、策略阶梯计划和索引；历史结果保持原样并说明新旧
   benchmark revision 的语义边界。

## Tests

先写单一契约接受目标输入、拒绝旧脚本输入的回归，再逐项迁移使用方。保留并验证
混合动作、独立完成条件、输入不可覆盖、共享模型用量、取消/撤权、旧回复零派发、
重复状态停止、unknown 有界只读协调和真实 Runner/SDK/Chromium 流程。历史仅针对
里程碑排序/精确标签规则的断言改为当前目标语义的行为测试，不删除仍适用的安全验证。
benchmark 的确定性、评分真值隔离、冻结哈希、停批和完整分母仍须通过。无实机桌面
操作或付费模型请求。

## 实施与验收记录（2026-10-07）

- 实现提交 `86f6abde`：唯一 `GoalContract` 使用 schema_version=2；删除 Milestone、
  v1 解析和执行分流、重复候选构造及联合类型。所有源码调用、测试与当前 benchmark
  fixture 迁移；旧版本输入明确拒绝，不保留运行时兼容层或旧类名别名。
- 新 benchmark revision 与归档报告分离。DOM harness 改读当前 `fixtures/s3-dom`
  数据；公共效果模板不从评分标签生成。当前重放最多 72 次模型请求，策略批次上限
  81 次、按任务冻结选择次数。fake HTTP 验证正常/强制回退为 60/81 次；不沿用旧
  S3 调用数或收益结论。`reports/` 目录无改动，无新付费模型批次。
- 迁移保留已声明缺失输入的 Advisor 注入补充，校验固定输入和完成条件不可覆盖；
  保留版本、累计用量、授权和原生引用。未扩展完整生产 Advisor、同进程恢复或 AX 实机。
- 独立 code-reviewer 第 1 轮确认 R1：唯一 submit 且输入满足不足以证明意图，回归
  复现自动点击其他表单 Subscribe / 同表单 Delete profile。删除自动 submit 规则，
  只保留显式绑定字段的 fill 快捷路径；提交必须经配置的选择器，测试和预算同步迁移。
- 同轮 R2：Advisor 重新观察后 ready/complete 恢复被误判为重复状态。两个回归先红
  后绿，状态比较加入这两个标志；真正重复观察仍有界停止。修复提交 `9c203f39`。
  第 2 轮复核无新增或遗留可操作问题并立即结束，这是评审者对自己修复的自检。
- 最终冻结后端 **5608 passed / 1 skipped / 21 warnings**（`/tmp/tank-review-full.log`），
  强制启用 Chromium；E2E **17 场景 / 67 步**（`/tmp/tank-review-e2e.log`）。后端/CLI
  ruff、全任务 diff Python pyright、web lint/`tsc -b --noEmit`、test TypeScript、
  开发服务日志、docs/diff check 均通过。协议未改，第 10 项不适用。
- 中间一轮发现 unknown fixture 仍显示已成功填入的值，已修正为真正的未决效果场景；
  评审首次全量因追加 R2 回归主动中止，随后冻结完整重跑。未把失败或中止当作通过。
  协调者已核对最终 diff、测试日志及评审结论。

本次迁移范围全部完成，无新增延期项。S4-AX、完整恢复和生产 Advisor 继续由原
[策略阶梯计划](../active/computer-use-strategy-ladder.md) 跟踪，不因本次关档宣告完成。

## 最终步骤：Verification Checklist 与评审

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/agent-computer-use/src/ plugins/agent-computer-use/tests/ benchmarks/computer_use/`
4. `cd backend && uv run pytest`，启用实际 Chromium 验收；全量期间冻结源码。
5. `cd backend && uv run pyright <全部改动的 Python 文件>`
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`（开发服务运行），以及改动 E2E 时的 TypeScript 检查。
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`（仅改客户端协议或生成物时适用）。

上述全部适用检查与两轮有界 review-and-refactor 已完成，验收证据见上节；关档并同步索引。
