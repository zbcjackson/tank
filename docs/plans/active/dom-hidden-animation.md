> 状态：进行中（2026-10-20：修复、完整验证、新目录32/32资格重验及同轮第1次实现审查通过；待真实对照后的统一归档与结果审查，未新增有效凭据模型对照）。

# DOM隐藏伪元素动画准入

## 目标与范围

承接[主计划](computer-use-jev-vision.md)、用户“开始”及
[第二产品资格证据](../../research/jev-second-product-qualification.md)，基线21786a87。
仅修复已复现的隐藏伪元素动画误拒绝，保留普通元素/可见/未知动画的保守判定、
250ms有界等待与精确PNG/ref/导航/撤权守卫。不得修改产品页面、暂停动画或按
loading类特判；不将零模型资格结果解释为模型收益。

先支持空内容且无marker的::before/::after CSS动画，computed visibility:hidden，
报告关键帧及全部可读CSS定义仅含transform/opacity。CSS扫描最多4096规则，
包含import/嵌套/adopted sheet，读取失败或超限保守拒绝。伪元素可见覆盖、
visibility或其他属性动画、无法识别的效果仍纳入
运动检查；不依据父元素隐藏或当前opacity=0笼统跳过动画。边界测试驱动具体实现。

## 步骤

1. 在既有test_dom.py逐项red→green：真实CSS隐藏无限伪元素可捕获且动画仍运行；
   可见/变可见/普通元素及其可见子代继续拒绝；捕获后变更仍拒绝派发。
2. 最小修改现有capture的动画筛选，补既有managed Chromium E2E及现行设计/
   开发文档，完成适用完整验证。与同轮主计划的Controller配方一起做第1轮
   实现审查，收费模型执行须在审查后新冻结；无模型重验保留完整源快照。
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

## 实现与验证进展

先在真实Chromium复现隐藏无限伪元素捕获拒绝，再最小修复；新增24项回归。
进一步红测发现getKeyframes省略CSS自定义属性，混合transform/未知属性能被
误准入，故同时检查可读CSS定义并限制4096规则；采用/导入/嵌套样式表真实验证。
空内容/无marker的隐藏before/after transform/opacity可捕获且保持running，
可见/变可见、文字/marker、其他属性/程序动画、读入失败/超限保持保守；CSSOM
无DOM修订的变可见/像素变化及替换引用仍拒绝。26专项（含2旧动画回归）通过。

完整后端6469 passed、1 skipped、21 warnings（662.05秒），强制Chromium及
既有sqlite-web fixture。web lint/tsc-b、backend/CLI ruff、两份Python pyright
0错误/警告、docs82及diff通过。dev日志空输出通过；初次沙箱拒绝读取tmux，
按只读权限重试后通过，不把权限错误当空日志。协议未变。

E2E最终21场景/83步骤通过（182.685秒）。初次75项子进程超过旧45秒包装器，
单独诊断75 passed（57.53秒），将该进程/步骤等待改为75/90秒，生产期限不变。
随后一次E2E语音场景遇ElevenLabs提交超时，单独诊断1场景4步骤通过，再完整
重跑全部通过；保留失败记录，没有据一次远端超时推测修改ASR或放松断言。

原版linkding单次预检查通过，隐藏loading仍running，PNG与旧归因图字节相同
（308c1d0f…9ed206），资源已关闭；该预检查本身不是32项重验或模型结果。
随后新目录v2已完成4原生流程、32完整观察/32图片准入及5次动画归因，编辑页
16/16可捕获；全部32配对PNG与旧图相同。初始化失败的v1及旧证据原样保留，
详见[同轮Controller计划](jev-linkding-route.md#实现与资格进展)。

第1轮独立实现审查覆盖完整基线21786a87→2a7eb81b，包括本修复、资格原始
证据、共享生命周期、linkding配方及fake HTTP；未发现需要源码/测试修复的
确认问题。审查者重算资格与fake结果并核验旧16档，不把它们解释为模型效果。
仅更新状态与审查事实，未修改执行源；下一步按同轮计划新冻结并运行真实4项，
最后统一归档/结果审查，不另起或重置最多三轮的计数。

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
