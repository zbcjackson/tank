> 状态：已完成（2026-10-24：显式实验接线、全部适用验证及第1轮独立审查完成，无可操作或遗留问题；默认不变，无新增真实模型调用。）

# 动作级选择器的显式实验配置

## 范围与验收

承接[主计划](../active/computer-use-jev-vision.md)及[边界结论](../../research/jev-action-boundary.md)。
将已验证的动作级文字准入作为插件内selector，通过现有factory显式选择
jev-action-vision；复用VisualSelector继承的视觉注册/接管、原Controller/执行器、
权限/数据接收准入/期限/账本/清理。构造仍不启动浏览器或模型，不改真实config.yaml、
默认selector或模型profile，不导入benchmark的数据库/完成/进展补强。历史benchmark
原型和全部74工件保留，生产模块不得导入benchmarks。

只接受可文字区分的被选完整候选；其余沿原视觉路线。不增加参数猜测、候选过滤、
硬错误重试或Box坐标执行。独立观察不足仍停止，唯一性不等于动作正确。显式
visual-model继续声明图片接收方，调用者可用text-only scope拒绝图片。

本片仅做受控开发接线与假HTTP/原生边界/真实Chromium验证，无新增真实API、个人桌面
或真实用户写入实测。中性/误导命名拒绝泛化条件项仍在backlog，未触发也不移除，
不能把此前带提示词的负例当安全认证；生产原始DOM/AX效果尚须后续受控体验核验。

## 步骤

1. TDD验证显式工厂装配（浏览器/原生）、默认/旧jev-vision保持；复制最小策略到
   插件独立模块，以公共行为复用原型测试证明候选/绑定/接管/硬停止契约一致。
2. 现有Runner+真实Chromium用例新增模式，验证decision/visual profile、同任务
   路由与账本/资源清理；已有原生Jev→视觉→Jev硬停止矩阵覆盖新生产类，不引入
   benchmark状态或私有oracle，补中性/误导标签的接线保护用例（不冒充模型质量）。
3. 更新插件README、backend开发/测试说明、主计划和索引，提供可复制的显式配置
   示例与作用范围。通过全部适用验证及最多3轮独立review-and-refactor后结案。

## Tests

TDD工厂用例先因未知selector失败2项，接入后2项通过。最终定向96项通过，
470项未选；全部5个改动Python文件的pyright为0错误。

在现有test_plugin.py、test_dom.py、test_vision.py增量覆盖，无新feature文件。
实际SDK仅替换外部HTTP；原生OS边界按既有fixture替换，DOM用实际Chromium。
检查工厂无副作用、旧默认不变、完整候选、被选动作区分、同绑定视觉接管、缺输入/
撤权/不完整或过期观察/未知用量与效果/图片拒绝、恢复上限及清理。原冻结原型不改。

## 验证记录

- 后端完整回归6769通过、1跳过，启用Chromium及既有两产品资格环境，耗时2042.81秒。
  使用uv run --no-sync pytest -q -x；真实产品配假模型HTTP，无新增收费实测。
- E2E首轮底层91项Chromium测试通过，但Cucumber仍断言旧88项而失败；同步为91后，
  全套24场景/95步骤通过。未新建feature文件。实际本地Sherpa、回环模型和隔离DB，
  无外部Python socket或真实凭据；finally恢复原开发后端，前后端reload无错误。
- web lint、tsc -b --noEmit、后端及CLI ruff、全部改动Python的pyright通过；协议及
  生成物未改，protocol-sync不适用。文档检查及完整任务diff空白检查通过。
- 默认config.yaml与基线6ee51ccdf775c1664ca4706aa4517060698b1ad7的SHA相同；
  原74工件全部哈希不变，历史benchmark源码未改，生产策略不导入benchmarks。
- 功能f12f406e、说明cce2496a、E2E断言195f9818分别签名提交。
- 第1轮独立review-and-refactor审查覆盖完整任务差异，无可操作或遗留问题、无修复，
  按规则立即结束。审查者独立复跑96项通过，文档及完整diff检查通过；结案迁移与
  链接由协调者自检，不另称为独立审查。主计划继续开放，中性命名条件项已在backlog，
  本片未触发、未移除，不追加真实模型或真实写入验收。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint。
2. cd web && npx tsc -b --noEmit。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/。
4. cd backend && uv run pytest（启用既有Chromium/两产品资格环境）。
5. cd backend && uv run pyright <全部改动Python>，不加type-ignore。
6. cd cli && uv run ruff check src/ tests/。
7. 检查tmux tank前后端reload错误，空输出为通过。
8. cd test && pnpm test，本地Sherpa/回环模型/隔离DB，finally恢复原服务。
9. python3 scripts/check_docs.py、git diff --check、旧74工件和默认config SHA、签名及
   测试/审查证据。未改变历史benchmark来源或追认历史实验成绩。
10. python3 scripts/check_protocol_sync.py；协议及生成物未改则不适用。
