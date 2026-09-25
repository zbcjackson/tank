# M7 live 批次 2：自动绑定生效；非法 JSON 崩溃与选择器错选两类新发现（2026-09-25）

用户授权后串行 9 trial（发送前复核 initial.png）。94 请求 / 1,084,785 tokens
（record-only）；清理 8/8、外层恢复 confirmed、零输入残留、门禁拦 2 次窗外
点击。live1+live2 累计 206 请求。

## 结果

| 臂 | strict | 失败形态 |
|---|---|---|
| A | **1/3**（`7×8=56`，本计划 M7 首个纯截图 strict 通过） | 只按 7、`7÷8=0.875`（÷ 键） |
| AX-quartz | 0/3 | 2 轮 max_steps（见下），1 轮 infra abort |
| AX-press | 0/3 | 3 轮全部 infra abort（同因） |

## 发现 1（已修复）：模型自产非法 JSON 使 agent 崩溃

5/6 AX trial 在第 2–3 步死于 `Agent error: Expecting value/delimiter`：AX
提示不再提窗口 id，但 **screenshot 工具 schema 仍暴露 `window_id`**，模型把
上一帧的 `frame_id`（32 位 hex、未加引号）当作 window_id 传入，产生非法
JSON；M5 守卫正确零派发但抛出杀死 agent。live1 的 2 次"截断"中止同属此类
守卫致命路径。**修复（先红后绿）**：(a) AX 模式 schema 隐藏 window_id（宿主
注入经 `_host_arguments` 豁免校验）；(b) 非法 JSON 参数改为**可恢复工具错误**
（零派发保持，模型收到错误后重发；finish_reason 非 tool_calls/stop 仍整响应
拒绝）。集成流测试扩 truncated/duplicate/malformed 三种收尾语义。

## 发现 2（真实模型能力数据）：选择器索引精度差

宿主自动绑定生效后（ax-quartz pair-1/2：locate found 3/2 次、点击全部派发
成功），**选择器（qwen3.7-flash）在 57 行候选列表中选错相邻项**：目标"7"
（index 23）实际选了 index 22（"10 to the X"）×3 次与 14（"All Clear"），
最终显示 `100`/`100×7`；pair-2 有一次正确选 23。AXPress 三轮均在发现 1 处
崩溃、未获得有效数据。**AX 自动获得边界 ≠ 选择模型能选对目标**——与计划
M7 第 2 项的预期一致，是选择模型能力问题而非寻址机制问题。

## 处置

- 修复提交后重生成 v3 冻结/提案/材料；live3 为声明新批次（≤234 请求）。
- 选择器错选是合法结果：若 live3 复现，AX 分支结论为**条件性暂缓**
  （机制可用、当前选择模型精度不足）。
