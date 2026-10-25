> 状态：进行中（2026-10-26：已启动同一原版只读任务的新源资格与冻结准备；尚无真实模型请求。）

# 已核验返回后的单次真实验证

## 目标与边界

承接[离线修复](../../research/jev-verified-return.md)和
[主计划](computer-use-jev-vision.md)。用户已要求开始下一步；沿用同一原版linkding
1.47.0合成只读任务，检验真实Jev是否在返回列表后正确选择Keep，并记录完整模型
路线、质量、用量和耗时。只做一次开发验证，不作统计采用或模型优劣确认。

原产品、目标与原版UI保持：预览红三角书签Edit→Cancel→右侧Tags下Keep；使用新
临时副本、两条合成书签/图片和原生产Runner/DOM/SDK。不给模型正确记录id、引用
或像素映射，不过滤候选、不强迫弃权，不改生产代码、默认或既有原始结果。

沿用已有接收方与范围：TypeSafe https://api.typesafe.ai/v1/systemone 的
jev-1.14.0接收公开合成目标、文字/结构、完整候选、几何与近期历史；OpenRouter
https://openrouter.ai/api/v1 的google/gemini-3.8-flash只在自然图片分支接收同状态及
绑定1280×720 PNG。不调用Jev图片/Box，不外发个人应用或真实用户数据。
上限仍为8SDK、120秒/6动作/24观察/10万宿主已记账token、视觉输出4096、retry0，
金额未定价，宿主token限额不是提供方预留硬上界。未知用量/效果、源漂移、未结
预留、审计或清理失败即停，失败不重发、不挑选成功轨迹。

## 步骤

1. 复用已审查的原版初始化/像素互换资格和独立审计器，在新目录运行零模型资格；
   固定当前354运行源、产品446文件/依赖、三个脚本、公开任务、预算与接收方。
   新驱动从既有真实入口派生，仅更新基线/路线假设及实测前审查绑定；旧离线入口
   保持禁用真实调用。
2. 真实Chromium/Runner/官方SDK假HTTP验证3Jev/1图片及3原引用正确动作、零POST/
   业务表变化、账本/清理；复用已审查的错误来源、图片/帧绑定、缺失返回和业务DB
   篡改拒绝。逐SHA核对前轮完整检查与当前字节，不用假HTTP宣称真实模型收益。
3. 完成实测前独立review-and-refactor；新冻结与通过的资格/审查绑定后才启动唯一
   一次真实任务。猜中直通、弃权继续图片、错误选择或停止均是实际结果，不重跑。
4. 独立核对全部真实请求/响应/SDK诊断、原引用/来源/效果、HTTP/物理业务DB、
   账本与清理。比较旧2Jev/2图片观测，分别报告SDK跨度和同口径驱动耗时；不把
   旧9.042秒直接当作节省，也不把一次差值外推为普遍提速。
5. 更新研究/主计划/索引，完成本任务最多3轮审查中的新增结果复核、证据SHA归档
   与签名提交；结案移done，剩余条件性工作交backlog。

## Tests

不改生产代码、测试或协议，明确复用前轮绑定同字节的完整后端6844通过/1跳过、
E2E24场景95步骤及静态/类型检查，不称为本轮重跑。新的实际产品资格、假HTTP
闭环、六类审计篡改拒绝和独立离线核对必须通过；前置失败保留，真实任务即使
失败也不重跑。若必须修改生产行为，先停止实测并按TDD及全适用检查另行修复。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest；启用Chromium与真实产品资格，修复所有失败。
5. cd backend && uv run pyright <全部改动Python>，不以type-ignore压制。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出即通过不重查。
8. cd test && pnpm test；重型浏览器验证串行、finally恢复原服务。
9. python3 scripts/check_docs.py、git diff --check；新资格/假HTTP/篡改拒绝、完整检查
   日志与源绑定、独立审计/审查、旧工件/默认及归档/签名逐SHA核对。仅docs变更
   按项目例外只需文档检查，运行字节不变的完整验证明确复用，不无故重跑。
10. python3 scripts/check_protocol_sync.py；协议/生成物未改则不适用。
