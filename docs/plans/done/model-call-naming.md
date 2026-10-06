> 状态：已完成（2026-10-06，代码与回归、独立评审均完成；不涉及 S4）。

# 模型调用命名与客户端所有权收敛

## 范围

- 通用类型 `SDKStream` → `ModelResponseStream`，`TaskModelCalls` → `TaskModelCallRunner`。
- 当前实验事件 `sdk_request/sdk_response` → `model_request/model_response`，
  捕获层级 `sdk_call` → `model_call`，结果状态 `sdk_returned` → `returned`。
  仍是调用级参数/结果，不是原始 HTTP。旧 reports、历史计划及冻结产物不改。
- DecisionModel 不再创建或注入 http_client/transport；官方 AsyncTypeSafeClient 自行
  创建及关闭客户端。保持固定 profile、30 秒超时、零 SDK 重试和原 choose 接口。
- 删除 trust_env=False 覆盖，采用 SDK/HTTP 库默认的环境代理与证书行为。当前库默认
  不跟随重定向；不再由 Tank 强制该默认值。其它文本/原始回放客户端不在本次改动范围。
- 不新增兼容别名或双事件输出；内部类型/实验日志同步迁移，运行时公开方法保持不变。

## Tests

先红后绿验证 SDK 构造无 http_client/transport 注入、SDK 默认客户端的创建/关闭、
超时与重试设置；无效凭据在创建 HTTP 客户端前拒绝。测试夹具仅替换外部网络，
不把测试用 fake transport 带入生产。复用请求记录、Jev、Runner/Chromium 和流式回归，
确认新事件名、调用关联、用量、停止和清理不退化；无付费模型调用。

## 完成记录

- 实现提交：`f69f5860`。通用类型与实验事件完成迁移，Jev 使用官方 SDK 默认客户端。
- 定向测试 71 项通过；完整后端 5580 passed、1 skipped；E2E 17 场景、67 步通过。
- Web lint/类型检查、Backend lint/改动文件类型检查、CLI lint、开发日志、文档与 diff 检查均通过。
  未改协议或生成物，协议同步检查不适用。
- 独立 review-and-refactor 第 1 轮通过，无需修复、无遗留问题。未调用付费模型，未开始 S4。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查改动 benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run pytest`，本机使用所需 opus 库路径。
5. `cd backend && uv run pyright <改动的 Python 文件>`。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，在后端全量之后顺序运行，避免浏览器争用。
9. `python3 scripts/check_docs.py` 和 `git diff --check`。
10. `python3 scripts/check_protocol_sync.py`，仅协议/生成物变动时适用。

随后执行仓库要求的独立 review-and-refactor，最多三轮；通过后提交并关档。
