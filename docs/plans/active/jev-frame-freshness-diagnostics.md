> 状态：进行中（2026-10-19：开始离线及无模型调用的真实TextEdit新鲜度诊断）。

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

## Tests

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
