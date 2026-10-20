> 状态：进行中（2026-10-20：真实应用准入探查中；未调用模型）。

# 真实产品中的结构优先与视觉路由

## 目标与边界

承接用户“开始”和[主计划](computer-use-jev-vision.md)。先用未改页面的固定版本
sqlite-web 0.8.1，在临时目录新建合成SQLite数据库及隔离Chromium，检验V/JT在
真实产品的新任务族中是否仍有质量/耗时/图片开销收益。它是数据库管理产品，
不是自编设置页；仍为单一产品的开发验证，不是未见独立确认或开放规划。
来源：[项目官方仓库](https://github.com/coleifer/sqlite-web)。

先无模型检查原始页面与现有宿主契约。已发现普通链接无声明效果时不会进入
ActionBuilder，编辑页还可能需要勾选列；不能通过给应用添加aria标签或脚本
操纵真实模型选择来掩盖缺口。必要通用DOM能力按TDD最小补齐，保留新鲜度、
权限、效果未知不重放和独立完成守卫。若准入不成立，保留实际失败并先处理宿主，
不以手工页面替代产品实验。

拟测创建记录、编辑指定记录且保持其他字段/记录不变，两种合成数据顺序；
附初始GET一次503后可显式重试的可恢复故障。故障由实验边界注入，产品页面/
实现不改；仅GET可重试，不重放未知POST。最终任务数、数据、故障时点与计分
须在真实调用前冻结。共享真实Controller/TaskRuntime/ActionBuilder/守卫与清理；
V规则后Gemini带图选择，JT适用时Jev文字，其余同一Gemini；Jev图片/Box不在本轮。
独立SQLite只读回执与写入轨迹核验业务效果，禁止以模型回答或到达页面视作业务完成。

沿用无固定批次请求/token/费用上限授权，record-only、每任务120秒/6动作/24观察、
SDK不重试，未知用量/运行/审计/清理失败停批、保留未运行分母。仅发实验合成数据
及真实产品界面：api.typesafe.ai接收Jev文字，openrouter.ai接收Gemini PNG+文字。
不访问个人数据库、账户或现有浏览器；全部旧11归档/原评分保持，生产默认不变。

## Tests

1. 无模型探查固定原始产品，记录DOM/候选/页面与数据库；形成最小准入回归。
2. 逐条TDD补实际需要的通用链接/控件效果，验证同源、替换/导航/像素/权限拒绝、
   不变/未知效果不算业务成功，真实产品源文件hash保持。
3. 扩展既有test_dom.py及managed Chromium E2E场景，不建同域feature。
   fake HTTP贯穿真实SDK、产品服务器/浏览器/宿主、独立数据库核验及全部清理；
   覆盖冻结篡改、错误选择/未知用量/故障恢复/停止后全部分母，准备不分配客户端。
4. 完整验证、第1轮独立review-and-refactor后新目录冻结并真实运行；保留原始
   请求/回复/图片、动作审计、HTTP/数据库轨迹、结果与清理，模型错误不补跑。
5. 按普通/故障、V/JT和任务族独立重算，失败取120秒，分列效果/质量/恢复及全部
   开销；归档与实际凭据扫描，旧证据核验，报告/主计划/索引/面板更新，经第2轮
   结果审查关档；不把本开发产品/探查用例当独立确认。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run --no-sync ruff check core/src/ core/tests/ plugins/`及改动benchmark。
4. `cd backend && TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest`
5. `cd backend && uv run --no-sync pyright <全部改动Python>`，不得type-ignore。
6. `cd cli && uv run --no-sync ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i 'error\|traceback\|exception'`，空输出通过。
8. `cd test && pnpm test`，与完整后端串行。
9. `python3 scripts/check_docs.py`、`git diff --check`，核验冻结、归档与旧证据。
10. 仅协议/生成物变化时`python3 scripts/check_protocol_sync.py`。
