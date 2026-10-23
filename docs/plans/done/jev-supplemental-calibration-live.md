> 状态：已完成（2026-10-23：本轮单次真实执行尝试停批结案，6尝试/3642未运行、6清理；unknown用量保留，完整audit拒绝，两轮审查完成。完整3648槽校准未完成，运行源码未改。）

# V/JT补充真实校准

## 范围与验收

承接[执行准备结案](jev-supplemental-calibration-execution.md)及
[主计划](../active/computer-use-jev-vision.md)，不修改运行源码、注册目标、顺序、产品、
SDK或统计门。精确执行SHA为
`6830e2d759bb9ee9db83b03d75f0afabb4886be0298e6994f13e802f95c2d494`；
资格SHA `1ea452def8851be240155b401055d5bb82f18b81032171adfc202c3e6e87cb81`，
当前host `f46fdb2764277fff39fd032e6f3573c5b23d1f960e27770b888d3d09bc63cf4c`。
固定912 seed、1824条件目标、3648槽；formal_N=null，属于校准，不是确认试验。

接收方沿用TypeSafe `jev-1.14.0`文字/结构及OpenRouter
`google/gemini-3.8-flash`合成1280×720 PNG，private oracle不进入模型请求，
没有Jev图片/Box或远端ASR。预算沿用用户“不做限定”的record-only，批次请求/
token/金额无固定上限，unpriced不等于免费；未知用量和未释放预留仍停批。
每目标120秒、6动作/24观察/64候选、零SDK重试不变。

只启动一次固定批次。已知目标失败保留并继续；安全事件、未知效果/用量、
预留、源码/产品漂移、审计或清理失败停止下一槽。停止或取消后保留全部计划行、
原始回执和未运行分母，禁止续跑、重排、挑绿或重放未知副作用。
正确停批属于有效实验处置，不等于全部目标完成或模型采用通过。

## 步骤

1. 记录本轮授权、基线与64个旧工件SHA；检查live目录未启动、当前42源/产品/
   SDK和九份闭合验证日志。只读check重新验当前96原生及192假HTTP证明，
   不读凭据、不探测模型；准入通过后才允许CLI读取既有环境/.env凭据。
2. 使用已审查`jev_execution run`、精确SHA和原verification-v3启动同一排程，
   自有`caffeinate -is`只在批次生命周期内防睡眠，不改全局配置；保存命令、
   PID/会话和起止结果。监控只读进度、停因、已知/未知用量、预留、清理及存储。
3. 正常结束或硬停止后，调用当前audit（不加--fake），独立重读所有已尝试raw
   以及未运行分母、SDK捕获/事件/账本；不得冒称真实HTTP线级发送证明。
   运行原scorer，保留失败、未知、未运行、配对簇及所有数值门，不改变阈值。
4. 研究记录实际完成范围、停因/清理、用量、质量/恢复/速度门及可解释边界。
   保留旧64工件；新增归档和清单。完成最多三轮code-reviewer
   review-and-refactor gate及签名提交，结案或明确保留尚未完成事项。
   后续formal_N/采用判断只按真实数据与原门推进，不从模拟资格外推。

## 启动记录

本轮用户“开始下一步”被协调者按已审阅下一步解释为执行范围授权；自动审批
拒绝创建启动进程，认为现有表述不足以明确批准具体第三方、数据及无固定费用上限。
该拒绝不是模型/SDK错误：live目录和run日志均未创建，真实请求为零。
原拒绝及检查保存在本轮临时证据目录。已请求一次具体范围确认；收到明确许可前
不重试、不通过间接入口或更换权限方式绕过。随后用户已对该具体问题回复“明确允许上述外发与预算范围，启动一次批次”，许可另存explicit-authorization.json。以原命令重新提交自动审批，不更换入口/接收方/摘要。3648是计划槽数，并非固定API请求数。

原命令再次获准创建进程，exec会话94171。实际live目录位于
`/private/tmp/tank-jev-execution-review-20261023/study-v3/live`，本轮授权/拒绝/启动与
只读进度记录位于`/private/tmp/tank-jev-live-20261023`。首次进度确认3648行分母、
前三槽strict完成/清理成功，9份known用量回执、105022已知tokens、停因为空；
这是运行中观察，不是最终质量或费用结论。后续以实际closed及完整审计为准。

## 本轮结果

真实命令退出1：6槽已尝试、4正例strict完成/1负例通过/1视觉用量未知，3642槽未运行。
14个SDK调用中13个用量已知，共156643 tokens，另1个未知不补零；清理6/6，
无未决UI效果。独立raw复核与旧64工件SHA检查通过。完整audit退出2且未出证明，
不带audit的scorer仅作缺口诊断、全部证据门为false；完整校准与采用判断未完成。
详见[研究记录](../../research/jev-supplemental-calibration-live.md)。

## 交付与未完成范围

本轮一次执行尝试已闭合并封存；6个物理包、13 known/1 unknown、3642未运行、
42源/九日志/64旧工件及closed副本字节均复核一致。两轮审查完成，R1文案歧义以
63ee3159签名修正，第2轮为修复者自检，无新增可操作问题；计划c339cd22及
结果3073c695亦签名G。完整audit未通过不计成功，scorer仅作缺口诊断。
[研究与新归档](../../research/jev-supplemental-calibration-live.md)保留全过程。

完整3648槽校准、底层SDK/提供方原因和未知用量仍未解决。未知账单/用量凭关联
提供方证据对账，已交接[backlog](../../backlog.md)；离线补失败观测/原始错误传播
由[主计划](../active/computer-use-jev-vision.md)直接承接，不重放本次调用或续跑目录。
父代理的生命周期/归档文字另作docs-only检查，不改raw、账本或九日志。

## Tests

- 运行源码与准备结案完全一致，沿用绑定当前42源的6671后端通过/1跳过、
  72项入口/资格及50项就绪/守卫、E2E24场景/95步和九项闭合检查。
  本片无行为代码改动时不重复收费/假HTTP资格或后端/E2E。
- check/audit/score为只读证据检查；启动前不创建模型客户端、不读凭据；
  真实批次按原逐行物理审核与用量对账，不补零或删分母。
- 修改文档运行docs检查；若确需改行为，另冻结当前失败，不在运行中改源或
  擅自续跑；先确定性RED/GREEN并执行下列全部适用验证与新资格。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`。
2. `cd web && npx tsc -b --noEmit`。
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查改动benchmark。
4. `cd backend && uv run pytest`，启用当前Chromium及原版应用环境。
5. `cd backend && uv run pyright <改动Python文件>`，不得type-ignore。
6. `cd cli && uv run ruff check src/ tests/`。
7. 检查运行开发server最后50行error/traceback/exception，空输出通过。
8. `cd test && pnpm test`，仅实际本地Sherpa/回环模型/隔离DB；结束恢复原服务。
9. `python3 scripts/check_docs.py`、完整`git diff --check`及旧64工件SHA检查。
10. `python3 scripts/check_protocol_sync.py`，协议/生成物未改则不适用。
    纯文档/证据收尾只执行第9项，其余沿用未变源码的已绑定通过证据。
