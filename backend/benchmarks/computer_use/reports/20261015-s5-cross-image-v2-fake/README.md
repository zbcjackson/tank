# S5 两图候选门：离线验收

> 状态：2026-10-15 fake4/4完成、一个共享账本、0外部模型/新GUI；完整验证6013/E2E18通过，本新调度第1轮R1修复验证通过，第2轮复核通过（无新增/遗留问题，立即结束）。

同签名[执行预览](../20261015-s5-cross-image-v2-live/README.md)，
[数据来源](../20261015-s5-cross-image-source/README.md)。签名
`e8de037d329dc7631ce2d76130d4b5e8e9073456d969809574b7147cd94c8dae`。
[freeze.json](freeze.json)、[result.json](result.json)、[spend.jsonl](spend.jsonl)、
[日志](execution.log)本地保留，不提交raw。

新a_cross_image调度恰好两图×两臂=4请求，图1 default/no-think，图2 no-think/default。
四项复用a_preflight提取的同一run_trial，不复制SDK/用量链；一批一个SpendLedger，
4request/$0.70/4000000tokens全局准入。原三请求入口仍对invalid_reply停批，
有专门SDK回归保持；新跨图配方预声明known错点/格式/弃权/length继续、operational全停。

fake结果：4行finished、4次fake HTTP/0external/0新GUI，4个trial共用一个账本，
合成known9900nano-USD、reserved0、stop_reason=null，2个synthetic pair。
verdict=fake_wiring_only_no_candidate_conclusion，不能据固定fake点评价模型或进入GUI。
completed仅指四项已settled执行完，不等于四项格式/坐标准确；中断无pairs、无候选结论。

新测试先红10项（缺新模块），旧入口known格式停批回归已通过；另复现fake中断门错误1项，
修正为任何mode未完成均incomplete后绿。共13项新增（含参数化），相关302项通过。
覆盖平衡顺序/同图消息相同/图SHA/无truth、单账本四试验、known格式与length继续、
unknown/超余量全停保留四行、候选误点不合格、fake不推荐、重复/漂移零发送、旧行为保持。
SDK实际序列化总输出2048且不含max_tokens，allowance2058；标注只作本地评分。

lint/type/web及运行时检查通过，E2E18场景/71steps通过；完整后端6013 passed/1 skipped/21 warnings（421.99s）、docs51/diff通过；
协议未改/sync不适用，本新调度第1轮R1修复自检/完整验证通过、第2轮复核通过（无新增/遗留问题，立即结束），日志见[validation](validation/)。旧封顶解析/数据诊断评审不重开。
本轮0新模型费用，旧账本/评分不变；提取共享调用后所有旧签名不能续跑。

## R1收尾修复与版本归档

第1轮评审发现原finally先ledger.close，持续journal fsync失败会跳过四行报告保存；
新增故障回归先红后绿，ca30d4e2仅修新调度finally与2项回归：settlement故障或4项完成后
close故障，结果路径可写时仍保存四行、completed=false/incomplete并继续抛错。
原4e5379配方目录/raw保留但source_changed，不补改旧freeze；当前v2以同两图重新prepare，
没有新GUI/模型请求，不改旧数据结果或输出预留。第2轮独立复核待完成。

第2轮实际复跑15项定向/docs51/diff并核对新旧冻结/原始来源，未再改源码。
R1由修复作者再次自检，root另行核对diff和完整6013/E2E18证据；不称为修复作者对自己修改的独立评审。
本新scope本轮结束，不自动第3轮；旧封顶scope未重开。真实请求与预算授权状态不变。
