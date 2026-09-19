> 状态：已完成，2026-09-19；真实 calc-open 三轮严格评分 2/3，失败原样保留

# GPT-5.5 computer use 闭环验收

1. 将 macOS 坐标链、pytest、真实校准、模型/协议消融及 DeepSeek 预算复测
   汇总到 `docs/design/computer-use.md`，从 benchmark 和架构文档链接。
2. 使用独立配置、现有 computer_use agent / AgentRunner / 工具 / validator，
   仅替换 OpenRouter 的 GPT-5.5 profile；不改变生产默认配置。
3. 本地检查权限与配置，以合成图预检真实 LLM 请求路径。此前仅合成图可外发，
   真实闭环需要明确允许本次清理后桌面截图发给 OpenRouter → OpenAI。
   用户已于本轮明确授权；截图仅保存在本机，不提交仓库。
4. 获准后先执行 macOS calc-open 三个 trial：重置、模型自行操作、截图反馈、
   AX 独立验证 7×8=56；保留实际模型/provider、请求图像 hash、动作与结果。
   区分键盘完成与鼠标定位证据；必要时追加明确鼠标路径的诊断。
5. 更新结果与限制，不把单任务闭环当全套跨应用/长历史验收，按逻辑子任务提交。

## 结果

- [统一文档](../../design/computer-use.md) 汇总此前全部验证及本轮新发现；
  benchmark 与架构入口已链接。
- 生产 temperature 强制发送造成 GPT-5.5 参数路由 404；配对合成请求确认
  后按 TDD 修复显式 null 省略。原默认值与数字覆盖保持，生产默认模型未改。
- 真实三轮 2/3 严格通过：两段四次鼠标点击成功，第三轮包含失败输入后的
  截图反馈与改用鼠标恢复。第二轮粘贴显示 56 但缺少表达式，严格评分拒绝。
- 本地输入隔离复现粘贴表达式语义差异；实际 HTTP 还确认 base 提示要求
  桌面子代理委托自己，工具面无 agent。评分策略与提示修复移交
  [backlog](../../backlog.md)，其因果影响未测。
- [证据](../../../backend/benchmarks/computer_use/reports/20260919-gpt55-loop/README.md)
  验证 13 个模型/provider 响应、7 张截图的实际发送与反馈。原图/完整 trace
  留本机，仓库仅存脱敏结果；遮挡窗口撤除并恢复隐藏应用。
- profile 测试 30 passed；backend 4484 passed/1 skipped；E2E 14/55；
  完整 Verification Checklist 全部通过。未执行全 14 任务或长历史测试。

## Tests

- 复用现有实际 SDK 图片/SSE/坐标链和 benchmark runner/validator 回归。
- 如预检或真实任务暴露代码问题，先用 pytest 复现再修复。
- 预检已确认生产默认携带 temperature 导致 GPT-5.5 路由 404；同请求仅省略
  该参数即成功。新增 profile 显式 null 到 SDK HTTP 的流式/非流式回归，
  保留原默认数值及 0.0 调用覆盖。
- 真实付费测试不进入单元测试；仅看模型声称成功不得通过。
- 验证每轮输入绑定、有效调用上限、终止原因、validator 与截图反馈证据。

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
