# Computer use：macOS 坐标链与验证结论

更新：2026-09-20。本文汇总自研 `computer_use` 与共享 `MacOSDesktopExecutor`
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

模型差异不排除宿主设计缺陷：M1 已修复提示职责冲突与输入语义；M2
新增显式 image/frame 接口由宿主还原 crop，默认 legacy 路径仍由模型换算。[外部实现对照](../research/computer-use-implementation-comparison.md)
梳理了 Anthropic、UI-TARS、Cua、Peekaboo、OmniParser、OpenAI 和 browser-use，
建议先修已确认问题，再分别测试宿主坐标还原、AX 元素寻址和反馈检查。
模型适配、AX 与定位拆分仍待验证；统一协议成绩不代表各模型最佳适配表现。
后续统一按[适配与定位执行计划](../plans/active/computer-use-adaptation-and-grounding.md)
推进，含历史完成核对、模型适配、规划定位分离四组对照及分阶段验收。

## 截图到点击：默认 legacy 转换

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

## 显式 image/frame 接口（M2）

macOS 工具组提供兼容默认 legacy 的可选 `coordinate_space="image"`。截图
返回不可变 Observation：会话/frame、主屏/窗口身份、实际图片尺寸、整数裁剪
矩形、显示几何及 PNG hash。`region` 为所选屏幕或窗口内的 0–1000 裁剪范围；
可选 `window_id` 必须是完整位于主屏的可见 Quartz 窗口。截图不含光标。

点击、框中心、移动、定位滚动与拖拽使用同一 `frame_id` 和图片内零起点像素
坐标；允许有限小数，拒绝字符串、布尔值、越界和倒置框。框中心先计算，再按
实际 `crop` 与 `image_size` 逐轴还原；最终在 Quartz 边界四舍五入（half up），
末端限制为裁剪区域最后一个有效源像素。Retina 不重复相乘；不使用全局默认尺寸。

ToolManager 注入会话身份。缺失/旧/跨会话 frame、窗口不匹配或几何失效时
零输入并要求重观察。每次坐标动作前重新无光标截屏，比对实际观察区域的
像素与显示/窗口几何；batch 共享 frame，逐步检查，首错即停并返回新截图。
键盘、文本和不带坐标的滚动不引入虚构参考系。

这是保守检查：动画、闪烁等可能造成拒绝，每步增加一次本地捕获成本，也无法
排除检查到投递之间的变化。多屏支持、模型效果、跨应用和完整停止验收不在
本次通过结论内。旧 normalized 调用及独立 DesktopExecutor 保持旧语义。

[M2 报告](../../backend/benchmarks/computer_use/reports/20260920-m2-observation/README.md)
保留初次全屏场景变化拒绝及窗口九点 9/9、每轴 0 point 的实机证据。
[Observation](../../backend/core/src/tank_backend/tools/computer_observation.py) 与
[frame 工具适配](../../backend/core/src/tank_backend/tools/computer_frame.py)
由实际 SDK HTTP/ToolManager/Quartz 回归覆盖；未进行本批模型截图请求。

## 共用定位适配器（M3 实现，尚未启用 locate）

[GroundingAdapter](../../backend/core/src/tank_backend/tools/computer_grounding.py)
位于 computer-use 工具层，按显式协议构建图片、提示、schema 并解析响应。
它与 probe 共用代码，不按型号建立继承树，也不根据坐标数值猜测单位。
模型、端点、temperature、输出预算及 thinking/provider 参数继续由已有
`LLMProfile` 提供；没有新增默认 profile 或修改当前模型。

- `point` 为 0–1000 点，`pixels` 为图片内整数点，`bbox` 为 0–1000 框；
  统一返回不可变 `ImageLocation`。点为图片内像素；框保留图片内边界，最大
  边界可等于图片宽/高，执行取单独提供的中心点。旧端点 1000 的点仍映射到
  最后一个有效像素。裁剪还原与 Quartz 取整继续由 M2 Observation 完成。
- 兼容旧 `found` schema（默认）：`false` 同时表示缺失或不确定，所以内部
  保守记为 `ambiguous`，不能宣称已证明目标不存在。显式 `status_field=True`
  使用 `found/not_found/ambiguous`，非 found 结果没有点/框。nullable/整数
  哨兵规则与旧探针一致；模型可用性和 strict 效果仍需独立实验。
- `request(llm, observation, png, target)` 先核验 PNG hash、格式和实际尺寸，
  再调用通用 `LLM.complete_response()`，只上传当前图与目标，不发送聊天历史。
  `build_request()` 的 previous/marked 等选项只保留给离线 probe 对照；
  `request()` 不开放这些历史/标记参数。API 仅返回位置声明，不执行 `click`。
- LLM 层新增的完整响应接口保留工具参数、结束原因、实际模型与 usage，
  不理解坐标。适配器关闭 SDK/封装层重试，取消直接传播。调用者先持有完整
  响应、记录用量，再 `parse_response()`；解析失败不会丢掉原响应及费用证据。
- 完整响应解析拒绝 length、content_filter、refusal、多 choice、缺失/多工具、
  错工具及非法坐标。数组、字符串、重复字段、越界、倒置框不自动修补。
  矩阵 probe 已使用同一检查，完整 JSON 也不能覆盖 length 失败。

本步是可调用的生产协议/LLM 接口；AgentRunner 尚未注册定位工具，默认一体
模式与桌面动作保持原路径。M4 才把返回值绑定当前任务/frame，并接入共享
预算、截止时间、重新观察、审批和动作派发。适配器的图片一致性检查不代表
屏幕仍然新鲜，不能替代 M2 执行前校验；调用者也不得自行相信模型 frame_id。

十份 M3 真实响应通过实际 SDK 的本地 HTTP 回放，与历史请求逐字段、图片 hash
一致；三份数组响应仍拒绝，合法错点仍是错点。没有新增付费调用、真实截图
外发或 holdout 结果，也未验证 strict/native bbox 模型效果。

M3 随后用同一生产调用路径完成六次 strict 配对预检：Qwen3.8 Flash 即使
strict=true 仍返回数组；Max 两次命中与历史失败并存；DeepSeek 只有一对
control 失败/strict 命中，不能认定收益。见
[strict 报告](../../backend/benchmarks/computer_use/reports/20260920-m3-strict/README.md)。
16 次预检额度用完；独立调参筛选首批 40 次已完成。
[点/框对照](../../backend/benchmarks/computer_use/reports/20260920-m3-screening-protocol/README.md)
使用四个开发布局：Max bbox 与 GPT 两协议均 4/4 命中，Flash 仍有数组，
DeepSeek bbox 仅 1/4。合法率与命中率分别记录；四布局不能作为采用结论，
自定义函数 bbox 不代表原生接口验收。生产默认与适配器未因此改变。
后续 [thinking 批](../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking/README.md)
在第七次 DeepSeek 请求遇到 402 余额不足后停止，只完成一个布局的三对 Qwen；
Flash on 命中而另两组 on 失误，不能作通用收益结论。缺失用量保持 unknown，
[余额恢复后续跑](../../backend/benchmarks/computer_use/reports/20260920-m3-screening-thinking-resume/README.md)
已补齐 32 个设置，保留旧 402 并为其未知用量预留完整估算额度。四布局 off/on
命中为：Qwen3.7 3/4、0/4；Flash 0/4、4/4；Max 4/4、3/4；DeepSeek
完成响应 2/4、3/4（含旧 402 时 off 为 2/5）。Flash on 是后续候选，
未因此切换生产配置；真实后端日志已重新通过。
[图像处理对照](../../backend/benchmarks/computer_use/reports/20260921-m3-screening-image/README.md)
在相同 2 倍放大合成图上分别比较 Qwen 高分辨率开关和 DeepSeek auto/low：
32 次格式均合法但仅 24 次命中，未观察到普遍收益。Qwen 图像 token 增加，
DeepSeek low 的总用量反而增加；保留默认设置，不猜测服务端坐标补偿。

[显式 status 筛选](../../backend/benchmarks/computer_use/reports/20260921-m3-screening-status/README.md)
在三个新开发布局的存在/缺失/同名歧义图片上完成 36 次调用；格式全部合法，
但 24 个负例中 5 次仍给出 found 坐标（Qwen3.7 三次、Flash/Max 各一次）。
正例命中 8/12；DeepSeek 六个负例未误报，但不能据此宣称可靠拒绝率。
显式状态提供可表达的结果类别，不验证视觉真值；生产默认及执行保护未改变。

[holdout 冻结](../../backend/benchmarks/computer_use/reports/20260921-m3-holdout-freeze/README.md)
保留 Qwen3.7 point 基线、Max bbox 与 GPT point，使用已实测旧 found schema
和 8000 输出上限。64 布局各重复两次的 384 份请求已离线核对；尚无模型
holdout 成绩。缺失与同名拒绝按真值分层，旧 false 不区分二者的语义状态。

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
  预算参数、length 用量保留。协议构建/解析现已与 M3 适配器共用，未替换默认生产 click schema。

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
  会话覆盖风险在 legacy 路径仍在；image 接口已有身份/几何失效拒绝，未实现
  多屏执行。当前静态实验不依赖这些因素，所以它们不是已复现大错
  的必要条件，但也没有被所有场景排除。
- 窗口移动、动画、抢焦点、并发鼠标，以及无截图高频 batch 连点。旧坐标
  可失效；legacy batch 通常仅在末尾截图，image batch 每步检查观察区域。
  静态校准中的早期异常原因仍未知。
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
3. **子代理继承主代理委托指令，已修复提示构建；效果未重测。** 历史 HTTP system 同时有桌面
   专家指令与“ALWAYS delegate to the computer_use agent immediately”；
   [runner](../../backend/core/src/tank_backend/agents/runner.py) 追加的
   [base.md](../../backend/core/src/tank_backend/prompts/defaults/base.md) 当时含该规则，
   而工具集中没有 agent。模型明确指出冲突；其定位影响尚无单因素对照。

本次完整后端 **4484 passed/1 skipped**，E2E **14 场景/55 步**，其余要求
检查通过。[验收计划](../plans/done/gpt55-computer-use-loop.md) 已完成；
全套跨应用、长历史及上述剩余问题已纳入
[后续执行计划](../plans/active/computer-use-adaptation-and-grounding.md)；
多屏/压力等条件性范围仍见 [backlog](../backlog.md)。

### 提示职责隔离（2026-09-19）

共享 `base.md` 只保留安全规则、沙箱说明和环境信息；主代理的桌面委托规则
由 PromptAssembler 单独加载 `orchestration.md`。AgentRunner 构建子代理
提示时不加载该主代理规则。`ask_user` 说明依据最终可用工具集注入，受注册、
allowlist、命名 toolset、disallowed 共同约束；不可用时结束并报告所缺信息。

[离线请求快照](../../backend/benchmarks/computer_use/reports/20260919-adaptation-m0/README.md)
通过真实 SDK HTTP 边界验证只有 system 改变；主代理委托和共享安全规则均有
回归。[M1 首步 A/B](../../backend/benchmarks/computer_use/reports/20260920-m1-acceptance/README.md)
在三个合成布局各重复两次，旧/新提示均 0/6 命中，未观察到定位收益；
不据此更改历史分数。完整真实任务效果仍待后续对照。

### 文本输入与 Calculator 证据（M1）

macOS `type_text(text, mode="auto")` 在当前输入源支持 ASCII 时，ASCII 字母、
数字和空格走 AppleScript keystroke；非 ASCII 输入源或其能力未知时走剪贴板，
避免字母被 IME 改写。标点、换行和非 ASCII 文本始终走剪贴板。不切换用户
输入法。`mode="paste"` 显式强制
粘贴，允许用于纯数字；未知模式在操作系统调用前拒绝。工具说明告知剪贴板
会被替换，以及 Calculator 对粘贴表达式的特殊语义。Enter/快捷键仍通过
`key_press`，其中带 Shift 的映射键使用物理 key code，避免 `shift+8` 被
AppleScript keystroke 当成 `8`。工具报告实际输入路径，只确认已派发，
不声称应用接受或任务完成。M1 主屏实测覆盖 TextEdit 六项和 Calculator 八项。

`trial-token-gui-calc-v4` 的严格总分维持原表达式口径。新增
`calc-evidence-v1` assessment 独立写入每轮 result.json 和报告 outcomes：

- `strict_expression`：前台 Calculator 的 AX 表达式为 7×8、结果为 56。
- `business`：本轮已验证清零且有完整成功输入轨迹，再根据表达式/结果判断。
  允许完整插入 `7*8` 或 `7×8` 后得到 56；直接插入答案 56 不通过。
  中途失败、未完成动作、未知工具或缺少当轮证据时记 null，不冒充通过。
- `mouse_only`：在业务证据完整且严格结果成立时，计算输入全部为鼠标点击
  并至少四次才通过；按键/文本不计为鼠标定位成功。此指标不证明各点击的
  几何精度，逐按钮命中仍需 oracle/独立边界诊断。
- `pixels` 当前为 unknown，保留人工核验；AX 和图片 hash 都不是像素评分。
  M1 受控截图另有本地 OCR 与独立助手视觉复核；OCR 对部分孤立数字误识别，
  未将其推广为通用自动评分，也不将助手复核称为人工签字验收。
  `last_screenshot` 记录 hash、捕获时间及最近一次实际 SDK HTTP 序列化时间；
  后者仅证明图片进入请求，不证明远端模型已读取或截图仍代表最新界面。

内置 benchmark driver 在实际 SDK HTTP 边界记录图片 hash，不记录鉴权头或
图片内容；真实截图仍只保存在本轮本地目录。插件传输不套用此内置 hook，
没有匹配证据时不会伪报截图回流。GUI-only 违规使业务/鼠标轨道也失败。
旧报告不重评分，不把新增业务轨道加入原 strict 分母。
