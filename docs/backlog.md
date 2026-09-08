# Backlog — 条件触发的后续工作

> 生命周期：**持续维护的登记表**，不是一次性计划。计划文档关档移入 `plans/done/` 前，其中"暂缓 / 按触发条件立项 / 非目标但将来可能做"的条目移交到这里；调研文档与代码注释产生的同类条目也登记于此。

## 登记规则

- 每条必填：**触发条件**（什么事实发生时立项）、**背景/前置**（一两句）、**来源**（文档链接）。
- 只有"带前置或触发条件的将来工作"进本表；确定要做的近期待办直接进 `plans/active/` 写计划。
- 条目被触发立项（新建 `plans/active/` 计划）或被明确放弃时，**从本表删除**——历史由新计划文档与 git 承担，本表只保留尚未启动的项。
- 前置条件已满足、随时可立项的条目照常保留，在触发条件栏注明。

## 条目

| 项目 | 触发条件 | 背景/前置 | 来源 |
|---|---|---|---|
| 客户端 token 携带（web/cli/device 连接时发 `?token=`） | 远程部署启动 | P0-2 只落地了服务端校验，三端客户端从未实现携带；需与 token 分发方式一并设计 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) P0-2 |
| 认证 token 分发方式定案 | 远程部署设计时 | 配置文件 vs 首次配对流程，计划 §11.2 未决问题 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §11 |
| Resume（断线续传） | 远程部署实测断线频繁到影响体验 | 现靠 session_id 恢复会话历史，在途 turn 状态全丢；需 text/audio 帧序号 + 重连 replay 窗口 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| WebRTC 传输 | 远程实测 Opus-over-TCP 仍因队头阻塞卡顿 | Opus-over-WS 已拿 80% 收益；届时 WebRTC 仅作传输层挂入，私有消息集原样复用（JSON 走 data channel） | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| Realtime 端点（`/v1/realtime`） | 第一个第三方客户端/机器人接入需求确认 | 作为边缘网关建立在演进后的私有栈之上（同一管线池 + 同一认证） | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| LLM Proxy | 出现需要借用服务端凭据的外部旁路任务 | tank 的摘要在服务端内部直调 LLM client，当前无旁路需求 | [protocol-evolution-plan.md](plans/done/protocol-evolution-plan.md) §6 |
| memory `pinned_soft_cap_kb` 软上限告警 | **前置已满足**（IMP-1 Dream Consolidation 已落地，默认关闭），可随时立项 | 12 KB pinned 软告警当初因无收敛路径而暂缓；现在 consolidator 可收敛超限 pinned 集，告警有意义了 | [memory-context-improvements.md](plans/done/memory-context-improvements.md) §0 |
