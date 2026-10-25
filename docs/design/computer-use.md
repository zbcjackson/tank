# Computer use：macOS 坐标链与验证结论

更新：2026-10-25（逐步界面证据驱动的Jev优先/视觉接管；原始DOM两项正例及单项控制退出已验证，默认不变）。本文汇总自研
`computer_use` 的现行行为；旧N2及其官方SDK、独立DesktopExecutor已移除。
历史报告中的 N2 数据仅作为当时的实验记录。

## 界面证据驱动的逐步路由

显式实验配置`jev-action-vision`以当前任务、界面证据和待选动作决定路线，不建立
App名称白名单或事先为每类任务指定模型。可用证据包括控件role、可访问名称、文字、
值、命名祖先/行上下文及可核验效果；图标即使无可见文字，有可靠AX/ARIA名称仍可
先走文字。布局复杂不自动要求图片；纯图形/颜色/相对位置及无语义图标只有截图提供
所需依据时，图片更有价值。当前文字DOM投影不含控件位置或CSS视觉属性。

宿主先检查完整/新鲜观察、授权、候选范围和用户参数。存在文字可区分候选时，向Jev
提供全部候选；只有其所选动作具有唯一语义身份、非空且非通用标签，才接受该选择。
返回控制选项或选择未通过该检查，沿原绑定取图交给显式视觉profile；全无可区分
候选时直接读图。此检查证明可区分性，不证明动作正确，不仅凭confidence决定执行。
执行前仍查引用/权限/场景，执行后核验效果；下一步重新观察并判断，可返回Jev。

“先试”指请求选择并检查，再决定是否执行。缺用户信息须询问/停止；未知用量、
未知操作效果、失效引用、撤权及预算/期限等沿既有停止或只读核查，不通过换模型
重做来绕过。视觉服务可替换；当前图片分支只在已有合法候选中选择，不生成任意
坐标动作。无可执行DOM/AX的canvas仍需定位/执行能力，不因配置兜底自动获得。

原始生产DOM[两项正例](../research/jev-runtime-smoke.md)共7次Jev、零图片并完成；
[中性命名反例](../research/jev-target-boundary.md)为Jev需上下文→Gemini none→停止，
零动作/写入。这是有限路径证据，未确认拒绝泛化、图片必要性或默认采用。按界面
特征选择下一验证样本见[进行中计划](../plans/active/jev-interface-routing.md)；计划内容
与待执行项不放在本节。原`jev-vision`及其他选择器各自准入逻辑保持。

## 公开结果与图片能力

可信browser配置`readback_tables: true`在普通DOM通道提供有界简单表格结果事实。
`dom_table_fact(url, columns, rows)`生成现有GoalContract的完整期望事实，值绑定
实际frame URL、唯一表头和全部可见命名列/正文行；submit效果、进展与完成沿原
等值核验，不读取数据库。条件应来自公开目标及需保护的公开观察值。
发出事实前先离开文档再GET原URL，重新执行原完整/就绪/一致读，防止POST重放或
把临时编辑值当保存；每观察最多一次GET，原期限和引用失效规则保持。
表单存在启用的可编辑文本字段（含form属性关联）时不刷新/不供事实；仅HTTP(S)
frame文档提供此读回，srcdoc等保留普通观察且不刷新。重复签名、合并/嵌套、
隐藏/忙碌/可编辑表头或数据（含继承contenteditable）或超限数据
不产生部分结果。上限32命名列、64行、128字符键/4096字符值，单元格压缩显示空白。
该事实仅证明声明页的DOM结果，不证明隐藏页/列或数据库持久性。默认false，保留
原始观测及其他选择器；Jev/视觉profile不变。配置/示例见
[插件说明](../../backend/plugins/agent-computer-use/README.md#explicit-table-result-readback)。

本次后续离线切片将SDK固定为0.7.5，增加显式Jev profile `images: true`准入及
原任务的图片Choice/Box证据接口。普通文本接口仍拒绝图片。准入/capture包含
参数JSON、图片引用/实验头与独立文件字节；限额不冒称HTTP线级大小。插件
`JevImageProbe`只读，规范化方向/尺寸/补边、保留原帧逆映射并在响应后复核帧；
Box同请求另问none/one/several，无任何自动动作派发。新合成开发任务规格36项/
60阶段，输入与标签分离；两轮真实开发调用已完成，但只有两个合成布局，不构成
真实应用完成质量或GUI恢复收益证据。详见[准备协议](../../backend/benchmarks/computer_use/fixtures/jev-image-dev/README.md)。

新增显式`selector: jev-image`，原生/浏览器正向PNG经尺寸/补边规范化后，将候选
bounds同步映射到图内像素，直接由Jev图片Choice选择原动作；不创造坐标动作。
先在最多三次捕获中确认两帧一致，输入前仍由原执行器核验窗口、场景及引用。
可选`advisor: jev-image`只作有限候选复核，保留四次上限且不生成事实/输入/焦点。
Qwen专项后置，视觉服务保持可替换；Box只读校准。真实应用先用新拥有的系统
计算器窗口，独立AX读回和实际按钮路径核验；
[配方](../../backend/benchmarks/computer_use/fixtures/jev-image-native/README.md)不使用手工页面。
真实Jev小样本已完成两个算式，独立AX值、完整按钮路径与清理均通过；只读Box
中心2/2命中、未派发动作。完整AX仍在，不能据此认定图片增量或开放规划能力。
详见[真实计算器记录](../research/jev-image-native-pilot.md)。

绑定原生窗口的图片路径与输入前场景复查获取所选显示器的原始backing像素，
Observation先按逻辑窗口映射裁剪原图，再缩放输出，避免整屏缩小过滤器混入
窗口外像素。scene_sha256覆盖原始裁剪像素；screen_size/crop和图内点逆映射
仍使用逻辑坐标与显示器原点。普通截图默认的逻辑PNG路径不变，未采用离屏
窗口捕获或像素容差，原进程/窗口/AX/输入门继续生效。原生AX仍仅支持主屏；
通用帧的副屏映射回归不代表新增AX副屏执行能力。诊断依据见
[新鲜度记录](../research/jev-frame-freshness-diagnostics.md)。
原生新鲜度拒绝另发只读stage/observation事件，区分绑定、窗口、像素与AX复扫；
观察者失败不影响原输入门或stale_reference结果语义。

显式`selector: jev-vision`与extension的`visual-model`声明接线一条有限候选图片路径。
完整结构先Jev文本，合法弃权后用绑定窗口/主frame PNG做单步选择；缺标签或语义
身份重复时直接读图。原TaskRuntime保留授权、期限、观察额度、账本、动作回执与
效果读回；下一步重新评估结构准入，重复语义状态只允许一次额外图片恢复。原生
复用M2 Observation映射和窗口/场景校验；Chromium在trial前检查图片，trial后检查
DOM身份与导航（trial可能改变hover像素）。错误、未知用量、撤权和限制保持硬停止。
Chromium模型图与复查图统一使用`visual_png`：通过constructable stylesheet隐藏
原生输入光标，不改DOM属性或修订号；仍按原PNG哈希逐字节核对，其他画面变化
不作容差。输入值、焦点、节点身份、导航和动作准入检查保持；当前动作仅click/fill。
截图前最多250ms等Web Animations结束，不禁用动画；继续动态则拒绝捕获。仅排除
空内容、无list marker、computed visibility:hidden的::before/::after CSS动画，
且报告关键帧与全部可读CSS定义均只含transform/opacity。CSS扫描包含import/
嵌套/adopted sheet，最多4096规则；未知/自定义属性、不可读来源、普通元素及
程序动画仍保守纳入。后续派发仍比较精确PNG，CSSOM无DOM修订的可见性/像素
变化也会拒绝。观察前最多500ms等待绑定frame的DOMContentLoaded、文档根声明的
`aria-busy`清除及上述相同的250ms有限动画收尾，同时检查原任务的撤权、取消、
期限及预算；超时或仍在运动时丢弃为无元素/事实的不可用快照，失效旧引用。
就绪后须前后DOMView一致才冻结；节点、值、焦点、修订或导航代次变化均丢弃。等待不
重放点击或POST；即便URL相同，重载后的新文档也不能继承旧节点引用。
DOM新鲜度拒绝发`computer_use_freshness`阶段/观察/动作关联及必要图片hash，
普通事件不含PNG或正文；即时图片仅由显式诊断配方保留。
HTML控件的内容命名和非输入值读取浏览器innerText（无该属性的节点保留原
textContent回退），避免隐藏后代/格式空白放大聚合内容；输入/textarea原值、
可见预格式换行及真实长内容限制保持。只读观察若跨文档导航提交，丢弃结果为
无元素/事实的不可用快照并失效旧绑定，由原有有限只读协调重新观察；派发前
导航/精确PNG/节点身份拒绝不改，不重放动作。真实产品附加业务投影也必须
与基础快照处于同一导航代次；异步读回完成后还须重读DOM，节点、值及修订均
与基础视图一致才发布，避免同代次内的页面切换混合。新校准配方显式使用既有64候选接口，两臂相同、
保留整组候选且超限拒绝；浏览器工厂默认32和原生通道64均未更改。
可见值替代HTML格式空白后，原本仅靠不同缩进被误认为可区分的重复控件会被
既有歧义门转到图片；不保留不可见空白来抬高Jev占比。校准需记录实际路由，
不能沿用旧表示下的文字/图片调用比例。新配方的[96项真实校准](../research/jev-calibration-route.md)
两臂各40/40正例、8/8负例；JT图片111对V168，58次Jev文字、1次同绑定图片
接管。整体JT封顶均时较低，但sqlite-web没有速度收益，不能外推为各应用均更快
或Jev视觉更强；24seed只作后续正式N设计，当前未切换默认。
原版linkding1.47.0的[四项开发对照](../research/jev-linkding-route.md)完成：V/JT
各2/2，完整耗时均值34.614/12.047秒，图片请求6/2。JT列表因重复语义直接读图，
编辑页使用Jev文字；本批没有弃权后接管，也未测试Jev图片/Box。两臂共享额外
真实DB/DOM业务事实，全部书签字段/schema、正确编辑/单POST/返回列表独立核验。
仅两个开发任务，不作普遍排名或采用确认；原产品源/样式未改。
文本TaskModel及普通Jev choose不接收图片；显式视觉profile或image-enabled Jev
可接收截图，调用方数据范围仍可收窄。尚无合法候选的canvas/Box动作及真实系统收益未验证，生产
默认未变。详见[插件边界](../../backend/plugins/agent-computer-use/README.md#bounded-generative-selection-and-jev-fallback-s3)
与[进行中计划](../plans/active/computer-use-jev-vision.md)。旧J/F文本回退和历史测量
仍按原配置解释，不追改strict/费用/unknown预留。
逐轮原始证据、历史测试数量和异常记录见
[macOS 调研](../research/macos-coordinate-chain.md)，复现入口见
[benchmark 文档](../../backend/benchmarks/README.md)。
适配与定位专项（M0–M8）已于 2026-09-25 关档，[M8 收口报告](../../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)
给出采用决定：**保留生产基线（A：一体规划定位 + legacy 归一化坐标，
qwen3.7-flash）**；M2 image 坐标、M4 分离、M5 一体适配、M7 AX 均为显式
opt-in，默认全程未切换。条件性后续工作见 [backlog](../backlog.md)。

## 当前结论

静态主屏的本地尺寸转换已经过 pytest、真实九点校准和 Calculator 真值点击
验证。仍出现的大偏移已在固定合成图的模型原始响应中复现，发生在鼠标执行前。
因此不能用一个全局 Retina/缩放补偿系数解决，也不能将所有失败归为 macOS
输入投递问题。最直接的瓶颈是模型在当前定位任务与输出协议上的可靠性。

这只定位到服务输出边界，不能进一步断言是提供方平台故障、模型权重、视觉
识别、空间表达或内部预处理中的某一个原因。同一提供方换模型会改善表现；
原生 API 也可复现偏移；合法 JSON、严格 schema 和充足预算均不保证点中目标。
GPT-5.5 在独立合成布局上最好；本次真实 calc-open 严格评分 2/3，已验证
鼠标批量点击与一次截图反馈后的恢复，但不是全套 GUI 可靠率结论。

模型差异不排除宿主设计缺陷：M1 已修复提示职责冲突与输入语义；M2
新增显式 image/frame 接口由宿主还原 crop，默认 legacy 路径仍由模型换算。[外部实现对照](../research/computer-use-implementation-comparison.md)
梳理了 Anthropic、UI-TARS、Cua、Peekaboo、OmniParser、OpenAI 和 browser-use，
建议先修已确认问题，再分别测试宿主坐标还原、AX 元素寻址和反馈检查。
M3–M7 已分别完成模型适配、四组因果对照、真实闭环/长历史/停止验收与
AX 独立分支：适配一体+宿主还原（B-combined）在 calc-open 上是最差臂且
耗 ~2.4× token；拆分架构（C/D）在 calc-open 上与生产基线持平（p=0.43）
但在 13 任务宽集上 A 10/36 > C 5/36 且 C 耗 1.7–2× token；AX 机制闭环成立
但选择模型精度是瓶颈，条件性暂缓。统一内部坐标协议与保留各模型外部
协议并存；单位应匹配模型原生习惯（qwen3.8-max 在 pixels 契约下系统性
误发归一化值），不能靠换协议普适修复。全部结论见各节及
[M8 收口报告](../../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)。

## S5 当前采用结论（2026-10-18）

当前配置不采用Jev＋同候选文本回退策略作为生产新默认；H/J保留显式实验，A维持现有默认/参照。
这是依据有限场景证据作出的发布取舍，不证明A可靠或Jev普遍劣于视觉。所测DOM两臂
均24/24 accepted，J省费约47%但慢约44%；原生pilot仅描述性；后续长任务/完整context门未过，
没有稳定净收益的采用证据。两个150项批次保持各6finished/144not_run及确认未完成，
不因研究结案补判H1–H4，不追加同配置试验，也不改变原评分、unknown预留或预算。

G1–G3按现行可信适配器范围具备治理验收证据，不代替模型质量。Jev图片/Box、替代
驱动和条件性观察优化仍未启用。图片/Box已按用户追加要求纳入
[混合计划](../plans/active/computer-use-jev-vision.md)，其余条件项保留在[backlog](../backlog.md)。
当前具体失败链未建立缺图原因，但这不阻止新视觉场景的能力试验；计划区分版本、
图片、Box和路由增量，尚未升级现行SDK/模型或开启图片。
完整证据和未完成试验处置见[主计划S5正式处置](../plans/done/computer-use-strategy-ladder.md)。
S6已交付现行可信API 3的已验收治理与显式能力范围，计划完成评审并归档至done/；
原确认仍incomplete，后续扩展保持backlog触发条件，生产配置没有变更。

**用户目标复审**：`jev-fallback`与Advisor均只接收文本，结构不足时没有切到默认A
或其它图片路径。因此上述不采用结论仅限已测配置，不能否定「适用时用Jev、视觉
兜底并可返回」的混合策略；默认A保留也不是其效果已改善的证据。DOM的24/24各含
18个完成＋6个合理退出，长任务34/40共同入口失败，不能用于计算Jev总体操作准确率。
当前链路、评估缺口及待验证提案见[复审报告](../research/computer-use-hybrid-review.md)；
后续最小接线/新对照见[混合计划](../plans/active/computer-use-jev-vision.md)。提案尚未实现，
Jev直接图片/Box仍按原backlog独立处理。

## 截图到点击：默认 legacy 转换

1. Quartz 枚举活跃显示器拓扑（`CGGetActiveDisplayList`，按 id 排序；主屏恒在
   全局原点 (0,0)，负坐标原点合法）。默认 `screencapture -m` 仅截主屏；显式
   `display=<CGDirectDisplayID>` 时用该屏全局 bounds 的 `screencapture -R` 矩形
   精确截取（`-D` 是无文档排序的 1-based 序号，不可用于身份选择；两者均在
   本机双屏实测：主屏 1920×1080@2x，副屏 1080×1920@2x @ (1920,-602)）。
2. Retina 图片通过 `sips --resampleWidth` 缩到所选屏逻辑宽度。Pillow 检查实际宽高
   与该屏逻辑尺寸均一致；缩放失败或命令成功但尺寸错误都返回错误。
3. 完整 PNG 尺寸按屏更新截图缓存（`display_id → (w, h, 全局原点)`），另记
   最近截图的屏。坐标动作缺省指向该屏，未传 `display` 且从未截图时仍是主屏
   1920×1080 默认值与 (0,0) 原点——单屏行为与历史字节级一致。显式传未知
   `display` 时现场读拓扑解析（等价），不存在则错误并列出活跃屏，零输入。
4. 可选 `region=[left,top,right,bottom]` 使用所选屏 0–1000：转换为像素裁剪，
   最多放大 3 倍；全屏缓存保持不变。例：右下半屏裁为 960×540，再放大
   2 倍成 1920×1080。生产路径由模型按工具提示恢复全屏归一化坐标：
   `full_x = left + local_x * (right-left)/1000`，y 同理；宿主不自动恢复。
5. PNG → Base64 data URL → `ImageBlock(detail=auto)` → 工具结果序列化
   → 后续 user 消息的 `image_url` → OpenAI SDK HTTP JSON。本地此后没有
   再次缩图。tool 文本占位和前端显示尺寸不是模型图片输入。
6. SDK 累积 SSE 工具参数，ToolManager 解析并分派。生产支持 x/y、数字字符串、
   bbox 数组中心，display/display2 id 同样容忍数字字符串（2026-09-26 实跑
   发现）；macOS 拒绝非有限数、越界及非法结构，不再把越界值静默夹紧。
   数字合法无法区分模型想表达的是 pixels 还是 normalized。
7. ClickTool 逐轴计算 `min(W-1, int(nx*W/1000))` 后**加目标屏全局原点**；
   executor 使用 `round(nx*(W-1)/1000)`（仅主屏，见 executor 一节）。终点
   在屏幕内，两条路径的内部取整可相差约 1 point。实机验证：`CGEventPost`
   到副屏全局坐标逐点精确（含负 y 原点）。
8. points 直接进入 Quartz mouse down/up 和 `CGEventPost`，不再乘 Retina
   倍率。成功投递不等于命中控件或完成业务，必须再观察实际结果。

多屏截图结果仅在活跃屏 >1 时追加 DISPLAYS 段（各屏 id、主屏标记、尺寸、
布局与缺省规则）；单屏文案不变，保证 benchmark 前后可比。截图后拔掉显示器
会让缓存原点过期，动作会落在旧坐标——与旧单屏分辨率变化同类，重截图即恢复。

源代码：[macOS 工具](../../backend/core/src/tank_backend/tools/computer_use_macos.py)、
[共用转换](../../backend/core/src/tank_backend/tools/computer_use_common.py)、
[LLM 消息链](../../backend/core/src/tank_backend/llm/llm.py)。

## 显式 image/frame 接口（M2）

macOS 工具组提供兼容默认 legacy 的可选 `coordinate_space="image"`。截图
返回不可变 Observation：会话/frame、屏幕/窗口身份、实际图片尺寸、整数裁剪
矩形、显示几何及 PNG hash。`region` 为所选屏幕或窗口内的 0–1000 裁剪范围；
可选 `window_id` 必须是完整位于**恰好一台活跃显示器**内的可见 Quartz 窗口
（跨屏/出界窗口拒绝，与旧“完整在主屏”同级严格度）；截图捕获包含该窗口的
显示器，也可显式传 `display` 指定屏（与窗口所在屏冲突时报错）。截图不含光标。

点击、框中心、移动、定位滚动与拖拽使用同一 `frame_id` 和图片内零起点像素
坐标；允许有限小数，拒绝字符串、布尔值、越界和倒置框。框中心先计算，再按
实际 `crop` 与 `image_size` 逐轴还原，**再加绑定屏的全局原点**（`display_geometry[1:3]`，
主屏为 (0,0)）；最终在 Quartz 边界四舍五入（half up），
末端限制为裁剪区域最后一个有效源像素。Retina 不重复相乘；不使用全局默认尺寸。
Image 模式的坐标动作拒绝显式 `display`——frame 已固定屏幕。

ToolManager 注入会话身份。缺失/旧/跨会话 frame、窗口不匹配或几何失效时
零输入并要求重观察。每次坐标动作前检查显示/窗口几何，不额外截屏或比较像素；
batch 共享 frame，逐步检查，首错即停并返回新截图。
键盘、文本和不带坐标的滚动不引入虚构参考系。

像素哈希仅保留为观察证据，不是动作准入条件。允许动画、光标闪烁和无关
应用变化；同一几何内的按钮移动或弹窗也不会由像素校验拦截，规划器须根据
反馈截图判断效果并在必要时重新观察。几何检查也无法排除检查到投递之间的变化。
多显示器拓扑、任意屏窗口绑定与跨屏坐标已在 2026-09-26 支持（见上文 legacy
节与[多显示器计划](../plans/done/computer-use-multi-display.md)）；模型效果、
跨应用和完整停止验收不在通过结论内。旧 normalized 调用保持既有语义。AX 分支接收绑定屏几何但副屏行为未验收（M7 暂缓不变）。

[M2 报告](../../backend/benchmarks/computer_use/reports/20260920-m2-observation/README.md)
保留初次全屏场景变化拒绝及窗口九点 9/9、每轴 0 point 的实机证据。
[Observation](../../backend/core/src/tank_backend/tools/computer_observation.py) 与
[frame 工具适配](../../backend/core/src/tank_backend/tools/computer_frame.py)
由实际 SDK HTTP/ToolManager/Quartz 回归覆盖；未进行本批模型截图请求。

## 共用定位适配器（M3）

[GroundingAdapter](../../backend/core/src/tank_backend/tools/computer_grounding.py)
位于 computer-use 工具层，按显式协议构建图片、提示、schema 并解析响应。
它与 probe 共用代码，不按型号建立继承树，也不根据坐标数值猜测单位。
模型、端点、temperature、输出预算及 thinking/provider 参数继续由已有
`LLMProfile` 提供；没有新增默认 profile 或修改当前模型。

- `point` 为 0–1000 点，`pixels` 为图片内整数点，`bbox` 为 0–1000 框；
  统一返回不可变 `ImageLocation`。点为图片内像素；框保留图片内边界，最大
  边界可等于图片宽/高，执行取单独提供的中心点。旧端点 1000 的点仍映射到
  最后一个有效像素。裁剪还原与 Quartz 取整继续由 M2 Observation 完成。
- 兼容旧 `found` schema（默认）：`false` 同时表示缺失或不确定，所以内部
  保守记为 `ambiguous`，不能宣称已证明目标不存在。显式 `status_field=True`
  使用 `found/not_found/ambiguous`，非 found 结果没有点/框。nullable/整数
  哨兵规则与旧探针一致；模型可用性和 strict 效果仍需独立实验。
- 2026-09-22 起，旧 found 提示也明确要求唯一、无歧义匹配；多个匹配时
  必须 found=false 并使用既定零/null 哨兵。schema、解析器和 LLM profile
  不变；提示约束不能代替模型效果验证或执行前检查。
- `request(llm, observation, png, target)` 先核验 PNG hash、格式和实际尺寸，
  再调用通用 `LLM.complete_response()`，只上传当前图与目标，不发送聊天历史。
  `build_request()` 的 previous/marked 等选项只保留给离线 probe 对照；
  `request()` 不开放这些历史/标记参数。API 仅返回位置声明，不执行 `click`。
- LLM 层新增的完整响应接口保留工具参数、结束原因、实际模型与 usage，
  不理解坐标。适配器关闭 SDK/封装层重试，取消直接传播。调用者先持有完整
  响应、记录用量，再 `parse_response()`；解析失败不会丢掉原响应及费用证据。
- 完整响应解析拒绝 length、content_filter、refusal、多 choice、缺失/多工具、
  错工具及非法坐标。数组、字符串、重复字段、越界、倒置框不自动修补。
  矩阵 probe 已使用同一检查，完整 JSON 也不能覆盖 length 失败。

这是可调用的生产协议/LLM 接口；M4 的可选分离模式已把结果绑定当前任务/frame，
接入共享预算、截止时间、重新观察、审批和动作派发。默认一体模式仍走原路径。
适配器的图片一致性检查不代表
屏幕仍然新鲜，不能替代 M2 执行前校验；调用者也不得自行相信模型 frame_id。

十份 M3 真实响应通过实际 SDK 的本地 HTTP 回放，与历史请求逐字段、图片 hash
一致；三份数组响应仍拒绝，合法错点仍是错点。没有新增付费调用、真实截图
外发或 holdout 结果，也未验证 strict/native bbox 模型效果。

M3 随后用同一生产调用路径完成六次 strict 配对预检：Qwen3.8 Flash 即使
strict=true 仍返回数组；Max 两次命中与历史失败并存；DeepSeek 只有一对
control 失败/strict 命中，不能认定收益。见
[strict 报告](../../backend/benchmarks/computer_use/reports/20260920-m3-strict/README.md)。
16 次预检额度用完；独立调参筛选首批 40 次已完成。
[点/框对照](../../backend/benchmarks/computer_use/reports/20260920-m3-screening-protocol/README.md)
使用四个开发布局：Max bbox 与 GPT 两协议均 4/4 命中，Flash 仍有数组，
DeepSeek bbox 仅 1/4。合法率与命中率分别记录；四布局不能作为采用结论，
自定义函数 bbox 不代表原生接口验收。生产默认与适配器未因此改变。
后续 [thinking 批](../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking/README.md)
在第七次 DeepSeek 请求遇到 402 余额不足后停止，只完成一个布局的三对 Qwen；
Flash on 命中而另两组 on 失误，不能作通用收益结论。缺失用量保持 unknown，
[余额恢复后续跑](../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking-resume/README.md)
已补齐 32 个设置，保留旧 402 并为其未知用量预留完整估算额度。四布局 off/on
命中为：Qwen3.7 3/4、0/4；Flash 0/4、4/4；Max 4/4、3/4；DeepSeek
完成响应 2/4、3/4（含旧 402 时 off 为 2/5）。Flash on 是后续候选，
未因此切换生产配置；真实后端日志已重新通过。
[图像处理对照](../../backend/benchmarks/computer_use/reports/20260921-m3-screening-image/README.md)
在相同 2 倍放大合成图上分别比较 Qwen 高分辨率开关和 DeepSeek auto/low：
32 次格式均合法但仅 24 次命中，未观察到普遍收益。Qwen 图像 token 增加，
DeepSeek low 的总用量反而增加；保留默认设置，不猜测服务端坐标补偿。

[显式 status 筛选](../../backend/benchmarks/computer_use/reports/20260921-m3-screening-status/README.md)
在三个新开发布局的存在/缺失/同名歧义图片上完成 36 次调用；格式全部合法，
但 24 个负例中 5 次仍给出 found 坐标（Qwen3.7 三次、Flash/Max 各一次）。
正例命中 8/12；DeepSeek 六个负例未误报，但不能据此宣称可靠拒绝率。
显式状态提供可表达的结果类别，不验证视觉真值；生产默认及执行保护未改变。

[holdout 冻结](../../backend/benchmarks/computer_use/reports/20260921-m3-holdout-freeze/README.md)
保留 Qwen3.7 point 基线、Max bbox 与 GPT point，使用已实测旧 found schema
和 8000 输出上限。64 布局各重复两次的 384 份请求先经离线核对，
实测结果见下。缺失与同名拒绝按真值分层，旧 false 不区分二者的语义状态。

[冻结 holdout 实测](../../backend/benchmarks/computer_use/reports/20260921-m3-holdout/README.md)
已完成 384 次：Qwen3.7/Max/GPT 正例为 57/96、96/96、96/96，缺失拒绝
均 16/16，同名歧义拒绝均 0/16；全部配置未通过完整门槛。旧提示未明确
要求多匹配拒绝，不能把失败单独归为视觉识别能力。默认不变；该 holdout
已用于评估，后续调参不得继续用它宣称独立验收。
冻结输入执行器已支持真实 SDK、逐请求预算和原始响应保留；独立 mask 评分
在执行结束后读取真值。这是 benchmark 能力，与 M4 的可选 AgentRunner locate 分开验收。

[唯一匹配开发检查](../../backend/benchmarks/computer_use/reports/20260922-m3-unique-match/README.md)
使用明确的旧 found 提示，在一个既有同名开发图上 Max/GPT 拒绝，Qwen3.7
仍误报。三次单样本 smoke 不证明可靠性或正例无退化；静态首轮 544 次额度
已用完，默认模型未切换。旧 holdout freeze 因源码改变继续拒绝重发，历史
报告保持原样；当前契约的执行器测试使用临时 freeze，不覆盖历史证据。

2026-09-22 [M3 证据与范围收尾](../../backend/benchmarks/computer_use/reports/20260922-m3-closeout/README.md)
已完成：实现和首轮实验具备可追溯证据，候选仍未通过完整采用门槛。
未测原生协议/专用模型及追加静态复验条件登记在 [backlog](../backlog.md)；
M4 离线集成已验收；M5–M8 对照和真实任务验收继续执行，不因 M3 收尾视为完成。

## 已修复与测试覆盖

- 主屏截取、Retina 缩放失败处理、缩放后宽高检查、边界点不超屏，以及非法
  坐标拒绝已有回归；鼠标位置读取使用正确的 `CGEventGetLocation`。
- 真实 Pillow / Base64 / 工具 / 序列化链配合 mock OS：覆盖 1x/1.5x/2x、
  非正方形和非整千尺寸；核对目标像素与最终 Quartz 参数。
- crop、2x/3x 放大、小区域倍率限制、全屏缓存保持、局部到全屏映射均有测试。
  正确 mock 模型输出只能验证宿主链，不能证明真实模型能自行恢复 crop 坐标。
- 实际 AsyncOpenAI + HTTP MockTransport 验证上传字节、尺寸、图片顺序、
  user/tool 消息，按字符碎片回放 SSE，再经 ToolManager 到 ClickTool；包含
  全图和 crop。batch 返回的图像也进入模型消息和 benchmark 归档。
- 真实服务端畸形 SSE 成为 fixture：SDK 与本地累积结果相同，非法 JSON
  被工具层拒绝且不注入事件；真实模型坐标回放验证本地落点，不把错点修正成真值。
- 新探针覆盖独立 point/pixel/bbox、严格整数/范围/重复字段/边框顺序、缺失
  目标、host bbox 中心/crop 还原、圆角按钮 mask 评分、CLI 到 HTTP 的思考与
  预算参数、length 用量保留。协议构建/解析现已与 M3 适配器共用，未替换默认生产 click schema。

入口：[macOS 测试](../../backend/core/tests/test_computer_use_macos.py)、
[探针测试](../../backend/core/tests/test_grounding_probe.py)、
[测试指南](../../backend/TESTING.md)。这些覆盖已识别的静态主屏转换，不能表述为
“所有硬件、动态状态和模型输出均正确”。sips 的 mock 由真实机器校准补充。

## 真实输入校准

[九点校准脚本](../../backend/scripts/calibrate_macos_coordinates.py) 在自己的
AppKit 窗口内核对截图红色目标，再发点击，独立记录 down/up、窗口坐标和
光标回读。最终主屏九点每轴最大误差 1 point、距离约 1.42 points；两轮
1 秒间隔通过，恢复 0.1 秒额外间隔后也通过。它每次仍截图，不是无截图连点压测。

首次存在未收到事件、一次回读与事件不一致；Calculator oracle 首次还有一次
未保存坐标的光标断言异常。证据不足以归因，后续通过不能抹去这些观察。
随后 [Calculator oracle](../../backend/benchmarks/computer_use/reports/20260919-calculator-oracle/results.json)
三次通过真实 ScreenshotTool/ClickTool 完成 7×8=56，12 次光标误差 ≤1 point。
按钮真值来自本地 AX，故它验证执行链，不验证模型识别和闭环决策。

## 模型、协议与提供方实验

以下各轮任务、布局及评分不同，不能合并成单一准确率。

- 最初 16 次固定合成图：稀疏界面 4/4 命中，密集计算器 12 次仅 2 次命中；
  另有合法错点、畸形 bbox 和未声明工具。裁剪或统一缩图未稳定解决问题。
- 32 次坐标空间基线加 16 次 point-only 对照：同图输出在归一化/像素等
  解释间变化，简化 schema 后格式改善但仍有 >50 px 偏移。1000×1000 控制
  图上仍错，因此不是统一乘错某个倍率。
- [100 次请求消融](../../backend/benchmarks/computer_use/reports/20260919-grounding-ablation)：
  代理/最小提示、尺寸公式、thinking、高分辨率、普通 JSON 均未稳定修复。
  原始 SSE 4/4 与本地参数一致且非法，非流式 8 次也非法，排除本批错误由
  本地 SSE 拼接或仅流式接口导致。旧原生 bbox_2d 文本任务 hard 8/8 在
  15 px 内，holdout 4/8，最大约 41 px；收益不能泛化到所有 bbox 工具协议。
- [80 次同提供方换模型](../../backend/benchmarks/computer_use/reports/20260919-grounding-model-comparison)：
  point-only Flash 5/16、Plus 15/16、VL Plus 7/16 中心误差 ≤15 px；生产
  click schema 下 Flash 3/16、Plus 15/16。Plus 仍有大错；此处 15 px 精度
  阈值不是按钮命中率，不能直接宣称真实 calc-open 修复。
- [304 次跨模型/协议隔离](../../backend/benchmarks/computer_use/reports/20260919-protocol-models/README.md)：
  同一独立 16 布局各重复两次，GPT-5.5 32/32 命中，最大误差 2.08 px；
  GPT-5.4 Mini 30/32，最大 38.83 px；Qwen3.8 Flash 25/32，最大 417.91 px。
  全部格式有效。GPT 经 OpenRouter 限定 OpenAI、禁 fallback，响应 provider
  已核实。这仍是合成静态定位，不是完整代理运行。
- nullable type-array/anyOf 在四个 Qwen 预检中都产生字符串坐标，strict
  也未阻止；单一 integer schema 修复该格式适配，未解决定位。found=false
  的 0/null 两种协议分别严格验证。schema 不能证明坐标对应目标按钮。
- 标记、打乱布局、裁剪、缩放、旧图片历史、agent 提示和完整工具定义已做
  小样本隔离，未找到普适修复。当前 Flash 在最小提示已错，工具数量不是
  必要条件；一张历史图实验也不等于长会话/compaction 验证。
- 原生 DashScope 同样出现大错：当前 Flash 1/4 命中、最大约 282 px；
  Qwen3.8 Flash 2/4、最大约 533 px。兼容层不是必要条件，四次随机调用也
  不足以判断哪种 API 更可靠。
- Qwen usage 与近原尺寸 patch 对齐相符，不支持“必定缩到 1280 宽”，但
  不能由 token 数唯一反推内部尺寸。GPT-5.5 low-detail 首次约 407 px 大错，
  追加 auto/low 各六次都命中，未复现确定性缩放故障。上传 hash 相同只证明
  上传字节相同，不能证明服务端预处理相同。

## DeepSeek 预算专项

[112 次复测](../../backend/benchmarks/computer_use/reports/20260919-deepseek-budget/README.md)
确认旧 4000 是探针硬编码，不是服务上限；现可用 `--max-tokens` 和
`--thinking on|off` 覆盖。生产 default/planning DeepSeek 为 10000/20000，
computer_use Qwen 为 40000，均未因实验修改。

配对筛选每组 12 次：on/4000 两次纯推理截断，on/16000 无截断但同为 3/12
命中；off/4000、off/16000 均正常输出，分别 3/12、5/12 命中。独立布局
off/4000 为 20/32 命中，on/16000 为 23/32；后者仍一次 16000 全用于推理，
没有点击。关闭思考的平均输出从 736 降至 104 token，减少约 86%，仍有约
339 px 大错。全部 56 次 off 响应无推理输出。

截断与错误坐标是不同失败类型；提高预算不能保证完成，关闭思考节省输出
token 也不保证定位。off 与 on 的有效采样不同，不能用小分差证明预算收益。

## 仍未确定或未验收

- 多显示器、非主屏、跨屏、旋转、截图后切主屏/分辨率；全局尺寸缓存及多
  会话覆盖风险在 legacy 路径仍在；image 接口已有身份/几何失效拒绝，未实现
  多屏执行。当前静态实验不依赖这些因素，所以它们不是已复现大错
  的必要条件，但也没有被所有场景排除。
- 窗口移动、动画、抢焦点、并发鼠标，以及无截图高频 batch 连点。旧坐标
  可失效；legacy batch 通常仅在末尾截图，image batch 每步检查观察区域。
  静态校准中的早期异常原因仍未知。
- 模型权重与服务端预处理、OCR 与空间表达仍无法独立归因；未采用猜测倍率
  进行运行时补偿。跨部署同权重控制及更多按钮尺寸需要另行实验。
- 全套跨应用任务、长历史/compaction、生产可靠率。
  16 个布局重复两次不等于 32 个独立布局；不能从合成 32/32 推断零错点。

## 完整闭环的判定

现有 benchmark 直连 AgentRunner，覆盖生产提示、LLM 多轮消息、截图、真实
动作、反馈与独立 validator；不覆盖 Supervisor 调度、持久化、审批 UI 或语音。
macOS `calc-open` 使用 `trial-token-gui-calc-v4`：每轮重置为 0，结束时要求
前台未最小化 Calculator 的 AX 表达式为 7×8、结果为 56，拒绝 shell/file
绕路。Linux 仅检查进程，仍属 smoke。截图存在和像素内容当前不是评分条件，
因此本次闭环应额外检查最后截图及调用轨迹；键盘成功与鼠标定位成功分开报告。

### GPT-5.5 真实闭环结果

[三次原始评分与脱敏证据](../../backend/benchmarks/computer_use/reports/20260919-gpt55-loop/README.md)
采用生产 AgentRunner、原 computer_use 定义和工具；仅独立配置切到
OpenRouter → OpenAI GPT-5.5，reasoning=low、输出预算 16000、temperature
省略。全部 13 次实际响应的 model/provider 已核实；七张真实截图的 HTTP
hash 均与各自 trial 归档一致，各轮最后截图确实进入后续模型请求。
用户明确允许清理后的主屏截图外发，其他应用被隐藏/遮挡；原始截图仅存
本机 `/tmp/tank-gpt55-loop/`，不进入仓库。测试后恢复隐藏应用。

- 第一轮四次鼠标点击 7、×、8、=，截图与 AX 均显示 7×8=56，通过。
- 第二轮 `type_text("7*8")` 再 Enter，截图显示 56 但无表达式，严格评分失败。
- 第三轮粘贴 `7*8=` 后仍为 0，模型观察新截图后改用四次鼠标点击，成功。

最终严格评分 **2/3**，三次末尾画面都显示 56。未超时、未使用 shell/file，
共 72140 token；完整任务耗时分别 28.93/27.76/58.82 秒。两段鼠标序列验证了
应用结果，不等于八次分别记录事件/按钮边界的校准；仍不改变历史九点证据。
Calculator 重启后位置在 trial 之间变化，新截图后模型适配了位置；未测试
截图后几何突变、非主屏或跨屏。旧 driver 的 cleanup=unknown 原样保留。

本轮还确认三个与统一坐标倍率无关的问题：

1. **生产 LLM 参数接入缺口，已修复。** 合成图预检时，强制携带 temperature
   被 OpenRouter require_parameters 路由拒绝；同请求只去掉该键即成功。
   profile 新增显式 `temperature: null`，两条请求路径均省略该参数；没有
   设置此键时仍用旧默认值。流式/非流式、0.0 覆盖到实际 HTTP 的回归通过。
2. **输入路径与评分约定不一致，未改评分。** 本地独立重置后复现：粘贴
   `7*8` 直接得到 56 而无表达式，粘贴 `7*8=` 不改变 0。生产含标点的
   type_text 走剪贴板，不能等同逐键/逐按钮输入。第二轮满足“显示 56”，
   但不满足额外的表达式校验；保留失败，不归类为错点。
3. **子代理继承主代理委托指令，已修复提示构建；效果未重测。** 历史 HTTP system 同时有桌面
   专家指令与“ALWAYS delegate to the computer_use agent immediately”；
   [runner](../../backend/core/src/tank_backend/agents/runner.py) 追加的
   [base.md](../../backend/core/src/tank_backend/prompts/defaults/base.md) 当时含该规则，
   而工具集中没有 agent。模型明确指出冲突；其定位影响尚无单因素对照。

本次完整后端 **4484 passed/1 skipped**，E2E **14 场景/55 步**，其余要求
检查通过。[验收计划](../plans/done/gpt55-computer-use-loop.md) 已完成；
全套跨应用、长历史及上述剩余问题已纳入
[后续执行计划](../plans/done/computer-use-adaptation-and-grounding.md)（已关档，
结论见 [M8 收口报告](../../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)）；
多屏/压力等条件性范围仍见 [backlog](../backlog.md)。

### 提示职责隔离（2026-09-19）

共享 `base.md` 只保留安全规则、沙箱说明和环境信息；主代理的桌面委托规则
由 PromptAssembler 单独加载 `orchestration.md`。AgentRunner 构建子代理
提示时不加载该主代理规则。`ask_user` 说明依据最终可用工具集注入，受注册、
allowlist、命名 toolset、disallowed 共同约束；不可用时结束并报告所缺信息。

[离线请求快照](../../backend/benchmarks/computer_use/reports/20260919-adaptation-m0/README.md)
通过真实 SDK HTTP 边界验证只有 system 改变；主代理委托和共享安全规则均有
回归。[M1 首步 A/B](../../backend/benchmarks/computer_use/reports/20260920-m1-acceptance/README.md)
在三个合成布局各重复两次，旧/新提示均 0/6 命中，未观察到定位收益；
不据此更改历史分数。完整真实任务效果仍待后续对照。

### 文本输入与 Calculator 证据（M1）

macOS `type_text(text, mode="auto")` 在当前输入源支持 ASCII 时，ASCII 字母、
数字和空格走 AppleScript keystroke；非 ASCII 输入源或其能力未知时走剪贴板，
避免字母被 IME 改写。标点、换行和非 ASCII 文本始终走剪贴板。不切换用户
输入法。`mode="paste"` 显式强制
粘贴，允许用于纯数字；未知模式在操作系统调用前拒绝。工具说明告知剪贴板
会被替换，以及 Calculator 对粘贴表达式的特殊语义。Enter/快捷键仍通过
`key_press`，其中带 Shift 的映射键使用物理 key code，避免 `shift+8` 被
AppleScript keystroke 当成 `8`。工具报告实际输入路径，只确认已派发，
不声称应用接受或任务完成。M1 主屏实测覆盖 TextEdit 六项和 Calculator 八项。

`trial-token-gui-calc-v4` 的严格总分维持原表达式口径。新增
`calc-evidence-v1` assessment 独立写入每轮 result.json 和报告 outcomes：

- `strict_expression`：前台 Calculator 的 AX 表达式为 7×8、结果为 56。
- `business`：本轮已验证清零且有完整成功输入轨迹，再根据表达式/结果判断。
  允许完整插入 `7*8` 或 `7×8` 后得到 56；直接插入答案 56 不通过。
  中途失败、未完成动作、未知工具或缺少当轮证据时记 null，不冒充通过。
- `mouse_only`：在业务证据完整且严格结果成立时，计算输入全部为鼠标点击
  并至少四次才通过；按键/文本不计为鼠标定位成功。此指标不证明各点击的
  几何精度，逐按钮命中仍需 oracle/独立边界诊断。
- `pixels` 当前为 unknown，保留人工核验；AX 和图片 hash 都不是像素评分。
  M1 受控截图另有本地 OCR 与独立助手视觉复核；OCR 对部分孤立数字误识别，
  未将其推广为通用自动评分，也不将助手复核称为人工签字验收。
  `last_screenshot` 记录 hash、捕获时间及最近一次实际 SDK HTTP 序列化时间；
  后者仅证明图片进入请求，不证明远端模型已读取或截图仍代表最新界面。

内置 benchmark driver 在实际 SDK HTTP 边界记录图片 hash，不记录鉴权头或
图片内容；真实截图仍只保存在本轮本地目录。插件传输不套用此内置 hook，
没有匹配证据时不会伪报截图回流。GUI-only 违规使业务/鼠标轨道也失败。
旧报告不重评分，不把新增业务轨道加入原 strict 分母。


## 可选规划/定位分离（M4）

Agent markdown frontmatter 增加 `grounding: {}` 即启用分离模式；删除该键
回到原一体模式。仓库默认定义未启用。默认复用规划 LLM，可以独立指定
`profile` 和可选 `fallback_profile`（必须已存在于 `llm` 配置，拼错不回退）。
适配参数为 `protocol: point|pixels|bbox`、`nullable_style`、`strict`、`detail`
和 `status_field`；分离默认使用显式 status，做 B/C 对照时需显式冻结相同参数。
后备 profile 使用同一协议配置，模型切换不自动切换坐标协议。

```yaml
grounding:
  profile: computer_use  # 省略则复用规划模型
  protocol: point
  status_field: true
```

- Runner 为每个任务建立独立工具视图、FrameState、图片和定位引用，不修改
  父 ToolManager。分离提示明确覆盖定义正文的旧坐标/调用格式约定，
  保留其余自定义任务要求、workspace/security 和按实际工具生成的澄清指引。
  只支持已有 macOS frame 工具；不改变 SDK 或 Linux 路径。
- `screenshot` 自动走 M2 image 模式；`locate(frame_id, target, window_id?, backend?)`
  只发送已绑定 PNG 和目标描述。窗口身份由宿主检查和裁剪约束，不信任模型
  返回 frame。规划器得到 status/frame 和不可伪造的随机 `location_id`，不接收坐标。
- click/mouse_move/scroll 使用 `location_id`，drag 另需 `end_location_id`。宿主
  从引用读取坐标，经同一个 M2 逆映射和帧/几何校验派发；拒绝规划器传 x/y、bbox、
  legacy 模式或 ctx。分离模式不提供原始 mouse_down/mouse_up。
- 新截图作废旧引用；定位失败/歧义作废可执行引用。定位前后均复核帧与几何，
  动作前再检查 frame、窗口和几何，不比较画面像素。每步最多首次定位加两次重定位，
  重新截图不重置次数；primary/fallback 最多切换一次，且没有自动网络重试。
- 共享 SubAgentBudget 只由规划流和定位响应各记一次；无 usage 记录 unknown，
  有预算上限时停止。取消或 deadline 会中断定位 HTTP，并在派发前再检查。
  命名定位 profile 的客户端在任务退出时关闭；已开始的原生键盘/启动操作
  会等待收尾后再释放桌面锁，不宣称中途即时终止物理输入。
- 单动作返回新截图；短 batch 最多 8 步，只能使用该任务允许的动作，固定
  目标逐步重新检查。帧作废或几何变化使后续旧引用失败，首错即停，剩余步骤标 skipped；
  相同失败 batch 不允许盲目重放。返回 `dispatch=dispatched|error` 和
  `effect=unknown`，截图由规划器检查，不把事件投递当作效果成功。

验证覆盖离线真实 Runner/ToolManager/SDK 和 M2 macOS 边界；不代表模型会选对
目标、识别正确或真实动态 UI 稳定。M5 因果对照与 M6 真机停止/效果仍待执行。


M5 的 benchmark 入口支持上述分离模式：Runner 的可选 LLM 工厂让 benchmark
对命名规划/定位客户端使用同一个计量器，生产默认仍使用原 profile 工厂。
任务拥有的命名客户端在任务退出时关闭。分离截图通过任务 observer 保存，
避免外围截图包装遮蔽 FrameTool；真实图仍只写本轮本地 trace。
`describe()` 保留 grounding 配置，HTTP hook 同时覆盖规划和定位图片 hash。
定位请求失败/取消/无 usage 计为 unknown；非流式定位不伪造 TTFT，嵌套 RTT
从规划计时区间扣除。规划区间仍含部分本地工具时间，不代表纯 HTTP 延迟。
评分 revision 为 `trial-token-gui-grounding-v5`：locate 允许用于 GUI 任务但
不计输入 primitive，Runner 终止错误会记录为 trial error。完整 A/B/C/D 模型配对尚未验收；B 一体接口与 batch primitive 计量的软件
实现见下节，默认 agent/profile 不变。


## 一体适配实验（M5 B）

在独立实验 agent 定义中配置：

```yaml
grounding:
  mode: integrated
  protocol: point
  host_restore: true
  status_field: true
  detail: auto
```

模型直接调用 `click(frame_id, location={status: found, x: 500, y: 500})`，
或使用同样的 location 进行 mouse_move/scroll；drag 另传 end_location。
这是工具对象示意，JSON 使用正常引号。截图可绑定 window_id，后续定位动作
携带相同窗口身份。内部仅用宿主引用复用 M4 的派发代码，不发起定位模型调用，
不向规划器提供 locate。键盘工具和短 batch 仍使用原允许的工具集合。

复用原 agent 的模型、任务提示和工具范围时，以下配置提供共同框架内的
两个因子；其他 GroundingConfig 字段保持一致：

- A-control：`mode: integrated, protocol: legacy, host_restore: false`。
- B-host-only：`mode: integrated, protocol: legacy, host_restore: true`。
- B-protocol-only：`mode: integrated, protocol: point, host_restore: false`。
- B-combined：`mode: integrated, protocol: point, host_restore: true`。

原 A 仍省略 grounding。共同框架增加 location 包装、帧校验、反馈、统一
取整和截断拒绝，A→A-control 必须独立报告。框架内还原开关保持 schema
相同：true 使用当前图坐标并由宿主逆变换；false 要求模型利用截图返回的
crop/image_size/screen_size 自行还原主屏坐标。两者都拒绝当前观察区域外
的输入，并在派发前复核几何/场景。它们没有复刻旧驱动的全部执行行为。

legacy location 保留 x/y、数组和 bbox 解析；point/pixels/bbox 使用共用
GroundingAdapter 的字段、整数约束和拒绝哨兵。像素 schema 在截图前没有
宽高上限，执行时仍按实际尺寸校验；分离定位的 SDK schema 有当前图上限。
集成截图采用 detail 配置；冻结 B/C 对照需固定共同 detail（首轮用 auto），
并保存各自完整提示/工具 schema，不把工具包装和目标提示差异隐藏起来。

一体模式的 `computer_batch` 只接收 `actions`，自动返回末帧；pointer action
使用与单工具相同的 `frame_id/location` 字段。提示显式覆盖旧版 `screenshot`
batch 选项，不沿用 split 的 `location_id` 参数说明。`actions` 和截图的
`region` 必须是 JSON 数组；`screenshot` 创建新帧，不接受 `frame_id`。
截图失败后必须重新成功观察，再使用新帧操作；不自动修复字符串化参数。

集成模式禁止定位 profile/fallback/strict=true。未知字段、无效/过期 frame、
非法坐标、拒绝定位及失败 batch 都不会继续派发。拒绝定位在动作工具中返回
error=true 以停止当前 batch，并不表示模型的拒绝判断本身错误。一体/分离
任务对不完整流式工具响应和重复 JSON 字段在派发前拒绝，usage 先保留。
成功 batch 通过任务 observer 计量实际已派发动作；效果正确性仍需独立评分。


## AX 语义寻址（M7，实验分支）

在独立实验 agent 定义中配置：

```yaml
grounding:
  mode: ax
  ax_action: quartz   # 或 ax_press
```

工具层为 `tools/computer_ax.py`：`locate(frame_id, target, window_id)` 对当前
绑定的窗口**实时枚举 Accessibility 树**（HIServices C API，经 pyobjc 懒加载，
含 AXValueGetValue 解码与坐标朝向自校准），生成编号候选列表（角色/标题/
值/标识/动作/屏幕 frame），以**纯文本请求**（无图片外发）交给定位模型从
编号中选择（status=found/not_found/ambiguous + index，越界拒绝）。候选
由本次真实观察发现，不写死应用按钮，不携带评分真值。

派发两种模式：`quartz` 在派发前刷新元素（stale 拒绝）并将元素帧中心换算
回观察坐标系，复用 M2 帧校验/几何检查后由 Quartz 点击；`ax_press` 直接对
元素执行 AXUIElementPerformAction，仅支持默认 click（button/clicks、drag、
mouse_move、scroll 明确拒绝），并在派发前检查 AXPress 可用与元素帧在绑定
窗口内。旧引用、窗口不匹配、无候选、未绑定窗口帧、歧义/缺失选择均
零输入拒绝；计账/取消/事件结构与 split 模式一致（usage unknown 不计零，
grounding_call_id 关联 HTTP）。

已知覆盖边界：macOS 26 按钮普遍 AXTitle 为空、标签在 AXDescription/
AXIdentifier，且 AXActions 属性普遍缺失但 AXPress 实测可用（因此 ax_press
不预检查动作列表，以 PerformAction 返回码为准）；pyobjc 返回的 NSArray
不是 Python list 子类，子树遍历与动作解析按迭代协议处理（回归覆盖）。
同名候选（Chromium 内容中常见，如 "Add to Cart" ×9）由选择模型消歧或报
ambiguous。本分支成绩单列，不替代纯视觉 A/B/C/D；默认配置不变。实测
覆盖与边界验收（2026-09-25）：全部 benchmark 应用 57–429 候选、100% 有
frame、无截断；旧引用/窗口不匹配零输入拒绝，见
[覆盖率报告](../../backend/benchmarks/computer_use/reports/20260925-m7-ax-coverage/README.md)。

真实对照结论（2026-09-25，条件性暂缓）：机制端到端成立——AXSession 截图
省略 window_id 时宿主自动绑定前台常规应用主窗口；live3 中 AX-quartz 以
完美选择序列（7/×/8/=）拿到本计划首个 AX 臂 strict 通过。但 qwen3.7-flash
选择器在 57 行候选列表中反复选错相邻项（off-by-one、误选 All Clear），
三臂 A 1/3 / AX-quartz 1/3 / AX-press 0/3（n=3），AX 臂 token 成本更高；
不采用为默认，选择模型复验与 OCR/编号方案登记 backlog。期间修复的三个
生产缺陷（M2 省略 window_id 验证、AX schema 隐藏窗口 id、非法 JSON 工具
参数可恢复且零派发保持）见
[live3 报告](../../backend/benchmarks/computer_use/reports/20260925-m7-ax-live3/README.md)。


### Benchmark 原生输入清理（2026-09-24）

built-in macOS benchmark 可通过 `input_cleanup=True` 显式启用自动输入清理；
默认关闭，不改变插件已有清理契约。Runner 在同进程桌面锁内检查起始按键/
鼠标为空，结束时先关闭动作流并等待原生操作完成，再释放残留输入、回读验证。
macOS 工具取消时等待原生线程收尾，重复取消不会提前交还桌面。清理失败保持
unconfirmed 并隔离桌面；批次不启动下一轮。外部取消保留 trace 后继续传播。

`cleanup=confirmed` 表示原生操作已结束且按键/鼠标已释放，不代表关闭所有
应用或恢复剪贴板/光标；后者仍是 trial/harness 的责任。输出保持供 validator
评分。挂死原生线程无法安全强杀，因此收尾可超过任务时限；操作者须保持受控
桌面空闲，不提供跨进程锁或用户同时操作下的输入归属保证。

Benchmark 的输入源管理通过独立 Python 辅助进程的主线程调用 Carbon。
查询、切英文和恢复均有 5 秒辅助进程超时，并检查退出状态/响应；SIGTRAP
不会终止持有桌面恢复状态的 benchmark 进程。父进程保存输入源 ID，恢复失败
保留 ID 以便重试；这不改变生产 `type_text` 的输入源策略。

受控 Calculator pilot 可由 `backend/scripts/supervise_computer_pilot.py` 外层启动：
在子进程执行前 fsync 私有桌面基线/PID，子进程结束或超时后回收并逐项恢复。
恢复文件包含剪贴板/应用状态，只存本机私有目录，不作为实验报告附件。入口拒绝
已有 Calculator 会话、残留输入及 loginwindow 前台；原 launcher 的授权/冻结门禁
仍须独立通过。外层恢复不重启试验，也不改变 batch 的评分/输入清理字段。
辅助进程 IME 切换/恢复已本机通过。外层恢复推进主运行循环后有界回读 AppKit
状态；launchDate 缺失时用系统进程启动时间补齐身份，不以 loginwindow 读数推断锁屏。
正常退出/硬退出/超时三类本机恢复已通过，记录见
[回读修复与验收](../../backend/benchmarks/computer_use/reports/20260924-m5-recovery-readback/README.md)。

## 采用决定与关档（M8，2026-09-25）

适配与定位专项（M0–M8）已关档。**生产基线保留不变**：默认 agent 无
`grounding` frontmatter，即一体规划定位 + legacy 归一化坐标 + 现有
`computer_use` profile。三层证据（静态 holdout 门槛、真实配对任务、
AX 独立分支）均不支持切换默认，详见
[M8 收口报告](../../backend/benchmarks/computer_use/reports/20260925-m8-closeout/README.md)。

研究结论与生产已实现行为分开表述：

- **已进生产且默认启用**：M1 提示职责隔离与输入语义修复（显式 paste 模式、
  IME/Shift 物理键码、粘贴 Command 成对事件）、M2 Observation 与 image 坐标
  （作为可选 `coordinate_space`，legacy 仍默认）、M3 共享 GroundingAdapter
  （供实验/探针路径）、期间修复的生产缺陷（type_text Carbon TIS 移入子进程、
  M2 省略 window_id 验证接缝、非法 JSON 工具参数可恢复）。
- **已实现、opt-in、未被采用**：M4 规划/定位分离、M5 一体适配
  （integrated + host_restore/protocol 变体）、M7 AX 语义寻址。一键回退 =
  删除 agent frontmatter 的 `grounding:` 键。
- **调查结论（不改变生产行为）**：适配一体 + 宿主还原（B-combined）在
  calc-open 上四批皆最差（合并 0/6）且耗 ~2.4× token；拆分架构在 calc-open
  上与基线持平（split vs A p=0.43，vs B-combined p=0.011）但 13 任务宽集上
  A 10/36 > C 5/36 且 C 耗 1.7–2× token；单位应匹配模型原生习惯
  （qwen3.8-max 在 pixels 契约下系统性误发归一化值，gpt-5.5 两种单位均可用）；
  静态首轮候选（Max bbox / GPT point）因同名歧义拒绝 0/16 未过采用门槛；
  AX 机制闭环成立但选择器精度不足。点击大偏移根因未解决，只能定位到
  服务输出边界。
- **条件性后续工作**：原生协议/专用定位模型、静态候选复验、AX 选择模型
  复验、OCR/编号方案、子代理历史压缩、动态几何——见
  [backlog](../backlog.md)。多显示器已于 2026-09-26 立项支持（生产/测试/
  benchmark，[计划](../plans/done/computer-use-multi-display.md)）：按屏
  截图与坐标、任意屏窗口绑定、拓扑校验、benchmark min_displays 与
  multi-display-calc 任务；实机双屏冒烟（拓扑/副屏截图/跨屏事件坐标）通过。

全量回归（backend 5116 passed / 1 skipped，含旧 N2/SDK）、E2E 16 场景 63 步、
停止/清理五场景验收全部通过；无新增清理失败或停止后动作。


## S0 Computer Use 插件：离线宿主循环（2026-09-28）

[agent-computer-use](../../backend/plugins/agent-computer-use/README.md) 通过既有
`type: subagent` extension 接缝接入，不在 Runner 或 GroundingConfig 新增策略分支。
插件内实现严格目标输入、click/fill 有限候选、规则/注入选择器/Advisor 路由、引用门控、
逐动作效果/最终目标核验和有界只读协调。当前统一使用下文目标契约；Advisor 注入接口仅补已声明的缺失输入或选择当前候选；
未知派发不会重放，结果保留观察绑定回执及核验来源，取消证据随通用清理链路保留。

当前空配置工厂没有真实通道，返回 `stopped / observation_unavailable`；未知配置项拒绝。
S2 的显式 `browser` 配置见下文。离线测试注入 fake UI/选择器/Advisor，不代表已接入
Jev、LLM，也不证明 PDF 产物或不覆盖约束。通道须提供可信语义事实，后续实现具体
身份、完成条件与派发边界。通用恢复及 Jev/Advisor 领域适配仍待实现；
生产 A 与现有实验 transport 拒绝条件不变。

### 通用模型装配（2026-10-05 SDK 调用级简化）

Extension agent 通过 `model: <profile>` 借用文本服务，通过 `decision-model: <profile>`
借用决策服务。核心解析配置与凭据；插件不配置端点或创建 SDK。未知 profile 明确拒绝。
文本 `TaskModel.complete()` 复用普通 LLM；独立 `DecisionModel.choose()` 使用官方 Jev SDK，
`TaskDecisionModel` 只添加任务绑定。二者均在 SDK 调用/流式事件层检查取消、deadline 和
已配置限额，使用同一 TokenUsageLedger，不再包裹底层 HTTP 或自研解析 SSE。

SDK 负责协议，核心保留所需结果/选项校验和已知/未知用量。默认只统计；调用级记录不能
冒称网络实际发送数、供应商费用上界或取消后不计费。普通 telemetry/Langfuse 可禁用，
记录失败不阻断调用；模型不再写必需执行审计，界面操作的审计与引用门控仍保留。
运行时负责关闭自有模型，借用的 SDK/pool 不被任务关闭。当前运行时 API 3。

真实 SDK + fake 网络覆盖 SDK 缓冲流式事件间取消、迟到结果、重复取消/清理、同账本去重
及可观测性失败；这不提供 S4 规划能力或新的真实模型收益证据。

### S0 模型调用记录与普通遥测（2026-09-29）

2026-10-06验收的[调用层简化](../plans/done/model-call-simplification.md)取代原模型
transport。当前`TaskModelCallRunner`在SDK调用前后发出开始/终结事件，终结区分
`not_started`、`unknown`、`returned`；记录task_id/call_id、耗时和可用用量。
`returned`表示调用返回且取得用量，不表示文本/目标语义成功；无效决策的已知用量
仍记账。记录与原任务账本、显式实验策略复用同一call_id。最近128条执行记录属于
TaskRuntime的UI/工具执行记录，不再将其描述为模型HTTP记录缓存。

Runner 自动将 extension 的 model_call 事件经核心 TaskObserver 转发到 Bus 的
`task_model_call`；已发送请求的终结同时转换为现有 `llm_usage` 格式，未知用量不
伪装成零或估算值。TokenUsageObserver 可消费这些事件并按 call_id 去重，但仍是
可选遥测消费者，任务授权与账本不依赖它。调用方原 observer 继续接收事件。

新遥测使用 Bus.post_bounded：队列已有 256 条消息时丢弃新增普通遥测，poll 排空后
可恢复投递；控制/生命周期消息保留原 post 语义。它限制的是新增模型遥测的排队，
不是整个 Bus 的全局容量。自定义 observer 仍遵循现有同步回调契约；异常由 context
隔离，不声称能抢占阻塞回调。事件和日志不含凭据、目的地、请求或响应正文。
普通遥测允许丢失，不能代替下述UI/工具必需持久审计。Adapter 对插件输出设置字节/事件上限；
不把模型遥测的有界队列宣称为整个应用 Bus 的全局硬配额。


### S0 Supervisor 的必需持久审计（2026-09-29）

WorkerSupervisor 为 extension 任务装配数据库审计回调，复用 TaskRuntime 的审计
失败锁定机制；当前原生操作写入统一数据库的 worker_audit_events 表，模型调用
按2026-10-06已验收设计使用普通遥测，不写必需执行审计。
每行保存任务/调用身份、类别、阶段、状态与可用的用量/耗时，按追加顺序保留；
不保存端点、凭据或请求/响应正文。WorkerStore.audit_records 提供按任务分页读取。
直接 Runner 使用者仍须显式注入 audit，不能把未注入的路径当成已持久化。

UI/工具注册操作在invoke前先提交prepared/not_sent，再提交dispatch/unknown意图，
异步写入后再次检查授权、取消和期限；操作返回后追加finished记录，丢失回复则
保留dispatch/unknown意图，不把未知效果改成未派发。
unknown 意图不是已确认发送：进程可能在提交意图后、实际发送前退出，因此不可
盲目重放。终结记录引用同一call_id；终结审计失败锁定任务，不向调用者交付成功
结果。模型用量独立保留在原任务账本。插件即使捕获审计异常并返回 DONE，
Adapter 也拒绝将其当作成功任务。

审计写入串行等待并设 2 秒上限，失败/取消/超时锁定原运行时，后续业务拒绝；
已失败后不再追加新审计尝试，保留此前已提交的保守意图。数据库操作放入线程，
等待超时不代表能撤销底层数据库提交；迟到提交只追加证据，不能重新开放业务。
普通Bus遥测仍可丢失，不承担这一派发前门控。运行时关闭有界等待在飞操作和资源
清理；模型调用另等待SDK取消/关闭并结算用量，不承诺模型终结审计。
Supervisor保留audit_failed终止原因。
内存 SQLite 在同一 Database 实例内共享跨线程连接并串行化事务；它仅用于临时数据，
不具备文件数据库的重开持久性。文件库保持原连接池行为。
跨进程恢复、审计数据库保留/容量策略不在 S0 骨架验收内；同进程恢复及真实通道
的统一接入仍按 S4-G3 验收。


### S0 保留调用方与出口清单（2026-09-30）

- Computer Use：观察、派发经 TaskOperation；测试 Advisor 借用 TaskModel。
  规则零模型、多步 fake Jev、一次 Advisor 后恢复、旧回复/未知效果等均离线验收。
  当前工厂可显式装配DOM或macos；空配置仍unavailable，实际接线见下方G3清单。
- 非 GUI fixture：同一 SubAgent/Runner/TaskModel 服务，无 Computer Use 领域依赖。
- Runner 的 LLMAgent：planner、locator、fallback 和审批 classifier 绑定原 context；
  流式/非流式共享 SDK 调用级记账，旧 usage 投影按 call_id 去重；保留现有工具政策与提示。
  主会话直接使用的 ChatAgent 不因此变成受管 SubAgent，其原审批/账本契约保持不变。
- 实验入口：显式ModelCallPolicy/ModelCapture注入SDK调用准入、费用策略和调用级捕获，覆盖上述模型
  客户端；没有已声明模型能力的 extension 仍拒绝启用请求限额。凭据不进入审计/遥测。

公共验收为 `core/tests/test_subagent.py::test_retained_callers_share_governance`：
三条真实Runner/SDK路径共用授权、唯一用量、响应时撤权、普通observer失败不阻断、
任务关闭后拒绝调用、连续任务与借用连接所有权断言。UI执行审计失败零派发另由
TaskRuntime/Supervisor测试核验，不将模型调用描述为发送前必需审计。
HTTP与OS被替换，无付费或真实桌面调用。
领域证据在 `agent-computer-use/tests`；核心限额、撤权/取消/迟到完成及资源回收
在task_runtime/model_calls/task_model测试。2026-10-02移除两条N2验收路径。

2026-10-17出口审计发现G1请求数据准入缺口，随后在原SDK调用入口补齐实现：
`SubAgentContext.model_data_scope`持有不可变ModelDataScope，默认仅文本/4MiB。
Runner为既有内置LLMAgent/grounding显式允许文本与image_url图像/32MiB，调用方
只能收紧该范围；extension默认仍文本/4MiB。TaskModel保持文本专用，即使原任务
允许图像也拒绝图像块。未知/混合内容块、音频等未接线数据拒绝，不启用Jev图片。

TaskModelCallRunner在实验预留、捕获和SDK进入之前统一检查；Jev当前Choice的
state/questions为JSON文本，同样受原任务类别/字节上限约束。字节按参数快照规范
JSON（UTF-8、非ASCII不转义、紧凑分隔、拒绝NaN等非JSON值）计算，包含内联图像
内容；这是调用级载荷上限，SDK序列化/HTTP头及遥测开销不在该字节口径内，不冒称
逐包HTTP长度拦截或远端URL图片下载体积上限。内容类型不等于语义脱敏，不能识别
文本内所有秘密。拒绝保留model_data_denied/model_request_too_large原因，零SDK
请求/零已发送用量；原授权、deadline及关闭检查仍在异步捕获之后再次执行。

适配器保留私有输入快照，捕获回调只能改自己的副本，不能把已准入文本改成实际
发送的图像。独立静态图片诊断harness显式声明已有图像范围；旧冻结和真实评分
不改，未来配方固定model_data源码指纹。本切片完整验证与第1轮独立评审通过，
无可操作或遗留问题、无源码修复即结束，G1-DS1阻断已解除；状态补记由评审者自检，
不自动宣告S5/S6整体验收。见[主计划S6审计及实施](../plans/done/computer-use-strategy-ladder.md#s6-出口审计与当前采用建议2026-10-17)。


### S1 AX / Vision 观察适配器（2026-09-30）

Computer Use 插件新增可注入的只读 AX 与 Vision 观察源，默认工厂仍不启用实机任务。
AX 复用核心枚举，补原生动作名 API、AXValue 可写性、祖先、焦点、PID/窗口；
深度/子节点/总节点/文本裁切均标记不完整，窗口几何重合无法唯一绑定时拒绝。
插件用任务内原生对象身份分配引用，重排保持引用，消失后不复用旧引用；
快照保留语义数据，原生句柄不进入模型文本。候选先检查全范围歧义，再保留至多
32 条，携带总数/截断状态；明确唯一目标不受原列表位置影响。

Vision 为可选惰性依赖，固定 revision 3 / accurate / 中英 / 关闭语言纠错，
只识别宿主绑定 hash/尺寸的 PNG。文字框保留为 image-pixel text_region，
通过 M2 Observation 映射全局坐标；不推断可点击性，不融合 AX/OCR。
两种观察源经 Controller 的 TaskOperation 读取，撤权/关闭后不得新增原生读取。
[合成样本验收与限制](../../backend/benchmarks/computer_use/reports/20260930-s1-observation/README.md)
记录逐例输出；实机应用 AX、动作派发/效果、Jev/Advisor 与恢复不在本次证据内。

### S2 管理的 Chromium 通道（2026-09-30）

插件显式 `browser` 配置装配惰性的 Playwright 通道；空配置与生产 A 不变。
extension 声明 desktop/network 权限，真实 Runner 复用通用审批、配额和清理。
首次获准观察创建 headless Chromium 和非持久 context，限定配置的 origin 与固定 page，
不附着用户浏览器、不用 URL/窗口标题选页；关闭 service worker、WebSocket 和下载。
有 iframe 时须显式选择唯一具名叶子 frame；无法确认范围、frame 被替换或连接丢失时停止。

单一 locator engine 用实际 DOM 对象身份贯通观察、点击/填写和读回；重渲染替代节点
不会继承旧引用。快照绑定任务、观察、代次及真实 page/frame，导航和状态改变拒绝旧动作。
button/link 支持 click，原生或 contenteditable textbox 支持 fill；节点/文字上限及
open shadow root 标记范围不完整。语义命名仅覆盖 aria-labelledby/aria-label/原生 label/
控件文本子集，不宣称完整可访问性树。唯一 `role:label` 的当前值/文本形成事实，
宿主按目标谓词核验，不能据页面“成功”文字推断外部持久化或真实文件产物。

所有动作保留 Playwright actionability 检查，fill 同样先做 trial click 防止穿透遮挡；
异步预检后再次检查原任务授权、取消、deadline 和预算。待执行原生命令期间停止会关闭
任务拥有的浏览器，避免仅取消 Python await 后命令继续运行；不宣称跨浏览器原子性。
回包丢失后只做有限读回，未知效果不重放。资源创建与关闭同步，清理失败沿核心路径报告。
真实本地浏览器测试及配置见
[插件说明](../../backend/plugins/agent-computer-use/README.md#s2-managed-chromium)。
这不代表 AX 实机动作、Jev/Advisor、同进程恢复或生产采用已验收。


## Core-owned Jev decision service (S3-M, 2026-10-04)

Computer Use now borrows `context.runtime.decision_model.choose(...)` from core.
Core owns the named `decision_models` profile, fixed Jev version, environment key,
TypeSafe SDK and lifecycle; TaskDecisionModel adds SDK-call accounting and task checks. The plugin manifest
registers only its SubAgent; no `model_route` extension remains. UI evidence and
whole-action candidate construction stay in the plugin; core decisions have no
computer-operation knowledge. See [core model assembly](agent-orchestration.md#core-decision-model-assembly-sdk-call-contract-2026-10-05).

The sole `GoalContract` uses schema version 2 and the goal-driven host loop.
Version-1 input, Milestone and the compatibility execution path have been removed.
The core SDK service preserves the four explicit non-action choices and hard-stop
behavior. Goal-driven schema-v2 execution is described below; Advisor planning and core
resume are not yet available. Production defaults and the historical S3 no-net-gain conclusion
remain unchanged; prior raw HTTP results do not establish SDK latency or savings.


## S4 目标驱动 DOM 闭环（2026-10-07，首批）

显式 `schema_version: 2` 使用 goal_id、intent、objective、scope、authorization_ref、
allowed_operations、带 purpose/field_scope 的 inputs 和 completion；不接受 milestones。
授权引用使用 `current_task` 或匹配已有任务身份，不能新增权限。类名统一为
`GoalContract`，不再保留旧类、转换兼容层、联合类型或里程碑循环。

v2 根据当前 DOM 能力构造混合 click/fill；fill 只使用声明范围内的已给定输入，
已核验输入绑定实际元素引用；引用包含文档实例身份，不因同名控件替换或 reload
后局部编号重用而自动迁移。导航click接受`aria-controls`指向唯一具名区域，或同源/
同窗口/非下载链接的精确目的URL效果；`status:Page URL`来自宿主真实frame URL，
页面同名文本不能覆盖它。唯一具名原生复选框保留checked读回。同名框现在也可
形成候选，使用宿主保留命名空间`dom:checked:`与实际节点绑定，其他同名/替换节点
和页面伪造角色不能充当该效果。唯一原生表单name会作为字面`[name=...]`上下文；
缺少可区分上下文或注解碰撞仍是语义歧义，opaque事实key不作目标语义，视觉选择
也只能选原绑定候选。submit仍需先满足输入并核验目标回执。
不按按钮名字猜副作用，不将任意页面变化或输入框内容视为保存成功。
原生HTML表格行没有作者指定的可访问名称时，将所属行的可见文字加入`row`
祖先上下文，把记录内容与同名操作关联；不读隐藏文字。重复/空上下文仍不能消歧，
沿用祖先长度上限及原DOM/ref/精确图片新鲜度守卫，不修改页面或推断业务身份。

Jev/F 接收同一目标、当前快照、完整动作描述与宿主进度。v2 不沿用“单一同名按钮即执行”
规则。仅有一个显式字段绑定 fill 时可直接执行；即使输入已核验且只有一个原生
form submit，也不能证明提交意图，仍须走配置的选择器。引用和授权仍由宿主核查。模型选完整动作，不能覆盖参数。动作后重新观察：fill
核验相同原生引用的值，click 核验已绑定效果；未核验时只读协调，不能重放。
模型自称完成不产生终态。重复语义状态会停止，观察代次变化不算进展。

真实受控 Chromium/Runner/SDK 的 fake-HTTP 测试覆盖两种布局与中间页，并独立检查
fixture 服务端结果。仅此测试中的回执有受控服务端语义；任意页面 status 文本不构成
外部业务系统真实性证明。S4 能力主线已于 2026-10-10 按证据收口（见策略阶梯计划
“S4 收口”）；同进程恢复（G3）仍于 S6 前，OCR/视觉后备与 N 第二片在 backlog。
文本 Advisor 的现行接线见下文；仅能填充已声明为可生成且为空的输入，更新版本但不重置
进度或用量。
旧 schema-v1 输入被明确拒绝。当前可执行 benchmark 使用新的目标契约 revision；
历史 S3 报告未重写，新请求/候选不能被当作历史实验的原样复现。

## S4-AX 原生接线（2026-10-07）

统一 GoalContract/Controller 可通过显式 `macos` 配置借用原生窗口。通道绑定 bundle、
PID、内核启动标识、窗口、文档和元素身份；每次输入前重读 AX 状态及窗口边界。
当前仅验证主屏前台窗口，不按标题自动重新附着，不关闭用户应用。AXPress 与 Quartz
为显式模式；fill 写可写 AXValue，保留原始文本，不隐式切换剪贴板/键盘或另一派发模式。

宿主配置 readouts，将原生角色/标识/祖先标识对应为 `ax:value:<name>` 事实；未绑定的
完成谓词拒绝。macOS 绑定另支持通用条件 `ax:present:` / `ax:absent:` / `ax:title:`：
相对各窗口首个完整观察（基线；原窗口须在首次派发前）判定，值出现只看元素值且须新出现、
唯一，元素消失须基线中存在，标题包含须新成立。无画像 App 的点击以 AX 观察变化为局部效果，
标签含危险词（内置中英文名单，`macos.blocked_terms` 可追加）的元素只去掉 click、保留 fill。绑定读数的变化仅是局部动作效果，最终仍独立检查目标条件。Calculator
数学显示采用紧凑文本，TextEdit 正文保持逐字比较。作用域超限/不完整、旧引用、用户
输入冲突和未知效果均不盲目继续，失败的原生清理不能报告完成。普通核心不导入 benchmark。

真实应用 fake HTTP 与经授权真实模型矩阵均已 9/9 通过（含移窗/Quartz/TextEdit）；
NL 端到端 live 3/3 通过。更早真实批次曾出现首项失败停批，保留为历史证据。
冻结配方与收口状态以[策略阶梯计划](../plans/done/computer-use-strategy-ladder.md)
“S4 收口”为准。运行器及接口说明见
[插件说明](../../backend/plugins/agent-computer-use/README.md#s4-ax-explicitly-bound-native-macos-channel)。


S4-AX 的 Jev 模型视图现对全 AX 快照使用局部短引用和显式元素默认值，并从目标元素
复用候选的角色、祖先及当前值。全部候选和返回 action ID 保留，执行侧快照/引用、
输入文本和效果检查不变。该压缩解决了实测 HTTP 400 `max_tokens_exceeded`；
压缩后十二次真实 Jev 选择和 AXPress 派发成功，但本批未完成算式目标，不能宣称
多步能力验收通过。决策错误事件保留 SDK 类型、HTTP 状态及原因类型，在结算停批
检查之前发出；pilot 按 task/call 保存，不保存原始正文/headers/凭据，不改变停止规则。


## S4-R4 语义执行记录与模型视图（2026-10-09）

宿主在 TaskRuntime 派发准入后、外部操作前创建不可变 `ExecutionStep`，保留动作与
目标语义、输入、rules/selector/advisor 来源、观察身份及派发/效果状态。进展保存
最近十条，编号仍按整个任务累计；完整派发回执仍另外保留。成功读回时记录所选字段
或该动作声明的读数/效果事实 before→after，缺失事实为 null、实际空值为字符串。
观察失败、取消、不完整或未就绪时不伪造变化；已尝试操作不会因后续异常消失。
变化是观察证据，不自动代表动作与变化的因果关系，也不代表整体目标推进。

`model_view.py` 统一 Jev、文本 selector 和 Advisor 的纯数据投影：发送
`state.recent_actions` 的动作语义与效果记录，移除历史 action/observation ID 和
可执行元素引用；模型进展用 `verified_action_count` 代替旧 UUID 列表。宿主原始
ActionSet、快照、授权和回执不变。模型候选使用本轮 `c1` 等短别名，Jev/文本 selector/
Advisor 返回后都映射回该次 ActionSet 的原始完整动作，不接受原始 ID 或伪造别名。
共享 `value_change_checks` 保存原有读数核验基线，候选用 `change_refs` 引用；它不是
预测结果，也不是历史变化。全候选保留，目标元素上下文和几何信息保留。宿主提案事件
记录候选集、别名与原始动作 ID，用于和派发回执关联。进一步视图实验和
置信度门槛仍分片验证。当前原生驱动与未知效果零重放
没有变化。本片验证是离线/假模型接线，不宣称真实任务选择能力已经改善。

## S4-R4 文本 Advisor 与目标进展复核（2026-10-07）

工厂显式 `advisor: llm` 启用 LLMAdvisor，借用核心任务文本模型与同一账本、权限、
取消和时限。输入为父任务上下文、GoalContract、当前观察/候选及进度/触发原因；
接受结构化候选动作、允许生成的缺失输入补充、有界规划 focus、补观察、需用户输入或无法处理。
模型不创建工具、不派发动作、不修改目标条件；候选走同一执行前校验和效果读回。
源为 user 的缺失值不猜测；缺失的 generated 输入可补齐，已有值不能替换。

2026-10-09 增加动态规划 focus（不是原生键盘焦点）：仅配置了 selector 时向模型提供
此能力。`FocusProposal` 包含短 objective 和 1–8 个精确事实谓词，宿主验证键来自当前
观察、原目标或候选核验依据，且尚未满足。`PlanningFocus` 由宿主绑定原 scope、目标
版本、提案观察和起始动作编号；先重新观察、重建候选，再交给 Jev/文本 selector。
模型只接收语义指导及已完成/失效历史，不取得旧元素句柄。focus 是期望，不能当作事实
或扩权依据；整体成功仍仅按原 GoalContract 判定。

focus 条件满足后完成并清除；三个准入动作仍未满足、重复状态、观察不完整、目标更新、
再次升级或任务结束时失效。模型看到 `progress.current_focus` 和 `focus_history`，
宿主历史保留观察身份。focus revision 区分同一画面上的新决策上下文，防止刚交接就被
视为无动作重复；四次 Advisor 上限及原任务计数不重置，纯规划空转仍有界。未知效果
直接停止并使 focus 失效，不借规划更新重复派发。完整恢复属 S4-G3（S6 前）；
规划稳定性已按原生矩阵与 NL live 收口，见下文「S4 收口」。

`unverified_goal_steps` 区分动作局部效果与目标推进。连续三次有核验效果但无新增
目标条件/结果条件或绑定输入证据时暂停普通选择，触发规划复核。一个已出现的目标
证据不能因反复切换而多次清零计数；复核本身不表示目标推进，只允许一个新的有界
选择间隔。没有 Advisor 时明确停止；最多四次 Advisor 调用，累计治理预算不重置。
动作后重访状态可请求有界修复；无新动作的重复观察停止。none 停止，歧义/需上下文
先只读补观察；未知效果不交给 Advisor 盲目重放。

该规则不是通用语义距离或数学错误判定器；无中间目标证据的合法长任务也可能需要
复核。文本接线有离线 SDK/原生边界、真实 Chromium 验证，以及经授权原生矩阵中
Advisor 纠偏后完成任务的证据。OCR/视觉后备与自动通道发现未实现（见 backlog）；
同进程完整恢复属 S4-G3（S6 前）。S4 能力主线已按证据收口，见策略阶梯计划。

## S4-G3 同进程等待用户输入（2026-10-17）

Supervisor给插件Runner注入可选`user_input`回调，`SubAgentContext.ask_user(question)`
在原协程等待答案，沿用同一个授权、runtime、用量账本、取消信号和期限。等待期间
每0.1秒检查原治理状态，答案到达后再次检查；取消、撤权、额度/期限耗尽会结束等待，
撤销尚未交付的答案并进入原有清理路径。它不是重启或从聊天记录重建任务。

Supervisor将同一行置waiting并保存问题，前台派发立即返回waiting及question；
任务保留在监督任务表，持有桌面锁和窗口绑定，仍占并发名额，可由stop取消。
前台转出的行持久化background=true，恢复及最终事件按后台投递，避免完成通知丢失。
wait可等待当前仍挂起的插件任务收束。桌面锁仅协调本进程中的Runner任务，不能
阻止用户或其它进程操作桌面。等待计入原期限，默认桌面插件600秒，不另给期限。

resume_with_answer仅向本进程中该task_id尚未交付的答案future交付一次，状态恢复
running；错误/重复/终态答案不重启执行器。持久waiting行没有活的等待future时
仍拒绝插件恢复，包括进程重启后；已有普通聊天恢复路径保持。

控制器只询问唯一缺失的source=user输入，问题取自purpose/field_label。可见字段
缺值且无已知待填值时优先澄清，不先选择其它导航按钮；尚不可见的字段仍可通过
导航显现。答案只作为该字段的字面value，原GoalContract验证后版本+1，重新观察、
重建候选；授权、约束、完成条件、累计动作/观察/回执和用量不重置。空答案、多字段
缺失或未注入回调时以needs_input结束；超出字段schema以invalid_user_input结束。
Advisor无键的needs_user_input仍为终态。未知效果在原路径停止，不因等待而重放。

隔离Chromium三布局使用真实Supervisor/Runner/SDK、fake模型HTTP验证导航后等待、
用户补值、原页面保存及独立服务端读回；这不是私人桌面或真实模型效果验收。
本片不涵盖G3跨任务资源生命周期、统一接入套件/能力清单或跨进程恢复。

## G3 能力与资源接线清单（2026-10-17）

以下为当前可信适配器清单，不增加权限或默认启用。工厂仍只接受显式browser或macos
配置；空配置使用unavailable通道。所有命令从backend执行，SDK网络/原生输入边界
由相应测试fake；隔离Chromium是实际浏览器，原生实机证据另列。

- **公共任务/资源治理**：`agents/task_runtime.py`、`task_resources.py`及
  `subagent_adapter.py`管理原授权、账本、执行审计、动作/观察、在飞操作和关闭顺序。
  每任务独立runtime，不接受另一task_id重绑；释放只针对已登记资源。借用资源登记
  detach回调，不关闭所有者。DesktopResource协调本进程Runner并在清理未知时隔离
  后续桌面任务；不承诺抢占线程或跨进程恢复。公共入口为
  `uv run --no-sync pytest core/tests/test_subagent.py core/tests/test_task_model.py core/tests/test_task_runtime.py core/tests/test_plugin_manifest.py core/tests/test_model_calls.py -q`。
- **宿主LLM/LLMAgent**：`llm/task_binding.py`创建借用SDK客户端视图，宿主持有原
  HTTP池，任务只拥有自己的调用包装和关闭回调。绑定前检查上下文存活、权限和
  task_id，关闭任务不会关闭宿主池或另一任务的在飞调用。LLMAgent仍通过既有
  Allowlist/ApprovalGate工具链，模型调用共享原任务账本；不把旧工具改成新策略。
  证据为公共入口的三个retained_callers、连续任务和跨任务在飞关闭测试。
- **任务文本模型**：`llm/task_model.py`由TaskRuntime配置并持有，首次调用才创建
  本任务AsyncOpenAI/HTTP客户端，任务关闭时释放。ModelSelector的文本选择/回退、
  LLMAdvisor及LLMIntake只借用complete，不拥有客户端，也不能改模型profile。
  SDK调用级准入/记账在`model_call.py`，不重复写为原生执行审计；相关契约为
  `core/tests/test_task_model.py`、`test_model_calls.py`及插件`test_jev.py`/`test_native.py`。
- **Jev Choice**：`llm/decision_model.py`持有官方SDK客户端，TaskRuntime登记该模型
  及`task_decision_model.py`调用包装的分别关闭；插件JevSelector只提交问题和候选。
  凭据与profile由核心解析，SDK拥有其HTTP默认行为，不声称宿主逐包拦截重定向/
  代理或证书。相关契约为`core/tests/test_decision_model.py`、`test_model_calls.py`及
  插件`test_jev.py`；新版图片/Box没有本插件接线。
- **DOM**：`channels/dom.py`的ManagedChromiumChannel任务独占driver/browser/context/page，
  由SubAgent资源集合关闭；不附着私人浏览器。旧引用受文档身份、scope和代次校验。
  `TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest plugins/agent-computer-use/tests/test_dom.py -q`
  覆盖创建/取消/断连/清理，以及同一Runner连续两任务的新页面引用和服务端保存读回。
- **AXPress/Quartz**：`channels/native.py`经`channels/apps.py`绑定进程/窗口，使用
  `observation.py`观察和`computer_ax.py`/`computer_use_macos.py`原生输入；操作必须走
  Controller注册的TaskOperation。通道只持有任务引用/指针状态并在关闭时释放，用户
  App不被终止；按产品规则启动的App结束后保留。测试harness对自建App进程另行拥有
  并负责关闭，不能把该行为推广到用户实例。`test_native.py`及
  [本版本原生fake实机](../../backend/benchmarks/computer_use/reports/20261017-g3-resource-native-fake/README.md)
  提供AXPress/Quartz/输入清理与独立读回证据；实机各case新建Runner，跨任务同Runner
  的生命周期由公共套件和DOM连续任务验证，不混称为同一证据。
- **AX/OCR与融合**：AXObservationSource是工厂原生通道的只读观察；`vision.py`的本地
  Vision观察和`fusion.py`的AX/OCR融合仅能受控注入，工厂无自动OCR/融合开关。
  OCR元素没有可执行动作，融合不会引入OCR动作/事实，不代表视觉完成核验已启用。
  `uv run --no-sync pytest plugins/agent-computer-use/tests/test_observation.py plugins/agent-computer-use/tests/test_vision.py plugins/agent-computer-use/tests/test_fusion.py -q`
  核对受控读入口；`uv run --no-sync python -m benchmarks.computer_use.s1_acceptance`
  只对固定合成PNG调用实际Vision，不截取私人桌面，也不证明生产自动回退。
- **拒绝与未接线能力**：manifest runtime_api与私有配置在创建任务资源前校验；未知
  配置拒绝，工厂不启动浏览器/模型/原生动作。`test_factory_rejects_unimplemented_configuration`
  与`core/tests/test_plugin_manifest.py`版本拒绝测试保留。Jev图片/Box、视觉Advisor、OCR生产回退和跨进程恢复
  不属于已启用能力；S5采用证据与生产默认不因本清单改变。

统一E2E入口为既有chat.feature的`lifecycle`案例：运行公共五文件完整套件；managed
Chromium场景另外验证两个连续任务。G3专项fake与常规E2E聊天连接开发服务的计量
边界保持，不将实验账本误作整个开发服务账单。验收结果见主计划G3第二片。

## S4-N 插件内自然语言 intake（2026-10-10）

工厂显式 `intake: llm`（仅 `macos`）在 `task_input` 无完整 GoalContract 时，用任务文本
模型一次调用读取 `TaskBrief`（application、objective、inputs 的 purpose/value、
completion 的 present/absent/title + value，或 unable 原因）。宿主确定性补齐为
schema_version=2 契约（`goal_id` 新生成、`authorization_ref=current_task`、
`allowed_operations=[click,fill]`、条件键 `ax:<type>:c<n>`），输入非 null 值须规范化后
出现在 request.task/context 原文中，否则 `needs_input`/`ungrounded_input`。父代理可附
`target` 覆盖应用名。完整契约路径不变；简述写入结果 `details.intake`。无模型时
`intake_model_unavailable`；非法回复 `invalid_intake`。调用计入任务用量。
2026-10-16 入口提示明确区分按钮/按键动作与文字填充值：动作写入objective/constraints，
纯按键任务提示inputs为空，文档中的字面符号与末尾换行仍须原样填写。该提示的模型
效果尚待独立对照，不是宿主自动纠正动作或放宽来源校验。仅intake解析接受一个完整
`json`/LF代码围栏；外围说明、多段/错误围栏、重复键及无效schema仍拒绝。消息构造和
parse_brief供生产与无桌面探针共用，无新增调用或重试；其它模型协议保持原有规则。
第二片
（绑定后看初始快照再写完成条件）因 live 未暴露缺口已移交 backlog。桌面 fake 后：绑定若声明了
`ax:value:result`，intake 的单一 `present` 会确定性对齐到该读数键；无 readout 的画像仍套用
危险词（与完全无画像相同），有 readout 才省略。

## S4 收口（2026-10-10）

S4 能力主线（DOM/原生通道、Advisor、动态绑定、通用完成核验、NL intake、端到端）
已按证据收口：原生矩阵 9/9 与 NL live 3/3 结案规划稳定性；OCR/视觉完成核验后备与
N第二片移交backlog；G3与G1-DS1已于2026-10-17验收。S5当前配置不采用，
S6按现行范围交付，生产默认与基线A不变。细节见
[策略阶梯计划](../plans/done/computer-use-strategy-ladder.md) “S4 收口”。

