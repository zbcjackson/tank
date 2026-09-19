> 状态：已完成，2026-09-19；公开实现调研与方案归档，未实施候选运行时改动

# Computer use 实现对照调研

1. 对照现有坐标、模型隔离与 GPT-5.5 闭环证据，重新判断模型和宿主责任边界。
2. 阅读 macOS 相关实现及官方 computer-use 示例，记录坐标契约、语义定位、
   输入语义与反馈机制；仅将源码/文档作为实现证据，不宣称已在本机验证。
3. 将结论写入 research，更新 computer-use 设计文档入口；给出优先级、
   单因素实验及验收条件。候选实现转入 backlog，本轮不修改运行时或默认模型。

## Tests

- 核对已有报告中的样本数量、评分定义、鼠标与键盘路径；不重跑付费模型实验。
- 核对每项外部实现结论的官方源码/文档和适用平台；不借用外部排行榜作为本机结果。
- 本轮仅文档变更，不新增镜像实现的单测；列出未来行为变更所需的回归与真实验收。
- 检查内部文档链接及索引，执行仓库要求的全套检查并记录结果。

## 结果

- [调研记录](../../research/computer-use-implementation-comparison.md) 对照七个
  官方项目/接口，明确模型 × 协议成绩不代表模型最佳适配能力。
- [现行文档](../../design/computer-use.md) 已补责任边界及入口；提示冲突、输入
  语义、截图引用、AX/定位器和效果检查候选登记到 [backlog](../../backlog.md)。
- 本轮只变更文档，没有新增模型调用、桌面操作、运行时逻辑或模型配置。
- web lint/类型检查、backend/cli lint、协议检查通过；backend
  4484 passed / 1 skipped，E2E 14 场景 / 55 步通过；实际后端面板无匹配错误。
  未改 Python，定向 pyright 不适用。归档后文档一致性检查通过（36 个文档）。

## 最终 Verification Checklist

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/`
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright` 加本轮修改的 Python 文件（无则不适用）
6. `cd cli && uv run ruff check src/ tests/`
7. 检查 tmux tank 实际后端面板的 reload 错误
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`
