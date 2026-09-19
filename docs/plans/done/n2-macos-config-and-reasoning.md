> 状态：代码与回归修复已完成（2026-09-17）；运行日志检查仍有限制，macOS 待实机复测

# N2 macOS 配置与通知修复

macOS 日志显示 `agent-n2` profile 不存在，Runner 回退到默认 DeepSeek。
N2 插件因此可能只返回文字，没有桌面操作。通知轮次另因未读取流中的
`reasoning_content`，无法回传思考字段，收到 DeepSeek 400。

## 实施

1. 引擎 profile 按名称精确查找；N2 缺少 profile 或模型不是 `n2` 时明确失败。
   构造失败不留下活跃 Agent；增加实际 profile/model 与动作名称日志。
2. 同时支持流中的 `reasoning_content` 和兼容字段 `reasoning`，将字段完整
   保留到助手历史，覆盖工具续请求和后续通知请求。
3. 补充 macOS 配置、重启、新会话与日志验证说明。保留 engine/executor。
4. 必需的开发服务检查复现客户端在初始化期间断开：发送 ready 时 uvloop
   抛出 closed transport RuntimeError。按正常断开处理，保留其它异常的错误日志。

## Tests

- 先复现真实 AppConfig 的默认模型回退、N2 模型误配与构造失败残留。
- 使用 OpenAI SDK 的真实 ChatCompletionChunk 测试思考字段分片、兼容字段、
  工具续请求与下一轮历史回传，避免 mock 掩盖字段名称错误。
- 验证 ready 发送时已关闭 transport 不记录错误、会话仍清理；其它 RuntimeError
  仍保留错误日志。
- 保留插件的审批、预算、动作与 benchmark 回归测试；不调用真实桌面或 API。

## 验证结果

- 配置、思考字段、插件与 hook 定向测试：72 passed；握手、认证、Opus 与
  会话配置回归：78 passed。
- 最终全量后端：4265 passed、2 skipped、16 warnings（165.71 秒）。
  退出时还输出一条 async-generator 清理的 pending-task 错误，不能称为零错误日志。
- Web lint、TypeScript、后端/CLI lint、9 个修改文件的 pyright、文档一致性与
  协议同步全部通过。E2E 复跑：10 scenarios、39 steps 全部通过。
- `/api/health` 正常；E2E 后后端 pane `tank:0.0` 最后 50 行无错误，原先
  ready 发送时的 closed transport traceback 未再出现。后续定时任务执行时
  再出现工具错误与 Langfuse 导出错误；默认选中的 Vite pane 也仍记录浏览器
  断开导致的代理 socket 错误，因此完整日志检查未通过。
- 未调用真实 N2 API，也未操作 macOS 桌面；用户须同步修复、合并配置后
  重启并在新会话中复测，见插件 README。localhost:3001 的 Langfuse 服务
  未启动时，仍会出现独立的遥测导出错误。
  实机验证现由 [SDK 插件实施计划](plugin-subagents-and-n2-sdk.md)
  的 T5 项追踪，不视为本次代码回归已证明桌面操作成功。
- DeepSeek 思考字段要求依据
  [官方 Thinking Mode 文档](https://api-docs.deepseek.com/guides/thinking_mode/)。

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
