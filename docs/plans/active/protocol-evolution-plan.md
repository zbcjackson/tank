# Tank 私有协议演进计划（Protocol Evolution Plan）

> 状态：P0-1、P0-2、P1-1 已落地（2026-09-02）。**P1-2 全部落地（2026-09-06）**：Step 1-4（09-03 ~ 09-05）、Step 5（device）真机集成完成——opus 全双工经真机验证（说话→正常回复，后端零解码失败）。P1-3 已落地（2026-09-05，协议包 0.3.0 + 服务端热配置/注入）。P2 按触发条件（§6）。
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

### P1-2 Opus 协商 —— 计划细化（2026-09-03，spike 与代码事实核实完毕；实施未开始）

**开工前置定案（spike 实测；方法：300-3400Hz 语音形噪声突发 + 整数相关对齐 SNR——纯音/白噪声上的 SNR 测量有歧义，不可用）**

- **绑定选型：`opuslib`**（cffi 绑定系统 libopus；本机 AArch64 实测加载 `libopus.so.0` 成功，无需 dev 包；解码按构造速率原生输出 16k/24k PCM，免重采样；16k enc+dec 合计 146× 实时，约 6.9ms CPU/20ms 帧）。后备 `PyAV`（PyPI 包名 `av`；自带 FFmpeg 轮子零系统依赖、维护活跃，但解码强制输出 48kHz，两方向都要补重采样）。**互通性已位级验证**：opuslib 编码的包被 opuslib/av 两个解码器解码 corr=1.00000，两绑定同码率包长区间一致（32k：67-127B）——服务端选哪个绑定都不影响 wire，其余三端自选实现。
- **质量锚点**（opuslib 16k，对齐 SNR，随码率单调正确）：16k→7.5dB / 24k→11.8dB / 32k→14.7dB / 64k→22.3dB；round-trip 延迟 = 104 样本 @16k = libopus 文档的 6.5ms 编码前瞻，无额外延迟。
- **参数定案**：帧长 20ms（与 mic 帧 / TTS chunk 节奏一致）；上行 16kHz mono、下行 24kHz mono（TTS 原生率 = 设备喇叭率）；码率起点双向 32kbps；复杂度/DTX/FEC 用 libopus 默认（关），TCP 无需 FEC/DTX。带宽收益：上行 32KB/s→约 4KB/s（8×），下行 48KB/s→约 4KB/s（12×）。
- **device 内存实测仍待**——仅门控下述 Step 5；本机 CoreS3 serial 有 JTAG 争用问题，需专门硬件会话。

**Wire 设计定案（本文档此前未写明的两点）**

1. **分帧**：一条 WS binary 消息 = 一个 Opus 包，双向皆然。WS 消息边界即包边界，无需长度前缀（opus 包上限 1275B；20ms@32k 实测约 80-127B）。
2. **协商确认流**（connect 时一次性；v1 无中途重协商/关闭，连接生命期内编解码固定）：
   `signal: ready`（`protocol_features` 含 `opus`，由服务端能否导入 opuslib 决定点亮与否——`router.py:146` 现传空列表）→ 客户端 `signal: capabilities`、`metadata.enable=["opus"]`（P1-1 已定义的帧形）→ 服务端校验后回 `signal: capabilities` ack，`metadata` = `{"enabled": ["opus"], "opus": {"uplink": {"sample_rate":16000, "frame_ms":20, "bitrate":32000}, "downlink": {"sample_rate":24000, "frame_ms":20}}}` → 双方各自切换编解码。
   - 竞态窗口（ack 在途时客户端旧 PCM 被服务端按 opus 解码）只出现在连接建立瞬间、早于任何用户语音，实际为空窗；已知并接受。
   - opus 连接中 `audio_format` 信号忽略（上行率已协商固定）；`?output_rate=` 查询参数忽略（下行率已协商固定）。未协商连接（含全部旧客户端）逐帧行为不变。

**实施步骤（每步一 commit + §10 全量验证清单）**

- **Step 1 — tank_protocol**：`payloads.py` SIGNAL metadata 键集加 `enabled`/`opus`；`factories.py` 加 capabilities-ack 工厂；schema/golden 生成物重生成（ack 帧样例如入 golden）；`__version__` → 0.2.0（additive minor bump，`protocol_version` 随之升级）；包测试 + `scripts/check_protocol_sync.py`。
  **落地记录（2026-09-03，commit d1923a6）**：另加 `handshake.OPUS_PROFILE` 常量（协商参数单一来源，ack 工厂内嵌之，客户端从 wire 自取、服务端自读同一处）；ack 的 `enabled` 排序去重保证 wire 确定性；README 补 handshake 模块行与协商流程小节；golden 新增 `TANK_GOLDEN_SIGNAL_CAPABILITIES_ACK`（native 21 例全过，C++ 侧零改动——ack 帧对设备仍是忽略的 signal 变体）；`web/src/types/protocol.ts` 零变化（json2ts 忽略 `x-tank-*`，信封未动）。全量验证清单通过（包 33 / 后端 3301 / cli 24 / device native 86 / E2E 10 / sync OK）。顺带发现：健康检查路由实际是 `/api/health`（`server.py:692`），根 ARCHITECTURE.md 与 backend 文档仍写 `/health`——既有文档漂移，非本阶段范围。
- **Step 2 — 服务端**：
  - `backend/core` 依赖加 `opuslib`（uv add）；新增 `audio/opus_codec.py`：`OpusUplinkDecoder`（逐包 decode → PCM16）与 `OpusDownlinkEncoder`（20ms 重缓冲任意长度 PCM chunk → 逐包 encode；中断时直接丢弃残量——playback 本就 fade-out，无爆音）。
  - `api/signal_handlers.py::handle_capabilities`（现仅记日志，:159-174）实现真协商：校验 feature → 建编解码器 → 回 ack。
  - `api/router.py`：上行 binary 分支（:611-631）加 opus 解码路径（编解码器实例存 ws handler 闭包，连接级）；`on_playback_chunk`（:468-507）加 opus 编码路径；**channel 音频 fan-out（:497-503）按订阅者各自编码**——现扇出直接转发已编码帧，混合编解码下必须每订阅者重建；`ConnectionManager` 增加每会话编解码器注册表供扇出查询。
  - `_ready_metadata`（:140-146）：`handshake_metadata()` 传入服务端实际支持的 feature 列表（opuslib 可导入 → `opus`）。
  - Tests：`test_ws_opus.py`——round-trip SNR（spike 的信号生成+对齐方法移植为 helper，阈值：32k ≥ 10dB）；协商关/开两分支（无声明 = 现行为逐帧不变）；ack 对未知 feature warn-忽略；fan-out 混合编解码（自身 opus + 订阅者 PCM）。
  **落地记录（2026-09-03，commit acdc0a4）**：全部按计划落地，另加两项实现中发现必要的补充——① PCM 自身会话 + opus 订阅者的扇出组合（讲话方未协商 opus）需要共享编码器，落为 `ConnectionManager.get_channel_encoder()` 懒创建（profile 全局相同，一条包流服务所有 opus 消费者）；② 编码器残量陈旧判定（>1s 即丢弃，可注入时钟）——中断后 TTS 半帧残量若不清理会漏进下一响应开头。`test_ws_opus.py` 19 例：编解码单元（SNR/重缓冲/残量语义/垃圾包容错）+ handle_capabilities 决策矩阵 + 真 endpoint 集成（MagicMock assistant + 真 ConnectionManager 驱动 `websocket_endpoint`，覆盖 ready 广告、双向切换、混合扇出）。既有 `test_protocol_handshake` 的 dispatch 用例因 handler 现在触碰 deps 而补初始化（并强化为断言注册发生）。全量验证：后端 3318、cli 24、E2E 10/10、真机 smoke（dev server 上 ready 广告 opus/ack 携带 profile/上行包入管线/未知 feature 被拒）全过。
- **Step 3 — web**：wasm libopus 选型（候选 `opus-encoder`/`opus-decoder` npm wasm 包，开工时按 bundle 体积与 API 定）；`services/audio.ts` 上行编码（AudioContext 已锁 16k，:103）；下行 `services/audioFrame.ts`（现 8 字节头解析处）与 `services/audioPlayback.ts`/`browserAudio.ts` 调度路径加 opus 分支；`hooks/useAudioPipeline.ts`（或 useAssistant）ready 后发声明、收 ack 后切换；不协商则现有 PCM 路径零改动。
  **落地记录（2026-09-03，commit 8f035e7 + af90871）——选型偏差：改用 WebCodecs 而非 npm wasm 包**。理由：2026 年浏览器 `AudioEncoder`/`AudioDecoder` 原生支持 opus——零 bundle 体积（对 Tauri 静态打包零负担）、浏览器自带 libopus、可 `isConfigSupported` 探测优雅回退 PCM；而 wasm 路线的编码器侧没有一等 npm 包，且 MB 级内联 wasm 会进 .app。关键事实：WebCodecs 把 opus 锁在 48kHz——下行包解出 48k float（包本身与码率无关，无碍）；上行 16k mic 线性 3× 上采样后编码。实现：`services/opusCodec.ts`（OpusUplink/OpusDownlink/isOpusSupported）；opus 在 `useAudioPipeline` 的 binary 入口处终止——解码后重封 8 字节头 PCM（48k）再走既有路由，channel audio 与 playback 零改动；`websocket.sendBinary` + `audioFrame.encodeAudioFrame`。
  **smoke 抓到两个真 bug**：① `isConfigSupported()` 的规范字段是 `supported` 而非 lib.dom 里误导性的缺失——初版探针恒 false，线上会静默回退 PCM；② Chrome 的 WebCodecs opus 编码器产出**变长包**（非严格 20ms），服务端 320 样本解码容量报 "buffer too small"（一次 E2E 掉 47 帧）——修复为按 libopus 120ms 上限容量解码（commit af90871，opus_decode 返回实际样本数，管线本就消费变长帧）。**跨实现互通实证**（真实 chromium + opuslib，经真 wrapper 模块）：上行（浏览器编码→服务端解码）51 包全 20ms、SNR 18.8 dB；下行（服务端编码→浏览器解码）50 包、SNR 11.3 dB。E2E 10/10 且协商在 E2E 中真实发生（服务端日志 5 会话 negotiated，修复后 0 解码失败）。验证全量：web lint/tsc/vitest 153、后端 3318。
- **Step 4 — cli**：`cli/client.py`（:76 `send_audio` 及下行 binary 分支）+ `audio/input/handler.py`、`audio/output/handler.py` 接 opuslib（与服务端同库同 API）；ready 后声明、ack 后切换。
  **落地记录（2026-09-05）——偏差：opus 落点从 audio handler 改为 TankClient**。原计划点名的 `audio/input/handler.py`、`audio/output/handler.py` 已重构为 `mic.py`/`playback_worker.py`（由 `cli/audio_capture.py`、`cli/audio_playback.py` 包装）；改在 `TankClient`（wire 收发的唯一出入口）内做协商与编解码，capture/playback 零改动——与 web Step 3「在 binary 入口处终止 opus、重封 8 字节头 PCM 再走既有路由」同模式。其余要点：
  - 新增 `cli/src/tank_cli/audio/opus_codec.py`：`OpusUplinkEncoder`（任意块长重缓冲为 20ms 帧，与服务端下行编码器同构）+ `OpusDownlinkDecoder`（120ms 容量提示，容忍变长包）；参数直接读 `tank_protocol.OPUS_PROFILE`（cli 可 import Python 包，与服务端同一常量即单一来源；wire 内嵌 profile 仍服务于不可 import Python 的 web/device）。
  - 协商状态机在 `TankClient._handle_handshake`：ready 广告 opus → 发一次声明（`_declared` 防重）→ ack 含 opus 才建编解码器；opuslib 不可导入则永不声明；disconnect 重置。竞态窗口（ack 在途时上行 PCM 被服务端按 opus 解码丢弃）沿用计划已接受的连接瞬间空窗——CLI mic 虽连接即采集，但此时段用户尚未开口，仅头几十 ms 静音帧可能被丢。
  - 上行编码器不做服务端式的残量过期丢弃：capture 流（含静音）连续不断，缓冲永不过期。
  - 测试 14 例新增：codec 6（SNR round-trip 移植服务端 spike helper、重缓冲、变长包、垃圾包→OpusDecodeError）+ client 8（ready 声明/无 opus 不声明/防重/ack 切上行（解码验证）/ack 无 opus 保持裸 PCM/ack 切下行（8 字节头 24k）/垃圾包丢弃不断连/disconnect 重置）。CLI 24 → 38。
  - 真机 smoke：dev server 上 ready 广告 opus → 声明 → ack（profile 完整）→ 50 上行包入真管线，服务端日志 "Opus negotiated for opussmoke"，零解码错误。全量验证清单通过（web lint/tsc、后端 3318、cli 38、E2E 10/10、sync/docs OK）。
- **Step 5 — device（门控：ESP32-S3 内存/CPU 实测）**：libopus 的 ESP-IDF 移植选型（候选 ESP-ADF opus component）+ heap/PSRAM 占用与实时性实测，定案后才接入；触点 `net/WsProtocol.cpp`、`net/WsClient.cpp` 路由、`audio/AudioCapture.cpp`/`AudioPlayback.cpp`；native golden-frame 测试同步。
  **门控实测落地记录（2026-09-06）——结论：GO，但设备端编码器必须 complexity ≤5。**
  - **选型定案：vendor 上游 libopus 1.4 源码**（`device/components/opus`，定点配置 FIXED_POINT+VAR_ARRAYS+DISABLE_FLOAT_API，裁掉 x86/arm/mips asm 与 float analysis/mlp；license 随附）。ESP-ADF 的 opus 组件已不存在（v2.5 起收进预编译的 esp-adf-libs）；先试了托管组件 `espressif/esp_audio_codec` 2.6.2（声明 idf>=4.4），实测在 IDF 5.3.1 上有致命问题：INFO 日志绕过运行时级别过滤、日志互斥锁结构被踩断言崩溃——已回退移除。源码 libopus 与服务端 opuslib 同核心，测量口径对齐，且可调试。
  - **实测数据**（CoreS3 真机，`test/test_device/test_opus_bench`，Unity 4 用例全绿，全程 COMPREHENSIVE 堆毒化校验通过；语音形噪声 300-3400Hz 最坏情形，240MHz）：
    - 内存：enc(16k)+dec(24k) 合计 **25,084 B 内部 RAM**（状态 24,544+17,776 B）；10 次 create/destroy 零泄漏；largest free block 98K→59K。
    - 解码（24k/20ms/32kbps）：avg **2,037µs = 10.2%** 帧预算，max 2,161µs——余量充足。
    - 编码（16k/20ms/32kbps）：cx0=33.8% / **cx3=48.9% / cx5=73.3%** / cx8=110.9% / **cx9=110.9%（服务端默认，超实时）** / cx10=111.0%。
    - 质量：32kbps round-trip **14.4 dB**（spike 浮点 14.7dB——定点与浮点无实质差）。
  - **集成定案**：上行编码器 `OPUS_SET_COMPLEXITY(5)`（73%，语音实际成本更低；cx3 48.9% 为保守档）——编码器内部参数，不进 OPUS_PROFILE（wire 无关，各端自由）。下行解码 10% 无压力。集成检查项：真实固件（WiFi+LVGL+esp-sr 常驻）下 largest free block 须 ≥ encoder 状态单块 24.5KB。
  - **集成尝试与回退（2026-09-06）——协商链路真机打通，但固件内存墙未能跨越，main/ 集成已 revert（commit 序列见 git log），设备恢复 PCM 运行**。已验证的部分：真机协商全流程（ready 广告 → 声明 → ack → "Opus negotiated" 双端日志一致）、PSRAM placement-init 的 codec 状态（`opus_encoder_init/decoder_init` + `heap_caps_malloc`）、上行编码路径。未跨越的墙：
    1. **内部 DRAM 无 36KB 余量**：真实固件内部堆碎片化到 free≈39KB / largest≈19KB（WS init 时点），而 opus 需要 ~36KB 任务栈（编码 24KB + 解码 12KB）。栈改 BSS 会 1:1 缩小堆池（WS client 的 init 缓冲 ~17KB 连续分配随即失败）；缩 WS buffer/队列只挤出 ~12KB。
    2. **PSRAM 任务栈不可用**：静态栈放 PSRAM 的任务首次调度即野 PC（gdb 实证 0x40000000 + SP 不可读）——与 IDF「cache 关闭窗口（NVS 写等）期间外部栈任务不能运行」的限制一致；WiFi 常开设备上是致命雷。
    3. **队列存储搬 PSRAM**（内核结构体内、数据 PSRAM）：afeFeedTask 在 xQueueReceive 临界区内 LoadProhibited（用户说话即崩）——原因未深究，随集成一并回退。
  - **设备端恢复 opus 的候选路径**（后续立项再评估）：① libopus 以 `NONTHREADSAFE_PSEUDOSTACK` 构建——VLA 搬进静态 BSS scratch（~25KB），任务栈缩到 4-8KB，encode/decode 加互斥串行；② 内部 RAM 预算重构（mic/clean/event 队列裁剪 + 实测各栈 HWM 后精确配额）；③ 远程部署时优先给 web/cli 用 opus，device 保持 PCM（LAN 带宽充裕，非痛点）。组件 `device/components/opus` 与 bench 保留，随时可复用。
  - **集成最终落地（2026-09-06，同日）——内存墙的答案在 LVGL**：ELF 分析发现内部静态 RAM 单项最大占用是 **LVGL 的 64KB tlsf 池**（`CONFIG_LV_MEM_SIZE_KILOBYTES=64`，lv_mem_core_builtin.c 的 `work_mem_int[]`）。LVGL v9 内建分配器支持 `LV_MEM_POOL_ALLOC(size)` 宏钩子——在项目 CMakeLists 对所有 C/C++ 编译单元 force-include `main/lv_mem_psram_pool.h`（`heap_caps_malloc(size, MALLOC_CAP_SPIRAM)`），池整体迁入 PSRAM（控件元数据容忍 PSRAM 延迟；DMA 绘制缓冲不动；LVGL 不 de-init 故不释放）。注意 force-include 必须限定 C/C++ 语言（`$<$<COMPILE_LANGUAGE:C,CXX>:...>`），否则汇编文件编译报语法错；`-include` 与路径必须写成一个 token（分开写触发 gcc "multiple files" 错）。
    - 迁移后内部堆 WS init 时点 free≈49KB / largest≈31.7KB（对照迁移前 33/8.7），opus 编解码任务栈以 BSS 静态数组保留内部 RAM（链接期保留，免疫碎片）：ws_send 32KB、WS client 8KB（内联解码）。
    - **真机全双工验证通过**：说话→后端 ASR→回复→下行 opus 解码播放，声音正常；后端零解码失败；设备端零队列满/解码错误。栈溢出实测：opus_encode@cx5 在 24KB 栈上溢（canary 触发），32KB 通过——bench 的 64KB 栈掩盖了精确 HWM，回填值取 32KB。
    - 复活的集成代码 = cherry-pick 683df88 + 两处改进：codec 状态改 PSRAM placement-init（`opus_encoder_init/decoder_init` + `heap_caps_malloc`，规避会话中期内部堆 -7 分配失败）；destroy 改 `heap_caps_free`。
  - **工程教训（写入 bench 注释与 TESTING.md 语境）**：① libopus VAR_ARRAYS 在调用者栈上开大数组——**opus_encode 至少需 ~20-30KB 任务栈**，bench 用 64KB 专用任务；② `heap_caps_check_integrity_all` 走 8MB PSRAM 池需数秒、饿死 INT WDT——校验用 `MALLOC_CAP_INTERNAL` 限内部池；③ 虚拟串口读法：VM 里每次 flash 后 CDC 端点楔死，冷启动（拔插≥10s）恢复，读端用 O_NONBLOCK 裸 open（pyserial 的 tcsetattr 会卡在楔死端点上），先挂读端再 OpenOCD 软复位可消竞态。
  - 生成/脚本零变化（协议包未动），`check_protocol_sync` 不涉及。

**P1-2 非目标**：不做中途重协商/关闭；不做 UDP/WebRTC（§6 触发条件）；不动 `tank_contracts` 的 PCM frame codec。

### P1-3 热配置 + 上下文注入 —— 计划细化（2026-09-05，代码事实核实完毕）

**Wire 设计定案**

1. 新入向消息类型两个（信封形状不变，additive minor → `__version__` 0.3.0）：
   - `config`：配置对象放 `metadata.config`（dict，deep-merge：重复发送同名键即替换，显式 `null` 清除；信封 `content` 是 `str`，结构化数据按 capabilities 先例走 metadata）。v1 可配置键：`instructions`（str|null，追加为 stable tier 的 "SESSION INSTRUCTIONS" 段，非整体替换——替换会摧毁 SOUL.md/AGENTS.md 组装出的人格与工具指引）、`voice`（str|null，TTS 音色 override，null 回退引擎按语言默认）、`vad`（dict，v1 仅 `speech_threshold` float ∈ (0,1)）。未知键/类型错/越界 → 整帧拒绝（原子：先全量校验后应用），回 `signal: error`（metadata.error），会话不受影响；成功不回帧（fire-and-forget，仿 input）。
   - `context_inject`：`content` = 注入文本，`metadata.role` ∈ {user, system, assistant}（默认 user）。服务端直接 `ContextManager.add_message`（追加+持久化），**不投 BrainInputEvent → 不触发生成**（对应 Realtime `conversation.item.create`）。
2. factories：`session_config(config, *, session_id)` + `context_inject(content, *, role=None, session_id)`；payloads 收录两类型的 ENVELOPE_FIELDS/METADATA_KEYS；golden frames 增两条（`_golden_frames()` 手写清单追加，device 侧 expectGolden 同步）。
3. `signal: ready` 的 `protocol_features` 增 `"config"`（纯后端逻辑，无条件支持；现有 `supported_protocol_features()` 在 opus_codec 只报 opus，router 侧组合为 `["config"] + opus?`）。

**服务端落点（代码事实）**

- `Assistant.apply_session_config(config)`（ValueError 拒绝）：instructions → `Brain.set_instructions` → `ContextManager` → `PromptAssembler` 新增 override 槽 + `mark_dirty()`（Brain 每次 LLM 调用前已检查 `needs_rebuild` 重组 prompt，llm.py:542）；voice → `self._tts_processor.set_voice_override`（TTSProcessor 是 `request.voice → generate_stream` 的唯一咽喉，tts.py:76，比改 Brain 4 处 AudioOutputRequest 构造点省）；vad → `self._vad_processor.set_session_threshold` → `VADStream` 新增 session 阈值槽——**必须**让 `reset_threshold()` 回落到 session 阈值而非出厂默认，否则 echo guard 播放结束回调（vad.py:76）会把热配置冲掉。目标 processor 为 None（TTS/ASR 未启用）时跳过 + warning，不算拒绝。
- `Assistant.inject_context(content, role="user")`：校验后转 `ContextManager.add_message(role, content)`。
- router `websocket_endpoint` 的 elif 链加 CONFIG / CONTEXT_INJECT 分支（消息类型不走 signal 注册表），ValueError → `signal: error`。

**实施步骤（每步一 commit + §10 全量验证清单）**

- **Step 1 — tank_protocol 0.3.0**：枚举/payloads/factories/golden/schema + 重生成三份生成物 + device `test_ws_message.cpp` 补两条 expectGolden + 包测试。
- **Step 2 — 服务端**：Assistant 两方法 + VADStream/TTSProcessor/PromptAssembler 热应用面 + router 分发 + `tests/test_session_config.py`（校验矩阵/原子性/注入不生成/三参数热应用/路由错误帧）。
- **Step 3 — 文档**：backend/ARCHITECTURE.md 与根 ARCHITECTURE.md 的入向消息表补两行 + 本节落地记录。

**P1-3 非目标**：不做中途重协商的 config 回执/版本化（error 帧已够用）；不做任意 VAD 参数全量热配置（v1 仅 speech_threshold， additive 扩展）；注入不做去重/长度上限（交给既有 token 预算与 compaction）。

**落地记录（2026-09-05，两 commit：协议包 654e5dd + 服务端）**：全部按细化落地，无设计偏差。

- **Step 1（commit 654e5dd）**：`MessageType` 增 `CONFIG`/`CONTEXT_INJECT`；factories `session_config`/`context_inject`；payloads 字段集（config 只允许 `session_id`+`metadata.config`，context_inject 允许 `content`+`metadata.role`）；golden 增 `TANK_GOLDEN_CONFIG`/`TANK_GOLDEN_CONTEXT_INJECT`（device native 21→23 例，入向类型也进 golden——设备不路由但解析器必须完整吞下）；`__version__` 0.3.0；三份生成物重生成，`check_protocol_sync` OK，web tsc 零代码改动通过。
- **Step 2**：`Assistant.apply_session_config`（全量校验后原子应用；非 dict/未知键/空 instructions/voice/越界或 bool 阈值 → ValueError）+ `Assistant.inject_context`（role ∈ user/system/assistant）；`VADStream.set_session_threshold`（session 阈值槽，`reset_threshold` 回落到 session 阈值——否则 echo guard 播放结束回调会冲掉热配置，pyright 抓到 None 清除路径后补全）+ `VADProcessor` 透传；`TTSProcessor.set_voice_override`（`request.voice or override`，单咽喉点避免改 Brain 4 处构造点）；`PromptAssembler.set_instructions`（追加 "SESSION INSTRUCTIONS" stable 段，重发替换、None 清除、mark_dirty）；`ContextManager.set_instructions`/`Brain.set_instructions`/`Brain.inject_context` 转发链；router `_handle_config_message`/`_handle_context_inject` + elif 分发，ValueError → `signal: error`。`_negotiable_protocol_features()` = `["config", "opus"?]`。
- **Tests**：`test_session_config.py` 42 例（VAD 阈值 3、assembler 3、TTS override 3、Assistant 校验矩阵+原子性+缺处理器跳过 10、路由分发 5、真 endpoint 4 + 参数化），`test_protocol_handshake` 特性断言更新为 `["config", "opus"]`。后端 3318 → 3360。
- **真机 smoke**：dev server 上 ready 广告 `['config', 'opus']`/0.3.0；合法 config（vad+instructions）应用（日志 "Session config applied"/"Session instructions updated"）；`{"bogus":1}` 被拒回 error 帧带支持键列表；context_inject system 角色注入成功（"Injected system context message"）。web lint/tsc、E2E 10/10 通过。

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
3. ~~Opus 码率/复杂度参数与 device 端内存实测~~ **部分已定（2026-09-03）**：绑定 opuslib（后备 PyAV）、20ms 帧、上行 16k/下行 24k、起点双向 32kbps——spike 实测见 §7 P1-2；device 端内存/CPU 实测仍待，仅门控 P1-2 Step 5（device 段）；
4. ~~web 生成类型的落盘路径与 lint 集成方式~~ **已定（2026-09-02）**：生成物入库（`web/src/types/protocol.ts`、device golden_frames.h、schema.json 同理），一致性由 `scripts/check_protocol_sync.py` + 验证清单保障（仓库 CI 为手动触发，不依赖 GitHub Actions）。
