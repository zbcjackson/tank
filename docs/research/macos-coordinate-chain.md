> 日期：2026-09-19；结论状态：已解决（本机静态主屏链路与模型隔离定位）；动态屏幕变化及模型内部预处理未验证。

# macOS 从截图到鼠标点击的尺寸与坐标

范围是自研 computer_use 与共享 MacOSDesktopExecutor；官方 N2 SDK 不在本链路。
此前仅有现状刻画测试，本轮已增加正确性回归并修复明确缺陷。

## 结论与证据

真实主屏为 1920×1080 logical points、3840×2160 backing pixels。
专用 AppKit 窗口九点校准通过：真实截图中的红色目标、CGEvent 点击、窗口
收到的按下及释放事件一致；最终一轮每轴最大误差 1 point，最大距离约 1.42 points。
这符合归一化到整数坐标的取整误差，解释不了历史样本数百像素的偏移。

只发送用户授权的合成图至配置的 qwen3.7-flash-2026-07-15 / DashScope。
复杂合成计算器上，AC 真实中心 (1021,434)，一次模型 bbox 中心映射为
(1328,428)，横向偏离 307 points；另一次 1280×720 输入返回 (688,288)，
映射回主屏 (1320,311)。错误已存在于模型响应，尚未执行任何鼠标动作。
请求中的图片 SHA-256 与本地图片相同；未发现本地序列化改变图片。

这是当前大偏移最直接的证据：模型定位/坐标输出错误。无法继续细分为模型
视觉识别、坐标约定理解还是提供商内部预处理；不能断言是云端 resize。

## 逐步变换与测试边界

1. **显示信息与截图**：主屏 backing width / logical width 得到浮点倍率，
   不再用整除丢弃 1.5x 等比例。`screencapture -x -C -m` 显式只截主屏。
   本机原始图 3840×2160，输入事件使用 points。
2. **缩到逻辑尺寸**：倍率大于 1 时 `sips --resampleWidth 1920`，保持比例
   得到 1920×1080。缩放失败立即返回错误；成功后用 Pillow 同时检查宽、高
   与 Quartz 逻辑尺寸一致。避免将原 Retina pixels 当作 points。
3. **缓存**：ScreenshotTool 缓存完整 PNG 尺寸，executor 同理。
   必须先截图；未截图仍有 1920×1080 默认值。截图之后改分辨率/主屏、窗口
   移动或动画不由缓存自动追踪，不能将本次静态验证外推到这些场景。
4. **可选裁剪**：region 为全屏 0–1000。右下半屏 region
   [500,500,1000,1000] → 960×540 crop → 2x 放大为 1920×1080；最多 3x。
   完整屏幕缓存不变。模型必须把 crop 局部坐标还原为全屏坐标：
   `full_x = left + local_x * (right-left)/1000`，y 同理。
   工具不自动还原，也不自动判断模型给的是局部坐标还是全屏坐标。
5. **发送模型**：PNG bytes → Base64 data URL → ImageBlock(detail=auto)
   → tool-result serializer → 后续 user-role image_url → OpenAI SDK HTTP JSON。
   本地无额外 resize。tool-role 文本只是图像消息提示，UI display 不是模型输入。
   服务端缩图/切片不在本地可观测范围内。
6. **接收参数**：SDK 解析 SSE，累积工具名与分片 JSON 参数，ToolManager 分派。
   x/y 数字字符串转数值；bbox 数组取中心。macOS 拒绝非有限数、越界值及
   非法结构；不再把 1030 静默 clamp 为 1000。数值范围合法仍不保证语义正确，
   例如 800 pixels 与 800 normalized 不能只靠范围检查区分。
7. **归一化到 points**：工具使用 `min(W-1, int(nx*W/1000))`，y 同理。
   (750,750) → (1440,810)，(1000,1000) → (1919,1079)。executor 使用
   `round(nx*(W-1)/1000)`；两者内部点仍可能有约 1 point 的取整差异。
8. **系统投递**：CGPointMake → mouse down/up CGEvent → CGEventPost。
   不再乘 Retina 倍率。工具返回成功本身不证明命中；真机校准另行回读鼠标、
   记录窗口实际收到的事件，并核对截图目标像素。

实现：[macOS tools](../../backend/core/src/tank_backend/tools/computer_use_macos.py)、
[共用转换](../../backend/core/src/tank_backend/tools/computer_use_common.py)、
[LLM](../../backend/core/src/tank_backend/llm/llm.py)、
[executor](../../backend/core/src/tank_backend/computer/executor.py)。

## pytest 覆盖

[macOS 测试](../../backend/core/tests/test_computer_use_macos.py) 的 capture_chain
只替换 subprocess 与 Quartz；截图函数、Pillow、Base64、序列化、工具执行均真实。
模拟 sips 使用 Pillow，不能替代真机 sips 验证。

- capture_to_wire_to_quartz：1x/1.5x/2x、非正方形与非整千尺寸，核对像素、
  消息与最终 Quartz 事件参数；确认 -m 主屏标志。
- resize_failure_never_advertises_retina_pixels_as_points：缩放失败时工具和
  executor 都报错；替换了原来“断言错误 2x 行为”的现状测试。
- successful_but_wrong_screenshot_dimensions_are_rejected：命令返回成功但
  PNG 与逻辑高度不符仍报错。
- zoom_wire_pixels_and_full_screen_click_mapping / small_crop_caps_zoom：
  真实裁剪、2x/3x 放大、目标像素、全屏缓存与坐标还原。
- model_arguments_reach_quartz / macos_rejects_invalid_coordinates：字符串、
  bbox、原点、端点、越界小数、NaN/Inf；错误输入不创建鼠标事件。
- http_tool_loop_preserves_image_and_fragmented_coordinates：真实 AsyncOpenAI
  + httpx.MockTransport HTTP JSON 边界 + 字符级 SSE 参数碎片 + ToolManager，
  截图、模型消息、click 和下一轮消息一起验证；含全图与 crop。
- recorded_synthetic_model_coordinates_reach_expected_points：重建请求图片并
  验证 hash，将真实模型归档参数送入真实 ClickTool、只 mock OS；核对准确落点
  与目标命中，非法 bbox 字符串不注入，错误工具名单独分类。
- batch 与 executor 回归保留；最大边界现在都位于显示器内部。

这些测试覆盖已识别的本地主屏静态转换，不是“所有硬件/状态/模型输出都正确”
的证明。模型自身从 crop 还原坐标的能力只可通过真实模型样本评估，不能用
预设正确输出的 mock 测试证明。

## 固定合成图实验

[证据目录](../../backend/benchmarks/computer_use/reports/20260919-synthetic-coordinate-isolation)
包含两张程序生成 PNG、三组 JSON 及运行时探针源文本。没有真实桌面截图。
源文本是一次性实验记录（含本机工作目录），不是通用运行工具。

使用实际 agent prompt、click schema、LLM.chat_stream，关闭 tracing，无
工具执行器。每张图分别问 AC 与 7，temperature 使用项目配置 0.1。
目标内部区域：AC [994,413,1048,455]、7 [928,467,982,509]。
裁剪 region [450,350,620,620]，326×292 裁剪放大 3x 成 978×876。

- 稀疏合成界面：全图与裁剪共 4 次，4 次命中。
- 密集科学计算器与纯生成背景：共 12 次（全图重复、crop、1280×720、960×540）；
  2 次命中、5 次合法参数但位置错误、4 次非法 bbox 字符串、1 次返回未提供的
  screenshot 工具名。错误工具名不算 click；归档保留并标注探索脚本原评分。
- 密集图 crop 的 7 命中，但 AC 格式非法；960×540 的 7 命中、AC 格式非法；
  1280×720 两个都错。因此不能说裁剪或统一缩图已稳定解决问题。

仅 16 个诊断请求，不作为成功率 benchmark。它们隔离了模型输出问题，未证明
换模型、提示词调整或局部定位协议的收益；这些需要独立重复实验。

## 真实校准与限制

[校准脚本](../../backend/scripts/calibrate_macos_coordinates.py) 不联网，只操作
自己创建的窗口。主屏 origin=(0,0)，当前两台显示器中只测试主屏。
检查 Screen Recording / Accessibility，核对截图红色目标后才点击，记录
AppKit 局部坐标、CGEvent 坐标、鼠标回读及 down/up，失败立即停止并还原鼠标。

第一次运行第二点没有收到事件，鼠标位置已到正确点附近；第二次九点按下
命中，其中一个鼠标回读与事件不同。它们保留为异常观察，无法据此确定原因。
随后增加等待释放及 1 秒间隔的完整九点校准连续两轮通过；恢复原来的
0.1 秒额外间隔后再跑九点，按下/释放与落点也全部通过。最终 JSON 单独归档，
真实截图只存本机 /tmp，未发送模型、未纳入仓库。每次截图自身有耗时，此实验仍不等于无截图的高频连点压力测试；
人为输入与系统调度也尚未隔离。

历史计算器 [trace](../../backend/benchmarks/computer_use/reports/20260918-082609-computer-use/trials/calc-open/1/trace.jsonl)
中的 (690,288) → (1324,311) 本就在窗口外；与本轮合成图证据方向一致。

未验收项：切换主屏/分辨率、非主屏与跨屏、旋转、截图后窗口移动、并发鼠标、
高频输入稳定性、提供商内部 resize。它们不阻止对“当前静态主屏出现大偏移”
的定位，但不能被描述为已经全部排除。

完整检查结果见 [验证计划](../plans/done/macos-coordinate-chain-tests.md)。
