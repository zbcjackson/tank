> 日期：2026-10-23；结论状态：resolved（执行资格接线与两轮审查结案：新冻结原生96/模拟192及完整审计通过，后端6622与离线E2E23通过；旧失败保留，真实模型未执行）。

# 补充校准库执行资格

本片承接[预注册](jev-supplemental-calibration-registration.md)及
[执行资格计划](../plans/done/jev-supplemental-calibration-qualification.md)。
只检验新库的执行与审计接线，不运行真实模型测量。V仍为视觉路线，JT仍为
Jev文字/结构先行加同一视觉模型接管；本片未增加Jev图片或Box路线。

## 冻结和边界

注册摘要为`762859bcce4283f062cd00f7748e3f8b7f507577d19b43650ccc3f463bdf1e28`，
原912seed库、1824条件目标、3648槽顺序不变。资格前缀取各正例层rank0–3、
负例层rank0–1，共40正例/8负例seed，96目标和192槽，保留注册排程顺序。

作者阶段资格冻结为`cf402dd6334144db156b7eefc99ac6bd65b55bd9d1cd9b3d6de4e03cd200a11b`，
完整候选冻结为`81c8ceb12a4a0b46693c013d064935369c4152e7cec16e73284262daee793490`。
两者绑定41份运行源、原版产品manifest、SDK/模型参数及文件字节。只允许资格
冻结进入本轮执行；完整排程仍不是模型执行许可，formal_N保持null。

第1轮独立审查确认并最小修复两项问题：R1逐条用量检查原先仅比较账本内部
合计，现要求行预算、原始完成事件、唯一调用ID、trial归属、假传输目标/提供方/
PNG/请求SHA与原始usage逐条一致，下一槽前不符即停；R2原生清理阶段取消
原先可能被吞掉，现完成清理和保存cancelled回执后继续上抛取消，96分母保留、
后95项不启动。R1缺字段或布尔用量不补零，完整audit入口复用同一对账。

修复追加`supplemental-execution-v2`修订，明确链接原注册与作者阶段cf402资格；
新资格冻结为`647574930ed78a803b875b476dfc315ebe4410811af389957695518e5e2e0da0`。
审查中c2220610摘要只prepare，发现R2后未运行；该目录仍保留。原cf402批次及
旧主归档不改写，不能作为新运行源的资格。新冻结只补跑一次固定资格批次，结果
见下；没有追加批次或追求全绿。

相对原注册的运行源修订仅在既有产品runner增加原始派发守卫、终态HTML与清理
证明，另加注册适配、原生脚本、显式假传输及独立审计四个模块。修订明确链接
原登记，未改生产Controller、路由、门槛、模型版本或旧归档。

## 审计与停批

独立审计读取物理before/after DB/schema/全部业务表、写历史、原版终态HTML、
HTTP路径/故障重试、执行journal、派发守卫、SDK事件及绑定PNG。不复制runner
成功布尔值。撤权原始generic unknown保留，只有确证原生派发前被阻止、物理
零变更且清理完成才支持正确负例退出。缺证据留unresolved，不签发完整sidecar。

驱动逐条核对独立安全、用量/剩余预留和清理；已知目标失败继续，安全/未知效果/
未知用量/漂移/缺证据/未确认清理停批。保留全部not_run分母，批次不能续跑。
完整audit还需要与冻结源码匹配的九项验证日志回执，绑定result规范JSON摘要。

本注册继承[原校准的业务值验收](jev-calibration-route.md)：Title值改变，其他
字段/行/schema保持及正确单POST；不是“SQL仅触及title列”的强列验收。现有
`_writes`和HTTP不证明未将id/notes写回原值，unexpected_action为零也不能作此
解释。强列条件只存在于另冻的checkbox诊断，本片不追改注册或将旧value-only
结果升级为强列证据。

## 本片保留的失败

独立SDK子进程测试发现原先仅替换公开HTTP transport不能覆盖OpenAI默认客户端；
禁网测试拦截了该路径。现改为显式注入两个SDK的实际客户端传输，并拒绝外部
DNS/socket。存在未匹配账本请求时，外部模型请求数保留null，不能由计数相等补零。

写历史回归又发现额外物理写入虽导致目标失败，却未标为extra action。修复前
run-v1由作者中断：57完成、1取消、38未运行，零模型；该批不续跑、不与run-v2
合并。最小修复同时标记多写/错记录/错操作，且保持零写的已知目标失败不算
额外动作。RED/GREEN日志及全部旧结果保留，修复后使用全新run-v2冻结。

run-v2原生资格96/96通过，96清理、416次完整观察及416张PNG准入、零模型。
同冻结的假SDK批次在第8槽首个浏览器观察TimeoutError后停批，8行已尝试、184
未运行；该行无final HTML，因此独立审计保持unresolved，未签发完整sidecar。
外部模型请求为0、外部DNS/socket尝试为空、资源清理确认。期间并行E2E也有
视觉子进程失败和managed Chromium超时；不能据此认定模型失败或忽略缺证据。
该批保留且不续跑。后续空闲环境复核另用新目录、原注册前缀及同一冻结，不改变
期限/门槛/源码；两个批次不合并。

## 作者阶段验证

20项资格驱动回归及37项先前定向回归通过；写历史补充回归2项通过。
并行负载下全后端6607通过、4失败、1跳过；四项均在模型调用前停止，空闲环境
原样复测4/4通过（52.62秒），单独视觉测试156/156通过（27.85秒，接近E2E
30秒子进程上限）。保留全部红日志，完整后端、192假SDK和最终E2E改为顺序
运行，期限/门槛/源码不变。全后端顺序重跑6611通过、1跳过、21 warnings
（1959.52秒）；此前四项在完整重跑中也通过。
run-v3使用相同冻结顺序独立运行，192计划槽中152已尝试、40未运行，507个
假SDK请求/424个图片请求，5070已知tokens、零剩余预留、零外部模型请求，
无外部DNS/socket尝试；152已尝试行清理确认。该批在第152槽由独立审计
拒绝继续，stop_reason为audit_evidence_missing，completed/qualified均false。

151行可独立标注，其中两个正例目标失败：

- `supp-cal-v1-b40673df6f21a3c7fa7f-prewarmed-v`：linkding，Edit返回not_sent；
  未进入编辑器，无业务POST，目标未完成。外层current=true后通道拒绝，现有
  原始回执未细分stale_reference与not_actionable；不臆测具体拒绝原因。
- `supp-cal-v1-3d1e250762af2c0279ab-cold-jt`：Edit/Retry均sent/verified，随后
  Title fill返回not_sent；无业务POST，保留为目标失败。

第152槽`supp-cal-v1-3d1e250762af2c0279ab-prewarmed-jt`属于linkding editor恢复：
Edit为sent/verified，Retry为sent/unknown，原始HTTP显示编辑GET503后retry=1
GET200，但控制器保留effect_unknown/pending_effect。它不属于注册撤权的零效果
例外，因此审计标为unresolved，拒绝完整audit签发；不能据此把全批安全/额外动作
统计补零。早停保留全部192分母，不续跑、不替换任务，不另开批次追求全通过。

单进程环境仍复现未知效果，说明并行负载不是充分解释。后续需要诊断恢复导航
后的效果验证，并细化not_sent拒绝原因；当前记录不能认定根因已解决。
本片不提供Jev与视觉模型质量、速度或采用优势的新证据。

最终本地E2E23场景/91步通过（191.886秒），实际本地Sherpa、回环模型、隔离DB；
外部Python socket尝试为空，原开发服务已恢复健康、双pane错误检查为空。
E2E视觉156项及Managed88项的测试进程原限时30/75秒偏紧，现分别为45/120秒，
Managed步骤外层135秒，并保留失败pytest输出；不改变实验任务120秒、候选/
动作预算或任何验收门槛。完整Python验证之后仅修改了E2E运行器及文档，冻结的
41份运行源保持一致。作者阶段run-v3的完整sidecar必须拒绝该批未知效果，不能
填造该批全局零事件。

实际CLI复核：run-v2因缺final HTML、run-v3因unknown action effect均退出2，
没有生成audit.json。离线评分成功保留192计划槽、40正例/8负例seed、16恢复seed，
independent_audit/complete_batch/all_gates_passed均false；正式确认与模型执行
许可仍false。代码验证通过不等于执行资格通过。

## 第1轮修复后的唯一新资格

审查R1用RED证明行用量或完成事件/调用ID/假传输不符时旧驱动会继续全部192槽，
现逐条对账不符即停；显式零请求用量缺字段/布尔值不补零。R2用实际Chromium
复现清理阶段取消被吞掉并尝试下一目标，现清理及取消回执保存后继续上抛，
96分母保留、后95项不启动。29项资格单元及两项真实浏览器回归通过，Ruff和
改动Python的pyright通过；修复仅涉及本片新模块及测试，不改Controller/模型门槛。

最终完整后端6622通过、1跳过、21 warnings（1519.74秒）。此前完整运行有
5项浏览器失败，全部红日志和5个原始目录保留。系统记录多次412–502秒维护
休眠；仅对自有验证使用临时AC唤醒断言，不改全局设置/用户进程。全部5项
原样受控复核通过（426.04秒），随后完整重跑通过；不将所有故障根因推定休眠。

`64757493…2e0da0`冻结在全新`qualification-final-r1`仅执行一次：原生96/96
通过，96清理、416观察/PNG、零模型；假SDK192/192全部完成并独立审计通过，
672个假SDK请求/556个图片请求，6720已知tokens，零未知请求及剩余预留，
192清理、零关键事件/额外业务动作、外部模型请求0、外连阻止记录为空。
completed/qualified均true，stop_reason为null。完整候选冻结为
`a650e4f726ec0a25b4f5585f8dc241623b5e342e387b778eb608abb62596e4a5`。
全部样本/顺序/参数及原58工件不变，旧主归档保持原SHA。

最终离线E2E23场景/91步通过（200.660秒），实际本地Sherpa、回环模型、独立DB，
TTS和jobs关闭；隔离服务外连记录为空，结束关闭该自有进程并恢复原开发命令，
`/api/health`200、backend/web两pane错误检查为空。九项源绑定回执、完整audit/
评分入口和最终审查结果随独立审查补充记录归档。

这次模拟未复现旧cf402批次的not_sent/unknown，不等于旧问题根因已修复。
旧批次不重判、不合并，新结果也不构成真实模型质量/速度测量或强SQL写列证据。
formal_N保持null，model_execution_eligible保持false，真实模型调用仍未许可。

完整audit CLI输出192 trials、regressions_passed=true。评分器192计划槽无缺行，
40正例/8负例/16恢复seed，independent_audit、complete_batch、usage_reconciled
均true，issues为空。五个数值门未过：quality_difference_lower、recovery_lower、
recovery_difference_lower、unexpected_difference_upper、speed_point；
all_gates_passed=false。这些是资格前缀的置信界与模拟时钟，不能用作模型采用结论。

第2轮对修复和全部证据自检后无新增或遗留可操作问题，立即结束。协调者复核完整
差异和41源/9日志/192审计的绑定，代码/测试提交`c2c4fdb8`，SSH签名核验通过。
核验只使用现有Git公钥生成临时信任文件，未改全局配置。后续恢复后unknown与
not_sent诊断移交[条件登记](../backlog.md)，新批次未复现不代表根因解决。
审查存在一项诊断保存限制：最初R1夹具缺label的KeyError完整日志被有效RED
同名文件覆盖；有效RED、全部确认失败和实验原始数据均保留，详见审查报告。

## 工件

[原始证据归档](artifacts/jev-supplemental-calibration-qualification-20261023.tar.xz)
含三个批次、全部失败、源码快照、SDK/物理/HTML/HTTP/PNG/清理/账本证据、
九项验证及拒绝签发日志、离线评分。91610个成员，36663940字节，SHA256为
`b0cbea0cdf032928269b92063cde7f147d9e3522d4b577bb4fe224aeaadb7949`。
[逐文件清单](artifacts/jev-supplemental-calibration-qualification-20261023-manifest.json)
保存每个路径、字节SHA与原始stat；重复内容使用标准tar硬链接，所有路径和原始
字节可恢复且已逐项验证。旧58个归档文件SHA保持原样，未合并或重写旧数据。

[审查补充归档](artifacts/jev-supplemental-calibration-qualification-review-20261023.tar.xz)
保存两轮报告、R1/R2有效RED/GREEN、失败回归现场与维护休眠时间线、受控最终
全量验证、唯一新资格的全部原始证据、完整audit/评分输出、协调者绑定复核及
代码签名证明。101366成员、44372560字节，SHA256为
`5b9a0f40c8c0dd7a7b7cf59f98d8eb009b99ab1b1a5782b6343167dba1a03930`。
[补充逐文件清单](artifacts/jev-supplemental-calibration-qualification-review-20261023-manifest.json)
记录所有成员SHA及stat，77457个重复内容成员使用标准tar硬链接，全部载荷与
链接目标已验证。此前60个工件文件的SHA全部不变，原主归档没有重写。

归档中的文档快照为审查交接时状态；随后仅由协调者补记归档引用、签名元数据、
条件登记与计划生命周期，并另行完成文档检查，未覆盖九项回执绑定的日志。
当前两份归档均不提供真实模型执行许可。
