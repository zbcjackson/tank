import React, { useRef, useEffect, useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { ArrowUp, Square } from 'lucide-react';
import { MessageStep } from './MessageStep';
import { EnrollmentBanner } from './EnrollmentBanner';
import type { Step } from '../../types/message';

const DOT_ANIMATE = { opacity: [0.2, 0.8, 0.2] };
const DOT_TRANSITION_0 = { repeat: Infinity, duration: 1.2 };
const DOT_TRANSITION_1 = { repeat: Infinity, duration: 1.2, delay: 0.15 };
const DOT_TRANSITION_2 = { repeat: Infinity, duration: 1.2, delay: 0.3 };

const CHAT_BG_STYLE = { background: '#0a0a0a' };
const EMPTY_STATE_STYLE = {
  background: 'radial-gradient(circle, rgba(212,160,84,0.08) 0%, transparent 70%)',
};
const TEXTAREA_MAX_HEIGHT = { maxHeight: 120 };

interface ChatModeProps {
  messages: Step[];
  isAssistantTyping: boolean;
  isSpeaking: boolean;
  onSendMessage: (text: string) => void;
  onStopSpeaking: () => void;
  pauseAudioCapture: () => void;
  resumeAudioCapture: () => void;
}

export const ChatMode = ({
  messages,
  isAssistantTyping,
  isSpeaking,
  onSendMessage,
  onStopSpeaking,
  pauseAudioCapture,
  resumeAudioCapture,
}: ChatModeProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [enrollmentKey, setEnrollmentKey] = useState(0);

  const lastUserSpeaker = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') return messages[i].speaker;
    }
    return undefined;
  }, [messages]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages, isAssistantTyping]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputRef.current && inputRef.current.value.trim()) {
      onSendMessage(inputRef.current.value);
      inputRef.current.value = '';
      inputRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInput = () => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 120) + 'px';
    }
  };

  return (
    <motion.div
      key="chat"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="grain h-full flex flex-col"
      style={CHAT_BG_STYLE}
    >
      {/* Header */}
      <div className="px-6 pt-6 pb-4 flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-text-primary">Tank</h2>
          <p className="text-[11px] font-mono tracking-wider text-text-muted mt-0.5">
            VOICE ASSISTANT
          </p>
        </div>
        <div className="flex items-center gap-2">
          {(isAssistantTyping || isSpeaking) && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/8 border border-amber-500/15"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              <span className="text-[10px] font-mono text-amber-500/80">
                {isSpeaking ? 'SPEAKING' : 'THINKING'}
              </span>
            </motion.div>
          )}
        </div>
      </div>

      <EnrollmentBanner
        key={enrollmentKey}
        speaker={lastUserSpeaker}
        onEnrollComplete={() => setEnrollmentKey((k) => k + 1)}
        pauseAudioCapture={pauseAudioCapture}
        resumeAudioCapture={resumeAudioCapture}
      />

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 pb-4 scrollbar-thin">
        {messages.length === 0 && (
          <div
            data-testid="empty-state"
            className="h-full flex flex-col items-center justify-center gap-4"
          >
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center"
              style={EMPTY_STATE_STYLE}
            >
              <div className="w-2 h-2 rounded-full bg-amber-500/30" />
            </div>
            <p className="text-sm text-text-muted">开始对话</p>
          </div>
        )}

        <div className="max-w-3xl mx-auto space-y-1">
          {messages.map((msg, i) => {
            const prevMsg = i > 0 ? messages[i - 1] : null;
            const isFirstInRoleGroup = !prevMsg || prevMsg.role !== msg.role;

            return (
              <div
                key={msg.id}
                data-testid={msg.role === 'user' ? 'user-message' : 'assistant-message'}
              >
                {isFirstInRoleGroup && (
                  <div
                    className={`flex items-center gap-2 mt-6 mb-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase">
                      {msg.role === 'user'
                        ? msg.speaker && msg.speaker !== 'Unknown'
                          ? msg.speaker
                          : 'You'
                        : 'Tank'}
                    </span>
                  </div>
                )}

                <div className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`${msg.role === 'user' ? 'max-w-[85%]' : 'w-full max-w-[95%]'}`}>
                    <MessageStep
                      step={{ id: msg.id, type: msg.type, content: msg.content }}
                      role={msg.role}
                    />
                  </div>
                </div>
              </div>
            );
          })}

          {/* Typing indicator */}
          {isAssistantTyping &&
            messages.length > 0 &&
            !messages.some((m) => m.role === 'assistant' && m.type === 'thinking') && (
              <div data-testid="typing-indicator" className="flex justify-start mt-4">
                <div className="flex items-center gap-1.5 px-4 py-2.5 rounded-2xl bg-surface-raised">
                  <motion.span
                    animate={DOT_ANIMATE}
                    transition={DOT_TRANSITION_0}
                    className="w-1 h-1 bg-amber-500 rounded-full"
                  />
                  <motion.span
                    animate={DOT_ANIMATE}
                    transition={DOT_TRANSITION_1}
                    className="w-1 h-1 bg-amber-500 rounded-full"
                  />
                  <motion.span
                    animate={DOT_ANIMATE}
                    transition={DOT_TRANSITION_2}
                    className="w-1 h-1 bg-amber-500 rounded-full"
                  />
                </div>
              </div>
            )}
        </div>
      </div>

      {/* Input area */}
      <div className="px-6 pb-6 pt-3">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto relative">
          <div className="relative rounded-2xl bg-surface-raised border border-border-subtle focus-within:border-amber-500/20 transition-colors">
            <textarea
              ref={inputRef}
              rows={1}
              placeholder="输入消息..."
              data-testid="chat-input"
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              className="w-full bg-transparent px-5 py-3.5 pr-24 text-[14px] text-text-primary placeholder:text-text-muted resize-none focus:outline-none leading-relaxed"
              style={TEXTAREA_MAX_HEIGHT}
            />
            <div className="absolute right-2 bottom-2 flex items-center gap-1.5">
              {isAssistantTyping || isSpeaking ? (
                <button
                  type="button"
                  data-testid="stop-button"
                  onClick={onStopSpeaking}
                  className="w-9 h-9 rounded-xl flex items-center justify-center bg-red-500/15 text-red-400 border border-red-500/20 hover:bg-red-500/25 transition-colors"
                >
                  <Square size={14} fill="currentColor" />
                </button>
              ) : (
                <button
                  type="submit"
                  data-testid="send-button"
                  className="w-9 h-9 rounded-xl flex items-center justify-center bg-amber-500/15 text-amber-400 border border-amber-500/20 hover:bg-amber-500/25 transition-colors"
                >
                  <ArrowUp size={16} strokeWidth={2.5} />
                </button>
              )}
            </div>
          </div>
        </form>
      </div>
    </motion.div>
  );
};
