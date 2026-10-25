> 状态：进行中（2026-10-25：先做原版linkding预览图的零模型界面资格；通过后冻结一次视觉接管及返回Jev任务。）

# 像素语义与视觉后返回Jev

## 目标与边界

承接[主计划](computer-use-jev-vision.md)与[位置证据结案](../done/jev-spatial-evidence.md)。
目标是验证当前结构/几何未表达的像素语义能否通过自然视觉接管补充，并在新一步
恢复Jev选择，最终正确完成。只验证受控可行性，不作模型优劣、统计采用或默认切换。

优先原版linkding1.47.0预览图：真实原模板/样式/生产DOM和AgentRunner，临时副本、
合成账号/两条书签及确定性图片数据；不改界面、不删除可访问名称或过滤候选。
后台外网任务禁用，回环服务；合成登录属于测试初始化，不向模型提供会话或隐藏标签。
本片不计划改生产代码；若资格暴露运行缺陷，先保留失败并明确最小修复范围。

## 步骤

1. 零模型检查原预览功能、完整候选/几何、绑定PNG、公开效果/完成条件和数据只读。
   固定两条书签文字及布局，仅互换预览图像素。规范化随机引用/观察身份后，两种
   状态供Jev的结构与几何相同，但红色三角形目标随图片移动；不把模型可能猜中
   当作文字已表达颜色。截图应清楚区分目标，候选覆盖实际操作。
2. 资格后冻结一个任务：从带筛选条件的真实列表找到红三角预览对应书签，打开Edit，
   再通过Bookmarks返回不带筛选的列表。初始URL必须不满足完成条件；目标id/ref/
   位置/答案不进入公开任务。独立审计要求实际正确Edit来源和后续返回，不能只看
   最终URL。若该流程无合法引用、完整观察或可核验完成，则记录不合格，不收费。
3. 使用真实生产Runner/原DOM通道和官方SDK假HTTP，验证接管、正确来源、下一步
   Jev、两次原引用动作、零POST/DB变化、账本/清理及故障拒绝。模拟回答只验证协议，
   不计真实模型能力；假输出依据收到的公开包/PNG，不泄漏正确alias到真实请求。
4. 冻结驱动/独立审计器、当前运行源/依赖与原产品、任务/顺序/接收方/预算，核对既有
   完整回归字节未变及全部适用检查；独立审查材料后才启动一次真实单任务，不重跑。
   TypeSafe https://api.typesafe.ai/v1/systemone jev-1.14.0接收公开合成文字/几何；
   原自然兜底OpenRouter https://openrouter.ai/api/v1 google/gemini-3.8-flash接收
   同状态与绑定1280×720 PNG。最多8SDK、120秒/6动作/24观察/10万已记账token，
   视觉输出4096、retry0，金额未定价；宿主token限额不是提供方预留硬上界。
   沿用既有授权范围，不借旧3648槽无上限许可。未知用量/效果、源漂移、未结预留、
   证据/清理失败停批，保留失败且不重发。
5. 独立核对真实原始选择/图片/引用/执行/HTTP/DB/公开DOM/清理/账本：观察实际路线。
   理想路线为Jev请求上下文→视觉正确Edit→新观察Jev返回Bookmarks；不强迫Jev弃权，
   猜中直通、走错或停止均照实报告，不能凭路径期待重试或挑样。
6. 完成项目review-and-refactor（最多3轮，零可操作发现即停止），保存原报告及工件
   manifest/SHA。计划结案移done，更新索引/主计划；剩余条件扩展交backlog。

## Tests

本片计划不改运行行为，优先可复核资格和假HTTP集成：图片互换保持公开结构/几何，
目标随像素改变；初始完成为假；完整候选/正确Edit引用；视觉返回新Jev与正确后续
动作；仅URL相同但错误来源须拒绝；无图片、错误颜色/引用、未完成返回或DB变化
不能判通过。真实调用前用独立检查器核对源/原始包/日志，未知用量和清理失败停批。
若确需生产行为改动，沿既有测试域按TDD逐行为红绿，不新建同域feature。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest；启用Chromium和已恢复真实产品，修复所有失败。
5. cd backend && uv run pyright <全部改动Python>，不以type-ignore压制。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误；空输出通过，不重复空结果检查。
8. cd test && pnpm test；与重型浏览器验证串行，finally恢复原服务。
9. python3 scripts/check_docs.py、git diff --check；资格/假HTTP/独立审计、归档完整性、
   当前源/旧工件/默认配置SHA与审查/签名核对。只改docs时按项目例外仅需文档检查，
   运行字节未变的既有完整检查可明确复用，不将其称为本轮重跑。
10. python3 scripts/check_protocol_sync.py；协议/生成物未改则不适用。
