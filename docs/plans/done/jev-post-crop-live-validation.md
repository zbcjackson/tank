> 状态：已完成（2026-10-19：22次真实请求、完整证据归档与第2轮独立结果审查完成，保留小目标Box0/2及一次frame_scene拒绝）。

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

## 实现验证

实现增加8种原生拒绝阶段及观察者失败回归，保留原None/回执语义。配方增加
record-only/text-controls冻结选项，读取时重新计算全部冻结输入；新增指定行
意图与私有验收隔离检查，所有捕获立即存图与帧元数据（含Box前后）。

专项258通过（30.88秒）；完整后端6353通过/1跳过（460.58秒）。web lint/项目
引用类型检查、backend/CLI lint、4个修改Python文件pyright和dev日志均通过。
新准备目录`/private/tmp/tank-jev-post-crop-live-20261019`，冻结SHA256为
`24cf1173480a7ef51477b99243151859886860b43a965a822122dba846cd6d07`；
record_only=true、request_limit=null，账本0限额字段仅占位且不准入拦截。
E2E21场景/83步骤全部通过（142.299秒），与完整后端串行。docs62及diff检查
通过，协议未变。上述实现验证先于真实运行完成；按本轮已有授权执行。
实现签名提交8e54bccc。

第1轮独立代码审查（review-and-refactor，基线8858ab52）未确认可操作缺陷；
独立专项258通过（27.88秒），复载上述冻结成功，确认18个context、record-only
无批次准入上限且尚未启动。源码未改，复用上述完整回归；本轮仅补充验证与
审查记录，真实运行后的证据审查仍沿用本任务轮次。

## 真实交付

22次真实请求、198994已知tokens、无未知/重试/全批停止；历史冻结费率单独
估算USD0.008296512，record-only账本unpriced的费用0不代表免费。颜色图片
4/4完成、文字4次ambiguous弃权；指定行两臂模型各4/4正确，图片4/4完成、
文字3/4完成（1次frame_scene拒绝、零输入）。Box数量6/6正确，小italic中心
0/2，缺失/多目标4项通过，保留复合4/6评分及原始失败。18清理确认、11次
fill均有原生见证/收据/独立正文。152项原始工件及边界见
[真实复测记录](../../research/jev-post-crop-live-validation.md)。
本切片问题已完成运行，不按成功与否补题；后续小目标表示/裁剪假设、广泛真实
应用与可替换视觉模型对照仍由主计划承接，无新增条件暂缓条目。

第2轮独立结果审查未确认可操作缺陷；独立重算152个归档成员/130张PNG、
42项源码hash、22组调用/用量、11次原生输入关联、45次捕获、完整任务分母及
Box坐标/评分均一致。旧6份Jev归档不变、凭据字节扫描无命中，docs/diff和
面板类型检查通过；源码未改，复用上述完整回归。仅收尾状态、链接与证据边界
文字由审查者修改并自检，不另启动第3轮。面板实际渲染未验。

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
