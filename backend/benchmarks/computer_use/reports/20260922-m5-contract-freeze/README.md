# M5 离线请求契约冻结

2026-09-22。仅离线软件证据；真实模型请求、截图外发及桌面输入均为 0。
M5 效果对照尚未执行，旧 544 次静态额度不重置，默认配置不变。

## 冻结内容与复现

- `profiles.json`：原始生产 profile 的公开字段；所有实验组共同采用
  Qwen3.7 Flash dated model、temperature=0.1、thinking=false、max_tokens=8000、
  stream_options=true。原始 profile 的 40000、usage 关闭和未指定 thinking
  单独保留，不能拿历史分数直接相减。HTTP-Referer/X-Title 原样保留；无密钥。
- `definitions.json`：原始 prompt、约束和八个定义（original 仅归档，实验七组）。
  A 无 grounding；A-control=integrated/legacy/false；B-host-only=legacy/true；
  B-protocol-only=point/false；B-combined=point/true；C=split/point；
  D=split/bbox、独立 Qwen3.8 Max 2026-09-02 profile。共同 nullable=integer、
  strict=false、detail=auto、status_field=false，与 M3 对应候选一致。
  D 仍是未通过完整采用门槛的候选，不代表推荐切换默认模型。
- `toolset.json`：实际生产 computer_use allowlist。新框架移除 mouse_down/up，
  C/D 追加 locate；实际 schema 差异保留在请求中。
- `requests.json`：真实 Runner → LLM → OpenAI SDK 序列化后的 URL、公开 headers
  和完整 JSON body，包括 system prompt、工具 schema 和内嵌图像。original/A/B
  各 2 个模拟请求；C/D 各 4 个（截图前、截图后、locator、定位反馈后）。
  共 20 个本地 MockTransport 请求，无网络。locator 返回 scripted abstention，
  不执行 click；该假响应不能说明模型会拒绝。未来闭环的请求序列仍需逐次归档。
- `synthetic.png`：100×80 纯蓝合成图；区域 [100,100,800,800] 经过真实截图
  crop/upscale 实现。它没有新布局评分价值，不是 holdout。
- `manifest.json`：产物/源码 SHA-256、SDK/Python 版本与假环境；UUID/time 固定，
  每组独立重置。使用真实 desktop tools 与 Runner，离线构造 ToolManager，
  **没有运行 SubAgentDriver.create、任务 setup/validator 或真实环境采集**。
  真实 OS/显示器/App/窗口版本及物理清理证据仍待冻结。

从 backend 执行（输出目录必须不存在）：

```bash
uv run --no-sync python scripts/prepare_computer_comparison.py \
  --config core/config.yaml --output /tmp/m5-contract-replay
```

需同一源码、依赖及公开配置。测试验证重复运行逐文件一致、独立模型/历史隔离、
SDK 参数与 schema 配对、密钥不输出、未知 headers/body/provider 拒绝以及不覆盖
已有目录。manifest 的 artifacts 仅覆盖生成器产物，本说明是配套记录。

## 下一批闭环提案（未授权、未执行）

任务复用 `tasks/01-calc-open.yaml` 的 macOS strict validator（7×8=56），
每次独立 reset/新图/validator/teardown，纯 GUI，串行。先完成九点/Calculator
驱动和停止清理验收；不把诊断 pilot 当效果结论。

建议新增 **5 个单因素诊断 pilot**，每组一轮，顺序固定为：
`A-control → B-protocol-only → A → B-host-only → B-combined`。
这些是额外预算，不挤入也不暗中扩大 M6 原有 12 trial 额度；一个样本不足以
估计收益，只检查可运行性、清理和失败归因。若不足，另开预算，不追加重跑。

诊断通过后，核心 **12 trial** 的 B 固定为 B-combined，不根据 pilot 分数挑选：

1. 配对轮 1：A → B-combined → C → D。
2. 配对轮 2：B-combined → C → D → A。
3. 配对轮 3：C → D → A → B-combined。

每个配对轮都运行同一任务的四组，并记录各次实际初始窗口/显示环境。
三轮只轮换顺序，不宣称完全平衡或高统计功效；失败/超时原位保留。

提议硬上限（**当前 exporter 不执行或保障这些限制**）：

- 总计 17 trial、串行；每次 120 秒，任务执行合计至多 2040 秒；setup/清理
  另计并逐次设限，清理不确定立即停止全批，不开始下一轮。
- 每 trial 顶层工具≤15、规划 HTTP 请求≤16；C/D 定位 HTTP≤15；
  所有 HTTP 尝试（含失败）均计数，禁用所有层重试。全批规划≤272、
  定位≤90，其中 Max≤45，总计≤362 次。不能从工具次数推断请求次数。
- 每 trial 共享≤300000 token，全批≤5100000；单请求输出≤8000。
  调用前预留输入/输出最坏用量，未知 usage 用预留额结算并停批；禁止先超限
  再声称已守住硬上限。任何一个上限先到即停止，不自动补跑失败 trial。
- 费用暂拟 **8 USD** 上限，与请求/token/时间上限同时约束；必须先补齐预算
  执行器和未知用量处理。这里的估计不是账户账单或现有代码保证。

费用依据为阿里云北京公开非缓存价格（2026-09-22 查阅）：
[Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash)
最高列示档输入 0.165 / 输出 0.66 USD/百万 token；
[Max](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max)
输入 1.65 / 输出 4.951。用输出单价保守覆盖所有 token：14 个全 Flash trial
至多 4.2M×0.66=2.772 USD；3 个 D trial（连规划也按 Max 计）
至多 0.9M×4.951=4.4559 USD；合计 7.2279 USD，向上预留为 8 USD。
该推导依赖 token 硬限制和所列价格适用，执行前复核账户区域/价格与上下文上限。

图片范围提案仅限待确认的受控 Calculator 桌面/窗口截图；目标端点固定为
`https://dashscope.aliyuncs.com/compatible-mode/v1`，不包含 OpenRouter。
真实截图范围、这 17 trial 新预算和发送端点按计划 §6 在执行前确认；
本说明没有赋予 live 授权。仍须先补齐原始响应/失败归因、串行配对执行器、
预算/重试门禁和可验证清理，再提交具体 live 批次，不能直接运行现有通用 CLI。
