> 状态：进行中（2026-10-19：开始绑定帧先裁剪后缩放的TDD修复）。

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
