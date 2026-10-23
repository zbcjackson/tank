> 日期：2026-10-23；结论状态：resolved（本轮单次真实尝试停批归档结案；完整3648槽校准未完成，未知用量与底层原因未解，已交接后续。）

# V/JT补充真实校准：首批停批记录

承接[本轮计划](../plans/done/jev-supplemental-calibration-live.md)、
[执行准备](jev-supplemental-calibration-execution.md)和
[主计划](../plans/active/computer-use-jev-vision.md)。本轮确实调用了真实模型，
执行源码、注册银行、产品、SDK、门槛与顺序保持准备结案版本，不续跑或重放。

## 授权与执行范围

完整SHA `6830e2d759bb9ee9db83b03d75f0afabb4886be0298e6994f13e802f95c2d494`，
当前host `f46fdb2764277fff39fd032e6f3573c5b23d1f960e27770b888d3d09bc63cf4c`。
固定912 seed、1824条件目标、3648槽，formal_N=null。

TypeSafe `https://api.typesafe.ai/v1/systemone` / `jev-1.14.0`接收合成公开
目标、当前结构状态、候选及历史；OpenRouter `https://openrouter.ai/api/v1` /
`google/gemini-3.8-flash`另收绑定合成1280×720 PNG。没有Jev图片/Box或远端ASR，
private oracle不进入模型请求。沿用record-only，无固定批次request/token/金额上限，
金额unpriced不等于免费；未知用量/效果、预留、漂移、审计/清理失败仍停批。

初次“开始下一步”后自动审批拒绝创建进程，要求明确第三方、数据和无固定费用上限。
当时live目录/运行日志均未创建，请求为零。保留原拒绝并具体询问后，用户回复
“明确允许上述外发与预算范围，启动一次批次”；记录explicit-authorization.json。
同一原命令/入口/SHA随后获准，未更换路径绕过。3648是槽数，不是固定API请求数。
计划提交`c339cd22`使用原SSH签名配置，核验G。

## 实际结果

批次退出1，stop_reason=`unknown_usage`，completed/qualified均false。
计划3648行完整保存：尝试6、未运行3642；六行均finished且cleanup_confirmed=true。
首四槽是同一linkding正例seed的cold/prewarmed与V/JT，strict完成4；第五槽JT负例
通过，第六槽同一负例cold-V在模型调用后停止。只触及2个seed、一个产品，恢复槽0，
不得把这些观察作为完整配对模型比较或正式N依据。

14份SDK请求捕获、13份完成捕获。Jev用量已知4个调用，视觉用量已知9个调用，
另1个视觉调用未知；已知156643 tokens，reserved token/金额均0。record-only的
零预留不消除未知请求，金额仍unpriced，未知部分不能补零或记作免费。
此处统计SDK调用/捕获，不认证真实HTTP线级发送总数。

未知调用ID为`db3b8e82c7c24a2da86d6a31f21bbbff`，
槽位`supp-cal-v1-494f948d50376159bd5d-cold-v`。
公开记录为computer_use.visual，约28480.18ms后finished/status=unknown，
prompt_tokens/completion_tokens均null；calls.jsonl只有请求，没有完成响应。
控制器最终backend_error、error_type=SpendLimitExceeded，pending_effect=false。

该异常类型用于停止门，当前具体reason是unknown_usage，批次预算上限仍为空。
`model_call._Call.finish`记录未知用量，`SpendLedger.settle`设置停因，
`BenchmarkModelPolicy.check`可据任意停因抛出该类型；不能据类名断言金额超限。
现有记录没有底层SDK异常/HTTP状态或完成响应，无法确定是超时、提供方错误、
响应/用量解析还是捕获链路问题；约28.48秒耗时不构成超时证明。

## 原始复核及评分边界

只读独立脚本禁止DNS/socket及dotenv读取，逐行重读6个物理证据包
（DB/HTTP/HTML/PNG、派发/事件及清理），所得labels与保存audit-evidence完全相同；
关键事件/额外业务动作0、unresolved为空。验证全部固定顺序、closed摘要、42源、
14个唯一调用ID与账本关联，13个已知SDK完成用量与事件/账本精确一致；
唯一未知恰缺完成捕获，保留unknown而非合成零。3642行逐一证明未建目录/未调用。
旧64工件SHA保持，SDK捕获未含API认证头字段。

官方`jev_execution audit`（不加--fake）退出2：
`global ledger totals or reservations differ`，没有写live/audit.json。
该拒绝符合未知用量安全契约，不出具完整审计通过证明，也不绕过或改阈值。
另运行原scorer不传--audit，仅保存不完整批次诊断输出：
independent_audit/complete_batch/usage_reconciled均false，issues含未知请求、
未对齐trial/batch和未提供独立audit，all_gates_passed=false，执行资格false。
评分保留全部3648分母/未运行罚值，不把失败或未知剔除。其数值不用于能力/速度采用判断。

自有caffeinate/uv/python命令进程均已退出，未终止用户其他进程，没有续跑、重排、
重新调用或重放未知请求。保留实际收费调用原始证据；完整校准仍未完成。
临时只读复核脚本首次因benchmarks导入路径缺失退出，原脚本/日志保留；
只修临时脚本sys.path后通过，没有改冻结运行源码或重跑真实批次。

## 后续

先在离线故障注入中复现并补足SDK失败的安全异常/状态/完成捕获证据及原始错误传播，
保持unknown停批与账本契约；不得用再次请求猜本次原因或用量。之后如需新真实批次，
须按修订后的源码重新冻结、资格、审查与授权，不能续跑本目录。
本次未知用量仅在取得可关联的提供方usage或账单证据后对账，交接
[条件backlog](../backlog.md)。原cf402未知/not_sent及历史Save因果不据本轮改写。

当前证据目录`/private/tmp/tank-jev-live-20261023`保留授权、拒绝、启动/进度、
closed-live原始包、audit拒绝、无audit评分、独立复核及绑定输入。evidence-chain.json
固定前次准备归档SHA `41aec9afb80b3f60927ff53b7b9e2bb4b2d8d1973bf82972baa26581ffe74622`，
可在其`review/study-v3`叠加本轮closed-live还原，不改旧64工件。
两轮review-and-refactor完成：第1轮R1修正文案混淆“准备片/本轮真实调用”和
“计划/完成槽数”，签名提交63ee3159；第2轮为修复者自行复核，无新增可操作问题。
计划c339cd22、结果3073c695及修正文案提交均核验G，没有改签名配置或推送。
docs104、全diff、6物理/13known+1unknown/3642未运行、42源/九日志/64旧工件和
closed副本与原live全树3505文件/56431132字节均通过核对；这些通过不取代完整audit。

新证据见[归档](artifacts/jev-supplemental-calibration-live-20261023.tar.xz)与
[逐文件清单](artifacts/jev-supplemental-calibration-live-20261023-manifest.json)。
包括所有授权/审批记录、原始closed-live、绑定输入、audit拒绝、缺口评分、
独立复算脚本/失败与通过日志、审查报告和签名证据；前置准备包按evidence-chain还原。
归档SHA256为`9b9f6d6e5933fb5222d333f9aea9e9a2542a532e006e1517f4ea981b75101a55`，共3610成员、5056616字节，逐成员/硬链接摘要已核验。
父代理生命周期/指针文字另作docs-only核验，不覆盖raw、未知账本、原评分或九份绑定日志。
