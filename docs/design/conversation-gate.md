# Conversation Gate & Silence Timer

This document describes the audio gate state machine, the silence timer, and the signal protocol that govern when the microphone is open, when it closes, and how late-arriving TTS audio silently reopens it.

## Terminology

| Term | Definition |
|------|-----------|
| Session | A single WebSocket connection. Starts on connect, ends on disconnect. 1:1 with the WS lifecycle. |
| Conversation | A visible exchange between the user and Tank. One session may contain many conversations. |
| Context | The Brain's `_conversation_history` — system prompt, messages, tool calls. Cleared on each `wake`. |
| Audio gate | A logical switch that controls whether microphone PCM frames are sent to the backend. Open = sending, closed = not sending. |
| Silence timer | A frontend `setTimeout` that fires after `VITE_WAKE_WORD_SILENCE_TIMEOUT_MS` (default 30 s) of inactivity, closing the gate. |

## Signal Protocol

All signals are JSON frames of type `signal` sent over the WebSocket.

### Client → Server

| Signal | When sent | Backend behavior |
|--------|-----------|-----------------|
| `wake` | Wake word detected | Calls `assistant.reset_session()` (clears Brain context), responds with `conversation_ready` |
| `idle` | Silence timer fires | Logged as informational. No-op — backend does not clear context or stop processing. |
| `disconnect` | Tab closing / manual disconnect | Breaks the receive loop, triggers session cleanup. |
| `ping` | Heartbeat (every 30 s) | Responds with `pong` carrying the same metadata. |

### Server → Client

| Signal | When sent | Frontend behavior |
|--------|-----------|------------------|
| `ready` | Immediately after WS accept | Extracts `capabilities` from metadata (ASR, TTS, speaker ID). Triggers AudioProcessor start. |
| `conversation_ready` | After successful `reset_session()` | Currently unused by the frontend — the gate is already open by the time this arrives. |
| `session_reset_failed` | If `reset_session()` throws | Currently unused — logged to console. |
| `processing_started` | Brain begins LLM call | Sets `isAssistantTyping = true`. Does NOT affect the silence timer. |
| `processing_ended` | Brain finishes LLM call | Sets `isAssistantTyping = false`. Does NOT affect the silence timer. |
| `pong` | Response to `ping` | Updates heartbeat tracking in the WebSocket client. |

## State Machine

The conversation gate is managed by `useConversationSession` in `web/src/hooks/useConversationSession.ts`. It exposes a single value: `conversationState: 'loading' | 'idle' | 'active'`.

```
                    ┌──────────────────────────────────────────────┐
                    │                                              │
                    ▼                                              │
              ┌──────────┐                                        │
              │ loading  │  (wake word detector initializing)     │
              └────┬─────┘                                        │
                   │                                              │
          ┌────────┴────────┐                                     │
          │                 │                                     │
    detector loads    10 s timeout                                │
          │           (fallback)                                  │
          ▼                 ▼                                     │
     ┌────────┐       ┌────────┐                                  │
     │  idle  │◄──────│ active │──── silence timer fires ─────────┘
     └────┬───┘       └────────┘         (sends "idle",
          │                ▲              re-arms wake word)
          │                │
          ├── wake word ───┘  (sends "wake", clears context)
          │
          └── TTS starts ──┘  (silent reopen, NO "wake" sent)
```

### State descriptions

- `loading` — Wake word detector is being loaded. Audio gate is closed (`processor.pause()`). If the detector loads, transitions to `idle`. If it fails to load within 10 seconds, falls back to `active` (always-on mode).

- `idle` — Wake word detector is armed and listening. Audio gate is closed. The AudioProcessor is in wake-word-only mode: it runs the local wake word model on mic input but does not send PCM to the backend. Two events can transition to `active`:
  1. Wake word detected → full `startSession()` (sends `wake`, clears steps, starts silence timer)
  2. TTS starts playing → silent gate reopen (no `wake`, no context reset)

- `active` — Conversation is live. Audio gate is open (`processor.resume()`). Mic PCM flows to the backend. The silence timer is running. Transitions back to `idle` when the silence timer fires.

### No wake word mode

When `VITE_WAKE_WORD_ENABLED` is not `true`, the state machine starts directly in `active` and never transitions to `idle` or `loading`. The silence timer never runs. The gate is always open.

## Silence Timer

The silence timer is the mechanism that decides when a conversation is "over" and the gate should close.

### What resets the timer

| Event | Effect on timer |
|-------|----------------|
| `startSession()` (wake word detected) | Starts the timer |
| User speech (`transcript` message) | Resets the timer |
| TTS starts playing (`isSpeaking` → `true`) | Clears the timer (pauses countdown) |
| TTS finishes playing (`isSpeaking` → `false`) | Starts the timer |

### What does NOT affect the timer

| Event | Why it's ignored |
|-------|-----------------|
| `processing_started` signal | The LLM may think for a long time. If the timer fires during thinking, that's fine — TTS arrival will silently reopen the gate. |
| `processing_ended` signal | Same reasoning. These signals only control `isAssistantTyping` for UI display. |

### Timer fires during backend processing

This is the key design decision. Consider this timeline:

```
t=0s   User says "What's the weather in Tokyo?"
t=0.5s Backend receives transcript, starts LLM call (processing_started)
t=5s   LLM is still thinking (tool call to weather API)
t=30s  Silence timer fires → gate closes, state → idle, wake word re-armed
t=32s  LLM finishes, TTS starts playing
       → isSpeaking becomes true
       → Silent gate reopen: idle → active (no "wake" sent)
       → User hears the response normally
t=40s  TTS finishes → silence timer starts again
```

The user never notices the gate closed and reopened. The response plays normally. No context is lost because `wake` was never sent.

### Why this is safe

- The backend does not care about `idle`. It's informational. The backend continues processing regardless.
- TTS audio arrives as binary WebSocket frames. The frontend always plays them — the gate only controls mic input, not audio output.
- The silent reopen (`idle` → `active`) only calls `disableWakeWord()` and `processor.resume()`. It does not send `wake`, so the backend context is preserved.

## Silent Gate Reopen

When TTS starts playing while the gate is closed (`idle` state), the gate reopens silently:

```typescript
// useConversationSession.ts — isSpeaking effect
if (isSpeaking) {
  clearSilenceTimer();

  if (stateRef.current === 'idle') {
    // Silent reopen — no "wake", no context reset
    queueMicrotask(() => setConversationState('active'));
    audioProcessorRef.current?.disableWakeWord();
  }
} else if (stateRef.current === 'active') {
  // TTS finished — start silence timer
  resetSilenceTimer();
}
```

This handles two scenarios:

1. Timer fires during backend processing (described above). TTS arrives late, reopens the gate.
2. Multi-turn tool calls. The LLM calls a tool, waits for the result, calls another tool. TTS may arrive in bursts with gaps between them. Each burst clears the timer; each gap restarts it.

## Audio Gate in useAssistant

The `useAssistant` hook observes `conversationState` and controls the AudioProcessor accordingly:

```typescript
// useAssistant.ts — gate effect
useEffect(() => {
  if (conversationState === 'loading') {
    processor.pause();       // Gate closed, no audio sent
  } else if (conversationState === 'active') {
    processor.resume();      // Gate open, mic PCM flows to backend
  }
  // 'idle' is handled by enableWakeWord() in useConversationSession
}, [conversationState]);
```

The `idle` state is not handled here because `enableWakeWord()` in `useConversationSession.endSession()` already configures the AudioProcessor to run in wake-word-only mode.

## Mic Button Visual Feedback

The mic button in `VoiceMode.tsx` reflects the gate state, not VAD activity:

```typescript
const isGateOpen = conversationState === 'active';
const micStatus = isMuted ? 'muted' : isGateOpen ? 'active' : 'idle';
```

| `micStatus` | Appearance | Meaning |
|-------------|-----------|---------|
| `muted` | Zinc (gray), `MicOff` icon | User manually muted |
| `active` | Emerald glow, `Mic` icon | Gate open, mic is live |
| `idle` | Dim zinc, `Mic` icon | Gate closed, waiting for wake word |

The pulse animation on the mic button is still tied to `isUserSpeaking` (VAD activity), not the gate state. This gives the user visual feedback that their voice is being detected while keeping the base color tied to whether audio is actually being sent.

## Backend Signal Handling

In `backend/core/src/tank_backend/api/router.py`:

```python
elif msg.content == "wake":
    assistant.reset_session()          # Clears Brain context
    await websocket.send_text(         # Responds with conversation_ready
        WebsocketMessage(
            type=MessageType.SIGNAL,
            content="conversation_ready",
            session_id=session_id,
        ).model_dump_json()
    )

elif msg.content == "idle":
    logger.info(f"Client idle: {session_id}")   # Informational only
```

`wake` is the only signal that mutates backend state. `idle` is purely informational — the backend logs it but takes no action. This means:

- If the client sends `idle` while the backend is mid-processing, nothing breaks.
- If the client never sends `idle` (e.g., wake word is disabled), nothing breaks.
- The backend never needs to know whether the gate is open or closed.

## Complete Lifecycle Example

A typical voice conversation with wake word enabled:

```
1. Page loads
   - WebSocket connects
   - Server sends "ready" with capabilities
   - AudioProcessor starts
   - Wake word detector loads → state: loading → idle
   - Wake word armed, mic in wake-word-only mode

2. User says "Hey Tank"
   - Wake word detected locally
   - startSession():
     - state: idle → active
     - disableWakeWord()
     - sendMessage("signal", "wake")
     - onSessionStart() → clears steps (UI reset)
     - resetSilenceTimer() → 30s countdown starts
   - Backend: reset_session(), responds "conversation_ready"
   - AudioProcessor.resume() → mic PCM flows to backend

3. User says "What's the weather?"
   - Backend ASR produces transcript → frontend receives it
   - resetSilenceTimer() → countdown resets to 30s
   - Backend Brain starts LLM call → "processing_started"
   - isAssistantTyping = true (UI shows "思考中")

4. LLM calls weather tool, waits for result
   - Silence timer is still counting down
   - If it fires here, gate closes → state: idle
   - (This is fine — TTS will reopen it)

5. LLM finishes, TTS starts
   - isSpeaking = true
   - clearSilenceTimer()
   - If state was idle: silent reopen → active (no "wake")
   - User hears the response

6. TTS finishes
   - isSpeaking = false
   - resetSilenceTimer() → 30s countdown starts

7. User says nothing for 30 seconds
   - Silence timer fires
   - endSession():
     - sendMessage("signal", "idle")
     - state: active → idle
     - enableWakeWord() → mic back to wake-word-only mode
   - Waiting for next "Hey Tank"
```

## Configuration

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `VITE_WAKE_WORD_ENABLED` | `false` | Enable wake word detection. When `false`, gate is always open. |
| `VITE_WAKE_WORD_SILENCE_TIMEOUT_MS` | `30000` | Milliseconds of silence before the gate closes. |

## Files

| File | Role |
|------|------|
| `web/src/hooks/useConversationSession.ts` | State machine, silence timer, signal sending |
| `web/src/hooks/useAssistant.ts` | Wires the state machine to AudioProcessor and VoiceAssistantClient |
| `web/src/components/Assistant/VoiceMode.tsx` | Mic button color based on gate state |
| `backend/core/src/tank_backend/api/router.py` | Handles `wake` (reset context) and `idle` (log only) |
