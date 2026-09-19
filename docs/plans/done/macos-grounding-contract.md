> 状态：已完成（坐标协议隔离与 macOS 结果验收），2026-09-19

# macOS 模型坐标协议与计算器验收

1. 合成图控制尺寸、宽高比与目标位置，按实际 HTTP 图像 hash 保存模型输出。
2. 分别检验 0–1000 归一化、原图像素、最长边 1280 像素假设；不执行模型动作。
3. macOS calc-open 验证可见计算器结果 56，拒绝仅进程存在和错误结果。
4. 真机验证结果读取；仅合成图片允许发送模型。

## Tests

- 坐标假设评分分别识别已知输入，非法响应不进入命中统计。
- 计算器结果 35/空/遮挡或不可见/缺少权限失败；正确可见结果通过。
- 任务加载与实际 shell validator 接入；原有 benchmark 回归。

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

- 基线 32 请求：18 个可解析响应、14 个格式非法；同图同目标重复调用在
  归一化与缩放后像素两种解释间变化，否定全局固定倍率修复。
- point-only schema 对照 16 请求：全部可解析，仍有 6 次归一化误差超过
  50 pixels。仅简化 schema 不能保证定位正确；未修改生产模型协议。
- 计算器验证器读取表达式与结果，准备阶段清零，macOS strict/GUI-only；
  真实 trial runner：5×7 失败、7×8 成功；原始真实桌面图未发送模型。
- TDD 先复现缺失评分、非法值、结果误判与任务配置失败，再实现并通过；
  相关四文件 55 passed；完整后端 **4436 passed, 1 skipped**。
- web lint、tsc -b、backend/CLI ruff、所有修改 Python 文件 pyright 通过；
  E2E **14 scenarios / 55 steps** 通过，实际后端 reload 错误检查为空，
  docs/protocol consistency 与 diff whitespace 检查通过。
- 最初真机读取曾被自动审批用量额度阻断；用户要求继续后重试恢复，
  本轮所需真机验证全部完成。

[详细证据与局限](../../research/macos-coordinate-chain.md#2026-09-19-后续坐标系判别与-calc-open-验收)。
模型可靠定位方案仍需独立评测，截图像素级验收未纳入本轮结果读取器；
后续触发项已登记 backlog。
