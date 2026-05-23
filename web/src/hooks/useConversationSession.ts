/**
 * Conversation session state machine for wake word flow.
 *
 * States:
 *   loading   — wake word detector is loading, audio is gated
 *   idle      — detector armed, gate closed, waiting for wake word
 *   listening — wake word heard, gate open for one utterance
 *
 * Transitions:
 *   loading → idle:      detector loads successfully
 *   loading → listening: detector fails to load (fallback to always-open gate)
 *   idle → listening:    wake word detected (sends "wake", opens gate)
 *   listening → idle:    frontend MicVAD detected end of utterance
 *                        (sends end_of_utterance, closes gate, re-arms detector)
 *
 * Each utterance requires a separate wake word — there is no silence-timer
 * "active session" window. The detector keeps running even during TTS, so
 * the user can always interrupt by saying the wake word again.
 */
import { useState, useEffect, useRef, useCallback } from 'react';

import type { AudioProcessor } from '../services/audio';
import type { WakeWordDetector } from '../services/wakeWordDetector';
import type { VoiceAssistantClient } from '../services/websocket';

export type ConversationState = 'loading' | 'idle' | 'listening';

export interface ConversationSessionConfig {
  /** True when wake word feature is enabled in env config */
  intended: boolean;
  /** True when detector is loaded and ready */
  enabled: boolean;
}

interface UseConversationSessionArgs {
  clientRef: React.RefObject<VoiceAssistantClient | null>;
  audioProcessorRef: React.RefObject<AudioProcessor | null>;
  detector: WakeWordDetector | null;
  audioReady: boolean;
  config: ConversationSessionConfig;
  onSessionStart?: () => void;
}

export function useConversationSession({
  clientRef,
  audioProcessorRef,
  detector,
  audioReady,
  config,
  onSessionStart,
}: UseConversationSessionArgs) {
  // Initial state: 'loading' if wake word intended, 'listening' otherwise
  // (non-wake-word modes don't use this hook for gating, but we still
  // return a state so consumers can render correctly).
  const [conversationState, setConversationState] = useState<ConversationState>(
    config.intended ? 'loading' : 'listening',
  );

  const stateRef = useRef(conversationState);
  const onSessionStartRef = useRef(onSessionStart);
  const startSessionRef = useRef<() => void>(() => {});
  const initialConfigRef = useRef(config.intended);

  useEffect(() => {
    stateRef.current = conversationState;
  }, [conversationState]);

  useEffect(() => {
    onSessionStartRef.current = onSessionStart;
  }, [onSessionStart]);

  // Transition: idle → listening (wake word detected)
  const startSession = useCallback(() => {
    console.log('[ConversationSession] startSession called, current state:', stateRef.current);
    if (stateRef.current === 'listening') return;

    setConversationState('listening');
    audioProcessorRef.current
      ?.disableWakeWord()
      .catch((err) => console.error('[ConversationSession] Failed to disable wake word:', err));
    clientRef.current?.sendMessage('signal', 'wake');
    onSessionStartRef.current?.();
  }, [clientRef, audioProcessorRef]);

  useEffect(() => {
    startSessionRef.current = startSession;
  }, [startSession]);

  // Transition: listening → idle (utterance finished)
  const endUtterance = useCallback(() => {
    console.log('[ConversationSession] endUtterance called, current state:', stateRef.current);
    if (stateRef.current !== 'listening') return;

    clientRef.current?.sendMessage('signal', 'end_of_utterance');
    setConversationState('idle');

    const processor = audioProcessorRef.current;
    if (processor && detector) {
      processor
        .enableWakeWord(detector, () => {
          startSessionRef.current();
        })
        .then(() => {
          console.log('[ConversationSession] Wake word re-armed successfully');
        })
        .catch((err) => console.error('[ConversationSession] Failed to re-arm wake word:', err));
    } else {
      console.warn('[ConversationSession] Cannot re-arm: processor=%o, detector=%o', !!processor, !!detector);
    }
  }, [clientRef, audioProcessorRef, detector]);

  // Subscribe to MicVAD's end-of-utterance via the AudioProcessor callback.
  useEffect(() => {
    if (!initialConfigRef.current) return;
    const processor = audioProcessorRef.current;
    if (!processor) return;

    processor.setOnUtteranceEnd(() => endUtterance());
    return () => {
      processor.setOnUtteranceEnd(null);
    };
  }, [audioProcessorRef, endUtterance]);

  // Arm wake word detector when detector becomes available.
  // Transitions loading → idle on success, or loading → listening on timeout.
  useEffect(() => {
    if (!initialConfigRef.current) return;

    const processor = audioProcessorRef.current;
    if (!processor || !audioReady) return;

    if (detector) {
      processor
        .enableWakeWord(detector, () => {
          startSessionRef.current();
        })
        .catch((err) => console.error('[ConversationSession] Failed to enable wake word:', err));
      queueMicrotask(() => setConversationState('idle'));
    } else {
      const timeoutId = setTimeout(() => {
        if (stateRef.current === 'loading') {
          console.warn('Wake word detector timeout, falling back to always-open mode');
          setConversationState('listening');
        }
      }, 10000);

      return () => clearTimeout(timeoutId);
    }
  }, [detector, audioReady, audioProcessorRef]);

  return { conversationState };
}
