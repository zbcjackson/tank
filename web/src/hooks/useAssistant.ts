import { useState, useEffect, useRef, useCallback } from 'react';
import { VoiceAssistantClient } from '../services/websocket';
import type { WebsocketMessage } from '../services/websocket';
import { AudioProcessor } from '../services/audio';

export type StepType = 'thinking' | 'tool' | 'text' | 'weather';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  type: StepType;
  content: any;
  msgId: string;
  isFinal?: boolean;
}

export const useAssistant = (sessionId: string) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mode, setMode] = useState<'voice' | 'chat'>('voice');
  const [isAssistantTyping, setIsAssistantTyping] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'error' | 'disconnected'>('connecting');
  
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
    const metadataType = msg.metadata?.update_type ? msg.metadata.update_type.split('.').pop() : null;
    const turn = msg.metadata?.turn || 0;

    let activityType: StepType = 'text';
    if (metadataType === 'THOUGHT') activityType = 'thinking';
    else if (metadataType === 'TOOL_CALL' || metadataType === 'TOOL_RESULT') activityType = 'tool';
    else activityType = 'text';

    if (msg.type === 'transcript') activityType = 'text';

    // Unique ID including TURN to allow multiple separate thinking/text phases
    let stepId = `${msgId}_${activityType}_${turn}`;
    if (activityType === 'tool') {
        stepId += `_${msg.metadata?.index || 0}`;
    }

    setMessages(prev => {
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
        const toolData = {
          name: msg.metadata?.name || '',
          arguments: msg.metadata?.arguments || '',
          status: msg.metadata?.status || 'calling',
          result: metadataType === 'TOOL_RESULT' ? msg.content : undefined
        };

        if (existingIdx > -1) {
          updated[existingIdx] = {
            ...updated[existingIdx],
            content: { 
              ...updated[existingIdx].content, 
              ...toolData, 
              result: toolData.result || updated[existingIdx].content.result,
              status: toolData.status || updated[existingIdx].content.status
            },
            isFinal: msg.is_final
          };
          
          // Weather Card
          if (metadataType === 'TOOL_RESULT' && (toolData.name === 'get_weather' || toolData.name === 'weather')) {
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

    const audioProcessor = new AudioProcessor((data) => client.sendAudio(data));
    audioProcessorRef.current = audioProcessor;
    audioProcessor.start().catch(err => {
        console.error("Failed to start audio processor:", err);
        setConnectionStatus('error');
    });

    const handleBeforeUnload = () => {
      clientRef.current?.disconnect();
    };
    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
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

  return { messages, mode, isAssistantTyping, isSpeaking, connectionStatus, sendMessage, toggleMode };
};
