# M3 显式定位状态筛选

2026-09-21。36 次合成图请求完成。显式状态字段能区分结果类别，但不能保证模型
识别正确：24 个负例中 5 次仍返回合法 `found` 坐标。生产配置未改变，M3 未关闭。

## 样本与冻结条件

四模型 × 三个新开发布局（301–303）× 三条件：目标唯一存在、目标缺失、
两个同名按钮。共 9 张图片，每设置一次；统计独立布局数是 3，不能视为 36 个
独立样本。目标是 AC、7、AC，图片 1440×900、1050×1680、1536×1024。
从现有 calculator scene 生成，每个条件仅替换一个按钮文字，保留几何、颜色、
背景及同布局的目标提示。缺失将目标改为 DEL；歧义将另一按钮改为目标文字。
[联系图](contact-sheet.png) 已在付费调用前由助手视觉核对，未发送给模型；
[像素回放](offline-replay.json) 验证差异只发生在该文字区域。

所有调用使用生产 `GroundingAdapter.request()` 和 `LLM.complete_response()`，
point 0–1000 整数，`status_field=True`、strict=false、detail=auto；非 found
必须零坐标，解析后没有点/框。温度 0.1，输出上限 16000，单次 90 秒，无重试。
Qwen3.7/Max 关闭 thinking，Qwen3.8 Flash/DeepSeek 开启；Qwen 高分辨率参数
不传，DeepSeek 使用 beta 端点。三布局轮换模型及条件顺序，未随机化。
DeepSeek thinking 下 temperature 不生效。本批未重测 GPT 对照。

这是显式 status 的行为筛选，**不是新旧 schema 的 A/B**；没有把本批与旧批
不同图片的分数差归因为 schema 收益。holdout 图片/真值未用于筛选；只比对
其预先冻结的输入 hash，交集为零。无 holdout 请求、真实截图或桌面动作。

## 结果

所有 36 次 HTTP 200、schema 合法、usage 已知，无截断、超时或重试。
每模型各 3 个正例、3 个缺失、3 个歧义样本：

- Qwen3.7 Flash：正例命中 **1/3**；缺失状态正确 **3/3**；歧义正确 **0/3**，
  三次均误报 found。完整样本成功 **4/9**，负例可用错坐标 **3/6**。
- Qwen3.8 Flash（thinking on）：正例 **2/3**；缺失 **3/3**；歧义 **2/3**。
  完整成功 **7/9**，负例可用错坐标 **1/6**。
- Qwen3.8 Max（thinking off）：正例 **3/3**；缺失 **2/3**；歧义 **3/3**。
  完整成功 **8/9**，负例可用错坐标 **1/6**，发生在缺失数字 7 的布局 302。
  请求 snapshot 名为 qwen3.8-max-2026-09-02，响应为 qwen3.8-max-0902。
- DeepSeek Flash（thinking on）：正例 **2/3**；缺失 **3/3**；歧义 **3/3**。
  完整成功 **8/9**，负例可用错坐标 **0/6**，不能由六次零失败推断可靠拒绝率。

状态正确 31/36；正例命中 8/12；完整成功 27/36。正例成功要求 found 且落入
圆角按钮 mask；负例成功要求准确的 not_found/ambiguous 状态且没有坐标。
解析失败也计入失败分母；本批未出现。负例的旧按钮位置不作命中标准。
合法 schema 只能保证数据可解析，不能保证视觉判断正确；M4 不得把 found
或非空坐标本身视为执行正确性的证明，仍须遵循既定帧校验与动作反馈设计。

## 预算与费用

本批 **86783 tokens**，累计筛选 **141/144 次、406311 已知 tokens**；旧 402
实际用量仍 unknown，另保留 **26000 tokens** 估算预留，账面占用 432311。
剩余 **3 次 / 567689 tokens**（已扣预留），不重置额度或把预留记为已消耗。
预检仍为独立 16/16 次、26398 tokens。本批请求前冻结估计 $1.144782；按实际
输入/输出用量及未缓存峰值标价估算 **$0.059274144**。实际账单 unknown，
未把缓存命中折扣当成已知实付。

价目来源：[Qwen3.7 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash)、
[Qwen3.8 Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash)、
[Qwen3.8 Max](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max)、
[DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/)，2026-09-21 核对；
DeepSeek 复用同日图像批核对的价目，不因本次页面抓取失败猜测新价格。

## 证据与验证

- [manifest](manifest.json)：模型、请求参数、图片/源文件 hash、计费估算及累计预算。
- [结果](results.json)、[汇总](summary.json)：全部尝试，状态和空间评分分开。
- [离线预检](offline-check.json)：36 次 SDK 假请求，12 组三条件除图片外完全一致。
- [回放](offline-replay.json)：36 次实际 HTTP body 对冻结请求、原始响应对 SDK
  对象、生产解析与 mask/状态评分一致；9 张图像 hash/尺寸及局部修改校验。
- `*.response.json.gz` 保留原始响应；`*.request.json` 保存实际请求，图片 URL
  以 hash 替代；PNG 单独保存，无密钥。`runner.txt` 是调用前冻结执行记录，
  `replay.txt` 是离线审计记录，不作为新的生产框架。
- [全套验证](verification.json)：定位测试 83 项；后端全套、E2E、lint、类型、
  实际后端日志、文档和协议一致性。无 Python 源码或测试改动，pyright 为 N/A。

下一步收敛并冻结开发候选及未测试能力边界，再执行独立 holdout；不得因本批
样本少或剩余请求少而宣称 M3 已验收。native 协议仍未验收，生产默认保持原状。
