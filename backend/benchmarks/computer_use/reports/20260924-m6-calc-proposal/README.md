# M6 calc 批次提案（2026-09-24）

M6 第 2 项的固定调度：**12 个 trial = 4 臂 × 3 轮**（m6-pair-1/2/3，臂序轮转），
任务 `calc-open`（macOS strict 7×8=56）。

与 M5 core 批的**唯一差别**：`enforce_agent_budget=true` —— 账本保持仅记录
（token/费用准入门禁按用户 2026-09-22 指令继续关闭），但 agent 的共享 300000
token 预算不再置零：规划与定位（C/D 的 locate 调用）共同计入，超限即停
（A 臂经 runner 预算检查；B/C/D 臂经 SubAgentContext 共享账本）。

每轮限制沿用：120 秒、顶层工具 15 步、planner 请求 16 次；C/D 额外 locate
请求 15 次（总 31）。全批声明上限：282 HTTP、3.6M token、1440 任务秒
（均为上限，不是消耗承诺）。

预检（`preflight_m6_calc`，346 文件）：`offline_checks_passed=true`、
`effective_agent_token_budget=300000`、`token_cost_gate=record-only`、
`live_ready=false`。阻塞项仍是 `live_endpoint_and_image_scope_authorization`。

未授权、未执行；执行入口见 `../20260924-m6-calc-ready/`。
