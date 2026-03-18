import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

import type { Capabilities } from '../services/websocket';
import type { WakeWordDetector } from '../services/wakeWordDetector';
import {
  useConversationSession,
  type ConversationState,
  type ConversationSessionConfig,
} from './useConversationSession';
import { useAssistantStatus, type AssistantStatus } from './useAssistantStatus';
import { useMessageReducer } from './useMessageReducer';
import { useAudioPipeline } from './useAudioPipeline';
import type { Step, StepType, ToolContent, Message } from '../types/message';

export type { Step, StepType, ToolContent, Message, ConversationState, AssistantStatus };

const DEFAULT_CAPABILITIES: Capabilities = { asr: true, tts: true, speaker_id: false };

const WAKE_WORD_ENABLED = import.meta.env.VITE_WAKE_WORD_ENABLED === 'true';
const WAKE_WORD_SILENCE_TIMEOUT_MS = Number(
  import.meta.env.VITE_WAKE_WORD_SILENCE_TIMEOUT_MS || '5000',
);

export const useAssistant = (sessionId: string, wakeWordDetector?: WakeWordDetector | null) => {
  const [mode, setMode] = useState<'voice' | 'chat'>('voice');
  const [isMuted, setIsMuted] = useState(false);
  const [capabilities, setCapabilities] = useState<Capabilities>(DEFAULT_CAPABILITIES);

  const { assistantStatus, dispatchStatus } = useAssistantStatus();
  const conversationStateRef = useRef<ConversationState>('active');

  // Derived booleans for backward compatibility
  const isAssistantTyping =
    assistantStatus === 'thinking' ||
    assistantStatus === 'tool_calling' ||
    assistantStatus === 'responding' ||
    assistantStatus === 'speaking';
  const isSpeaking = assistantStatus === 'speaking';

  // --- Message/step state ---
  const messageCallbacks = useMemo(
    () => ({
      dispatchStatus,
      onCapabilities: (caps: Capabilities) => {
        setCapabilities(caps);
        if (!caps.asr) setMode('chat');
      },
    }),
    [dispatchStatus],
  );

  const { steps, messages, latestMessage, handleMessage, clearSteps, addLocalUserStep } =
    useMessageReducer(messageCallbacks);

  // --- Audio pipeline ---
  const {
    clientRef,
    audioProcessorRef,
    playbackRef,
    connectionState,
    connectionMetadata,
    isUserSpeaking,
    setIsUserSpeaking,
    calibrationState,
    audioReady,
    ttsRms,
  } = useAudioPipeline({
    sessionId,
    capabilities,
    conversationStateRef,
    onMessage: handleMessage,
    dispatchStatus,
  });

  // --- Wake word / conversation session ---
  const wakeWordConfig: ConversationSessionConfig = useMemo(
    () => ({
      intended: WAKE_WORD_ENABLED,
      enabled: !!wakeWordDetector,
      silenceTimeoutMs: WAKE_WORD_SILENCE_TIMEOUT_MS,
    }),
    [wakeWordDetector],
  );

  const { conversationState } = useConversationSession({
    clientRef,
    audioProcessorRef,
    detector: wakeWordDetector ?? null,
    audioReady,
    latestMessage,
    isSpeaking,
    config: wakeWordConfig,
    onSessionStart: clearSteps,
  });

  // Keep ref in sync so the AudioProcessor callback can read it
  useEffect(() => {
    conversationStateRef.current = conversationState;
  }, [conversationState]);

  // Gate audio during 'loading' state
  useEffect(() => {
    const processor = audioProcessorRef.current;
    if (!processor) return;

    if (conversationState === 'loading') {
      processor.pause();
    } else if (conversationState === 'active') {
      processor.resume();
    }
    // 'idle' state is handled by enableWakeWord() in useConversationSession
  }, [conversationState, audioProcessorRef]);

  // --- Actions ---
  const sendMessage = useCallback(
    (text: string) => {
      if (!clientRef.current) return;
      addLocalUserStep(text);
      clientRef.current.sendMessage('input', text);
    },
    [clientRef, addLocalUserStep],
  );

  const toggleMode = useCallback(
    () =>
      setMode((prev) => {
        if (prev === 'voice') return 'chat';
        return capabilities.asr ? 'voice' : 'chat';
      }),
    [capabilities.asr],
  );

  const toggleMute = useCallback(() => {
    const processor = audioProcessorRef.current;
    if (processor) {
      const newMuted = !processor.isMuted();
      processor.setMuted(newMuted);
      setIsMuted(newMuted);
      if (newMuted) setIsUserSpeaking(false);
    }
  }, [audioProcessorRef, setIsUserSpeaking]);

  const getAnalyserNode = useCallback(
    () => playbackRef.current?.getAnalyserNode() ?? null,
    [playbackRef],
  );

  const stopSpeaking = useCallback(() => {
    clientRef.current?.sendInterrupt();
    playbackRef.current?.stop();
    dispatchStatus({ type: 'INTERRUPT' });
  }, [clientRef, playbackRef, dispatchStatus]);

  const manualReconnect = useCallback(() => {
    clientRef.current?.reconnect();
  }, [clientRef]);

  const pauseAudioCapture = useCallback(() => {
    audioProcessorRef.current?.pause();
  }, [audioProcessorRef]);

  const resumeAudioCapture = useCallback(() => {
    audioProcessorRef.current?.resume();
  }, [audioProcessorRef]);

  return {
    steps,
    messages,
    mode,
    assistantStatus,
    isAssistantTyping,
    isSpeaking,
    isUserSpeaking,
    isMuted,
    connectionState,
    connectionMetadata,
    calibrationState,
    capabilities,
    conversationState,
    sendMessage,
    toggleMode,
    toggleMute,
    getAnalyserNode,
    stopSpeaking,
    manualReconnect,
    pauseAudioCapture,
    resumeAudioCapture,
    ttsRms,
  };
};
