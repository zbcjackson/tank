> 日期：2026-10-20。结论状态：资格诊断已解决；原生业务可行，编辑页视觉准入被不可见动画阻塞，修复与模型迁移比较待后续切片。

# 第二真实产品：linkding资格检查

本轮选定原版linkding 1.47.0并冻结两种新任务规格。4个原生脚本流程均能正确
保存并返回列表，但当前宿主在编辑页的16次图片准入全部拒绝，原因是隐藏的
无限loading动画。尚未运行V/JT模型对照，不能据此判断模型强弱、质量或速度。

## 产品、任务与实际执行

[官方项目](https://github.com/sissbruecker/linkding)是独立的书签管理器；
[官方安装文档](https://linkding.link/installation/)说明默认使用SQLite。
本机Docker引擎未运行，采用官方源码/锁文件的原生开发安装：`uv sync --frozen
--no-dev`、`npm ci --ignore-scripts`、`npm run build`、原生Django迁移。
不是手工重写页面，也未修改模板、JS、CSS或生产配置。

上游tag v1.47.0源归档SHA256为
`6ada53ec63abef00a02dac80444b6469d83bb3e9e9d3a40e70c638aa818bf48b`。
442份原始文件逐字节匹配；4份官方构建生成物单独保存，446应用文件在检查
前后不变。隔离Python3.13.5、Django6.0.7及26份依赖版本/uv与npm锁文件保存
于归档。未将产品依赖加入Tank。服务仅监听127.0.0.1，以并发WSGI和官方
StaticFilesHandler承载原应用；开发DEBUG与长连接存在，不等同于生产部署。

仅创建合成账户和两条`example.test`书签，默认列表顺序id2、id1。登录会话是
测量前设置，后台任务按[官方选项](https://linkding.link/options/#ld_disable_background_tasks)
关闭。原版前端组件使用light DOM，本次无iframe或shadow-root准入缺口。

无模型资格协议在执行前写入全新目录：两个目标位置，各2个独立浏览器上下文，
共4流程；每流程检查列表、编辑页、填入后、返回列表4状态，各立即与额外250ms
后新观察一次，共32观察。**操作由脚本选择Edit、填标题和Save**；没有Controller
动作闭环，也没有模型SDK配置或请求。250ms后重新观察是预声明诊断条件，不是
模型重试或补跑。

脚本流程4/4完成，32/32观察完整，四个浏览器/TaskRuntime及专用服务清理确认。
每项独立核对保存前后物理SQLite，所有`bookmarks_*`表的完整行/字段和schema：
仅目标标题及服务自动更新的`date_modified`变化，时间必须增加；其他书签、
URL/描述/标签/关联及其他字段保持。HTTP每项恰一次正确编辑路径POST/302，
此前有列表→正确编辑GET、此后有列表GET；真实DOM显示新标题及未变记录。
没有加SQL写触发器，不能据最终状态与单POST进一步宣称恰一次SQL UPDATE。

## 资格结果与机制

- 列表/返回列表共16次：12候选、`visual_required`，16/16图片准入通过，所有
  候选bounds位于1280×720视口内。
- 编辑页共8次：5候选、`jev_eligible`；填入后共8次：6候选、包含Save且
  `jev_eligible`。两类共16次图片准入均报`unstable_visual_frame`，不是模型拒答。
- 两条Edit都只有`Bookmark list/Bookmarks`祖先，没有所属书签文字；重复keep
  标签的语义身份完全相同，触发当前整组`visual_required`。完整列表事实仍在
  公共观察中，不能把“Edit缺所属祖先”误写成“没有任何记录文本”。

宿主`ManagedChromiumChannel.capture`对`document.getAnimations()`的所有
pending/running动画等待最多250ms，再检查是否仍存在；目前不区分不可见目标。
原版表单的`i.form-icon.loading`经computed style为`visibility:hidden`，但
`.loading::after`仍有500ms、无限循环的loading动画；这是编辑页唯一活动动画。
四流程中相同拒绝重复出现，增加250ms后仍不消失。

另用一个新上下文做5次只读归因检查：不取消动画、不改变产品样式，沿用宿主
已有caret处理。5/5捕获仍拒绝；5张1280×720 PNG字节完全一致，SHA256为
`308c1d0fdf9064eb0beb8c2d06e504294eb9b9824e5855105acc64d1879ed206`。
动画目标、computed style、所有祖先可见性、DOM revision与PNG均保存。
源码条件和该状态的唯一活动动画支持“不可见动画被运动门误拒绝”的机制判断；
5张相同PNG不证明任意动画或未来页面都稳定，也不能据此停用运动/新鲜度守卫。

V需要在编辑页合法读图；JT当前列表也需图片，在编辑页若文字弃权仍需同一图片
路径。当前可确认的是比较前提存在宿主缺口，不能把此时V的编辑页准入失败
解释为Jev视觉更强。实际仍为零模型调用，不报告成功率差、速度或费用优势。

## 新任务冻结与下一步

归档`qualification/task-freeze.json`冻结两种列表→编辑→返回任务、拟议4项
V/JT顺序（顶部/底部各一对、平衡先后）、公开输入与独立业务验收。源33文件
快照、4份资格脚本、运行/产品版本和构建hash均在其中。声明式digest为
`6e3532ed8eea83069e7dfc09d0fdfb53ffba20e0fd7467a79a74bb01524f819e`，
`model_execution_eligible=false`，不是可执行收费批准或已准备好的模型运行器。

后续验收按书签身份核对列表，不要求固定返回顺序；允许目标`date_modified`
增加，其他字段/关联/schema不变。必须正确编辑路径、单次成功POST、真实返回
列表及独立DB/HTTP共同成立，禁止未知效果重放POST。认证仍在测量前完成。
现有资格脚本中的期望completion只用于候选构建，没有被当成实际业务事实。
真正Controller迁移配方还需补真实只读业务回执/阶段观察，不能直接拿本脚本跑模型。

下一行为切片先在既有test_dom.py红测复现隐藏无限动画误拒绝，最小修复截图
相关动画的准入判定；测试可见无限动画仍拒绝、有限动画等待、伪元素/可见性
变化及像素/引用变化仍拒绝，扩展现有managed Chromium E2E。不得简单屏蔽
loading类、取消页面动画或放松exact PNG/ref校验。全套验证与独立审查通过后，
重新资格检查，再做新的可执行源/依赖/应用/任务freeze和一次V/JT比较。

沿用record-only及既有接收方授权，后续每任务120秒/6动作/24观察、SDK零重试，
未知用量/运行/审计/清理失败停批，全部分母保留。第二产品仍只有两个已见
开发任务，独立采用确认由[主计划](../plans/active/computer-use-jev-vision.md)承接。

## 归档与验证

基线38bc1eba，资格计划249d42ea。新
[归档](artifacts/jev-second-product-qualification-20261020.tar.gz)172成员，
6,796,222字节，SHA256
`adecf722acac0673aba12768273545dce0def7f1d731a93eacdfa1c8ac64570c`；
[manifest](artifacts/jev-second-product-qualification-20261020-manifest.json)
逐项列出字节/hash。41PNG＝32资格图＋5归因图＋4早期探查图，不能当41任务。
21个实际凭据值扫描无命中，15旧archive/manifest逐项不变。合成账户的数据库/
会话仅用于已关闭的本地实验，不能混称为个人凭据。

早期设置/探查失败单列于`discovery.json`：cookie名、单线程长连接、错误尾斜线
404/等待以及Fact序列化问题，修正实验脚本后才开始4项资格协议。早期目录曾
重用，中间探查图片并未完整保存；残留文件只能作不完整诊断，不称完整试验原档。
全新资格和归因目录保留协议规定的全部流程/观察，未删除其中失败项。

独立分析脚本不导入宿主评分器，重算4物理DB/HTTP/DOM流程、32准入、5像素
归因、全部来源hash及旧15档一致。仅docs/归档变更，按项目例外不重跑未变的
后端/E2E；docs检查及diff通过，面板TypeScript noEmit通过，未声称宿主UI渲染
验收。

第1轮独立review-and-refactor（基线38bc1eba，完整任务至50fd2234）从原始
物理数据库独立复算四组10个bookmarks表/全部字段/schema、单POST302/HTTP/
返回DOM，核验32观察及16次capture_motion关联、5次隐藏动画/同字节像素、
33源/4脚本、442原文件+4构建输出、172成员/41 PNG、旧15档/清单及21凭据扫描。
声明式freeze及eligible=false、面板内嵌数据/图像和筛选/类型检查均通过；仅明确
JT当前列表同样需图，避免把“编辑阶段可能靠文字”扩成整个工作流无需图片。
未发现本资格记录的确认缺陷或遗留审查问题，立即结束；没有新增模型调用或
修复宿主行为。隐藏动画阻塞仍由下一切片处理，不能把资格审查通过称为视觉
准入已通过。收尾文档仅评审者自检，无后续独立复核。
