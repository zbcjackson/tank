> 状态：测试与链路梳理完成；全量检查未通过，2026-09-18

# macOS 截图与点击坐标链路验证

范围：自研 computer_use 与共享 MacOSDesktopExecutor；只补测试和证据，
不改变运行行为，不调用真实鼠标或付费模型。

1. 梳理原始截图、逻辑分辨率、裁剪、模型消息、归一化参数与 CGEvent。
2. 在现有 macOS 测试文件补跨层 pytest，外部命令和 Quartz 使用替身。
3. 区分正确行为、已知缺陷的现状刻画和无法由离线测试验证的边界。

## Tests

- 1x/2x、非正方形屏幕：截图缩放到逻辑尺寸，图像消息不再次缩放，
  归一化输入最终送入真实点击实现的 Quartz 事件参数。
- 缩放失败：刻画原图被误用为逻辑尺寸导致 2x 错点；不是正确性验收。
- 裁剪并放大：核对像素内容、返回图尺寸、完整屏幕缓存、局部到全屏公式。
- bbox、字符串、越界 clamp、边界点；刻画直接工具与 executor 的取整差异。
- 固定历史计算器坐标：证明错误在模型输出时已经存在，不测试模型能力。
- batch 截图与后续点击；测试不会执行真实桌面输入。

## 最终 Verification Checklist

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/`（新 workspace 路径）
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright core/tests/test_computer_use_macos.py`
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`

环境阻碍必须单独记录，不能将离线通过等同于真实桌面验收。

## 结果

- 新增 14 个参数化测试用例；macOS 文件共 61 项，相关五个文件组合回归
  191 passed。测试提交 `9811659`；仅改测试，运行逻辑未改。
- 逐步尺寸、坐标与测试边界见
  [链路分析](../../research/macos-coordinate-chain.md)。
- web lint、`tsc -b --noEmit`、backend/core ruff、修改文件 pyright、CLI ruff、
  协议同步检查通过；E2E 14 scenarios / 55 steps 全部通过。
- docs check 与 diff whitespace 检查通过。
- 完整后端首次在收集时无法找到 Opus；增加
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/opus/lib` 后跑完：
  **4373 passed, 1 skipped, 13 failed, 5 errors**（增加最后一个 crop 上限测试前）。
  失败未被标记为通过，也没有添加 skip 或 xfail 掩盖失败。
  - pageserver/bench runner 与 CosyVoice fake server：沙箱禁止本地端口监听。
  - notification：写入默认 `~/.tank` 路径被禁止。
  - Edge TTS：外部网络请求失败。
  - click schema：oneOf 分支缺少局部 items/y properties，两个结构检查失败。
  - Opus：设置 bitrate 返回 invalid argument。
  全量日志在本次机器 `/tmp/tank-coordinate-pytest.log`，不纳入仓库。
- `tmux capture-pane -t tank` 默认面板实际是 shell，grep 命中用户脚本的
  `except Exception`，不是 dev server traceback。进一步只读枚举面板的
  require_escalated 请求被自动审批以额度耗尽拒绝；未绕过拒绝。
  所以不能宣称已检查实际运行中的 dev server reload 日志。

计划保留 active，完整验收未完成。已确认的坐标缺陷本次只作现状复现，
不将现状测试通过描述为 bug 修复。
