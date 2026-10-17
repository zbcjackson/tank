# G3 第二片：资源与能力接线验收

> 状态：2026-10-17 当前签名原生fake实机9/9通过，33次fake HTTP、0真实模型请求；合成PNG本地Vision通过。完整6119/E2E20及lint/type/docs通过，第1轮独立评审无可操作问题、无源码修复即结束。此目录只执行fake，不作为收费执行预览。

## 原生接线证据

复用s4_ax受控矩阵，签名`be21725f77c26af16e71891a318d7f47b102917ba7a6e89d9ed228dc756fcbb1`，
revision=s4-ax-bind-1。[freeze.json](freeze.json)新增固定task_binding.py源码SHA，来源漂移
在执行前拒绝；没有改写旧S4/S5签名或实验结果。

9项全部finished/passed：Calculator AXPress 3项、Quartz 3项、临时TextEdit 3项。
各项均有模型选中且派发的动作，独立AX读回完成，插件输入清理与owned应用/位置/
前台清理全部确认。33次HTTP由脚本fake回答，外部模型请求0。台账合成456tokens、
73944nano、reserved=0，不计入真实费用。真实Jev/Qwen准确率、稳定性与S5采用门槛
不由本记录判定。每case创建新Runner；同一Runner跨任务由公共套件和隔离DOM验证，
不将两个证据混为一谈。

[result.json](result.json) SHA256：
`a08ed428ae869d588c25af46af21b333961c6f58a6546341a13004c269d11644`。
本次task_binding.py SHA256：
`3e9ec44eaea37df3833e2069e9b0c860f439c440d1b994fd007a975c95b1020f`。
原始freeze/结果/上下文/调用及账本仅本地保留，不提交原始模型消息。

## 只读Vision证据

固定合成PNG调用实际macOS Vision，未截取私人桌面、未发送模型请求，mode=auxiliary_only。
14个固定case中，calibration与holdout各7/7命中，false_matches均0。此为本地OCR
可用性/边框核验，不是自动OCR回退、生产完成核验或通用识别率结论。
[vision.json](vision.json) SHA256：
`8b81ae73cc7f879baf771fd11ebe18f64810076718e42b88fc53ce7397766ecd`，
fixture manifest SHA为`48c70b9a823494652c98f30337082f25b5a4271768c59cf20f1d322118d8ce26`。

## 跨任务与统一接入

核心公共入口使用真实Runner/SDK、fake HTTP/OS：
`uv run --no-sync pytest core/tests/test_subagent.py core/tests/test_task_model.py core/tests/test_task_runtime.py core/tests/test_plugin_manifest.py core/tests/test_model_calls.py -q`。
三个保留入口（Computer Use、非GUI插件、LLMAgent）共享断言，连续两个任务的runtime/
账本/调用身份独立；旧任务拒绝再用，宿主池不被任务关闭。另测一个任务关闭时另一
任务的在飞调用正常完成，绑定错误task_id、失效授权/期限/预算/关闭状态在创建借用
视图前拒绝。此边界先红后绿；原生freeze漏固定binding源码也已先红后绿修复。

隔离Chromium三布局、含/不含用户等待共6例，每例在同一Runner连续两任务，共12任务，
新旧文档引用互斥、独立服务端保存两次、每任务关闭自己的SDK/浏览器资源、锁最终释放。
该专项6/6通过。初始公共三文件加native回归304项通过，扩展后的公共五文件255项通过。既有chat.feature新增lifecycle
入口运行公共五文件，managed Chromium场景同时执行连续任务。

能力与所有权、准入、验证命令及未接线边界见[现行清单](../../../../../docs/design/computer-use.md#g3-能力与资源接线清单2026-10-17)。
TaskResources/TaskRuntime原机制复用，不新增资源框架；原生执行审计与SDK调用级记账
分别核验，不能把model_call误称执行前持久审计。官方SDK管理的HTTP默认行为也不
包装成宿主逐包隔离。未知配置/版本在资源创建前拒绝。

G3专项均fake模型；常规全量E2E连接现有开发服务（含语音ASR），其用量不在S5实验
账本内。S5真实known+held口径保持$0.655977033，其中旧unknown预留$0.380096640
保持，不将fake合成费用当作真实费用或把该账本当作全部开发服务发票。

S5/S6和其它未验收治理项不由G3第二片自动完成。Jev图片/Box、视觉Advisor和自动
OCR生产回退不在已接线清单，跨进程持久恢复仍不支持。

## 验证记录

完整后端6119 passed/1 skipped/21 warnings（451.12s），E2E20场景/79步骤通过
（114.914s）；公共五文件255项、native组合304项、DOM6项通过。web lint/tsc-b、
backend/CLI ruff、test tsc、6个修改Python文件pyright0、后端错误查询为空、docs51/
diff通过。首次完整E2E的语音转写30s超时保留在日志；定向1/1及两次完整20/20复验
通过，未放宽断言或超时，也未宣称已定位ASR生产缺陷。日志为
`/private/tmp/tank-g3-resource-{full,e2e,e2e-final,e2e-current,voice-repro,types,common,dom}.log`。
本范围第1轮独立review-and-refactor无可操作问题、无源码修复即结束。评审者独立
复跑21项错绑/失效上下文/并行关闭/连续任务/冻结漂移测试通过；原生、Vision与源码
指纹复核一致，完整验证沿用未变代码的已通过记录。评审状态补记由评审者自检，
docs51/diff通过；原始载荷不提交。
