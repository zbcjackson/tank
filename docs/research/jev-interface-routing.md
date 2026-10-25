> 日期：2026-10-25；结论状态：resolved（自然图片接管与正确来源导航成功；Jev原选择已正确，第1轮独立审查无发现，已归档。）

# 界面证据路由：原版重复链接的空间任务

## 结论

计划/设计已明确为逐步界面证据驱动：有可区分结构候选先Jev，所选动作不成立或控制
输出转视觉，执行前检查、执行后核验，再判断下一步。App提供能力约束，不建立名称
分类器；图标有可靠名称仍可文字，布局复杂不自动需要图片。当前代码已有主路径，
本片没有修改生产源码或默认配置。

单次真实原版sqlite-web空间导航完成：Jev选左侧work_items链接c6，但该链接与顶部
同名链接c3的语义身份重复，原守卫accepted=false，自然交图片分支；Gemini同样选c6，
宿主实际派发该动作并导航到结构页，返回completed / goal_verified。独立核验原
PNG/位置、视觉proposal、实际target_ref/回执和HTTP，确认点击的是指定左侧来源，
不是仅凭同一个最终URL判成功。全批2次SDK、1动作、零POST/DB写入，清理确认。

关键限制：Jev已选对，不能说它在本任务失败。图片请求还带位置框，几何信息本身就
能区分左右；本片没有证明像素必要、Jev无法推断位置或视觉模型更强。它证明当前
保守守卫的自然接管与实际执行成立，同时暴露结构上下文缺失可能造成额外图片调用。

## 原始界面与资格

使用已资格的原版sqlite-web 0.8.1/10固定依赖，两个公开合成记录；产品模板、CSS、
DOM未改。生产基线363a3d4c36919895ea5f79046b1b86a4a3c69977，实际Runner、
jev-action-vision及readback_tables: true；不使用ProductChannel或DB完成/进展补强。
一次任务case-01从内容页开始，明确只通过左侧work_items链接进入结构页，禁止使用
顶部面包屑或Structure页签，禁止改数据。任务/goal不包含正确候选别名/ref或坐标。

无模型检查与实际捕获均确认27完整候选。c3/c6除了ref相同：role link、label/value
work_items、祖先空、effect同为/work_items/；文字投影没有bounds/CSS区域。
实际图框以1280×720图内像素计：顶部c3约(239.75,18.30,75.52,17)，左侧c6约
(15,132.80,183.33,30.5)。候选顺序仍可见，可作为猜测线索，不宣称文字绝不可能推断。
两同名候选均不通过当前text_candidate_ids，其他25项仍可区分，故仍先调用Jev。

公开completion是目标结构页URL，初始为内容页，条件初始不成立。该URL与多个入口
共享，不能泄漏“哪一个同名链接在左侧”；独立来源验收在实测前冻结，错误入口即使
goal_verified也判失败。此任务是导航，URL核验适用于导航；未把URL当作业务保存证明。

冻结SHA为cdd84c44c4cd7225fd01f37d55da697803888e875ee2c81656e50018cf5027c1，绑定
驱动/审计器、352源/依赖文件、实际产品652文件、SDK、任务及限制。先零模型界面
检查，再一次双SDK假HTTP资格：Jev选顶部c3，经原守卫转交，图片分支按真实图框选
左侧c6，实际点击并完成导航。Python外网阻断、假凭据；不是修改真实Jev回复。
资格/审计通过才加载凭据，只启动一次真实单任务，无失败后重跑或更换策略。

## 真实调用与原始证据

- Jev jev-1.14.0：c6；输入14,964、输出287 token，SDK事件跨度854.248毫秒。
  原动作准入记录choice=candidate、accepted=false、next_route=visual_fallback。
- OpenRouter google/gemini-3.8-flash：c6；输入14,816、输出526 token，SDK跨度
  17,107.100毫秒。收到同一goal/snapshot/全部27候选、原绑定PNG及image_candidates。
  图SHA256为e6140f5c1d48cefd77b9295a70bfbd36b71e6cecf3d431152501b6d7dddb59c2。
- 视觉proposal的action_id/frame_id/image_sha与回执及TaskResult近期动作ref一致，
  对应左侧图框；实际仅一次派发，结构页HTTP GET与最终结构HTML匹配。原DB两行、
  _writes/schema及独立返回列表保持不变，所有产品请求都是GET，cleanup confirmed。

总计30,593已知token，2次SDK完整结算，无unknown或未结预留。SDK跨度之和17.961秒，
含本地调用边界开销；驱动墙钟19.921秒还含产品启动/公开采集/事后读取与清理，不作
模型速度比较。金额未定价，账面零金额不表示免费。Jev只收合成公开文字，Gemini
按原自然分支接收同状态及PNG；未调用Jev图片/Box或自由坐标定位。
限额为120秒、6动作、24观察、10万宿主已记账token、全批8次SDK、视觉输出4096、
SDK重试0；token限额非提供方请求前预留硬上界。未知效果/用量、漂移或清理失败停批。

## 准备失败与验证

两次零模型检查失败保留：首次临时检查器未将dict转GoalContract；第二次检查上下文
默认text-only，捕获门正确以model_data_denied拒绝。分别修正临时类型转换及声明
只读合成图片scope，重新冻结后资格通过；生产门/实际Runner未改，无真实模型调用。
它们不算Jev失败或收费实测。inspection-attempt-1/2保留原驱动/冻结/日志与清理。

独立脚本不导入驱动，核对原DB/HTML/HTTP、初始URL条件、同名候选无位置及共享效果、
模型捕获/事件/SDK诊断/账本、同帧27图框、proposal/ref/回执/目标来源与执行闭合。
假/真各2次SDK、1动作均通过；源字节与冻结一致。旧78工件及默认config保持不变。
仓库仅docs/变化，按docs-only检查；未重跑前轮生产单元/E2E，旧结果不计为本轮验证。

## 完成审查

第1轮独立review-and-refactor无确认可操作问题或遗留，无修复即停止。审查者独立
解包逐字节核验、目视实际PNG并对齐来源/proposal/回执、352源码/652产品/旧78工件
和config；文档122项及两提交验签通过。原始review.md已归档。协调者核对报告及完整
差异后仅闭合状态/计划链接、后续交接并加入报告，原444项证据文件保持；闭合自检
不称为新增独立审查。本片docs-only，不重跑生产单元/E2E。

## 证据与后续调整

[证据归档](artifacts/jev-interface-routing-20261025.tar.xz)包含freeze、run/audit/verify_evidence、
sources、interface无模型检查，以及fake/live全部原始模型/页面/DB/执行/清理证据。
manifest列出文件SHA；446个普通成员，归档SHA256为
f5f7c04d9991a7d3fee650ee8b92b9a7870c3b311296494b325f4c9c971af147。
新目录解包核对后可用系统
Python执行python3 verify_evidence.py离线复核；不要为复核执行run.py live。

下一优先项调整为验证低成本可信区域/几何上下文，观察能否让这种正确Jev选择获得
可核验区分依据，减少保守回退。一次正确不构成放松守卫的依据；必要的同名/区域
冲突及失效边界须先资格。之后再选择结构无法表达的图形/颜色语义样本；本片不以
继续增加文字或布局试次证明图片能力。计划见[界面路由](../plans/done/jev-interface-routing.md)。
