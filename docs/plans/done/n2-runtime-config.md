> 状态：配置与回归检查已完成（2026-09-17）；完整运行日志检查仍有错误

# 补齐 N2 主配置

用户已配置 `.env`，本次只补齐 `backend/core/config.yaml` 的 N2 运行配置。

1. 在现有 `llm` 下加入 `n2`，引用 `${YUTORI_API_KEY}`，使用模型 `n2`
   和 `https://api.yutori.com/v1`。
2. 增加顶层 `agent_engines`，将 `agent-n2:agent` 绑定到 `n2` profile，采用
   插件示例中的 tool_set、reasoning_effort 和 max_steps。
3. 解析实际配置并验证插件构造，执行完整检查后提交；不调用 API 或桌面操作。

## Tests

- 变更前确认实际主配置缺少 N2 profile 与引擎映射。
- 加载已有环境与实际主配置，验证 profile 绑定、模型、地址与参数，使用
  mock DesktopExecutor 构造 N2 插件。此配置变更不增加单元测试。
- 运行现有后端与 E2E 测试；无 Python 源码改动，pyright 不适用。

## 验证结果

- 已确认环境中存在 YUTORI_API_KEY；实际 AppConfig 加载与 N2 插件构造通过，
  profile=n2、model=n2、max_steps=100；未输出密钥或调用真实 API/桌面。
- 后端：4265 passed、2 skipped、16 warnings（164.83 秒）。测试退出仍有
  async-generator 清理的 pending-task 错误，不能称为零错误日志。
- E2E：10 scenarios、39 steps 全部通过。
- Web lint、TypeScript、后端/CLI lint、文档一致性与协议同步通过。
- 后端自动重载成功，`/api/health` 正常，E2E 后后端 pane 最后 50 行无错误。
  默认选中的 Vite pane 仍有客户端断开导致的代理 socket 错误，完整运行日志
  检查未通过。既有日志限制见 [N2 修复记录](n2-macos-config-and-reasoning.md)。
- 配置提交：`f43cdb0`。

## Verification Checklist（最后一步）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --package tank-backend ruff check core/src/ core/tests/ contracts/ plugins/`
4. `cd backend && uv run --package tank-backend pytest`
5. `cd backend && uv run --package tank-backend pyright <修改的 Python 文件>`（无修改则不适用）
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`
