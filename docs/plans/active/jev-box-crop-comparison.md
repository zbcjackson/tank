> 状态：进行中（2026-10-19：冻结Box整窗/区域裁剪与Gemini同图只读对照，旧0/2保留）。

# Jev Box 图片表示与定位精度对照

## 目标与范围

用户要求开始上一轮提出的下一步：比较整窗/工具区域表示、不同大小目标和第二
布局，接入可替换视觉模型并验证输出契约。沿用用户“不做限定”的请求/费用授权，
只记用量，不设固定批次费用上限；未知用量或清理失败仍停。Box无执行器。

使用已归档TextEdit与Calculator各两个位置的真实窗口请求PNG，以及同一请求中
独立AX观察的矩形。它们是已见开发材料，不是新holdout或新的应用族；不重新操作
桌面。标签从AX描述构建，不从模型框或结果修正，原先小按钮0/2不重判。

对照模型选OpenRouter的google/gemini-3.8-flash，公开模型目录确认image输入及
response_format支持，目录原文件随新数据冻结；不假定协议声明等于实际符合。
资料：[模型](https://openrouter.ai/google/gemini-3.8-flash)、
[目录](https://openrouter.ai/api/v1/models)、
[JSON输出](https://openrouter.ai/docs/guides/features/structured-outputs)。

## 实验设计

- 来源：TextEdit的scene-01-p0-image、scene-02-p1-image，Calculator两个任务的
  首次图片请求。保持原PNG和同请求AX/窗口元数据，检查方向1、无原补边及hash。
- 目标：TextEdit italic、Helvetica字体选择器、多个对齐按钮、缺失Export CSV；
  Calculator Equals、AC清除按钮、多个数字按钮、缺失Export CSV。按实际AX矩形
  报告大小，不把目标数当独立布局数。
- 表示：原整窗、固定全宽工具区域。TextEdit裁剪窗口高度3%–8.5%，Calculator
  裁剪28%–100%键盘区域；该区域与目标问题无关，所有正例必须完整保留，不能围绕
  正确目标裁成居中答案。两种输入复用相同normalize_frame（长边1568、短边补280），
  因此比较是裁剪+现行规范化的组合干预，分别记录目标在输入中的实际像素大小。
- 模型：同图/同意图、无AX或正确矩形传入。Jev0–1框，Gemini固定0–1000 bbox_2d，
  转换一次，不猜单位或修复回复。丢失/多目标只计数量，唯一目标才映射和评分。
  Gemini官方示例常用[ymin,xmin,ymax,xmax]；本轮明确声明XY顺序并用非对称控制
  图验证，只评价该统一声明契约，不宣称其原生格式下的性能上限。依据
  [官方图片理解](https://ai.google.dev/gemini-api/docs/image-understanding)。
- 先以3张合成颜色卡验证两模型的唯一/不存在/多个、结构与几何，控制6请求。
  若不能全部通过，停止主比较，保留全部未运行项，不用坏契约冒充视觉能力劣势。
  主比较4源图×4问题×2表示×2模型=64问题，顺序平衡；每问题1请求，无重试。
  70是当前自然计划数而非计费上限，每任务保留120秒期限和SDK输出长度上限。
- 主评分：唯一目标中心落入独立AX矩形内缩短边10%的比例，数量正确、结构合法、
  补边无效、相对中心偏移及IoU单列。所有计划分母保留；按应用/源图分组解释，
  不用这些已见图推导跨应用采用、普遍优越性或更快。

## 实施步骤

1. Tests：在现有test_vision.py按TDD覆盖离线准备不创建SDK、标签/请求隔离、
   crop/padding逆映射及单位、真实SDK的fake HTTP两模型调用/用量/完整分母、
   预检失败/已知非法回复/未知用量停止、零desktop授权和资源清理。
2. 复用现有图像规范化、严格0–1000解析、TaskRuntime视觉服务与record-only账本，
   增加独立冻结只读benchmark；不修改生产定位器/默认配置，不加入坐标执行。
3. 完成完整适用回归及首轮独立review-and-refactor后运行已授权真实模型；所有
   prompt/图片/标签/源hash先冻结，客户端所有权与raw请求响应留档。
4. 独立重算并归档，更新主计划/索引/面板，结果审查沿用本任务轮次，最多3轮。
   新假设需要新冻结，不重试或微调旧题来改变失败结果。

## 实现验证

实现提交28bd01a8；6项新回归全部通过（3.84秒），覆盖逆映射/单位/补边、离线
冻结及两实际SDK的完整70项fake HTTP矩阵、未知/契约/已知非法回复停止或继续。
完整后端6359通过/1跳过（464.83秒），web lint/类型、backend/CLI lint、两个
修改Python文件pyright、dev日志均通过。原四份PNG与AX/calls记录匹配各自旧
不可变manifest，整窗预处理后仍与原请求PNG字节一致，所有正例保留在通用ROI。

准备目录`/private/tmp/tank-box-crop-live-20261019`，冻结SHA256：
`812e6cc3ba3a88ad1451fc9feef8b81b2531e28c78657ffc737bd78ee4f55158`，
26源文件hash、70计划项，6控制/64主问题，真实模型尚未运行。OpenRouter凭据
只读检查HTTP200，不计模型调用。E2E21场景/83步骤通过（142.791秒），与全
后端串行；docs64及diff检查通过。

首轮独立review-and-refactor审查以226c31a7为基线，覆盖完整实现及计划差异，未发现
可操作缺陷，源码未修改。审查者独立运行6项box_crop回归全部通过（3.05秒），核验
26源hash、23冻结文件、70项实际构造请求与preview相等，并对17个唯一目标/表示
组合独立检查中心逆映射。人工核对两应用区域PNG与目标描述，未调用真实模型或
操作桌面。完整回归复用上述未再变化源码的结果；本轮仅补文档审查事实。下一步
执行已授权真实实验，控制通过前不进入主比较，结果审查沿用本任务轮次。

## Tests

预检/正式题分别报告；模拟HTTP只证明接线，不计模型质量。样本来自两种已见
应用布局、每种两个源图，重复表示不是独立样本。截图从原始归档按hash验证，
区域裁剪仅用于受控图片实验，不能据此改变生产截图范围或跳过新鲜度检查。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`，另检查新benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部修改Python文件>`，不用type-ignore。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与全后端串行。
9. `python3 scripts/check_docs.py`与`git diff --check`；冻结/归档成员/旧证据/费用重算核验。
10. 协议/生成物变更才执行`python3 scripts/check_protocol_sync.py`；本片无协议变更。
