> 状态：已完成（2026-10-23：新冻结原生96/模拟192资格、完整审计及两轮审查通过；后端6622与离线E2E23通过，代码c2c4fdb8已签名；证据归档，旧失败保留并移交条件登记，真实模型未执行，基线528d6dae）。

# V/JT新校准库执行资格与审计接线

## 目标与范围

承接[预注册](../done/jev-supplemental-calibration-registration.md)，绑定注册摘要
762859bc…bdf1e28和原912seed库。实现可核验的新库执行冻结及固定资格前缀：
40正例/8负例seed、96条件目标无模型真实应用检查、192槽假SDK流程。
生成可供现有评分器读取的独立逐行审计，核对每条任务的安全/用量/清理再推进。
保留预注册全部样本/顺序/原门；本片不启动3648槽真实模型测量。

## 步骤与验收

1. TDD接入注册/库/槽顺序校验及新执行freeze，绑定当前源码、应用和模型参数；
   资格前缀严格为各正例层rank0–3、负例rank0–1，保持注册顺序。拒绝输入/
   源漂移、目录复用、错误摘要和把候选真实排程当资格入口。
2. 在既有benchmark产品循环补原始派发守卫、终态DOM和资源清理证明；独立
   审计器从物理before/after DB/schema/写日志、HTTP、原始轨迹和DOM读回核验
   完整目标/路径/恢复、额外变更和关键事件。不得复制runner成功布尔值；缺证据
   标为unresolved并阻止完整sidecar签发。绑定freeze/result规范JSON摘要。
3. 接入固定192槽调度：已知模型失败保留并继续；关键安全、效果未明、用量/
   预留异常、证据缺失和清理未确认停批，保留全部not_run分母，不续跑/重放。
   假SDK传输显式注入且拒绝外部连接，独立进程验证不会漏到真实提供方。
4. 在新freeze运行96无模型原版应用流程和192真实Controller/SDK假HTTP流程，
   独立复核物理/HTTP/图片/账本/审计及评分输入。保留所有失败目录，不挑换任务。
5. 更新接口和研究记录，完整适用验证后交code-reviewer执行review-and-refactor，
   本任务第1轮起、最多三轮，无遗留即止。原注册/旧归档保持不变；运行源变化
   作为调用真实模型前的追加修订绑定原登记，资格证据明确只支持当前冻结实现。

## 交付与后续

运行源冻结`64757493…2e0da0`的唯一新批次通过96原生目标、192模拟槽，完整
audit与评分入口对账通过；672假SDK请求/556图、零外部模型请求。最终后端
6622通过/1跳过，离线E2E23场景91步通过，两轮审查关闭R1/R2且无遗留发现。
第2轮是评审者对自身修复的自检；协调者仅补记归档、签名和生命周期并做文档检查。
源码/测试提交`c2c4fdb8`，SSH签名使用现有Git公钥核验通过。

完整结果和两份归档见[研究记录](../../research/jev-supplemental-calibration-qualification.md)。
模拟评分仍有五个数值门未通过，formal_N=null、model_execution_eligible=false。
本片不提供模型性能或强SQL写列证据。旧cf402批次不重判、不续跑；其恢复后
unknown及not_sent诊断移交[条件登记](../../backlog.md)，后续真实校准范围和
预算冻结由[主计划](../active/computer-use-jev-vision.md)承接。

## Tests

- 注册/完整库/固定前缀/顺序和源码绑定；准备无凭据/模型请求，篡改/复用拒绝。
- 派发守卫和清理原始证明；证据写入失败、撤权、取消、未知效果不继续派发。
- 独立物理目标/全记录/DOM/HTTP及恢复评分；假完成、错记录/多POST、缺证据、
  额外业务动作与关键事件不被bool标志掩盖，审计绑定与现有整数/布尔契约一致。
- 已知模型错误继续、未知用量/预留/审计/清理异常停批及全部分母保留。
- 实际SDK序列化、同绑定PNG及私有oracle隔离；显式假传输/拒外连独立进程。
- 96原版应用无模型资格、192真实Controller假SDK及独立审计/评分器接线。
- 扩展既有chat.feature域入口；无新feature文件，无新真实模型/远端ASR请求。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`。
2. `cd web && npx tsc -b --noEmit`。
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查改动benchmark。
4. `cd backend && uv run pytest`，要求Chromium、qualified sqlite-web和linkding fixture。
5. `cd backend && uv run pyright <改动Python>`，不得type-ignore掩盖错误。
6. `cd cli && uv run ruff check src/ tests/`。
7. 检查backend/web开发pane的error/traceback/exception，空输出通过。
8. `cd test && pnpm test`，使用实际本地Sherpa/回环LLM和隔离DB，结束恢复原服务；
   不重试此前自动审批拒绝的ElevenLabs外发语音配置。
9. `python3 scripts/check_docs.py`、`git diff --check`及新旧工件SHA/源冻结核验。
10. `python3 scripts/check_protocol_sync.py`，通信契约/生成物未改则不适用。
