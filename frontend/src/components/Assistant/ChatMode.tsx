import React, { useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { User, Cpu, MessageSquare, Mic, Send } from 'lucide-react';
import { MessageStep } from './MessageStep';
import type { Step } from './MessageStep';

export interface ChatMessage {
  role: 'user' | 'assistant';
  steps: Step[];
}

interface ChatModeProps {
  messages: ChatMessage[];
  isAssistantTyping: boolean;
  onSendMessage: (text: string) => void;
}

export const ChatMode = ({ messages, isAssistantTyping, onSendMessage }: ChatModeProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages, isAssistantTyping]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputRef.current && inputRef.current.value.trim()) {
      onSendMessage(inputRef.current.value);
      inputRef.current.value = '';
    }
  };

  return (
    <motion.div 
      key="chat"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="h-full flex flex-col bg-slate-50 dark:bg-zinc-950"
    >
      <div className="p-6 pb-2">
        <h2 className="text-2xl font-black tracking-tight dark:text-white">TANK</h2>
        <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Conversation History</p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-8 scrollbar-hide pt-2">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-4">
            <div className="w-16 h-16 bg-slate-100 dark:bg-zinc-900 rounded-3xl flex items-center justify-center">
                <MessageSquare size={32} className="opacity-20" />
            </div>
            <p className="text-sm font-medium italic">开始对话吧</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              <div className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 shadow-sm ${msg.role === 'user' ? 'bg-primary text-white' : 'bg-white dark:bg-zinc-800 text-zinc-600 border dark:border-zinc-700'}`}>
                {msg.role === 'user' ? <User size={20}/> : <Cpu size={20}/>}
              </div>
              <div className="space-y-3">
                {msg.steps.map((step) => (
                  <MessageStep key={step.id} step={step} role={msg.role} />
                ))}
              </div>
            </div>
          </div>
        ))}
        {isAssistantTyping && (
            <div className="flex justify-start">
                <div className="flex gap-4">
                    <div className="w-10 h-10 rounded-2xl bg-white dark:bg-zinc-900 flex items-center justify-center border dark:border-zinc-800 shadow-sm animate-pulse">
                        <Cpu size={20} className="text-primary" />
                    </div>
                    <div className="flex items-center gap-1 px-2">
                        <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1 }} className="w-1.5 h-1.5 bg-primary rounded-full" />
                        <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1, delay: 0.2 }} className="w-1.5 h-1.5 bg-primary rounded-full" />
                        <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1, delay: 0.4 }} className="w-1.5 h-1.5 bg-primary rounded-full" />
                    </div>
                </div>
            </div>
        )}
      </div>

      <div className="p-6 border-t dark:border-zinc-800 bg-white/50 dark:bg-zinc-900/50 backdrop-blur-md">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto flex gap-3">
          <div className="flex-1 relative group">
            <input 
              ref={inputRef}
              type="text" 
              placeholder="发送消息..."
              className="w-full bg-white dark:bg-zinc-800 border-2 border-slate-200 dark:border-zinc-700 rounded-2xl px-6 py-4 text-[15px] focus:outline-none focus:border-primary transition-all shadow-sm group-hover:border-slate-300 dark:group-hover:border-zinc-600 dark:text-white"
            />
            <div className="absolute right-4 top-1/2 -translate-y-1/2 flex gap-3 text-slate-400">
                <Mic size={22} className="cursor-pointer hover:text-primary transition-colors" />
            </div>
          </div>
          <button 
            type="submit"
            disabled={isAssistantTyping}
            className={`bg-primary text-white px-6 rounded-2xl font-bold flex items-center gap-2 shadow-lg shadow-primary/20 transition-all active:scale-95 ${isAssistantTyping ? 'opacity-50 grayscale cursor-not-allowed' : 'hover:bg-primary/90'}`}
          >
            <Send size={20} />
            <span>发送</span>
          </button>
        </form>
      </div>
    </motion.div>
  );
};
