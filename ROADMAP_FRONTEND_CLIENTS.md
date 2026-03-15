# Frontend Client Strategy & Roadmap

## Context

Tank currently has three clients: a web frontend (React/TypeScript), a CLI (Python/Textual), and a backend API server. This document defines the strategy for expanding to native desktop and mobile clients, starting with macOS.

### Current Pain Points

- **AEC/ANC**: Browser `echoCancellation` and `noiseSuppression` via `getUserMedia` constraints are inconsistent across browsers and offer no tuning. This is the primary motivation for native clients.
- **Platform presence**: A native macOS app enables menu bar integration, global hotkeys, system audio routing, and background operation — none of which are possible in a browser tab.

### Current Web Frontend Capabilities

| Feature | Implementation |
|---|---|
| Voice mode (real-time audio) | Web Audio API + AudioWorklet, 16kHz Int16 PCM capture |
| Chat mode (text) | React components, Markdown rendering |
| WebSocket protocol | Binary PCM frames + JSON text frames |
| VAD (Voice Activity Detection) | AudioWorklet with energy-based VAD, calibration |
| Wake word detection | Porcupine Web SDK |
| Audio playback | AudioContext at 24kHz, gapless scheduling |
| Waveform visualization | AnalyserNode FFT |
| Reconnection | Exponential backoff, heartbeat, stale socket guards |
| Mute/unmute | MediaStream track enable/disable |
| E2E tests | Cucumber + Playwright (7 feature files, 14 scenarios) |

All of these must be replicated in any new client.

---

## Technology Evaluation

### Option A: Tauri v2 (Web wrapper + Rust + native plugins)

**Approach**: Embed the existing React frontend in a native webview. Use Tauri's Rust backend and platform-specific Swift/Kotlin plugins for native audio.

| Pros | Cons |
|---|---|
| Reuses ~90% of existing React code | Audio still runs through webview unless bridged |
| Existing Cucumber E2E tests work with minimal changes | Tauri mobile support is beta |
| Small binary (~10MB vs Electron's ~150MB) | Rust ↔ Swift bridge adds complexity for audio |
| Cross-platform: macOS, Windows, Linux from one codebase | Two runtime environments to debug (webview + Rust) |
| Familiar web tooling (Vite, TypeScript, React) | Native UI patterns (menu bar, notifications) require Tauri APIs |

**AEC/ANC path**: Tauri plugin in Swift calling `AVAudioEngine` with voice processing IO, bridged to the webview via Tauri commands. Audio capture bypasses the webview entirely.

### Option B: Flutter (Cross-platform native)

**Approach**: Rewrite the UI in Dart/Flutter. Use platform channels for native audio on each platform.

| Pros | Cons |
|---|---|
| Single codebase for macOS, Windows, iOS, Android | Full UI rewrite (no React reuse) |
| Native rendering (not a webview) | Dart ecosystem smaller than JS/TS |
| Platform channels give direct access to AVAudioEngine, WASAPI, etc. | Flutter desktop is mature but less battle-tested than mobile |
| `bdd_integration_test` supports Gherkin feature files | Step definitions must be rewritten in Dart |
| Strong Google backing, large community | Two languages (Dart + Swift/Kotlin for plugins) |

**AEC/ANC path**: Platform channel calling `AVAudioEngine` (macOS/iOS), `AudioRecord` with `VOICE_COMMUNICATION` (Android), WASAPI (Windows). Each platform gets native AEC.

### Option C: SwiftUI (macOS/iOS native only)

**Approach**: Native Swift app using SwiftUI for UI, AVAudioEngine for audio.

| Pros | Cons |
|---|---|
| Best possible macOS/iOS integration | macOS + iOS only — Windows/Android need separate codebases |
| Direct AVAudioEngine, Vision, CoreML access | Full UI rewrite in Swift |
| XCUITest is mature and Apple-supported | No code sharing with web or other platforms |
| App Store first-class citizen | Gherkin E2E requires Appium (heavy setup) |
| Best performance and smallest memory footprint | 4 separate codebases if all platforms needed |

**AEC/ANC path**: `AVAudioEngine` + `setVoiceProcessingEnabled(true)` — the simplest and most capable option, but only for Apple platforms.

### Option D: Kotlin Multiplatform + Compose Multiplatform

**Approach**: Shared Kotlin business logic with Compose UI across platforms.

| Pros | Cons |
|---|---|
| Shared logic layer across all platforms | Compose Desktop is less mature than Flutter |
| Native performance | Smaller ecosystem than Flutter or React |
| Good Android story | macOS/Windows support is newer |
| Kotlin is expressive and type-safe | Still need platform-specific audio plugins |

**AEC/ANC path**: Similar to Flutter — expect/actual declarations with platform-specific audio implementations.

### Comparison Matrix

| Criteria | Tauri v2 | Flutter | SwiftUI | KMP |
|---|---|---|---|---|
| Reuse existing web code | ~90% | 0% | 0% | 0% |
| Reuse existing E2E tests | ~80% | Feature files only | Feature files only | Feature files only |
| macOS AEC/ANC | Via Swift plugin | Via platform channel | Direct | Via expect/actual |
| Windows support | Yes | Yes | No | Yes |
| iOS support | Beta | Yes | Yes | Yes |
| Android support | Beta | Yes | No | Yes |
| Time to first macOS app | ~1 week | ~3 weeks | ~2 weeks | ~3 weeks |
| Native UI fidelity | Webview (good enough) | Custom rendering | Best on Apple | Custom rendering |
| Binary size | ~10MB | ~25MB | ~5MB | ~30MB |
| Community/ecosystem | Growing | Large | Large (Apple) | Growing |

---

## E2E Testing Strategy

### Goal: Share Cucumber feature files across all clients

The 7 existing feature files (`chat.feature`, `connection.feature`, `voice.feature`, etc.) describe user behavior that is identical across platforms. Only the element-finding mechanism differs.

### Per-framework approach

| Framework | Test Runner | Feature Files | Step Definitions | Element Selectors |
|---|---|---|---|---|
| **Web (current)** | Cucumber.js + Playwright | Shared `.feature` files | TypeScript | CSS selectors, `data-testid` |
| **Tauri** | Cucumber.js + Playwright (webview) | Same `.feature` files | Same TypeScript (minor driver changes) | Same CSS selectors |
| **Flutter** | `bdd_integration_test` | Same `.feature` files | Rewrite in Dart | `find.byKey()`, `find.text()` |
| **SwiftUI** | Appium + Cucumber.js | Same `.feature` files | TypeScript (Appium driver) | Accessibility identifiers |
| **KMP** | Appium + Cucumber.js | Same `.feature` files | TypeScript (Appium driver) | Accessibility identifiers |

### Recommended test directory structure

```
test/
├── features/                    # Shared across ALL clients
│   ├── chat.feature
│   ├── connection.feature
│   ├── mode-toggle.feature
│   ├── mute.feature
│   ├── reconnection.feature
│   ├── stop-speech.feature
│   └── voice.feature
├── steps/
│   ├── common/                  # Shared step logic (assertions, helpers)
│   │   └── chat.common.ts
│   ├── web/                     # Web + Tauri (Playwright)
│   │   └── chat.steps.ts
│   ├── native/                  # SwiftUI / KMP (Appium)
│   │   └── chat.steps.ts
│   └── flutter/                 # Flutter (Dart, separate runner)
│       └── chat_steps.dart
├── support/
│   ├── drivers/
│   │   ├── playwright.ts        # Web + Tauri driver setup
│   │   └── appium.ts            # Native app driver setup
│   ├── hooks.ts
│   └── world.ts
└── cucumber.config.cjs
```

Key principle: **feature files are the contract**. Step definitions are the adapter layer per platform.

---

## Decision

**Phase 1: Tauri v2** — lowest effort, validates AEC/ANC via native audio plugin, reuses existing React code and E2E tests.

**Phase 2+: Re-evaluate** based on Phase 1 learnings. If multi-platform is confirmed, migrate to Flutter or keep Tauri depending on mobile maturity.

---

## Roadmap

### Phase 1: Tauri macOS App (Target: 2-3 weeks)

**Goal**: Ship a macOS app with feature parity to the web frontend, plus native AEC/ANC.

#### 1.1 — Tauri Project Scaffolding (~2 days)

- [ ] Initialize Tauri v2 project wrapping the existing `web/` React app
- [ ] Configure Vite for Tauri (dev server + build)
- [ ] macOS window configuration (title bar, size, resizable)
- [ ] App icon and metadata
- [ ] Verify all existing web features work in the Tauri webview
- [ ] Existing E2E tests pass against the Tauri app (Playwright connects to webview)

#### 1.2 — Native Audio Capture Plugin (~3-4 days)

- [ ] Create Tauri Swift plugin: `tauri-plugin-audio`
- [ ] `AVAudioEngine` setup with voice processing IO (`setVoiceProcessingEnabled(true)`)
- [ ] Microphone capture → Int16 PCM at 16kHz (matching backend expectation)
- [ ] Bridge audio chunks from Swift → Rust → webview via Tauri events
- [ ] Replace `getUserMedia` + AudioWorklet with native audio when running in Tauri
- [ ] VAD: port energy-based VAD to Swift, or keep in webview and only bridge raw PCM
- [ ] Calibration: port threshold calibration or use fixed threshold with native noise floor

#### 1.3 — Native Audio Playback (~2 days)

- [ ] Receive Int16 PCM from WebSocket in webview, forward to Swift plugin
- [ ] `AVAudioEngine` playback with gapless scheduling (replaces Web Audio API)
- [ ] Speaking state tracking (callback from Swift → webview)
- [ ] Interrupt support (stop playback immediately)

#### 1.4 — AEC/ANC Validation (~2 days)

- [ ] Test echo cancellation: play TTS through speakers while capturing mic
- [ ] Test noise suppression: capture in noisy environment
- [ ] Compare quality vs. browser `echoCancellation: true`
- [ ] Document findings and tuning parameters
- [ ] If insufficient: explore `AUVoiceIO` audio unit for more control

#### 1.5 — macOS Integration (~2 days)

- [ ] Menu bar icon with status (listening/processing/speaking)
- [ ] Global hotkey for push-to-talk
- [ ] System notification for assistant responses (optional)
- [ ] Auto-start on login (optional)
- [ ] Proper app lifecycle (background/foreground, sleep/wake)

#### 1.6 — Testing & Polish (~2 days)

- [ ] Verify all 14 existing E2E scenarios pass
- [ ] Add macOS-specific E2E scenarios (menu bar, hotkey)
- [ ] Performance profiling (memory, CPU during conversation)
- [ ] Code signing and notarization for distribution

### Phase 2: Multi-Platform Evaluation (After Phase 1)

**Goal**: Decide the long-term multi-platform strategy based on Phase 1 learnings.

#### 2.1 — Evaluate Phase 1 Results

- [ ] AEC/ANC quality: is the Tauri Swift plugin approach sufficient?
- [ ] Developer experience: how painful was the Rust ↔ Swift bridge?
- [ ] Performance: any webview overhead issues?
- [ ] Tauri mobile status: has v2 mobile stabilized?

#### 2.2 — Decision Point

```
If Tauri mobile is stable AND AEC/ANC quality is good:
  → Continue with Tauri for all platforms (Phase 3A)

If AEC/ANC needs deeper native control OR Tauri mobile is not ready:
  → Migrate to Flutter (Phase 3B)

If only Apple platforms needed:
  → Consider SwiftUI for iOS, keep Tauri for macOS (Phase 3C)
```

### Phase 3A: Tauri Multi-Platform (If Tauri chosen)

- [ ] Windows app (WASAPI audio plugin in Rust/C++)
- [ ] iOS app (Tauri mobile + AVAudioEngine plugin)
- [ ] Android app (Tauri mobile + AudioRecord plugin)
- [ ] Shared E2E: feature files unchanged, Playwright for all webview targets
- [ ] Platform-specific audio plugins per OS

### Phase 3B: Flutter Migration (If Flutter chosen)

- [ ] Flutter project setup with platform channels
- [ ] Port `useAssistant` state machine to Dart (`AssistantViewModel`)
- [ ] Port WebSocket client to Dart (`web_socket_channel`)
- [ ] Port UI: VoiceView, ChatView, MessageStep
- [ ] macOS audio plugin (AVAudioEngine, port from Tauri Swift plugin)
- [ ] Windows audio plugin (WASAPI)
- [ ] iOS audio plugin (shares with macOS)
- [ ] Android audio plugin (AudioRecord VOICE_COMMUNICATION)
- [ ] E2E: `bdd_integration_test` with shared feature files, Dart step definitions
- [ ] Retire Tauri app

### Phase 3C: Hybrid (If Apple-only + Tauri)

- [ ] SwiftUI iOS app with shared AVAudioEngine code
- [ ] Keep Tauri macOS app
- [ ] Appium + Cucumber for SwiftUI E2E (shared feature files)
- [ ] Windows: Tauri or defer

### Phase 4: Camera & Face Recognition (Any framework)

- [ ] Camera capture: periodic JPEG frames from native camera API
- [ ] Send frames to backend via REST or WebSocket sideband
- [ ] Backend: face embedding extraction + identity matching (same pattern as speaker ID)
- [ ] Frontend: display identified user name
- [ ] ~100 lines of frontend code regardless of framework

---

## Architecture: Tauri Phase 1

```
┌─────────────────────────────────────────────────────────┐
│                    Tauri macOS App                       │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Webview (React/TypeScript)            │  │
│  │                                                   │  │
│  │  useAssistant ──→ VoiceAssistantClient (WebSocket)│  │
│  │       │                    │                      │  │
│  │       │              Binary PCM + JSON             │  │
│  │       │                    │                      │  │
│  │       ▼                    ▼                      │  │
│  │  UI Components      Backend Server                │  │
│  │  (VoiceMode,        (localhost:8000)              │  │
│  │   ChatMode)                                       │  │
│  └───────┬───────────────────────────────────────────┘  │
│          │ Tauri Commands / Events                       │
│  ┌───────▼───────────────────────────────────────────┐  │
│  │           Rust Core (Tauri Backend)                │  │
│  │                      │                            │  │
│  │              Tauri Plugin Bridge                   │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │ FFI                            │
│  ┌──────────────────────▼────────────────────────────┐  │
│  │          Swift Audio Plugin                        │  │
│  │                                                   │  │
│  │  AVAudioEngine                                    │  │
│  │  ├── inputNode (voice processing IO)              │  │
│  │  │   ├── AEC (echo cancellation)                  │  │
│  │  │   └── ANS (noise suppression)                  │  │
│  │  ├── Tap → Int16 PCM → Rust → Webview events      │  │
│  │  └── playerNode ← Int16 PCM ← Rust ← Webview     │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Audio Data Flow (Capture)

```
Microphone
  → AVAudioEngine inputNode (voice processing: AEC + ANS)
  → installTap: PCMBuffer → convert to Int16 at 16kHz
  → Swift → Rust (Tauri command response or event)
  → Webview JS: received as Int16Array
  → VoiceAssistantClient.sendAudio() → WebSocket binary frame
  → Backend
```

### Audio Data Flow (Playback)

```
Backend
  → WebSocket binary frame (Int16 PCM, 24kHz)
  → Webview JS: received as ArrayBuffer
  → Tauri event → Rust → Swift
  → AVAudioEngine playerNode: schedule PCMBuffer
  → Speaker output
```

### Feature Detection Pattern

The webview code should detect whether it's running inside Tauri and switch audio backends accordingly:

```typescript
// In AudioProcessor or a new TauriAudioBridge
const isTauri = '__TAURI__' in window;

if (isTauri) {
  // Use Tauri commands for native audio
  await invoke('start_audio_capture');
  listen('audio-chunk', (event) => onAudio(event.payload));
} else {
  // Fall back to getUserMedia + AudioWorklet (existing code)
  await this.startWebAudio();
}
```

This keeps the web frontend fully functional in a browser while gaining native audio in Tauri.

---

## WebSocket Protocol Reference

The protocol is the shared contract between all clients and the backend. Any new client must implement this exactly.

### Client → Server

| Frame | Format | Description |
|---|---|---|
| Audio | Binary (Int16 PCM, 16kHz, mono) | Microphone audio stream |
| Text input | JSON `{"type":"input","content":"...","metadata":{}}` | User typed message |
| Interrupt | JSON `{"type":"signal","content":"interrupt","metadata":{}}` | Cancel current response |
| Ping | JSON `{"type":"signal","content":"ping","metadata":{"timestamp":...}}` | Heartbeat |
| Disconnect | JSON `{"type":"signal","content":"disconnect","metadata":{}}` | Graceful close |

### Server → Client

| Frame | Format | Description |
|---|---|---|
| Audio | Binary (Int16 PCM, 24kHz, mono) | TTS audio chunks |
| Signal | JSON `{"type":"signal","content":"ready\|processing_started\|processing_ended\|pong"}` | Status |
| Transcript | JSON `{"type":"transcript","content":"...","is_user":true,"msg_id":"..."}` | ASR result |
| Text | JSON `{"type":"text","content":"...","msg_id":"...","metadata":{}}` | Streamed LLM text |
| Update | JSON `{"type":"update","metadata":{"update_type":"THOUGHT\|TOOL",...}}` | Thinking/tool steps |

### Connection State Machine

```
idle → connecting → connected ⇄ reconnecting → failed
                        ↑                         │
                        └─── manual reconnect() ──┘
```

Reconnection: exponential backoff (1s base, 1.5x multiplier, 30s max, 10 max attempts).

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Tauri Swift plugin API changes (v2 is new) | Medium | Pin Tauri version, isolate plugin behind stable interface |
| AEC quality insufficient via AVAudioEngine | High | Phase 1.4 validates early; fallback to AUVoiceIO or custom DSP |
| Webview audio latency adds delay | Medium | Native playback (Phase 1.3) bypasses webview audio entirely |
| Tauri mobile never stabilizes | Medium | Phase 2 decision point explicitly covers this; Flutter is the backup |
| E2E tests flaky in Tauri webview | Low | Playwright webview support is mature; same engine as Chrome |

---

## References

- [Tauri v2 docs](https://v2.tauri.app/)
- [Tauri Swift plugins](https://v2.tauri.app/develop/plugins/)
- [AVAudioEngine voice processing](https://developer.apple.com/documentation/avfaudio/avaudioinputnode/3152106-setvoiceprocessingenabled)
- [Flutter platform channels](https://docs.flutter.dev/platform-integration/platform-channels)
- [bdd_integration_test (Flutter Gherkin)](https://pub.dev/packages/bdd_integration_test)
- [Appium](https://appium.io/)
- Existing: [ROADMAP_PIPELINE_ARCHITECTURE.md](ROADMAP_PIPELINE_ARCHITECTURE.md) — backend pipeline roadmap
