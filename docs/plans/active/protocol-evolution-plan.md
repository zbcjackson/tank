# Tank 私有协议演进计划（Protocol Evolution Plan）

> 状态：P0-1、P0-2、P1-1 已落地（2026-09-02）。P1-2 / P1-3 未开始。
> 起草日期：2026-09-01。关联文档：[s2s-comparison-and-improvement-plan.md](../done/s2s-comparison-and-improvement-plan.md)（P3 结论的落地）、[vad-smart-turn-design.md](../../design/vad-smart-turn-design.md)。
> 触发背景：Tank 将来要远程部署在服务器上，连接远程操控的机器人和客户端。远程化对协议提出三个硬前提——认证、弱网韧性、可演进性——当前协议一项都不具备。
> 本文所有代码事实均核对自实际代码（文件行号见引用）。

---

## 1. 背景与动机

### 1.1 决策上下文

对 s2s（HuggingFace speech-to-speech）的 OpenAI Realtime 兼容层调研（见 s2s 计划 P3）得出的战略结论：

- **私有协议是唯一第一公民**，持续发展；
- **Realtime 端点不立项**，改为一条触发条件：出现第一个真实外部消费者（第三方客户端/机器人）时，作为边缘网关立项，建立在演进后的私有栈（同一管线池 + 同一认证）之上；
- 决策规则一句话：**传输与能力类改进（Opus/热配置/认证/resume）进私有协议；只有生态兼容需求才开 Realtime 端点。**

远程部署场景恰好全部落在前一类：机器人/客户端均为自研，接入 Realtime 是纯成本（实现 30+ 事件却拿不到生态收益），还倒贴 base64 膨胀税。

### 1.2 远程化硬前提

| 前提 | 现状 | 差距 |
|---|---|---|
| 认证 | 无（`router.py` 全文无 token/auth，LAN 信任模型） | 远程暴露前必须补 |
| 弱网韧性 | 裸 PCM over TCP，丢包触发队头阻塞 | 需要 Opus 压缩 + （视实测）UDP 传输 |
| 可演进性 | 无版本、无能力协商、契约无单一事实源 | 见 §2.4，问题已经从"风险"变成"事实" |

---

## 2. 现状盘点（代码事实）

### 2.1 消息集清单

**入向**（Client → Server，`api/router.py:569-612`）：

| 帧 | 格式 | 语义 |
|---|---|---|
| 音频 | **纯二进制** Int16 PCM，零封包 | 服务端按 assistant 配置的 capture rate 重采样适配、stereo 自动 downmix（`router.py:579-584`）——客户端无需精确匹配采样率 |
| `{type:"signal"}` | JSON | `interrupt` / `wake`（触发服务端会话压缩，回 `conversation_ready`）/ `end_of_utterance`（PTT 显式结束）/ `disconnect`（`signal_handlers.py` 注册表） |
| `{type:"input"}` | JSON | 文本输入，metadata 携带 `user_id`、`attachments`（文件/图片上传） |

**出向**（Server → Client）：

| 类型 | 语义 |
|---|---|
| 二进制（下行 8 字节头 magic `0x544B` + rate + channels，仅设备端消费） | TTS PCM |
| `signal` | `ready` / `processing_started` / `processing_ended` / `conversation_ready` / `error` |
| `transcript` | ASR 结果，`msg_id` 支持原地更新（turn reopen 修订同一 `msg_id`） |
| `text` | LLM token 流，`msg_id + turn` 定位流式 step |
| `update` | `THOUGHT` / `TOOL_CALL` / `TOOL_RESULT` / `APPROVAL`（`core/events.py:26`） |
| `attachment` | 助手发送的媒体（图片） |
| `channel_notification` / `conversation_metadata_updated` | 频道消息 / 会话标题等元数据 |

### 2.2 做得好的（保留）

1. **极小正交**：2 种帧、8 个消息类型。ESP32 固件协议层几百行 + 19 个 native 测试用例即可完整实现——协议够简单的最好证明；
2. **服务端宽容**：入向音频由服务端重采样适配（`router.py:583`），适配责任放在能力更强的一端；
3. **扩展点已存在**：signal 走 `@register` 注册表分发，新信号零改动；三端客户端对未知类型均"warning + 忽略"——forward-compatible 行为已天然存在，只是没成文；
4. **富通道**：update/attachment/metadata 承载 Realtime 标准事件集表达不了的 UI 语义（thinking、工具卡片、审批、图片附件、turn reopen 原地更新）；
5. **测试文化**：三端各有协议测试（web E2E、cli pytest、device native）。

### 2.3 问题清单（按风险排序）

| # | 问题 | 证据 |
|---|---|---|
| W1 | **契约无单一事实源**：4 端 × 3 语言各自手写解析，语义活在"共识"里。漂移已发生：`backend/ARCHITECTURE.md` 描述入向音频为 `{"type":"audio","data":"<base64>"}`，代码里不存在（`router.py:572` 是纯 binary 分支，连 sample_rate 字段都没有），与根 ARCHITECTURE.md 互相矛盾 | 文档 vs 代码 |
| W2 | **Python 内部两端已分叉**：`cli/src/tank_cli/schemas.py` 是手抄副本，`MessageType` 缺 `ATTACHMENT`/`CHANNEL_NOTIFICATION`/`CONVERSATION_METADATA_UPDATED` 三个值，信封缺 `speaker`/`attachments` 字段 | `cli/schemas.py`（30 行）vs `backend/api/schemas.py`（56 行） |
| W3 | **信封是扁平袋**：`WebsocketMessage` 8 个可选字段全类型共享（`speaker/is_user/is_final/msg_id` 只对部分类型有意义）；`metadata: dict[str, Any]` 是无类型逃生舱，语义全靠约定 | `api/schemas.py:41-55` |
| W4 | **无版本、无能力协商**：加 Opus/resume 时没有握手机制 | — |
| W5 | **无认证** | `router.py` |
| W6 | **无 resume 语义**：重连靠 session_id（设备 MAC 派生）恢复会话历史，在途 turn 状态全丢 | device/FEATURES.md |
| W7 | **构造点发散**：20 处 outbound 消息构造散在 5 个文件（signal_handlers 8、router 8、audio_service 2、jobs/delivery 1） | `grep "WebsocketMessage("` |

W1 + W2 是同一根因：**契约只存在于四处手写副本 + 过时文档中，没有任何机器可校验的单一来源。**

---

## 3. 与 Realtime 协议的对比结论

| 维度 | 私有协议现状 | 私有协议+演进（本计划） | Realtime |
|---|---|---|---|
| 带宽（音频） | ✅ 裸 PCM | ✅✅ 协商 Opus（8-10×） | ❌ WS 模式 base64 +33%（Opus 锁死在 WebRTC 模式，ESP32 上不了） |
| 弱网韧性 | ❌ TCP 队头阻塞 | ⚠️ Opus 缓解，UDP 缺（视实测） | ✅ WebRTC/UDP |
| 功能表达（thinking/卡片/审批/附件/reopen） | ✅ 全有 | ✅ 全有 | ❌ 需扩展事件，服务端工具审批模型冲突 |
| 热配置 / 上下文注入 | ❌ 无 | ✅ 补齐（§5.4） | ✅ 原生 |
| 外部生态接入 | ❌ | ❌（仍私有） | ✅ 唯一强项 |
| 自研新端成本 | ✅ 极低 | ✅ 低（+握手） | ❌ 30+ 事件，无生态收益 |
| 认证 / 版本 / 续传 | ❌ 全无 | ✅ 补齐 | ❌ 同样没有（Realtime 不替你解决） |
| 演进控制权 | ✅ 完全自主 | ✅ 完全自主 | ⚠️ 跟随 OpenAI 演进 |
| 维护面 | 1 套协议 | 1 套协议 | 2 套协议 + 映射层 |

**结论**：Realtime 相对私有协议的实质优势只有两项（WebRTC 传输、生态兼容），均可通过私有协议自身演进或触发条件式立项覆盖；而私有协议的二进制效率、富通道、服务端工具安全模型、reopen 语义是 Realtime 表达不了的。

---

## 4. 核心设计决策：契约剥离

> 即：协议应否显式地从业务代码中剥离出来，成为独立被各端引用的一层？

### 4.1 三个选项

| 选项 | 内容 | 问题 |
|---|---|---|
| A. 现状 + 规范文档 | 只写协议 spec 文档，代码不动 | 文档就是 W1 的失败现场——没有强制力，漂移继续 |
| B. **契约包（本计划采纳）** | 协议 schema + 构造工厂剥离为叶子包 `tank_protocol`，后端/CLI 直接依赖，web/device 经生成物对齐 | 需要一次重构 + CLI 依赖接线 |
| C. 全量客户端 SDK | 契约包 + TS 生成包 + C++ 移植库 | 过度工程：8 个消息类型的协议不配拥有一条 C++ 代码生成流水线；device 的 golden-frame 测试已够用 |

### 4.2 决策：剥离**契约**，不剥离**传输**

**采纳选项 B，边界划在"wire 契约"与"传输/会话逻辑"之间：**

```
                    ┌──────────────────────────────────┐
                    │  tank_protocol（新叶子包）          │
                    │  · MessageType / UpdateType 枚举   │
                    │  · WebsocketMessage 信封模型       │
                    │  · 按类型 payload 校验模型          │
                    │  · 信号名常量 / 构造工厂函数         │
                    │  · 握手 / 能力协商模型（§5.1）       │
                    │  · JSON Schema 导出                │
                    │  依赖：仅 pydantic。零后端内部依赖。  │
                    └───────┬──────────┬───────┬────────┘
                            │          │       │
              import（uv     │  schema  │  JSON │ golden-frame
              workspace 依赖)│  生成    │ Schema│ 夹具生成
                            ▼          ▼       ▼
                     backend/core    web     device
                     cli          （CI 校验） （native 测试）
```

**消费者各取所需：**

| 端 | 消费方式 |
|---|---|
| backend/core | uv workspace 依赖，直接 import；20 处构造点收拢为工厂函数调用（修 W7） |
| cli | **删除手抄的 `schemas.py`**（修 W2），uv path/workspace 依赖 `tank-protocol` |
| web | 包构建时导出 JSON Schema → `json-schema-to-typescript` 生成 `web/src/types/protocol.ts`，CI 校验与包版本同步 |
| device | 从同一包生成 golden-frame 夹具（每种消息类型一条真实 wire 帧），进 `test/test_native` 套件——C++ 解析器对样例帧断言，不共享代码 |

**明确不进包的东西**（它们在四端合法地不同）：

- 传输层（WebSocket 连接管理、Tauri 插件分支、esp_websocket_client）
- 重连/退避策略、会话生命周期逻辑
- 业务处理（VAD/ASR/Brain 等管线内容）

### 4.3 wire 兼容承诺

**信封 wire 形状不变**（`{type, content, speaker, is_user, is_final, msg_id, session_id, metadata, attachments}`）。payload 类型化发生在**代码模型层**（按类型的校验模型 + 构造工厂），不发生在 wire 上——四个已出货客户端不做任何破坏性迁移。扁平袋问题（W3）通过"按类型 payload 校验模型"在收发两侧校验缓解：wire 仍是宽松信封，但每侧知道每种类型合法的字段集，违反即告警。

### 4.4 与 `tank_contracts` 的关系

不合并。`backend/contracts/tank_contracts` 是**插件引擎 SDK**（ASR/TTS/speaker ABC，受众是 plugin 作者）；`tank_protocol` 是**客户端 wire 契约**（受众是四个客户端）。受众、依赖方向、变更节奏都不同。两者同为 uv workspace 成员，模式一致（参照 `tank-contracts = { workspace = true }`）。

### 4.5 为什么值得做（收益对账）

- W1/W2（已发生的漂移）从"靠人肉同步"变为"类型错误/CI 失败"——backend 和 cli 两个 Python 端获得编译期契约保障；
- W7 收拢：出向消息只剩一种构造路径，改信封不会漏；
- §5 的一切演进项（握手、Opus、热配置）都只需要改一个包 + 各端消费，而不是四端各改各的；
- JSON Schema 导出让 web 的 TS 类型和 device 的 golden frames 从同一来源派生，**这是四端对齐的唯一现实机制**（web/device 无法 import Python）。

---

## 5. 协议演进项

### 5.1 版本与能力协商（握手）

- `signal: ready` 增加 `protocol: <int>` 与 `capabilities: ["opus", "resume", "config", ...]`；
- 客户端首帧可回应声明采用的能力（如 `{"type":"signal","content":"capabilities","metadata":{"enable":["opus"]}}`）；
- **字段缺失 = 旧客户端 = 现行为**，完全向后兼容，无需协商也可工作；
- 协议版本号 = `tank_protocol` 包版本，单一来源。

### 5.2 认证（远程部署前置项，可最先独立做）

- 连接级 token：WebSocket URL query `?token=` 或首帧 `{"type":"signal","content":"auth"}`；
- 服务端校验失败即断连；token 来源沿用 `.env` secret 模式；
- 与协议版本正交，旧客户端在 LAN 下不携带 token 时按现有配置放行（可配置强制）。

### 5.3 Opus 编码协商

- **按能力协商切换，不全局切换**：LAN 继续裸 PCM（零开销），远程/弱网会话协商切 Opus；
- 上行：客户端声明 `opus` 能力后改发 Opus 帧（服务端 opus → PCM 解码入管线）；下行同理；
- 服务端解码/编码走 libopus 绑定；设备端 ESP32-S3（双核 240MHz + PSRAM）可承载 16kHz 语音实时编解码，内存占用需在 device 侧实测后定案；
- 这是 Realtime 给不了的灵活性（它的 WS 模式锁死 base64 PCM）。

### 5.4 热配置与上下文注入（补功能缺口）

- 新增 `config` 消息类型：会话中途改 instructions / voice / VAD 参数（deep-merge，仿 s2s `session.update` 语义）；
- 新增上下文注入：向对话塞内容**不触发生成**（RAG 结果、笔记），对应 Realtime `conversation.item.create` 能力；
- 均为 additive 变更：服务端 `@register` 模式 + 客户端忽略未知类型的既有行为使成本极低。

### 5.5 演进规则（成文，进 `tank_protocol` README）

1. **Additive-only**：新增类型/字段允许，改语义/删字段必须升协议大版本；
2. **未知必须忽略**：客户端遇到未知类型/字段 warning + 忽略，从民间行为升格为契约；
3. `metadata` 键收进 schema 文档，不再新增"只有一端认识"的隐式键；
4. 三端 golden/类型生成物与包版本不一致 = CI 失败。

---

## 6. 暂缓项与触发条件

| 项 | 暂缓理由 | 触发条件 |
|---|---|---|
| WebRTC 传输 | Opus-over-WS 已拿 80% 收益；ESP32 端 aiortc 对等物极重 | 远程实测 Opus-over-TCP 仍因队头阻塞卡顿；届时 WebRTC 仅作传输层挂入（JSON 消息走 data channel，私有消息集原样复用） |
| Resume（断线续传） | 两个协议都没有；现靠 session_id 恢复历史勉强可用 | 远程部署实测断线频繁到影响体验；需 text/audio 帧序号 + 重连 replay 窗口 |
| Realtime 端点（`/v1/realtime`） | 无真实外部消费者 | 第一个第三方客户端/机器人接入需求确认；作为边缘网关建立在演进后私有栈之上 |
| LLM Proxy | 无旁路需求；tank 的摘要在服务端内部直调 LLM client | 出现需要借用服务端凭据的外部旁路任务 |

---

## 7. 实施阶段

> 2026-09-02 细化为文件级步骤（代码事实逐一核实，行号以核实日为准）。每步完成即 commit（gitmoji shortcode），并跑 §10 验证清单。

### 事实基线（P0-1 开工前核实）

- 信封：`backend/core/src/tank_backend/api/schemas.py`（56 行）= `MessageType`（8 值）+ `WebsocketAttachment` + `WebsocketMessage`（9 字段）。
- 出向构造 **18 处**：`api/router.py` 8、`api/signal_handlers.py` 8、`channels/audio_service.py` 2、`jobs/delivery.py` 1；全部经 `model_dump_json()` 上 wire。入向解析 1 处（`router.py:596`）。
- cli 手抄副本 `cli/src/tank_cli/schemas.py`（31 行）仅 4 个消费文件；web 手写 TS 镜像在 `web/src/services/websocket.ts:1-50`（`'approval_response'` 为死类型）；device `WsProtocol.cpp` 解析 5 字段、native fixture 内嵌源码。
- workspace：`backend/pyproject.toml` members=`["core","contracts","plugins/*"]`；tank-contracts 为扁平布局（零依赖、hatchling）；cli 是独立 uv 项目。
- 仓库无活跃 CI（backend-ci.yml 仅手动 dispatch）→「CI 校验」落地为本地检查脚本 + 验证清单步骤。

### P0-1 契约包抽取（纯重构、行为零变化）

**Step 1 — 新建 `backend/contracts/tank_protocol/`（嵌套 workspace 成员，§11.1 倾向落地）**

```
backend/contracts/tank_protocol/
├── pyproject.toml        # name="tank-protocol", version="0.1.0", deps=["pydantic>=2.0"],
│                         #   hatchling, dev 组 pytest
├── README.md             # §5.5 演进规则成文
└── tank_protocol/
    ├── __init__.py       # re-export + __version__（协议版本单一来源，P1-1 消费）
    ├── enums.py          # MessageType 8 值逐字照抄
    ├── envelope.py       # WebsocketAttachment + WebsocketMessage 字段/默认值逐字照抄
    ├── payloads.py       # 每类型合法字段集声明 + validate_envelope() → 违规列表
    │                     #   （wire 仍宽松，违反仅告警——§4.3 扁平袋缓解）
    ├── factories.py      # 按类型构造工厂（signal/transcript/text/update/attachment/
    │                     #   channel_notification/conversation_metadata_updated），仅原语参数
    ├── schema.py         # build_json_schema() + `python -m tank_protocol.schema <out>`
    │                     #   生成 schema.json 与 device golden_frames.h
    └── tests/            # round-trip / 字段集合法性 / 工厂快照 / 生成稳定性
```

接线：`backend/pyproject.toml` members 增加 `"contracts/tank_protocol"`；`uv lock` 验证嵌套成员（若 uv 报错，回退平级成员 `backend/protocol/`，其余步骤不变）。

**Step 2 — backend 构造点收拢（修 W7），删除 `api/schemas.py`**

- `backend/core/pyproject.toml` 依赖加 `"tank-protocol"` + `[tool.uv.sources]`（仿 tank-contracts）。
- 4 个 import 点改 `from tank_protocol import ...`：`api/router.py`、`api/signal_handlers.py`、`jobs/delivery.py`、`channels/audio_service.py`；18 处构造逐个改走工厂；`DisplayMessage→ws_msg` 映射逻辑留在 backend。
- 同步改 3 个测试文件 import（test_signal_handlers / test_websocket_attachment_frame / test_worker_live_push）。
- 安全网：新增 `backend/core/tests/test_protocol_wire_compat.py`，把 18 处现存构造的 wire dict 冻结为期望值，逐工厂断言 `model_dump()` 相等。

**Step 3 — cli 删除手抄 schema（修 W2）**

- `cli/pyproject.toml`：dependencies 加 `tank-protocol`，`[tool.uv.sources]` 用 path 依赖 `../backend/contracts/tank_protocol`（editable）。
- 删除 `cli/src/tank_cli/schemas.py`；4 个消费点改 import；新增喂 `speaker`+`attachments` 帧的测试（原副本会丢字段）。

**Step 4 — web TS 类型生成（§11.4 倾向落地：生成物入库）**

- web devDep `json-schema-to-typescript` + script `generate:protocol`（从入库的 `schema/tank_protocol.schema.json` 生成 `web/src/types/protocol.ts`）。
- `websocket.ts` 删除手写三类型，改 re-export（消费方零改动）；`'approval_response'` 死类型随之消失。

**Step 5 — device golden frames**

- `python -m tank_protocol.schema` 生成 `device/test/test_native/test_ws_message/golden_frames.h`（每出向类型一条真实 wire JSON + 一条含未知字段帧，内嵌头文件）。
- `test_ws_message.cpp` 增用例：每条 golden frame 解析后字段完整；未知字段帧解析不失败。

**Step 6 — 同步检查 + 文档修正（修 W1）**

- 新增 `scripts/check_protocol_sync.py`（仿 check_docs.py）：重生成三份生成物与入库版本 diff；校验 `__version__` 三处一致；失配非零退出。
- `backend/ARCHITECTURE.md` 协议章节修正：入向音频=纯二进制 Int16 PCM（无信封、服务端重采样/downmix 适配）；下行=8 字节头（magic 0x544B）；update_type 线上取值=`UpdateType.THOUGHT|TEXT|TOOL|APPROVAL|MESSAGE|USAGE`；删除不存在的 `{"type":"error"}` JSON 帧（错误走 `signal: error`）；目录结构补 tank_protocol。
- CLAUDE.md 验证清单加第 10 步：`python3 scripts/check_protocol_sync.py`。

**P0-1 非目标**：UpdateType 线上格式 `UpdateType.THOUGHT` 保持原样（行为零变化）；`cli/src/tank_cli/audio/frame.py` 对 tank_contracts codec 的手抄保留（CLI 已具备 path 依赖基建，后续顺手项）；device `platformio.ini` 的 magic build flags 不改为生成。

**Commit 顺序**：① `:sparkles:` 包 + 接线 → ② `:recycle:` backend 收拢 → ③ `:recycle:` cli 切换 → ④ `:sparkles:` web 生成 → ⑤ `:white_check_mark:` device golden → ⑥ `:memo:`+`:white_check_mark:` 文档与同步脚本。

**落地记录（2026-09-02）**：六个 commit 全部落地；全量验证清单通过（后端 3284 测试、cli 24、web 142 + E2E 10 场景、device native 86、sync 脚本双向验证）。补充事实与偏差：

- 嵌套 workspace 成员（`contracts/tank_protocol`）uv 实测可用；gotcha：`tank-contracts` 的 editable 安装把 `backend/contracts/` 放上 sys.path，新建 `tank_protocol/` 目录到 `uv sync` 之间的窗口内它会被当成无内容 namespace 包遮蔽真包——在这个窗口里 dev server 的 reload worker 会 ImportError，重跑 `scripts/dev.sh` 即恢复。
- golden frames 立即抓到一个真实固件缺陷：`WsMessage.type[20]` 装不下 `channel_notification`（20 字符）与 `conversation_metadata_updated`（29 字符），已扩为 32 字节（两类型本就不参与设备路由，行为仍是忽略，只是从"截断巧合"变成"完整字符串"）。
- web 生成接口用 schema 后处理对齐旧手写接口：strip pydantic 逐字段 title（避免垃圾别名）、信封必填 `type/content/is_user/is_final/metadata`、attachment 四字段全必填——依据是"服务端每帧全量序列化、null 显式"这一 wire 事实。
- 验收标准 2 演练通过：把 `msg_id` 临时改为 `int | None` 后，cli 测试即红、web `tsc -b` 即报错。

### P0-2 认证（独立可先行）——已落地（2026-09-02）

- 配置：`config/models.py` 新增 frozen dataclass `AuthConfig`（`token: str = ""`，YAML 里 `${TANK_WS_TOKEN:-}`；`require: bool = false`），`AppConfig` 注册字段 + `from_raw_dict` 接线 + `config.yaml` 注释示例（三处插入点见 `config/app_config.py` 现有模式）。
- 校验：`api/auth.py` 纯函数 `check_ws_auth`（`hmac.compare_digest` 按 UTF-8 字节比对）；`websocket_endpoint` 在 accept 后、任何会话工作前读 `?token=` 并校验，拒则 `close(1008)`。`require=true` 且未配 token 时 fail-closed（拒绝一切连接并记 error 日志）。
- Tests：`test_ws_auth.py` 11 例 —— 纯函数决策矩阵（含非 ASCII token、fail-closed）+ endpoint 级 4 条拒绝路径（TestClient 断言 close code 1008）。放行路径由既有 E2E（无 token 连默认配置）覆盖。
- 注意：拒绝发生在 `get_or_create_assistant` 之前，被拒连接零会话开销；客户端侧 token 携带（web/cli/device 发 `?token=`）属远程部署设计（§11.2）的后续工作，本阶段不涉及。

### P1-1 握手/版本/能力 ——已落地（2026-09-02）

- `ready` 帧 metadata 增加 `protocol_version`（= `tank_protocol.__version__`；用字符串取代 §5.1 草案的 int，包版本即单一来源）与 `protocol_features: list[str]`（随各阶段落地逐个点亮：opus/resume/config）。
  - **命名偏差记录**：§5.1 草案的 `capabilities: [...]` 与 ready 帧既有键 `capabilities`（`{asr,tts,speaker_id}` 流水线能力字典，web 在消费）冲突，wire 兼容承诺不允许改语义，故协议能力列表落在新键 `protocol_features` 下。
- `tank_protocol.handshake` 模块：`handshake_metadata()`（版本 + 特性列表的单一来源）+ `KNOWN_PROTOCOL_FEATURES`；payloads 的 SIGNAL metadata 键集与 KNOWN_SIGNALS 同步收录 `protocol_version`/`protocol_features`/`enable`/`capabilities` 信号。
- 新 signal `capabilities`（`@register` 零改动扩展）：`metadata.enable` 已记录（info 日志）；当前无已实现的协议特性，连接级能力集的消费推迟到 P1-2/P1-3 落地时引入（避免无人读取的死存储）。
- 旧客户端不发声明帧 = 现行为。Tests：包侧 5 例（handshake_metadata / 帧合法性）+ backend 6 例（`_ready_metadata` 携带字段、声明信号可分发、未知信号仍未处理）；实机 ready 帧验证 + E2E 全过。

### P1-2 Opus 协商（开工前置：码率/复杂度起点、device 内存实测定案）

- tank_protocol：能力名 `opus` + 协商状态模型。
- 服务端：libopus 绑定（选型开工时定）编解码器；协商开启时 binary 分支 Opus→PCM 入管线、下行 PCM→Opus 出。
- web：AudioWorklet + wasm 编解码；cli：Python 绑定；device：ESP32-S3 实测通过后接入。

### P1-3 热配置 + 上下文注入

- tank_protocol：`config` 消息类型 payload 模型（deep-merge 语义）+ 上下文注入消息类型。
- 服务端：`@register` 处理器 → Assistant 会话热应用（instructions/voice/VAD 参数）；注入只入上下文不触发生成；非法配置先校验后应用，拒绝时会话不受影响。

### P2 按触发条件（§6）

WebRTC / Resume / Realtime 端点 / LLM Proxy —— 见 §6 触发条件表。

依赖关系：P1-x 全部依赖 P0-1（没有单一契约源，每项都要四端各改一遍）；P0-2 独立可先行。

---

## 8. Tests

- **P0-1 契约包**：
  - unit（新包）：信封模型 round-trip（dict → model → wire dict 与现状逐字段一致，锁定 wire 兼容）；payload 校验模型对每类消息的合法/非法字段集；构造工厂产出的帧与现存手写构造逐字段 diff 为空；
  - cli：删除本地 schema 后全量测试通过（import 路径替换）；故意给 cli 喂带 `attachments` 的帧验证新契约生效；
  - web：生成的 `protocol.ts` 编译通过、`pnpm lint`/`tsc -b` 通过；CI 校验生成物与包版本一致的测试；
  - device：golden-frame 夹具加入 `test_ws_message` / `test_audio_protocol`（每种消息类型一条真实帧，含未知字段容忍用例）；
  - 同步：`scripts/check_protocol_sync.py` 重生成三份生成物（schema.json / golden_frames.h / protocol.ts）与入库版本 diff 为空、`__version__` 三处一致；
- **P0-2 认证**：unit —— 有效/无效/缺失 token 三分支（可配置强制模式下缺失即拒）；
- **P1-1 握手**：unit —— `ready` 帧携带 protocol/capabilities；旧客户端（无声明帧）行为不变；
- **P1-2 Opus**：unit —— 编解码 round-trip（PCM → Opus → PCM，SNR 阈值断言）；能力协商开关关/开两分支；
- **P1-3 热配置**：unit —— config 消息 deep-merge 生效、非法配置被拒且会话不受影响；注入消息不触发生成；
- **E2E**：既有 `test/` feature 文件加 scenario——文本 + 语音双路径回归（协议重构后全链路不变）；认证启用模式下无 token 连接被拒。

## 9. 验收标准

1. `grep -rn "MessageType" cli/src/` 仅命中对 `tank_protocol` 的 import，本地副本删除；
2. 改动 `tank_protocol` 任一字段类型 → cli/web 侧在编译/CI 阶段即失败（人为演练一次）；
3. 四端在 LAN 下与现状行为逐帧一致（E2E 全绿 + 语音人工抽测）；
4. `backend/ARCHITECTURE.md` 协议章节与代码一致（音频帧描述修正）；
5. 远程部署就绪项勾选：认证 ✅、Opus 可协商 ✅、握手 ✅。

## 10. 验证清单（每阶段完成后全量执行）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check src/ tests/`（contracts 与 cli 侧各自再跑）
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <改动文件>`（禁止 `# type: ignore`）
6. `cd cli && uv run ruff check src/ tests/ && uv run pytest`
7. dev server 日志检查：`tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`（空输出即通过，不重试）
8. `cd test && pnpm test`（E2E，需 backend + frontend 运行中）
9. device 侧（P0-1/P1-2 涉及时）：`cd device && uv run pio test -e native`
10. `python3 scripts/check_protocol_sync.py` — 协议生成物与 `tank_protocol` 包同步（P0-1 起生效）

**测试失败政策**：任何阶段发现红测试——无论是否本阶段引入——修复后才算完成。

## 11. 未决问题

1. ~~`tank_protocol` 放 `backend/contracts/` 下还是仓库根 `protocol/`？~~ **已定（2026-09-02）**：嵌套 workspace 成员 `backend/contracts/tank_protocol/`（复用现有 workspace，cli path 依赖路径短）；若将来非 backend 生态（如独立发布）再迁出；
2. 认证 token 的分发方式（配置文件 vs 首次配对流程）——远程部署设计时定；
3. Opus 码率/复杂度参数（16kHz 语音建议 24-32kbps 起点）与 device 端内存实测——P1-2 开工时定；
4. ~~web 生成类型的落盘路径与 lint 集成方式~~ **已定（2026-09-02）**：生成物入库（`web/src/types/protocol.ts`、device golden_frames.h、schema.json 同理），一致性由 `scripts/check_protocol_sync.py` + 验证清单保障（仓库 CI 为手动触发，不依赖 GitHub Actions）。
