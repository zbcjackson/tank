> 状态：执行中（2026-10-25：承接表格GET读回；两项真实模型试跑各一次，先假HTTP资格再实测。）

# 原始DOM两项真实模型闭环试跑

## 目标与取舍

承接[主计划](computer-use-jev-vision.md)和[表格读回修复](../done/dom-table-readback.md)。
先回答当前生产路径是否能端到端完成，不继续六任务比较或扩大样本。真实产品为隔离的
原版sqlite-web 0.8.1；真实AgentRunner、jev-action-vision、readback_tables: true。
不改生产代码、默认配置、产品模板、策略或候选上限，不注入数据库完成/进展事实。

## 步骤

1. 固定两个公开任务：从记录1编辑页将title Nora改为Miro；从列表进入记录2将notes
   Keep B改为Checked B。均保存并保持其余公开字段/行。每项新数据库、新浏览器、一次实测。
2. 复用既有Runner/产品服务/SDK用量政策与捕获；临时驱动归档，不新增通用benchmark框架。
   从真实初始列表DOM生成期望完整表格，再应用明确用户修改；数据库只初始化及独立事后审计。
3. 冻结驱动、生产源码、产品版本、模型/接收方、任务与限制，先双SDK假HTTP资格。
   TypeSafe jev-1.14.0只收公开文字状态/目标/候选/历史；OpenRouter
   google/gemini-3.8-flash只在自然兜底时收同一状态及绑定的合成1280×720 PNG。
   不强迫Jev弃权，不要求发生图片调用。每任务120秒、6动作、24观察、10万已记账token；
   全批最多24次SDK调用，视觉输出每次最多4096token，SDK重试0。金额未定价，非免费；
   token限额由宿主按返回用量记账，非服务商预留硬上界。未知用量/效果、预留未释放或
   清理未确认立即停批，不盲重试；所有计划行保留，包括未执行行。
4. 两项各实测一次；独立核对原始DB、POST与GET、执行/模型事件、捕获、账本及清理。
   真实失败保留，结论只限当前两条路径的可行性，不作模型排序、准确率或默认采用结论。
5. 记录研究与可复核证据，更新主计划/索引；中性命名拒绝与自然视觉需求仍留backlog，
   不用初始已成立的completion充当拒绝能力。通过最终验证和项目规定的独立审查后归档。

## Tests

不新增生产行为。两任务先使用真实产品/生产Runner、双SDK假HTTP和Python外网阻断，
验证公开DOM目标、导航/启用字段/填值/保存/GET回读及独立业务审计。成功仅为实测准入，
不算模型证据。实测必须对齐请求/完成调用ID与账本整数用量，并核对正确行与保护字段。
生产代码未改，既有38定向、6801后端/1跳过及E2E24/95只是前轮代码依据，不冒充本轮实测。

## Verification Checklist（最终步骤）

本片仓库变更限docs/（含临时驱动证据归档），适用项目docs-only规则，只执行第9项；
若实际修改源码/测试，则恢复全部适用项，不用证据归档规避代码验证。

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest。
5. cd backend && uv run pyright <全部改动Python>。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出通过。
8. cd test && pnpm test；浏览器重型验证串行执行。
9. python3 scripts/check_docs.py、git diff --check；两任务资格/实测/独立审计、源码/配置/
   历史工件SHA与归档完整性核对；最多3轮review-and-refactor后签名提交。
10. python3 scripts/check_protocol_sync.py；协议及生成物未改则不适用。
