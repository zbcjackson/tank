> 日期：2026-10-23；结论状态：resolved（执行准备完成；R1/R2修复、当前96原生/192假HTTP、九项验证及两轮审查通过，真实模型未运行）。

# V/JT补充校准执行准备

承接[计划](../plans/done/jev-supplemental-calibration-execution.md)及
[上一片资格结案](jev-supplemental-calibration-qualification.md)。本片实现真实批次入口
和准入检查，只进行离线/假HTTP验证，不把新库资格当成真实模型结果。

## 范围与预算

原注册912 seed、1824条件目标、3648槽及顺序/门槛保持。V为Gemini视觉路线，
JT为Jev文字/结构先行加同一Gemini图片接管；没有增加Jev图片或Box路线。
实际接收方固定为TypeSafe `jev-1.14.0`（`https://api.typesafe.ai/v1/systemone`）
和OpenRouter `google/gemini-3.8-flash`（`https://openrouter.ai/api/v1`）。
Jev只收公开目标/结构状态/候选，视觉模型另收绑定的合成1280×720 PNG；seed、
private_acceptance及oracle不进入请求，实际线索继承相同宿主观察和历史。

沿用用户“不做限定”和预注册record-only：批次请求、token与金额无固定上限，
金额为unpriced，不等于免费，不提供当前费率/发票估算。每目标120秒、6动作、
24观察、64候选，SDK零重试；未知用量、未结束预留等仍停批。3648×120秒为
121.6小时的统计期限和，不是含清理的整批墙钟上界。正式N保持null。

## 执行冻结

首版历史完整执行摘要（不再准入当前源码）：`55ecb1740a8e00486acda520d800f75f309f8f098e5c8a184e19b18ba2d7859b`。
独立资格前缀摘要：`78d468e692299225f7b12693fb69139330356c81e24cc869e2d39a3ba895d1d1`。
两者不可交叉使用，前缀仍是固定96目标/192槽，不对模型选择结果重新抽样。

首版42份运行源由原41份已资格化宿主加新增`jev_execution.py`组成。首版宿主96原生
资格引用固定审查归档，SHA256为
`5b9a0f40c8c0dd7a7b7cf59f98d8eb009b99ab1b1a5782b6343167dba1a03930`；
该首版41源/产品/SDK/参数须逐字节保持对应64757493资格和a650e4f7候选冻结。
新入口必须单独通过同一循环的192假HTTP槽，不能借用旧入口192通过的布尔值。
源码、保存副本、原注册、模式、产品或预算漂移都在下一槽前拒绝。

完整入口先保存全部计划行。已知目标失败保留并继续；物理独立审计、安全事件、
未知效果/用量、预留、清理、源码漂移、取消/运行异常停止下一槽，并保留部分行。
开始目录不能复用或续跑。业务验收仍是原登记的值保持，不升级成强SQL写列证据。

真实用量核对密封的SDK请求/完成捕获、事件和账本；该证据不冒称HTTP线级发送。
模拟额外核对实际假传输的目标/请求SHA/图片/usage，并拒外部Python DNS/socket。
九项验证日志必须绑定当前42源且使用整数退出码0，日志字节漂移即拒绝。完整audit
再逐行重读原始证据，保存未尝试分母不等于通过资格。`check`仅输出可审阅预览，
不读取凭据或授予执行许可；实际`run`须新完整摘要授权，在准入后才读取凭据。

## 首版验证与证据保存

20项离线回归通过（88.61秒），新模块/测试pyright零诊断，后端/CLI Ruff及
web lint、TypeScript构建引用检查通过。既有chat.feature新增execution例，核对
CLI准入失败前零凭据读取。完整后端最终6642通过、1跳过、21 warnings
（1616.65秒）；本地隔离E2E24场景/95步通过（209.123秒）。使用实际本地
Sherpa、回环HTTP模型、独立DB，TTS/jobs关闭且外连记录为空；结束SIGINT关闭
自有服务并恢复原开发命令，health200、后端/前端两pane错误检查均为空。
本地配置通过不认证原远端ASR；本片没有外发该音频或模型数据。

首版新入口固定资格批次完成192/192，stop_reason为null，completed/qualified
均true。独立重读物理/HTTP/HTML/PNG/派发与SDK完成捕获，160正例槽、32负例槽、
其中64恢复槽均通过，192清理确认、关键事件/额外业务动作0、unresolved为空。
672假SDK请求/556带图请求，6720已知tokens，未知请求及预留0，外部模型请求0，
外连阻止记录为空。全批原始证据保留，不新增批次追求通过。

本批study目录的实际`du -sk`为1427776 KiB；该时文件系统可用1581281036 KiB。
这是离线资格的存储观察，不是完整真实批次的容量或时长保证，不据此估算模型费用。

保留准备、批次、SDK回执、日志准入和零尝试账本的有效RED/GREEN。另补住
假传输创建失败时漏记停因的问题：现在保留192零尝试、operational_error及
零SDK调用，不误报假HTTP上下文已建立。初始Ruff错误记录也保留，均已修复。
之前62个工件文件已保存SHA快照，不重写旧资格或旧失败。

计划提交`ed0266c2`、执行入口/测试提交`9cc8b4a4`均使用SSH签名，核验通过。
本片当前不提供真实模型质量、速度、费用或生产采用的新证据。

## 第1轮审查与必要宿主修订

问题ID与评审轮次分开计数：R1和R2均在第1轮及其必需验证处置中发现并修复；
全部验证通过后，第2轮自行复核无新增可操作问题，立即结束，未进入第3轮。R1在隔离副本中将成功标记true改为整数1、更新闭合
摘要并重建公开audit后，旧预检仍可显示ready，而评分器拒绝该回执。现要求三个
成功字段均为严格布尔，包括不使用的false字段；六项RED及26项定向GREEN保存。

首次完整重跑受沙箱loopback bind EPERM阻止，保留中止日志和确定性环境诊断。
获准非沙箱的完整重跑为6647通过、1失败、1跳过、21 warnings（1588.39秒）。
唯一失败在既有完整96路径：`cal-linkding-recovery-editor-4-prewarmed-jt`填Title后，
Save前以`dom_state/stale_reference`拒绝，未发Save且清理确认。整批原始工件保全；
历史expected/current DOMView差值未捕获，确切历史根因仍未定。

独立自然诊断未重现该失败，不作为修复或资格。固定0.65秒Retry GET控制触发
另一类`effect_unknown`，不能混作同一原因。固定仅延迟晚到`bundles.css`的控制
独立证实R2就绪缺口：新编辑URL已经出现，DOM仍为旧Retry链接却complete=true；
实际根节点仍`aria-busy=true`。修复在有界、可取消的就绪等待内处理文档声明busy
与原250ms有限动画收尾，再检查前后DOM一致；原图片/引用/revision/派发/验收门
保留。六项确定性就绪RED及50项相关守卫GREEN已保存，不能替代完整96复核。

当前宿主明确修订DOM通道与`jev_qualification.py`两源，其余39旧源必须逐字节
一致；42源仍由当前41宿主加入口组成。旧固定归档仍只导入JSON，作为provenance，
旧96不再准入已变宿主。新完整冻结显式记录两源差异与当前host摘要；必须重做
原固定96原生目标，逐行以原`audit_native_trial`重读DB/HTML/HTTP/PNG/events和
清理证明，再运行当前入口固定192假HTTP。缺失、旧host、顺序、严格类型、原始
证明或独立审计不符均拒绝，不回退旧证明。audit与预览额外显示当前host摘要、
native结果字节摘要及完整原始证明摘要。

当前study-v3完整执行摘要为
`6830e2d759bb9ee9db83b03d75f0afabb4886be0298e6994f13e802f95c2d494`，
资格前缀摘要为
`1ea452def8851be240155b401055d5bb82f18b81032171adfc202c3e6e87cb81`，
当前host摘要为
`f46fdb2764277fff39fd032e6f3573c5b23d1f960e27770b888d3d09bc63cf4c`。
当前宿主固定96原生全部通过，80正例/16负例/32恢复、96清理、零模型；独立重读
全部原始证据通过，隔离副本PNG篡改按原门拒绝。native结果字节摘要为
`42988ed2fce544919927ed6da40eb81e7e945725e44595b5663cfc5af12c3cc5`，
完整原始证明摘要为
`8f189e76c7f4e048f00e30453f01b28d9b3fb1bf00a78944f0dd9856ce8c9d30`。

当前入口仅运行一次固定192假HTTP槽：160正例/32负例/64恢复均通过、192清理，
672假SDK/556图片、6720已知tokens，未知/预留/安全事件/额外动作/外部模型均零。
当前完整后端6671通过、1跳过、21 warnings（1636.45秒），含原完整96路径全通过；
执行准入与既有资格72项定向回归通过（199.95秒）。新证据及全部失败日志分目录
保留，源码冻结后不变；九项日志绑定、原始审计、预检和两轮审查现均完成。

本地隔离E2E当前24场景/95步骤通过（226.191秒），实际本地Sherpa、回环HTTP
模型、独立DB，TTS/jobs关闭，外连记录为空；自有服务SIGINT退出0，原开发命令
恢复后`/api/health`为200，后端/前端最后50行错误均为空。先前临时编排脚本误查
`/health`得到404，启动条件超时且未运行场景；该失败与服务停止/恢复记录保留，
修正临时脚本后另开隔离目录验证，没有修改冻结源码或调用远端ASR/真实模型。

## 最终审计、审查与交付

当前九项闭合日志绑定42份运行源及13个审查文件，receipt字节SHA为
`54662f5b2e1a2266327d582feb9d3f7f141d569b4978ac597151d10e8b4cc9cd`。
完整audit结构摘要为
`a20f748bb668edca07c2599d8d36b7aee85d32fc19833d16905173985b891efe`。
audit/check/score CLI均exit0，原始复算重读当前96原生及192假HTTP证据，
保存与重建audit完全一致。父代理另行复核42源/保存副本、九日志、13审查文件、
旧62工件和四个签名提交，并重新运行只读预检，均通过；未覆盖源绑定日志。

预检`ready_for_authorization=true`、`model_execution_eligible=false`，
完整912 seed/1824条件目标/3648槽、当前host及native原始证明摘要均一致。
评分independent_audit/complete_batch/usage_reconciled为true、issues为空，
但quality_difference_lower、recovery_lower、recovery_difference_lower、
unexpected_difference_upper、speed_point五个数值门未过；阈值未改。
这些模拟数据不是模型质量、速度、费用或采用测量，正式N仍null。

审查共两轮。R1严格布尔、R2就绪缺口及不可拆的当前宿主证明接线已修复，
第2轮是修复者自行复核，无新增可操作或遗留代码问题；不称为另一执行者独立验收。
签名修复提交`c432bafe2e7e`、`4ea720d32110`均为G，原计划/入口提交
`ed0266c2`、`9cc8b4a4`亦为G；没有改签名配置或推送。
历史Save/dom_state的确切因果仍未定，已交接
[条件backlog](../backlog.md)，与旧cf402未知效果/not_sent分开保留，复发保存精确差值、
MutationObserver及HTTP/CSS/Turbo时间线，不重放、不放宽门。

完整证据见[归档](artifacts/jev-supplemental-calibration-execution-20261023.tar.xz)及
[逐文件清单](artifacts/jev-supplemental-calibration-execution-20261023-manifest.json)。
包含首版study-v1、仅准备的study-v2、当前study-v3、全部RED/中间失败/诊断、
九日志、原始96/192、评分、审查报告和父代理复核；重复字节使用标准tar硬链接，
保留每条路径及其原始字节摘要。清单使用紧凑JSON，普通文件缺省mode按清单头的33188还原；逐项回填后与原完整清单完全一致，所有原始元数据无损保留。当前有效批次位于归档`review/study-v3`，
审查交接报告为`review/final-review-report.md`；旧62工件未改。
归档SHA256为`41aec9afb80b3f60927ff53b7b9e2bb4b2d8d1973bf82972baa26581ffe74622`，共291952个成员、98774276字节；逐成员及硬链接目标的字节摘要均已校验。

后续按[主计划](../plans/active/computer-use-jev-vision.md)运行真实校准，精确完整摘要为
`6830e2d759bb9ee9db83b03d75f0afabb4886be0298e6994f13e802f95c2d494`。
接收方/数据种类和无固定批次上限的record-only预算见上文；新摘要授权后才可启动。
现存准备目录为`/private/tmp/tank-jev-execution-review-20261023/study-v3`，
对应`verification-v3.json`位于其父目录，实际命令见
[后端测试指南](../../backend/TESTING.md#supplemental-calibration-execution-admission)。
本片未执行真实run成功路径、未读取真实API凭据、未调用真实模型或远端ASR。
