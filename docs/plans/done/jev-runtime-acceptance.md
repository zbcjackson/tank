> 状态：已完成（2026-10-24：资格阻塞诊断结案；第1轮独立审查无发现，缺口未修复、真实实测0/6未准入；实测前置及中性命名验证交backlog。）

# 动作级实验配置的原始DOM闭环验收

## 目标与范围

承接[主计划](../active/computer-use-jev-vision.md)、[已完成接线](jev-action-runtime.md)
和[边界研究](../../research/jev-action-boundary.md)。使用一个已有真实产品的隔离副本，
六项固定任务各一次，通过真实AgentRunner及显式jev-action-vision工厂。
生产源码、默认配置、模型profile及历史工件保持不变；临时配方与原始证据封存到研究工件。
模型只获得普通DOM通道观察；数据库仅在测量外用于初始化和事后独立核验。

六项为文字正常操作、视觉接管操作、目标缺失、同名歧义、缺少用户参数，以及标题含
误导词但目标实际存在。负例使用中性名称，不因Absent/Shared词义提供拒绝线索。
此前backlog的中性命名条件项在此触发并由本计划承接，尚未验证的限制不能移除。
视觉需求先核对原产品候选，不人为让Jev错误/弃权，不改页面标签或注入状态。

## 步骤

1. 读取原版产品页面的普通DOM快照，核对完成事实与Controller允许的完成条件。
   使用真实Runner、原插件及假HTTP作资格；先复现，再补最小诊断/输入冻结。
2. 若原始观察不能支持所需业务完成/进展核验，保存精确复现并停止实测准入，
   不用URL到达代替业务完成，不导入benchmark数据库事实，不放宽完成或派发规则。
   此时交付宿主缺口及具体修复入口；六项仍保留计划分母，未运行不算模型失败。
3. 资格通过才冻结公开输入、接收方与调用上限，并执行一次六项真实调用；沿用既有
   Jev文字/可替换视觉profile，120秒/任务、6动作/24观察/32候选、零SDK重试。
   未知效果/用量、未释放预留或清理失败停批，不续跑或改任务凑通过。
4. 独立核对业务记录、派发、路由、SDK用量及清理，区分宿主完成与业务实际完成。
   本片是闭环可用性验收，不作模型总体准确率/速度优越或生产默认采用结论。
   更新研究、主计划及索引，通过适用验证和最多3轮独立review-and-refactor后结案。

## Tests

诊断配方先用一个可失败的行为断言确认原始DOM完成契约，再通过真实产品/Chromium/
Runner假HTTP重现；不得伪造角色、重写DOM、替换Controller或给模型私有oracle。
保留六项任务与逐项准入状态、零真实调用证明和所有实际失败。若无生产行为改动，
不增加镜像策略测试；临时配方按实际执行路径验收，源码与数据一起封存。

## 实际结果与交接

[定向研究](../../research/jev-runtime-acceptance.md)记录参考保存已成功，但status:*只有URL；
真实Runner固定正确候选后DB已改对、宿主effect_unknown仍保留。已有textbox事实作
completion被提前拒绝；URL弱化条件可在0写入时满足，不能用作业务修复。
三项独立诊断最终4次假SDK、全部清理；独立读取证据的五组断言通过。
六项仅保留意图清单，视觉任务未完成自然需求资格，真实输入/接收方/预算未冻结，实测0/6。
临时脚本准备失败单列保留，既不算模型失败也不算成功样本。

生产缺口未修复；后续应先接通公开DOM业务谓词与保存后核验，再重新资格六任务。
实测与中性命名验证移交[backlog](../../backlog.md)，本片不继续扩为生产行为修改。
仓库仅docs改动，执行docs-only检查；默认配置及原74工件SHA不变。

第1轮review-and-refactor独立审查无可操作或遗留发现、无修复，按规则结束。
审查者独立核对268归档成员、75源码、654环境文件、原始DB、三项Runner、调用及签名，
五组断言、115文档与完整diff检查通过；3个端口明确ECONNREFUSED。
原始审查全文及SHA绑定至工件manifest；归档字节不变。协调者仅自检结案状态/链接，
不把该闭合称为新增独立审查。步骤3条件未满足，六任务留在backlog，未补跑付费批次。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest（Chromium及既有两产品资格环境）。
5. cd backend && uv run pyright <改动Python>，不加type-ignore。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出通过。
8. cd test && pnpm test；如运行则用本地Sherpa/回环模型/隔离DB并恢复原服务。
9. python3 scripts/check_docs.py、git diff --check；原工件/默认配置/运行源码SHA、
   真实产品与Runner证据、用量/清理、签名和归档逐成员验证。
10. python3 scripts/check_protocol_sync.py；协议未改则不适用。

仓库仅docs改动时遵循docs-only例外，仅步骤9；不把此前未变源码验证冒充本片新实测。
