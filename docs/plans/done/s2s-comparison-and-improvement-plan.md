# Tank vs HuggingFace speech-to-speech 对比研究与改进计划

> 状态：已完成（2026-09-02）。P0-1~P0-5、P1-1/P1-2、P2 各项均已落地；P3 单独立项，由 [protocol-evolution-plan.md](../active/protocol-evolution-plan.md) 承接。
> 研究日期：2026-08-25/26。对象：`huggingface/speech-to-speech`（本地检出 `/home/zbcjackson/src/speech-to-speech/`，以下简称 s2s）。
> 方法：对 s2s 的管线核心 / Realtime API 层 / LLM 后端抽象 / 工程实践四个侧面做代码级调研，并对 tank backend 对应实现逐项核对（文件路径均来自实际代码）。

---

## 1. 定位差异

| | s2s | tank |
|---|---|---|
| 本质 | 聚焦的语音管线：VAD→STT→LLM→TTS 四段级联 + OpenAI Realtime 协议服务器 | 全功能语音助手平台：管线 + agent 编排 + 工具/审批 + 持久化 + 多 connector |
| 源码规模 | 99 文件 / 2.2 万行 | 344 文件 / 6.7 万行（core 257 + plugins 87） |
| 测试规模 | 56 文件 / 2.6 万行 | 200 文件 / 5.2 万行 |
| 服务客户端 | 任何 Realtime 客户端（stock OpenAI SDK、@openai/agents、Reachy Mini 机器人） | 自有 web / cli / macos / device 四端（自定义协议） |

对比意义不在功能全不全，而在**语音管线这个交集上的单位质量差距**。

---

## 2. 对比结论

### 2.1 tank 已领先之处（重构中不可丢失）

| 维度 | tank | s2s |
|---|---|---|
| **回声防御** | 两层：播放期 VAD 阈值升至 0.85（`audio/input/vad.py:66-76`）+ EchoGuard 文本重叠检测 | **完全没有**。`should_listen` 事件只有 `.set()` 从不 `.clear()`，服务端全双工裸跑，隐含假设客户端戴耳机或自带 AEC（浏览器 WebRTC）。tank 的 ESP32 设备（无硬件 AEC）依赖这层防御 |
| **背压** | 有界队列 + `FlowReturn` 传播，正经流控 | 无界队列 + 主动丢弃（VAD 剔除被取代 revision、STT 丢陈旧输入）。丢陈旧数据对语音合理，但无界队列是内存风险 |
| **可观测性** | Bus + 6 种 observer + Langfuse + 健康检查 + QoS 反馈 | 基本只有日志 + `/v1/usage` |
| **会话模型** | 按需 `get_or_create_assistant` + 30s idle 回收（`api/manager.py:29`），重引擎进程级单例 | 启动时固定大小池，满了拒连（`session_limit_reached`） |
| **Agent/工具/审批/持久化** | 完整 | 无（工具仅客户端侧执行契约） |

### 2.2 s2s 领先、值得借鉴之处

#### ① 端点检测（turn-taking）——差距最大

| | tank | s2s |
|---|---|---|
| 静音阈值 | 固定 1000ms（`core/assistant.py:257` 硬编码 `SegmenterConfig()` 默认值） | 64ms（激进） |
| 二次验证 | 无 | **Smart Turn v3.2**：ONNX 模型对整段音频做内容+韵律完整性判断；仅在 Silero 找到 speech→silence 边界后调用一次，CPU 开销极小（`VAD/smart_turn.py`） |
| 停顿后继续说 | 无机制：触发 interrupt + 变成两条独立 user 消息 | **speculative reopen**：说完只是"软结束"，800ms grace 期内继续说则 turn revision+1，音频前缀拼接后重转写，旧 revision 在途输出全部作废（`pipeline/speculative_turns.py`） |
| 迟滞设计 | 单阈值 0.5 | 开始判定延迟确认（384ms 活跃才算 speech start）；续说门槛减半（192ms）；<100ms 碎片不累积，防噪声假 barge-in |

核心哲学：把"说完了吗"从**硬判定**变成**带 grace 期的软判定**，用小的重复计算换自然对话感。

#### ② LLM→TTS 流式切分——首音频延迟的最大单点

- **tank 现状**：`pipeline/processors/brain.py:928-936` 整 turn 攒齐 `full_response_text` 后才发**一次** `AudioOutputRequest`。首音频延迟 = 整个 LLM 生成时间 + TTS 首包。**git 历史核对**（`git log -S "AudioOutputRequest"` 最早引入提交 `fd67044`）：该边界**从未流式过**，不是回归——"TOKEN → TTS immediately" 从未在 Brain→TTS 边界成立。
- **s2s**：token 流式 → 分句（保护 markdown 代码块）→ 攒 3 句 yield 一个 `TTSInput`（`stream_batch_sentences=3`），边生成边合成（`LLM/language_model.py:310-412`）。
- ⚠️ tank 的 `backend/ARCHITECTURE.md` 声称 "TOKEN → TTS immediately (no batching)"，**与代码不符**（文档失实，见 §2.4 T1）。
- 附带发现（现状缺陷，与分批无关）：`normalize_for_tts` 处理 markdown 链接 `[text](url)`（只念 text），但**裸 URL 无任何规则**，会被整串念出。

#### ③ 取消传播：generation 计数 vs 事件脉冲

s2s 的 `CancelScope`：打断时 `generation+1` 并置 `discarding`；每个 handler 在响应开始捕获代数，之后每个 token/chunk 轮询 `is_stale(gen)` 自杀；队列清理在 mutex 下 drain，用 preserve 谓词保住计费/哨兵项。代数计数天然免疫"晚到的旧输出"时序竞态。另有 send loop 细节：**text 事件优先于音频处理**，speech_started 抢在音频批之前——打断低延迟的关键。

#### ④ 管线池的排空纪律

s2s 释放会话时投 `SESSION_END` 控制消息，等它**穿过整条 handler 链回到输出端**才归还 unit；10s 超时警告、180s 超时隔离（宁少一个 unit 不让死 handler 旧输出泄漏给下一个客户端）。tank 的 `close_session` → `assistant.stop()` 等 brain idle，但无等价"排空证明"。

#### ⑤ 功能层

- **OpenAI Realtime 标准协议**（核心战略选择）：实现 GA 事件集核心子集，协议模型直接 import 官方 `openai` SDK 的 pydantic 类型；CI 用 pinned `@openai/agents` stock transport 做互操作测试。收益：任何 Realtime 客户端只改 `base_url` 即可接入。代价：富交互（审批、说话人、工具卡片）需走扩展事件。
- **WebRTC**（aiortc，`oai-events` data channel + RTP 音轨）：与 WebSocket 共享协议层与管线池；浏览器端免费获得 Opus + 内置 AEC。
- **LLM Proxy**（`--enable_llm_proxy`）：把已配置的远程 LLM 再暴露为普通 `/v1/chat/completions` 端点，旁路任务（摘要/标题/后台 agent）与语音管线并发、**永不被语音打断**（不触碰管线队列和 cancel scope）。
- **转写稳定化**：连续两个假设在归一化词边界一致才确认 + 扣留最新边缘词，实现 append-only 的 partial 语义（`handlers/conversation.py` `_stable_transcript_words`）。tank 的 partial 是引擎给什么发什么，UI 会看到文本抖动。
- **客户端侧工具执行契约**：工具声明统一走 `session.update`，执行在客户端；`ToolResult(output, create_response: bool)` 区分"要念给用户"与 fire-and-forget。

#### ⑥ 工程层

- **"真 SDK + 假 pipeline"测试**：服务端用内存 Queue 注入预编排事件保证确定性；客户端侧全是真的（真实 OpenAI SDK 连本地 uvicorn、真实 aiortc peer SDP 握手、Playwright 真浏览器跑 @openai/agents）。跨 Python/Node/浏览器三个 CI job。
- **打包即测**：`package` job 产 wheel → `install-smoke` 矩阵在新 venv 装包 + CLI 冒烟。
- **组件级 README**：`STT/`、`TTS/`、`LLM/`、`openai_realtime/` 每个可替换槽位一份目录式说明，含设计决策与 mermaid 图。
- **AGENTS.md 模式**：只写"AI 助手容易做错的事"（不许擅自 merge、不改写已开 PR 历史、发布 runbook），知识文档下沉组件 README。
- **基准/压测脚本**：`benchmark_tts.py`（warmup/推理/首 chunk 时间/RTF）、`benchmark_stt.py`、`synthetic_conversation_realtime_client.py`（N 并发合成对话压测）。
- CI 全部 action pin 到 commit SHA；GitHub trending 级开源项目的供应链纪律。

### 2.3 s2s 的反面教训（避坑）

- 无界队列 + `should_listen` 恒真：换来全双工 barge-in 的代价是服务端零回声防御——tank 的双层 EchoGuard 在裸麦克风景观是必需品，不能学它删掉。
- macOS 上 `num_pipelines > 1` 与 live transcription 互斥（MLX 全局锁）——多管线池并非免费。
- Apple Silicon 以外平台 OmniVoice/Qwen3 依赖冲突（transformers 4 vs 5）——平台矩阵靠 pyproject 标记硬扛，维护成本高。

### 2.4 本次调研发现的 tank 侧问题（与借鉴无关，独立成立）

| # | 问题 | 位置 |
|---|---|---|
| T1 | **文档失实**：`backend/ARCHITECTURE.md` 声称 "TOKEN → TTS immediately (no batching)"，实际整 turn 攒齐（`brain.py:928-936`）；git 核对确认该边界**从未流式过**（引入提交 `fd67044` 已是攒齐式） | `backend/ARCHITECTURE.md` |
| T2 | **文档过时**：根/后端 ARCHITECTURE.md 仍描述 `src/tank_backend/` 单包布局，实际已是 `core/ + contracts/ + plugins/` 多包 | 同上 |
| T3 | **配置硬编码**：`SegmenterConfig` 用默认值硬编码构造，断句参数（`min_silence_ms=1000` 等）未暴露到 config.yaml | `core/assistant.py:257-258` |
| T4 | **死配置**：sherpa `EndpointConfig` 配置了 rule1/2/3（`enable_endpoint=True`）但 `SherpaASRStream` 从不调用 `is_endpoint`，端点实际全由 Silero VAD 决定 | `plugins/asr-sherpa/asr_sherpa/engine.py:203-217` |
| T5 | **turn 修订缺失**："我想吃……不，还是喝吧" 成为两条独立 user 消息 + 一次可能已被打断的回答 | `context/manager.py:483`（仅 append） |

---

## 3. 改进计划

依赖关系：**基准脚本（P0-3）先行**，为流式 TTS 与端点检测改造提供前后对比数据。P0 全部低风险可立即做；P1 是本计划的核心体验改造；P2 穿插进行；P3 单独立项决策。

### P0 快赢（合计约 2-3 天）

#### P0-1 暴露 VAD/断句配置到 config.yaml（修 T3）

- **改动**：`config.yaml` 新增 `vad:` 段（speech_threshold / min_silence_ms / min_speech_ms / pre_roll_ms / max_utterance_ms）；`core/assistant.py:257` 改为从 `AppConfig` 构造 `SegmenterConfig`，默认值不变。
- **不做**：不改任何默认行为；不动 VAD 内部逻辑。
- **Tests**：unit —— config.yaml 注入非默认值后 `SegmenterConfig` 字段生效；缺省段落回落现默认值。
- **验收**：改 `min_silence_ms` 无需改代码；既有测试全绿。

#### P0-2 清理 sherpa 死 EndpointConfig（修 T4）

- **改动**：删除 `engine.py:203-217` 的 `EndpointConfig` 相关配置（断句已由 Silero VAD 负责，留着误导读者）。
- **Tests**：既有 asr-sherpa 插件测试通过即可（纯删配置）。
- **验收**：`grep is_endpoint` 零命中，行为无变化。

#### P0-3 首音频延迟基准脚本（为 P0-4/P1 量化）

- **改动**：新增 `backend/scripts/benchmark_pipeline.py`——连本地 backend WebSocket，发文本 input（跳过 ASR 环节以隔离 LLM+TTS 路径），计时 `input → 首个音频帧`、`input → 最后音频帧`、LLM 首 token 时间（bus 指标），输出 JSON；跑 N 轮取分布。
- **Tests**：脚本冒烟（本地 backend 可跑、JSON 字段齐全）。不进 pytest 常规套件（需要真实 backend）。
- **验收**：产出改造前基线数字，记录到本文档 §4。

#### P0-4 文档修正（修 T1/T2）

- **改动**：`backend/ARCHITECTURE.md` 修正两处失实（TOKEN→TTS 描述改为现状 + 指向 P0-5 改造项；目录结构更新为 core/contracts/plugins 布局）。**单独提交**，不与代码改动混合。
- **验收**：文档描述与代码一致。

### P0-5 句级流式 LLM→TTS（核心项，约 3-5 天）

把"整 turn 攒齐再 TTS"改为"分句批流式下发"。预期首音频延迟从"整个生成时间"降到"前几句生成时间"。

#### 设计定稿（2026-08-26 讨论，逐项经代码核对）

**目标形态**——只改 `BrainProcessor._process_via_agents` 循环内动作，管线拓扑零改动：

```
                     ┌─> 句批流（新增）──> TTS 实时语音（每 turn N 个 AudioOutputRequest）
LLM token 流 ─> 累积 ┤
                     └─> 全文（维持现状）─> ① _finish_turn：完整回答进对话历史
                                        ② schedule_memory_store：记忆持久化
                                        ③ outbound_voice bus 事件：connector 旁路合成
                                        ④ _extract_and_emit_markdown_images：UI 图片附件
```

```python
sentence_buf = SentenceBuffer(min_sentences=N)   # 中英混合分句器（新模块）
language: str | None = None                      # 首批才判定
full_response_text = ""                          # 仍完整累积（服务上排四个出口）
async for output in gen:
    if self._interrupt_event.is_set(): raise BrainInterrupted()
    bus.post(ui_message)                         # UI 文字流不变
    if output.type == TOKEN:
        full_response_text += output.content
        sentence_buf.feed(output.content)
        for batch_text in sentence_buf.drain_ready():
            if language is None:
                language = detect_language(batch_text, preferred=event.language).language
            yield AudioOutputRequest(content=batch_text, language=language, msg_id=msg_id)
# 循环结束后：flush 尾批 → 图片抽取/outbound_voice/finalize（均对全文，不变）
```

**决策 1：完整累积保留（双出口原则）**。句批只服务实时语音出口；对话历史、记忆、connector、图片附件仍需全文——下一轮 LLM 上下文必须看到完整回答。累积是已有的字符串 `+=`，零额外成本。

**决策 2：语言检测 = LLM 输出首批判定，用户语言作低置信回退先验**。
- TTS 需要语言来选 voice（edge-tts `_voice_for_language` → `voices` map：`en-US-JennyNeural`/`zh-CN-XiaoxiaoNeural`），选错 voice 中文会用英文音色念；
- 主判据必须是 **LLM 输出文本**（要念的就是它）：用户中文提问、要求英文回答的 code-switch 场景，跟用户语言走会选错；
- `detect_language`（`core/language.py`）置信度 < 0.55 时回落 `preferred`——把 `preferred` 从全局默认改为 `event.language`（ASR 判定的用户话语语言），"用户说什么语言回答大概率同语言"是最佳先验；
- 首批定下后整 turn 沿用（跨批换 voice 会音色突变，与现状"整 turn 一个 language"语义一致）。

**决策 3：队列架构不动**（已核对）。
- `builder.build()` 本来就在 Brain 与 TTS 之间自动插有界 `ThreadedQueue`（`pipeline/builder.py:250`，maxsize=10，push 满则阻塞）。现状"每 turn 1 个 item"，改后"每 turn N 个 item"——FIFO 保序，`TTSProcessor.process` 逐 item 消费，**流式只是 item 粒度变细**，拓扑/队列/线程边界零改动；
- 背压方向正确且更有意义：TTS 跟不上 → 队列满 → Brain 挂在 yield → LLM 流暂停消费（音频跟不上就不催生成）；UI 文字流同循环被同步拖慢，文字与语音同步是合理行为；
- EchoGuard 不在 Brain→TTS 之间（config 传入 Brain 内部），按批记录时间滑窗即可，不受影响。

**决策 4：TTS 插件契约零影响**（已核对 `contracts/tank_contracts/tts.py:50`）。
- `generate_stream(text, language, voice, is_interrupted)` 是无状态单调用接口，今天每 turn 调一次，改后每 turn 调 N 次——签名/返回/中断回调全不变，**7 个 TTS 插件（cartesia/chatterbox/cosyvoice/edge/elevenlabs/hume/kokoro）一行不用改**，可换性保持；
- 按引擎类型分化的实际影响与对策：

| 影响 | 说明 | 对策 |
|---|---|---|
| 每批固定开销 | edge-tts 每批新起 Communicate + ffmpeg 子进程（~200-300ms/批）；云 API 每批一个 HTTP 请求；本地模型（kokoro/cosyvoice）常驻、开销最小 | `stream_batch_sentences` 可配，默认 4-5 句偏大；观察后再考虑分引擎调（首期不做） |
| 限流/计费 | 字符计费总量不变，请求数 ×4-7（20 句 ≈ 5 批）→ 云引擎注意 RPM | 现有 QoS 水位机制覆盖，必要时加批间微调 |
| 韵律连续性 | 批边界语调轻微不连续；edge-tts 内部本就按句切（影响小），高质量神经 TTS 可感 | 流式固有权衡，批调大缓解 |

- 反向收益：非流式（整段合成）引擎首批 4-5 句即可出声，之前要等全文；interrupt 粒度从"整 turn"细化到"批间"，打断响应更快；QoS 反馈变成真实的批级水位信号。

**决策 5：normalize 边界情况在分句器层面处理**。`normalize_for_tts` 在 `TTSProcessor` 内对每 item 独立调用（`tts.py:53`），分批天然兼容；跨批次边界交给分句器：

| 情况 | 处理 |
|---|---|
| 代码块跨批（``` 未闭合） | 分句器扣留整块直到闭合，永不切在代码块中间（代码块对 TTS 整体丢弃，扣住不影响延迟） |
| 裸 URL 假句界（`example.com` 的 `.`） | 分句器在 URL 模式内不切 |
| 加粗/斜体跨批（`**重` \| `要**`） | 只在句末标点后切、句内不切；markdown 强调几乎都在句内，概率极低，测试覆盖残留 `**` 容错 |
| 图片 markdown | 分句前先剥 `![](url)`（图片不进 TTS）；`_extract_and_emit_markdown_images` 仍对全文跑（UI 附件不变） |

**决策 6：裸 URL 不念**（顺手修现状缺陷，单独 commit）。markdown 链接现状已只念 text；裸 URL 现状整串念出（"https 冒号斜杠…"），体验差且无意义——有屏客户端 UI 显示完整 markdown 可点，无屏客户端（ESP32）念了也记不住。normalizer 加规则：裸 URL 整体移除；删空的批次由现有 `tts.py:54` "nothing speakable" 跳过兜底。只影响语音出口，LLM 历史/UI 显示不变。

#### 任务拆解（建议 commit 顺序）

| # | 任务 | 文件 | 说明 |
|---|---|---|---|
| 1 | 分句器 `SentenceBuffer` | `core/src/tank_backend/pipeline/text/sentence_buffer.py`（新） | 纯函数模块：中文标点 `。！？；…` 直切；英文 `.!?` 切并排除小数/缩写；代码块扣留；URL 内不切；`feed(token) → drain_ready() / flush()` 接口 |
| 2 | `AudioOutputRequest` 加 `msg_id` | `core/events.py:9` | 现有 `content/language/voice` 不动，新增可选字段默认 None，向后兼容 |
| 3 | Brain 流式改造 | `brain.py:825-975` | 按上方目标形态；finalize/outbound_voice/图片抽取仍在循环后对全文 |
| 4 | normalizer 裸 URL 规则 | `tts_normalizer.py` | 独立 commit（修现状缺陷）；空批兜底已有 |
| 5 | config 暴露 | `config.yaml` + `config/models.py` | `brain.stream_batch_sentences`（默认 5） |
| 6 | 客户端播放核查 | web/cli/device（只读确认） | web 端 `nextStartTime` 指针天然无缝吃连续 chunk；CLI/device 顺序播放——只需确认无"turn 结束才播"的假设 |

#### 风险与对策

- 中文分句质量 → 分句器纯函数、独立单测全覆盖；
- interrupt 时半句状态 → 沿用现有 `_finish_turn` 部分持久化；批间检查中断，粒度更细；
- 长时间背压拖住 LLM 流 → 队列 maxsize=10 + TTS RTF<1 正常不会持续满；出现时 LLM 流在 SDK 缓冲，恢复后继续。

#### Tests

- unit（分句器）：中文/英文/混合/代码块跨 token/URL 内点号/无标点长句/markdown 强调残留容错；
- unit（normalizer）：裸 URL 移除、删空跳过；
- unit（Brain）：流式产出多个有序 `AudioOutputRequest` 且同 `msg_id`；首批判定语言、后续批次沿用；interrupt 后不再产出后续批；finalize 仍以全文执行一次；
- E2E（`test/` 现有 feature 文件加 scenario）：长回答场景，客户端在响应文本结束前收到首个音频帧。

#### 验收

- P0-3 基准对比：首音频延迟 ≤ 前 N 句生成时间 + TTS 首包（长回答场景显著下降，数字回填 §4）；
- 全量验证清单（§5）通过。

### P1 端点检测升级（约 1-2 周）

#### P1-1 Smart Turn 式 ML 端点验证

- **改动**：
  1. 新增 Smart Turn 模块（`pipecat-ai/smart-turn-v3` ONNX，CPU，`intra_op=1`）：Silero 判定 speech→silence 边界后对整段音频（取尾部 8s）单次推理；
  2. `min_silence_ms` 默认从 1000 降到 ~250ms（经 P0-1 已可配），由 Smart Turn 裁决：`complete`（概率 > 0.5）→ 立即提交；`incomplete` → 延迟 600ms 再启动 STT/LLM，给续说留窗口；
  3. 模型加载失败/推理异常 → **fail-open 回退**纯静音策略（回 1000ms 阈值）；
  4. 阈值与延迟参数进 config.yaml。
- **风险**：Smart Turn v3 以英文训练为主，**中文话语完整性判断精度未验证**——上线前用中文音频做 A/B（基准脚本 + 人工对话评测）；效果不佳则仅对英文会话启用或调高阈值，回退策略兜底。
- **Tests**：unit —— Smart Turn 包装器（mock ONNX session）complete/incomplete/异常回退三分支；unit —— VAD 集成后端到端时序（mock 判定）；E2E —— 语音场景断句延迟对比。
- **验收**：中文+英文实测断句延迟 < 现基线，误断率不升；模型缺失时行为与现状一致。

#### P1-2 speculative reopen / turn revision（修 T5）

> **落地说明（2026-08-31）**：已实现，设计较下文简化——P1-1 的 hold 已覆盖 commit 前合并，
> 故无需 `SpeculativeTurnTracker` 阻塞机制。实际形态：`VADStream` 在静音/超时提交后保留
> reopen 候选（turn_id + PCM 前缀 + revision），恢复语音落在 `speculative_reopen_ms`
> （默认 800ms，流时间戳域）内则 revision+1 拼接前缀重转；VADProcessor 发
> `turn_reopened`，Assistant 提前取消在途 Brain/TTS；ASR 整段重转写并复用原 msg_id
> （三端 UI 原地更新）；ContextManager 对同 turn_id 的修订**替换**原 user 消息并截断
> 其后孤儿回复（身份不匹配则安全回退为 append）。显式结束（PTT flush）不触发 reopen。

- **改动**：
  1. 管线消息（`BrainInputEvent` 等）加 `turn_id` / `turn_revision` 字段；
  2. VAD 软结束：段完成不再立即终局，进入 grace 期（默认 800ms，`speculative_reopen_ms`）；grace 内续说 → revision+1，音频前缀拼接重新转写；
  3. 新增 `SpeculativeTurnTracker`（线程安全，参考 s2s `pipeline/speculative_turns.py`）：下游（Brain/TTS）commit 输出前阻塞等 grace 过期；revision 前移后在途旧输出作废；
  4. 与现有 interrupt 机制的交互：reopen 优先于 interrupt 触发（同一用户 turn 的延续不算打断）；UI 侧 transcript 原地更新而非新消息。
- **依赖**：P1-1（Smart Turn 的 incomplete 判定是 grace 期长度的依据）。
- **Tests**：unit —— Tracker 的 revision 竞态（grace 内 bump、commit 后不可 reopen、并发 commit 暂停）；unit —— VAD 前缀拼接；E2E —— "停顿后继续说"场景输出为合并后单条消息、无孤立回答。
- **验收**：T5 场景实测正确；正常无停顿对话零额外延迟。

### P2 体验与工程细节（穿插进行，每项 0.5-2 天）

| 项 | 改动 | Tests |
|---|---|---|
| partial 转写稳定化 | `asr.py` `_post_partial`：连续两个假设归一化词边界一致才确认 + 扣留最新边缘词 | unit：固定假设序列断言确认/扣留行为 |
| 会话释放排空证明 | `close_session` 借鉴 `SESSION_END` 穿链确认 + 超时告警 | unit：释放后队列残留可见/超时路径 |
| plugins/ 组件 README | 18 个插件各一份简短 README（能力、flag、语言支持），模式照 s2s `TTS/README.md` | 无（文档） |
| docker 镜像冒烟 CI | build 镜像 → 干净容器起服务 → `/health` 通过（对应 s2s install-smoke） | CI job 本身 |
| 基准脚本扩展 | P0-3 脚本加语音路径（合成 PCM 走 VAD）与并发压测模式 | 脚本冒烟 |

### P3 战略评估项（单独立项，不在本计划内实施）

1. **Realtime 兼容端点 `/v1/realtime`**：动机（第三方客户端/机器人零适配接入 + WebRTC 路径）、事件映射表（审批/说话人/工具卡片 → 扩展事件）、`@openai/agents` 互操作测试方案、与现有 `/ws/{session_id}` 双协议并存策略。**建议先出独立设计文档再动手**。
2. **LLM Proxy**：若存在旁路任务需求（会话摘要、标题生成），可单独先行——不触碰管线队列，实现轻。

### 计划执行顺序

```
P0-1 ─┬─> P0-5（句级流式，核心）
P0-2 ─┤
P0-3 ─┘   P0-4（文档，独立提交）
              │
              v
        P1-1（Smart Turn）──> P1-2（speculative reopen）
              │
              v
             P2（穿插）           P3（另立项）
```

---

## 4. 基线记录（P0-3 产出后回填）

测量方法：`backend/scripts/benchmark_pipeline.py`（文本输入，长回答 prompt，本地 backend，n=3 + 1 warmup；2026-08-26）。语音行：`--mode voice`（E2E 同款「你好」WAV 走 VAD/ASR，尾静音窗 2.5s，n=3 + 1 warmup；2026-08-31）。

> **2026-09-01 口径修正**：脚本原先在音频流完（含 2.5s 注入静音窗）**之后**才开始收消息，`endpoint_ms` 被地板在静音窗长度——旧中文值 2.63s ≈ 2.5s 窗 + 0.13s 开销，不反映真实断句速度，**作废**。修复为收发并发、且取**首次** `processing_started`（speculative reopen 重发不覆盖）。下表断句延迟 = `processing_started 时刻 − 夹具语音结束点`（语音长度已知：你好 2.2s、how_are_you 1.6s；夹具结构一致：语音 + 2.5s 数字静音尾）。英文夹具 `test/fixtures/audio/how_are_you.wav`（edge-tts en-US-JennyNeural 合成）。附带观察：带逗号停顿的英文话语会触发 Smart Turn 误断 → reopen 合并循环（观测全链路 5.5s，真实产品行为而非测量口径问题）；当前 ASR 为 ElevenLabs 云端（每段 ~1.1s flush 延迟），换引擎数字会变。

| 指标 | 改造前基线 | P0-5 后 | P1 后 |
|---|---|---|---|
| 首音频延迟（文本输入，长回答） | p50 **8.0s**（7.2 / 8.0 / 51.4s，首轮 LLM 冷启动离群） | p50 **3.2s**（3.0 / 3.2 / 4.9s，**-60%**） | — |
| 其中：LLM 首 token 到客户端 | p50 1.6s | p50 2.0s（LLM 波动，非回归） | — |
| 其中：turn 生成完毕（processing_ended） | p50 7.2s | p50 5.7s | — |
| 末音频延迟（整段播完） | p50 52.6s（~1000 chunks / 800+ 字） | p50 41.8s（~850 chunks） | — |
| 首音频延迟（语音输入） | 待测 | 待测 | p50 **7.3s**（自发声起，含 4.7s 语音流；`--mode voice`，2026-08-31） |
| 断句延迟（说完→processing_started，中文） | 待测 | — | p50 **1.51s**（"你好"被 Smart Turn 判 incomplete（p≈0.02）→ 600ms hold 后提交，设计内代价；修复口径后重测 2026-09-01，旧值 2.63s 作废见上） |
| 断句延迟（英文） | 待测 | — | p50 **0.71s**（首个候选 ~350ms 即判 complete（p≈0.99）立即提交；`--audio how_are_you.wav`，2026-09-01） |

基线确认了 §2.2② 的诊断：`first_audio（8.0s）≈ turn_end（7.2s）+ TTS 首包`——音频确实等整 turn 生成完才出声，而 LLM 首 token 1.6s 就到了客户端。P0-5 后关系反转：`first_audio（3.2s）< turn_end（5.7s）`——首批 5 句生成完即出声，E2E 场景（`@streaming-audio` profile）断言首音频帧先于文本流结束到达，已通过。

---

## 5. 验证清单（每个阶段完成后全量执行）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check src/ tests/`（多包布局下在 core/ 与各改动插件分别执行）
4. `cd backend && uv run pytest`（后端单元测试全量）
5. `cd backend && uv run pyright <改动文件>`（禁止 `# type: ignore`）
6. `cd cli && uv run ruff check src/ tests/`
7. dev server 日志检查：`tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`（空输出即通过，不重试）
8. `cd test && pnpm test`（E2E，14+ scenarios，需 backend + frontend 运行中）

**测试失败政策**：任何阶段发现红测试——无论是否本阶段引入——修复后才算完成。

---

## 6. 参考文件索引（s2s 侧）

| 主题 | 路径（相对 `/home/zbcjackson/src/speech-to-speech/`） |
|---|---|
| 通用 handler 基类 | `src/speech_to_speech/baseHandler.py` |
| VAD + Smart Turn + speculative reopen | `src/speech_to_speech/VAD/vad_handler.py`、`VAD/smart_turn.py`、`pipeline/speculative_turns.py` |
| 句级切分流式 | `src/speech_to_speech/LLM/language_model.py`（`_process_printable_text`）、`LLM/utils.py` |
| 取消传播 | `src/speech_to_speech/pipeline/cancel_scope.py` |
| Realtime 协议层（含 358 行设计文档） | `src/speech_to_speech/api/openai_realtime/`（`README.md` 必读） |
| 管线池 / send loop / 排空隔离 | `src/speech_to_speech/api/openai_realtime/websocket_router.py`、`pipeline_unit.py` |
| 后端注册表 / 两阶段 CLI 解析 | `src/speech_to_speech/backend_registry.py`、`s2s_pipeline.py` |
| 历史 compaction | `src/speech_to_speech/LLM/chat.py`、`compaction_prompt.py` |
| 互操作测试范式 | `tests/openai_realtime/agents_sdk_server.py`、`demo/tests/` |
| 基准/压测脚本 | `scripts/benchmark_tts.py`、`scripts/synthetic_conversation_realtime_client.py` |
