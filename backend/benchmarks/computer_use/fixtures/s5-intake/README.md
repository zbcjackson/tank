# S5 intake 受控样本

2026-10-16：用于动作/填充值边界回归及无桌面提示对照，不是模型效果验收。

- `legacy-system.txt`为原H/J真实批次的system提示，SHA256 `33a0144178d0f52f84a989a616cb6e4b51920fc5b095b95be2ce4446fb00c360`。
- `recorded-failures.json`保留三类未绑定按键值和一份完整JSON围栏回复；来源result SHA
  `98e46670f9bc2b989b681c9e3dd5837a3588a38181633aea252f18b6f9dbbd0f`。
  context简化为单应用约束，不保存原始安全规则/用户目录等上下文；不是逐字网络重放。
- `cases.json`为两个受控任务：原Calculator长算式与TextEdit字面运算符/末尾换行。
  expected只供本地判定；模型只收到request/context/application/response_schema。

原错误回复仍须被来源校验拒绝。新提示效果必须通过单独真实对照观察，不能用fake回复
或围栏兼容回头修改原40项评分。
