# M3 唯一匹配提示修正与最后三次开发检查

2026-09-22。旧 found 协议现明确要求唯一、无歧义匹配；多个匹配必须拒绝。
同一开发图各测一次：**Max bbox 与 GPT point 正确拒绝，Qwen3.7 point 仍误报
坐标**。这是单布局 smoke，不是独立验收或因果 A/B；默认模型不切换。

## 最小实现

[GroundingAdapter](../../../../core/src/tank_backend/tools/computer_grounding.py)
只修改旧 found 提示文字：found=true 限于 exactly one unambiguous matching
target；多个匹配、缺失或不确定时 found=false，沿用零/null 哨兵。schema、
坐标解释、解析器、thinking/detail/模型 profile 和 LLM 层不变，没有新增模型类。
显式 status 分支已含多匹配规则，本次未修改。生产一体 agent 和桌面动作路径
未切换；共用接口尚未注册 locate。提示表达要求，不能强制模型判断正确。

代码提交 `73f6b0e`。实际 SDK 规则断言先失败，修改后通过；九组 point/pixels/
bbox × nullable 配置及三条 provider HTTP 通路覆盖。历史回复仍作解析回归，
请求比较仅允许已声明的提示文字差异，不修改历史请求或历史成绩。

源码变化会使旧 holdout freeze 校验失败，这是预期保护，不更新旧 manifest
绕过它。执行器失败路径测试使用临时当前契约 freeze；另有回归确认旧 freeze
继续拒绝源码变化。曾出现的十项历史请求文字不相等失败已按上述精确差异
修正，格式、图片、模型参数、原始解析和历史 mask 分数断言全部保留。

## 开发检查与证据

[freeze/manifest](freeze/manifest.json) 锁定三配置、当前源码 hash、3 次请求、
剩余筛选额度与停止条件。复用已知开发图 `302-ambiguous`（1050×1680），
有两个“7”；PNG 与 [status 开发批](../20260921-m3-screening-status/README.md)
字节一致。不是新独立样本，也没有重跑已评估的 64 图 holdout。

三配置：Qwen3.7 point/off、Max bbox/off、GPT point/none；旧 found schema、
integer、strict=false、detail=auto、8000 输出上限。schema/profile 设置与先前
开发请求相同；[离线准备](offline-preparation.json) 和三份 fake SDK 请求已核对。
复用冻结请求执行器，仅将本批上限设为剩余 **3 次 / 567689 tokens**；该 token
额度已扣除原已知用量和历史未知预留，不是新的 holdout 配额。

全部 HTTP 200、格式合法、usage 已知，无截断或重试；[回放](replay.txt)
核对实际 body 对冻结 body、原始响应对 SDK 对象、生产解析及无点/框拒绝条件。

- Qwen3.7 Flash：found=true，返回 `(830.55, 1382.64)`，**错误接受**同名目标；
  2226 tokens。明确提示后仍未可靠拒绝，不能假定基线问题已解决。
- Qwen3.8 Max bbox：found=false、坐标全零；解析后无点/框，**正确拒绝**；
  2345 tokens，返回模型别名 qwen3.8-max-0902。
- GPT-5.5 point：found=false、坐标全零；解析后无点/框，**正确拒绝**；
  2326 tokens，返回 openai/gpt-5.5、provider=OpenAI。

只有一张开发图、每配置一次，没有本轮旧提示控制组或正例，因此不能从 2/3
推导可靠拒绝率、正例无退化或提示的因果收益；不能与不同 schema/图片的
历史分数直接相减。保留既有 holdout 全部失败记录和默认模型，本批不作采用。

## 预算

本批 **6897 tokens**。筛选累计 **144/144 次、413208 已知 tokens + 26000
历史未知预留**，尚余 560792 token 空间但请求额度为零，不能据此追加请求。
预检 16/16、26398 tokens；holdout 384/384、715802 tokens，均保持不变。
首轮静态累计 **544/544 次、1155408 已知 tokens + 26000 预留**。旧 402
仍为未知，不计零；本批没有新未知用量，也没有真实截图或桌面动作。

[价格 manifest](prices.json) 2026-09-22 核对：
[Qwen3.7](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash)、
[Max](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max)、
[OpenRouter GPT-5.5](https://openrouter.ai/openai/gpt-5.5)。保守估计 **$0.347268**；
按实际 token 未缓存标价估算 **$0.016570457**。GPT 回报 cost **$0.012255**，
Qwen 未回报，因此整批实际账单仍 unknown。

新增付费实验须另列批次、理由、样本与预算；旧 holdout 不重新标为独立样本。
后续可推进已授权 M4 的离线 locate 编排和契约测试，不能把本批 smoke 当成
模型可靠性验收，或绕过帧校验、共享预算、取消及动作反馈。

## Tests 与验证

[verification](verification.json)：定位 **103 passed**；完整后端 **4615 passed /
1 skipped**，E2E **14 场景 / 55 步**；web lint/TypeScript、backend/CLI ruff、
两个改动 Python 文件 pyright、真实后端日志、文档与协议一致性通过。
实现测试不替代模型成绩。历史报告只读，本次新增 freeze/live/summary 归档。

[summary](summary.json) 保留全部结果和累计账本；`live/*.response.json.gz`
是原始 HTTP，`live/*.request.json` 是以图片 hash 替换 URL 的实际请求；
无密钥。`prepare.txt` 为离线冻结记录，复用既有执行器，未引入新的执行框架。
