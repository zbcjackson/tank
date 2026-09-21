# M3 holdout 候选与请求冻结

2026-09-21。三组候选及 384 次请求计划已冻结，离线 SDK 验收完成。
本批零模型请求、零 token、零费用；**尚无 holdout 模型成绩**，不关闭 M3。

## 冻结候选及选择依据

最多三组的既定上限包含基线，不能另加第四组。选择只使用开发批证据：

- Qwen3.7 Flash `qwen3.7-flash-2026-07-15`：point，thinking off，温度 0.1。
  保留现有模型作静态定位基线；它使用共用 adapter，不等同生产一体 agent
  的完整任务基线，后续 A/B/C/D 闭环仍须独立进行。
- Qwen3.8 Max `qwen3.8-max-2026-09-02`：bbox，thinking off，温度 0.1。
  开发点/框批 bbox 4/4，选择该已实际测试组合。这里是自定义函数框，
  **不是原生 computer/bbox 接口**；后续 point 的图像/status 结果不冒充 bbox 成绩。
- GPT-5.5 `openai/gpt-5.5`：point，reasoning effort=none，不传 temperature。
  开发点/框均 4/4，选更简单的 point，并保留计划要求的 GPT 对照。
  OpenRouter 固定 only=openai、allow_fallbacks=false、require_parameters=true。
  响应实际 model/provider 必须逐次记录，不能由路由配置推断实际身份。

三组统一 max_tokens=8000、旧 found 布尔 schema、integer、strict=false、
detail=auto；Qwen 不传高分辨率参数。SDK 请求除图片/目标/尺寸外，与
[开发点/框批](../20260920-m3-screening-protocol/README.md)的已发送请求相同。
不是根据 holdout 成绩挑选协议、补偿坐标或改变预算。

Qwen3.8 Flash thinking on 仍有坐标错误和歧义误报；DeepSeek 仍有错点且
bbox 开发结果弱，因此本轮三席优先保留基线、Max 和 GPT。未入选不意味着
普遍能力排序。显式 status 没有新旧 schema 配对收益证据，且 24 个负例中
5 次仍误报坐标，暂不采用。strict/high-resolution/detail-low 未见可靠收益，
不扩大变体。筛选余 3 次保留不用；未测试的 native、其他部署与 UI-TARS
继续记为未知，不将通用函数 schema 的成功写成原生协议支持。

## 请求、数据和计分冻结

复用 M0 已冻结的 64 张合成图：48 个正例、8 个缺失、8 个同名歧义；每组
每布局 2 次，共 384 次，统计独立样本仍为 64 个布局。只有一个字体家族、
有限遮挡和 keypad 场景，不能外推跨应用能力。生成过程只读 inputs.json
中的图片/尺寸/语义目标；没有打开评分 truth，也未视觉查看 holdout 图片。

[manifest](manifest.json) 锁定 profile/adapter、源文件与输入 hash、请求和
顺序 hash；[requests](requests.json) 保存 192 份不同的实际 SDK body，图片
以 SHA-256 引用 M0 PNG；[schedule](schedule.json) 展开 384 次顺序和重复。
请求顺序按重复轮、输入顺序、轮换候选排列，不是并发延迟测试。

沿用 M0/M8 门槛：正例 mask 命中率 ≥95%、中心误差 p95 ≤15 px、无 >50 px
大偏移；无目标不允许可执行点。负例仅当合法解析为无点时算拒绝，非法/超时
不算正确拒绝。旧 found=false 内部保守为 ambiguous，缺失/重复拒绝率按
独立真值分层报告，**不能评价两种语义状态的精确分类正确率**。

实际 mask 计分使用最近整数像素（floor(value+0.5)），中心误差单列；p95
用 nearest-rank，对有合法点的正例计算，同时报告无点/非法失败数。缺失点
不能从命中率分母排除。按布局聚类 bootstrap（seed=20260921，10000 次）
估计候选与基线的配对区间，两次重复一起采样；只有完整同尺执行才作完整
通过判断。所有失败保留，未发请求标 pending；不把部分批次当完整验收。

本轮只冻结计分规则，尚未新增付费执行器或 mask 评分实现。下一步先用独立
夹具测试执行/计分，再发送冻结请求；请求侧与评分真值侧保持分离，批次结束
或预算停止后才评分，不用 holdout 调参。后续确需变更另开批次、保留原记录。

## 预算和执行条件

本轮零付费。筛选台账不变：141/144 次、406311 已知 tokens，旧 402 另留
26000 tokens，余 3 次。holdout 独立上限 384 次 / 3000000 tokens；每请求
实际冻结输出上限 8000（低于 M0 的 16000 规划上限），输入保守估计 10000。
发出前检查已知用量 + 未知请求预留 + 下一请求 18000 ≤3000000。输入超估、
usage 缺失、API 错误、超时或阶段上限停止并保存；零自动重试，失败也占请求。
90 秒/请求、HTTP 85 秒，最多 34560 模型秒。预算不保证一定能发完 384 次。

首次付费前必须：复核源码/图片/请求 hash，核实当时路由价格并记录费用估算，
完成冻结输入驱动和独立评分测试。未来实付仍 unknown，不沿用旧价格冒充现价。
授权仍限现有端点的合成图，没有真实截图或桌面动作。

## Tests 与验证

[离线检查](offline-check.json) 通过生产 GroundingAdapter → LLM → SDK 的
384 次 MockTransport 调用，核对每张图片字节和尺寸、每组实际参数/schema
与开发请求一致、两次重复完全相同。fake 始终拒绝定位，仅验证解析通路，
不计模型命中分。进程 audit hook 拒绝网络与 truth 文件读取。
`freeze.txt` 是此次离线执行记录，不是新增生产接口。

[verification](verification.json) 记录完整仓库检查；无 Python 源码/测试
变更，changed-file pyright 为 N/A。生产默认与 AgentRunner 注册均未改变。
