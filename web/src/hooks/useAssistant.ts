import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { VoiceAssistantClient } from '../services/websocket';
import type { WebsocketMessage } from '../services/websocket';
import { AudioProcessor, type CalibrationState } from '../services/audio';
import type { Step, StepType, ToolContent, Message } from '../types/message';

export type { Step, StepType, ToolContent, Message };

export const useAssistant = (sessionId: string) => {
  const [steps, setSteps] = useState<Step[]>([]);
  const [mode, setMode] = useState<'voice' | 'chat'>('voice');
  const [isAssistantTyping, setIsAssistantTyping] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'error' | 'disconnected'>('connecting');
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [calibrationState, setCalibrationState] = useState<CalibrationState>({ status: 'idle' });

  const clientRef = useRef<VoiceAssistantClient | null>(null);
  const audioProcessorRef = useRef<AudioProcessor | null>(null);

  const handleMessage = useCallback((msg: WebsocketMessage) => {
    if (msg.type === 'signal') {
      if (msg.content === 'ready') setConnectionStatus('connected');
      else if (msg.content === 'processing_started') setIsAssistantTyping(true);
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

    setSteps(prev => {
      const updated = [...prev];
      const existingIdx = updated.findIndex(m => m.id === stepId);

      // --- TEXT & THINKING (Streaming) ---
      if (activityType === 'text' || activityType === 'thinking') {
        if (existingIdx > -1) {
          updated[existingIdx] = {
            ...updated[existingIdx],
            content: msg.type === 'transcript' ? msg.content : (updated[existingIdx].content + (msg.content || '')),
            isFinal: msg.is_final
          };
          return updated;
        } else {
          // If we see a FINAL empty message for an ID that doesn't exist, ignore it.
          // But if it has content or is a start of a stream, create it.
          if (!msg.content && msg.is_final) return prev;
          
          return [...prev, { 
            id: stepId, 
            role, 
            type: activityType, 
            content: msg.content || '', 
            msgId, 
            isFinal: msg.is_final 
          }];
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
          result: hasResult ? msg.content : undefined
        };

        if (existingIdx > -1) {
          const existing = updated[existingIdx].content as ToolContent;
          updated[existingIdx] = {
            ...updated[existingIdx],
            content: {
              ...existing,
              ...toolData,
              result: toolData.result || existing.result,
              status: toolData.status || existing.status
            },
            isFinal: msg.is_final
          };
          
          // Weather Card
          if (hasResult && (toolData.name === 'get_weather' || toolData.name === 'weather')) {
             const weatherId = `${msgId}_weather_${turn}_${msg.metadata?.index || 0}`;
             if (!updated.some(m => m.id === weatherId)) {
                try {
                    const res = msg.content;
                    const t = res.match(/'temperature':\s*'([^']+)'/);
                    const c = res.match(/'condition':\s*'([^']+)'/);
                    const l = res.match(/'location':\s*'([^']+)'/);
                    if (t && c && l) {
                        updated.push({ id: weatherId, role: 'assistant', type: 'weather', content: { city: l[1], temp: t[1], condition: c[1], wind: '4km/h' }, msgId });
                    }
                } catch (e) { console.error(e); }
             }
          }
          return updated;
        } else {
          return [...prev, { id: stepId, role, type: 'tool', content: toolData, msgId, isFinal: msg.is_final }];
        }
      }

      return prev;
    });
  }, []);

  useEffect(() => {
    const client = new VoiceAssistantClient(sessionId);
    clientRef.current = client;
    client.connect(handleMessage, (speaking) => setIsSpeaking(speaking), () => setConnectionStatus('connected'));

    const audioProcessor = new AudioProcessor((data) => client.sendAudio(data), {
      onSpeechChange: (isSpeech) => setIsUserSpeaking(isSpeech),
      onCalibrationChange: (state) => {
        setCalibrationState(state);
        if (state.status !== 'ready') setIsUserSpeaking(false);
      },
    });
    audioProcessorRef.current = audioProcessor;
    audioProcessor.start().catch(err => {
        console.error("Failed to start audio processor:", err);
        setConnectionStatus('error');
    });

    const handleBeforeUnload = () => {
      clientRef.current?.disconnect();
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
      client.disconnect();
      audioProcessor.stop();
    };
  }, [sessionId, handleMessage]);

  const sendMessage = useCallback((text: string) => {
    if (clientRef.current) {
      clientRef.current.sendMessage('input', text);
    }
  }, []);

  const toggleMode = useCallback(() => setMode(prev => prev === 'voice' ? 'chat' : 'voice'), []);

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

  return { steps, messages, mode, isAssistantTyping, isSpeaking, isUserSpeaking, isMuted, connectionStatus, calibrationState, sendMessage, toggleMode, toggleMute, getAnalyserNode, stopSpeaking };
};
