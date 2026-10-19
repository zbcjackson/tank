> 状态：已完成（2026-10-19：实现46567ca5，后端6331通过/1跳过、E2E21场景通过、真实只读24/24，第1轮独立审查无可操作问题）。

# 绑定窗口帧的裁剪与缩放

## 目标与范围

承接[新鲜度诊断](../../research/jev-frame-freshness-diagnostics.md)确认的整屏缩小
再裁剪边缘串色机制。NativeAXChannel的模型图及执行前像素复查均改为获取指定
显示器原始backing图，先在原始像素中裁剪绑定窗口，再缩放输出。通用逻辑分辨率
截图默认不变，不使用按窗口ID离屏捕获，不修改严格像素、窗口/进程/AX与输入门。

Observation保留逻辑screen_size/crop、显示器原点和图内坐标映射；scene哈希覆盖
原始裁剪像素，窗口内变化仍拒绝。原生AX目前仍仅支持主屏，副屏几何在通用帧
映射层验证，不借此声称新增AX副屏执行能力。零新收费调用，旧模型评分不追改。

## 步骤

1. Tests：在现有test_vision.py、test_computer_use_macos.py按TDD逐项覆盖绑定
   窗口外紧邻像素变化不影响PNG/scene、窗口内单像素仍失效，1x/1.5x/2x、窗口
   边界、负坐标副屏映射及非法尺寸拒绝；通过实际channel.current验证原门仍在。
2. 最小实现：截图函数显式原始backing选项；Observation先裁剪再归一化和放大；
   NativeAXChannel捕获与复核使用同一路径。保留普通截图默认路径及原生授权门。
3. 运行完整适用回归；以实际sips/旧合成图作离线边缘复核。必要时最多4个自有
   TextEdit只读上下文验证新路径/清理；不调用真实模型、不派发任务输入。
4. 更新现行设计/测试说明、主计划和索引，归档验证证据；完成强制独立
   review-and-refactor，最多三轮；所有项目完成后移done，未完成的后续由主计划承接。

## 实现与验证记录

实现提交46567ca5：原生通道的捕获和current均显式请求backing图；Observation
先在原始像素裁剪窗口，再按原逻辑尺寸放大策略生成PNG。screen_size/crop仍为
逻辑点，显示器原点与map_point保持；scene哈希覆盖原始裁剪像素。普通截图
默认仍走原逻辑缩图路径；不加像素容差、不采用离屏窗口捕获，不改变原生AX
仍仅主屏的限制。新增17项参数化行为用例，先观察到失败再最小实现。

专项461通过（35.57秒），后续奇数/整屏边界补充用例纳入完整后端6331通过/
1跳过（453.49秒）；web lint/项目引用类型检查、backend/CLI lint、五个修改
Python文件pyright及dev server错误日志均通过。dev日志为空按规则通过，不重复。
真实TextEdit新建4个实验文档，24次原current检查全部通过、52份窗口PNG哈希
核验、正文/标题选区保持、4清理确认，0模型调用、0任务输入。该检查并非与旧
诊断配对，不从24/24推导稳定率改善或动态GUI可靠性。

离线复核使用旧合成原图、实际截图函数与真实sips（仅替换screencapture输入）：
普通逻辑路径保留窗口外变化引发scene改变的旧现象；backing新路径的窗口外
变化不改变PNG/scene，窗口内单像素仍改变scene。源码hash与真实检查保持一致。
本次不是模型质量重测，不追改旧TextEdit完成率，旧原始归档保持不变。

E2E21场景/83步骤全部通过（135.790秒），与完整后端串行执行。docs与diff检查
通过，协议未变，第10项不适用。原始证据见
[验证归档](../../research/artifacts/jev-bound-frame-capture-20261019.tar.gz)和
[逐文件清单](../../research/artifacts/jev-bound-frame-capture-20261019-manifest.json)。
归档共71项、5064086字节，SHA256为
`d9235bc413b6ef984e85b611c06b4e9661be3a2e13d21739e1a9539a0622dc6f`。
覆盖真实只读帧/检查、离线输入/输出/脚本、TDD失败及最终回归日志；逐成员
hash/字节数与原文件一致，实际API凭据字节扫描无命中，旧5份Jev原始归档不变。

第1轮独立review-and-refactor对照基线11b4e73b审查全部变更，未发现可操作问题，
未改源码。独立运行macOS/common/native/vision专项467通过（34.18秒），
复核71项归档成员hash/字节数、42项源码绑定及24次current/52份PNG/4次清理。
源码未在完整后端与E2E后变化，复用其通过证据；本轮仅补记录与计划归档，
再运行docs/diff检查。后续新配方模型重测与拒绝阶段诊断由仍active的
[主计划](../active/computer-use-jev-vision.md)承接，本切片不包含新收费运行。

## Tests

先写一个失败行为回归，再最小实现，逐项扩展。优先使用原生通道和真实Pillow/
截图函数，只替换OS/HTTP边界；不写仅验证新增参数存在的镜像测试。原像素变化、
窗口切换/撤权、未知副作用与Box只读回归均须继续通过。真实模型质量不由fake测试
推断。新截图配方不得复用旧源码冻结做新的付费运行。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部变更Python文件>`，不用type-ignore。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与全后端串行，避免浏览器资源竞争。
9. `python3 scripts/check_docs.py`、`git diff --check`；如有归档核验成员hash/字节数，
   旧原始归档保持不变。
10. 协议/生成物变更才运行`python3 scripts/check_protocol_sync.py`；本片无协议变更。
