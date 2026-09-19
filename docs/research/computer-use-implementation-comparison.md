> 日期：2026-09-19。结论状态：调研已完成；候选改进尚未实现或实机验证。

# Computer use：模型差异与实现设计的责任边界

## 结论

两者都有。固定截图实验已证明模型服务在当前任务/协议下的输出可靠性存在
差异，但不能据此排除宿主设计问题，也不能把差异直接归为提供方故障。
Tank 已确认提示冲突和输入语义问题，局部截图仍要求模型还原全屏坐标。
比继续增加坐标提示更值得尝试的是：修正接口语义，让宿主负责几何计算，
按模型适配坐标协议，并为 macOS 增加 AX 元素寻址的独立对照。

本轮阅读官方文档和公开源码，没有安装这些项目、上传桌面或调用付费模型。
外部实现说明“可以怎样设计”，不证明迁移后一定提高 Tank 的成功率。
下面的运行证据来自[统一验证记录](../design/computer-use.md)，新的实验均为建议。

## 模型差距到底证明了什么

- 固定合成截图在发出鼠标事件之前，原始模型响应已包含大偏移。跨屏、动态
  分辨率和高频输入不是这批错误的必要条件；在用户描述的稳定 benchmark
  中，暂不把它们作为首要排查方向。
- 16 个独立布局在同一归一化点协议下各重复两次：GPT-5.5 32/32 命中、最大误差 2.08 px；
  Qwen3.8 Flash 25/32、最大约 418 px。格式全部有效。这证明当前部署与接口
  组合的差异，不能推广为所有 GUI、各模型最佳适配后的排名或生产可靠率。
  同一布局的两次测量不是两个独立布局；不同提供方、推理和预算仍有混杂。
- 同为百炼，Plus 相比 Flash 在同图同协议下改善，说明不能只归罪于百炼
  平台。原生 DashScope 也出错，兼容接口不是必要条件。服务端预处理与模型
  本身尚不能分离；统一缩放补偿、加预算、严格 JSON 已没有普适修复证据。
- GPT-5.5 真实 calc-open 的 2/3 是严格任务评分，不是鼠标准确率：失败轮
  通过粘贴显示 56，却没有 validator 要求的表达式；该轮没有坐标点击。
  另外两轮各四次鼠标点击完成任务，其中一轮先观察输入失败再恢复。

证据：[协议对照](../../backend/benchmarks/computer_use/reports/20260919-protocol-models/README.md)、
[同提供方对照](../../backend/benchmarks/computer_use/reports/20260919-grounding-model-comparison)、
[真实闭环](../../backend/benchmarks/computer_use/reports/20260919-gpt55-loop/README.md)。

## 我们已有的问题，哪些确认了

1. **提示职责冲突，已确认；因果收益未测。**
   [runner](../../backend/core/src/tank_backend/agents/runner.py) 的
   `_build_sub_agent_prompt` 给桌面子代理追加完整
   [base.md](../../backend/core/src/tank_backend/prompts/defaults/base.md)，
   包含必须委托 computer_use 的主代理规则，但工具面没有 agent。
   实际 HTTP 中确实同时出现“直接操作”与“必须委托”。应分离共享安全规则
   和主代理调度规则，并校验最终提示与实际可用工具，而非只看模板。
   最小提示的固定图也会错，因此修复它不保证消除全部定位错误。
2. **type_text 隐藏了不同输入语义，已确认。**
   [macOS `_type_macos`](../../backend/core/src/tank_backend/tools/computer_use_macos.py)
   对字母数字发送 keystroke，对标点等使用剪贴板。Calculator 粘贴 `7*8`
   直接计算，粘贴 `7*8=` 却不改变 0，不能等价于按 7、×、8、=。
   这不是“剪贴板一定错误”：它解决了其它应用的 IME 问题；缺陷是工具契约
   没有让代理明确选择文本插入、粘贴和按键，并在应用内验证效果。
3. **crop 的计算责任放在模型，源码确认；具体失败归因未完成。**
   [region_note / crop_and_upscale](../../backend/core/src/tank_backend/tools/computer_use_common.py)
   会裁剪放大，但点击仍用全屏 0–1000，靠文字公式要求模型还原。
   正确 mock 响应的测试只证明公式和执行器正确，不能保证模型执行这段计算。
   探针已有宿主还原实验，不能当作生产已实现。
4. **截图身份与执行结果契约偏弱，源码确认；本批大错的因果未证实。**
   `_screen_point_size` 是模块全局尺寸缓存，有截图前默认值，没有 frame/window
   绑定。当前提示已要求动作后观察、失败时重截图，batch 默认也有末尾截图；
   缺口是执行层没有独立判定“该动作仍适用于这一帧”“应用确实响应”。
   不应描述为完全没有反馈。静态屏幕下仍可能选错窗口、元素或输入方式。
5. **提供方参数接入缺口，已修复。**
   GPT-5.5 路由因 temperature 参数被拒绝，同请求省略即成功；显式 null
   到实际 HTTP 省略已有回归。它是请求失败，不是几百像素偏移的解释。

主屏真实九点与 Calculator 真值点击通过，支持宿主静态坐标转换基本正确；
不支持“测试全绿，所以接口设计和模型理解一定正确”。当前取整差约 1 point，
也不能解释约 400 px 的偏移。

## 外部实现中值得借鉴的机制

### Anthropic：截图坐标与鼠标坐标成对适配

官方示例声明发送图像的宽高，截图缩放和输入逆变换共用 `scale_coordinates`；
模型输出以所见截图为参照，宿主转换到执行空间。示例使用 Linux 的 xdotool，
不是可直接替换 Quartz 的 macOS 驱动。
来源：[computer.py](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-demo/computer_use_demo/tools/computer.py)。

对 Tank 的启发是将裁剪、放大和窗口偏移作为截图元数据保存，让代码逆变换。
参考实现也需要审查边界及回归，不能因来自官方就假定适合本项目所有硬件。

### UI-TARS：坐标协议和模型版本一起适配

其解析器显式区分模型：`qwen25vl` 分支按 `smart_resize` 后宽高解释绝对坐标，
另一分支按 factor 归一化，再由执行转换使用图像宽高。不能把整个系列概括为
统一的 0–1000 协议，更不能直接把旧模型解析公式套到 Qwen3.8。
来源：[action_parser.py](https://github.com/bytedance/UI-TARS/blob/main/codes/ui_tars/action_parser.py)。

对 Tank 的启发是区分“统一内部动作表示”和“所有模型使用同一种外部提示”。
已有 pixel/normalized 对照仍必要；下一步还要核验所选具体模型的官方输入和
输出契约。不能凭一次错点猜倍率。GUI 专用定位模型也可作为候选定位器，
但要与更换负责整段任务的规划模型分开评估。

### Cua / Peekaboo：macOS 元素引用、AX 与精确窗口

Cua 的工具文档提供截图绑定的 `element_token`，索引须配 `snapshot_id`，
新快照替代旧快照后拒绝旧引用；同时支持 AX 元素动作及坐标路径，部分坐标
动作由驱动负责 image-pixel → screen-point。非主屏支持仍受平台约束。
来源：[Cua MCP 工具契约](https://github.com/trycua/cua/blob/main/docs/content/docs/reference/cua-driver/mcp-tools.mdx)。

Peekaboo 的 click 在元素 ID、文字查询和坐标间要求明确选一种，并绑定窗口/
快照；其坐标定义是逻辑坐标，不能和另一驱动的图片像素混用。文档还明确
区分事件派发和应用效果：部分原生事件成功派发后仍报告未验证。
来源：[Peekaboo click](https://peekaboo.sh/commands/click.html)。

对 Tank 最有价值的实验是提供“按钮名称/角色/边界 → 当前帧内元素引用”，
让模型选择目标，宿主计算中心或调用 AXPress。先读取 AX 后用 Quartz 点击，
再单独比较 AXPress，可区分收益来自目标发现还是事件投递。
Calculator oracle 已证明本机能读取该应用的 AX，但没有证明通用代理能选对
元素，也没有验收通用 AXPress。自绘控件、缺失标签及多个同名按钮都要回退。

### OmniParser：先解析界面，再交给规划模型

OmniParser 把截图转为结构化元素，OmniTool 将该解析器与不同模型组合。
官方 OmniTool 示例面向 Windows 11 VM，不能作为 macOS 驱动直接接入。
来源：[Microsoft OmniParser](https://github.com/microsoft/OmniParser)。

Tank 可验证“控件检测/OCR → 候选框编号 → 模型选 ID → 宿主取框内点”的路线。
此前给目标加彩色边框不等于这个实验：前者仍要求模型输出坐标，后者把数值
定位交给独立检测器和代码。检测器漏检、选错编号和框中心不在可点击区域仍
会失败，应分别统计；不能声称加编号必然解决。先复用本机 AX，证据不足时
再承担视觉检测器的部署成本和延迟。

### OpenAI / browser-use：可保留自定义工具，按动作效果闭环

OpenAI 官方支持自定义 UI 函数/MCP，也有结构化 computer 工具和代码执行
路线；computer 调用可以包含有序动作数组，执行后回传截图并检查应用结果。
所以使用自定义工具、或一次调用多个动作，本身不能判定为设计错误。
来源：[OpenAI computer use](https://developers.openai.com/api/docs/guides/tools-computer-use)。

本项目的 OpenRouter Chat Completions 自定义工具测试不等于原生 Responses
computer 接口验收；不能把后者特有参数直接塞进现有端点。可以做适配对照，
但本轮没有验证当前已授权端点是否支持它。

browser-use 的 Actor 提供元素选择、点击、填值和取边界等接口，适合将浏览器
目标解析交给 DOM 路径。它不能直接操作 macOS Calculator。
来源：[browser-use Actor](https://github.com/browser-use/browser-use/blob/main/browser_use/actor/README.md)。

对 Tank 的取舍：固定计算器按钮可以批量点击；打开菜单、切页、出现弹窗等
会改变后续目标的步骤应重新观察。增加脚本执行或 DOM 接口不应混入现有纯
视觉鼠标评分，尤其不能靠读文件/执行算式绕过 GUI 后宣称定位提升。

## 建议的改进顺序与验证方式

### P0：先修复已确认问题，建立公平对照

1. 分离主/子代理提示。测试实际构建的 system、可用工具和 HTTP payload，
   保留共享安全规则；在同模型、同图、同参数下只改变该因素。
2. 明确 `paste_text`、字符输入和 `key_press` 的语义；无需马上扩出大量工具，
   可以先让现有工具明确模式。以 Calculator、TextEdit、含标点及中文输入
   验证真实结果，避免修复计算器却重新引入原 IME 问题。
3. 分开“用户任务完成”与“鼠标定位诊断”评分。保留旧 strict 结果不追改。
   鼠标诊断必须真的点击；接受粘贴的业务评分仍须验证当轮输入与当轮结果，
   不能只看到历史 56 就通过。

这些修复的价值已有问题证据支持，但对定位成功率的提升仍须 A/B。

### P1：把空间计算从模型移到宿主

建议截图返回不可变 observation：frame_id、会话、窗口/显示器身份、实际
image_size、截图对应的屏幕逻辑矩形和裁剪/缩放变换。动作只选一种寻址：
当前 frame 的局部图片点，或该 frame 内的元素引用。

模型原生坐标 → 适配器 → 图片内点 → 截图变换逆映射 → Quartz 逻辑点。
完整整数舍入、轴向倍率及窗口原点由代码完成。旧协议可由显式 adapter 保留，
不根据坐标大小猜单位；没有有效截图、窗口不匹配或几何失效应重观察。

回归应验证 crop/resize/Retina 组合、窗口原点、非整除尺寸、边缘、小控件、
旧 frame 和多会话隔离；实际 HTTP 图像和 frame 对应，最终 OS 落点可追溯。
frame_id 只能防误用引用，不能独自发现同一窗口里的页面变化或模型新鲜错点。
模型收到图片坐标后能否更稳定定位，需要独立 holdout，不能用 mock 证明。

### P2：比较语义辅助和专用定位器

在保留同一个规划模型时依次比较：纯截图、AX 候选 + Quartz、AX 候选 +
AXPress；再决定是否加入视觉检测/OCR/专用定位模型。候选必须从当次观察
得到，不向代理泄漏 benchmark 真值，不能写死 Calculator 的按钮位置。

纯视觉与 AX/DOM 混合两条赛道分别报告。前者测视觉定位，后者测产品能力；
若 AX 路径显著改善，即可量化减少数值定位负担的价值，而非又换一个模型。
同时加入缺失目标、同名按钮、自绘控件、拒绝陈旧引用和 fallback 的验收。

### P3：让失败恢复成为执行契约

保留已存在的截图反馈，在会改变目标布局的动作后增加可观测的状态检查，
未达预期时重新截图/定位，再在预算内切换输入或定位方式。不要把返回
ToolResult 成功当作应用效果成功，也不要用模型自报 confidence 代替证据。
稳定按钮 batch 与逐步观察作独立对照，报告成本与延迟，避免盲目禁用 batch。

## 如何判定改进真的有效

- 两类矩阵分别测：固定接口换模型、固定模型换接口。每次只改变一个因素；
  若同时换模型、提示、截图和 schema，无法归因。
- 先在已获准的合成图上重放历史失败，加未用过的布局、字体、目标尺寸、
  窗口位置和多个标签；按布局分组报告，避免重复图片虚增样本量。
- 真实阶段扩到其它应用；记录格式合法、选对元素、框内命中、事件落点、
  应用效果、恢复次数、耗时和 token，明确每项分母。盲点允许报告未知。
- 驱动使用独立已知目标验证落点；定位器在不执行动作的固定图上评分；完整
  代理由独立 validator 判定任务。三层通过才能缩小未确定原因的范围。
- 本轮未执行以上新实验，也未证明其它项目在本机更可靠。后续真实截图测试
  需沿用各次授权范围，不能将上轮 GPT-5.5 清理桌面的单次授权当成通用许可。

候选工作登记在 [backlog](../backlog.md)；调研检查见
[完成计划](../plans/done/computer-use-implementation-research.md)。
