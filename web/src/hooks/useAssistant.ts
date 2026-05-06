import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

import type { Capabilities, WebsocketMessage } from '../services/websocket';
import type { WakeWordDetector } from '../services/wakeWordDetector';
import {
  useConversationSession,
  type ConversationState,
  type ConversationSessionConfig,
} from './useConversationSession';
import { useAssistantStatus, type AssistantStatus } from './useAssistantStatus';
import { useMessageReducer } from './useMessageReducer';
import { useAudioPipeline } from './useAudioPipeline';
import { useChannelAudio } from './useChannelAudio';
import type { Step, StepType, ToolContent, ApprovalContent, Message } from '../types/message';

export type { Step, StepType, ToolContent, ApprovalContent, Message, ConversationState, AssistantStatus };

const DEFAULT_CAPABILITIES: Capabilities = { asr: true, tts: true, speaker_id: false };

const WAKE_WORD_ENABLED = import.meta.env.VITE_WAKE_WORD_ENABLED === 'true';
const WAKE_WORD_SILENCE_TIMEOUT_MS = Number(
  import.meta.env.VITE_WAKE_WORD_SILENCE_TIMEOUT_MS || '5000',
);

export const useAssistant = (
  sessionId: string,
  wakeWordDetector?: WakeWordDetector | null,
  onChannelNotification?: (msg: WebsocketMessage) => void,
) => {
  const [mode, setMode] = useState<'voice' | 'chat'>('voice');
  const [isMuted, setIsMuted] = useState(false);
  const [capabilities, setCapabilities] = useState<Capabilities>(DEFAULT_CAPABILITIES);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

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

  const { steps, messages, latestMessage, handleMessage, addLocalUserStep, loadHistory, appendSteps } =
    useMessageReducer(messageCallbacks);

  // Wrap handleMessage to intercept channel notifications before the reducer
  const channelNotificationRef = useRef(onChannelNotification);
  channelNotificationRef.current = onChannelNotification;

  // --- Channel audio (second playback track) ---
  const channelAudioClientRef = useRef<import('../services/websocket').VoiceAssistantClient | null>(null);
  const channelAudio = useChannelAudio({
    clientRef: channelAudioClientRef,
  });
  const channelAudioRef = useRef(channelAudio);
  channelAudioRef.current = channelAudio;

  // Ref for playback (populated by useAudioPipeline below, used in binary router)
  const localPlaybackRef = useRef<import('../services/audioPlayback').AudioPlayback | null>(null);

  const wrappedHandleMessage = useCallback(
    (msg: WebsocketMessage) => {
      if (msg.type === 'channel_notification') {
        channelNotificationRef.current?.(msg);
        return;
      }
      // Let channel audio hook handle its signals first
      if (channelAudioRef.current?.handleSignal(msg)) {
        return;
      }
      handleMessage(msg);
    },
    [handleMessage],
  );

  // Binary frame router: channel audio track or interactive playback
  const handleBinaryMessage = useCallback(
    (data: ArrayBuffer) => {
      if (channelAudioRef.current?.isChannelAudioActive()) {
        channelAudioRef.current.playChannelChunk(data);
      } else {
        localPlaybackRef.current?.play(data);
      }
    },
    [],
  );

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
    onMessage: wrappedHandleMessage,
    onBinaryMessage: handleBinaryMessage,
    dispatchStatus,
  });

  // Keep local ref in sync with pipeline's playbackRef
  useEffect(() => {
    localPlaybackRef.current = playbackRef.current;
  });

  // Wire channel audio clientRef + re-subscribe after pipeline is connected
  useEffect(() => {
    if (connectionState === 'connected' && clientRef.current) {
      channelAudioClientRef.current = clientRef.current;
      channelAudio.resubscribeAll();
    }
  }, [connectionState]); // eslint-disable-line react-hooks/exhaustive-deps

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
      clientRef.current.sendMessage('input', text, {
        ...(selectedUserId ? { user_id: selectedUserId } : {}),
      });
    },
    [clientRef, playbackRef, addLocalUserStep, isAssistantTyping, dispatchStatus, selectedUserId],
  );

  const respondToApproval = useCallback(
    (_approvalId: string, approved: boolean) => {
      if (!clientRef.current) return;
      // State-machine approval: send as text input so Brain's CONFIRMING
      // mode handles it via the LLM + confirm_action tool.
      const text = approved ? 'approved' : 'rejected';
      clientRef.current.sendMessage('input', text, {});
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
        const historySteps: Step[] = [];

        // Build a lookup of tool_call_id → tool result content for pairing
        const toolResults = new Map<string, string>();
        for (const m of historyMsgs) {
          if (m.role === 'tool' && m.tool_call_id) {
            toolResults.set(m.tool_call_id, m.content);
          }
        }

        let stepIdx = 0;
        for (const m of historyMsgs) {
          // Skip raw tool-result messages — they're merged into tool steps below
          if (m.role === 'tool') continue;

          const msgId = m.msg_id;

          // If assistant message has tool_calls, emit tool steps
          if (m.role === 'assistant' && m.tool_calls?.length) {
            for (const tc of m.tool_calls) {
              const result = toolResults.get(tc.id);
              const toolData: ToolContent = {
                name: tc.function.name,
                arguments: tc.function.arguments,
                status: result !== undefined ? 'success' : 'calling',
                result: result ?? undefined,
              };
              historySteps.push({
                id: `history_tool_${stepIdx++}`,
                role: 'assistant',
                type: 'tool',
                content: toolData,
                msgId,
                isFinal: true,
              });
            }
            // If the assistant message also has text content, emit a text step
            if (m.content) {
              historySteps.push({
                id: `history_text_${stepIdx++}`,
                role: 'assistant',
                type: 'text',
                content: m.content,
                msgId,
                isFinal: true,
                speaker: m.name,
              });
            }
          } else {
            // Regular user or assistant text message
            historySteps.push({
              id: `history_text_${stepIdx++}`,
              role: m.role as 'user' | 'assistant',
              type: 'text',
              content: m.content,
              msgId,
              isFinal: true,
              speaker: m.name,
            });
          }
        }

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
    selectedUserId,
    setSelectedUserId,
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
    appendSteps,
    ttsRms,
    channelAudio,
  };
};
