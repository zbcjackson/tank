> 状态：进行中（2026-10-19：用户授权不设建议的固定请求/费用上限，开始拒绝诊断与真实复测）。

# 裁剪修复后的 Jev 真实验证

## 目标与范围

用户要求继续真实复测并明确“可以不做限定”。取消建议的14请求/USD0.10硬上限，
保留未知用量/效果停止、期限、原生授权与资源清理。沿用同版Jev与TextEdit临时
RTF，先复测颜色任务及Box，再加入AX文字充分的指定行任务；不以取得成功为由
重试，固定每项独立分母，不把观察次数当独立应用样本，不操作个人会话。

## 步骤

1. Tests：TDD为原NativeAXChannel增加只读拒绝阶段事件，保留原返回值/派发语义；
   覆盖像素、窗口及AX复扫拒绝与观察者失败。Benchmark持久化所有捕获，包括
   Box响应前后帧，不引入新动作权限。
2. 扩展现有TextEdit配方的显式record-only用量模式，不设置请求/费用/token批次
   上限；未知用量仍停止。原限额模式保留，普通生产预算不变。补充文字充分的
   North/South指定行对照，两臂相同公开任务/候选，私有验收不发送。
3. 按新源码准备/复载冻结、完成完整回归与独立审查后执行真实模型。初始矩阵为
   颜色8任务、指定行8任务、Box6问题（自然计划数22，不是收费上限）。每个微任务
   仍只选择一次、最多一个fill，保留120秒期限；这是两选一判断实验，不是开放规划。
4. 依据全分母分析实际选择/弃权/闭环与精确拒绝阶段，核对只读Box唯一/缺失/重复
   结果及中心命中。若需扩展，在新冻结声明新问题，不补跑已见失败来抬高评分。
5. 归档每次调用、捕获、事件、动作见证、独立读回与清理，记录实际tokens及单独
   的冻结费率估算（record-only账本为unpriced），不把估算当账单。更新主计划/索引，
   结果收尾独立审查沿用本任务轮次，总计不超过3轮。

## Tests

验证record-only无费用/请求准入限制但未知用量停止、原默认限额不变；指定行公开
意图与私有完成隔离、两臂候选对称；捕获失败/帧后拒绝仍保留分母与原图，Box零
输入；所有新增行为在现有test_native.py/test_vision.py覆盖。真实模型能力与模拟
HTTP接线分开报告，不使用旧冻结或改写旧评分。只读遥测不能影响输入门的判定。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`，另检查修改benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部修改Python文件>`，不加type-ignore。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与完整后端串行。
9. `python3 scripts/check_docs.py`与`git diff --check`；冻结、原始成员hash/字节数、
   分母、用量守恒、旧归档不变核验。
10. 协议/生成物变更才执行`python3 scripts/check_protocol_sync.py`；本片无协议变更。
