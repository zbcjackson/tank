> 状态：已完成，2026-09-19；112 次合成请求与全部验证通过

# DeepSeek 定位预算与思考开关复测

4000 是诊断探针的输出预算，不是生产配置或服务上限。仅上传程序生成的
合成图；保持生产配置不变，检验截断与定位误差是否由同一因素造成。

1. 为矩阵探针添加独立的输出预算与思考开关，保留现有默认行为。
2. 相同 seeds 101–102、point / strict-bbox / low-detail、各重复两次，
   比较 thinking on/off × max_tokens 4000/16000，保留真实 HTTP 参数和响应。
3. 在独立 seeds 201–216 上复测 off/4000 与 on/16000，每布局重复两次，分别统计
   截断、格式、按钮命中、误差、推理及输出 token；不将小样本认作完整 GUI 验收。
4. 归档证据、更新研究结论与测试说明，提交代码和实验记录。

## 结果

- 4000 是诊断默认值；新增 `--max-tokens` 与独立的 `--thinking on|off`，
  生产配置未改。实际 SDK HTTP 验证开关、预算、图片与 schema。
- 48 次配对筛选：on/4000 有两次纯推理截断，off 两种预算均正常输出；
  on/16000 在筛选中消除截断但未提高总命中率。
- 64 次独立布局复测：off/4000 20/32 命中，on/16000 23/32 命中；后者
  仍一次耗尽 16000 推理 token 无点击。关闭思考平均输出 token 减少 85.9%，
  定位错误仍然存在，不能把格式正确或不截断等同准确。
- Probe 48 passed，backend 4476 passed/1 skipped，E2E 14/55；下列检查全通过。
- [完整实验记录](../../../backend/benchmarks/computer_use/reports/20260919-deepseek-budget/README.md)。
  本计划范围内无待办；真实模型 GUI 闭环仍由既有
  [backlog](../../backlog.md) 跟踪，不以本次合成实验替代。

## Tests

- 先写失败测试：CLI 开关穿过探针和实际 SDK 到达 HTTP，保持合成图片、
  坐标 schema 不变；思考开关与预算独立；默认 no-thinking 变体兼容。
- 非正预算在网络请求及输出目录创建前失败。
- 原始响应的 length / reasoning_tokens 留在结果中，不能误判为坐标偏差。
- 回归整个 grounding probe 与 backend；实际付费请求不进入单元测试。

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
