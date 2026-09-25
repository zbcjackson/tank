# M7 批次 4 重跑材料（v2，宿主窗口绑定修复后，2026-09-25）

live1 批次（`../20260925-m7-ax-live1/`）证明 AX 寻址从未生效：模型无法得知
CGWindowNumber，所有 locate 因"未绑定窗口帧"被拒绝。修复：AXSession 截图
省略 window_id 时由**宿主**解析前台常规应用主窗口绑定（回归覆盖）；AX 提示
不再要求模型传窗口 id。live1 的 112 请求计入本轮授权总额（不重置）。

- `../20260925-m7-ax-runtime2/`：重生成冻结（AX 快照的脚本化截图改为无
  window_id，走宿主自动绑定路径）。
- `../20260925-m7-ax-proposal2/`：同定 9 trial 日程，352 文件预检通过。
- 本目录 launcher：指向 v2 冻结/提案；gate 11 例 / scope 5 例通过
  （launcher sha 一致）；预览（0 模型请求）清理 8/8、外层恢复 confirmed。
- 验收决策记录：`reviewed-2026-09-25-m7-live1-host-window-binding-fix`。

## 重跑授权范围

受控 Calculator 桌面截图 → DashScope（qwen3.7-flash），9 trial /
≤234 请求（live1 已用 112，本轮为声明新批次）；发送前复核 initial.png
后写 go 放行；串行执行。
