> 状态：进行中（2026-10-21：从9ee84cde开始修复列表观察、校准执行器及完成验收；完整验证/审查/新冻结后运行一次96项校准，不进入正式确认）。

# V/JT四行列表修复与校准

## 目标和范围

承接[主计划](computer-use-jev-vision.md)及
[准备结果](../../research/jev-confirmation-preparation.md)。用户已授权开始下一步，
包含容量/完成事实/身份验收修复、新资格、Controller/SDK验证和后续校准。基线
9ee84cde；同一任务独立审查最多三轮，不因分实现/结果阶段重置。保留所有旧
raw/freeze/归档，不覆盖原协议或把校准计入正式确认。

观察修复针对非输入控件的DOM聚合显示文本，输入值保留原样，实际内容过长/
范围不完整仍拒绝。现有ActionBuilder/Controller支持显式max_candidates：只在
新配方声明64（与已有原生通道额度一致），两臂相同、完整候选不删减，超64仍
拒绝；浏览器生产默认32不变。不是无界放大、不隐藏动作，也不放松PNG/ref/
授权/业务验收。任务仍120秒/6动作/24观察、32MiB参数、SDK零重试、record-only。

## 步骤

1. TDD在已有test_dom.py复现空白放大导致聚合文本不完整，最小修复；可见长
   内容/隐藏内容/输入空白/导航与旧帧仍按对应契约处理，扩展已有Chromium E2E。
2. 新配方按已准备24案例与补充协议构建真实目标：Records、当前返回列表/path
   与实际编辑器历史共同完成；按公开id/URL匹配目标，不按seed位置。新增配置
   只作用新配方，旧两产品12/8/4任务及原默认/旧freeze解释不改。
3. 校准沿用两产品原版应用、合成数据和诊断GET503一次（从不重放POST），补
   缺目标/编辑器设置后撤权、冷fixture/预热服务且新浏览器上下文。完整计时
   包含设置/预热/关闭，供应方缓存不受控。每案例两臂×两启动条件=96项，
   80正例/16负例；24案例为cluster。所有分母在执行前固定，不补跑模型失误。
4. 用真实Controller/SDK和fake外部HTTP验证所有案例/条件、正确完整回执、
   私有oracle隔离/错误记录/错误返回列表/缺字段与停止/取消/审计/清理。新目录
   无模型重验24案例，并核图片/候选与原生业务；失败保留，不悄悄替换任务。
5. 完整适用验证后首次review-and-refactor覆盖本任务全diff。新源变化新freeze；
   全新收费目录验证协议/源/应用/环境/任务/补充hash后才读凭据，执行一次96项。
   沿用Jev1.14文字TypeSafe/Gemini3.8-flash PNG+同文OpenRouter既有授权，无
   固定批次请求/token/费用上限；未知用量/运行/审计/清理失败即停，保留96分母。
6. 独立物理DB/HTTP/DOM/路由/用量/计时复算，全部阶段源/失败/新结果归档、
   实际凭据扫描及旧档核验，结果面板和剩余轮次审查。完成后归档此子计划，
   主计划继续按新校准估计正式N；不把96项当正式非劣/采用确认。

## Tests

- vertical red→green：聚合空白、真实长内容仍拒绝、textbox空白不变；默认32
  与显式64分别拒绝/保留四行全部候选，超64仍拒绝，无语义删选。
- 新任务需实际Records+当前返回列表+正确编辑历史；打乱seed仍按id验收。
  缺/错列表或wrong-record不能成功，私有oracle不参与观察/选择。
- 24×2×2的固定顺序/分母与冷暖定义，CLIprepare不读凭据/建客户端；freeze
  篡改、未知用量/非法回复/取消/审计/关闭/fixture故障均安全停止并保存96行。
- fake SDK调用与真实模型结果分列，原生资格不是模型或Controller完成率。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查改动benchmarks。
4. `cd backend && uv run pytest`，强制Chromium及sqlite-web/linkding原版fixture。
5. `cd backend && uv run pyright <全部改动Python>`，不以type: ignore规避。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`，另核backend pane；空输出通过。
8. `cd test && pnpm test`，在全后端测试后串行运行。
9. `python3 scripts/check_docs.py`，另核工件/独立复算/面板tsc及diff。
10. `python3 scripts/check_protocol_sync.py`，协议或生成物变化时适用。
