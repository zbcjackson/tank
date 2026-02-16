import { useState, useEffect, useRef, useCallback } from 'react';
import { VoiceAssistantClient } from '../services/websocket';
import type { WebsocketMessage } from '../services/websocket';
import { AudioProcessor } from '../services/audio';
import type { ChatMessage } from '../components/Assistant/ChatMode';

export const useAssistant = (sessionId: string) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mode, setMode] = useState<'voice' | 'chat'>('voice');
  const [isAssistantTyping, setIsAssistantTyping] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'error' | 'disconnected'>('connecting');
  
  const clientRef = useRef<VoiceAssistantClient | null>(null);
  const audioProcessorRef = useRef<AudioProcessor | null>(null);
  const currentAssistantMsgIdRef = useRef<string | null>(null);

  const handleMessage = useCallback((msg: WebsocketMessage) => {
    if (msg.type === 'transcript') {
      // User is speaking
      setMessages(prev => {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg && lastMsg.role === 'user') {
          // Update existing user message
          const newSteps = [...lastMsg.steps];
          newSteps[0] = { ...newSteps[0], content: msg.content };
          return [...prev.slice(0, -1), { ...lastMsg, steps: newSteps }];
        } else {
          // New user message
          return [...prev, { role: 'user', steps: [{ id: Date.now().toString(), type: 'text', content: msg.content }] }];
        }
      });
    } else if (msg.type === 'text' || msg.type === 'update') {
      setIsAssistantTyping(!msg.is_final);
      
      const updateTypeStr = msg.metadata?.update_type;
      // Backend sends str(UpdateType.X) which might be "UpdateType.THOUGHT"
      const updateType = updateTypeStr ? updateTypeStr.split('.').pop() : 'TEXT';
      
      const msgId = msg.metadata?.msg_id || 'default_assistant';
      currentAssistantMsgIdRef.current = msgId;

      setMessages(prev => {
        let lastMsg = prev[prev.length - 1];
        
        // If last message is not from assistant or different ID, create new one
        if (!lastMsg || lastMsg.role !== 'assistant' || (msg.metadata?.msg_id && lastMsg.steps.some(s => s.id === msg.metadata.msg_id) === false)) {
            // Check if we already have an assistant message for this ID (rare but possible if out of order)
            // For now, assume sequential
            if (lastMsg?.role === 'assistant' && msg.is_final && msg.content === "") return prev;
            
            lastMsg = { role: 'assistant', steps: [] };
            prev = [...prev, lastMsg];
        }

        const newSteps = [...lastMsg.steps];
        
        if (updateType === 'THOUGHT') {
          const stepIdx = newSteps.findIndex(s => s.type === 'thinking' && s.id === msgId + '_thought');
          if (stepIdx > -1) {
            newSteps[stepIdx] = { ...newSteps[stepIdx], content: newSteps[stepIdx].content + msg.content };
          } else {
            newSteps.push({ id: msgId + '_thought', type: 'thinking', content: msg.content });
          }
        } else if (updateType === 'TEXT') {
          const stepIdx = newSteps.findIndex(s => s.type === 'text' && s.id === msgId + '_text');
          if (stepIdx > -1) {
            newSteps[stepIdx] = { ...newSteps[stepIdx], content: newSteps[stepIdx].content + msg.content };
          } else {
            newSteps.push({ id: msgId + '_text', type: 'text', content: msg.content });
          }
        } else if (updateType === 'TOOL_CALL') {
          const toolIdx = msg.metadata?.index || 0;
          const stepId = `${msgId}_tool_${toolIdx}`;
          const stepIdx = newSteps.findIndex(s => s.id === stepId);
          
          const toolData = {
            name: msg.metadata?.name || '',
            arguments: msg.metadata?.arguments || '',
            status: msg.metadata?.status || 'calling'
          };

          if (stepIdx > -1) {
            newSteps[stepIdx] = { ...newSteps[stepIdx], content: toolData };
          } else {
            newSteps.push({ id: stepId, type: 'tool', content: toolData });
          }
        } else if (updateType === 'TOOL_RESULT') {
          const toolIdx = msg.metadata?.index || 0;
          const stepId = `${msgId}_tool_${toolIdx}`;
          const stepIdx = newSteps.findIndex(s => s.id === stepId);
          
          if (stepIdx > -1) {
            const currentContent = newSteps[stepIdx].content;
            const resultStr = msg.content;
            newSteps[stepIdx] = { 
              ...newSteps[stepIdx], 
              content: { ...currentContent, result: resultStr, status: msg.metadata?.status || 'success' } 
            };
            
            // Special handling for weather to show a card
            if (currentContent.name === 'get_weather' || currentContent.name === 'weather') {
                try {
                    // Try to extract JSON-like data from the string representation
                    // The backend sends str(dict), which is not valid JSON (uses single quotes)
                    // Simple regex or heuristic to get data
                    const tempMatch = resultStr.match(/'temperature':\s*'([^']+)'/);
                    const condMatch = resultStr.match(/'condition':\s*'([^']+)'/);
                    const locMatch = resultStr.match(/'location':\s*'([^']+)'/);
                    
                    if (tempMatch && condMatch && locMatch) {
                        newSteps.push({
                            id: `${msgId}_weather_${toolIdx}`,
                            type: 'weather',
                            content: {
                                city: locMatch[1],
                                temp: tempMatch[1],
                                condition: condMatch[1],
                                wind: '4km/h' // Mocked as it's not in current tool output
                            }
                        });
                    }
                } catch (e) {
                    console.error("Failed to parse weather data:", e);
                }
            }
          }
        }

        return [...prev.slice(0, -1), { ...lastMsg, steps: newSteps }];
      });
    } else if (msg.type === 'signal') {
        if (msg.content === 'ready') {
            setConnectionStatus('connected');
        }
    }
  }, []);

  useEffect(() => {
    const client = new VoiceAssistantClient(sessionId);
    clientRef.current = client;

    client.connect(handleMessage, () => {
      setConnectionStatus('connected');
    });

    const audioProcessor = new AudioProcessor((data) => {
      client.sendAudio(data);
    });
    audioProcessorRef.current = audioProcessor;
    
    audioProcessor.start().catch(err => {
        console.error("Failed to start audio processor:", err);
        setConnectionStatus('error');
    });

    return () => {
      client.disconnect();
      audioProcessor.stop();
    };
  }, [sessionId, handleMessage]);

  const sendMessage = useCallback((text: string) => {
    if (clientRef.current) {
      clientRef.current.sendMessage('input', text);
      // Optimistically add user message
      setMessages(prev => [...prev, { 
        role: 'user', 
        steps: [{ id: Date.now().toString(), type: 'text', content: text }] 
      }]);
    }
  }, []);

  const toggleMode = useCallback(() => {
    setMode(prev => prev === 'voice' ? 'chat' : 'voice');
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    messages,
    mode,
    isAssistantTyping,
    connectionStatus,
    sendMessage,
    toggleMode,
    clearMessages
  };
};
