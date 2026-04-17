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
import type { Step, StepType, ToolContent, ApprovalContent, Message } from '../types/message';

export type { Step, StepType, ToolContent, ApprovalContent, Message, ConversationState, AssistantStatus };

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

  const { steps, messages, latestMessage, handleMessage, addLocalUserStep, loadHistory } =
    useMessageReducer(messageCallbacks);

  // --- Audio pipeline ---
  const {
    clientRef,
    audioProcessorRef,
    playbackRef,
    connectionState,
    connectionMetadata,
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
    onSessionStart: undefined,
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

  // During TTS playback, bypass frontend MicVAD gate so audio flows to
  // the backend. The backend VAD (with echo-guard threshold) detects
  // user speech and can trigger an interrupt.
  useEffect(() => {
    audioProcessorRef.current?.setSpeaking(isSpeaking);
  }, [isSpeaking, audioProcessorRef]);

  // --- Actions ---
  const sendMessage = useCallback(
    (text: string) => {
      if (!clientRef.current) return;
      // Auto-interrupt if assistant is still speaking/responding
      if (isAssistantTyping) {
        clientRef.current.sendInterrupt();
        playbackRef.current?.stop();
        dispatchStatus({ type: 'INTERRUPT' });
      }
      addLocalUserStep(text);
      clientRef.current.sendMessage('input', text);
    },
    [clientRef, playbackRef, addLocalUserStep, isAssistantTyping, dispatchStatus],
  );

  const respondToApproval = useCallback(
    (approvalId: string, approved: boolean) => {
      if (!clientRef.current) return;
      clientRef.current.sendMessage('approval_response', '', {
        approval_id: approvalId,
        approved,
        reason: '',
      });
    },
    [clientRef],
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
    }
  }, [audioProcessorRef]);

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

  /**
   * Resume a persisted conversation: load history into UI and tell backend to switch.
   */
  const resumeConversation = useCallback(
    async (conversationId: string) => {
      const { fetchConversationMessages } = await import('./useConversationList');
      try {
        const historyMsgs = await fetchConversationMessages(conversationId);
        const historySteps: Step[] = historyMsgs.map((m, i) => ({
          id: `history_${i}`,
          role: m.role as 'user' | 'assistant',
          type: 'text' as StepType,
          content: m.content,
          msgId: m.msg_id,
          isFinal: true,
          speaker: m.name,
        }));
        loadHistory(historySteps);

        clientRef.current?.sendMessage('signal', 'resume_conversation', {
          conversation_id: conversationId,
        });

        setMode('chat');
      } catch (e) {
        console.error('Failed to resume conversation:', e);
      }
    },
    [clientRef, loadHistory],
  );

  /**
   * Start a new conversation: clear UI and tell backend.
   */
  const newConversation = useCallback(() => {
    loadHistory([]);
    clientRef.current?.sendMessage('signal', 'new_conversation', {});
  }, [clientRef, loadHistory]);

  return {
    steps,
    messages,
    mode,
    assistantStatus,
    isAssistantTyping,
    isSpeaking,
    isMuted,
    connectionState,
    connectionMetadata,
    capabilities,
    conversationState,
    wakeWordKeyword: wakeWordDetector?.keyword ?? null,
    sendMessage,
    respondToApproval,
    toggleMode,
    toggleMute,
    getAnalyserNode,
    stopSpeaking,
    manualReconnect,
    pauseAudioCapture,
    resumeAudioCapture,
    resumeConversation,
    newConversation,
    ttsRms,
  };
};
