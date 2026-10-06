> 状态：已完成（2026-10-06，实现、全部适用验证及三轮有界评审收口；Computer Use S4 未启动）。

# 模型调用层简化

## 范围与最终设计

用户确认清理 Jev 及 Chat Completions 的自定义 Route/Transport。核心 `DecisionModel`
独立封装官方 SDK、配置及 Choice 结果，`TaskDecisionModel` 通过组合增加任务检查、取消、
deadline 和唯一用量记录。文本模型复用现有 LLM SDK 接口，任务绑定采用同样调用级包装。
移除 provider 单选配置、生产 ModelRoute/ChatCompletionsRoute/JevChoiceRoute、
TaskModelTransport、httpx2/httpx 桥接、自研 SSE 字节解析和绕过 Langfuse 的 SDK 子类。

SDK 负责 HTTP/序列化/流式解析；任务层仅围绕 SDK 调用和 SDK 流式事件工作。保留调用前
准入、取消/超时、关闭后拒绝、共享记账、已知错误用量与未知用量区分、结果选项校验。
不再承诺实际网络发送阶段的线级审计、逐字节协议/压缩/重复字段限制、未发送证明。
普通可观测性采用现有任务 observer 与可选 Langfuse，失败不阻断业务调用；模型调用
不再写必需执行审计。UI/工具的授权、派发、回执和必需审计仍保留。

实验费用/捕获保持显式 opt-in，消费调用级请求/结果而非伪称实际 HTTP；历史原始回放
采用实验内小型原始请求函数，不保留另一份生产 Transport。旧 reports/fixture/评分结果
不改，新代码必须新冻结；旧 wire 证据按记录的 Git revision 复现。取消已送请求不承诺
供应商停止计费，用量无法取得记 unknown。累计限额也不等于并发请求的精确费用上界。

## 实施顺序

1. 定义 SDK 调用级记录/实验 hook，复用已有 TokenUsageLedger 和 task observer；先写红测试。
2. 分离 DecisionModel / TaskDecisionModel，去 provider；使用 SDK 原生 HTTP，不自定义 transport。
3. 迁移 TaskModel、普通 LLM 任务绑定和 SDK 流式生命周期；保留工具/视觉消息行为。
4. 清理旧 Route/Transport/TaskStream/TaskOpenAI，迁移实验与测试，更新当前设计/配置文档。
5. 完成下方完整验证及最多三轮独立 review-and-refactor，按逻辑子任务提交。

## Tests

真实 SDK + fake 网络验证独立决策服务、任务包装、已知/未知/失败用量、并发去重、取消与
迟到结果、关闭借用资源边界、流式首 token/工具/推理字段、SDK 已缓冲事件仍逐事件检查。
Langfuse/observer 可禁用、失效不改变选择或调用次数；不允许重复上报造成重复记账。
退役仅用于原 HTTP 强保证的断言，替换为新 SDK 级行为测试，不删除仍需保留的任务边界。
扩展既有 core/插件测试和 managed Chromium E2E，不另建同域 feature，不追加付费实验。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查改动 benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run pytest`，本机加载 opus 库路径。
5. `cd backend && uv run pyright <全部改动 Python 文件>`，不增加 type-ignore。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，连接运行中的本地服务。
9. `python3 scripts/check_docs.py` 及 `git diff --check`。
10. `python3 scripts/check_protocol_sync.py`：仅改动协议契约/生成物时适用。


## 实施与验证记录（2026-10-05）

基线 `e311025a`。独立 DecisionModel、组合式 TaskDecisionModel、公共 SDK 调用级
TaskModelCalls 已实现；普通 LLM/TaskModel 借用 SDK 客户端，不再替换底层 transport。
删除 ModelRoute、ChatCompletionsRoute、JevChoiceRoute、TaskModelTransport、TaskStream、
TaskOpenAI 及 SDK httpx2/httpx 桥接。profile 去除 provider 字段，运行时 API 升级为 3，
旧版本在工厂前拒绝。UI/工具的执行审计与 Computer Use S4 均未改动。

普通可观测性复用原 observer 与可选 Langfuse；独立 Jev span 标记错误并保留已知用量，
遥测故障不改变调用结果。实验驱动去除旧 HTTP hook，防止与 SDK 级计量重复；SDK 记录
保留调用关联和图片哈希，不再冒称原始 HTTP。历史 raw 回放使用实验内原始请求函数，
既有 reports/fixture/冻结文件未改。所有模型测试使用 fake provider，没有付费调用。

TDD 覆盖独立 SDK 接口、已知错误用量、候选集合在调用时绑定、重复取消与关闭期间的
清理、排队后取消零 SDK 进入，以及观测失败/错误状态。修正旧 malformed fixture 的
无效替换（此前输入实际上仍是合法 JSON）；保留真正无效参数零派发、修正后仅一次
执行的断言。测试共享 SDK fake 边界同时覆盖 workspace 与 core-only 两种 pytest root。

完整后端 **5575 passed / 1 skipped / 21 warnings**（317.83 秒，
`/tmp/tank-model-slim-backend-serial.log`，强制 Chromium）。E2E 单独运行 **17 场景 /
67 步通过**（`/tmp/tank-model-slim-e2e-serial.log`）。前期并行浏览器测试遇到启动/导航
超时，改为顺序验收，未放宽生产浏览器超时或断言。核心流式/驱动 96 项、定位与模型层
198 项、核心/Jev 328 项定向回归通过；完整计数因旧 HTTP 契约测试退役而变化。
web lint/tsc、backend/CLI lint、全部改动 Python pyright、dev 日志、docs/diff check
通过。未修改协议契约/生成物，第 10 项不适用。最终工作树 E2E 再次通过 **17 场景 / 67 步**（`/tmp/tank-model-slim-e2e-ready.log`）；
最终开发日志检查无错误。独立评审记录待追加。


### 独立评审与继续修复（2026-10-06）

第 1 轮评审发现两项问题：文本包装仍将可选 usage 缺失作为错误；任务决策调用的
实验快照与 SDK lambda 引用的可变输入可能分叉。已移除前者的结果门槛，缺失/null usage
记录 unknown 并返回有效文本；严格实验策略仍可停止。Jev 和普通聊天均在任务入口复制
私有输入，实验记录器拿到独立副本；回归同时修改原始参数与记录器参数，验证实际 SDK
请求仍等于原入口快照。普通聊天问题先用新增回归复现失败，再修复为通过。

原评审因工具额度中断，不能将其记录成评审通过；协调者继续补齐修复和全量验证后
恢复同一有界评审流程。签名代理曾两次返回 `agent returned an error`，未禁用签名，
当时尚无本轮实现提交，现已恢复，见最终验收。没有修改 S4 或历史实验原始证据。


### 最终验收（2026-10-06）

实现签名提交 `cfe5cb59`，包含 R1 可选 usage 处理和 R2 Jev/普通 LLM 私有快照修复。
第 2 轮复核确认 R1/R2 后发现 R3：官方 SDK 构造因无效凭据失败时，刚创建的原生
httpx2 客户端未关闭。新增零 HTTP 的离线回归先红后绿，最小异常清理修复签名提交
`be68504e`，没有恢复自定义 transport，错误不回显凭据。

第 3 轮复核无遗留可操作问题，停止评审，未重置轮次。原实现由独立执行者审查，
评审者的 R3 修复由其自检；协调者已核对最终差异及验证证据。最终模型定向 **63 通过**，
完整后端 **5579 passed / 1 skipped / 21 warnings**（322.44 秒，
`/tmp/tank-model-slim-review-final-backend.log`），随后顺序运行 E2E **17 场景 / 67 步通过**
（`/tmp/tank-model-slim-review-final-e2e.log`）。全部适用 lint/type/dev-log/docs/diff
检查通过；协议契约未改，protocol-sync 不适用。

签名代理已恢复，未关闭签名设置。代码与模型配置已经提交；本记录及当前设计一并关档。
历史 HTTP 实验结果保持原样，没有付费模型调用、生产默认切换或 S4 实现。LiteLLM /
LangChain 研究仍由既有 backlog 登记跟踪；本任务没有新增延期项。
