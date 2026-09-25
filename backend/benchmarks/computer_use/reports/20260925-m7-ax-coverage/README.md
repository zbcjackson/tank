# M7 批次 2：AX 分支本机覆盖率与边界验收（2026-09-25）

零模型请求、零截图外发；桌面动作仅限本脚本启动/复位/移动/关闭的 Calculator
窗口（`7`/`8` 各一次按键级派发 + 复位 Escape）。其余应用只读枚举，不移动、
不关闭。证据：`enumeration.json`、`boundaries.json`；脚本：`enumerate.py`、
`boundaries.py`（均经生产 `tank_backend.tools.computer_ax` 路径）。

## 覆盖率（真实观察，57–429 候选，无截断）

| 应用 | 候选 | 全有 frame | 同名组（按 title） | 枚举耗时 |
|---|---|---|---|---|
| Calculator | 57 | 57 | 0（title 空，标签在 description，见下） | 0.16 s |
| TextEdit | 22 | 22 | 0 | 0.04 s |
| Terminal | 7 | 7 | 0 | 0.03 s |
| System Settings | 56 | 56 | 0 | 0.17 s |
| Safari | 31 | 31 | 1（页标题出现两次：窗口/标签） | 0.04 s |
| Poe（Electron） | 14 | 14 | 0 | 0.04 s |
| Arc（Chromium） | 429 | 429 | 多组（"Add to Cart" ×9 等） | 0.93 s |

- **批次 1 的"Electron/Chromium 空树"结论被撤销**：那 pyobjc `NSArray` 不是
  Python `list`/`tuple` 子类导致 `isinstance` 失败、子树从未入队。修复
  （`_strings` 与子元素入队改为迭代协议 + 回归测试
  `test_ax_window_candidates_walks_nsarray_children_and_actions`）后，所有
  实测应用的 AX 树均可用。
- 标签来源：macOS 26 按钮普遍 `AXTitle` 为空，标签在 `AXDescription`/
  `AXIdentifier`（如 `7`/`OpenParenthesis`）；候选列表已包含这些字段。
- `AXActions` 属性普遍缺失（`pressable` 计 0），但 **AXPress 实测可用**：
  因此 `ax_press` 派发不预检查动作列表，以 `AXUIElementPerformAction` 返回码
  为准（回归 `test_ax_press_works_without_advertised_actions`）。
- 同名歧义真实存在（Arc 的 "Add to Cart" ×9），由选择模型消歧或报 ambiguous；
  本批未测模型行为（批次 4）。

## 边界行为（Calculator，生产 AXSession 派发路径）

| 场景 | 结果 |
|---|---|
| quartz 派发 | `7` 按钮 AX frame (1006,287,60,48) → 派发 **(1036,311)**（精确帧中心，经 M2 校验），AX 显示 `7` |
| ax_press 派发 | `8` 按钮 → AXPress err 0，显示 `78`；无指针事件 |
| 旧引用（stale） | 退出应用后 `ax_refresh_candidate` → None；会话派发被 M2 窗口守卫拒绝（"Window is missing or no longer on screen"），零输入 |
| 窗口不匹配 | 绑定后移动窗口 → "Window geometry changed" 拒绝，显示仍 `0`，零输入 |
| 清理 | 无按键/鼠标残留，Calculator 已关闭，原前台恢复 |

`ax_press` 对 Calculator（无 AXActions 宣告）实测生效，错误码为权威；
quartz 与 ax_press 两次 `desktop_dispatch` 事件均 `succeeded=true`，
`effect=unknown`（由独立 AX 读回验证效果，非模型自报）。

## 现场与披露

- 脚本启动的 Calculator/TextEdit（空 Untitled）/Terminal（新 zsh 窗口）已
  全部关闭；TextEdit AppleScript 退出间歇性 "User canceled"（M1 已知），
  以 Cmd+W + 按名关闭文档 + killall 兜底。
- System Settings 与 Safari 窗口归属不确定（运行状态判断受 AppKit 缓存影响，
  且期间有用户活动：WeChat/Cua Driver 出现）；按保守原则未关闭，保留现状。
- 枚举脚本首次运行因 TextEdit 退出超时崩溃，已改为逐应用增量写盘 + 稳健
  退出；崩溃与清理过程如实保留在本 README。

## 结论（M7 第 2 项）

每条分支的真实覆盖率已明确：全部 benchmark 应用均有可用 AX 树（57–429
候选、100% 有 frame、无截断）；缺失 AX 的自绘控件在本批实测中**未出现**
（此前空树结论系实现 bug）；同名歧义在 Chromium 内容中常见、原生应用罕见；
旧引用/窗口不匹配均零输入拒绝；ax_press 覆盖 Calculator 类无宣告控件。
AX 自动获得边界 ≠ 模型能选对目标——选择正确性留待批次 4 与纯视觉臂对照。
