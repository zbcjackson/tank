> 日期：2026-10-20；结论状态：已解决（候选遗漏与列写入语义诊断完成；真实模型收益待新实验）。

# sqlite-web逐列复选框与列写入诊断

## 结论

旧流程确实遗漏了三个同名原生复选框，只向模型提供唯一具名的全选框。现已按
实际DOM节点补齐checked事实与动作效果，并把唯一原生表单name作为字面上下文。
同一原始页面的逐列候选从0变为3；没有产品专用selector或人工重标页面。

“其他字段最终值不变”和“SQL仅写title列”是两个条件。实际全选路径会触及
id、title、notes三列，即使id/notes最终值不变；仅选title路径只触及title。
两条路径都能通过旧value-only条件。本轮没有据此重判旧实验：V6/6、JT5/6，
42请求及其失败、用量、费用全部保留。候选遗漏是已确认缺口，尚不能认定它是
旧Jev none和随后Gemini none的唯一原因。

本轮12个隔离上下文、36次实际UI输入、44张任务PNG，模型调用0、模型HTTP
客户端构造尝试0，12项清理全部确认。这是脚本功能诊断，不是模型成功率，
不能证明Jev比视觉模型更准确、更快，或证明修复已经改善旧模型失败。

## 证据来源与方法

使用已安装的未修改sqlite-web0.8.1及其654项应用环境文件，每例新建合成
SQLite数据库、上游app进程和隔离Chromium。页面、JS、CSS及应用源码不改。
新增列级审计触发器只存在于新夹具数据库，记录每次UPDATE OF列的实际旧/新值。
SQLite的[UPDATE OF触发规则](https://www.sqlite.org/lang_createtrigger.html)
取决于SET左侧出现哪些列；旧值与新值相同仍可触发。本轮逐列审计也实际观测
到了这种差异，没有从最终值反推SQL写列集合。

- 修复前：4例，两个数据顺序×全选/仅选title，12次输入、12张PNG；保存各帧
  DOM候选、checked与bounds、前瞻decision_question、HTTP与物理数据库。
- 修复后：同样4例，加4例经过真实Controller的受控有限候选提议路径，共8例、
  24次输入、32张PNG。manual表示脚本直接驱动原生UI；host表示脚本提议由
  宿主派发，两者都没有LLM。仅诊断脚本使用原生name选择器，生产实现不含它。
- 每例均勾选一次、填标题一次、提交一次；实际HTTP恰一次POST，数据库恰一次
  UPDATE。四组对应manual初始PNG前后逐字节相同，证明页面视觉输入未被修补。
- before/after分别保存35份实际运行源码；before驱动是尚无host路径的较早版本，
  两阶段各按自身freeze核验，不把before源码当作当前实现。生产DOM/ActionBuilder
  的before字节对应基线3ecbe7f0，after对应实现c76af867。

原始路径为`/private/tmp/tank-checkbox-before-20261020`和
`/private/tmp/tank-checkbox-after-20261020`；两阶段冻结digest分别为
`1ac1b883d38ab933ff1b0e6bfd5953465f6f7bca7d7d779d564a5d4b9c4a1e5c`、
`a94d9f4f02d8cad1ac1b1407e6574e52e800c640f8cf012f3a10dd1c991affbd`。
宿主候选/PNG与前瞻问题是本地诊断记录，不冒称SDK已发送的请求。

## 修复的行为与边界

唯一具名原生checkbox保持原checked效果路径。同名checkbox改用完整实际DOM
ref的SHA256构造宿主保留的`dom:checked:`事实键，单次click必须读回同一节点
的实际checked变化；页面不能用role事实伪造这个命名空间。preventDefault、
节点替换后新节点勾选、仅有目标终态都不能替旧节点确认效果，也不会重放输入。

对唯一原生表单name，候选明确显示原始字面上下文，例如
`Allow updating this column. [name=chk_title]`。不猜测name代表何种业务列；
重复/缺失name不补虚构语义。宿主在语义身份比较时规范化节点绑定key，不能
因为两个opaque key不同就认为目标可区分；无其他区分上下文时仍需视觉，
非视觉配置返回ambiguous_target。人工注解与原生label碰撞也保留歧义。

修复后受控host-title两例均goal_verified。host-all两例虽然最终值正确，
在额外要求`status:Written columns == ["title"]`的强目标下均effect_unknown。
这两例已经实际提交并触及三列，宿主随后拒绝确认完成，没有重放；本结果不代表
在派发前阻止全选、不代表回滚，也不是任意业务副作用保证。读回来自实际mode=ro
数据库状态，不读取goal/oracle；强列目标仅用于本诊断，未偷偷改变旧评分协议。

驱动在每个下一案例前校验冻结文件与后端源哈希，案例结束校验应用环境源哈希；
检测到漂移即使已有UI输入也保留该事实并停止后续排程。取消保存已尝试行及未运行
分母，清理与最终读回延后重复取消，关闭资源后再抛出；没有吞掉已写数据库的事实。

## 归档与独立重算

[归档](artifacts/jev-checkbox-grounding-20261020.tar.gz)包含869成员，6,273,981字节，
SHA256为`38ac24e835fe557fc4df1a2d19ba7e73689cfd8550bbe30388eb3db00203e89b`；
[manifest](artifacts/jev-checkbox-grounding-20261020-manifest.json)逐项记录大小/哈希。
62张包内PNG中44张为本轮任务捕获，另18张属于未修改的应用环境资源。

独立分析脚本与summary保存在包内analysis/，不导入宿主评分函数；重算freeze、
归档源码、654项环境字节、物理数据库全部行/schema/审计旧新值、HTTP、候选
实际ref绑定checked与标签、host提议/回执、PNG和0模型计量。12项清理确认，
4组初始图相同，候选0→3、title-only与all写列差异均一致。打包前对21个实际
凭据值扫描无命中，并按基线核验原12份archive及manifest未改；不输出凭据。

## 验证与审查

11项新增回归按red→green通过，覆盖节点/语义歧义、原生name、阻止默认动作/
替换节点、保留事实命名空间，以及真实产品脚本、强列回执、取消与冻结篡改。
稳定实现完整后端6422 passed、1 skipped、21 warnings（607.06s）；设置
TANK_REQUIRE_CHROMIUM=1及固定TANK_REAL_PRODUCT_PYTHON，未以缺应用环境跳过
本轮诊断。现有E2E21 scenarios、83 steps全部通过（154.953s），managed
Chromium场景包含46项宿主契约。

web lint与tsc -b --noEmit、backend/CLI ruff、全部4份修改Python的pyright
（0 errors/0 warnings）、tmux重载错误检查（空输出）通过。协议及生成物未变，
协议同步检查不适用。最终docs75与git diff --check通过；面板按实际SDK声明做
TypeScript noEmit检查0诊断，未做宿主UI渲染验收。独立review-and-refactor待
收尾补记，目前尚不宣称审查通过。行为验证日志保存在归档verification/；
此后仅补报告/索引/审查记录，未改已验证的实现源码。

## 下一步

已仅prepare新的12项真实模型开发配方，目录
`/private/tmp/tank-checkbox-route-ready-20261020`，digest为
`8b36857c1ab5dd0fed263e410a833cfe849fa6ce69633fc9aabc2df7ea8b90b7`。
仅有freeze，没有started/result/spend；34份执行源已冻结，没有模型调用。
源码若被审查修改，必须另建冻结目录，不能修补此freeze。

下一步在修复后的新候选上做V/JT开发对照，检验模型是否会利用逐列上下文，
报告全部成功/失败、路由、时间与用量。该配方仍沿用旧value-only条件，属于
已知开发案例，既非独立holdout，也不是“仅写title列”的模型实验；如需后者，
应先单独冻结新目标/核验协议。旧模型结论和生产默认保持，跨页/第二产品、
Jev图片/Box增量与独立采用确认继续由主计划推进。
