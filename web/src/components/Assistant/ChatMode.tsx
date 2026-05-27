import React, { useRef, useEffect, useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { ArrowUp, Square, Paperclip, Upload, Volume2, VolumeX } from 'lucide-react';
import { MessageStep } from './MessageStep';
import { EnrollmentBanner } from './EnrollmentBanner';
import { UserSelector } from './UserSelector';
import { AttachmentChips } from './AttachmentChips';
import { PttButton } from './PttButton';
import type { Step } from '../../types/message';
import { ActivityIndicator } from './ActivityIndicator';
import type { AssistantStatus } from '../../hooks/useAssistant';
import { useUpload } from '../../hooks/useUpload';

const CHAT_BG_STYLE = { background: '#0a0a0a' };
const EMPTY_STATE_STYLE = {
  background: 'radial-gradient(circle, rgba(212,160,84,0.08) 0%, transparent 70%)',
};
const TEXTAREA_MAX_HEIGHT = { maxHeight: 120 };

/** Map assistantStatus → header badge label */
const STATUS_BADGE: Partial<Record<AssistantStatus, string>> = {
  speaking: 'SPEAKING',
  thinking: 'THINKING',
  responding: 'TYPING',
  tool_calling: 'WORKING',
  interrupted: 'INTERRUPTED',
  error: 'ERROR',
};

interface ChatModeProps {
  messages: Step[];
  assistantStatus: AssistantStatus;
  onSendMessage: (
    text: string,
    attachments?: Array<{ media_uri: string; mime_type: string }>,
  ) => void;
  onStopSpeaking: () => void;
  onApprovalRespond: (approvalId: string, approved: boolean) => void;
  pauseAudioCapture: () => void;
  resumeAudioCapture: () => void;
  selectedUserId: string | null;
  onSelectUser: (userId: string | null) => void;
  sessionId: string;
  chatSpeakEnabled: boolean;
  onChatSpeakEnabledChange: (enabled: boolean) => void;
  isPttActive: boolean;
  onPttStart: () => void;
  onPttStop: () => void;
}

export const ChatMode = ({
  messages,
  assistantStatus,
  onSendMessage,
  onStopSpeaking,
  onApprovalRespond,
  pauseAudioCapture,
  resumeAudioCapture,
  selectedUserId,
  onSelectUser,
  sessionId,
  chatSpeakEnabled,
  onChatSpeakEnabledChange,
  isPttActive,
  onPttStart,
  onPttStop,
}: ChatModeProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [enrollmentKey, setEnrollmentKey] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const { attachments, upload, remove, clear } = useUpload(sessionId);

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
  }, [messages, assistantStatus]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputRef.current) return;
    const text = inputRef.current.value.trim();
    // Don't send while uploads are still in flight — would arrive at
    // the LLM without the media attached.
    const hasUploading = attachments.some((a) => a.status === 'uploading');
    if (hasUploading) return;
    // Collect only successfully-uploaded attachments; errored ones stay
    // visible but are excluded from the send.
    const uploaded = attachments.filter((a) => a.status === 'uploaded');
    const media = uploaded.map((a) => ({
      media_uri: a.mediaUri!,
      mime_type: a.mimeType!,
    }));
    // Require either text OR at least one uploaded attachment.
    if (!text && media.length === 0) return;
    onSendMessage(text, media.length > 0 ? media : undefined);
    inputRef.current.value = '';
    inputRef.current.style.height = 'auto';
    clear();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
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

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    // Clipboard can carry a file (screenshot) alongside text. We only
    // intercept when there's a file; otherwise fall through to the
    // default text-paste behavior.
    const files = Array.from(e.clipboardData.files);
    if (files.length === 0) return;
    e.preventDefault();
    upload(files);
  };

  const handleDragOver = (e: React.DragEvent) => {
    // Only treat as a file drag when the dataTransfer actually advertises
    // files — dragging text selection within the textarea shouldn't flip
    // the overlay on.
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    // Only react when leaving the form container, not when the pointer
    // moves between child elements (dragleave bubbles from children).
    if (e.currentTarget === e.target) setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) upload(files);
  };

  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) upload(files);
    // Reset so selecting the same file twice still triggers onChange.
    e.target.value = '';
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
          {STATUS_BADGE[assistantStatus] && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/8 border border-amber-500/15"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              <span className="text-[10px] font-mono text-amber-500/80">
                {STATUS_BADGE[assistantStatus]}
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
            const isLastMessage = i === messages.length - 1;
            const showIndicator = isLastMessage && assistantStatus !== 'idle';

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
                  <div
                    className={`relative ${msg.role === 'user' ? 'max-w-[85%]' : 'w-full max-w-[95%]'}`}
                  >
                    {showIndicator && (
                      <div
                        data-testid="activity-indicator"
                        className="absolute right-full bottom-0 mr-2 pointer-events-none"
                      >
                        <ActivityIndicator status={assistantStatus} />
                      </div>
                    )}
                    <MessageStep
                      step={{ id: msg.id, type: msg.type, content: msg.content }}
                      role={msg.role}
                      onApprovalRespond={onApprovalRespond}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Input area */}
      <div className="px-6 pb-6 pt-3">
        <form
          onSubmit={handleSubmit}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className="max-w-3xl mx-auto relative"
        >
          {/* Drag-drop overlay — covers the form when files are dragged over */}
          {isDragging && (
            <div
              className="absolute inset-0 z-20 rounded-2xl border-2 border-dashed border-amber-500/50 bg-amber-500/8 flex items-center justify-center pointer-events-none"
              data-testid="drop-overlay"
            >
              <div className="flex items-center gap-2 text-amber-400 text-sm font-mono">
                <Upload size={16} />
                <span>DROP TO ATTACH</span>
              </div>
            </div>
          )}

          <AttachmentChips attachments={attachments} onRemove={remove} />

          <div className="relative rounded-2xl bg-surface-raised border border-border-subtle focus-within:border-amber-500/20 transition-all duration-200">
            <div className="absolute left-2 top-1/2 -translate-y-1/2 z-10 flex items-center gap-1">
              <UserSelector selectedUserId={selectedUserId} onSelectUser={onSelectUser} />
              {/* Attach-file button. Hidden file input triggered via ref. */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                aria-label="Attach file"
                data-testid="attach-button"
                className="w-7 h-7 rounded-lg flex items-center justify-center text-text-muted hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
              >
                <Paperclip size={14} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleFilePick}
                data-testid="file-input"
              />
            </div>
            <textarea
              ref={inputRef}
              rows={1}
              placeholder="输入消息..."
              data-testid="chat-input"
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              onPaste={handlePaste}
              className="w-full bg-transparent pl-[150px] pr-[160px] pt-[18px] pb-[13px] text-[14px] text-text-primary placeholder:text-text-muted resize-none focus:outline-none leading-relaxed"
              style={TEXTAREA_MAX_HEIGHT}
            />
            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => onChatSpeakEnabledChange(!chatSpeakEnabled)}
                aria-label={chatSpeakEnabled ? '关闭语音回复' : '开启语音回复'}
                data-testid="chat-voice-reply-toggle"
                className={`w-9 h-9 rounded-xl flex items-center justify-center border transition-all ${chatSpeakEnabled ? 'text-amber-400 bg-amber-500/10 border-amber-500/15' : 'text-text-muted hover:text-amber-400 hover:bg-amber-500/10 border-border-subtle hover:border-amber-500/15'}`}
              >
                {chatSpeakEnabled ? <Volume2 size={15} /> : <VolumeX size={15} />}
              </button>
              <PttButton
                isRecording={isPttActive}
                onStart={onPttStart}
                onStop={onPttStop}
                size="sm"
              />
              {assistantStatus !== 'idle' ? (
                <button
                  type="button"
                  data-testid="stop-button"
                  onClick={onStopSpeaking}
                  className="w-9 h-9 rounded-xl flex items-center justify-center bg-red-500/10 text-red-400 border border-red-500/15 hover:bg-red-500/15 hover:border-red-500/25 transition-all duration-200"
                >
                  <Square size={14} fill="currentColor" />
                </button>
              ) : (
                <button
                  type="submit"
                  data-testid="send-button"
                  className="w-9 h-9 rounded-xl flex items-center justify-center bg-amber-500/10 text-amber-400 border border-amber-500/15 hover:bg-amber-500/15 hover:border-amber-500/25 transition-all duration-200"
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
