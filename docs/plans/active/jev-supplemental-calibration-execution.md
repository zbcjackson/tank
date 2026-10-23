> 状态：进行中（2026-10-23：开始完整校准执行入口、准入与预算冻结；基线f139c421。本片仅准备及假HTTP验证，未授权或启动真实模型批次）。

# V/JT补充校准执行准备

## 目标与范围

承接[执行资格结案](../done/jev-supplemental-calibration-qualification.md)和原预注册，
保持912 seed、1824条件目标、3648槽及原顺序/门槛。新增独立的完整批次入口，
复用已资格化的run_task和逐行物理审计，不修改41份既有运行源。
预算沿用用户此前“不做限定”及登记的record-only：批次请求/token/金额上限均不
设置，仍逐调用登记已知/未知用量及预留，未知或未释放预留停止后续槽位。
每目标120秒、6动作/24观察/64候选、零SDK重试不变；不把437760秒的统计
期限和当作包含全部清理的批次时长保证，不提供当前价格或发票估算。

本片完成可执行入口和可审阅冻结，真实模型的TypeSafe文字/OpenRouter合成PNG
请求须在完整验证/审查完成后以新摘要另行授权；不以旧96/192资格或本次“开始”
代替对新批次精确范围的审阅。正式N仍null，资格或模拟速度不作为采用证据。

## 步骤与验收

1. 固定上一片审查归档SHA、原生96/假SDK192成功与完整audit，核对41源/产品/
   SDK/参数。准备全批和固定资格前缀两种摘要，绑定新增入口源码、保存的源码、
   完整排程、接收方/数据种类及record-only预算。准备与检查均不读凭据/建客户端。
2. TDD实现同一批次循环的真实/显式假HTTP模式：预填全部分母，已知目标失败
   继续；独立审计、安全、未知效果/用量、预留、漂移、异常、取消、清理不符停批，
   保留部分行且禁止目录复用/续跑。真实用量核对SDK捕获/事件/账本，不冒称原始
   HTTP级发送证明；模拟另核原始假HTTP请求/usage。
3. 为新入口运行一次固定192槽假HTTP资格，既有宿主41源不变时引用原96原生
   资格；不能把旧入口192通过当作新增入口资格。冻结全部实际证据和九项验证
   日志，完整audit及预检必须绑定当前源码和对应模式/摘要，凭据读取在准入之后。
4. 输出准确的完整排程/预算/数据预览和启动命令；本片不执行真实模型。按项目
   code-reviewer的review-and-refactor gate完成最多三轮，签名提交及研究归档。

## Tests

- 无模型准备保留1824目标/3648槽及固定96/192前缀，全部源/文件/产品漂移拒绝，
  错摘要/跨模式摘要/伪资格/旧回执/目录复用拒绝；预检失败前零凭据读取。
- 逐行调用ID/事件/预算/账本关联；零调用缺字段或布尔用量不补零；假传输额外
  请求及目标/图片/usage不符停批；实际SDK与真实原版应用验证两臂接线。
- 已知失败继续及关键事件、未知效果/用量、预留、清理、漂移、异常/取消停止；
  保留全部计划行和原始部分回执，不启动后续目标。
- 新入口192槽假HTTP资格、完整audit与源绑定预检；扩展既有chat.feature，
  所有验证无真实模型/远端ASR请求，保留所有失败证据。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`。
2. `cd web && npx tsc -b --noEmit`。
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另查新增benchmark。
4. `cd backend && uv run pytest`，启用Chromium及两原版应用环境。
5. `cd backend && uv run pyright <改动Python>`，不得type-ignore。
6. `cd cli && uv run ruff check src/ tests/`。
7. 检查backend/web开发pane的error/traceback/exception，空输出通过。
8. `cd test && pnpm test`，实际本地Sherpa/回环模型/隔离DB，结束恢复原服务。
9. `python3 scripts/check_docs.py`、完整`git diff --check`及全部旧工件SHA核验。
10. `python3 scripts/check_protocol_sync.py`，协议/生成物未改则不适用。
