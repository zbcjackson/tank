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
import { useListenMode, type ListenMode } from './useListenMode';
import { fetchConversationMessages, type HistoryMessage } from './useConversationList';
import type { Step, StepType, ToolContent, ApprovalContent, Message } from '../types/message';

export type {
  Step,
  StepType,
  ToolContent,
  ApprovalContent,
  Message,
  ConversationState,
  AssistantStatus,
  ListenMode,
};

const DEFAULT_CAPABILITIES: Capabilities = { asr: true, tts: true, speaker_id: false };

const WAKE_WORD_BUILD_ENABLED = import.meta.env.VITE_WAKE_WORD_ENABLED === 'true';

/**
 * Convert backend conversation history into reducer Steps.
 *
 * Pure / side-effect-free so both ``resumeConversation`` (user picks
 * a session from the sidebar) and the auto-resume path (page refresh
 * with a same-day conversation) use the same conversion.
 */
function historyToSteps(historyMsgs: HistoryMessage[]): Step[] {
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

    if (m.kind === 'image' && m.attachments?.length) {
      for (let idx = 0; idx < m.attachments.length; idx++) {
        const att = m.attachments[idx];
        historySteps.push({
          id: `history_image_${stepIdx++}_${idx}`,
          role: 'assistant',
          type: 'image',
          content: {
            url: att.url,
            mimeType: att.mime_type,
            caption: idx === 0 ? (att.caption ?? '') : '',
          },
          msgId,
          isFinal: true,
          speaker: m.name,
        });
      }
      continue;
    }

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

  return historySteps;
}

export const useAssistant = (
  sessionId: string,
  wakeWordDetector?: WakeWordDetector | null,
  onChannelNotification?: (msg: WebsocketMessage) => void,
  backendUrl?: string,
) => {
  const [mode, setMode] = useState<'voice' | 'chat'>('voice');
  const [capabilities, setCapabilities] = useState<Capabilities>(DEFAULT_CAPABILITIES);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [isPttActive, setIsPttActive] = useState(false);
  const [isContinuousMicOn, setIsContinuousMicOn] = useState(false);

  const wakeWordAvailable = WAKE_WORD_BUILD_ENABLED;
  const {
    listenMode,
    voiceInterruptEnabled,
    chatSpeakEnabled,
    setListenMode,
    setVoiceInterruptEnabled,
    setChatSpeakEnabled,
  } = useListenMode({ wakeWordAvailable: WAKE_WORD_BUILD_ENABLED });

  // speakEnabledRef: voice mode always true; chat mode uses chatSpeakEnabled.
  const speakEnabledRef = useRef(mode === 'voice' || chatSpeakEnabled);
  useEffect(() => {
    speakEnabledRef.current = mode === 'voice' || chatSpeakEnabled;
  }, [mode, chatSpeakEnabled]);

  const { assistantStatus, dispatchStatus } = useAssistantStatus();
  const conversationStateRef = useRef<ConversationState>('listening');

  // Derived booleans for backward compatibility
  const isAssistantTyping =
    assistantStatus === 'thinking' ||
    assistantStatus === 'tool_calling' ||
    assistantStatus === 'responding' ||
    assistantStatus === 'speaking';
  const isSpeaking = assistantStatus === 'speaking';

  // --- Message/step state ---
  const loadHistoryRef = useRef<((steps: Step[]) => void) | null>(null);

  const messageCallbacks = useMemo(
    () => ({
      dispatchStatus,
      onCapabilities: (caps: Capabilities) => {
        setCapabilities(caps);
        if (!caps.asr) setMode('chat');
      },
      onResumedConversation: (conversationId: string) => {
        fetchConversationMessages(conversationId)
          .then((historyMsgs) => {
            const steps = historyToSteps(historyMsgs);
            loadHistoryRef.current?.(steps);
          })
          .catch((e) => {
            console.error('Failed to load resumed conversation:', e);
          });
      },
    }),
    [dispatchStatus],  
  );

  const { steps, messages, handleMessage, addLocalUserStep, loadHistory, appendSteps } =
    useMessageReducer(messageCallbacks);

  // Keep ref in sync so the callback closure can call loadHistory
  loadHistoryRef.current = loadHistory;

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
    speakEnabledRef,
    backendUrl,
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
  // Wake word session is only active when the user has explicitly chosen
  // listenMode='wake_word'. Other modes bypass useConversationSession
  // (it falls into its always-active branch when intended=false).
  const wakeWordConfig: ConversationSessionConfig = useMemo(
    () => ({
      intended: listenMode === 'wake_word',
      enabled: !!wakeWordDetector,
    }),
    [listenMode, wakeWordDetector],
  );

  const { conversationState } = useConversationSession({
    clientRef,
    audioProcessorRef,
    detector: listenMode === 'wake_word' ? (wakeWordDetector ?? null) : null,
    audioReady,
    config: wakeWordConfig,
    onSessionStart: undefined,
  });

  // Keep ref in sync so the AudioProcessor callback can read it
  useEffect(() => {
    conversationStateRef.current = conversationState;
  }, [conversationState]);

  // Reset continuous-mic state whenever listenMode changes — switching
  // modes should always leave the mic OFF. If the mic was ON when
  // switching away from continuous mode, send end_of_utterance so the
  // backend cleans up any in-progress ASR session.
  useEffect(() => {
    if (isContinuousMicOn) {
      clientRef.current?.sendMessage('signal', 'end_of_utterance');
      setIsContinuousMicOn(false);
    }
    // Only react to listenMode changes — isContinuousMicOn must not
    // re-trigger this effect or it would fight with toggleContinuousMic.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listenMode]);

  // --- Listen mode orchestration ---
  // All modes start with mic OFF on entry. Explicit user actions
  // (toggleContinuousMic / wake word / PTT press) open the gate.
  useEffect(() => {
    const processor = audioProcessorRef.current;
    if (!processor || !audioReady) return;

    if (mode === 'chat') {
      processor.disableWakeWord().catch(() => {});
      processor.setBypassMicVad(false);
      if (!isPttActive) processor.pause();
      return;
    }

    if (listenMode === 'wake_word') {
      processor.setBypassMicVad(false);
      // useConversationSession owns the gate — we don't pause/resume here.
      return;
    }

    if (listenMode === 'continuous') {
      processor.disableWakeWord().catch(() => {});
      if (isContinuousMicOn) {
        processor.resume();
        processor.setBypassMicVad(true);
      } else {
        processor.setBypassMicVad(false);
        processor.pause();
      }
    } else if (listenMode === 'ptt') {
      processor.disableWakeWord().catch(() => {});
      processor.setBypassMicVad(false);
      if (!isPttActive) processor.pause();
    }
  }, [mode, listenMode, audioReady, audioProcessorRef, isPttActive, isContinuousMicOn]);

  // During TTS playback in continuous mode (mic on): bypass the frontend
  // MicVAD gate so audio flows to the backend, allowing natural interrupt.
  // In wake-word mode: only bypass when interruption is enabled.
  // Otherwise mic stays gated during TTS.
  useEffect(() => {
    const processor = audioProcessorRef.current;
    if (!processor) return;

    const allowInterrupt =
      (listenMode === 'continuous' && isContinuousMicOn) ||
      (listenMode === 'wake_word' && voiceInterruptEnabled);

    processor.setSpeaking(isSpeaking && allowInterrupt);
  }, [
    isSpeaking,
    listenMode,
    isContinuousMicOn,
    voiceInterruptEnabled,
    audioProcessorRef,
  ]);

  // --- Actions ---
  const sendMessage = useCallback(
    (text: string, attachments?: Array<{ media_uri: string; mime_type: string }>) => {
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
        ...(attachments && attachments.length > 0 ? { attachments } : {}),
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

  const toggleContinuousMic = useCallback(() => {
    const processor = audioProcessorRef.current;
    if (!processor) return;
    setIsContinuousMicOn((prev) => {
      const next = !prev;
      if (next) {
        processor.resume();
      } else {
        // Close the gate first, then signal end_of_utterance so the
        // backend finalizes any in-progress ASR segment. WebSocket
        // in-order delivery ensures the signal arrives after the last
        // audio frame.
        clientRef.current?.sendMessage('signal', 'end_of_utterance');
        processor.pause();
      }
      return next;
    });
  }, [audioProcessorRef, clientRef]);

  const getAnalyserNode = useCallback(
    () => playbackRef.current?.getAnalyserNode() ?? null,
    [playbackRef],
  );

  const stopSpeaking = useCallback(() => {
    clientRef.current?.sendInterrupt();
    playbackRef.current?.stop();
    dispatchStatus({ type: 'INTERRUPT' });
  }, [clientRef, playbackRef, dispatchStatus]);

  // --- Push-to-talk ---
  // Press: interrupt any in-flight response, open mic.
  // Release: send end_of_utterance so the backend force-finalizes the
  // current speech segment (skips silence detection), then pause the mic.
  const startPtt = useCallback(() => {
    const processor = audioProcessorRef.current;
    if (!processor) return;
    if (isAssistantTyping) {
      clientRef.current?.sendInterrupt();
      playbackRef.current?.stop();
      dispatchStatus({ type: 'INTERRUPT' });
    }
    processor.resumeForPtt();
    setIsPttActive(true);
  }, [audioProcessorRef, clientRef, playbackRef, dispatchStatus, isAssistantTyping]);

  const stopPtt = useCallback(() => {
    const processor = audioProcessorRef.current;
    if (!processor) return;
    clientRef.current?.sendMessage('signal', 'end_of_utterance');
    processor.pauseForPtt();
    setIsPttActive(false);
  }, [audioProcessorRef, clientRef]);

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
      try {
        const historyMsgs = await fetchConversationMessages(conversationId);
        const historySteps = historyToSteps(historyMsgs);

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
    toggleContinuousMic,
    isContinuousMicOn,
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
    // Listen mode + speak mode
    listenMode,
    setListenMode,
    voiceInterruptEnabled,
    setVoiceInterruptEnabled,
    chatSpeakEnabled,
    setChatSpeakEnabled,
    wakeWordAvailable,
    isPttActive,
    startPtt,
    stopPtt,
  };
};
