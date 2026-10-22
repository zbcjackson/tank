> 状态：进行中（2026-10-22：评分接线、只读复算及全部适用验证通过，待独立审查；基线a006e5a1）。

# Jev benchmark离线评分

## 目标与接口

将[已审查算法](../../research/jev-confirmation-design.md)接入
`backend/benchmarks/computer_use/`，读冻结计划和回执，按seed配对汇总，输出JSON及
简短Markdown报告。速度为固定主终点：复用Chernoff-KL有界簇区间及分层配对
BCa20000。不新增生产依赖/决策路径，不执行模型或改旧回执，也不生成执行许可。

支持当前两种计划：内嵌cases的校准freeze，及带cases.json哈希的资格freeze。
保留冻结清单全部行；失败/未执行正例取120秒。两条件先在seed内平均，10个
产品/场景层等权；缺重复/错身份不能静默挑选。安全、额外动作及独立验收采用
绑定freeze和result内容摘要的显式审计输入，缺证据则未定义/不通过。

## 步骤与验收

1. 按TDD落地最小纯统计函数：二项有界簇区间、配对差界、BCa及退化语义。
2. 接入冻结清单/回执/可选独立审计，保留缺失/失败/未运行分母；核元数据、
   清理、完整时钟、已知/未知用量。输出各原采用门及独立的证据完整性检查；
   fake/calibration标签保留，不因数值过门宣称正式确认。
3. 提供只读CLI和JSON/Markdown输出，输出独占创建以免覆盖旧工件；复算既有
   真实校准及最终fake回执，核对原点估计/BCa/分母和原档hash。
4. 文档说明审计契约/限制，完成全部适用检查及第1轮code-reviewer审查，最多
   三轮，无遗留即止。本片只实现评分接线，补充校准预注册仍由主计划承接。

当前进展：步骤1–3已落地，35项定向测试通过。真实96行和fake192行均只读复算，
校准比值0.743232283228、BCa[0.697465313362,0.791253167834]与归档算法一致；
回执乱序不改变指标/门，50份既有工件逐字节保持基线一致。旧数据未补造新审计
sidecar，缺安全/额外动作/治理标签仍unknown。新增CLI已通过现有chat.feature，
本地ASR/回环LLM E2E22场景87步通过、外部连接记录为空，开发服务已恢复。
完整后端6572/1skip通过，静态检查及文档检查通过；无协议变更。
实现和接口详见[报告](../../research/jev-benchmark-scoring.md)。

## Tests

- 零事件界、非平衡/少量/退化数据、比值的均值而非比值均值、配对簇不可拆。
- 冻结/结果绑定、完整四槽、错/重/缺行、无效成功时钟、清理失败、负例单列。
- 未知用量与残留预留不能过证据门；缺安全/额外动作/独立审计不能默认为零。
- 各门边界、BCa独立核验、CLI跨进程只读/无网络/输出不覆盖，加入现有E2E域。
- 真实校准与fake资格只读复算；不新增模型/远端ASR调用或大型统计框架。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`。
2. `cd web && npx tsc -b --noEmit`。
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另检查新增benchmark。
4. `cd backend && uv run pytest`；要求Chromium及两原版应用fixture。
5. `cd backend && uv run pyright <本轮改动Python>`，禁止用type-ignore掩盖错误。
6. `cd cli && uv run ruff check src/ tests/`。
7. 检查运行backend/web开发pane的error/traceback/exception。
8. `cd test && pnpm test`；沿用已审查本地Sherpa/回环LLM/隔离DB的离线配置，
   验证后恢复服务，不触发先前被拒绝的ElevenLabs外部语音复测。
9. `python3 scripts/check_docs.py`、`git diff --check`及研究输出/旧档hash核验。
10. `python3 scripts/check_protocol_sync.py`（无契约变更则不适用）。
