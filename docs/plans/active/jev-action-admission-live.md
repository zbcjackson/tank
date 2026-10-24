> 状态：进行中（2026-10-24：用户要求继续直至实测完成；启动最小SDK诊断与新36试次三臂开发测量，先TDD/全检/审查，再冻结执行。旧未知调用不续跑或重放，生产默认不变。）

# 动作级准入的小批三臂实测

## 目标与范围

承接[主计划](computer-use-jev-vision.md)及[隔离原型](../done/jev-action-admission.md)。
本片完成SDK异常/完成/用量/停批原因的最小记录，接入并运行一次V/现有JT/动作级JT
开发比较，审计全部试次与费用口径，形成实测结论。不是正式确认或生产采用。

沿用已讨论接收方：TypeSafe jev-1.14.0仅公开目标/结构/候选/历史；OpenRouter固定
同一视觉模型接收同一公开状态及合成1280×720 PNG。不发送个人桌面/真实业务数据，
不含Jev图片/Box、远端ASR或新增接收方。用户“开始直到完成实测”授权本片执行；
另冻摘要绑定具体任务/源码/配置，摘要是完整性校验，不伪称用户逐字批准新摘要。
record-only继承既有不设固定批次request/token/金额上限范围，价格未定价，不等于免费；
若实际接收方、数据或预算范围改变，再提交具体预览请求授权。

## 开发设计与决策

- sqlite-web/linkding各唯一标题、重名标题、目标缺失三类：6个seed，冷/本地预热两条件，
  三策略共36试次（24正例、12负例）；每策略8正例/4负例。每产品/启动条件策略位置
  配平、六种执行顺序均出现。小批用于开发决策，不估正式N或一般视觉模型排名。
- 新namespace和公开内容，保留原产品及已见模板族，按原始目标身份及完整读回核验，
  不把换nonce说成新应用/未见布局；不取旧确认保留库或续跑第6槽目录。
- 仅选择器政策变化；保留完整候选、规划/权限/账本、实际产品与控制器。串行新进程
  benchmark在试次边界临时注入选择器并finally恢复，生产42冻结源码保持原样。
- SDK边界诊断在所有三臂等同开启：安全异常类型/状态/因果类型链、调用ID、完成状态、
  known/unknown用量、预留状态和停批原因。无原始异常消息/请求头/密钥，不增加重试。
  原始异常在账本settle覆盖前记录，继续保留原unknown/停批行为。
- 目标缺失但存在唯一无关控件必须留在负例；唯一性不等于动作正确。已知模型失误保留
  失败继续；未知用量/效果、未释放预留、异常、证据缺失或清理失败停全批，不自动扩样。
- 全部正/负分母、错误写入、接管、Jev/图片次数、完整任务/SDK边界耗时及tokens分别报告，
  相关seed/条件不当独立确认样本，不把少图或token数直接换算成费用/速度收益。

## 实施步骤

1. TDD实现benchmark专用SDK诊断，复现真实异常被unknown_usage遮盖的信息缺口，
   验证异常类型可查但消息/密钥不泄漏、known/unknown/取消/未发送均不重试。
2. 新小批入口生成/冻结36试次，保留已见族与旧库隔离说明；复用真实产品适配器与
   独立业务核验，用真实SDK/fake HTTP跑完整三臂，审计用量、执行策略和所有分母。
3. 全部适用验证与第1轮独立review-and-refactor通过后，冻结实际源码/依赖/输入并
   校验资格、授权来源与接收方预览，读取凭据执行新目录实测；不改变冻结后源码。
4. 独立审计、配对开发分析、原始证据归档及后续审查（本任务累计最多三轮）。
   若实测触发安全停批，如实报告完成/未运行和根因，不把部分批次写成全部完成。

## Tests

- 在已有test_model_calls.py覆盖SDK诊断：SDK异常与账本异常分层、状态码/取消/期限、
  零重试、异常消息/密钥不落盘、known/unknown原账本保持、记录失败阻止执行。
- 在已有test_dom.py/test_vision.py覆盖新入口：36试次配平、新内容/不泄漏oracle、
  三选择器独立及恢复、冻结篡改/目录复用拒绝、调用前失败/未知用量全批停止。
- 实际Chromium/两真实产品/实际SDK替换HTTP，全部36业务及账本/清理审计；保留失败。
  类型检查仅改动Python；协议/默认/旧工件不改。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/；另查改动benchmark。
4. cd backend && uv run pytest；启用既有Chromium及两产品资格环境。
5. cd backend && uv run pyright <全部改动Python>，不加type-ignore。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出为通过。
8. cd test && pnpm test；本地Sherpa/回环模型/隔离DB，finally恢复原服务。
9. python3 scripts/check_docs.py、git diff --check、旧70工件/42运行源SHA、新冻结/资格/
   调用/用量/实测审计、签名与归档逐成员核验。
10. python3 scripts/check_protocol_sync.py；协议及生成物未改不适用。
