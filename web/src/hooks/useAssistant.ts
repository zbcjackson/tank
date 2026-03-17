import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  VoiceAssistantClient,
  type ConnectionState,
  type ConnectionMetadata,
  type Capabilities,
} from '../services/websocket';
import type { WebsocketMessage } from '../services/websocket';
import { AudioProcessor, type CalibrationState } from '../services/audio';
import type { WakeWordDetector } from '../services/wakeWordDetector';
import {
  useConversationSession,
  type ConversationState,
  type ConversationSessionConfig,
} from './useConversationSession';
import type { Step, StepType, ToolContent, Message } from '../types/message';

export type { Step, StepType, ToolContent, Message, ConversationState };

const DEFAULT_CAPABILITIES: Capabilities = { asr: true, tts: true, speaker_id: false };

const WAKE_WORD_ENABLED = import.meta.env.VITE_WAKE_WORD_ENABLED === 'true';
const WAKE_WORD_SILENCE_TIMEOUT_MS = Number(
  import.meta.env.VITE_WAKE_WORD_SILENCE_TIMEOUT_MS || '5000',
);

export const useAssistant = (sessionId: string, wakeWordDetector?: WakeWordDetector | null) => {
  const [steps, setSteps] = useState<Step[]>([]);
  const [mode, setMode] = useState<'voice' | 'chat'>('voice');
  const [isAssistantTyping, setIsAssistantTyping] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');
  const [connectionMetadata, setConnectionMetadata] = useState<ConnectionMetadata>({});
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [calibrationState, setCalibrationState] = useState<CalibrationState>({ status: 'idle' });
  const [capabilities, setCapabilities] = useState<Capabilities>(DEFAULT_CAPABILITIES);
  const [latestMessage, setLatestMessage] = useState<WebsocketMessage | null>(null);
  const [audioReady, setAudioReady] = useState(false);

  const clientRef = useRef<VoiceAssistantClient | null>(null);
  const audioProcessorRef = useRef<AudioProcessor | null>(null);
  const audioStartedRef = useRef(false);

  const wakeWordConfig: ConversationSessionConfig = useMemo(
    () => ({
      intended: WAKE_WORD_ENABLED,
      enabled: !!wakeWordDetector,
      silenceTimeoutMs: WAKE_WORD_SILENCE_TIMEOUT_MS,
    }),
    [wakeWordDetector],
  );

  const clearSteps = useCallback(() => setSteps([]), []);

  const handleMessage = useCallback((msg: WebsocketMessage) => {
    // Track latest message for conversation session hook
    setLatestMessage(msg);

    if (msg.type === 'signal') {
      if (msg.content === 'ready') {
        // Extract capabilities from ready signal metadata
        const caps = msg.metadata?.capabilities as Capabilities | undefined;
        if (caps) {
          setCapabilities(caps);
          // Force chat mode when ASR is disabled
          if (!caps.asr) {
            setMode('chat');
          }
        }
      } else if (msg.content === 'processing_started') setIsAssistantTyping(true);
      else if (msg.content === 'processing_ended') setIsAssistantTyping(false);
      return;
    }

    const role = msg.is_user ? 'user' : 'assistant';
    const msgId = msg.msg_id || (msg.is_user ? 'user_default' : 'assistant_default');

    // Parse activity type and turn
    const updateType = msg.metadata?.update_type;
    const metadataType = typeof updateType === 'string' ? updateType.split('.').pop() : null;
    const turn = msg.metadata?.turn || 0;

    let activityType: StepType = 'text';
    if (metadataType === 'THOUGHT') activityType = 'thinking';
    else if (metadataType === 'TOOL') activityType = 'tool';

    if (msg.type === 'transcript') activityType = 'text';

    const stepId = msg.metadata?.step_id as string;

    setSteps((prev) => {
      const updated = [...prev];
      const existingIdx = updated.findIndex((m) => m.id === stepId);

      // --- Reconcile backend echo with optimistic local user step ---
      if (msg.type === 'transcript' && msg.is_user) {
        const localIdx = updated.findLastIndex(
          (s) => s.role === 'user' && s.id.startsWith('local_') && s.content === msg.content,
        );
        if (localIdx > -1) {
          updated[localIdx] = {
            ...updated[localIdx],
            id: stepId,
            msgId,
            speaker: msg.speaker || updated[localIdx].speaker,
          };
          return updated;
        }
      }

      // --- TEXT & THINKING (Streaming) ---
      if (activityType === 'text' || activityType === 'thinking') {
        if (existingIdx > -1) {
          updated[existingIdx] = {
            ...updated[existingIdx],
            content:
              msg.type === 'transcript'
                ? msg.content
                : updated[existingIdx].content + (msg.content || ''),
            isFinal: msg.is_final,
            speaker: msg.speaker || updated[existingIdx].speaker,
          };
          return updated;
        } else {
          // If we see a FINAL empty message for an ID that doesn't exist, ignore it.
          // But if it has content or is a start of a stream, create it.
          if (!msg.content && msg.is_final) return prev;

          return [
            ...prev,
            {
              id: stepId,
              role,
              type: activityType,
              content: msg.content || '',
              msgId,
              isFinal: msg.is_final,
              speaker: msg.speaker || undefined,
            },
          ];
        }
      }

      // --- TOOL ACTIVITIES ---
      if (activityType === 'tool') {
        const status = (msg.metadata?.status as string) || 'calling';
        const hasResult = status === 'success' || status === 'error';
        const toolData: ToolContent = {
          name: (msg.metadata?.name as string) || '',
          arguments: (msg.metadata?.arguments as string) || '',
          status,
          result: hasResult ? msg.content : undefined,
        };

        if (existingIdx > -1) {
          const existing = updated[existingIdx].content as ToolContent;
          updated[existingIdx] = {
            ...updated[existingIdx],
            content: {
              ...existing,
              ...toolData,
              result: toolData.result || existing.result,
              status: toolData.status || existing.status,
            },
            isFinal: msg.is_final,
          };

          // Weather Card
          if (hasResult && (toolData.name === 'get_weather' || toolData.name === 'weather')) {
            const weatherId = `${msgId}_weather_${turn}_${msg.metadata?.index || 0}`;
            if (!updated.some((m) => m.id === weatherId)) {
              try {
                const res = msg.content;
                const t = res.match(/'temperature':\s*'([^']+)'/);
                const c = res.match(/'condition':\s*'([^']+)'/);
                const l = res.match(/'location':\s*'([^']+)'/);
                if (t && c && l) {
                  updated.push({
                    id: weatherId,
                    role: 'assistant',
                    type: 'weather',
                    content: { city: l[1], temp: t[1], condition: c[1], wind: '4km/h' },
                    msgId,
                  });
                }
              } catch (e) {
                console.error(e);
              }
            }
          }
          return updated;
        } else {
          return [
            ...prev,
            {
              id: stepId,
              role,
              type: 'tool',
              content: toolData,
              msgId,
              isFinal: msg.is_final,
              speaker: msg.speaker || undefined,
            },
          ];
        }
      }

      return prev;
    });
  }, []);

  useEffect(() => {
    const client = new VoiceAssistantClient(sessionId);
    clientRef.current = client;
    client.connect(
      handleMessage,
      (speaking) => setIsSpeaking(speaking),
      () => {}, // onOpen - handled by onConnectionStateChange
      (state, metadata) => {
        setConnectionState(state);
        setConnectionMetadata(metadata || {});

        // Reset UI state on reconnecting
        if (state === 'reconnecting') {
          setIsAssistantTyping(false);
          setIsSpeaking(false);
          setIsUserSpeaking(false);
        }
      },
    );

    // AudioProcessor is created eagerly but started lazily (after capabilities arrive)
    const audioProcessor = new AudioProcessor((data) => client.sendAudio(data), {
      onSpeechChange: (isSpeech) => setIsUserSpeaking(isSpeech),
      onCalibrationChange: (state) => {
        setCalibrationState(state);
        if (state.status !== 'ready') setIsUserSpeaking(false);
      },
    });
    audioProcessorRef.current = audioProcessor;
    audioStartedRef.current = false;

    const handleBeforeUnload = () => {
      clientRef.current?.disconnect();
      audioProcessorRef.current?.stop();
    };
    window.addEventListener('beforeunload', handleBeforeUnload);

    const handleDeviceChange = () => audioProcessorRef.current?.recalibrate();
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        audioProcessorRef.current?.recalibrate();
      }
    };
    navigator.mediaDevices?.addEventListener('devicechange', handleDeviceChange);
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      navigator.mediaDevices?.removeEventListener('devicechange', handleDeviceChange);
      document.removeEventListener('visibilitychange', handleVisibility);
      // Disconnect immediately — the backend keeps the session alive via
      // an idle timer, so a strict-mode remount with the same session ID
      // will reattach to the existing pipeline.
      client.disconnect();
      audioProcessor.stop();
      clientRef.current = null;
      audioProcessorRef.current = null;
    };
  }, [sessionId, handleMessage]);

  // Start AudioProcessor only after capabilities confirm ASR is enabled
  useEffect(() => {
    const processor = audioProcessorRef.current;
    if (!processor || audioStartedRef.current) return;
    if (!capabilities.asr) return;

    audioStartedRef.current = true;
    processor
      .start()
      .then(() => {
        setAudioReady(true);
      })
      .catch((err) => {
        console.error('Failed to start audio processor:', err);
        setConnectionState('failed');
        setConnectionMetadata({ error: 'Failed to start audio processor' });
      });
  }, [capabilities.asr]);

  // Conversation session (wake word state machine)
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
  }, [conversationState]);

  const sendMessage = useCallback((text: string) => {
    if (!clientRef.current) return;

    // Optimistic local user step — visible immediately without waiting for backend echo
    const localMsgId = `local_${Date.now()}`;
    const localStepId = `${localMsgId}_text_0`;
    setSteps((prev) => [
      ...prev,
      {
        id: localStepId,
        role: 'user' as const,
        type: 'text' as const,
        content: text,
        msgId: localMsgId,
        isFinal: true,
      },
    ]);

    clientRef.current.sendMessage('input', text);
  }, []);

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
  }, []);

  const getAnalyserNode = useCallback(() => clientRef.current?.getAnalyserNode() ?? null, []);

  const stopSpeaking = useCallback(() => {
    clientRef.current?.stopSpeaking();
    setIsSpeaking(false);
    setIsAssistantTyping(false);
  }, []);

  const manualReconnect = useCallback(() => {
    clientRef.current?.reconnect();
  }, []);

  const pauseAudioCapture = useCallback(() => {
    audioProcessorRef.current?.pause();
  }, []);

  const resumeAudioCapture = useCallback(() => {
    audioProcessorRef.current?.resume();
  }, []);

  // Group flat steps into messages by msgId
  const messages = useMemo((): Message[] => {
    const map = new Map<string, Message>();
    for (const step of steps) {
      let msg = map.get(step.msgId);
      if (!msg) {
        msg = { id: step.msgId, role: step.role, steps: [], isComplete: false };
        map.set(step.msgId, msg);
      }
      msg.steps.push(step);
      if (step.isFinal) msg.isComplete = true;
    }
    return Array.from(map.values());
  }, [steps]);

  return {
    steps,
    messages,
    mode,
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
  };
};
