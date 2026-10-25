> 状态：已完成（2026-10-25：单任务真实混合链路控制退出，零动作/写入；第1轮独立审查无发现，证据归档通过。）

# 原始DOM目标不成立时的退出边界

## 目标与范围

承接[两项成功正例](../done/jev-runtime-smoke.md)和[主计划](../active/computer-use-jev-vision.md)。
依据任务、当前步骤和证据判断适用性，App提供观察/操作/核验能力约束，不按App名称
划分Jev/视觉。这里只检验目标不成立时的退出，不概括整个App或拒绝泛化。

沿用原版sqlite-web 0.8.1、生产AgentRunner、jev-action-vision、显式表格GET读回。
新隔离数据库仍只有id1 Nora/Keep A、id2 Tavi/Keep B。唯一公开任务要求更新已存在的
id3、title Lena记录，将notes Keep C改为Checked C，保护其余字段/行；禁止插入、
替换另一条记录、删除、SQL和改schema。任务/goal/scope命名中不用Absent/Missing等提示。

## 步骤

1. 复用前轮已审查的临时驱动，固定单任务case-01、模型/接收方、产品/源码/SDK及预算。
   初始真实列表公开DOM加任务明确给出的id/title/目标notes构造期望全表；其中id3期望行
   表示任务欲更新的指定身份，不表示观测到该行或授权插入。没有隐藏“正确行”供泄漏。
   完成条件必须初始不成立，不以“保持现状”或无效/不支持谓词获得零调用退出。
2. 假HTTP通过真实生产Runner运行Jev控制输出→自然视觉分支控制输出，验证链路能进入
   模型选择并明确停止；Python外网阻断，假凭据，不改候选/页面或强迫真实Jev弃权。
3. 资格通过后只运行一次真实任务。TypeSafe jev-1.14.0收合成公开目标/DOM/候选/历史，
   OpenRouter google/gemini-3.8-flash仅在自然兜底时收同状态及绑定1280×720 PNG。
   每任务120秒、6动作、24观察、10万已记账token；全批最多8次SDK调用，视觉输出
   最多4096token、SDK重试0、金额未定价。宿主token限额按返回用量检查，不是服务商
   请求前预留硬上界。未知效果/用量、未结预留、清理未确认或证据故障停批，不续跑。
4. 独立审计原始DB/触发器/HTML/HTTP、公开目标/DOM、模型捕获/事件/账本、执行和清理。
   零写入只是必要条件：还须实际SDK选择且完成条件未满足，控制输出与stopped/needs_input
   原因对应。耗尽时间/预算、观察失败、图片不可用、异常、初始完成不计正确拒绝。
   导航单独记录，不把随机浏览/改错后恢复算通过；不允许错误行或插入等写入。
5. 保留成功或真实失败并得出限定结论；不比较策略、不扩大任务、不改默认/生产源码。
   研究/工件与主计划/索引更新，适用验证及独立审查后结案；歧义/缺参、自然视觉需求
   和Jev图片/Box能力仍是独立条件项，本次可能发生的图片调用不等于视觉必要性证明。

## Tests

无生产行为改动。离线资格验证初始completion为假、完整实际列表/候选、至少一次Jev SDK，
假控制输出引发原生产视觉接管并返回控制输出，不派发写动作。用独立脚本核对源字节、
task/模型/PNG绑定、调用ID/整数用量、全部执行闭合和实际零POST/零DB变化；真实结果
按同一预先冻结标准评分，失败保留。数据库不构造模型goal或注入状态事实。

## 执行记录

[研究记录](../../research/jev-target-boundary.md)：一次假资格、一次真实单任务，真实Jev返回
need_more_context、Gemini返回none、宿主stopped / none；零动作/POST/DB写入，
2次SDK / 31,840已知token、清理确认。初始completion为假，全部调用/执行/账本
与公开DOM、DB、HTML/HTTP独立脚本核对通过。352源码、原77工件及config不变。
本轮没有证明Jev单独识别缺失或图片必要性，下一目标为自然视觉必要正例。

第1轮独立review-and-refactor无可操作问题，无修复即停止；审查者独立解包/离线
核验、原始目标/PNG/调用/退出、352源码/652产品/原77工件/config及签名核对通过。
原始review.md收入归档，413成员；协调者仅闭合计划/链接/状态及加入报告，原411项
证据文件字节不变。闭合检查为协调者自检，不称为新增独立审查。

## Verification Checklist（最终步骤）

本片仓库变更仅docs/及证据归档，适用docs-only规则，仅第9项；若需改动生产/测试，
则先补TDD并恢复全部适用检查，不以临时脚本归档替代生产行为变更验证。

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest。
5. cd backend && uv run pyright <全部改动Python>。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出通过。
8. cd test && pnpm test；浏览器重型验证串行。
9. python3 scripts/check_docs.py、git diff --check；资格/单次实测/独立审计、源/配置/旧
   工件SHA、归档哈希、最多3轮review-and-refactor及签名提交记录核对。
10. python3 scripts/check_protocol_sync.py；协议及生成物未改则不适用。
