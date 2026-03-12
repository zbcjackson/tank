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
 *   idle → active:    wake word detected
 *   active → idle:    silence timeout expires (deferred while Tank is speaking)
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
  const isSpeakingRef = useRef(isSpeaking);
  const stateRef = useRef(conversationState);
  const onSessionStartRef = useRef(onSessionStart);
  const startSessionRef = useRef<() => void>(() => {});
  const initialConfigRef = useRef(config.intended);

  // Keep refs in sync via effects (React 19 strict mode disallows ref writes during render)
  useEffect(() => {
    isSpeakingRef.current = isSpeaking;
  }, [isSpeaking]);

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

  // Transition: idle → active
  const startSession = useCallback(() => {
    if (stateRef.current === 'active') return;

    setConversationState('active');
    audioProcessorRef.current?.disableWakeWord();
    clientRef.current?.sendMessage('signal', 'session_start');
    onSessionStartRef.current?.();
  }, [clientRef, audioProcessorRef]);

  useEffect(() => {
    startSessionRef.current = startSession;
  }, [startSession]);

  // Transition: active → idle
  const endSession = useCallback(() => {
    if (stateRef.current !== 'active') return;

    clientRef.current?.sendMessage('signal', 'session_end');
    setConversationState('idle');

    const processor = audioProcessorRef.current;
    if (processor && detector) {
      processor.enableWakeWord(detector, () => {
        startSessionRef.current();
      });
    }
  }, [clientRef, audioProcessorRef, detector]);

  const resetSilenceTimer = useCallback(() => {
    clearSilenceTimer();

    if (stateRef.current !== 'active') return;

    silenceTimerRef.current = setTimeout(() => {
      // Don't end while Tank is still speaking — defer
      if (isSpeakingRef.current) {
        return; // Will be re-checked when isSpeaking changes
      }
      endSession();
    }, config.silenceTimeoutMs);
  }, [config.silenceTimeoutMs, clearSilenceTimer, endSession]);

  // When isSpeaking transitions false while in active state, ensure timer is running
  useEffect(() => {
    if (!isSpeaking && stateRef.current === 'active') {
      if (!silenceTimerRef.current) {
        resetSilenceTimer();
      }
    }
  }, [isSpeaking, resetSilenceTimer]);

  // Track signals to reset silence timer
  useEffect(() => {
    if (!latestMessage || stateRef.current !== 'active') return;

    if (latestMessage.type === 'signal') {
      const content = latestMessage.content;
      if (content === 'processing_ended' || content === 'processing_started') {
        resetSilenceTimer();
      }
    } else if (latestMessage.type === 'transcript') {
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
      processor.enableWakeWord(detector, () => {
        startSessionRef.current();
      });
      queueMicrotask(() => setConversationState('idle'));
    } else {
      // Detector not loaded yet — set timeout to fall back to active
      const timeoutId = setTimeout(() => {
        if (stateRef.current === 'loading') {
          console.warn('Wake word detector timeout, falling back to always-on mode');
          setConversationState('active');
        }
      }, 10000); // 10 second timeout

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
