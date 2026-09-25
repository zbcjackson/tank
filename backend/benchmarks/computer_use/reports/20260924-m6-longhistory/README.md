# M6 第 4 项：长历史专项（2026-09-25 00:2x，两组各一轮）

按独立 manifest 执行：`long-history` 任务（TextEdit 输入 16 行、每 4 行核对），
A/C 各一轮，上限 600 秒 / 60 顶层工具 / 60 定位调用 / 300000 token（agent 预算
强制）。夹具：仅 TextEdit 允许可见 + 黑背景；门禁绑定任务窗口；发送前程序化
复核 initial 后放行。总消耗 626,560 tokens（A 314,947 + C 311,613），费用未核价。

## 核心发现：该路径没有历史压缩，预算停止就是事实上界

- **代码证据**：自研子代理链路（SubAgentDriver → AgentRunner → LLMAgent →
  `chat_stream`）不经过 ContextManager/Compactor——压缩机制只存在于主助手
  （语音对话）路径（`context/compactor.py`），子代理工具循环的历史只受
  MAX_TOOL_ITERATIONS=100、请求次数与 token 预算约束。
- **实测**：两轮均在**共享 300000 预算处受控停止**（`stop_reason=budget`；
  A 27 步/28 请求/64s，C 17 步/20 规划+2 定位/80.9s），无一轮接近 600s/60 步。
  预算停止的消息与元数据按第 2 项实现正确落 trace/报告（A 走 runner 检查、
  C 走共享账本 SubAgentStopped）。
- **结论与计划修正**：M6 第 4 项"压缩实际触发才算通过"的前提（存在配置的
  压缩阈值）**不成立**——如实报告"压缩未触发（机制缺失）"，不伪造验收。
  行为性验收（长历史下当前图引用/目标/失败恢复）通过；"为子代理路径引入
  历史压缩"移交 backlog（条件触发：任务 routinely 触顶预算时）。

## 行为验收（长历史下引用与恢复）

- **C 臂 stale-location 守卫实测**：两次 locate 返回 `ambiguous` 后，模型两次
  试图复用旧 `location_id` 派发 `mouse_move`/`click` → 守卫拒绝（"Missing or
  stale location; observe and locate again"，**零输入**）→ 模型重新截图观察后
  继续输入。当前帧引用/位置引用在长历史中保持有效且失效时安全拒绝。
- 停止时文档已正确输入 7 行（`第 N 行：N 乘以 7 等于 N×7`，内容逐行正确），
  未完成部分与预算停止一致；strict 判失败（16 行未完成）。
- 清理：两轮 `cleanup=confirmed`，launcher 清理全过，外层恢复 `confirmed=true`。

## 边界

- 单任务、每臂一轮；626,560 tokens 的行为证据不构成任务效果结论。
- 压缩缺失的结论以当前源码为准；主助手路径的压缩不受本项影响、未在本项测。
