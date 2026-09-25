> 状态：已完成并归档，2026-09-19；修复与回归已完成，既有 N2 benchmark 作为参考，后续按统一计划改进效果。

# Computer-use benchmark 修复

## 归档处置（2026-09-19）

用户明确本会话目标为改进效果，N2 已验证，可参考既有 benchmark。
[统一执行计划 §2.1/R](../done/computer-use-adaptation-and-grounding.md) 已读取
旧 N2 33/42、N2 SDK strict 4/36（smoke 2/6）及自研 7/42 报告。
本计划不再承担待办，不强制重跑完整三路作为新计划前置；如需同尺效果
比较，仅补必要任务。不同版本/评分保留原口径，不写成未经测试或全部成功。
下文为历史修复记录，当时的待验收描述不再产生本轮额外任务。

依据桌面的 Part A、N2 engine、N2 SDK 三组报告修复已确认的问题。
旧评分不覆盖；2026-09-18 修复时的执行环境为 Linux，后续 macOS 证据见下。

## 2026-09-19 状态核对

后续自研路径已完成 macOS 九点、Calculator 真值点击及 GPT-5.5 calc-open
三轮（严格 2/3，失败为粘贴路径表达式缺失），见
[统一验证](../../design/computer-use.md)。它们补充了真实主屏证据，但不是
Part A、旧 N2、N2 SDK 修复后同版本三路全套重跑，本计划继续 active。
自研模型适配、规划定位分离及跨应用后续见
[执行计划](../done/computer-use-adaptation-and-grounding.md)；三路比较当时与
[SDK 计划](plugin-subagents-and-n2-sdk.md) M1/M6 一起验收。下方保留当时结果。

## 实施

1. 保留 SDK GuardedComputer 方法签名；用真实 SDK 和严格签名的
   computer/假 transport 验证 GUI 调用及授权、取消检查。
2. 修复共用 Quartz 鼠标位置 API、点击 schema/bbox 与 esc 别名；
   保留 Part A batch 的截图图像，统一 batch 说明和 agent 操作流程。
3. 补 N2 engine 鼠标动作兼容和 shell 非 UTF-8 输出处理。
4. 保留已有 trial-token 隔离，完善非流式延迟、动作/轮次/有效上限
   报告；要求 GUI 的任务执行路径纳入评分，避免 shell/file 绕路得分。
5. 同步 benchmark 文档，记录验证结果和实机限制。
6. 完整验证中发现 HTTPS WebSocket 客户端断开时 Vite 向已结束的
   TLS socket 写入；关闭对应代理 tunnel，保留真正的错误日志。
7. 修复验证中发现的 fake-audio E2E：PCM fixture 不能走 Opus 链路，
   明确协商 PCM 格式，并断言新转录而非历史会话消息。

## Tests

- SDK 包装后签名与底层一致，真实 SDK 调用真实 MacOSComputer 配合假
  transport，不发生 model_action 参数错误，取消和授权检查仍生效。
- Quartz 按下/松开调用 CGEventGetLocation；两平台 bbox/schema、esc
  一致；batch 图像到达 LLM 内容并被 benchmark 归档。
- N2 鼠标动作别名、batch 失败成员与跳过成员；shell 非 UTF-8 输出。
- benchmark 非流式 TTFT 为 N/A；调用数、实际动作、轮次和限制可见；
  GUI 任务使用非 GUI 工具即使产物正确也不能通过。
- 已有 capture 隔离、过期请求、smoke 排除回归继续通过。
- 本地 HTTPS 代理连接真实假后端，客户端 FIN 与后端持续输出竞态
  不再触发 write-after-FIN 错误；完整 E2E 再次验证连接与断开。
- 浏览器 reset 断开不会被当作代理故障；ECONNREFUSED 等真正
  故障及 HTTP 错误继续可见。
- fake-audio fixture 按 16 kHz mono PCM 发送并产生新转录。

## 最终验证（完整 Verification Checklist）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check src/ tests/`（workspace 实际路径为
   `core/src/ core/tests/` 和改动的插件）
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <全部改动的 Python 文件>`；不新增
   `# type: ignore`。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
8. `cd test && pnpm test`（需要 backend/frontend）
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`

实机验收：macOS 先验证 GUI 基础动作，再同配置、同任务、同评分规则
运行三种实现。不得以 mock 测试或旧报告代替真实验收。

## 已落地的修复

- SDK GuardedComputer 使用 `functools.wraps` 保留底层签名；真实
  SDK + MacOSComputer + 假 transport 已覆盖点击、modifier、键盘、
  输入、移动和拖动。授权撤销与停止检查保持有效。
- Part A batch 返回实际 ImageBlock，benchmark 归档其截图；两平台
  ClickTool schema 对齐整数坐标、坐标数组及 bbox，补 esc 别名。
- 共用 Quartz 位置读取改为 `CGEventGetLocation`；N2 engine
  支持历史 left_mouse_down/up 动作别名，shell 非 UTF-8 内容替换
  解码且保留退出码、cwd 与 sudo 禁令。
- 保留已有 trial-token 隔离；评分版本改为 trial-token-gui-v3。
  严格 GUI 套件拒绝尝试 shell/file 工具的执行路径，smoke 单列。
  这属于评分约束，不替代工具权限或 sandbox。
- 工具调用、成功完成的 GUI 动作、模型轮次和有效调用上限分别
  报告；失败与跳过的 batch 成员不计为已完成动作。非流式 TTFT
  为 null / N/A；记录 RTT、模型配置、prompt/task/git revision。
- Vite 在浏览器 FIN 时清理 tunnel，正常 reset 断开单独处理，
  真正的代理错误仍输出。测试使用独立临时缓存，避免污染正在
  运行的 dev server。
- fake-audio E2E 明确用 16 kHz mono PCM；必须观察本次音频
  触发的 user transcript 帧，不能借历史会话转录通过。

## 本机验证结果

- SDK 签名修复、Part A 图像/参数、N2 动作/解码均先复现失败
  再修复；相关集成回归 142 项通过，后续新增计数回归与 SDK/
  runner 71 项通过。
- 后端完整 workspace：4364 passed、2 skipped；收集后新增的
  SDK 计数用例在后续定向测试中通过。
- 前端完整测试：157 passed；E2E：14 scenarios、55 steps 全通过。
- Web/CLI lint、后端 core 及改动插件 ruff、全部改动 Python
  文件 pyright、web `tsc -b --noEmit`、E2E TypeScript 检查通过。
- 文档检查和协议产物同步检查通过。
- dev server：后端末 50 行没有 error/traceback/exception；Vite
  16:06:13 重启后没有新增错误。指定末 50 行检查仍能看到修复前
  的旧断开错误，未清除历史日志。FIN/reset 真连接回归均通过，
  ANSI 彩色日志和真正代理故障的保留输出也有回归覆盖。

实施与回归分逻辑子任务提交：SDK 签名 `fddf794`、桌面输入与
截图 `6b8b598`、engine 动作/解码 `0e38c0a`、评分/指标
`af0a5fe`；完整验证发现的 dev proxy 和 E2E 问题单独提交。

本机是 Linux；真实 macOS 三路 benchmark 尚未复跑。旧三组
报告仍是历史记录，不能据本次 mock/回归结果宣称新成功率。
