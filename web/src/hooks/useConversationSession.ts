/**
 * Conversation session state machine for wake word flow.
 *
 * States:
 *   loading — wake word detector is loading, audio is gated (no mic input sent)
 *   idle    — wake word detector ready, audio gated, waiting for wake word
 *   active  — conversation active, audio flows to backend, silence timer running
 *
 * Transitions:
 *   loading → idle:   detector loads successfully
 *   loading → active: detector fails to load (fallback to always-on)
 *   idle → active:    wake word detected (sends "wake", resets context)
 *   idle → active:    TTS starts playing (silent reopen, no "wake" sent)
 *   active → idle:    silence timeout fires
 *
 * Audio gate flow:
 *   1. Wake word detected → send "wake", open gate, start silence timer
 *   2. User speaks (transcript) → reset silence timer
 *   3. TTS starts playing → clear silence timer; if idle, reopen gate silently
 *   4. TTS finishes playing → start silence timer
 *   5. Silence timer fires → send "idle", close gate, re-arm wake word
 *
 * If wake word is not enabled, starts directly in 'active' state.
 */
import { useState, useEffect, useRef, useCallback } from 'react';

import type { AudioProcessor } from '../services/audio';
import type { WakeWordDetector } from '../services/wakeWordDetector';
import type { VoiceAssistantClient, WebsocketMessage } from '../services/websocket';

export type ConversationState = 'loading' | 'idle' | 'active';

export interface ConversationSessionConfig {
  /** True when wake word feature is enabled in env config */
  intended: boolean;
  /** True when detector is loaded and ready */
  enabled: boolean;
  silenceTimeoutMs: number;
}

interface UseConversationSessionArgs {
  clientRef: React.RefObject<VoiceAssistantClient | null>;
  audioProcessorRef: React.RefObject<AudioProcessor | null>;
  detector: WakeWordDetector | null;
  audioReady: boolean;
  latestMessage: WebsocketMessage | null;
  isSpeaking: boolean;
  config: ConversationSessionConfig;
  onSessionStart?: () => void;
}

export function useConversationSession({
  clientRef,
  audioProcessorRef,
  detector,
  audioReady,
  latestMessage,
  isSpeaking,
  config,
  onSessionStart,
}: UseConversationSessionArgs) {
  // Initial state: 'loading' if wake word intended, 'active' otherwise
  const [conversationState, setConversationState] = useState<ConversationState>(
    config.intended ? 'loading' : 'active',
  );

  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateRef = useRef(conversationState);
  const onSessionStartRef = useRef(onSessionStart);
  const startSessionRef = useRef<() => void>(() => {});
  const resetSilenceTimerRef = useRef<() => void>(() => {});
  const initialConfigRef = useRef(config.intended);

  // Keep refs in sync via effects (React 19 strict mode disallows ref writes during render)
  useEffect(() => {
    stateRef.current = conversationState;
  }, [conversationState]);

  useEffect(() => {
    onSessionStartRef.current = onSessionStart;
  }, [onSessionStart]);

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }, []);

  // Transition: idle → active (wake word detected — sends "wake", resets context)
  const startSession = useCallback(() => {
    if (stateRef.current === 'active') return;

    setConversationState('active');
    audioProcessorRef.current
      ?.disableWakeWord()
      .catch((err) => console.error('[ConversationSession] Failed to disable wake word:', err));
    clientRef.current?.sendMessage('signal', 'wake');
    onSessionStartRef.current?.();
    // Start silence timer — will be cleared if TTS starts playing
    resetSilenceTimerRef.current();
  }, [clientRef, audioProcessorRef]);

  useEffect(() => {
    startSessionRef.current = startSession;
  }, [startSession]);

  // Transition: active → idle
  const endSession = useCallback(() => {
    if (stateRef.current !== 'active') return;

    clientRef.current?.sendMessage('signal', 'idle');
    setConversationState('idle');

    const processor = audioProcessorRef.current;
    if (processor && detector) {
      processor
        .enableWakeWord(detector, () => {
          startSessionRef.current();
        })
        .catch((err) => console.error('[ConversationSession] Failed to re-arm wake word:', err));
    }
  }, [clientRef, audioProcessorRef, detector]);

  const resetSilenceTimer = useCallback(() => {
    clearSilenceTimer();

    if (stateRef.current !== 'active') return;

    silenceTimerRef.current = setTimeout(() => {
      endSession();
    }, config.silenceTimeoutMs);
  }, [config.silenceTimeoutMs, clearSilenceTimer, endSession]);

  useEffect(() => {
    resetSilenceTimerRef.current = resetSilenceTimer;
  }, [resetSilenceTimer]);

  // isSpeaking transitions drive the silence timer and silent gate reopen
  useEffect(() => {
    if (isSpeaking) {
      // TTS started playing — clear silence timer
      clearSilenceTimer();

      // Silent gate reopen: if idle, transition back to active without sending "wake"
      if (stateRef.current === 'idle') {
        queueMicrotask(() => setConversationState('active'));
        audioProcessorRef.current
          ?.disableWakeWord()
          .catch((err) => console.error('[ConversationSession] Failed to disable wake word:', err));
      }
    } else if (stateRef.current === 'active') {
      // TTS finished playing — start silence timer
      resetSilenceTimer();
    }
  }, [isSpeaking, clearSilenceTimer, resetSilenceTimer, audioProcessorRef]);

  // User speech (transcript) resets silence timer
  useEffect(() => {
    if (!latestMessage || stateRef.current !== 'active') return;

    if (latestMessage.type === 'transcript') {
      resetSilenceTimer();
    }
  }, [latestMessage, resetSilenceTimer]);

  // Arm wake word detector when detector becomes available.
  // Transitions loading → idle on success, or loading → active on timeout.
  useEffect(() => {
    if (!initialConfigRef.current) return; // Wake word was never intended

    const processor = audioProcessorRef.current;
    if (!processor || !audioReady) return; // Wait for audio processor to be ready

    if (detector) {
      // Detector loaded successfully: loading → idle
      processor
        .enableWakeWord(detector, () => {
          startSessionRef.current();
        })
        .catch((err) => console.error('[ConversationSession] Failed to enable wake word:', err));
      queueMicrotask(() => setConversationState('idle'));
    } else {
      // Detector not loaded yet — set timeout to fall back to active
      const timeoutId = setTimeout(() => {
        if (stateRef.current === 'loading') {
          console.warn('Wake word detector timeout, falling back to always-on mode');
          setConversationState('active');
        }
      }, 10000);

      return () => clearTimeout(timeoutId);
    }

    return () => {
      clearSilenceTimer();
    };
  }, [detector, audioReady, audioProcessorRef, clearSilenceTimer]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearSilenceTimer();
    };
  }, [clearSilenceTimer]);

  return { conversationState };
}
