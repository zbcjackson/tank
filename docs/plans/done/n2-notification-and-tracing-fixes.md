> 状态：代码与回归修复已完成（2026-09-17）；运行检查限制及 macOS 复测见结果

# N2 通知与追踪修复

用户确认 macOS 操作正常；本次日志显示 N2 使用正确 profile，9 轮结束，
随后主 Agent 的通知请求被 DeepSeek reasoning_content 校验拒绝。

## 实施

1. 检查已有历史与确认/通知轮次的思考字段完整性，补齐历史兼容与部分轮次
   的持久化路径。缺失的思考字段不能通过占位内容重建。
2. 修复 Langfuse SDK 导入时自动注册后又手动注册的重复包装，支持官方
   `LANGFUSE_TRACING_ENABLED=false` 开关，不修改用户 `.env`。
3. 将已有 ping/pong 的毫秒 timestamp 元数据登记到协议，消除误报。
4. 完成回归检查并提交；不调用真实 N2 API 或操作 macOS 桌面。

## Tests

- 使用真实 SDK chunk 验证通知历史回传和缺失字段兼容；保留正常完整历史
  的模型行为和用户配置，不修改持久历史内容。
- 验证 LLMAgent 在异常/关闭前暴露已完成的轮次消息，保留原始思考字段。
- 验证 Langfuse 只触发一次自动包装、显式禁用时不初始化追踪。
- 验证 ping/pong timestamp 原样保留且不触发协议警告；协议生成物仍同步。

## 结果与限制

- 用户确认此次复用了之前的 N2 会话，符合旧历史缺失思考字段的路径。
  未取得 macOS 的完整持久历史，不能断言其中具体哪条消息缺失字段；
  新日志会输出缺失字段的消息索引，不输出消息内容。
- 主 DeepSeek flash/pro 的带工具请求遇到缺失字段时，保留历史并改用该次
  请求的非思考模式；完整历史仍遵循 profile 配置。已完成消息在异常或
  提前关闭流时也可由 Brain 持久化，不伪造思考内容。
- 用实际 DeepSeek 服务验证一条旧 assistant 历史加后台完成通知的请求：
  服务接受兼容请求，profile 配置未改变。请求限制为 128 输出 token，
  未执行任何工具、调用 N2 API 或操作桌面。
- 修复 Langfuse SDK 的重复包装；没有修改用户 `.env`。连接拒绝仍需
  启动配置对应的 Langfuse 服务，或设置 `LANGFUSE_TRACING_ENABLED=false`
  后重启进程。日志中的独立 404 缺少请求地址，尚不能定位具体来源。
- 登记已有 ping/pong timestamp，重新生成协议 schema；web 类型和设备
  golden frames 内容未改变，协议同步检查通过。
- 针对性回归 98 项通过；后端全量 4276 项通过、2 项跳过、16 条 warning；
  E2E 10 个场景、39 个步骤通过。前端 lint/TypeScript、后端和 CLI ruff、
  修改的 8 个 Python 文件 pyright、文档与协议一致性检查均通过。
- 全量 pytest 退出码为 0，但退出时仍打印异步生成器任务未清理错误；
  开发服务的 Vite 日志仍有连接断开错误。后端最后 50 行没有错误，健康
  检查正常，不能据此宣称所有运行检查全绿。
- macOS 已确认 N2 桌面操作正常；同步这些提交并重启后，可继续在旧会话
  验证完成通知是否正常。实机验收继续由
  [插件子 Agent 计划](../active/plugin-subagents-and-n2-sdk.md)的测试项追踪，
  此次没有实施官方 SDK 迁移或 benchmark 改动。

## Verification Checklist（最后一步）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --package tank-backend ruff check core/src/ core/tests/ contracts/ plugins/`
4. `cd backend && uv run --package tank-backend pytest`
5. `cd backend && uv run --package tank-backend pyright <修改的 Python 文件>`
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`
