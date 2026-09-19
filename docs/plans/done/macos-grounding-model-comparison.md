> 状态：已完成（80 次三模型/生产 schema 对照），2026-09-19

# macOS 固定图模型对照

1. 在同一 DashScope 端点比较当前 Flash、Qwen3.7 Plus 与 Qwen3 VL Plus 的固定版本。
2. 固定生成图片、agent 提示、point-only schema、temperature 与 thinking 参数；hard/holdout 各八次，不执行返回动作。
3. 保存实际 HTTP model、图片 hash 与原始响应，区分格式错误与定位误差。
   若候选明显改善，追加使用生产完整 click schema 的同图基线/候选对照。
4. 结论区分模型相关性、共同提供方与未验证的动态 macOS 因素，不根据小样本自动更换生产模型。

## Tests

- pytest 验证探针 model override 只作用于该次请求配置，不改生产 profile。
- 回归原始 SSE、图像/参数 HTTP 序列化与评分测试。
- 模型对照只能发送纯合成图。

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

- 三个固定模型 point-only 各 16 次，Flash/Plus 生产 click schema 各 16 次，
  累计 80 次；HTTP 参数/图片 hash 与响应模型已核实，只发送合成图。
- point-only 超过 50 px 的次数：Flash 8/16、Plus 1/16、VL Plus 2/16。
  生产 schema：Flash 12/16、Plus 1/16；Plus 仍有一次约 150 px 的大错。
- 支持模型及输出协议适配相关的问题，尚不能区分模型权重与提供方服务
  内部实现；生产配置未切换，未将合成图精度等同真实 GUI 点击成功率。
- model override 先写失败测试，再实现并通过；相关 24 passed；完整后端
  **4452 passed, 1 skipped**；E2E **14 scenarios / 55 steps** 通过。
- web lint、tsc -b、backend/CLI ruff、修改文件 pyright、docs/protocol、
  后端 reload 日志检查与 diff whitespace 检查全部通过。

[详细结论与剩余原因](../../research/macos-coordinate-chain.md#2026-09-19-同一提供方的模型对照)。
本轮为隔离实验，真实定位方案验收与动态屏幕条件沿用已有 backlog 项。
