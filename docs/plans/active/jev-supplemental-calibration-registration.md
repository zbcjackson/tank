> 状态：进行中（2026-10-22：预注册/912新seed离线冻结核验通过，待独立审查；基线3c2a980a）。

# V/JT独立补充校准预注册

## 目标与范围

承接[主计划](computer-use-jev-vision.md)和[评分接线结案](../done/jev-benchmark-scoring.md)，
冻结补充校准的信息目标、新任务库、分配/顺序、停止规则和逐行独立审计协议。
选择既有0.5%条件提案作为本轮设计目标，固定760正例seed及152负例seed，
两启动条件×V/JT共3648次计划测量。正式确认N继续为null；本预注册及任务库
不构成模型执行许可，新库原生/模拟执行资格与执行冻结由后续阶段验收。

仍是sqlite-web/linkding原布局、四行记录Title更新。新数据不等于新布局；
使用新namespace/master，与旧24校准seed和12288确认保留seed的ID/数据指纹隔离。
Jev仍走文本结构选择，Gemini仍为V及JT接管的视觉服务，不检验Jev图片/Box。

## 步骤与验收

1. 冻结一个主要精度目标：JT正例失败的seed平均量，零事件时双侧95%有界簇
   区间上界≤0.5%；独立复算736解析门槛及760平衡取整，负例单独报告。
2. 复用已审查生成规则，最小替换namespace/ID及校准元数据，封存首次生成的
   master和912个新seed/1824个GoalContract。核全部目标、分层、顺序和隔离；
   正例每层76，目标1/4×cold先行arm各19；负例每层38，缺失目标99/撤权目标1
   保持原任务语义，cold先行arm各19，预热反转。不额外发明负例目标配平。
3. 写出机器可读协议和人可读预注册：固定全分母、120秒规则、已知失败继续/
   关键异常停批、不可补跑至过门、独立审计证据来源与未知处理、分析/资源报告，
   明确未来原生/假HTTP资格及执行冻结要求，绑定当前评分器/运行源码/应用/模型。
4. 离线结构/数学复核、两次构建一致性和旧档不变检查；归档协议/任务/验证材料，
   完成文档检查及code-reviewer的review-and-refactor，最多三轮，无遗留即止。

当前结果：4项研究测试通过；全1824目标解析、96分配格各19、实际master重建、
与24旧校准/12288确认保留seed的ID/数据零交集、736解析门槛和760理论上界
0.484203%均已核验。37运行/评分源及已安装SDK与候选绑定一致，54旧工件保持。
完整协议和初稿澄清记录见[预注册](../../research/jev-supplemental-calibration-registration.md)。

## Tests

- 736前后解析边界及760簇上界复算；不能把3648次当作独立样本。
- 新namespace/ID/数据与旧库隔离、生成确定性、输出不覆盖、固定数量和分配。
- 全部1824份GoalContract解析、完整业务目标和数据一致；资格前保持不可执行。
- 每个正例层/目标/启动条件的先行arm配平；负例固定目标语义与先行arm配平。
- 协议和评分器12门、方法/单位/审计字段一致；审计缺失不能写成零或制造通过。
- 全分母、固定停止/修订规则、无结果驱动抽换任务；全部旧工件保持字节一致。

## Verification Checklist（最终步骤）

仓库只更新docs中的预注册与研究工件，不改应用/benchmark运行源码或仓库测试。
按docs-only例外执行第9项，并运行上述离线研究校验；其余项仅在实际源码范围
变化时适用，不重跑未变的后端/E2E或调用真实提供方。

1. `cd web && pnpm lint`。
2. `cd web && npx tsc -b --noEmit`。
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/`，另覆盖改动benchmark。
4. `cd backend && uv run pytest`，如适用须要求Chromium及两原版应用fixture。
5. `cd backend && uv run pyright <改动Python>`，禁止type-ignore掩盖错误。
6. `cd cli && uv run ruff check src/ tests/`。
7. 检查运行backend/web pane的error/traceback/exception。
8. `cd test && pnpm test`；如适用使用已审查本地Sherpa/回环LLM配置并恢复服务。
9. `python3 scripts/check_docs.py`、`git diff --check`、协议/工件摘要及离线校验。
10. `python3 scripts/check_protocol_sync.py`，仅通信契约或生成物变化时适用。
