> 状态：已完成（2026-10-23：已有96项离线路由/开销分析、742成员归档及两轮审查完成，无遗留问题；第2轮为审查者修正文案后的自检。无新模型调用、运行源码未改；候选等价准入假设交回主计划，未作采用确认。）

# 真实96项校准的路由与开销分析

## 范围与验收

承接[主计划](../active/computer-use-jev-vision.md)，先使用已有96项真实执行回答linkding与
sqlite-web的路由和时间差异。输入仅为[已完成校准](../../research/jev-calibration-route.md)
归档，SHA256为11d5c73c56b1637349fa5984d5e1243e0d08e9442654d9b0e3c3c80a2bb1a972。
保留24个seed、两启动条件、V/JT和80正例/16负例；不与第6槽停批新批次混合，
不重跑、不改旧结果、阈值或生产默认，不修SDK或扩大任务范围。

## 步骤

1. 逐字节验证输入归档/清单，读取result、冻结、SDK捕获和归档版路由代码语义。
   不导入执行器或模型客户端，读取阶段禁用网络和dotenv凭据。
2. 输出96任务、337调用及配对/分层数据，重算质量、图片、Jev/视觉、弃权/接管、
   直接视觉绕过、SDK耗时与任务总耗时；负例时间单列。验证call ID、事件/usage/
   回执一致。SDK耗时含网络/服务；总耗时减SDK只记作未细分其余时间，不冒称纯宿主
   或模型内部推理时间，不把重叠task_execution跨度相加。
3. 依产品、冷/预热、正常/恢复及实际路由路径拆分，找支持和反例；路径子集为
   事后描述，不能当随机分配或独立因果效应。形成可验证的准入假设及小规模新测量建议。
4. 提供单文件交互Canvas与研究证据，所有数据内联、无网络；补充可复算归档。
   完成项目code-reviewer最多三轮review-and-refactor及签名提交，再结案。
   原66旧工件及原有Canvas保持，当前分析不是正式采用/安全确认。

## 完成结果

[研究记录](../../research/jev-calibration-route-analysis.md)已区分文字准入覆盖、
任务/SDK边界/其余时间及事后路径子集。全局重复候选谓词与336路由逐项一致；
SQLite仅Retry调用Jev，Linkding编辑/Retry使用文字。第二脚本核96任务/337事件、
72分层/48配对/52筛选及36源；Canvas内联数据及定向TypeScript检查通过。
独立审查另核194组场景/路径配对筛选，11份规范输出重生成逐字节一致；
R1摘要分母文案已修，规范数据不变，第2轮为审查者自检，无新增或遗留问题。
[研究记录](../../research/jev-calibration-route-analysis.md#验证与交付)包含归档、清单及SHA；
原66旧工件保持。后续假设验证由主计划承接，不计作本轮已实施行为。

## Tests

- 输入SHA/硬链接解析和全部所选成员SHA核验；96行/24seed/48配对、337调用/
  279图片、58Jev及4412681已知tokens等基线回算，不从报告抄数作新测量。
- 每调用开始/完成唯一关联、路径互斥分类、图片/文本边界、时间计量与分组加总；
  两启动条件保留在seed内，正负例不混算。独立第二脚本复算导出数据及筛选分母。
- Canvas仅引用新规范数据，指定文件TypeScript检查、无fetch/凭据/模型调用；
  筛选保持配对并清楚标注样本量、范围、时间和描述性限制。
- 本片只改docs/及独立分析Canvas/静态证据，不改运行行为或应用测试，使用docs-only
  例外；分析校验及Canvas类型检查仍须通过。

## Verification Checklist（最终步骤）

1. cd web && pnpm lint，应用源码未改不适用。
2. cd web && npx tsc -b --noEmit，应用源码未改不适用；另查新Canvas。
3. cd backend && uv run ruff check core/src/ core/tests/ plugins/，运行源码未改不适用。
4. cd backend && uv run pytest，运行源码未改不适用。
5. cd backend && uv run pyright <改动Python>，运行/测试Python未改不适用。
6. cd cli && uv run ruff check src/ tests/，CLI未改不适用。
7. 检查开发server reload错误，应用未改不适用。
8. cd test && pnpm test，应用未改不适用；不向远端ASR发送音频。
9. python3 scripts/check_docs.py、完整git diff --check、旧66工件SHA、输入/分析/
   Canvas核验及签名检查，必须通过。
10. python3 scripts/check_protocol_sync.py，协议/生成物未改不适用。
