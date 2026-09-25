# M8 收口：采用决定、回退与关档（2026-09-25）

本报告是[适配与定位计划](../../../../../docs/plans/done/computer-use-adaptation-and-grounding.md)
的固定收口报告：版本/manifest、请求与测试总数、失败分母、按布局/任务的配对结果、
未知项、成本/延迟与失败原始记录索引。除本文汇总外不新增模型请求或桌面动作。

## 1. 采用决定：保留生产基线，不切换默认模式

**决定**：生产默认保持为 A——`computer_use` profile
（`qwen3.7-flash-2026-07-15` @ DashScope compatible-mode）+
[agents/computer_use.md](../../../agents/computer_use.md)（无 `grounding` frontmatter，
一体规划定位、legacy 归一化坐标）。该默认在 M1–M8 全程未被修改。

依据（三层证据一致指向）：

1. **静态首轮筛选门槛无人通过**（[M3 holdout](../20260921-m3-holdout/README.md)）：
   Max bbox 与 GPT point 正例 96/96（满足 ≥95% 命中、p95 2.29/1.82 px ≤15 px、
   无 >50 px 正例偏移），但同名歧义拒绝均 **0/16**、可执行误报 12/16、14/16、16/16
   ——违反"无目标样本不得误报可执行点"；Qwen3.7 基线正例仅 57/96。
   门槛在 M0 冻结，结果后未调整。
2. **真实严格配对任务候选不优于基线**：M6 宽任务集（13 任务 × 3 轮 × 两臂）
   **strict A 10/36 vs C 5/36**（含 smoke 13/39 vs 8/39；并入 calc-open 后
   A 11/39 vs C 6/39，p≈0.19），C 每任务耗 **1.7–2× token** 且 3 次预算停止全在
   C 臂；M5 calc-open 单任务上 split（C+D 8/12）显著优于 B-combined（0/6，
   p=0.011）且与 A 不可区分（p=0.43），但该优势未在宽任务集复现。
3. **AX 分支条件性暂缓**（M7）：机制闭环成立但选择精度是瓶颈，成绩持平或更差
   且成本更高，不采用为默认。

结论按计划第 4 项要求如实表述：**全部候选劣于或不优于基线 → 保留基线并归档
未解问题；不宣称点击根因已解决**。主要未解问题：定位模型单位/参照系遵从
（pixels 契约下系统性误发归一化值）、窗口矩形纵向估计偏小、粘贴路径不留表达式行、
AX 选择器 off-by-one、子代理链路无历史压缩（见 §8 未知项与 backlog）。

**回退**：M2 image 坐标、M4 分离、M5 一体适配、M7 AX 均为 agent frontmatter
显式 opt-in（`grounding:`）；删除该键即回到原一体模式。生产 agent 从未启用，
legacy `normalize_point` 宽容解析与旧 region/crop 语义全程保留，旧模式一键回退成立。

## 2. 确定性测试（转换/协议/取消/预算/清理）

- 全量 backend **5116 passed / 1 skipped**（2026-09-25 收口运行），含：M2 真实像素
  crop/缩放/frame 逆变换回归（1x/1.5x/2x、2x/3x crop、非整尺寸、窗口原点、
  越界/旧帧/跨会话拒绝）；M3/M5 协议解析（数组/字符串/重复字段/截断拒绝、
  三提供方 SDK 请求回放）；M4 取消/截止时间/重定位上限；M5 请求准入与
  SpendLedger 预留/结算/持久化（fsync、进程退出）；M6 agent 预算强制与
  原生输入清理（正常/异常/超时/取消）；M7 AX 枚举/选择/派发边界。
  旧 N2 与 SDK（yutori 0.9.29 fake transport）回归包含在内——本轮共享代码
  变更（粘贴配对、TIS 子进程、window_id 接缝、AX schema、非法 JSON 可恢复）
  未破坏既有 N2 路径。
- 物理停止/清理：[M6 stop-acceptance](../20260924-m6-stop-acceptance/README.md)
  五场景（planner/locate 在飞取消、key-hold、batch、drag）返回后严格 10 秒
  零事件、按键/鼠标释放、资源可复用，全部通过（本地回环 mock）。
- 清理失败分母：M6 calc 12/12 + task 78 trial + M7 live3 9/9 `cleanup=confirmed`，
  清理失败 **0**；两次外层恢复 `applications_restored=false`（killall Finder
  自愈重启身份误报）已逐项核查为 launcher/事后核对均确认桌面完整，记录在案。

## 3. 版本与 manifest

- 关档 HEAD：`b86d290e`（M7 收口提交）；本报告为纯文档提交。
- 基线冻结：[M0 manifest](../20260919-adaptation-m0/README.md)（revision、主屏
  几何、权限、配置模型/端点、最终 system 与 12 工具定义）、
  [M0 准备报告](../20260920-adaptation-m0-preparation/README.md)（126 历史 trial
  索引、64 holdout 布局）。M0 首项缺口"端点实际 model/provider 预检"由
  [M3 端点预检](../20260920-m3-preflight/README.md)补齐（五模型请求/响应型号归档；
  仅 OpenRouter 返回 provider=OpenAI，其余响应无 provider 字段）。
- 采用门槛/分母/失败分类冻结于看 holdout 结果之前（M0）。
- live 批次冻结链（每批预检通过、漂移拒绝）：M5 `pixels-unified`/`normalized`
  系列 → M6 `calc`/`tasks` → M7 `runtime3`。
- 生产默认（config `computer_use` profile、agent 定义、评分 revision
  `trial-token-gui-grounding-v5`、`calc-evidence-v1`）与计划开始时一致。

## 4. 请求与 token 总量（含失败分母）

### 静态赛道（合成/受控图，不发真实桌面截图）

| 批次 | 请求 | tokens | 说明 |
|---|---|---|---|
| M1 提示 A/B | 12 | 73,940 | 两组均 0/6 命中 |
| M3 端点预检 | 16 | 26,398 | 五模型 × 两协议 |
| M3 调参筛选（schema/thinking/image/status/唯一匹配） | 144 | 413,208 已知 + 26,000 预留 | 含一次 402 余额失败（unknown 用量保留） |
| M3 holdout | 384 | 715,802 | 544 预检+筛选+holdout 额度至此用尽 |
| M5 静态坐标探针 | 49 | ≈161,000 | 48 有效 + 1 脚本 bug 丢弃（证据保留） |
| M5 接口矩阵 | 60 | 149,914 | 3 模型 × 2 单位 × 2 取景 × 2 帧 |
| **静态合计** | **665** | **≈1.57M** | 544 额度未重置；额外批次各自列明理由 |

### 真实桌面 live（逐批授权，发送前复核 initial.png）

| 批次 | 轮数 | 请求 | tokens | strict 结果 |
|---|---|---|---|---|
| M5 pilot 单轮 ×12（六臂 + 复跑/对照） | 12 | 143 | 2,570,349 | 2/12（B-host-only、B-pixels-only） |
| M5 core pairs attempt1（材料缺陷，无效证据） | 12 | — | 1,032,056 | 0/12（范围拒绝 99 次） |
| M5 core pairs attempt2–5（pixels→消歧→normalized→6 对） | 48 | — | 9,610,305 | 3/12、3/12、6/12、5/12 |
| M5 框架配对（A vs A-control，6 对） | 12（10 有效） | — | 1,823,108 | A 1/4 vs A-control 1/4；2 对 infra 中止 |
| M6 calc-pairs（4 臂 × 3，预算强制） | 12 | 183 | 1,889,843 | 5/12（A1 B2 C1 D1） |
| M6 task-pairs（13 任务 × 3 × 两臂） | 78 | 1,082 | 11,749,659 | A 10/36 vs C 5/36（smoke 13/39 vs 8/39） |
| M6 长历史专项（A/C 各 1） | 2 | 50 | 626,560 | 均 budget 停止（压缩机制缺失） |
| M7 AX live1–3（三臂 × 3 × 3 批） | 27 | 360 | 4,515,964 | A 1/3、AX-quartz 1/3、AX-press 0/3（live3） |
| **live 合计** | **203** | **≈1,818** | **33,817,844** | — |

- attempt2–5 token 合计：2,257,522 + 2,493,751 + 2,305,835 + 2,553,197 = 9,610,305；
  core 五次尝试共 10,642,361。M5 core 请求计数未在 README 汇总（逐 trial 见各
  attempt 目录）；其余批次请求数均为实际 HTTP 计数。
- **全计划总消耗 ≈ 35.4M tokens / ≈2,483 次模型请求**，费用 unpriced
  （见 §7）；全部批次零自动重试、HTTP 失败/未知 usage 计入上限并停批。

## 5. 按布局/任务的配对结果

### 静态（按布局配对，分母 = 独立布局）

- M3 holdout（64 布局 × 3 配置 × 2 重复）：正例命中 Qwen3.7 57/96、Max bbox
  96/96、GPT point 96/96；缺失拒绝均 16/16；**同名歧义拒绝均 0/16**；条件于
  合法正例的中心误差 p95 = 469.68 / 2.29 / 1.82 px。Max/GPT 正例配对提升
  +40.63 pp，95% CI [+28.13, +54.17] pp（48 布局聚类）。
- M5 接口矩阵（有效 n=8/格，真实帧）：`full-point` 均值 flash 2.7 / max **1.1** /
  gpt **1.1** px；`full-pixels` flash 5.4 / max **375.1**（2/3 误发归一化值）/ gpt 0.7 px；
  gpt-5.5 四组合全中（0.7–1.2 px）。**单位匹配模型原生习惯是关键因子**，
  强模型使单位问题消失。
- 通用像素自动评分：**unknown**（Vision OCR 对孤立数字误识别，保留人工/AX 核验）。

### 真实任务（按任务配对，轮转先手）

- calc-open（M5 合并每臂 6 轮）：A 3/6、**B-combined 0/6**、C 4/6、D 4/6；
  split(C+D) 8/12 vs B-combined 0/6 **p=0.011**；split vs A p=0.43。点击归因：
  C 17/17、D 15/15 全部命中目标键（失败为流程未走完）；B-combined 0 命中 /
  23 窗内空点（纯落点问题）。
- M6 calc（每臂 3 轮，预算强制）：A 1/3、B-combined 2/3、C 1/3、D 1/3；
  零坐标/定位错误（失败 = 流程 5 / 输入语义 1 / 粘贴路径 1）。
- 13 任务宽集（A vs C 各 3 轮）：**A 10/36 vs C 5/36**；逐任务区间与失败分类见
  [task-pairs 报告](../20260924-m6-task-pairs/README.md)（每任务 n=3，异质任务，
  不作显著性宣称；编辑器/文件/拖拽类全败是能力现状如实记录）。
- 框架效应（A vs A-control，配平 4 对）：1/4 vs 1/4，未检出框架效应。
- AX（M7 live3，n=3/臂）：A 1/3、AX-quartz 1/3、AX-press 0/3；AX 臂 token
  成本更高（225–245k vs 181k）。live1 整批无效（窗口绑定设计缺陷，已修复），
  live2 部分有效，均已按无效/有效分别归档，不混入结论分母。

## 6. 失败分类汇总（M6 第 6 项口径，78 trial 宽集）

流程未走完 48、预算停止 3、窗外点击（门禁拦截零派发）5、应用启动失败 1、
超时 0、清理失败 0。识别/定位错以门禁拦截形式出现且零派发；无变换错、
无陈旧观察逃逸。M5 calc-open 补充分类：输入语义（运算符被忽略）与粘贴路径
（求值但不留表达式行）。全部以独立 validator/AX 判定，模型自报不替代应用结果。

## 7. 成本与延迟

- 费用状态 **unpriced**（record-only 批次金额字段为占位）。已核价部分：
  `qwen3.7-flash-2026-07-15` 百炼国际站 $0.030/$0.130 per M（0–32K）；本项目
  端点为中国内地、`qwen3.8-max-2026-09-02` 未列入价目表 → M5 core 五批
  9.61M tokens 估算 **$0.30–15.87**（内地口径 ¥23.80 上限），单次配对批次
  成本为**个位数美元**量级。其余批次未单独估价；精确账单需控制台数据。
- 延迟/用量与质量同表展示（各报告）：pilot wall 20.6–126.3 s；M6 calc 每臂
  均值 150–163k tok；task-pairs A 均值 60k–154k tok/任务 vs C 1.7–2×；
  B-combined 在 calc-open 上耗 ~2.4× token（359k vs C/D ~150k）。历史图像
  重复输入成本已实际观测（单 trial 11 个图像哈希累计出现 86 次）。

## 8. 未知项（不冒充已解决）

1. **通用截图像素自动评分**：unknown（M1 保留人工/AX 核验口径）。
2. **I09 首次校准异常根因**：M6 重验 9/9 误差 0 未再现，仅计本批通过；根因
   不补写。
3. **I11 服务端预处理/权重内部机制**：证据仅到服务输出边界（单位习惯、批间
   方差已记录为可识别差异）。
4. **实际账单**：全部 live 批次 unpriced；402 历史失败用量保留 unknown+预留。
5. **批间方差来源**：同契约同模型批间通过率 3/12→6/12，未归因。
6. **多屏/动态分辨率/高频压测**：M2 几何失效拒绝已测；扩展验收在 backlog。
7. **原生协议/专用定位模型（UI-TARS、Responses computer）**：未测试，backlog。

## 9. I01–I11 逐条对照

| 编号 | 问题 | 处置 | 状态 |
|---|---|---|---|
| I01 | 提示职责冲突 | M1 修复 + 离线 HTTP 回归；A/B 0/6 无定位收益；完整任务效果 M5/M6 验证 | **已修复**（正确性保留，无效果宣称） |
| I02 | 输入语义与评分 | 显式 paste 模式、IME/Shift 物理键码修复、calc-evidence-v1 分轨评分 | **已实现/已验证** |
| I03 | 截图像素与当轮结果证据 | 受控图像独立核验 + SDK 本地回放；真实闭环 M6；通用自动像素评分 | 已实现；**像素自动评分 unknown** |
| I04 | 全局尺寸缓存、crop 依赖模型还原 | M2 Observation/宿主还原；legacy 默认保留 | **已实现/已验证** |
| I05 | 模型适配 | M3 五模型共享 adapter + 544 次静态；无候选过完整门槛 | **已实现；未采用** |
| I06 | 规划定位分离 | M4/M5；calc-open split 显著优于 B-combined（p=0.011）但宽任务集 A 10/36 > C 5/36 | **已实现/已验证；不采用为默认** |
| I07 | AX/视觉解析辅助 | M7 机制闭环成立；选择精度瓶颈；两触发项移交 backlog | **条件性暂缓（已移交）** |
| I08 | 效果验证、长历史、跨应用、资源清理 | M6 六项完成；78 trial 跨应用、停止 5 场景、清理 0 失败 | **已验证**；压缩机制缺口移交 backlog |
| I09 | 早期真实校准异常 | M6 重验 9/9、误差 0，未再现 | **未再现（本批）；根因 unknown** |
| I10 | 多屏、动态分辨率、高频压测 | 几何失效拒绝有测试；扩展验收条件触发 | **部分；其余在 backlog** |
| I11 | 服务端预处理/权重归因 | 证据到服务输出边界；可识别差异已记录 | **unknown（保持）** |

§2.3 复用核对：N2 三份历史 benchmark（33/42、strict 4/36、7/42）按原口径保留
为参照，未重跑全套三路；共享代码变更经含旧 N2/SDK 回归的全量测试覆盖。
R 项核对：A/B/C/D 同尺比较已完成（M5/M6），未新增 N2 请求。

## 10. 失败原始记录索引

静态：[M3 holdout](../20260921-m3-holdout/README.md)（384 原始响应 + 逐布局评分）、
[接口矩阵](../20260924-m5-interface-matrix/README.md)。
live：[pilots 汇总](../20260924-m5-pilots-summary/README.md)、
[core pairs](../20260924-m5-core-pairs/README.md)（五批对照 + 归因）、
[框架配对](../20260924-m5-framework-pair/README.md)、
[M6 calc](../20260924-m6-calc-pairs/README.md)、
[M6 tasks](../20260924-m6-task-pairs/README.md)（analysis.json 逐 trial 分类）、
[M6 长历史](../20260924-m6-longhistory/README.md)、
[M7 live1](../20260925-m7-ax-live1/README.md)（无效批证据）、
[live2](../20260925-m7-ax-live2/README.md)、[live3](../20260925-m7-ax-live3/README.md)。
每个 trial 目录含 report/trace/spend 与逐请求 usage；截图与原始 HTTP 二进制仅
本地保留，文本证据入库。历史异常（TextEdit AppleEvent 间歇超时、Carbon TIS
SIGTRAP、killall Finder 恢复误报）均按发生时记录保留，修复以先红后绿回归覆盖。
