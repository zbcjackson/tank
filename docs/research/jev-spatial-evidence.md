> 日期：2026-10-25；结论状态：resolved（有界位置证据实现及单次真实Jev直通成功；完整回归通过，第1轮独立审查无发现，签名归档完成。）

# 有界位置证据：Jev直通验证

## 结论

显式DOM几何与相对位置提示已接入现有jev-action-vision。原版sqlite-web同一空间
导航目标在一次真实任务中由Jev直接完成：1次Jev、0图片模型/任务截图调用、1个正确
左侧链接点击、completed / goal_verified、0 POST/DB写入，清理confirmed。

前轮Jev已选对但重复身份守卫仍转图片；本轮给出当前位置依据及显式leftmost提示，
宿主独立验证该候选能被区分，因此接受它。它不是让Jev预测Box或执行坐标。
这只是一个受控空间声明任务的可行性；未证明任意自然语言空间理解、拒绝泛化、
模型优劣或默认采用。前后各一次且本轮增加提示/几何，不作严格同输入性能对照。

## 当前接口与边界

- browser.observe_bounds: true从拥有的主frame读取实际renderer bounding_box与视口，
  与完整一致DOMView一起冻结和重读。默认false，原生AX/子frame不继承此坐标系。
  模型geometry声明main_frame_viewport_css_pixels，bounds为[x,y,width,height]，
  原点左上，x向右/y向下；数据没有像素或新动作权限。
- 可选spatial_hint声明role、label与leftmost/rightmost/topmost/bottommost，只为
  同语义DOM候选提供额外可区分性依据。至少两个匹配候选、全部框有效且在视口内、
  一个框沿目标轴完全位于所有同组框的一侧才可额外准入。未给/不匹配提示、重叠、
  缺失/越界/无效数据或混合来源不借坐标放行重复控件；非有限数据在SDK前停止。
- 原唯一文字候选、完整集合、图片分支、权限/引用/效果与未知用量停止均保持。
  提示是目标声明，不是动作脚本或完整语义/权限校验；不自动解释任意用户文字。
  不用能力时省略hint/geometry，旧模型请求形状保持。Pydantic最低2.12，锁定2.12.5
  未升级；锁只增加直接依赖及最低版本元数据，uv lock --check --offline通过。

## 真实任务与冻结

任务基线2f88ad5edafeb93bb25bb56dfce2769d20eb8143。沿用原版sqlite-web 0.8.1与两条
合成记录，真实AgentRunner/生产通道，不带ProductChannel/DB完成补强，不改模板/CSS。
公开任务只允许点击左侧work_items进入结构页，禁止顶部同名面包屑、Structure页签
和改数据。新增公开spatial_hint为role link、label work_items、relation leftmost；
没有正确alias/ref或坐标答案。公开completion是多个入口共享的结构页URL，初始为假；
来源正确须由预冻独立审计另外确认，不用相同URL冒充正确点击来源。

冻结SHA884d7d66072c2877cb23b66b6ec695ec10a8067bc68bb82140f3697703b995ce，绑定
驱动/审计器、353项运行源/依赖文件、产品652文件、SDK与预算。全部适用检查通过后，
先零模型界面检查，再一次官方SDK假HTTP资格，最后唯一一次真实单任务，不重跑。
假资格使用发布给模型的实际几何选最左同名链接，不硬编码c6或改真实Jev输出。
当前独立驱动不运行pytest/conftest，产品指纹为真实当前环境，不用旧回归指纹夹具。

## 实测原始证据

27个候选全部保留。c3顶部链接约(239.75,18.296875,75.515625,17)，c6左侧链接约
(15,132.796875,183.328125,30.5)，role/label/value/祖先/effect相同；renderer几何
和声明给出唯一空间依据。原文字可区分25项，加空间1项；Jev仍看到全部27项。

Jev jev-1.14.0选择c6。准入accepted=true、next_route=text_candidate、
spatial_candidates=1，selected_id与Jev proposal、sent回执、近期动作id/ref一致。
实际source ref对应左侧框，结构页GET和最终结构HTML符合目标。执行只含observe两次
和dispatch一次，没有computer_use.capture或视觉SDK事件。原DB/触发器、返回列表
DOM/HTML及schema保持，_writes空；不是只用TaskResult或共享URL判断成功。

输入16,270、输出287，共16,557已知token，SDK跨度1,252.793毫秒；该跨度含本地
调用边界开销。驱动墙钟4.447秒还含服务/公开采集/独立读回及清理，不等于纯Runner。
与[前轮](jev-interface-routing.md)观察到的2模型/1图片对照，本轮为1模型/0图片，
但不据一次样本作速度排名、模型能力归因或统计采用结论。金额未定价，零账面不是免费。

外发仅TypeSafe的公开合成目标、DOM/几何、候选与历史；自然兜底的OpenRouter
google/gemini-3.8-flash声明保持但实际零调用。Jev图片/Box未使用。预算8次SDK、
Runner 120秒/6动作/24观察/10万已记账token、视觉输出4096/retry0；宿主token限额
不是提供方请求前预留硬上界。实际无unknown、未结预留或清理失败。

## TDD与完整验证

- 有效接口红灯：observe_bounds未声明时真实Chromium测试失败；spatial_hint未声明时
  准入测试失败。最小实现后逐项验证。一次fake测试缺json导入导致model_error，修复
  测试导入后通过；未据此改变生产语义或将其计作模型失败。
- DOM定向7项、准入27项通过：四向/候选顺序、默认兼容、主frame限定、重叠/缺失/
  越界/非有限/混合来源、CSSOM/滚动/视口变化无DOM修改仍拒绝旧动作，以及原版产品
  Runner一假Jev直通。既有视觉与硬停止边界由完整回归继续覆盖。
- 当前完整后端6,836 passed、1 skipped、21 warnings，2003.13秒；唯一跳过仍为
  ToolManager requires full config。前轮完整运行5,161 passed/1 skipped后在旧sqlite-web
  产品指纹失败，保留原失败日志，没有当作通过或忽略。
- E2E 24场景/95步骤全通过，4m01.315s，本地真实Sherpa/回环SDK/新隔离DB，Python
  外网尝试0。finally恢复原后端health200，后端reload错误空；前端最后50行仅检查
  一次，空即通过。临时caffeinate -is，无全局电源设置变更。
- Web lint、tsc -b --noEmit、后端/CLI ruff、全部11改动Python的pyright通过。
  文档一致性通过；内部GoalContract不改tank_protocol/生成物，protocol-sync不适用。
  verification.json将9项检查绑定到已闭合日志SHA、运行源和12项Python/TS测试源。

## 旧测试环境与指纹夹具

旧临时环境文件被清理，先从已审查归档恢复linkding 446个原文件与26固定依赖；旧
路径备份后指向恢复环境。sqlite-web新环境的依赖版本、应用/依赖代码字节与旧记录
一致，差异为路径、4个RECORD、pyvenv.cfg及两项virtualenv bootstrap。

旧校准准入还正确拒绝新增运行源。为使回归测试表达冻结协议，显式测试夹具读取经原
归档校验的源/产品指纹；两产品用例另验证真实代码字节，仅将安装记录/bootstrap作为
测试环境差异处理。当前行为仍由正常安装代码/实际产品运行。这些不是新资格或收费
准入，生产amendment allowlist、原冻结与旧未知结果均未放宽；独立测试确认当前源
无法复用旧注册，输出目录未创建。真实本片独立驱动不使用这些pytest夹具。

依赖解析器曾提出无关旧Python分支的onnxruntime等变化，已丢弃；最终lock只增加
Pydantic声明两行、版本图不变，并经uv检查。所有原79工件及默认config SHA保持。

## 独立审查

第1轮review-and-refactor检查完整基线2f88ad5e到a986cfd1，无确认可操作问题，未改
源或追加模型调用；按规则立即结束。评审者独立执行34项位置测试及2项旧准入测试，
全部通过，并安全解包核对完整检查、运行/测试源、原始实测、旧工件和配置。
原始报告review.md与检查日志随归档保存。协调者核对报告和完整diff后仅更新结案
文档/封包，并自行复核；这些收尾未再做独立审查，不算追加运行源验证。
[实现计划](../plans/done/jev-spatial-evidence.md)已结案，条件扩展交回backlog。

## 证据与后续

[证据归档](artifacts/jev-spatial-evidence-20261025.tar.xz)保存源/检查源、TDD/两轮完整
运行日志、E2E生命周期、冻结/验证收据、独立检查器及interface/fake/live完整原始
页面/模型/DB/执行/清理证据。最终归档504个普通文件（含manifest），SHA256为
c41c55cd9c62603e284a4afcdb0d0cf22ab7d2c088f0935ae94d6b4681664c40。原审查版498项
内容SHA均保持，只追加原始审查报告、两项定向日志、旧manifest及结案收据。
新目录解包核对后运行python3 verify_evidence.py离线复核；不要执行run.py live重放。

下一步由[主计划](../plans/active/computer-use-jev-vision.md)按条件选择真实界面特征
扩展；自然语言提示提取、命名区域与图形/颜色需求仍需独立资格。当前显式配置及
结构化提示可用于受控开发，不自动切默认或扩大真实用户写入。
