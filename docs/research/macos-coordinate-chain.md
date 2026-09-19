> 日期：2026-09-19；结论状态：开放（静态主屏变换已校准，偏差已复现于模型/服务端输出）；稳定定位方案与动态屏幕变化仍待验证。

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

## 2026-09-19 后续：坐标系判别与 calc-open 验收

最新 verify-calc 使用已修复版本，截图仍为 1920×1080。首个模型点击
(687,290) 转成 (1319,313)，在计算器外，早于 batch；后续错点打开背景
视频窗口并切走焦点。五个按钮若按 1280×720 图像像素解释，均接近真实目标，
因此提出“缩放后像素误作归一化”的假设，并进行了如下对照，而未硬编码补偿。

[新证据目录](../../backend/benchmarks/computer_use/reports/20260919-grounding-contract)
包含 8 张程序生成图、baseline.json、point-only.json、summary.json 和本地
计算器验收记录。未包含真实桌面 PNG，也未把真实桌面内容发送到模型。

实验使用相同 qwen3.7-flash-2026-07-15、temperature=0.1、实际 agent prompt
和 SDK；矩阵是 1920×1080、1280×720、1080×1920、1000×1000，左上/右下
两种布局，每图分别定位 AC/7。基线每例重复两次，共 32 请求。HTTP image
哈希全部等于本地生成 PNG。每条响应按三种假设计算到真实中心的欧氏距离：
0–1000 归一化、输入图原始像素、最长边缩至 1280 的像素。

基线 32 次中 18 次坐标可解析、14 次格式非法。非正方形的 13 个可解析
响应中，7 个按归一化解释在中心 15 pixels 内，1 个按最长边 1280 像素解释
在 15 pixels 内，其余 5 个三种解释均超过 15 pixels。1000×1000 时三个
假设完全重合，只能作为定位控制，不能用来判别坐标系。15 pixels 是本次
中心精度阈值，不等同于实际按钮命中率。

最有判别力的一对记录：同一张 1920x1080-0.png（哈希相同），7 的真实
中心 (560,311)。第一次响应 (379,205)，归一化误差 190.1 pixels，按
1280 像素假设误差 9.2；第二次响应 (296,283)，归一化误差 9.9，按
1280 像素假设误差 162.3。**固定图片也发生输出规则不一致，单一缩放因子
无法同时修正这些响应。** 这支持坐标参照系混淆，但不等于观测到服务端
内部 resize，也无法将所有错点归为坐标变换。

随后用相同 8 张图、相同指令，只把 click schema 改成必填整数 x/y，
去掉 bbox/oneOf，运行 16 次。16 次均可解析；归一化误差在 15 pixels 内
的有 8 次，超过 50 pixels 的仍有 6 次，最大约 394.5。甚至 1000×1000
控制图的一次 AC 也偏约 67.6 pixels，三种坐标解释在此等价。由此可见
还存在目标识别或位置估计错误，不能只靠消除坐标单位歧义解决。

32/16 次是有限诊断样本，不作为模型胜负或可靠成功率结论。point-only
只在探针使用；没有据此改变生产坐标协议，也未添加全局 1.5 补偿。

计算器验收已修复：macOS calc-open 在准备阶段清零并读取确认，结束时
读取前台、未最小化 Calculator 的 StandardResultView 与 StandardInputView，
同时要求表达式 7×8 和结果 56。不再仅凭进程存在判成功；Linux 仍 smoke。
评分版本升为 trial-token-gui-calc-v4，macOS 此任务 strict + GUI-only。
真实 trial runner 用确定性本地键盘输入验证：5×7 判失败，7×8 判成功，
覆盖真实 setup→driver→validator→teardown；没有调用模型。

验收器验证的是辅助功能树中的显示状态，不是屏幕 OCR；要求前台降低了
后台残留误判，不能证明所有浮动覆盖物都未遮挡。截图完成条件仍未单独
计分，未知 macOS 控件结构与权限不足会失败而不是降级为进程检查。

## 2026-09-19 继续：请求消融与服务端原始响应

[本轮证据](../../backend/benchmarks/computer_use/reports/20260919-grounding-ablation)
保留纯合成图、各组原始结果、后续请求的原始 SSE 和逐例评分。完整代理提示
与纯定位提示的区别、thinking 开关、显式尺寸公式、高分辨率开关分别对照。
同一模型与 temperature=0.1；工具组统一使用 point-only schema。
hard 集是旧样本中的四张非正方形图片，只定位 7，各重复两次；它包含已知
困难样本，不能用于估算任意桌面的成功率。holdout 使用新尺寸 1600×900、
900×1600 和新位置 (.3,.35)/(.65,.6)，分别定位 AC/7，共八例。

七组 hard 对照各 8 次：

- 完整代理提示：7 次可解析，2 次中心误差 ≤15 px，5 次 >50 px。
- 完整代理提示、关闭思考：4 次可解析，2 次 ≤15 px，1 次 >50 px；
  另有非法 JSON 与未声明的 screenshot 调用。
- 纯定位提示：8 次可解析，2 次 ≤15 px，5 次 >50 px，最大约 683 px。
- 纯定位提示、关闭思考：8 次全部非法 JSON；不能把“没有可评分的大误差”当成功。
- 纯定位提示加真实图片尺寸、两轴归一化公式：8 次可解析，2 次 ≤15 px，
  6 次 >50 px。显式公式未消除位置错误。
- 纯定位提示加高分辨率：8 次可解析，4 次 ≤15 px，3 次 >50 px，最大约 679 px。
- 纯定位提示改成普通 x/y JSON、无 tools：2 次符合点对象结构但带 markdown
  围栏（分别约 264 px、2 px），3 次擅自改为 bbox_2d 数组，1 次 JSON 损坏，
  1 次服务端 URL 错误、1 次超时。原始结果文件是早期严格 JSON 解析记录，
  summary.json 对完整围栏做了单独解码评分，没有修复损坏 JSON。

高分辨率组在原样本上略有改善，留出样本未显示稳定收益：完整代理提示
8/8 可解析、0/8 在 15 px 内、4/8 超过 50 px、最大约 236 px；纯定位加
高分辨率 8/8 可解析、1/8 在 15 px 内、3/8 超过 50 px、最大约 252 px。
这两组同时改变提示和分辨率，用于检验候选方案，不是单因素因果对照。
各组次数很少且服务端生成非确定，不能把差异当作统计显著结果。

### 确认格式损坏发生在服务端输出

对“纯定位、关闭思考”补录 4 次原始 HTTP SSE，独立逐帧连接 arguments
与本地 LLM 最终 arguments **4/4 完全相等**，且全部非法。例：
`{"x": 778, y=693]}`。将同一请求的 stream 改成 false，直接使用 SDK 的
8 次响应仍全部出现这类格式损坏。由此排除这批错误由本地 SSE 累加导致，
也排除“仅流式接口出错”的解释；仍不能区分模型权重与服务端工具编码实现。

真实 SSE 已成为 pytest fixture：经实际 OpenAI SDK 和 LLM 解析后仍保持
上述字符串，ToolManager 返回 error，底层 execute_tool 没有被调用。
另外的 HTTP 测试核对图片字节、两轴尺寸、provider 参数在请求顶层的位置、
工具/纯文本两种返回路径。**非法格式会被拒绝，但格式合法且落在 0–1000
内的错误坐标仍可执行**，不能靠 schema 验证判断“点的是不是目标”。

### 内部预处理的证据边界

[官方 API 文档](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)
给出的 Qwen3.7 默认 max_pixels 是 2621440；高分辨率模式提升上限。
1920×1080 的 2073600 pixels 本来低于默认上限。官方
[图像 Token 说明](https://help.aliyun.com/zh/model-studio/vision)描述 32 像素
对齐后的面积计数，加两个视觉标记。非流式实际 usage.image_tokens：

- 1920×1080 与 1080×1920：2042；与 1920×1088 / 1024 + 2 一致。
- 1280×720：882；与 1280×704 / 1024 + 2 一致。

这是**与近原尺寸 patch 对齐相符的证据**，不支持“所有图片都必定缩至
1280 宽”的假设；Token 数不能唯一反推内部图像形状，更不能看到后续
视觉编码、分块或模型对位置的表示。因此不把这些尺寸描述为直接观测值，
也不将它们用作运行时补偿倍率。

[官方思考模式文档](https://help.aliyun.com/zh/model-studio/deep-thinking)
列出本模型默认启用思考；实际记录中默认组返回 THOUGHT，关闭组为零，
并在 HTTP 请求体核实 enable_thinking=false。关闭思考不能修复本问题。

本轮没有真实桌面截图外发、没有执行模型动作、没有更改生产模型配置。
动态分辨率/跨屏/高频连点仍是独立验收项：本轮固定图片、无输入的实验
证明它们不是复现当前模型输出偏差的必要条件，不能宣称所有真机场景已排除。

### 原生边框格式候选

普通 x/y JSON 组有三次自行输出了 `[{"bbox_2d": [...], "label": ...}]`，
因此追加明确要求这种边框格式的对照，仍只发送同一批合成图，由本地计算
边框中心。hard 8/8 可解析且中心误差均 ≤15 px，最大约 11.8 px；相比
同图纯定位工具组的 2/8 明显改善。holdout 8/8 可解析、4/8 在 15 px 内，
最大约 41.1 px，均未出现 >50 px 的大偏移。全部响应仍带 JSON 围栏，
探针仅解包完整围栏，不修复内容。16 次新调用计入本轮总计 **100 次**。

这个结果说明**输出任务/格式会显著影响这批样本的定位表现**，与“自研
坐标换算统一乘错倍率”不符。它同时改变了中心点/边框任务和输出协议，
无法据此把全部原因归为某一个提示词或证明服务端的内部机制。新位置仍
有约 30–41 px 的误差，且只有四张新图，不能承诺真实 GUI 可靠命中。

可验证的后续方案是独立定位步骤输出边框，本地校验并换算中心，再结合
实际目标区域判断与点击后反馈；需要更多布局和不同按钮尺寸的独立样本，
以及真实输入的离线回放校准后才考虑替换生产路径。当前没有将该候选
写入生产提示或静默补偿已有坐标。

## 2026-09-19 同一提供方的模型对照

用户要求进一步判断提供方归因并换模型测试。新增探针 `--model` 仅替换
本次请求的 model，不修改配置或端点。依据官方模型资料选择
[Qwen3.7 Plus](https://help.aliyun.com/zh/model-studio/qwen3-7-plus) 和
[Qwen3 VL Plus](https://help.aliyun.com/zh/model-studio/qwen3-vl-plus)，与当前
Flash 比较；使用固定快照，保留同一 DashScope 服务、完整 agent 提示、
temperature=0.1、enable_thinking=true、max_tokens=4000。

[本轮原始证据](../../backend/benchmarks/computer_use/reports/20260919-grounding-model-comparison)
复用上一轮合成图，HTTP 图像 hash、请求 model/参数以及响应 model 均核实。
每个模型 point-only schema 的 hard/holdout 各八次；又用生产完整 click
schema（含 bbox/oneOf）复验 Flash/Plus 各十六次。只有 click 被声明，
不等于包含所有工具与真实桌面的完整 agent benchmark。

已完成的 Flash/Plus point-only 对照：

- Flash：16/16 可解析，5/16 中心误差 ≤15 px，8/16 >50 px，最大约 414 px。
- Plus：16/16 可解析，15/16 中心误差 ≤15 px，1/16 >50 px，最大约 86 px。
  唯一大误差是竖图 7，响应 (720,695) 对应点 (777.6,1334.4)，目标
  (782,1420)；重复请求随后定位正确。
- VL Plus：16/16 可解析，7/16 在 15 px 内，2/16 超过 50 px，最大约
  157 px。hard 集没有 >50 px 的大错，holdout 仍出现约 128/157 px 的错点。
  本轮 hard/holdout 请求耗时中位数约 32.6/31.4 秒，明显慢于其他两款；
  请求并发和网络未做性能隔离，不能视为正式延迟 benchmark。

生产 click schema 下差异仍存在：Flash 16/16 可解析、3/16 在 15 px 内、
12/16 超过 50 px、最大约 471 px；Plus 16/16 可解析、15/16 在 15 px 内、
1/16 超过 50 px、最大约 150 px。因此 Plus 的改善不只出现在简化 schema
条件，但个别大错仍存在，不能直接宣称真实 calc-open 已修复。

总计 **80 次请求全部可解析**，与上一轮的格式错误并不矛盾，而说明
格式正确仍不足以保证点击正确。Plus 值得优先继续验收，当前证据支持
定位可靠性与模型/输出适配相关，不能据此认定提供方整个平台有故障。
探针相关 pytest 24 passed，完整 backend **4452 passed, 1 skipped**；
E2E 14 scenarios / 55 steps、web lint/tsc、backend/CLI ruff、改动文件
pyright、docs/protocol consistency、实际后端 reload 日志检查全部通过。

### 归因与仍需区分的原因

1. **已定位的责任边界**：部分 API 响应在抵达本地时已经格式非法或位置
   错误；当前静态主屏校准与原始响应回放不支持“大偏移来自本地统一倍率”
   的解释。测试通过仅覆盖已测条件，不是对所有动态条件的证明。
2. **不能泛化成提供方平台故障**：同一服务的 Plus 明显改善，支持模型及
   其服务实现相关的问题。模型权重、推理配置、视觉预处理与 OpenAI 兼容层
   仍在同一个不可直接观测的服务边界内；非流式也失败不能排除兼容层。
   区分这些原因需要同模型的原生/兼容 API 对照，或同权重跨部署对照。
3. **定位任务与输出协议适配**：旧模型改为原生 bbox_2d 明显改善，说明
   边框/中心点任务和工具格式影响表现。目标文字识别、密集邻接按钮和
   坐标参照系混淆都可能参与；并非所有错误都能通过换算修复。
4. **动态几何的代码风险仍在**：macOS 工具的 `_screen_point_size` 是模块
   全局状态，仅截图后更新；click 没有核对该截图的显示器身份/当前几何。
   截图后切换主屏/分辨率，或多会话覆盖缓存，需要单独验收。
5. **视觉状态与执行时序**：截图后窗口移动、弹窗/动画/焦点变化，会让
   正确的旧坐标失效；batch 顺序发事件、通常结束后才截图，没有逐动作
   视觉反馈。这些可能放大真实任务失败，但不是固定图无输入实验出错的
   必要条件，历史 calc-open 首次错点也早于 batch。

仍仅发送合成图，生产模型保持 Flash；真实桌面内容未重新发送模型。
样本数量很少，holdout 是相对原困难集而言，已在先前实验使用过，不能
作为全新无偏选型集；15 px 为中心精度阈值而不是按钮命中率。

## 2026-09-19 跨提供方与严格协议隔离

结论状态：本轮隔离完成；最有证据的瓶颈是当前模型/定位任务的可靠性，
不是 macOS 静态坐标链的统一倍率错误。模型权重与服务端视觉处理仍无法
分开归因，真实模型驱动的完整 calc-open 尚未验收。

[304 次请求的复现说明与原始证据](../../backend/benchmarks/computer_use/reports/20260919-protocol-models/README.md)
覆盖七个候选、三种坐标协议、nullable schema、strict、标记/打乱布局、
裁剪/缩放、历史图、agent/完整桌面工具定义、原生/兼容接口及 detail 参数。
外发内容全部为生成的校准图，没有真实桌面、截图路径或用户文件。
新探针通过实际 OpenAI SDK 调用，不执行模型返回动作，不修改生产配置。

### 模型与独立布局结果

基线使用四张新布局，每模型/协议四次。归一化点的按钮命中数：当前
Qwen3.7 Flash 0/4、Plus 2/4、Qwen3.8 Flash 4/4、Max 3/4、DeepSeek 4/4、
GPT Mini 4/4、GPT-5.5 4/4。三协议的 84 个响应全部符合单一整数约束，
但存在大量位置错误。边框不普遍更好：Qwen3.8 Flash 2/4、Max 1/4、
DeepSeek 2/4 命中。这个 flat bbox 工具协议与旧 bbox_2d 文本实验不同。

筛选后用未参与调参的 16 个新布局、每图重复两次，测试归一化点：

- **GPT-5.5：32/32 命中**，中心误差中位数 1.01 px，最大 2.08 px。
- **GPT-5.4 Mini：30/32 命中**，中位数 4.77 px，最大 38.83 px。
- **Qwen3.8 Flash：25/32 命中**，中位数 5.56 px，最大 417.91 px。

这 96 个响应全都通过格式校验；“整数且在范围内”显然不等于正确定位。
留出集沿用四种画布尺寸和两种标签，只改变位置，不是跨应用、跨字体或
各种小按钮的通用验收。评分使用生成按钮的圆角 mask，并独立记录有符号
dx/dy 与欧氏中心距离；命中不等于完成计算器任务。

Qwen 使用当前 DashScope 端点；DeepSeek 使用官方 deepseek-flash。
用户指定 GPT 使用 OpenRouter，读取 OPENROUTER_API_KEY，限定 openai
provider、禁止 fallback，并在全部返回值中核实 provider=OpenAI。
GPT 的生产服务直连路径未测试。Qwen3.8 Max 请求快照
qwen3.8-max-2026-09-02，实际返回官方别名 qwen3.8-max-0902。
DeepSeek 别名可能变化，不能把旧 Pro 路由算成另一个独立模型。

### 输出约束的效果与兼容陷阱

新候选协议试用了 found + nullable 整数坐标。四个 Qwen 在 type-array
写法共八次、语义等价 anyOf 写法共八次均输出字符串坐标；设置 strict
也未阻止。DeepSeek/GPT 在相同预检中返回整数。它是新协议的适配问题，
不能倒推成生产代码原先就有 nullable schema 的问题。

矩阵默认改为单一 integer 类型；未找到时 found=false 且所有坐标为 0，
这是明确的“不点击”状态。保留 nullable 作为实验开关，其未找到状态必须
为 null。两种约定都在宿主严格校验，不猜单位、不交换边框、不将字符串
或数组修复成数字。host 计算边框中心、裁剪偏移和逐轴缩放。
这些校验目前只在实验探针中，未宣称生产 ClickTool 已采用新协议。

严格边框追加实验中，当前 Flash 0/2 命中，GPT-5.5 与 Qwen3.8 Flash
各 2/2；样本太小，不能据此替代更大的重复验收。DeepSeek 一次边框
定位错误，另一次耗尽 4000 reasoning tokens，没有输出工具调用。
low-detail 条件也有一次同样的预算截断，两次均保留 finish_reason=length，
不计为“严格解码仍产生非法整数”的证据。

### 其他原因的隔离

- **视觉识别与空间表达**：当前 Flash 在标记、裁剪、缩放、打乱布局
  条件各两次都未命中，单纯增加标记或裁剪不能修复。它们没有直接暴露
  模型内部识别结果，不能严格区分 OCR 与空间表达两种原因。
- **历史与提示**：GPT-5.5 在所有有目标隔离条件命中，并正确拒绝两个
  缺失目标；Qwen3.8 Flash 在历史/agent/完整工具定义下各 2/2 命中。
  当前 Flash 在最小提示中已经失败，完整工具定义不是失败的必要条件。
  历史实验仅加入一张旧位置图片，不包含完整长会话、compaction 或真实
  AgentRunner 的所有自动注入；这些仍是生产验收缺口。
- **思考参数**：Qwen3.8 Flash 关闭思考后两次把整数字段写成数组，宿主
  均拒绝。当前 Flash 在这两张图关闭思考后 2/2 命中，但之前更大实验
  已失败，不能以这两个样本证明通用修复。
- **原生/兼容接口**：原生 DashScope 多模态接口中，当前 Flash 1/4 命中、
  最大误差 281.96 px；Qwen3.8 Flash 2/4 命中、最大 533.33 px。
  因此兼容层不是大偏移发生的必要条件。四次随机响应不足以证明哪种
  API 更好；也不能排除两者共用的视觉预处理或推理服务问题。
- **服务端图像处理**：GPT-5.5 的 detail=low 首次出现一次 406.94 px 大错；
  追加同图 auto/low 各六次均命中，low 最大 3.91 px。大错未复现，不能
  将此宣称为确定的内部缩放错误。实际 HTTP 图片 hash 相同仅证明上传
  图片相同，不证明内部视觉 token、分块或有效清晰度相同。

### 本地真实 Calculator 对照与验证边界

[本地 oracle 记录](../../backend/benchmarks/computer_use/reports/20260919-calculator-oracle/results.json)
读取 AXIdentifier 为 Seven、Multiply、Eight、Equals 的按钮位置，以实际
ScreenshotTool 建立 1920×1080 坐标尺寸，再经生产 ClickTool 输入。三次
完整操作都被独立 AX 校验为 7×8=56；12 次光标观测最大偏差 1 个逻辑点。
真实截图仅用于本地内存中的尺寸读取，未外发或归档。

首轮尝试曾因光标不在按钮内的断言失败，当时未在断言前保存坐标，因此
无法判断是事件观测时序、外部输入还是其他原因。随后已修正实验记录顺序，
完整三次通过；不能抹去首轮异常或声称所有真实输入问题已排除。
动态跨屏与分辨率不是这些纯合成、无输入失败的必要条件，按用户提供的
benchmark 运行条件降为低优先级。

当前可推进的候选为 **GPT-5.5 + 明确点坐标约定 + 本地严格校验 + 点击后反馈**；
还需在获准的真实画面或隔离合成桌面中运行完整模型闭环，之后才考虑生产
切换。未把 32/32 合成图命中宣称为 calc-open 已修复。

新增探针相关 pytest 共 **40 passed**；完整 backend **4468 passed, 1 skipped**；
web lint、tsc -b、backend/CLI ruff、修改文件 pyright、E2E **14 scenarios / 55 steps**、
docs/protocol 与后端 reload 检查通过。完整测试需本机 Opus 库路径与沙箱外
本地端口访问；另修复一个通知测试将输出写入真实用户目录的测试隔离问题。

官方参考：[Qwen3.8 Flash](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)、
[Qwen3.8 Max](https://help.aliyun.com/zh/model-studio/qwen3-8-max)、
[DeepSeek 版本公告](https://api-docs.deepseek.com/news/news260910/)、
[DeepSeek strict](https://api-docs.deepseek.com/guides/tool_calls/)、
[OpenAI Function calling](https://developers.openai.com/api/docs/guides/function-calling)、
[OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)。
