> 状态：实施中，2026-09-18

# Computer-use benchmark 修复

依据桌面的 Part A、N2 engine、N2 SDK 三组报告修复已确认的问题。
旧评分不覆盖，真实 macOS benchmark 另行复测；本机为 Linux。

## 实施

1. 保留 SDK GuardedComputer 方法签名；用真实 SDK 和严格签名的
   computer/假 transport 验证 GUI 调用及授权、取消检查。
2. 修复共用 Quartz 鼠标位置 API、点击 schema/bbox 与 esc 别名；
   保留 Part A batch 的截图图像，统一 batch 说明和 agent 操作流程。
3. 补 N2 engine 鼠标动作兼容和 shell 非 UTF-8 输出处理。
4. 保留已有 trial-token 隔离，完善非流式延迟、动作/轮次/有效上限
   报告；要求 GUI 的任务执行路径纳入评分，避免 shell/file 绕路得分。
5. 同步 benchmark 文档，记录验证结果和实机限制。

## Tests

- SDK 包装后签名与底层一致，真实 SDK 调用真实 MacOSComputer 配合假
  transport，不发生 model_action 参数错误，取消和授权检查仍生效。
- Quartz 按下/松开调用 CGEventGetLocation；两平台 bbox/schema、esc
  一致；batch 图像到达 LLM 内容并被 benchmark 归档。
- N2 鼠标动作别名、batch 失败成员与跳过成员；shell 非 UTF-8 输出。
- benchmark 非流式 TTFT 为 N/A；调用数、实际动作、轮次和限制可见；
  GUI 任务使用非 GUI 工具即使产物正确也不能通过。
- 已有 capture 隔离、过期请求、smoke 排除回归继续通过。

## 最终验证（完整 Verification Checklist）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check src/ tests/`（workspace 实际路径为
   `core/src/ core/tests/` 和改动的插件）
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <全部改动的 Python 文件>`；不新增
   `# type: ignore`。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
8. `cd test && pnpm test`（需要 backend/frontend）
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`

实机验收：macOS 先验证 GUI 基础动作，再同配置、同任务、同评分规则
运行三种实现。不得以 mock 测试或旧报告代替真实验收。
