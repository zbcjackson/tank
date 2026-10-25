> 状态：进行中（2026-10-25：离线复现已核验动作返回相同界面后直接读图，按TDD最小收窄路由；本片不发真实模型请求。）

# 已核验返回状态中的Jev准入

## 目标与边界

承接[像素实测](../../research/jev-pixel-handoff.md)和[主计划](computer-use-jev-vision.md)。
原版Edit→Cancel两个效果已核验，但返回列表命中repeated_state，唯一文字Keep仍
直接交图片。现有visited已保存每次访问时verified_actions数量，可用于识别期间
确有已核验动作；这不证明目标进展，也不能为循环增加重试或动作额度。

最小范围限显式jev-action-vision：当前观察完整/新鲜，返回后已核验动作数增加，
且本状态尚有原来的一次视觉恢复额度时，在该同一额度内重新走原ActionAdmission。
所选动作仍须通过原唯一文字/有界空间准入，失败沿原视觉分支。其他选择器、无动作
反复观察、不完整/不可用状态、未知效果/用量、原恢复次数和最终停止保持；不以
“动作已核验”声称正常返回一定有益，不引入进展分类器或放宽权限/引用。

## 步骤

1. 在既有test_dom.py先加真实Chromium/SDK假HTTP回归，复现列表→编辑→取消→
   同列表的文字Keep；旧代码必须因额外图片而失败，正确来源/效果与完成仍独立断言。
2. 最小调整controller的重复状态路由：使用已有visited计数与一次恢复额度，仅为
   ActionAdmission保留正常可选理由；不重置visited、visual_recoveries或no_progress。
   路由事件标记该恢复原因，模型仍接收完整候选及真实近期动作。
3. 逐项补足/更新现有边界回归：循环有/无Advisor仍同次数停止；无已核验动作仍
   图片恢复；恢复Jev弃权继续图片；未知用量/效果、撤权、陈旧引用不增派发；原
   jev-vision及图片选择器行为保持。新行为进入既有E2E同域，不新建feature。
4. 对原版linkding相同合成只读任务重新做离线/假HTTP资格，使用新源和新冻结，
   拒绝真实执行入口/凭据加载。预期3假Jev/1假图片、3正确点击、零POST/业务表变化；
   保留原真实四调用和9.042秒开销，不据假HTTP宣称真实速度或模型质量改善。
5. 更新现行设计、插件/测试/开发说明与主计划/索引；完成下列所有适用检查，重型
   浏览器验证串行。若旧冻结测试失败，修复明确的测试契约，不放宽生产旧注册。
6. 完成项目review-and-refactor（最多3轮），保留原报告/完整失败和检查证据，签名
   提交、计划移done及条件性后续移交backlog。新的真实收益验证需单独冻结，不在
   本片自动追加付费或扩大用户场景。

## Tests

TDD逐行为红绿；真实DOM/Controller/TaskRuntime/SDK假HTTP，核对原引用三动作和
已核验效果、完整候选、同一恢复额度。仅更换模型路径不能增加循环派发次数；
no-action重复、不完整观察、未知效果/用量及撤权等保持原停止边界。当前默认和
原jev-vision保留。原版产品离线复核公开DOM/HTTP/业务DB及清理，不使用benchmark
业务完成补强或改产品模板。无真实模型、无个人应用/数据输入。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest；启用Chromium/已恢复真实产品环境，修复所有失败。
5. cd backend && uv run pyright <全部改动Python>，不以type-ignore压制。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出即通过不重查。
8. cd test && pnpm test，浏览器重型串行、本地隔离模型/DB、finally恢复原服务。
9. python3 scripts/check_docs.py、git diff --check；TDD/原产品离线资格、全检查日志及
   源/旧工件/默认SHA、归档/独立审查和签名收据核对。
10. python3 scripts/check_protocol_sync.py；协议和生成物未改则不适用。
