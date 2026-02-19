import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Mic, MicOff, Send } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { VoiceAssistantClient } from '../services/websocket';
import type { WebsocketMessage } from '../services/websocket';
import { AudioProcessor } from '../services/audio';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  id: string;
}

export const Chat: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [inputText, setInputText] = useState('');
  const [status, setStatus] = useState<'idle' | 'listening' | 'processing' | 'speaking'>('idle');
  
  const clientRef = useRef<VoiceAssistantClient | null>(null);
  const audioRef = useRef<AudioProcessor | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sessionId = Math.random().toString(36).substring(7);
    const client = new VoiceAssistantClient(sessionId);
    clientRef.current = client;

    client.connect((msg) => {
      handleIncomingMessage(msg);
    }, () => {
      setMessages([{ role: 'system', content: 'Connection established. Ready to assist.', id: 'sys-1' }]);
    });

    return () => {
      client.disconnect();
      audioRef.current?.stop();
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleIncomingMessage = (msg: WebsocketMessage) => {
    if (msg.type === 'transcript') {
      updateOrAddMessage('user', msg.content, msg.metadata.msg_id || 'last-user');
      if (msg.is_final) setStatus('processing');
    } else if (msg.type === 'text') {
      updateOrAddMessage('assistant', msg.content, msg.metadata.msg_id || 'last-ai');
      setStatus('speaking');
      if (msg.is_final) setStatus('idle');
    } else if (msg.type === 'signal' && msg.content === 'ready') {
      setStatus('idle');
    }
  };

  const updateOrAddMessage = (role: 'user' | 'assistant', content: string, id: string) => {
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === id);
      if (idx !== -1) {
        const next = [...prev];
        next[idx] = { ...next[idx], content: next[idx].content + content };
        // If it's a full replacement (transcript usually replaces), we could handle that.
        // For now, let's assume content delta for assistant, but full for transcript.
        if (role === 'user') next[idx].content = content; 
        return next;
      }
      return [...prev, { role, content, id }];
    });
  };

  const toggleListening = async () => {
    if (isListening) {
      audioRef.current?.stop();
      setIsListening(false);
      setStatus('idle');
    } else {
      if (!audioRef.current) {
        audioRef.current = new AudioProcessor((data) => {
          clientRef.current?.sendAudio(data);
        });
      }
      await audioRef.current.start();
      setIsListening(true);
      setStatus('listening');
    }
  };

  const handleSendText = () => {
    if (!inputText.trim()) return;
    clientRef.current?.sendMessage('input', inputText);
    setMessages(prev => [...prev, { role: 'user', content: inputText, id: Date.now().toString() }]);
    setInputText('');
  };

  return (
    <div className="flex flex-col h-screen bg-black text-green-500 font-mono p-4 max-w-4xl mx-auto border-x border-green-900/30">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 border-b border-green-900/50 pb-2">
        <div className="flex items-center gap-2">
          <Terminal size={20} className="text-green-400" />
          <h1 className="text-lg font-bold tracking-tighter uppercase">Tank_OS v0.1.0</h1>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className={cn(
            "px-2 py-0.5 rounded border",
            status === 'listening' ? "bg-red-950 border-red-500 text-red-400 animate-pulse" : 
            status === 'processing' ? "bg-blue-950 border-blue-500 text-blue-400" :
            "bg-green-950 border-green-500 text-green-400"
          )}>
            {status.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto mb-4 space-y-4 scrollbar-hide">
        {messages.map((m) => (
          <div key={m.id} className={cn(
            "flex flex-col",
            m.role === 'user' ? "items-end" : "items-start"
          )}>
            <span className="text-[10px] opacity-50 mb-1 uppercase">
              {m.role === 'system' ? 'root@tank' : m.role === 'user' ? 'operator' : 'tank_ai'}
            </span>
            <div className={cn(
              "max-w-[80%] p-3 rounded text-sm",
              m.role === 'user' ? "bg-green-900/20 border border-green-700/30" : 
              m.role === 'system' ? "text-yellow-500 italic opacity-80" :
              "bg-zinc-900/50 border border-zinc-800"
            )}>
              {m.content}
              {status === 'speaking' && m.role === 'assistant' && (
                <span className="inline-block w-2 h-4 ml-1 bg-green-500 animate-pulse align-middle" />
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 bg-zinc-900/50 p-3 rounded-lg border border-zinc-800">
        <button
          onClick={toggleListening}
          className={cn(
            "p-3 rounded-full transition-all",
            isListening ? "bg-red-500 text-white shadow-lg shadow-red-500/20" : "bg-zinc-800 text-zinc-400 hover:text-green-400"
          )}
        >
          {isListening ? <Mic size={20} /> : <MicOff size={20} />}
        </button>
        
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSendText()}
          placeholder="Enter command or speak..."
          className="flex-1 bg-transparent border-none focus:ring-0 text-sm placeholder:text-zinc-700"
        />
        
        <button 
          onClick={handleSendText}
          className="p-2 text-zinc-500 hover:text-green-400"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
};
