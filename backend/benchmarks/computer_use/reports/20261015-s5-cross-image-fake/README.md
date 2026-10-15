# S5 两图候选门：离线验收

> 状态：2026-10-15 source_changed：R1收尾修复后本冻结失效；旧fake4/4仅作历史，禁止运行/补改旧目录，使用新v2配方。

同签名[执行预览](../20261015-s5-cross-image-live/README.md)，
[数据来源](../20261015-s5-cross-image-source/README.md)。签名
`4e5379e3695c394b2be8869b1fe830ff4a72a2f928544f94f32429b874f320fc`。
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

lint/type/web及运行时检查通过，E2E18场景/71steps通过；完整后端6011 passed/1 skipped/21 warnings（421.29s）、docs51/diff通过；
协议未改/sync不适用，本新调度最多三轮独立评审待完成，日志见[validation](validation/)。旧封顶解析/数据诊断评审不重开。
本轮0新模型费用，旧账本/评分不变；提取共享调用后所有旧签名不能续跑。

有效新版本：[v2 fake验收](../20261015-s5-cross-image-v2-fake/README.md)。旧raw/分母/账本保持，源码修复未覆盖旧结果。
