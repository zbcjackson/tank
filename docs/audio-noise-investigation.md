# TTS Playback Noise Investigation

Status: **unresolved as of 2026-05-06**. Noise persists; architecture decisions and evidence documented here so the next attempt starts from data, not guesses.

## Symptom

When the Tank web frontend plays TTS audio, there is audible noise — described by the user as "not continuous fizz/buzz, not rhythmic either." Noise does not correlate with any specific TTS content and is independent of network conditions.

## What's been verified clean (ruled out as sources)

Each of these was captured to a file, measured, and/or listened to. Any of them could have been the culprit; none is.

| Layer | Evidence | Verdict |
|---|---|---|
| Edge TTS MP3 stream | raw MP3 saved to `/tmp/tank-audio-debug/raw-edge.mp3`, plays cleanly through ffplay | Clean |
| ffmpeg decode to s16le PCM | `/tmp/tank-audio-debug/ffmpeg.wav`, stats: peak=21760, DC offset=0.3, 0 big jumps, 0 clips | Clean |
| `EdgeTTSEngine.generate_stream` output | `/tmp/tank-audio-debug/plugin.wav`, **byte-for-byte identical** to ffmpeg output, 62 chunks, 0 odd-length | Clean |
| Odd-byte Int16 alignment | `_align_int16` helper ensures every emitted chunk has even byte length; 0 odd chunks observed in captures | Not the issue |
| Sample rate mismatch (generic) | Browser console confirms `requested 24000Hz, got 24000Hz (state=running)` | Context honors the hint |
| WebSocket byte corruption | `browser-received-24000.pcm` (captured at `BrowserAudioAdapter.playChunk` entry) plays cleanly through ffplay | Clean |
| `LinearResampler` output | `tank-resampled-192000.f32`, stats: peak=0.72, 0 big jumps, hf/rms=0.039 (cleaner than voice baseline) | Clean |
| PCM → Float32 conversion | Division by 32768 correct from day 1, not modified | Not the issue |
| Endianness / signedness | `Int16Array` is always signed LE in browsers; matches ffmpeg `s16le` | Not the issue |
| Clipping / excessive gain | Measured peak 0.66-0.72 across all captures, 0 clips in all captures | Not the issue |
| Other apps on same output | User confirmed YouTube, Spotify, etc. sound clean through the same USB DAC | DAC + macOS mix stack OK |

## Key hardware context

User's setup:

- **External USB DAC** running at **192 kHz native output rate** (reported by `new AudioContext().sampleRate` with no hint)
- Other web apps (YouTube, Spotify) produce clean audio through the same device
- Other output devices not tested; symptom status on built-in speakers / Bluetooth unknown

The 192 kHz native rate is unusually high and means any Web Audio stack that runs the graph at a lower rate must do a large upsampling ratio (24 → 192 = 8×) at the output stage.

## What IS the source

Evidence narrows the noise to one location: **browser-side playback scheduling**. Specifically, per-chunk `AudioBufferSourceNode.start()` chaining.

The chain of logic:

1. Backend-produced PCM is clean (measured).
2. The exact bytes reaching the browser's `playChunk()` are clean (captured and verified).
3. Playing those same bytes through `ffplay` sounds clean.
4. Playing the same bytes through Web Audio sounds noisy.
5. ⇒ Noise is introduced by Web Audio's playback of these chunks.

## Fix attempts and why they failed

### Attempt 1: Request `sampleRate: 24000` on `AudioContext`

**Intent**: force the context to run at the PCM rate so the graph doesn't resample per-buffer.

**Result**: the browser honored the hint (confirmed in console), but noise remained. The browser still resamples 24 → 192 at the output stage, and appears to do so per `AudioBufferSourceNode` rather than continuously across the stream.

### Attempt 2: 2 ms linear fade-in/out at each chunk boundary

**Intent**: mask the discontinuity at the join between two `AudioBufferSourceNode`s.

**Result**: made things worse — created an ~12 Hz amplitude modulation (one fade per ~85 ms chunk), which produced a rough quality on the voice. Reverted.

### Attempt 3: AudioContext at native rate + main-thread `LinearResampler` + per-chunk `AudioBufferSourceNode`

**Intent**: do the resampling ourselves with stateful phase carry across chunks, hand pre-resampled buffers to the browser so no per-buffer resampling happens at output.

**Result**: noise remained audible. The resampled output was measured clean (see analyzer results below); the noise still came from the `AudioBufferSourceNode` scheduling itself, independent of rate matching.

### Attempt 4: AudioContext at native rate + `LinearResampler` + single long-lived `AudioWorkletNode` with ring buffer

**Intent**: replace chained `AudioBufferSourceNode`s with one pull-model node that drains a ring buffer continuously, so there are no per-chunk scheduling gaps.

**Result**: made things much worse. User reported "popping at the start, then no sound, but still playing." Analyzer confirmed **the worklet output was 49.4 seconds for a 32.98-second input**, with a single zero run of 40.2 seconds. The worklet drained its ring buffer faster than the main thread could fill it, emitting silence during gaps, which accumulated into most of the stream being silence.

#### Numbers from that attempt (2026-05-06 capture)

```
inputRate   = 24000 Hz, ctxRate = 192000 Hz
chunkCount  = 487, inputDur = 32.98s, outputDur = 49.39s

(A) pre-resample input:
    samples    : 791424 (32.98s @ 24000Hz)
    peak=0.72, dc=+0.000012, max_jump=0.46 (>0.3: 208), hf/rms=0.312
    → clean

(B) post-resample (LinearResampler output):
    samples    : 6331385 (32.98s @ 192000Hz)
    peak=0.72, dc=+0.000012, max_jump=0.058, hf/rms=0.039
    → clean (hf/rms much lower than voice baseline, as expected for upsampled signal)

(C) worklet output:
    samples    : 9483776 (49.39s @ 192000Hz)   ← 16.4s LONGER than input!
    max_jump=0.39, hf/rms=0.039
    max zero run: 7725865 samples (40238.9ms)  ← 40s of silence in one run
    → dropouts, not wrong samples
```

The worklet approach cannot work without proper producer-side rate matching and a pre-buffer (e.g. wait until 200 ms queued before starting, refuse to drain below some floor). That's non-trivial to implement correctly and was judged out of scope for "fix the noise" after two failed tries.

### Attempt 5: Revert to per-chunk `AudioBufferSourceNode` scheduling

**Intent**: ship the known-imperfect-but-predictable path rather than the broken one.

**Result**: the shipped state. Noise is audible but the system works. Keeps the valuable wire-format work from this session (binary frame protocol, per-chunk sample rate, Int16 alignment).

## What's in the tree right now

Kept (all are unconditional wins):

- `backend/contracts/tank_contracts/tts.py`: `encode_audio_frame` / `decode_audio_frame` — every audio frame carries its sample rate + channel count in an 8-byte header.
- `backend/core/src/tank_backend/api/router.py` and `channels/audio_service.py`: backend frames each chunk before send.
- `backend/plugins/tts-edge/tts_edge/engine.py`: `_align_int16` helper carries odd bytes to the next read so emitted `AudioChunk`s are always Int16-aligned.
- Web frontend decodes frame header, passes rate + channels to `playChunk()`.
- Tauri adapter passes sample rate + channels to Rust `play_audio` command.
- CLI `audio/frame.py` mirrors the codec (decoupled from backend workspace).
- Diagnostic `[BrowserAudio] requested Xhz, got Yhz` log.

Reverted / deleted:

- `web/public/tank-playback-processor.js`
- `web/src/services/linearResampler.ts` (and test)
- `web/src/services/audioDebug.ts`
- Per-chunk fade-in/out in `browserAudio.ts`

## Reproducing and capturing

Two instrumentation scripts are in `backend/scripts/`:

### `capture_tts.py` — backend-side capture

```sh
cd backend
uv run python scripts/capture_tts.py "Some sentence to speak"
```

Writes three files to `/tmp/tank-audio-debug/`:
- `raw-edge.mp3` — what edge-tts streams
- `ffmpeg.wav` — after our ffmpeg decode
- `plugin.wav` — what the pipeline consumes

Plus stats (peak, DC offset, big jumps, chunk sizes).

### `analyze_browser_captures.py` — browser-side capture

No longer wired up by default (the `audioDebug.ts` helper was deleted). To re-enable, restore `audioDebug.ts` and its `main.tsx` import from git history, then in DevTools Console:

```js
__tankAudioArm()
// trigger TTS, wait 5-10s
__tankAudioSave()
```

Then:

```sh
cd backend
uv run python scripts/analyze_browser_captures.py ~/Downloads
```

Outputs stats for three points — input, post-resample, worklet output — plus WAV files for each.

## Paths not yet tried (candidates for next attempt)

Ordered by estimated fix probability and change size:

### 1. HTMLMediaElement-based playback

YouTube and Spotify use `<audio>`/`<video>` elements with proper buffered streaming, not `AudioBufferSourceNode` chaining. The browser's media pipeline handles decoding and buffering. The noise almost certainly doesn't affect this path.

**How**: build a MediaSource buffer that we append WAV-encoded PCM chunks to. Create an `<audio>` element whose `src` is the MediaSource's object URL. Keep `AnalyserNode` support by going through `MediaElementAudioSourceNode`.

**Trade-offs**: higher latency than `AudioBufferSourceNode`, adds MediaSource API complexity, may not support all TTS engines' chunk formats cleanly. Untested.

### 2. Single long `AudioBufferSourceNode` rewritten periodically

Instead of one source node per chunk, accumulate ~0.5 s of audio into one buffer, schedule it, and schedule the next one seamlessly (next start time = previous end). Still uses `AudioBufferSourceNode`, but far fewer of them → fewer join artifacts.

**Trade-offs**: 0.5 s latency before audio starts (bad for interactive voice). Still does per-buffer resampling, so may not help on the 192 kHz DAC case.

### 3. AudioWorklet with proper producer-side rate matching

The Attempt 4 architecture, done right: pre-buffer 200 ms before starting playback; track ring-buffer fill level; on underrun, pause the worklet's output rather than emitting silence; resume when refilled.

**Trade-offs**: much more code. Requires careful producer/consumer coordination. The underrun-to-silence path was what killed Attempt 4; fixing it means building a proper elastic buffer.

### 4. Ask the user to test on other output devices

The 192 kHz USB DAC is a suspect — not for the noise itself (other apps are clean on it), but for why Web Audio's built-in resampling is so much worse than YouTube's media pipeline resampling. If the same code is clean on built-in speakers (likely 48 kHz), it narrows the problem to the 24 → 192 resampling specifically and makes attempt 1 look weaker than it should.

Quick test to capture: switch macOS output to built-in speakers, reload Tank, trigger TTS. If clean: we have a device-specific workaround story. If still noisy: the problem is more general.

## Files worth reading

- `web/src/services/browserAudio.ts` — current playback implementation
- `web/src/services/audioPlayback.ts` — playback coordinator
- `web/src/services/audioFrame.ts` — wire format decoder
- `backend/contracts/tank_contracts/tts.py` — `encode_audio_frame` / `decode_audio_frame`
- `backend/plugins/tts-edge/tts_edge/engine.py` — TTS source + `_align_int16`

## Git history worth reading

The attempts are not preserved as separate commits (the reverts clobbered them). If you want to revive the worklet / resampler approach with proper buffering:

- `web/src/services/linearResampler.ts` and its test had 7 passing tests including a 24 → 192 sine-wave chunked-vs-oneshot test (`maxDelta < 1e-6`). The resampler itself was correct; the ring-buffer consumer was the problem.
- `web/public/tank-playback-processor.js` was the worklet processor. Its underrun-to-silence policy is what broke it.

These live only in conversation history for now. If picking this up again, reconstruct from there rather than re-deriving.
