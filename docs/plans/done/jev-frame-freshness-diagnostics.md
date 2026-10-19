> 状态：已完成（2026-10-19：无模型诊断与合成因果复现完成，归档97项，第1轮独立审查通过；未修改生产）。

# Jev 图片帧与引用拒绝诊断

## 目标与范围

承接[TextEdit对照](../../research/jev-image-real-app-ablation.md)中两个模型调用前
unstable_visual_frame、一个正确选择后的stale_reference和三个Box帧后拒绝。
定位检查层次及可复现因素，不追加收费调用、不追改旧评分、不放宽原输入门。
若未取得可验证根因，明确证据边界，不为得到成功而反复运行。

## 步骤

1. 离线核对旧PNG、帧元数据与审计，辨别像素身份、窗口身份和AX引用判定链。
2. 用临时诊断脚本新建最多4个TextEdit实验文档（两颜色×两位置），只执行已有
   实验准备动作。逐帧保存绑定窗口图、实际AX变化与原current检查返回位置；
   不调用模型、不派发任务fill/click，清理自有资源。单上下文最长30秒。
3. 比较即时与有界等待后的帧；若需要验证某个已观察因素，最多追加一组4上下文
   的单变量只读对照，预先写清条件。无证据不修改生产，诊断脚本归档供复核。
4. Tests：本切片如仅增加诊断记录/归档则按docs-only检查；若确认缺陷需要修改
   运行代码，先在现有test_native.py/test_vision.py写行为失败回归，再最小修复，
   保留真实像素/引用/权限/未知副作用拒绝，并运行全部适用检查。
5. 归档原图、源脚本、源码hash、完整上下文分母和清理结果；记录结论及未解决项，
   更新主计划与索引，按项目规则完成最多三轮独立review-and-refactor。

## 交付结果

首组4上下文含1个准备失败，其余18次current检查13通过/5在像素层拒绝。
追加4上下文对照：按窗口RGBA每上下文3张一致，12个屏幕前后比较中1个变化。
离线合成只改窗口外像素，经原整屏缩小/窗口裁剪流程仍改变scene哈希；先裁剪
控制不变。没有生产修改，不能回填旧项唯一根因。8个真实上下文全部清理确认，
零模型、零任务输入；97项原始证据见[诊断记录](../../research/jev-frame-freshness-diagnostics.md)。
后续行为回归及最小捕获修复由仍active主计划承接，无新增条件暂缓条目。

第1轮review-and-refactor以a73f3f90为基线，独立核验97成员hash/字节数与原文件、
42源码及4脚本绑定，逐图重算18次current检查、窗口对照及合成差异，与记录一致。
8个上下文清理确认，7个成功上下文正文/选区不变，模型及任务输入均为零；实际
凭据字节扫描无命中，旧4归档hash不变。无可操作缺陷，仅补审查事实并关档，
docs与diff检查通过。源码未变，未重复全后端/E2E，未运行GUI或模型，不再开第2轮。

## Tests

首组4个上下文保留1个注册顺序准备失败，清理确认；修正临时脚本后只运行其余
3个，得到18次原current只读检查：13通过、5在像素门返回，窗口身份相同。
不能据此倒推旧stale_reference的唯一原因，像素拒绝时AX复扫尚未执行。

2026-10-19追加的唯一单变量对照：最多4个新上下文，使用同样RTF、位置、标题
选区与原channel。每上下文3轮“原屏幕捕获并裁剪 → 系统screencapture -l窗口ID
-o无阴影捕获 → 原屏幕捕获并裁剪”，前后核验绑定窗口和正文/选区。记录像素
与alpha哈希，不将新捕获方式接入生产、模型或坐标映射。两种方式实际分辨率
分别保留，不比较不同分辨率的逐像素相等，不修改像素以消除差异。

只读探查需验证正文/选区不变，所有上下文零任务输入和零模型请求，绑定窗口身份
一致且清理确认。像素差异由原图独立重算，跟踪器不得改变原current返回值。
临时诊断不证明新策略或模型质量；不把未复现当作缺陷已修复。

## Verification Checklist（最终步骤）

按实际改动执行；仅docs/原始归档时只需第9项，源码不变可引用已通过的旧回归。

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`，另检查变更benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <变更Python文件>`，不加type-ignore。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与全后端串行。
9. `python3 scripts/check_docs.py`、`git diff --check`；逐成员hash/字节数、来源源码与
   旧归档不变、零模型/输入及清理结果复核。
10. 协议或生成物变更才运行`python3 scripts/check_protocol_sync.py`。
