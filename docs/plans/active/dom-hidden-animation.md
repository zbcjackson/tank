> 状态：进行中（2026-10-20：开始TDD修复linkding隐藏伪元素动画误拒绝，尚未新增模型调用）。

# DOM隐藏伪元素动画准入

## 目标与范围

承接[主计划](computer-use-jev-vision.md)、用户“开始”及
[第二产品资格证据](../../research/jev-second-product-qualification.md)，基线21786a87。
仅修复已复现的隐藏伪元素动画误拒绝，保留普通元素/可见/未知动画的保守判定、
250ms有界等待与精确PNG/ref/导航/撤权守卫。不得修改产品页面、暂停动画或按
loading类特判；不将零模型资格结果解释为模型收益。

先支持可确认的::before/::after、computed visibility:hidden、仅transform/opacity
属性的动画。伪元素可见覆盖、visibility或其他属性动画、无法识别的效果仍纳入
运动检查；不依据父元素隐藏或当前opacity=0笼统跳过动画。边界测试驱动具体实现。

## 步骤

1. 在既有test_dom.py逐项red→green：真实CSS隐藏无限伪元素可捕获且动画仍运行；
   可见/变可见/普通元素及其可见子代继续拒绝；捕获后变更仍拒绝派发。
2. 最小修改现有capture的动画筛选，补既有managed Chromium E2E及现行设计/
   开发文档。完成适用完整验证和第1轮review-and-refactor后冻结稳定修复。
3. 使用全新输出目录重跑原版linkding四个无模型脚本流程及五次动画检查，保持
   原资格分母、页面/任务/业务验收，记录源与应用hash、前后PNG与清理。
4. 独立复算、扫描、归档并在剩余审查轮次内审查结果；修复/资格切片关档。
   资格通过后由主计划承接真实Controller回执/阶段观察、可执行freeze和V/JT
   比较；若本切片修复仍不能准入，保留全部失败并继续诊断。

## Tests

- 真实Chromium/公共capture与is_current接口，不mock浏览器可见性或动画效果。
  隐藏::before/::after transform/opacity可捕获，动画保持running；可见伪元素、
  可见覆盖、非白名单属性、伪元素嵌套marker和普通动画保持保守拒绝。
- 保留有限动画等待；隐藏→可见、像素/DOM/ref/导航变更后不得派发旧动作。
  当前接口无法确认的效果继续拒绝，不引入class名或产品专用特例。
- 沿用原版linkding4流程×4状态×2时机=32观察与额外5次归因。独立核物理DB
  全部书签表/字段/schema、单POST与返回列表，全部新旧归档及实际凭据扫描。
- 复用既有managed Chromium cucumber条目，不新增同域feature。模型比较需要
  真实业务回执与新执行器，本切片的脚本成功不能替代它。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查改动benchmark。
4. `cd backend && uv run pytest`，启用TANK_REQUIRE_CHROMIUM及既有真实产品fixture。
5. `cd backend && uv run pyright <修改的Python文件>`，不使用type: ignore规避。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`；空输出通过，不重复。
8. `cd test && pnpm test`，在全量后端测试完成及后端/前端运行时执行。
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`，协议或生成物变化时适用。

全部适用检查通过后独立review-and-refactor，最多三轮，无遗留即停止。每逻辑
子任务签名提交，不修改旧冻结/原始证据；后续源码变化必须新freeze。
