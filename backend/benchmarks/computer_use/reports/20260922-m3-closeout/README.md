# M3 证据核对与范围收尾

日期：2026-09-22。结论：**M3 实现、首轮实验与范围处置完成；没有候选通过完整采用门槛。**
本次用户明确要求完成证据核对与范围收尾；无新增付费推理、真实截图外发或桌面动作。
代码基线 `6522882`（唯一匹配提示实现 `73f6b0e`），本次仅新增核对记录并更新文档。

## 实现与契约证据

生产共用 `GroundingAdapter` 以参数表达 point/pixels/bbox、nullable、strict、detail
和状态格式；LLMProfile 管理端点/型号/思考参数，通用单次 LLM 接口保留原始响应。
解析输出统一图片坐标类型，再由 M2 observation/transform 还原；不猜测单位、不修复
非法输出、不执行点击。尚未向 AgentRunner 注册 locate，属于 M4 的后续集成。

[五模型预检](../20260920-m3-preflight/README.md)保留 2026-09-20 官方契约来源、
图片 hash、实际请求、原始响应和 SDK HTTP 回放证据。型号核对如下：

- Qwen3.7 请求/返回 `qwen3.7-flash-2026-07-15`。
- Qwen3.8 Flash 请求/返回 `qwen3.8-flash`。
- Qwen3.8 Max 请求 `qwen3.8-max-2026-09-02`，返回 `qwen3.8-max-0902`。
- DeepSeek 请求/返回 `deepseek-flash`；V4.1 归属依据当日官方文档，不证明不可变权重身份。
- OpenRouter 请求/返回 `openai/gpt-5.5`，实际响应 provider 为 OpenAI。
  Qwen/DeepSeek 直连响应未返回 provider 字段，不将配置提供商当作响应证据。

预检证明当时配置端点的图片与自定义工具调用，不证明今天的可用性，也不证明原生
computer 能力。外部统一采用 Chat Completions image_url PNG + 自定义 click 工具。
[strict 六次配对](../20260920-m3-strict/README.md)仅覆盖 Flash/Max/DeepSeek；
Flash 仍出现数组，不能宣称 strict 保证格式。Qwen3.7/GPT 的 strict 未单独验证，
冻结路线不启用它；不是宣称不支持。自定义 bbox 不是供应商原生框协议。

## 实验与采用结论

- [点/框筛选](../20260920-m3-screening-protocol/README.md) 40 次。
- [thinking 首批](../20260920-m3-screening-thinking/README.md) 7 次尝试，
  [余额恢复续跑](../20260920-m3-screening-thinking-resume/README.md) 26 次，
  共 32 设置、33 次尝试。DeepSeek 16k 配对 off/on 完成请求命中 2/4、3/4；
  off 包含历史 402 为 2/5，另一次 HTTP 200 缺工具响应亦保留。
  关闭思考候选已测试，余额恢复解除执行阻塞，没有证明其质量合格。
- [图片参数](../20260921-m3-screening-image/README.md) 32 次，未见普遍命中收益；
  不据此推断服务端缩图补偿。
- [显式状态](../20260921-m3-screening-status/README.md) 36 次，24 负例中 5 次误报坐标；
  格式合法不代表视觉判断正确。
- [冻结](../20260921-m3-holdout-freeze/README.md)后的
  [holdout](../20260921-m3-holdout/README.md) 384 次：64 独立布局 × 2 重复 × 3 配置。
  Qwen3.7/Max/GPT 正例命中 57/96、96/96、96/96，缺失拒绝均 16/16，
  同名歧义正确拒绝均 0/16。Max/GPT 正例中心误差 p95 为 2.29/1.82 px，
  仍因负例不合格未采用。旧提示未明确多匹配必须拒绝，结论针对该配置整体，
  不单独归因于模型视觉能力；已消耗的 holdout 不再充当调参后的独立验收。
- [唯一匹配修正](../20260922-m3-unique-match/README.md)后 3 次开发 smoke：
  同一既有歧义图，Max/GPT 拒绝、Qwen3.7 误报。无旧提示实时对照、无正例复验，
  不证明修正的因果收益、可靠拒绝率或正例无退化。

因此保留默认模型；M3 完成不等于误差问题消失、模型采用通过或真实任务验收完成。

## 离线账本核对

运行仓库根目录命令：

```sh
python3 backend/benchmarks/computer_use/reports/20260922-m3-closeout/audit.py.txt
```

[audit.json](audit.json)逐条核对原始响应的 prompt/completion/total tokens、返回
model/provider 与结果行一致，并记录 10 份结果文件、544 份请求、544 份压缩原始
响应的 SHA-256。仅审计档案一致性，不重新评分，也不声称 hash 证明供应商真实性。

- 预检 16 次：26,398 已知 tokens。
- 筛选 144 次：413,208 已知 tokens；其中 1 次 HTTP 402 未知用量。
- holdout 384 次：715,802 已知 tokens。
- 合计 544 次尝试、543 次 HTTP 200；1,155,408 已知 tokens，加历史未知用量
  26,000 预算预留，共占账 1,181,408。未知不是零，也不是已知实际消耗。

三阶段请求额度全部耗尽，剩余 token 容量不产生新请求权限。续跑只读取本批
26 行，不重复累计包含首批的组合汇总；M1 提示 A/B 不属 M3 账本。完整实际账单
仍未知；本次未重新估价，亦未新增收费。

## 明确范围处置

- 原生点框、Responses computer 与 UI-TARS 等专用部署：**未测试，条件触发暂缓**。
  需明确采用该路线的需求、可用端点/部署、协议/授权及新实验预算；不能冒充验证通过
  或不支持。已交接到 [backlog](../../../../../docs/backlog.md)。
- 追加静态采用复验：需决定重新考虑候选、新预算、新独立数据与冻结；当前 smoke
  不够支持采用。相同 backlog 登记触发条件，不能默认重开已耗尽的 544 次额度。
- M4–M8 的定位集成、对照和真实任务验收继续保留在
  [active 计划](../../../../../docs/plans/active/computer-use-adaptation-and-grounding.md)，
  不移交为可选项，也不将整份计划移到 done。

M3 的“适配无收益亦为有效结果”允许在未找到可采用候选时收尾。本次范围处置
明确记录未测项，未降低采用门槛；尚未实现的 M4 是下一步，不是 M3 的隐藏完成声明。

## 回归验证

完整项目检查通过，后端 4615 passed / 1 skipped，E2E 14 场景 / 55 步通过。
命令、环境和边界见 [verification.md](verification.md)。
