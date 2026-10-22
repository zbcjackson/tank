> 日期：2026-10-22。结论状态：资格调查及第1轮独立审查结案；原生96/96通过，Controller模拟资格未通过；正式N仍未准入。

# V/JT新任务库与执行器资格

## 结论

新任务在原版应用上可以完成，但现有Controller尚不能获得执行资格。全库24576
份目标结构解析通过；固定48组seed的96份冷/预热目标，原生业务、候选、416张
PNG及清理全部通过。随后显式MockTransport模拟矩阵保留192行，首项V通过，
第二项JT在Retry导航后以`no_viable_actions`退出，190项未运行。不能把1/2或诊断
重复的结果解释成模型成功率，也不能把原生96通过推广为全库原生资格。

失败跟踪发现：观察仍是旧故障页的Retry节点，URL及编辑器投影已经更新，观察
却标记ready/complete。该Retry已无可验证导航效果，候选为空。两次预声明固定
跟踪一次成功、一次复现，支持观察一致性存在时序缺口；具体失效边界仍须下一
切片用确定性TDD定位。当前不启动补充校准、正式确认或改变策略默认。

## 冻结、组成及原生证据

任务基线5b5dc713。输入为上一轮已审查的
[保留库](jev-confirmation-design.md)，源档91成员、36运行源及全库字节均核验。
按原规则正例每层rank0–3、负例每层rank0–1，固定40正例+8负例seed，两条件
共96目标；两臂按原先后顺序排192次。未挑换失败任务、改提示、改产品页面或
把这些脚本资格当作确认测量。只是新合成数据，仍是原两应用、四记录和ID1/4。

原生`run-v4`96/96：80正例各一次正确业务POST并返回完整列表；8缺目标业务
不变；8撤权守卫拒绝输入且业务不变。96清理，96列表候选准入；416张原始
1280×720 PNG逐份核验。GET故障仅注入指定读路径，POST不重放。独立审计直接
读取物理before/after DB，核对SQLite写日志、Linkding全部10张业务表、HTTP、
完整返回列表和图片；不复用Controller评分函数。

原生驱动的早期清单字段错误、finally断言遮蔽原错误及登录重定向均保留。首次
`run`未进入任务，`run-v2`保留首项物理DB但原驱动未写完row，`run-v3`15项失败/
15清理后主动中断。修正新驱动入口/错误记录及代理认证时序后以新freeze重验
全部96项，不覆盖旧目录。产品与36运行源未变。

## 网络替换缺口与纠正

早期`run-v4/fake`在第2项停批。5次请求由模拟HTTP响应，另1次Jev SDK调用绕过
Mock，使用字面假凭据`qualification-fake`，得到映射HTTP401的
`TypeSafeAuthenticationError`；SDK max_retries=0。未加载真实模型凭据、未取得
真实模型输出，但这仍是一次未Mock的外部调用。原账本`unknown_usage`和请求/
事件保留，不据认证错误猜测用量或释放未知项。原回执硬编码
`external_model_requests: 0`对这次中止批次不成立；单独`network-incident.json`
勘误，不重写原证据。本轮不能称为零外部请求。

原因是httpx2默认传输不读取被替换的公共`AsyncHTTPTransport`；现有仓库测试的
autouse fixture还替换了AsyncClient构造，独立脚本没有继承该fixture。已将研究
驱动改为给真实httpx2.AsyncClient显式注入MockTransport，保留SDK创建和协议
解析；另加Python非回环connect拒绝及独立子进程SDK回归。8项研究回归通过。
独立进程回归使用`.invalid`地址且禁Python DNS，必须收到两次本地模拟响应。
前期pytest路径/async标记、端口沙箱、探针参数和诊断序列化失败日志均保留。

`run-v5`仅改变fake HTTP接线。目标、原生驱动、代理、应用、36源及原生实际
使用的verify函数AST与run-v4一致，`native-reuse-bridge.json`记录逐项哈希，因此
复用原生96证据，不重复原生实验。首簇已存在认证失败的外发事实；未来预注册
必须保留此来源记录，不能悄悄换簇后声称整个库从未外发。

## 显式模拟批次与失效证据

最终`run-v5/fake`计划192行、尝试2行、1通过/1失败、190未运行、两项清理确认。
6次模拟SDK调用（V4次，JT2次），5次图片调用，60个模拟tokens，已接收用量
均已知。本批模型HTTP均为模拟；与上一节认证失败调用分列。32项负例全部未
运行，不给负例通过率。正例失败保留DB不变、无业务POST，不能计为成功退出。

固定失败任务为`hold-v2-a585ef03eac8ab04cb1e-cold-jt`，场景linkding/recovery-editor。
V正确编辑目标1；JT先点Edit再点Retry，之后无可用动作。另做两次固定JT跟踪，
`diagnostic-v2/0`成功，`diagnostic-v2/1`复现。更早诊断因JSON序列化中断，也有
失败回执，不能删除后只报告一次成功。三者均不并入主矩阵，不自适应追加到通过。

`failure-evidence.json`中的关键读数：

- Retry前后generation为3→5，节点ref完全相同；后快照ready=true、complete=true。
- 后快照仅1个元素，仍为Retry；`click_effect=[]`、`click_changes=[]`、
  `click_observable=false`，ActionBuilder输出0动作。
- URL为`/bookmarks/1/edit?retry=1`，额外投影已经读到目标1的编辑器及原始标题。
- 原生DOM代码只在destination不等于location时给普通链接添加Page URL效果；
  readyState不为loading便可标为complete。上述轨迹证明单靠generation和该
  complete条件不足以排除这次混合观察，不把尚未实现的修复说成已验证。

独立物理/HTTP/PNG审计核对主矩阵两行及192行顺序/未运行分母，确认V只有一次
正确POST，JT无POST且DB不变；6份SDK请求均对应公开目标/输入，不包含私有
oracle/seed字段。目标的SDK规范化默认值与原始JSON结构不同，按公开身份、
intent和输入字段核对，不误以JSON逐字不同判为泄漏。5张PNG完整核验。

## 验证与下一步

8项研究测试、全库静态审计、原生96物理审计、部分模拟矩阵及两次固定跟踪、
面板tsc通过。Controller资格本身未通过，不把这个实验结果改称绿色验证。
本任务只变更docs/和研究工件，按docs-only例外不重跑未变的后端全套或E2E。
后续先TDD修复Retry导航后的文档/观察一致性：DOM元素、URL、投影、候选和
图片须绑定同一就绪文档；补确定性失败与正常恢复回归，再以新freeze重跑完整
原生及192 fake资格。统计评分器接线、补充校准预注册及正式N仍由
[主计划](../plans/active/computer-use-jev-vision.md)承接，760+152提案不自动执行。

完整脚本、freeze、原生/两次中止fake、诊断、物理DB/HTTP/PNG、独立审计及
面板在[归档](artifacts/jev-confirmation-qualification-20261022.tar.xz)和
[逐成员manifest](artifacts/jev-confirmation-qualification-20261022-manifest.json)。
Linkding逐trial原源hash核验并只存一份；工作库不重复打包，保留物理前后备份
及完整读回。SQLite安装环境由freeze逐文件hash和此前原产品归档证明，非完整
环境镜像。旧22归档/22manifest共44文件保持。

归档2759成员、16940164字节，SHA256
`8007375903989adbba9ab39b3dcfbb1c0a9c7b09de549afeb1e5012d7655559c`。
71份逐trial应用源逐文件hash一致后去重；21实际凭据值零命中。面板数据来源为
实际审计及失败轨迹，tsc通过，未声称宿主UI渲染验收。

第1轮独立review-and-refactor未发现可操作或遗留问题，按规则结束。审查员核验
完整任务diff、全部归档成员、21实际凭据零命中、44旧文件及基线Git blob、5个
freeze、91设计成员、36运行源、全24576目标、416PNG完整解码及71份应用源；
重跑8项研究测试（8 passed），隔离重放原生/fake审计与原结果逐字段一致，
核对网络事故unknown_usage/401和固定诊断证据、面板内联数据及tsc通过。没有
新增外部模型调用或生产修改。[调查子计划](../plans/done/jev-confirmation-qualification.md)
结案及链接收尾仅由评审者自检，不把资格失败改为通过；运行时修复仍待下一切片。
