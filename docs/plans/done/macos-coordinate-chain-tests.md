> 状态：已完成（静态主屏链路、隔离定位与真机校准），2026-09-19

# macOS 截图与点击坐标链路验证

初轮范围：自研 computer_use 与共享 MacOSDesktopExecutor 的测试和证据。
本轮用户追加授权：补齐转换测试缺口，开始隔离验证及真实校准。
继续使用 TDD：先正确性回归，再最小修复；真实输入仅在专用校准窗口，
固定截图模型请求不执行返回的动作。

1. 梳理原始截图、逻辑分辨率、裁剪、模型消息、归一化参数与 CGEvent。
2. 在现有 macOS 测试文件补跨层 pytest，外部命令和 Quartz 使用替身。
3. 区分正确行为、已知缺陷的现状刻画和无法由离线测试验证的边界。
4. 扩展至真实 OpenAI SDK HTTP JSON 请求及分片工具参数返回。
5. 修复明确的 macOS 转换错误，并增加失败/边界/显示尺寸变化覆盖。
6. 检查权限与显示器，运行专用窗口九点校准；固定截图分别评估全屏和裁剪。
   保存系统落点、窗口事件与目标命中；权限不足明确记录，不绕过 TCC。

## Tests

- 1x/2x、非正方形屏幕：截图缩放到逻辑尺寸，图像消息不再次缩放，
  归一化输入最终送入真实点击实现的 Quartz 事件参数。
- 缩放失败：由现状刻画升级为正确性回归，明确报错而非误用 Retina 原图。
- 裁剪并放大：核对像素内容、返回图尺寸、完整屏幕缓存、局部到全屏公式。
- bbox、字符串、拒绝越界/非有限值、边界点；核对工具与 executor 的取整差异。
- 固定历史计算器坐标：证明错误在模型输出时已经存在，不测试模型能力。
- batch 截图与后续点击；测试不会执行真实桌面输入。

## 最终 Verification Checklist

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/`（新 workspace 路径）
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright` 加上本轮所有修改的 Python 文件
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`

环境阻碍必须单独记录，不能将离线通过等同于真实桌面验收。

## 结果

- 初轮提交 `9811659` 增加 14 个现状用例；本轮将已知缺陷升级为正确性断言，
  增加真实 HTTP/SSE 边界、1.5x、尺寸不符、非法坐标与真实响应回放。
- macOS 文件 **81 passed**，六文件坐标相关回归 **242 passed**。
- 完整后端 **4413 passed, 1 skipped**。首次全量仍有 3 个 Opus 失败：
  opuslib 的 CTL 是 C 可变参数函数，遗漏固定参数 argtypes 导致 Apple ARM64
  间歇 invalid argument；已修复声明，增加 100 次 bitrate setter/getter 原生回归。
  依据：[Python ctypes 可变参数文档](https://docs.python.org/3/library/ctypes.html#calling-variadic-functions)。
  此修复是仓库要求“修复所有失败测试”的附带工作，和坐标偏差无因果关系。
- web lint/tsc、backend ruff/修改文件 pyright、CLI ruff 均通过。
- 实际后端 tmux tank:1.1 的最终重载日志检查为空，通过。
- E2E 最终 14 scenarios / 55 steps 通过；协议同步、docs check 和 diff 检查通过。
- 16 次实际模型请求仅包含程序合成图；复杂图复现数百 points 偏移和非法参数。
  本地请求字节校验通过；未执行模型返回动作。真实截图未发送模型。
- 获得 Paseo 的 Screen Recording 与 Accessibility 权限后运行校准：
  c/d 两轮完整九点通过，e 恢复 0.1 秒额外间隔后九点也通过，最大每轴误差 1 point。
  a/b 的初始异常一并归档，不将它们删掉或描述为全程无异常。
- [链路分析](../../research/macos-coordinate-chain.md) 记录证据强度和未验收边界。

本轮完成当前静态主屏转换验证与大偏移定位；不能用有限测试保证所有 macOS
硬件、动态屏幕状态及模型输出正确。非主屏/动态几何和无截图高频输入若进入
产品支持范围，须另行设计验收，不能沿用此轮通过结论。
