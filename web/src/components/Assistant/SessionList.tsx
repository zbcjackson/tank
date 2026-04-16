import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, MessageSquare, Plus } from 'lucide-react';
import { useSessionList, type SessionInfo } from '../../hooks/useSessionList';

interface SessionListProps {
  open: boolean;
  onClose: () => void;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  activeSessionId?: string | null;
}

function formatTime(isoString: string): string {
  const d = new Date(isoString);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = d.toDateString() === yesterday.toDateString();

  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (isToday) return time;
  if (isYesterday) return `Yesterday ${time}`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ` ${time}`;
}

function groupByDate(sessions: SessionInfo[]): Map<string, SessionInfo[]> {
  const groups = new Map<string, SessionInfo[]>();
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);

  for (const s of sessions) {
    const d = new Date(s.start_time);
    let label: string;
    if (d.toDateString() === now.toDateString()) label = 'Today';
    else if (d.toDateString() === yesterday.toDateString()) label = 'Yesterday';
    else label = d.toLocaleDateString([], { month: 'long', day: 'numeric' });

    const list = groups.get(label) || [];
    list.push(s);
    groups.set(label, list);
  }
  return groups;
}

export const SessionList: React.FC<SessionListProps> = ({
  open,
  onClose,
  onSelectSession,
  onNewSession,
  activeSessionId,
}) => {
  const { sessions, loading, refresh } = useSessionList();

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  const grouped = groupByDate(sessions);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 z-40"
            onClick={onClose}
          />
          {/* Sidebar */}
          <motion.div
            initial={{ x: 320 }}
            animate={{ x: 0 }}
            exit={{ x: 320 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 w-80 bg-neutral-900 border-l border-neutral-800 z-50 flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-800">
              <span className="text-sm font-medium text-neutral-200">Sessions</span>
              <div className="flex gap-1">
                <button
                  onClick={onNewSession}
                  className="p-1.5 rounded-md hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
                  title="New session"
                >
                  <Plus size={16} />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-md hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Session list */}
            <div className="flex-1 overflow-y-auto">
              {loading && sessions.length === 0 && (
                <div className="px-4 py-8 text-center text-neutral-500 text-sm">Loading…</div>
              )}
              {!loading && sessions.length === 0 && (
                <div className="px-4 py-8 text-center text-neutral-500 text-sm">No sessions yet</div>
              )}
              {Array.from(grouped.entries()).map(([label, items]) => (
                <div key={label}>
                  <div className="px-4 pt-3 pb-1 text-xs font-medium text-neutral-500 uppercase tracking-wider">
                    {label}
                  </div>
                  {items.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => onSelectSession(s.id)}
                      className={`w-full text-left px-4 py-2.5 hover:bg-neutral-800/60 transition-colors ${
                        activeSessionId === s.id ? 'bg-neutral-800/80' : ''
                      }`}
                    >
                      <div className="flex items-start gap-2.5">
                        <MessageSquare size={14} className="text-neutral-500 mt-0.5 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-neutral-200 truncate">
                            {s.preview || 'Empty session'}
                          </div>
                          <div className="text-xs text-neutral-500 mt-0.5">
                            {s.message_count} messages · {formatTime(s.start_time)}
                          </div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
