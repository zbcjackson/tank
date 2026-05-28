import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { X, Loader2, RefreshCw } from 'lucide-react';

import * as api from '../../services/api';

const MODAL_INITIAL = { scale: 0.96, opacity: 0 };
const MODAL_ANIMATE = { scale: 1, opacity: 1 };
const MODAL_TRANSITION = { duration: 0.2 };
const TITLE_MAX = 80;

interface ConversationTitleModalProps {
  conversationId: string;
  initialTitle: string;
  onClose: () => void;
  onSaved: (title: string) => void;
}

export const ConversationTitleModal = ({
  conversationId,
  initialTitle,
  onClose,
  onSaved,
}: ConversationTitleModalProps) => {
  const [title, setTitle] = useState(initialTitle);
  const [busy, setBusy] = useState<'idle' | 'saving' | 'regenerating'>('idle');
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const trimmed = title.trim();
  const canSave = busy === 'idle' && trimmed.length > 0 && trimmed.length <= TITLE_MAX;

  const handleSave = async () => {
    if (!canSave) return;
    setBusy('saving');
    setError(null);
    try {
      const res = await api.conversations.updateTitle(conversationId, trimmed);
      onSaved(res.title ?? trimmed);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
      setBusy('idle');
    }
  };

  const handleRegenerate = async () => {
    if (busy !== 'idle') return;
    setBusy('regenerating');
    setError(null);
    try {
      const res = await api.conversations.regenerateTitle(conversationId);
      if (res.title) {
        setTitle(res.title);
      } else {
        setError('LLM returned an empty title — try again or write one manually.');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Regenerate failed');
    } finally {
      setBusy('idle');
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
      data-testid="conversation-title-modal"
    >
      <motion.div
        initial={MODAL_INITIAL}
        animate={MODAL_ANIMATE}
        transition={MODAL_TRANSITION}
        className="bg-neutral-900 border border-neutral-800 rounded-2xl shadow-2xl shadow-black/60 w-full max-w-md flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-neutral-800">
          <h3 className="text-sm font-semibold text-neutral-200">Rename conversation</h3>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-neutral-800 transition-colors"
            aria-label="Close"
          >
            <X size={18} className="text-neutral-400" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-mono tracking-wider text-neutral-500 uppercase mb-2">
              Title
            </label>
            <input
              ref={inputRef}
              type="text"
              value={title}
              maxLength={TITLE_MAX}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleSave();
                }
              }}
              disabled={busy !== 'idle'}
              placeholder="Untitled conversation"
              className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-blue-500/40 transition-colors disabled:opacity-50"
              data-testid="conversation-title-input"
            />
            <div className="mt-1 flex justify-between text-[11px] text-neutral-500">
              <span>{trimmed.length === 0 ? 'Title cannot be empty' : ' '}</span>
              <span>
                {title.length}/{TITLE_MAX}
              </span>
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-400" data-testid="conversation-title-error">
              {error}
            </p>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={handleRegenerate}
              disabled={busy !== 'idle'}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 disabled:opacity-50 transition-colors text-sm text-neutral-200"
              data-testid="conversation-title-regenerate"
            >
              {busy === 'regenerating' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              Regenerate
            </button>
            <div className="flex-1" />
            <button
              onClick={onClose}
              className="px-3 py-2 rounded-lg hover:bg-neutral-800 transition-colors text-sm text-neutral-300"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!canSave}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/15 text-blue-300 border border-blue-500/30 hover:bg-blue-500/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-sm font-medium"
              data-testid="conversation-title-save"
            >
              {busy === 'saving' && <Loader2 size={14} className="animate-spin" />}
              Save
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
