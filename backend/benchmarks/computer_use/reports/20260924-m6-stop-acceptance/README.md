# M6 第 5 项：完整派发路径的停止/清理验收（2026-09-24 23:4x）

五个场景在**真实 driver/Runner/工具链 + 真实 Quartz 输入**上进行中途取消，LLM 端点为
本地回环 mock（`http://127.0.0.1:8931/v1`）：零外部请求、零模型调用；真实截图仅发往
本机 mock，截图文件以 sha256 归档（原始图含用户桌面，不落仓库）。

## 场景与结果（`results.json`，全部 PASS）

| 场景 | 取消时机 | 返回耗时（取消→返回） | 返回后 10s 事件 | 按键/鼠标 | 复用 |
|---|---|---|---|---|---|
| planner-wait | 规划请求在飞（mock 延迟 25s），+2.0s 取消 | **0.107s** | **0** | 空/空 | ✅ |
| locate-wait（C 拆分） | screenshot 后 locate 请求在飞（延迟 25s），+6.0s 取消 | **0.104s** | **0** | 空/空 | ✅ |
| key-hold | `hold_key(shift, 6s)` 保持中，+1.5s 取消 | **4.619s** | **0** | 空/空 | ✅ |
| batch | `computer_batch` 的 5s wait 成员执行中，+1.2s 取消 | **0.104s** | **0** | 空/空 | ✅ |
| drag | 窗内文本选择拖拽进行中，+0.4s 取消 | **0.366s** | **0** | 空/空 | ✅ |

关键行为证据：

- **join 语义验证**：key-hold 在取消后 4.619s 才返回——原生保持（6s，取消于 1.5s）
  由驱动层 join 到自然结束后释放，返回前完成 key-up；返回后严格 10 秒零输入事件
  （Quartz session tap 监听 mouse/keyboard/scroll 全事件）。
- **batch 首停即停**：取消后未执行的成员（`AFTERCANCEL` type_text）零执行——
  TextEdit 当轮内容核对确认标记串未出现。
- **拖拽无粘滞**：取消后鼠标按键释放（CGEventSourceButtonState 空），无拖尾事件。
- **资源可复用**：每个场景后全新 driver 短跑（mock 即时文本响应）均正常完成
  （`reuse-ok`，无 error）——桌面锁/输入清理未泄漏。
- 通知/计账：各 trace 记录 `desktop_cleanup`、取消传播（CancelledError）与请求
  生命周期事件；mock 用量（10+5 tok/请求）进 trace。

## 边界与披露

- 取消传播为 CancelledError（预期）；未测物理断电/kill -9（超出本轮）。
- 复用前执行的真实输入限制在空白 TextEdit 文档内。
- **操作失误披露**：验收脚本 teardown 后 TextEdit 仍在运行（说明验收开始前
  TextEdit 已在运行——脚本按 was_running 正确未退出它），但本助手随后手动执行了
  `quit`。核对：TextEdit 自动保存目录在本批开始后无任何文件变更、退出未出现
  保存对话框，未发现用户文档受影响；该手动操作仍属不该做的越界清理，如实记录。
- 本项不覆盖：停止时延的分布统计（单次每场景）、SDK/插件传输（引擎 transport
  不在自研路径内）、外层恢复（已在 M6 calc 批 confirmed）。
