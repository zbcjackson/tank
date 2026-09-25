# M7 live 批次 1：AX 寻址未生效（设计缺陷），整批无效（2026-09-25）

用户授权后串行执行 9 trial（发送前复核 initial.png：83.8% 受控黑背景、
仅 Calculator、AX 显示 0）。全部 HTTP 200、112/234 声明请求、
1,474,746 tokens（record-only、unpriced）；launcher 清理 7/7、外层恢复
confirmed、零按键/鼠标残留、遮罩陷阱零触发（门禁拦 3 次窗外点击）。

## 结果：三臂 strict 全 0，但 AX 臂的 locate 从未成功——整批不能作对照证据

| 臂 | strict | 步数/token（均） | 失败形态 |
|---|---|---|---|
| A | 0/3 | 15.0 / 245.7k | 键序错（`7×97×`）、只按 7、`78`（运算符忽略） |
| AX-quartz | 0/3 | — | **全部 locate 在 observation_before 失败**，退化为键盘输入 |
| AX-press | 0/3 | — | 同上；另 2 轮基础设施中止（见下） |

**根因（设计缺陷，非模型能力结论）**：AX 模式要求模型截图时绑定
`window_id`，但模型无法从像素得知 CGWindowNumber——6 个完成 trial 的每一次
locate 都因"未绑定窗口帧"被拒绝（trace：locate_outcome=error、
stage=observation_before、零指针派发）。批次 1 的离线测试通过是因为脚本化
规划器硬编码了 window_id，掩盖了该缺陷。**AX 臂实际未测 AX 寻址。**

**另 2 轮基础设施中止**（m7-pair-3-ax-press / ax-quartz）：提供方流在
tool-call 参数中段截断（finish_reason=tool_calls 已达但 arguments JSON
不完整，body closed_early），M5 截断守卫正确零派发（安全），但守卫抛出
使 agent 以 "Expecting ',' delimiter" 终止——归类 infrastructure abort，
不修改 M5 冻结语义。

## 处置

- 本批证据保留归档（trial-summary.json / gate-events.json）；A 臂 3 轮
  仍为有效纯截图数据（与 M6 calc 批一致口径：本批 A 0/3）。
- 修复（先红后绿）：**宿主自动绑定**——AXSession 截图省略 window_id 时由
  宿主解析前台常规应用主窗口（`resolve_frontmost_window`，排除自身/小窗），
  AX 提示不再要求模型传窗口 id；回归覆盖解析与会话路径。
- 冻结/提案/材料因源码变化重生成（live1 的 112 请求计入本轮授权，
  不重置；重跑为声明新批次）。
