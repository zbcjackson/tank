import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, MessageSquare, Plus, Hash } from 'lucide-react';
import { useConversationList, type ConversationInfo } from '../../hooks/useConversationList';
import { useChannelList } from '../../hooks/useChannelList';

interface ConversationListProps {
  open: boolean;
  onClose: () => void;
  onSelectConversation: (conversationId: string) => void;
  onNewConversation: () => void;
  activeConversationId?: string | null;
  onSelectChannel?: (slug: string) => void;
  activeChannelSlug?: string | null;
  unreadCounts?: Record<string, number>;
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

function groupByDate(conversations: ConversationInfo[]): Map<string, ConversationInfo[]> {
  const groups = new Map<string, ConversationInfo[]>();
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);

  for (const c of conversations) {
    const d = new Date(c.start_time);
    let label: string;
    if (d.toDateString() === now.toDateString()) label = 'Today';
    else if (d.toDateString() === yesterday.toDateString()) label = 'Yesterday';
    else label = d.toLocaleDateString([], { month: 'long', day: 'numeric' });

    const list = groups.get(label) || [];
    list.push(c);
    groups.set(label, list);
  }
  return groups;
}

export const ConversationList: React.FC<ConversationListProps> = ({
  open,
  onClose,
  onSelectConversation,
  onNewConversation,
  activeConversationId,
  onSelectChannel,
  activeChannelSlug,
  unreadCounts = {},
}) => {
  const { conversations, loading, refresh } = useConversationList();
  const { channels, refresh: refreshChannels } = useChannelList();

  useEffect(() => {
    if (open) {
      refresh();
      refreshChannels();
    }
  }, [open, refresh, refreshChannels]);

  const grouped = groupByDate(conversations);

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
            data-testid="conversation-list-sidebar"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-800">
              <span className="text-sm font-medium text-neutral-200">Conversations</span>
              <div className="flex gap-1">
                <button
                  onClick={onNewConversation}
                  className="p-1.5 rounded-md hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
                  title="New conversation"
                  data-testid="new-conversation-button"
                >
                  <Plus size={16} />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-md hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
                  data-testid="close-conversation-list"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto">
              {/* Channels section */}
              {channels.length > 0 && onSelectChannel && (
                <div>
                  <div className="px-4 pt-3 pb-1 text-xs font-medium text-neutral-500 uppercase tracking-wider">
                    Channels
                  </div>
                  {channels.map((ch) => {
                    const unread = unreadCounts[ch.slug] || ch.unread_count || 0;
                    return (
                      <button
                        key={ch.slug}
                        onClick={() => onSelectChannel(ch.slug)}
                        data-testid="channel-item"
                        className={`w-full text-left px-4 py-2.5 hover:bg-neutral-800/60 transition-colors ${
                          activeChannelSlug === ch.slug ? 'bg-neutral-800/80' : ''
                        }`}
                      >
                        <div className="flex items-start gap-2.5">
                          <Hash size={14} className="text-blue-400 mt-0.5 shrink-0" />
                          <div className="min-w-0 flex-1">
                            <div className={`text-sm truncate ${unread > 0 ? 'text-white font-medium' : 'text-neutral-200'}`}>
                              {ch.name}
                            </div>
                            <div className="text-xs text-neutral-500 mt-0.5">
                              {ch.message_count} messages
                            </div>
                          </div>
                          {unread > 0 && (
                            <span className="shrink-0 mt-0.5 min-w-[20px] h-5 px-1.5 flex items-center justify-center rounded-full bg-blue-500 text-white text-xs font-medium">
                              {unread}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                  <div className="border-b border-neutral-800 my-1" />
                </div>
              )}

              {/* History section */}
              <div className="px-4 pt-3 pb-1 text-xs font-medium text-neutral-500 uppercase tracking-wider">
                History
              </div>
              {loading && conversations.length === 0 && (
                <div className="px-4 py-8 text-center text-neutral-500 text-sm">Loading…</div>
              )}
              {!loading && conversations.length === 0 && (
                <div className="px-4 py-8 text-center text-neutral-500 text-sm">No conversations yet</div>
              )}
              {Array.from(grouped.entries()).map(([label, items]) => (
                <div key={label}>
                  <div className="px-4 pt-3 pb-1 text-xs font-medium text-neutral-500 uppercase tracking-wider">
                    {label}
                  </div>
                  {items.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => onSelectConversation(c.id)}
                      data-testid="conversation-item"
                      className={`w-full text-left px-4 py-2.5 hover:bg-neutral-800/60 transition-colors ${
                        activeConversationId === c.id ? 'bg-neutral-800/80' : ''
                      }`}
                    >
                      <div className="flex items-start gap-2.5">
                        <MessageSquare size={14} className="text-neutral-500 mt-0.5 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-neutral-200 truncate">
                            {c.preview || 'Empty conversation'}
                          </div>
                          <div className="text-xs text-neutral-500 mt-0.5">
                            {c.message_count} messages · {formatTime(c.start_time)}
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
