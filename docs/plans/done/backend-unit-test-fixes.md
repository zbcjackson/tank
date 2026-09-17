> **Status:** 已完成后端单元测试修复（2026-09-17）；开发服务日志验证仍有错误

# 后端单元测试修复

1. 复现 workspace 根目录测试收集错误与测试失败。
2. 最小化修复 pytest 配置、测试或实现，保留全部测试覆盖。
3. 全量后端测试通过后提交修复。

## 结果

- workspace pytest 配置统一收集 core、contracts 和 plugins，移除空的插件
  `tests/__init__.py`，避免模块冲突及重复执行其他插件的测试。
- n2 测试引用当前 `agents/n2.md`，并修正测试类型标注。
- speaker-sherpa 测试 mock 延迟加载入口。
- WeChat 测试使用实际 text_item 消息格式、显式启用语音输出并 mock 转码及
  当前上传/语音接口；未知 HTTPS 主机仍按 CDN 白名单拒绝。
- 全量后端：4257 passed、2 skipped、16 warnings（159.17 秒）。
- 全部插件：591 passed；修复涉及的三个插件：101 passed。
- Web lint、TypeScript、后端/CLI lint、修改文件 pyright、文档一致性、协议同步
  全部通过。E2E：10 scenarios、39 steps 全部通过。
- 开发服务日志检查未通过：浏览器在后端初始化期间断开时，发送 ready 帧出现
  uvloop closed TCPTransport RuntimeError，前端同时记录 ECONNRESET；另有
  Langfuse localhost:3001 不可用的导出错误。本次仅修改测试及测试配置，
  这些运行日志问题未修复，不能声称完整验证清单全部通过。

## Tests

- 通过现有失败测试复现问题；行为变更先补充回归测试。
- 从 backend 根目录执行 `uv run pytest`，覆盖 core、contracts 和 plugins。

## Verification Checklist（最后一步）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend/core && uv run ruff check src/ tests/`（workspace 布局）
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <修改的 Python 文件>`（如有）
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`
