# Computer use：macOS 坐标链与验证结论

更新：2026-09-19。本文汇总自研 `computer_use` 与共享 `MacOSDesktopExecutor`
的现行行为及验证边界；官方 N2 SDK 是另一条路径，不能直接套用结论。
逐轮原始证据、历史测试数量和异常记录见
[macOS 调研](../research/macos-coordinate-chain.md)，复现入口见
[benchmark 文档](../../backend/benchmarks/README.md)。

## 当前结论

静态主屏的本地尺寸转换已经过 pytest、真实九点校准和 Calculator 真值点击
验证。仍出现的大偏移已在固定合成图的模型原始响应中复现，发生在鼠标执行前。
因此不能用一个全局 Retina/缩放补偿系数解决，也不能将所有失败归为 macOS
输入投递问题。最直接的瓶颈是模型在当前定位任务与输出协议上的可靠性。

这只定位到服务输出边界，不能进一步断言是提供方平台故障、模型权重、视觉
识别、空间表达或内部预处理中的某一个原因。同一提供方换模型会改善表现；
原生 API 也可复现偏移；合法 JSON、严格 schema 和充足预算均不保证点中目标。
GPT-5.5 在独立合成布局上最好；本次真实 calc-open 严格评分 2/3，已验证
鼠标批量点击与一次截图反馈后的恢复，但不是全套 GUI 可靠率结论。

模型差异不排除宿主设计缺陷：提示职责冲突、输入方式语义及 crop 要求模型
自行还原坐标仍需处理。[外部实现对照](../research/computer-use-implementation-comparison.md)
梳理了 Anthropic、UI-TARS、Cua、Peekaboo、OmniParser、OpenAI 和 browser-use，
建议先修已确认问题，再分别测试宿主坐标还原、AX 元素寻址和反馈检查。
这些是待验证方案，尚未改变生产接口；统一协议成绩不代表各模型最佳适配表现。

## 截图到点击：实际转换

1. Quartz 读取主屏逻辑尺寸和 backing pixels；`screencapture -m` 仅截主屏。
   已校准环境为 1920×1080 points、3840×2160 pixels。
2. Retina 图片通过 `sips --resampleWidth` 缩到逻辑宽度。Pillow 检查实际宽高
   与逻辑尺寸均一致；缩放失败或命令成功但尺寸错误都返回错误。
3. 完整 PNG 尺寸更新截图缓存。点击使用该全屏尺寸；未截图时仍有 1920×1080
   默认值，缓存不会自动绑定显示器身份或追踪随后的几何变化。
4. 可选 `region=[left,top,right,bottom]` 使用全屏 0–1000：转换为像素裁剪，
   最多放大 3 倍；全屏缓存保持不变。例：右下半屏裁为 960×540，再放大
   2 倍成 1920×1080。生产路径由模型按工具提示恢复全屏归一化坐标：
   `full_x = left + local_x * (right-left)/1000`，y 同理；宿主不自动恢复。
5. PNG → Base64 data URL → `ImageBlock(detail=auto)` → 工具结果序列化
   → 后续 user 消息的 `image_url` → OpenAI SDK HTTP JSON。本地此后没有
   再次缩图。tool 文本占位和前端显示尺寸不是模型图片输入。
6. SDK 累积 SSE 工具参数，ToolManager 解析并分派。生产支持 x/y、数字字符串、
   bbox 数组中心；macOS 拒绝非有限数、越界及非法结构，不再把越界值静默夹紧。
   数字合法无法区分模型想表达的是 pixels 还是 normalized。
7. ClickTool 逐轴计算 `min(W-1, int(nx*W/1000))`；executor 使用
   `round(nx*(W-1)/1000)`。终点在屏幕内，两条路径的内部取整可相差约 1 point。
8. points 直接进入 Quartz mouse down/up 和 `CGEventPost`，不再乘 Retina
   倍率。成功投递不等于命中控件或完成业务，必须再观察实际结果。

源代码：[macOS 工具](../../backend/core/src/tank_backend/tools/computer_use_macos.py)、
[共用转换](../../backend/core/src/tank_backend/tools/computer_use_common.py)、
[executor](../../backend/core/src/tank_backend/computer/executor.py)、
[LLM 消息链](../../backend/core/src/tank_backend/llm/llm.py)。

## 已修复与测试覆盖

- 主屏截取、Retina 缩放失败处理、缩放后宽高检查、边界点不超屏，以及非法
  坐标拒绝已有回归；鼠标位置读取使用正确的 `CGEventGetLocation`。
- 真实 Pillow / Base64 / 工具 / 序列化链配合 mock OS：覆盖 1x/1.5x/2x、
  非正方形和非整千尺寸；核对目标像素与最终 Quartz 参数。
- crop、2x/3x 放大、小区域倍率限制、全屏缓存保持、局部到全屏映射均有测试。
  正确 mock 模型输出只能验证宿主链，不能证明真实模型能自行恢复 crop 坐标。
- 实际 AsyncOpenAI + HTTP MockTransport 验证上传字节、尺寸、图片顺序、
  user/tool 消息，按字符碎片回放 SSE，再经 ToolManager 到 ClickTool；包含
  全图和 crop。batch 返回的图像也进入模型消息和 benchmark 归档。
- 真实服务端畸形 SSE 成为 fixture：SDK 与本地累积结果相同，非法 JSON
  被工具层拒绝且不注入事件；真实模型坐标回放验证本地落点，不把错点修正成真值。
- 新探针覆盖独立 point/pixel/bbox、严格整数/范围/重复字段/边框顺序、缺失
  目标、host bbox 中心/crop 还原、圆角按钮 mask 评分、CLI 到 HTTP 的思考与
  预算参数、length 用量保留。新协议仍属探针，未替换生产 click schema。

入口：[macOS 测试](../../backend/core/tests/test_computer_use_macos.py)、
[探针测试](../../backend/core/tests/test_grounding_probe.py)、
[测试指南](../../backend/TESTING.md)。这些覆盖已识别的静态主屏转换，不能表述为
“所有硬件、动态状态和模型输出均正确”。sips 的 mock 由真实机器校准补充。

## 真实输入校准

[九点校准脚本](../../backend/scripts/calibrate_macos_coordinates.py) 在自己的
AppKit 窗口内核对截图红色目标，再发点击，独立记录 down/up、窗口坐标和
光标回读。最终主屏九点每轴最大误差 1 point、距离约 1.42 points；两轮
1 秒间隔通过，恢复 0.1 秒额外间隔后也通过。它每次仍截图，不是无截图连点压测。

首次存在未收到事件、一次回读与事件不一致；Calculator oracle 首次还有一次
未保存坐标的光标断言异常。证据不足以归因，后续通过不能抹去这些观察。
随后 [Calculator oracle](../../backend/benchmarks/computer_use/reports/20260919-calculator-oracle/results.json)
三次通过真实 ScreenshotTool/ClickTool 完成 7×8=56，12 次光标误差 ≤1 point。
按钮真值来自本地 AX，故它验证执行链，不验证模型识别和闭环决策。

## 模型、协议与提供方实验

以下各轮任务、布局及评分不同，不能合并成单一准确率。

- 最初 16 次固定合成图：稀疏界面 4/4 命中，密集计算器 12 次仅 2 次命中；
  另有合法错点、畸形 bbox 和未声明工具。裁剪或统一缩图未稳定解决问题。
- 32 次坐标空间基线加 16 次 point-only 对照：同图输出在归一化/像素等
  解释间变化，简化 schema 后格式改善但仍有 >50 px 偏移。1000×1000 控制
  图上仍错，因此不是统一乘错某个倍率。
- [100 次请求消融](../../backend/benchmarks/computer_use/reports/20260919-grounding-ablation)：
  代理/最小提示、尺寸公式、thinking、高分辨率、普通 JSON 均未稳定修复。
  原始 SSE 4/4 与本地参数一致且非法，非流式 8 次也非法，排除本批错误由
  本地 SSE 拼接或仅流式接口导致。旧原生 bbox_2d 文本任务 hard 8/8 在
  15 px 内，holdout 4/8，最大约 41 px；收益不能泛化到所有 bbox 工具协议。
- [80 次同提供方换模型](../../backend/benchmarks/computer_use/reports/20260919-grounding-model-comparison)：
  point-only Flash 5/16、Plus 15/16、VL Plus 7/16 中心误差 ≤15 px；生产
  click schema 下 Flash 3/16、Plus 15/16。Plus 仍有大错；此处 15 px 精度
  阈值不是按钮命中率，不能直接宣称真实 calc-open 修复。
- [304 次跨模型/协议隔离](../../backend/benchmarks/computer_use/reports/20260919-protocol-models/README.md)：
  同一独立 16 布局各重复两次，GPT-5.5 32/32 命中，最大误差 2.08 px；
  GPT-5.4 Mini 30/32，最大 38.83 px；Qwen3.8 Flash 25/32，最大 417.91 px。
  全部格式有效。GPT 经 OpenRouter 限定 OpenAI、禁 fallback，响应 provider
  已核实。这仍是合成静态定位，不是完整代理运行。
- nullable type-array/anyOf 在四个 Qwen 预检中都产生字符串坐标，strict
  也未阻止；单一 integer schema 修复该格式适配，未解决定位。found=false
  的 0/null 两种协议分别严格验证。schema 不能证明坐标对应目标按钮。
- 标记、打乱布局、裁剪、缩放、旧图片历史、agent 提示和完整工具定义已做
  小样本隔离，未找到普适修复。当前 Flash 在最小提示已错，工具数量不是
  必要条件；一张历史图实验也不等于长会话/compaction 验证。
- 原生 DashScope 同样出现大错：当前 Flash 1/4 命中、最大约 282 px；
  Qwen3.8 Flash 2/4、最大约 533 px。兼容层不是必要条件，四次随机调用也
  不足以判断哪种 API 更可靠。
- Qwen usage 与近原尺寸 patch 对齐相符，不支持“必定缩到 1280 宽”，但
  不能由 token 数唯一反推内部尺寸。GPT-5.5 low-detail 首次约 407 px 大错，
  追加 auto/low 各六次都命中，未复现确定性缩放故障。上传 hash 相同只证明
  上传字节相同，不能证明服务端预处理相同。

## DeepSeek 预算专项

[112 次复测](../../backend/benchmarks/computer_use/reports/20260919-deepseek-budget/README.md)
确认旧 4000 是探针硬编码，不是服务上限；现可用 `--max-tokens` 和
`--thinking on|off` 覆盖。生产 default/planning DeepSeek 为 10000/20000，
computer_use Qwen 为 40000，均未因实验修改。

配对筛选每组 12 次：on/4000 两次纯推理截断，on/16000 无截断但同为 3/12
命中；off/4000、off/16000 均正常输出，分别 3/12、5/12 命中。独立布局
off/4000 为 20/32 命中，on/16000 为 23/32；后者仍一次 16000 全用于推理，
没有点击。关闭思考的平均输出从 736 降至 104 token，减少约 86%，仍有约
339 px 大错。全部 56 次 off 响应无推理输出。

截断与错误坐标是不同失败类型；提高预算不能保证完成，关闭思考节省输出
token 也不保证定位。off 与 on 的有效采样不同，不能用小分差证明预算收益。

## 仍未确定或未验收

- 多显示器、非主屏、跨屏、旋转、截图后切主屏/分辨率；全局尺寸缓存及多
  会话覆盖风险仍在。当前静态实验不依赖这些因素，所以它们不是已复现大错
  的必要条件，但也没有被所有场景排除。
- 窗口移动、动画、抢焦点、并发鼠标，以及无截图高频 batch 连点。旧坐标
  可失效；batch 通常仅在末尾截图。静态校准中的早期异常原因仍未知。
- 模型权重与服务端预处理、OCR 与空间表达仍无法独立归因；未采用猜测倍率
  进行运行时补偿。跨部署同权重控制及更多按钮尺寸需要另行实验。
- 全套跨应用任务、长历史/compaction、生产可靠率与官方 N2 SDK 的独立验收。
  16 个布局重复两次不等于 32 个独立布局；不能从合成 32/32 推断零错点。

## 完整闭环的判定

现有 benchmark 直连 AgentRunner，覆盖生产提示、LLM 多轮消息、截图、真实
动作、反馈与独立 validator；不覆盖 Supervisor 调度、持久化、审批 UI 或语音。
macOS `calc-open` 使用 `trial-token-gui-calc-v4`：每轮重置为 0，结束时要求
前台未最小化 Calculator 的 AX 表达式为 7×8、结果为 56，拒绝 shell/file
绕路。Linux 仅检查进程，仍属 smoke。截图存在和像素内容当前不是评分条件，
因此本次闭环应额外检查最后截图及调用轨迹；键盘成功与鼠标定位成功分开报告。

### GPT-5.5 真实闭环结果

[三次原始评分与脱敏证据](../../backend/benchmarks/computer_use/reports/20260919-gpt55-loop/README.md)
采用生产 AgentRunner、原 computer_use 定义和工具；仅独立配置切到
OpenRouter → OpenAI GPT-5.5，reasoning=low、输出预算 16000、temperature
省略。全部 13 次实际响应的 model/provider 已核实；七张真实截图的 HTTP
hash 均与各自 trial 归档一致，各轮最后截图确实进入后续模型请求。
用户明确允许清理后的主屏截图外发，其他应用被隐藏/遮挡；原始截图仅存
本机 `/tmp/tank-gpt55-loop/`，不进入仓库。测试后恢复隐藏应用。

- 第一轮四次鼠标点击 7、×、8、=，截图与 AX 均显示 7×8=56，通过。
- 第二轮 `type_text("7*8")` 再 Enter，截图显示 56 但无表达式，严格评分失败。
- 第三轮粘贴 `7*8=` 后仍为 0，模型观察新截图后改用四次鼠标点击，成功。

最终严格评分 **2/3**，三次末尾画面都显示 56。未超时、未使用 shell/file，
共 72140 token；完整任务耗时分别 28.93/27.76/58.82 秒。两段鼠标序列验证了
应用结果，不等于八次分别记录事件/按钮边界的校准；仍不改变历史九点证据。
Calculator 重启后位置在 trial 之间变化，新截图后模型适配了位置；未测试
截图后几何突变、非主屏或跨屏。旧 driver 的 cleanup=unknown 原样保留。

本轮还确认三个与统一坐标倍率无关的问题：

1. **生产 LLM 参数接入缺口，已修复。** 合成图预检时，强制携带 temperature
   被 OpenRouter require_parameters 路由拒绝；同请求只去掉该键即成功。
   profile 新增显式 `temperature: null`，两条请求路径均省略该参数；没有
   设置此键时仍用旧默认值。流式/非流式、0.0 覆盖到实际 HTTP 的回归通过。
2. **输入路径与评分约定不一致，未改评分。** 本地独立重置后复现：粘贴
   `7*8` 直接得到 56 而无表达式，粘贴 `7*8=` 不改变 0。生产含标点的
   type_text 走剪贴板，不能等同逐键/逐按钮输入。第二轮满足“显示 56”，
   但不满足额外的表达式校验；保留失败，不归类为错点。
3. **子代理继承主代理委托指令，未修复。** 实际 HTTP system 同时有桌面
   专家指令与“ALWAYS delegate to the computer_use agent immediately”；
   [runner](../../backend/core/src/tank_backend/agents/runner.py) 追加的
   [base.md](../../backend/core/src/tank_backend/prompts/defaults/base.md) 含该规则，
   而工具集中没有 agent。模型明确指出冲突；其定位影响尚无单因素对照。

本次完整后端 **4484 passed/1 skipped**，E2E **14 场景/55 步**，其余要求
检查通过。[验收计划](../plans/done/gpt55-computer-use-loop.md) 已完成；
全套跨应用、长历史及上述剩余问题见 [backlog](../backlog.md)。
