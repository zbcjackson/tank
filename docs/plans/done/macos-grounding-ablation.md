> 状态：已完成（100 次合成请求隔离与真实响应回放），2026-09-19

# macOS 定位偏差的模型请求隔离

1. 固定纯合成图片与 x/y schema，比较完整代理提示、纯定位提示、显式尺寸公式。
2. 成组比较 enable_thinking 和高分辨率参数；记录实际 HTTP 图像 hash、参数、原始响应及误差，不执行模型动作。
3. 必要时比较纯 JSON 与工具输出，并使用新尺寸/位置留出样本复验，避免从单次成功推断修复。
4. 区分可证实的请求/输出问题与无法观测的模型内部预处理；记录证据与未覆盖条件。

## Tests

- pytest 经过实际 OpenAI SDK 的 HTTP 序列化验证图像尺寸/hash、请求参数以及返回坐标，网络响应使用固定 SSE。
- 固定样本误差评分回归；探针默认路径保持现有行为。
- 真实模型仅发送生成图片，所有输出仅评分。

## 最终 Verification Checklist

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/`
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright` 加本轮修改的 Python 文件
6. `cd cli && uv run ruff check src/ tests/`
7. 检查 tmux tank 实际后端面板的 reload 错误
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`

## 结果

- 固定图消融、留出验证、原始 SSE 和非流式复验累计 100 次，只有合成图外发。
- 确认非法 arguments 在服务端输出时已存在；4 次 raw SSE 与本地累加逐字
  相同，8 次非流式响应仍非法。pytest 回放真实 SSE 验证错误拒绝、不执行输入。
- 简化提示、公式、关闭思考、高分辨率均未稳定修复偏差；图像 token 用量
  与近原尺寸 patch 对齐相符，不支持统一 1280 宽或全局倍率补偿。
- 明确请求原生 bbox_2d 后 hard 8/8 在 15 px 内；独立尺寸/位置 4/8 在
  15 px 内、最高 41.1 px，尚不足以更改生产路径。后续候选验收交接 backlog。
- 探针相关 23 passed；最终完整 backend **4451 passed, 1 skipped**。
  web lint/tsc -b、backend/CLI ruff、修改文件 pyright、docs/protocol、
  后端 reload 日志检查通过；E2E **14 scenarios / 55 steps** 通过。
- 首轮 sandbox 内测试因监听端口/系统服务/Chromium Mach port 权限失败，
  终止后在批准的沙箱外环境重跑并通过，没有忽略红色测试结果。

[调查记录](../../research/macos-coordinate-chain.md#2026-09-19-继续请求消融与服务端原始响应)
说明各对照的请求、结果与结论边界；动态屏幕/高频输入沿用已有 backlog 项。
