# M6 第 1 项：本地九点与 Calculator oracle 重验 M2 驱动（2026-09-24 22:12）

按计划 M6 第一项执行。**本地-only**：零模型请求、零截图外发；真实鼠标/键盘
动作串行执行。环境：macOS 主屏 1920×1080 逻辑（2x backing，display 2），
副屏竖屏 1080×1920（origin 1920,-602，校准/Oracle 均未涉及）；Screen Recording
与 Accessibility 权限预检通过；前台应用 Paseo。

## 九点校准（`calibrate_macos_coordinates.py`，image 坐标系）

| 模式 | 结果 | 每轴误差 | down/up 事件对 | 清理 |
|---|---|---|---|---|
| 窗口绑定（crop [100,402,900,930]，image 1920×1267） | **9/9 命中** | **0.0 point** | 9/9 完整（含时间戳） | 窗口关闭 + 光标恢复 ✅ |
| 全屏（crop [0,0,1920,1080]，image 1920×1080） | **9/9 命中** | **0.0 point** | 9/9 完整（含时间戳） | 窗口关闭 + 光标恢复 ✅ |

每点证据（`nine-*/results.json`）按 M6 要求包含：事件 down/up（NSEvent 本地
监听 + view 命中判定）、光标回读（`CGEventGetLocation`）、时间戳、目标边界
（expected_screen/expected_view）与 frame 观察（frame_id、crop、image_size、
image_sha256、display_geometry）。每点点击前独立验证目标像素可见后才派发。

## Calculator oracle（`oracle-check.py`，复用 a-control pilot 脚本并补 frame 观察）

- 输入法 ASCII 钉定 → reset（ESC×2）→ 窗口定位 (600,100) → 生产
  `KeyPressTool` 依次派发 `7`、`shift+8`、`8`、`enter`（均成功，时间戳见
  result.json）。
- AX 回读：`expression=7×8, result=56` → **oracle_passed=true**。
- M2 窗口 frame 观察：crop [600,100,1274,508]、image 1920×1162，
  `calculator.png` 已存档（含 56 显示）。
- 清理：Calculator 退出确认、按键/鼠标均无残留、输入源恢复请求已发出。

## 边界（不因通过而改写）

- I09（早期事件缺失/回读异常）**未再复现只说明本批通过**，历史异常仍未解释，
  不得写为已解决。
- 副屏存在但本轮未触发任何多屏路径；不宣称多屏支持。
- 本轮不涉及模型、定位或 benchmark；M2 驱动在当前源码 revision 下功能完好。
