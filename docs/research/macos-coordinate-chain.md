> 日期：2026-09-18；结论状态：已解决（代码链路与离线复现）；真实模型与桌面投递仍未验收。

# macOS 从截图到鼠标点击的尺寸与坐标

范围是自研 `computer_use`；旧 N2 的 DesktopExecutor 只比较共享截图与
点击路径。官方 N2 SDK 的截图预处理不是本链路，不能混用结论。
本次仅增加测试，不修复运行逻辑。

## 逐步变换

1. **获取屏幕信息**：`_get_display_scale_factor` 从主显示器的
   `CGDisplayModeGetPixelWidth / CGDisplayModeGetWidth` 取整得到倍率。
   例：3840 backing pixels / 1920 logical points = 2。
   代码没有读取显示器原点，也没有用独立逻辑高度校验 PNG。
2. **原始截图**：`screencapture -x -C` 写 PNG，例为 3840×2160。
   输入工具最终交给 CGEvent 的单位是逻辑 points，不是这张原图的 pixels。
3. **缩放**：倍率大于 1 才调用 `sips --resampleWidth 1920`；保持宽高比，
   例图变成 1920×1080。失败时只记录 warning，仍返回 3840×2160 原图。
4. **缓存**：ScreenshotTool 读取 PNG 宽高，直接赋给 `_screen_point_size`。
   成功路径为 (1920,1080)；失败路径为 (3840,2160)，这一步混淆了单位。
   DesktopExecutor 同样从 PNG 更新 `_size`。未截图时两者均回退 1920×1080。
5. **可选裁剪**：region 用全屏 0–1000 表示。
   `[500,500,1000,1000]` 在 1920×1080 图上截取右下角 960×540，
   再放大 2 倍成 1920×1080；放大倍数最多 3。
   缓存仍是完整屏幕大小，不变成 crop 大小。
   裁剪中心 (500,500) 必须由模型换回全屏 (750,750)。工具不会自动还原。
6. **图像进入模型消息**：PNG bytes → Base64 data URL → ImageBlock(detail=auto)
   → `_tool_result_to_llm` → `_build_follow_up_user_message` → user-role
   `image_url`。本地这几步不 resize、不裁剪、不改字节。
   tool-role 消息只有指向后续多模态消息的提示；UI 的 “Screenshot captured”
   不是模型收到的全部内容。实际提供商如何缩图/切片不在本地代码可见范围内。
7. **模型返回参数**：要求全屏 0–1000，bbox 则取中心。
   数字字符串转整数，浮点数截断，结果 clamp 到 [0,1000]。
   因此 1030 会变成 1000；800 pixels 和 800 normalized 无法靠范围区分。
8. **输入转换**：直接工具为 `int(nx * W / 1000)`、`int(ny * H / 1000)`。
   例 (750,750) → (1440,810) points。
   DesktopExecutor 使用 `round(nx * (W-1) / 1000)`，边界差约 1 point。
   工具的 (1000,1000) → (1920,1080)，executor → (1919,1079)。
9. **系统事件**：`CGPointMake(px,py)` → mouse down/up CGEvent → CGEventPost。
   这一段没有再次乘 Retina 倍率。工具成功只表示注入调用未抛异常，
   不表示按钮命中，也没有实际鼠标位置或目标控件回读。

实现入口：[macOS tools](../../backend/core/src/tank_backend/tools/computer_use_macos.py)、
[共用转换](../../backend/core/src/tank_backend/tools/computer_use_common.py)、
[LLM 序列化](../../backend/core/src/tank_backend/llm/llm.py)、
[executor](../../backend/core/src/tank_backend/computer/executor.py)。

## 旧测试是否覆盖全部转换

**没有。** [原有 macOS 测试](../../backend/core/tests/test_computer_use_macos.py)
的 TestScreenshotTool mock 整个 `_capture_screenshot_macos`，
TestClickTool mock 整个 `_click_macos`。它们分别验证 PNG 缓存和坐标算式，
但中间两个重要 OS 边界被跳过，不能发现 sips 失败造成的单位混淆。

- TestScreenshotZoomMacos 原来只检查 note 和缓存，没有核对实际裁剪像素
  或后续点击。新增测试用右下角红色目标核对裁剪、放大、还原位置。
- [参数测试](../../backend/core/tests/test_computer_use_common.py) 已覆盖多种
  bbox/字符串/clamp；新增测试将参数一直送到 Quartz 事件参数。
- [多模态结果测试](../../backend/core/tests/test_tool_result_extraction.py)
  已覆盖 follow-up/image_url 结构；新增测试让真实截图结果经过相同 serializer，
  核对 URL 字节不变、detail=auto 和 PNG 解码尺寸。
- [batch 测试](../../backend/core/tests/test_computer_batch.py) 已覆盖调用顺序
  和图像返回；新增测试回放历史坐标并核对每个事件落点与批后图像。

## 新增 pytest 及其证据强度

同一 macOS 测试文件中新增 `capture_chain` fixture；只替换 subprocess 与
Quartz，保留真实截图函数、Pillow 裁剪、Base64、LLM serializer、参数转换、
ClickTool/ComputerBatchTool/Executor 和 `_click_macos`。
模拟 sips 用真实 Pillow resize，**不等于验证 macOS sips 实现**。

- `test_capture_to_wire_to_quartz_preserves_coordinate_space`：1x/2x、
  1920×1080 与 1512×982，核对返回图尺寸/像素、消息和 mouse down/up 参数。
- `test_known_resize_failure_uses_retina_pixels_as_points`：工具和 executor
  两条路径都复现 (500,500) 错映射成 (1920,1080)，正确值应为 (960,540)。
  这是**已知缺陷的现状刻画**，断言错误结果是为了验证诊断；通过不代表缺陷修复。
  修复时必须将断言改为正确逻辑坐标或明确失败，不能保留错误行为来迁就测试。
- `test_zoom_wire_pixels_and_full_screen_click_mapping`：裁剪后点击 (750,750)
  命中原屏目标；直接传局部中心 (500,500) 得到另一个点，证明没有自动还原。
- `test_small_crop_caps_zoom_at_three_without_changing_click_space`：192×108
  小裁剪只放大到 576×324，缓存和点击仍使用完整屏幕。
- `test_model_arguments_reach_quartz_after_real_capture`：字符串、bbox、
  越界截断、原点和最大边界的真实转换结果。
- `test_batch_replays_calculator_miss_and_returns_wire_screenshot`：回放
  20260918-082609-computer-use/calc-open/1 的固定调用值；全部点在窗口右侧。
  原截图中手工估读窗口右边界为 x≈1192；测试不声称自动测量原图或调用模型。
- `test_executor_and_tool_have_different_edge_rounding`：证明两条路径边界
  相差 1 point，这个差异解释不了数百像素的误差。

## 历史样本与限制

1920×1080 原图上 AC 中心约 (1021,434)，归一化约 (532,402)。模型却输出
(690,288)，工具算成 (1324,311)，已在窗口外。
最后一次等号坐标 (775,433) → (1488,467)，与批后截图光标近似吻合。
相关档案：[trace](../../backend/benchmarks/computer_use/reports/20260918-082609-computer-use/trials/calc-open/1/trace.jsonl)、
[原图](../../backend/benchmarks/computer_use/reports/20260918-082609-computer-use/trials/calc-open/1/screenshots/shot_001.png)、
[批后图](../../backend/benchmarks/computer_use/reports/20260918-082609-computer-use/trials/calc-open/1/screenshots/shot_002.png)。

离线测试没有验证提供商的图像预处理、模型定位能力、真实 screencapture/sips、
真实 Quartz 事件投递、系统缩放设置、多屏原点、窗口动画或人为鼠标干扰。
因此不能声称“每种转换都已真机验证”。今天样本没有裁剪，截图为 1920×1080，
目前证据优先指向模型给错坐标，不支持将今天的错误归因于 2x 缩放失败。

复现命令：`cd backend && uv run --no-sync pytest core/tests/test_computer_use_macos.py -q`。

新增 14 个参数化用例；该文件共 61 项，包含参数规范化、executor、batch 和
工具结果序列化的五文件组合回归 191 passed。完整检查结果及未解决失败见
[验证计划](../plans/active/macos-coordinate-chain-tests.md#结果)。
