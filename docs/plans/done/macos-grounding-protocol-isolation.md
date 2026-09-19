> 状态：隔离实验与本地 oracle 已完成，2026-09-19；生产模型闭环验收转 backlog

# macOS 定位模型与输出协议隔离

仅向外部模型发送程序生成的校准图；不上传真实桌面，不修改生产模型。
动态屏幕、外部操作和执行时序降为低优先级。严格输出只保证可解析与
坐标约定，准确定位必须用独立真值验收。

1. 扩展探针的提供方选择与单一输出协议：归一化点、像素点、归一化边框；
   主机严格验证类型、范围、边框顺序并计算中心，保留未找到结果。
2. 使用新合成布局，在 Qwen3.7 Flash/Plus 对照及 Qwen3.8 Flash/Max、
   DeepSeek V4.1 Flash、GPT Mini/5.5 上预检可用性与基线；缺少凭据或模型
   不可用单独记录，不视为定位失败，不静默替换模型或端点。
3. 对同一模型比较点/边框、strict 开关、标记/文字/打乱布局、完整/裁剪图、
   单图/历史图、最小/agent 提示。分阶段筛选后重复新布局，避免全因子盲跑。
4. 捕获实际请求图片 hash、顺序、参数及原始响应；统计格式、按钮像素命中、
   有符号误差与中心距离。可用时同模型原生/兼容接口对照，区分相关性与因果。
5. 本地 Calculator 已知坐标经过生产点击链，独立读取 7×8=56；不把
   模型合成图分数等同于真实完整 benchmark 成功。
6. 归档结果、剩余限制及复现命令；达到证据边界时明确未完成项。

## 结果与后续边界

- 共 304 次纯合成请求，实际 SDK HTTP 图片 hash/顺序与原始参数回放通过。
- 独立 16 布局各重复两次：GPT-5.5 32/32、GPT Mini 30/32、Qwen3.8 Flash
  25/32 命中；后者仍有约 418 px 大偏移。输出格式约束不足以保证定位。
- nullable schema 在 Qwen 上产生字符串坐标，单一 integer 修复格式；
  strict 与边框都不是普遍的定位修复，原生 API 仍复现大错。
- Calculator 真值坐标走生产截图/点击链：3/3 完成 7×8=56，12 次光标误差
  ≤1 逻辑点。首次未归档的光标断言异常仍未归因。
- 探针 40 passed，完整 backend 4468 passed/1 skipped，E2E 14/55；
  下列完整检查通过。提供方适配、协议及测试已提交，生产模型未改。
- 长历史/compaction、完整模型驱动的真实 GUI 和生产切换条件移交
  [backlog](../../backlog.md)，不能把本轮静态合成定位等同全场景修复。
- [研究结论](../../research/macos-coordinate-chain.md#2026-09-19-跨提供方与严格协议隔离)
  与原始证据记录全部实验、不确定性和复现命令。

## Tests

- 严格输出拒绝额外字段、字符串/布尔坐标、越界、颠倒边框和无效 JSON；
  支持 found=false；边框中心、裁剪偏移与逐轴缩放由主机计算。
- 实际 SDK HTTP 边界校验各提供方参数、图片字节、历史顺序及原始响应；
  不允许 Qwen 专有参数混入 GPT/DeepSeek，实验不修改原 profile。
- 合成布局生成和按钮 mask 命中评分使用独立已知样例，实际模型不进单元测试。
- 回归已有坐标链和模型探针测试；Calculator 真机结果单独归档。

## 最终 Verification Checklist

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/`
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright` 加本轮修改的 Python 文件
6. `cd cli && uv run ruff check src/ tests/`
7. 检查 tmux tank 实际后端面板的 reload 错误
8. `cd test && pnpm test`
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`
