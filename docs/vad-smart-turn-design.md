# VAD + Smart Turn 端点检测:实现与设计

> 撰写日期:2026-09-01。描述 `backend/core` 中 VAD / 端点检测 / speculative reopen 的**当前实现**及其设计原因。
> 背景分析见 [s2s-comparison-and-improvement-plan.md](s2s-comparison-and-improvement-plan.md) §2.2①(端点检测差距)与 §3 P1-1/P1-2(对应改造项,均已落地)。

---

## 1. 问题:端点检测在解什么

语音对话里有一个看似简单的问题:**用户说完了吗?**

- VAD(Voice Activity Detection)只能回答"**声音**停了吗"——它是声学判定;
- 端点检测(end-of-turn / turn-taking)要回答"**话**说完了吗"——这是语义 + 韵律判定。

两者不等价。"我想吃……(想了两秒)……还是喝吧"中间声音停了,但话没说完。这个不等价造成一个经典两难:

| 静音阈值 | 收益 | 代价 |
|---|---|---|
| 高(tank 改造前,固定 1000ms) | 不会误断停顿 | 每轮对话平白多等 ~1s,体验迟钝 |
| 低(s2s 的 64ms) | 响应快 | 停顿被切成两条消息,触发一次本不该有的回答 |

**核心哲学**(沿用 s2s 的分析):把"说完了吗"从**硬判定**变成**带 grace 期的软判定**——尽早给出候选结论,但保留反悔窗口,用小的重复计算换自然对话感。tank 的现状是这套哲学的三层落地:

1. **快速候选边界**:Silero 只需 ~250ms 静音就触发一次候选边界(而不是等 1000ms);
2. **ML 裁决**:Smart Turn 分类器对整段音频判断"完整 / 不完整",不完整则 hold 住不开转写;
3. **Speculative reopen**:即使已经提交,800ms 内恢复的语音仍会并回同一个 turn,取消在途回答、原地修订。

实测:中文断句延迟(说完 → processing_started)p50 **2.63s**(含 4.7s 语音流,2026-08-31 基准,`benchmark_pipeline.py --mode voice`),其中端点判定环节只占 ~350ms(见 §4.4 时序)。

---

## 2. 组件分层

```
┌──────────────────────────────────────────────────────────────┐
│ SmartTurnAnalyzer          (audio/input/smart_turn.py)        │
│ 无状态分类器:整段音频 → P(complete)。进程级一份。              │
├──────────────────────────────────────────────────────────────┤
│ VADEngine                  (audio/input/vad.py)                │
│ 进程级单例:加载 Silero ONNX 模型一次,create_stream() 出流。    │
├──────────────────────────────────────────────────────────────┤
│ VADStream                  (audio/input/vad.py)                │
│ 会话级状态机:VADIterator + pre-roll + 端点策略 + reopen 状态。  │
│ 持有 SmartTurnAnalyzer 引用(可 None)。                       │
├──────────────────────────────────────────────────────────────┤
│ VADProcessor               (pipeline/processors/vad.py)        │
│ 管线适配:AudioFrame → VADResult/AudioFrame;                   │
│ 回声防御 Layer 1 阈值切换;turn_reopened/speech_end 总线事件。   │
├──────────────────────────────────────────────────────────────┤
│ 下游联动                                                        │
│ ASRProcessor:msg_id 复用、修订整段重转写(asr.py)              │
│ Assistant:turn_reopened → 取消在途 Brain/TTS(core/assistant.py)│
│ ContextManager:同 turn_id 修订替换原 user 消息(context/manager.py)│
└──────────────────────────────────────────────────────────────┘
```

**分层原因**:

- **模型加载贵、流创建廉价**——Silero 模型进程级加载一次(`VADEngine`),每个会话只新建轻量的 `VADStream`(自己的 `VADIterator` + 状态缓冲,共享底层权重)。旧接口 `SileroVAD(cfg)` 直接构造会私加载一份模型,已标记 deprecated。
- **分类器无状态、VAD 有状态**——Smart Turn 是纯函数式推理(`predict(audio) → SmartTurnResult`),不持有会话状态;所有"说到哪了"的状态都收在 `VADStream`。这样分类器天然并发安全(仅推理处加锁),会话隔离天然成立。
- **`VADStream` 不知道管线存在**——纯音频逻辑,可在无管线环境下单测(`tests/test_vad.py` 直接喂帧);管线语义(总线事件、阈值切换、哨兵)全部留在 `VADProcessor`。

**接线**:`server.py` 启动时 `SmartTurnAnalyzer.from_config(config.smart_turn)`(永不抛异常,失败得 `None`)→ 放入 `AppContext` → Assistant 构造 `VADStream` 时注入。`None` 就是"退回纯静音策略"的信号(见 §4.3)。

---

## 3. VADStream 帧处理:基础状态机

### 3.1 输入路径:20ms 帧 → 512 样本 chunk

```
AudioFrame(20ms, 320 samples @16kHz, 流时间戳 timestamp_s)
  → 追加进 _chunk_buffer
  → 凑满 512 样本 → VADIterator(Silero,转换沿触发)
  → 不足 512 的尾部(leftover)→ RMS 能量阈值(0.01)补充判定
```

两个值得注意的细节(都有测试锁定):

- **Silero 契约要求 512 样本/块**(16kHz),而管线帧是 20ms/320 样本,所以必须有 re-buffer 层(`_chunk_buffer`)。
- **leftover 能量 OR 不是可删的优化,是修 bug 的**:`VADIterator` 是**转换沿触发**——只在"静音→说话"和"说话→静音"的跳变帧返回结果,持续说话期间的整 chunk 一律返回 None。如果只看 chunk 结果,一段"大帧 + 带声 leftover"会被判成静音,`_last_voice_at_s` 冻结,静音超时被误触发,造成**说话说到一半被切断**。所以 leftover(以及 partial chunk)用 RMS 能量兜底,与 chunk 结果做 OR(`_has_voice_activity`;`test_sustained_speech_tracked_across_big_frames`)。

### 3.2 状态机

```
NO_SPEECH ──检测到语音──► START_SPEECH(输出 VADResult,ASR 开会话)
                            │
                            ▼
                         IN_SPEECH(转发 AudioFrame 给 ASR 流式识别)
                            │
        ┌───────────────────┼─────────────────────┐
   静音超时(经端点策略)  max_utterance_ms 上限   flush()(PTT/打断)
        │                   │                    │
        ▼                   ▼                    ▼
                     END_SPEECH(输出 VADResult + 完整 utterance PCM)
```

每次 `process_frame(pcm, timestamp_s)` 的处理顺序:

1. 帧无条件进 pre-roll 环形缓冲(默认 200ms);
2. **先查静音/hold 超时**(基于上一帧的 `_last_voice_at_s`,见下),该提交的提交;
3. 再做当帧的语音活动判定;
4. 按状态机转移。

**"先查超时、后判当帧"是有意的顺序**:超时判定必须用"截至上一帧"的状态。若先处理当帧,一帧带声会把 `_last_voice_at_s` 顶到当前,边界判定就永远晚一帧;反过来,若用户恰好在 hold 到期那一帧恢复说话,旧 turn 会先按超时提交——这个"迟到"由 reopen 窗口兜住(§5.4),不丢内容。

**时间域**:全部判定基于 `timestamp_s`(音频流的采样时间戳),不是墙钟。这样基准脚本回放 WAV、真实麦克风、设备端推流都有一致的时序语义;reopen 窗口的 800ms 也是这个域(memory 里的"P1-1/P1-2 已落地:reopen 窗口 800ms 流时间戳域"即指此)。

### 3.3 卫生规则

| 规则 | 参数 | 原因 |
|---|---|---|
| 最短语音 | `min_speech_ms=200` | <200ms 的"语音"几乎全是噪声/咳嗽,丢弃,不发下游 |
| 最长语句 | `max_utterance_ms=20000` | 硬顶:无论是否检测到结束,20s 强制提交,防止单一状态永久占据会话 |
| pre-roll | `pre_roll_ms=200` | VAD 触发天然滞后于发声,把起始前 200ms 音频拼回 utterance,避免吞字 |

所有状态重置(`_finalize_utterance`、min_speech 丢弃、`flush`)统一走 `_reset_speech_state()`,它同时清掉 Smart Turn hold 状态——保证任何路径下**hold 中的 utterance 不可能泄漏进下一个 turn**。

---

## 4. 端点策略:两级判定(核心设计)

### 4.1 两条路径

`VADStream` 构造时确定端点静音阈值:

```python
self._endpoint_silence_ms = (
    smart_turn.candidate_min_silence_ms   # 250ms,有 analyzer
    if smart_turn else cfg.min_silence_ms # 1000ms,无 analyzer
)
```

在 `candidate_min_silence_ms` 静音后触发候选边界,调 Smart Turn 裁决:

- **complete** → `_finalize_utterance`,turn 提交进 ASR;
- **incomplete** → hold:`_st_pending = True`,utterance 保持 open,deadline = 当前 + `incomplete_delay_ms`(600ms);
- hold 期间恢复语音 → 清 hold,同一 utterance 继续,下一个边界对**更长的音频**重新裁决;
- hold 到期仍静音 → 到期提交(fail-forward,模型可能判错,不能永远等)。

无 analyzer 时:静音满 `min_silence_ms`(1000ms)直接提交——即改造前的行为,Smart Turn 整条链路(含 hold)全部短路。

### 4.2 Smart Turn 分类器本体

`pipecat-ai/smart-turn-v3`(v3.2)ONNX,Whisper-encoder 衍生的音频分类器:

- **输入契约**:mono float32,重采样到 16kHz(线性插值),**取尾部 8s**(不足则左侧补零),WhisperFeatureExtractor 出 `(1, 80, 800)` mel 特征;shape 不符直接 raise(模型契约防呆)。
- **输出**:P(complete) ∈ [0,1],**严格大于** `threshold`(0.5)判 complete(边界值判不完整——不确定时宁可多等 600ms,不要误断)。
- **短路**:<100ms 的音频(<1600 样本)不做推理,直接判 complete——这么短的"语音"分类器没有判别力,当噪声放行即可,省一次推理。
- **成本控制**:ONNX session 固定 `ORT_SEQUENTIAL` + `intra_op_num_threads=cpu_count`(默认 1)+ 全量图优化;构造时用 1s 静音 warmup,把首次推理的延迟移出对话路径;推理在锁内(feature extractor + session 都非线程安全)。

### 4.3 三处 fail-open——设计的第一原则

分类器是**增强项**,它的任何故障都不允许挂死或丢掉用户的 turn:

| 故障 | 行为 | 代码位置 |
|---|---|---|
| `smart_turn.enabled=false` / 模型文件缺失 / 加载异常 | `from_config` 返回 None,退回纯静音策略(1000ms),行为与改造前完全一致 | `smart_turn.py` `from_config`(模型缺失记 INFO——新装环境这是预期状态) |
| 单次推理异常 | 记 warning,**立即提交**该边界,本 turn 不受影响 | `vad.py` `_adjudicate_endpoint` |
| incomplete hold 到期仍静音 | 到期提交(fail-forward) | `vad.py` `process_frame` hold 分支 |

与之配套:**`vad.min_silence_ms` 必须保持保守默认(1000ms)**。它是回退路径——一旦 Smart Turn 缺席,它就是唯一的端点依据;把它调成激进值,回退就不再是安全网(config.yaml 注释与 `SmartTurnConfig` docstring 都强调了这一点)。

**时序参数放在 analyzer 上而不是 config 上**(`candidate_min_silence_ms` / `incomplete_delay_ms` 是 `SmartTurnAnalyzer` 的属性):`VADStream` 只接收一个 `smart_turn` 对象就拿到完整端点策略;回退路径(None)不需要任何额外配置。一个对象 = 一套策略。

### 4.4 时序账

```
用户说完(最后一声)
  │
  │ ~250ms  candidate_min_silence_ms(Silero 触发候选边界)
  │          (实际 ~350ms:Silero 的语音时间戳滞后声学偏移 ~100ms,
  │           config.yaml/SmartTurnConfig 均有注明)
  │ ~几十ms  Smart Turn CPU 推理(8s 尾窗,单线程;构造时已 warmup)
  │
  ├─ complete ──► 提交:END_SPEECH → ASR 终转写 → Brain
  │
  └─ incomplete ─► hold 600ms
                     ├─ 期间恢复语音 ─► 合并继续,下一边界重新裁决
                     └─ 静音到期 ────► 提交(最长额外 600ms)
```

对比改造前:每轮固定 +1000ms。现在的期望成本 ≈ 250~350ms + 推理(大概率 complete,无 hold);只有模型认为话没说完时才付 600ms hold——而这恰恰是"值得付"的场景(用户真的在停顿)。

**per-boundary 而非 per-chunk**:Smart Turn 只在 Silero 判定 speech→silence 边界时跑一次,**成本不随音频流长度增长**。这是它可以用 CPU(单线程)在线跑的根本原因。

**中文风险**:smart-turn-v3 以英文语料训练为主,中文话语完整性判断**未经验证**。config 注释给出降级开关——若中文 turn-taking 劣化,直接 `smart_turn.enabled: false`,整链路退回纯静音策略,无需改代码。

---

## 5. Speculative Reopen(turn revision)

### 5.1 动机(修复 T5)

> "我想吃……(静音超过阈值,提交,开始回答)……不,还是喝吧。"

改造前:两句成为**两条独立 user 消息**;"我想吃"触发一次错误回答并被第二句打断,对话上下文里留下两条 user + 一条被打断的 assistant 回复,模型下一轮看到的语境是破碎的。

hold 解决的是"**提交前**的停顿"(模型判 incomplete 时);reopen 解决的是"**提交后**的反悔"——hold 到期提交了、或模型判 complete 但用户又续说了。两层互补,合起来覆盖整个"停顿后继续说"谱系。

### 5.2 机制

**提交时 arm 窗口**(`_finalize_utterance(arm_reopen=True)`,静音/max-utterance 路径的默认):保留五元组——

```python
_reopen_turn_id, _reopen_revision, _reopen_pcm(整段utterance),
_reopen_started_at_s, _reopen_last_voice_at_s
```

**下一个语音起点消费窗口**(START_SPEECH 分支),四条件全满足才 reopen:

```python
prefix_pcm 存在 and turn_id 存在
and (timestamp_s - _reopen_last_voice_at_s) * 1000 <= speculative_reopen_ms  # 800ms
```

命中则:

- `turn_id` 沿用,`revision += 1`(链式:连续多次续说 revision 1→2→3…);
- `utterance_pcm = [prefix_pcm, *pre_roll_parts, pcm]`——**已提交音频拼回最前**,加上续说起点的 pre-roll;
- `_speech_started_at_s` 锚定到**原始 utterance 的起点**——"合并后的 turn 就是那个 turn",所以时长上限(`max_utterance_ms`)和对外报告的 started_at 都以它为准,不会因拼接而延长寿命或错报时间。

未命中(窗口过期/首次语音)则 `_clear_reopen_state()`,正常起新 turn,`turn_id = turn_{started_at:.3f}`,revision=0。

**惰性过期**:窗口没有定时器。五元组静静躺着,直到下一次语音起点被读取——要么消费,要么因超窗被丢弃。端点检测是高频热路径,不为低概率事件加定时器/后台任务。

### 5.3 显式结束永不 reopen

```python
def flush(self, now_s):    # push-to-talk、打断 flush 走这里
    ...
    return self._finalize_utterance(now_s, arm_reopen=False)
```

PTT 松手 / 客户端 EOU 信号 / pipeline flush 是**用户或客户端明确声明的硬边界**——"我说完了"是意图表达,不是 VAD 猜的。对明确意图再去猜"你是不是还想接着说"只会制造意外(`test_flush_finalized_turn_does_not_reopen`)。

### 5.4 与 hold 的边界衔接

一个精确覆盖衔接处的时序:用户在 hold 到期**之后**一帧才恢复说话——

```
hold 到期帧:先查超时 → 旧 turn 提交(arm_reopen=True,窗口开启)
下一帧:语音恢复 → 未在 hold 内,但落在 800ms reopen 窗口内 → reopen,revision+1
```

超时检查在语音判定之前(§3.2)使这个交接是确定性的:hold 管"到期前",reopen 管"到期后",中间没有缝隙。

### 5.5 下游联动:revision 如何贯穿管线

`VADResult` 携带 `turn_id` / `turn_revision`,三层各自消化:

| 层 | 收到 revision>0 时做什么 | 为什么 |
|---|---|---|
| **VADProcessor** | 发 bus 消息 `turn_reopened{turn_id, revision}` | 对外宣告,解耦:谁关心谁订阅 |
| **Assistant** | 立即 `_interrupt_pipeline("turn_reopen")`(若管线忙) | **不等第一个 ASR partial**——在途的 Brain/TTS/Playback 是针对旧 revision 的回答,越早取消,泄漏给用户的杂音越少 |
| **ASRProcessor** | START_SPEECH:复用记忆中的原 `msg_id`(链未知则兜底新 id);partial 前面拼上已提交文本,UI 看到"增长的合并语句";END_SPEECH:丢弃流式会话,对**合并后的完整 PCM 整段重转写** | 复用 msg_id → 三端 UI **原地更新**用户消息而非新开一条;流式会话只见过续说尾部,只有整段重转写才能得到连贯文本 |
| **ContextManager** | 同 `turn_id` 且 revision 更高 → **替换**原 user 消息,并截断其后的孤儿 assistant 回复;身份不匹配(如重启后链丢失)→ 安全回退为 append | 对话上下文里"我想吃……还是喝吧"必须是**一条**消息,模型下一轮才看到自洽语境 |

注意打断语义:`_interrupt_pipeline` 对 ASR 之前的链路不动(§6 同款设计)——用户续说的语音持续转写,被取消的只是对旧文本的回答。reopen 与普通打断共用取消机制,但触发时机不同:普通打断等 ASR 出首个 partial(`speech_detected`),reopen 在 VAD 层就知道"这是旧 turn 的延续",可以立刻动手。

---

## 6. 与回声防御的耦合(Echo Guard Layer 1)

`VADProcessor` 订阅 `playback_started` / `playback_ended`:

- 播放开始 → `vad.set_threshold(0.85)`(`echo_guard.vad_threshold_during_playback`);
- 播放结束 → `reset_threshold()` 回默认 0.5。

**为什么需要**:tank 的设备端(CoreS3 等)麦克风与扬声器同板、无硬件 AEC,TTS 从喇叭漏进麦克风,若不压制,助手会被自己的声音触发。播放期把 Silero 阈值抬到 0.85,只有近场大声说话才算语音。这是回声防御的第一层,文本重叠检测(EchoGuard,Layer 2)是第二层,均 fail-open,详见 backend/ARCHITECTURE.md。

**与 Smart Turn 正交**:阈值切换只改 Silero 的灵敏度(什么算"有语音"),不改端点策略(静音多久怎么裁决)。播放期语音被抑制 → 候选边界不会因回声触发 → Smart Turn 也不会被喂进回声段。两层机制互不感知、互不干扰。

---

## 7. Push-to-Talk 与 flush 路径

客户端显式结束(PTT 松手)不直接调 `VADStream.flush()`——那会从另一个线程碰 VAD 的内部状态。取而代之:

```
Assistant.end_utterance()
  → pipeline.push_at("vad", END_OF_UTTERANCE 哨兵)
  → VAD 消费线程在自己的 process() 里遇到哨兵(排完所有在途音频帧之后)
  → vad.flush(time.time()) → END_SPEECH 结果正常走下游
```

**原因**:`VADStream` 不是线程安全的,`_in_speech` 等状态只应被 VAD 消费线程触碰。哨兵进队列 = 让终结动作**串行化到 VAD 自己的线程**,天然无竞态。interrupt 的 pipeline flush 事件同理(`handle_event` 里 flush 后继续传播)。

flush 终结的 turn:`arm_reopen=False`(§5.3),不发 reopen 窗口。

---

## 8. 配置参考

`backend/core/config.yaml` → `vad:` 与 `smart_turn:` 段。`vad:` 直接解析进 `SegmenterConfig`(`audio/input/types.py`,无镜像 dataclass,单一事实来源);`smart_turn:` 解析进 `SmartTurnConfig`(`config/models.py`)。

### `vad:`(utterance segmentation)

| 参数 | 默认 | 作用 | 调参提示 |
|---|---|---|---|
| `speech_threshold` | 0.5 | Silero 判语音的概率阈值 | 播放期会被动态抬到 0.85(回声防御),勿把默认调太高否则轻声说话不识别 |
| `min_silence_ms` | 1000 | **回退路径**的端点静音 | 仅在 Smart Turn 缺席时生效;保持保守,它是安全网 |
| `min_speech_ms` | 200 | 最短有效语音 | 更小 → 更多噪声进 ASR |
| `pre_roll_ms` | 200 | 起始前补录 | 吞首字则调大 |
| `max_utterance_ms` | 20000 | 强制提交上限 | — |
| `speculative_reopen_ms` | 800 | 提交后可续并窗口(流时间戳域) | 0 关闭 reopen;显式结束(PTT)不受此参数影响,永不 reopen |

### `smart_turn:`(ML 端点裁决)

| 参数 | 默认 | 作用 | 调参提示 |
|---|---|---|---|
| `enabled` | true | 总开关 | false = 整链路退回纯静音策略 |
| `model_path` | null | 模型路径 | 缺省 `../models/smart-turn/smart-turn-v3.2-cpu.onnx`;缺失只降级不报错;下载:`uv run python scripts/download_models.py smart-turn` |
| `threshold` | 0.5 | P(complete) 判定线(严格大于) | 调高 → 更容易判 incomplete → 更多 hold,更不易误断但更慢 |
| `candidate_min_silence_ms` | 250 | 候选边界静音量 | 实际边界 ~+100ms(Silero 时间戳滞后);决定断句延迟的主参数 |
| `incomplete_delay_ms` | 600 | incomplete 后的 hold 时长 | 决定"停顿后继续说"能在多长停顿内不切断 |
| `cpu_count` | 1 | ONNX intra-op 线程 | per-boundary 推理,通常无需加 |

---

## 9. 测试覆盖

| 文件 | 覆盖 |
|---|---|
| `backend/core/tests/test_vad.py` | 基础状态机、chunk 重缓冲与边界、pre-roll、min_speech 丢弃、max_utterance 硬顶、flush;Smart Turn:complete 提交 / incomplete hold / hold 中续说合并 / 推理异常回退 / flush 清 hold / 带 analyzer 的 max_utterance;reopen:窗口内续并、超窗新 turn、0 关闭、链式 revision 递增、flush 终结不 reopen、大帧持续语音追踪(leftover OR 回归) |
| `backend/core/tests/test_smart_turn.py` | 8s 尾窗截取 / 左补零 / 非 16k 重采样 / 非 mono 拒绝 / 阈值严格大于 / <100ms 短路 / 非有限概率 raise / 特征 shape 契约 / disabled 与缺模型返回 None |

---

## 10. 已知限制与后续方向

1. **中文质量 A/B 已完成(2026-09-01,TTS 合成夹具,离线评测 `scripts/eval_smart_turn.py` + `scripts/smart_turn_ab/`)**:
   - zh:误断率 **3/6**(误判的全部是"内容听起来像完整祈使句"的从句——"帮我查一下明天的天气,"/“如果明天下雨的话,”,P 0.94-0.99),过度扣留 0/6;en 控制组 1/4(同一失败模式)。
   - **阈值扫描:中文两类概率分布重叠**(误判 incomplete 得分 0.94-0.99,判对 complete 0.58-0.98),无可用工作点——threshold 0.99 才清零误断,但 6/6 complete 全部过度扣留(每轮 +600ms);en 在 threshold 0.95 有零误断零扣留的工作点。
   - 缓解:生产中误断多数被 800ms reopen 窗口挽救(停顿内续说即合并),实际伤害集中于"停顿 >800ms 后续说"的场景;基线对比——纯静音策略对任何 ≥ 静音阈值的停顿误断 100%,Smart Turn 仍减半。
   - 结论:保持 `enabled: true` 观察,暂不调阈值;若实测不能接受则对中文会话 `enabled: false`(降级无损)。**待办**:人工真录音补测(TTS 无法复现真实犹豫韵律),样本收入 `scripts/smart_turn_ab/`。
2. **候选边界实际 ~350ms**:250ms 配置 + Silero 时间戳 ~100ms 滞后。若要再压,需换更细粒度的边界信号,收益/复杂度比当前不高。
3. **reopen 只覆盖 VAD 域**:文本输入、PTT 显式结束不存在 reopen(前者无 VAD,后者是明确意图——by design)。
4. **每个语音起点重算 reopen 判定**:惰性过期无定时器,换来的是 reopen 五元组在无人续说时多驻留最多 800ms 的 PCM(整段 utterance 引用),内存占用有界且随下一次语音释放。
5. **提交后残留 reopen(2026-09-01 基准测量中发现)**:快速裁决路径(首个候选即 complete → 立即提交)提交后 ~30ms,Silero 时序平滑残留仍过阈值,VADStream 误判为新语音 → 幻影 reopen → 整段重转写(云端 ASR 下多付 ~2s)。中文因 incomplete 600ms hold 让残留衰减而幸免——语言相关的偶然免疫,非设计保证。候选修复:提交时复位 Silero 状态/加提交后冷却窗。
6. **断句延迟数字依赖 ASR 引擎**:测量时 ASR 插槽为 ElevenLabs 云端,每段提交 ~1.1s flush 延迟且偶发 `commit did not flush in time`;切回本地 sherpa 后数字会不同,对比时应固定引擎。
