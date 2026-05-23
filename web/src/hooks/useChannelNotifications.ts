import { useState, useCallback, useRef, useEffect } from 'react';

import type { WebsocketMessage } from '../services/websocket';
import { buildApiUrl } from '../services/serverSettings';
import type { Step } from '../types/message';

interface ChannelNotificationMetadata {
  channel_slug: string;
  channel_name: string;
  event_type: string;
  job_name: string;
  run_id: string;
  messages: Array<{ role: string; content: string }>;
  message_preview: string;
}

interface UseChannelNotificationsArgs {
  activeChannelSlug: string | null;
  onActiveChannelMessages: (steps: Step[]) => void;
}

export function useChannelNotifications({
  activeChannelSlug,
  onActiveChannelMessages,
  apiBaseUrl = '',
}: UseChannelNotificationsArgs & { apiBaseUrl?: string }) {
  const [unreadCounts, setUnreadCounts] = useState<Record<string, number>>({});
  const activeSlugRef = useRef(activeChannelSlug);

  useEffect(() => {
    activeSlugRef.current = activeChannelSlug;
  }, [activeChannelSlug]);

  const handleNotification = useCallback(
    (msg: WebsocketMessage) => {
      if (msg.type !== 'channel_notification') return false;

      const meta = msg.metadata as unknown as ChannelNotificationMetadata;
      const slug = meta.channel_slug;
      if (!slug) return true;

      if (activeSlugRef.current === slug) {
        const steps: Step[] = [];
        const ts = Date.now();
        let idx = 0;
        const msgId = `delivery_${ts}`;

        for (const m of meta.messages ?? []) {
          if (m.role === 'assistant') {
            steps.push({
              id: `delivery_${ts}_${idx++}`,
              role: 'assistant',
              type: 'text',
              content: m.content,
              msgId,
              isFinal: true,
            });
          }
        }

        if (steps.length > 0) {
          onActiveChannelMessages(steps);
        }
      } else {
        setUnreadCounts((prev) => ({
          ...prev,
          [slug]: (prev[slug] ?? 0) + 1,
        }));
      }

      return true;
    },
    [onActiveChannelMessages],
  );

  const markRead = useCallback(async (slug: string) => {
    setUnreadCounts((prev) => {
      if (!prev[slug]) return prev;
      const next = { ...prev };
      delete next[slug];
      return next;
    });
    try {
      await fetch(buildApiUrl(`/api/channels/${slug}/read`, apiBaseUrl), { method: 'PUT' });
    } catch {
      // Best-effort — unread badge is already cleared locally
    }
  }, [apiBaseUrl]);

  const initFromChannels = useCallback((channels: Array<{ slug: string; unread_count: number }>) => {
    const counts: Record<string, number> = {};
    for (const ch of channels) {
      if (ch.unread_count > 0) {
        counts[ch.slug] = ch.unread_count;
      }
    }
    setUnreadCounts(counts);
  }, []);

  return { unreadCounts, handleNotification, markRead, initFromChannels };
}
