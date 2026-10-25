> 状态：执行中（2026-10-25：实现有界DOM位置证据与显式空间提示，先TDD、完整回归，再一次真实导航验证。）

# 有界位置证据与Jev准入

## 目标与最小接口

承接[空间实测](../../research/jev-interface-routing.md)：Jev已选正确链接，重复身份守卫
仍转图片。本片为当前DOM候选补充可核验位置依据，减少这种保守回退，不新增App分类器、
自由坐标动作或通用自然语言位置解析。保留完整候选、原引用/权限/效果/清理边界。

- 可信浏览器配置observe_bounds: true显式启用主frame的实际renderer bounding_box
  与视口CSS像素尺寸；与完整一致DOMView一起冻结，重读/派发前继续比对几何，默认关闭。
- GoalContract增加可选spatial_hint：role、label及leftmost/rightmost/topmost/bottommost。
  它是任务声明的相对位置提示，不授予动作权限；未给提示不扩大文字准入。不猜“sidebar”
  之类区域名称。提示默认省略，保持已有模型请求形状；本片仅启用有主frame几何的DOM。
- 原文字唯一候选规则保持。只有提示匹配一组同语义DOM候选，全部图框有限、在当前
  视口内，且一个候选沿所需轴与所有同组候选严格分离时，才额外允许它走文字。
  重叠、未知/不完整/陈旧几何、不同语义或没有提示均不借坐标区分来放松重复控件门。
  这是可区分性证据，不等于任务正确性或额外权限；原图片选择路径和核验仍保留。

## 步骤

1. 在既有test_dom.py先红绿验证显式主frame几何、坐标约定/模型投影及CSS布局变化的
   派发前拒绝；实现最小观察字段，不改变默认和原生AX坐标。
2. 在既有test_vision.py逐项验证显式位置提示下重复链接Jev直通且保持完整候选，再补
   未给/不匹配提示、重叠/越界/缺失/无效/陈旧数据等反例。接口保持可选和有界。
3. 原版sqlite-web/真实Runner/双SDK假HTTP回归；现有chat.feature同域加入新契约，
   不另建feature。正确左侧目标仅Jev一次/零图片；错来源即使URL完成仍独立判失败。
4. 更新现行设计/插件说明/开发与测试文档；通过下列全部适用检查，浏览器重型验证串行。
5. 对最终源重新冻结一次真实导航任务：原版页面、相同任务，增加显式公开spatial_hint
   和observe_bounds；先无模型/假HTTP资格再真实单次。TypeSafe Jev文字，原自然视觉
   分支仍为OpenRouter Gemini，沿用120秒/6动作/24观察/10万已记账token/8SDK上限、
   视觉输出4096/retry0、金额未定价；不是提供方预留硬上界。未知用量/效果、漂移、
   未结预留或清理失败停批，不重跑。独立来源/原DB/HTTP/HTML/捕获/执行/账本核对。
6. 目标为正确来源Jev直通、一次动作、零图片/写入/未结用量。真实失败保留，不因期望
   零图片而强迫输出。结果只限该空间提示任务，不宣称通用位置理解、Jev优于视觉或
   默认采用。当前源如被修复须重新资格，旧实测保持其源版本边界。
7. 通过项目review-and-refactor（最多3轮）后签名归档，条件性扩展交backlog，更新索引。

## Tests

使用TDD垂直切片：一个行为测试失败→最小实现→验证，再推进下一行为。真实Chromium/
生产Runner及双SDK假HTTP，实际渲染框而非模型坐标；模型只选原有动作。验证完整候选、
坐标系/视口、默认无几何/无提示兼容、同名组与相对位置、重叠/边界/非有限数据、CSSOM/
滚动/视口变化造成的陈旧拒绝，以及视觉接管/硬停止保持。实际产品来源与数据只读审计
不进入模型答案。既有单元/E2E全部适用，不用旧结果代替当前源检查。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest；启用Chromium和既有真实产品环境，修复所有失败。
5. cd backend && uv run pyright <全部改动Python>；不以type-ignore压制。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出通过，不重复检查空结果。
8. cd test && pnpm test；本地Sherpa/回环模型/隔离DB，finally恢复原服务，与浏览器重型
   后端测试串行。使用临时caffeinate -is防止维护休眠，不改全局电源设置。
9. python3 scripts/check_docs.py、git diff --check；定向/资格/单次实测、源/配置/旧工件SHA、
   归档完整性、独立审查及签名记录核对。
10. python3 scripts/check_protocol_sync.py；协议及生成物未改则不适用。
