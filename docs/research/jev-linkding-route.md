> 日期：2026-10-20。结论状态：真实四项与独立复算完成，待第2轮结果审查；两臂均成功，本批JT更快少图，尚非采用确认。

# linkding真实Controller迁移对照

原版linkding1.47.0的两种改标题任务，V/JT各2/2通过严格业务验收。完整耗时
均值V34.614秒、JT12.047秒，本批JT低65.20%；图片请求V6次、JT2次。
这是第二真实产品的正向开发证据，不能由各两项单次观测推成普遍准确率、模型
排名或默认采用。列表阶段两臂都调用Gemini，JT在编辑页才使用Jev文字。

## 修复、资格与执行边界

承接[原资格记录](jev-second-product-qualification.md)：隐藏无限loading动画
曾让编辑页16/16图片捕获拒绝。本轮宿主只排除可确认的空内容、无marker、
computed visibility:hidden的before/after CSS动画，且报告关键帧和可读CSS
定义都只含transform/opacity。CSS自定义属性可能被getKeyframes省略，因此
必须同时检查定义；不可读、超4096规则、普通/程序/可见/未知效果继续保守。
没有取消动画、特判loading类或放松精确PNG、节点身份、导航与授权守卫。

新目录无模型资格v2完成4原生脚本流程、32完整观察和32图片准入，编辑页
0/16→16/16；额外5次动画样本也可捕获。全部32配对PNG与旧图字节相同，
5张归因PNG仍同hash `308c1d0f…9ed206`。这只是资格恢复，不是模型成功率。
v1在首个页面请求前因HTTP日志未初始化失败，4项均未运行；保留0观察及
保守cleanup=false原记录。另一次准备的工作目录错误也保留，未重写旧freeze。

模型比较复用共享真实产品生命周期，产品适配器仅管理隔离fixture、原生WSGI、
实际观察与独立评分。每项复制446份原版源/官方构建文件，官方迁移、合成账户/
书签及认证后由Controller从真实列表执行。初次认证GET初始化默认设置，再保存
初态物理DB；完整计时包含fixture、浏览器、SDK、捕获、核验和关闭。原应用、
模板、JS、CSS不改，未将Django等外部fixture依赖加入Tank。

两臂共享公开目标、候选、真实只读Records投影、当前可见列表及实际观察到的
编辑器URL历史。观察者不读取私有oracle或把目标比较结果伪装成事实。强评分
独立核全部10个bookmarks表/字段/schema，正确编辑器、单次正确POST302及
真实返回列表；仅目标title和自动递增date_modified变化。其他值/关联保持，
不代表SQL只写title列或恰一次SQL UPDATE。

第1轮实现审查覆盖完整基线21786a87→2a7eb81b，未发现确认的源码/测试缺陷；
2dfafd8e只更新计划状态。随后全新目录冻结35份执行源、446应用文件、4687
环境文件及两种目标任务，digest：
`2b5d47b74bcc5c5e543a8e176a5568177b4fbf1a94ff7b5118359d46ed5394e2`。
固定顺序目标1-V、目标1-JT、目标2-JT、目标2-V，各臂先后各一次；未补跑。
继续已授权的record-only无固定批次上限，每项120秒/6动作/24观察、32MiB
参数限制、SDK零重试，未知用量/运行/审计/清理失败停批并保留全部4项分母。

请求profile固定为Jev1.14.0文字到TypeSafe，以及Gemini3.8-flash的PNG＋同样
文字到OpenRouter；不是Qwen。本记录描述请求的profile，不额外断言供应方
实际内部部署版本。两臂都有额外结构及业务事实，不能称纯像素能力排名。

## 真实结果与路由证据

- 目标1-V：48.143秒，Gemini选择Edit、Title、Save，3图片调用；SDK耗时
  43.582秒，其他4.561秒，27,228已知tokens。
- 目标1-JT：11.285秒，Gemini列表Edit→Jev文字Title→Jev文字Save；SDK
  7.490秒，其他3.795秒，26,701已知tokens。
- 目标2-JT：12.809秒，同样图片→文字→文字；SDK9.172秒，其他3.637秒，
  26,677已知tokens。
- 目标2-V：21.084秒，Gemini三步；SDK17.042秒，其他4.043秒，27,298已知
  tokens。V本批波动明显，不能把均值差外推为稳定固定加速。

每项3次实际输入，全部派发sent且效果verified；4/4业务、当前列表及清理
通过。12次SDK调用中Gemini8次、Jev4次；8张实际请求PNG加4张最终PNG，
不是12个视觉任务。总107,904已知tokens（V54,526、JT53,378），无未知、
重试或控制弃权。SDK elapsed包括网络/服务等待，不能称纯模型推理时间。

列表中重复keep标签触发整组visual_required，所以JT两次直接进入Gemini；
不是Jev拒绝后视觉兜底。到编辑页重新判断为jev_eligible，再回到Jev文字。
本批没有none/ambiguous/need_more_context/escalate，没有同binding弃权后接管。
模型只返回候选cN，候选bounds来自宿主；没有测Jev图片或Box生成能力。

按freeze历史单价估算V为USD0.05050155、JT为USD0.024781788；OpenRouter
响应报告的Gemini费用分别USD0.04591050、USD0.02148600。两种口径不同，
后者不含Jev，均非账单。record-only账本未配置的nano费用记0不表示免费；
没有将失败fake批次的未知费用猜成0或并入真实模型统计。

## 接线测试与失败记录

真实应用/Chromium/SDK、fake外部HTTP的20项专项通过，包含四项正例、私有
oracle投毒、错误记录、完成后实际DOM缺/错/错页、源篡改、非法已知回复、
未知用量、重复取消、审计/关闭/fixture IO失败；停止时四项分母完整。
单独保留fake-v2四项4/4、12模拟SDK、8图片、120假tokens，不当模型指标。

fake-v1独立驱动漏装pytest自动提供的TypeSafe SDK HTTP边界，首V模拟完成，
首JT在Jev处未知停止；保留2运行/2未运行、5次SDK尝试/1unknown。只传占位
凭据，没有加载有效用户API凭据，但不能冒称零网络或真实模型选择失败。
修正驱动复用共享测试HTTP边界，另冻脚本/新目录fake-v2，生产SDK默认不改。

完整验证：后端6489通过/1跳过/21警告，强制Chromium及两个原版外部产品；
E2E21场景/83步骤通过，含75项Chromium契约。web lint/tsc-b、backend与CLI
ruff、4份改动Python pyright0错误/警告、前后端重载检查均通过。新增24项动画
回归；早期E2E包装45秒不足和一次远端ASR超时的失败日志保留，修正包装等待/
独立诊断后完整重跑通过，未根据一次远端超时修改ASR。协议没有变化。
真实执行后未修改执行源，结果文档只重跑docs检查；面板TypeScript通过，
初次面板字段声明错误日志及版本保留，不冒称做过宿主UI渲染验收。

## 归档、复算与后续

独立分析不导入宿主评分器，从物理before/after DB、实际DOM/编辑器历史、
HTTP时序、SDK请求事实/choice/PNG/候选bounds、调用账本和耗时重算，四项
与宿主结果一致。无模型资格、两次fake和真实批次各自分列，保留所有原始
freeze、失败设置记录、阶段源码/驱动/依赖环境、验证日志与面板快照。

[归档](artifacts/jev-linkding-route-20261020.tar.gz)及
[逐成员manifest](artifacts/jev-linkding-route-20261020-manifest.json)提供完整证据。
归档9741成员、64,265,409字节，SHA256
`b3e70e0055ac23f042db472df5154bb7e9aae63ffa628719d9740f8204042ace`。
21个实际凭据值扫描零命中，16旧archive及其16份
manifest逐项保持。两个含其他会话内容的宽ASR tmux日志未归档；合成本地
fixture会话不是用户凭据。派生面板的初次打包副本留在本机，最终包保存初次
类型错误、初次面板及修正后版本；没有重跑实验以修正展示问题。

下一步由[主计划](../plans/active/computer-use-jev-vision.md)预冻结未见任务与
独立确认协议，再检验质量门和净收益；生产默认仍不变。仅写title列的强目标、
Jev图片/Box增量和Qwen契约属于不同验证问题，本轮没有顺带作结论。
