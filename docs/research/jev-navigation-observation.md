> 日期：2026-10-22。结论状态：resolved（修复、完整资格及离线验证通过，第1轮独立审查无遗留；原ElevenLabs语音复测限制移交backlog）。

# Retry观察一致性修复

## 当前结论

固定新任务前缀在最终修复源下通过96原生和192模拟资格：原生80正例、8缺目标、
8撤权，96清理、416张PNG；模拟160正例、32负例、192清理、160次正确业务
POST，672次SDK/556次图片调用均由显式MockTransport响应，6720为模拟tokens。
两臂各80正例/16负例。这验证执行器及验收接线，不是新的真实模型效果测量。

修复分两层：基础观察先等就绪文档；产品异步读回后重新校验完整DOM视图和导航。
只等待DOMContentLoaded并不足够，第一次新冻结仍在首项Retry后失败。该失败与
191项未运行全部保留；最终新源重验同一48组seed、96目标及192顺序，没有挑换
任务或把重复测量并入原批次。旧认证失败、unknown_usage和外发来源记录保持。

## 确定性TDD与行为

受控HTTP响应先提交新文档再暂扣表单正文。旧实现会提前返回观察；修复最多
500ms等待绑定frame的DOMContentLoaded，并每次轮询检查原授权、取消、期限及
预算，超时丢弃为没有元素/事实的不可用观察。等待本身不派发或重放任何动作。
异URL导航、同URL重载、超时后的旧capture/dispatch拒绝及三种任务停止均有回归。

随后给三类真实产品投影加入“读回期间变更DOM修订、不发生导航”的受控红测试。
SQLite校准、Linkding和旧SQLite工作流三路均失败；原来只比较导航代次不足以
发现同代次内变化。新增只读`is_snapshot_current`统一重读DOM，确认当前视图及
导航与基础快照一致后才发布附加事实；不一致由原有有限观察流程重新读取。
六个DOM变化/重载组合通过。已有managed Chromium E2E的`observe_navigation`
筛选直接包含新增通用回归，不新建feature文件。

测试驱动初期的冻结context误赋值、HTTP fixture变量复用错误均修正；中断的旧
全套运行不计通过，原日志保留。当前定向DOM/多布局23项、投影6项、研究驱动/
独立进程SDK8项已通过；最终全套验证另记录实际结果。

## 冻结与独立证据

基线1ec85dae。最终执行配方digest（含运行源、应用及配方）为
`dde7db9a13a2e4f5f32cc1b9914b184fcbc76ecdad917d5d55f47430600bf901`，
资格freeze为`096472b203217a388dc5cec6f4fad001851156be0699d15b670a5fdd2ccd5026`。
36运行源中只有DOM通道和三份产品投影benchmark变化；两应用manifest、原48簇
及96份目标保持。仍是同两个原版应用/布局/ID，不能称新布局泛化实验。

独立脚本直接读取物理before/after DB、SQLite写日志及Linkding全部10张业务表，
核对单正确POST、完整返回列表、所有其它字段、schema、缺目标/撤权业务不变、
原始PNG/SDK公共目标与输入、顺序和模拟用量，不导入Controller评分函数。
首次仅就绪等待的`run`失败和最终`run-v2`成功分开存放，不覆盖此前任何归档。

## 验证与后续

完整后端6537 passed、1 skipped、21 warnings（1363.99秒），要求真实Chromium及
两原版应用fixture。web lint/tsc-b、backend/CLI ruff、五个改动Python的pyright、
运行服务错误日志及docs检查通过；协议契约未改，同步检查不适用。

E2E先因Managed Chromium子测试新增6项后仍断言82而失败；子测试本身88项全过，
已更新为88并保留失败日志。随后原配置的语音场景等待转写超时，服务记录为
ElevenLabs commit未及时返回；不能把它说成本次DOM修复导致或已修复。单独外部
语音复测被自动审批拒绝，理由为会向ElevenLabs发送测试WAV及认证信息，授权
只覆盖离线/模拟验证。该请求未执行，未通过换入口重试此外部链路。

改用已安装的本地Sherpa模型，原WAV离线识别为“你好”；临时服务在导入API模块
之前注入配置，并断言实际ASR为Sherpa、LLM为回环测试端点、独立DB、TTS/定时
任务关闭。完整相同E2E 21场景/83步骤通过（206.878秒）；Python外部connect尝试
为空。本地LLM只是SDK回复fixture，ASR是真实本地解码，不放宽转写或浏览器断言。
首次临时配置注入太晚的草案未用于测试，启动后即停止并保留勘误。原开发配置
文件未写入，临时进程关闭后原服务已恢复。此结果不认证ElevenLabs原配置链路，
其远端commit超时及未获准复测仍是验证限制，不能用本地结果覆盖。

本任务第1轮独立review-and-refactor已完成，无可操作或遗留问题，未修改运行源
和测试。审查员独立重跑28项真实Chromium导航/停止/投影/多布局（36.74秒）及
8项研究/SDK隔离测试（29.00秒），准确范围ruff及五文件pyright通过；96/192
物理审计逐字段一致。归档6836成员逐hash、全部1601张PNG解码、21实际凭据
零命中、46旧文件与基线Git blob、36运行源及与旧资格相同96目标/192顺序均通过。
源未变，全套后端和离线E2E复用已核实日志，不重复称为本轮重跑。结案文案由
审查员自检。额外扩大到整个benchmarks的Ruff扫描发现历史reports的587项格式/
导入问题，日志保留；未改冻结历史源，规定范围及本次三份benchmark另行通过。
完整检查记录在
`full-verification.json`，含两次中断的旧全套日志、失败E2E、审批拒绝及离线配置
断言/外联审计；不以资格通过替代项目必需验证，不将不同配置的结果混称。

[完整归档](artifacts/jev-navigation-observation-20261022.tar.xz)及
[逐成员manifest](artifacts/jev-navigation-observation-20261022-manifest.json)保存两个
源阶段、失败/成功资格、全部物理DB/HTTP/PNG、改动源及验证/审批/离线配置证据。
共6836成员、52694856字节，SHA256
`47cb50e9ae696951d1832bb44f5dc012df32ad7fc36cf67daa897165e0aa84cb`。
193份逐trial原版Linkding源核hash后去重；工作DB不重复打包，物理前后备份及
完整读回保留。21实际凭据值扫描零命中，旧46工件保持。manifest的真实模型输出
0限于Jev/视觉资格，不是整个任务零ASR或零外部流量声明，发布元数据已明确此
范围；归档字节及旧回执未改。

[第1轮独立审查补充归档](artifacts/jev-navigation-observation-review-20261022.tar.xz)及
[manifest](artifacts/jev-navigation-observation-review-20261022-manifest.json)保留重跑日志、
物理重算、逐成员校验脚本/结果和额外历史Ruff失败日志。17成员、22512字节，
SHA256 `07849c14bf461dcdeb3e1c16cf9e37425265ff92d2fb739ff15206cb2c9d557e`；
21实际凭据零命中，原6836成员归档未改。

原ElevenLabs配置复测已交[backlog](../backlog.md)：须明确授权测试WAV及认证
信息的外发，不将本地通过解释为远端链路通过。
正式N仍未准入，后续按[主计划](../plans/active/computer-use-jev-vision.md)衔接统计
评分器接线及独立补充校准预注册；本次修复不替换旧真实校准统计，也不构成新的
Jev/视觉速度或准确率比较。可选760+152信息目标仍由既有backlog登记承接。
