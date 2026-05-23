/**
 * Hook for fetching and managing the conversation list from the backend.
 */
import { useState, useCallback } from 'react';
import { buildApiUrl } from '../services/serverSettings';

export interface ConversationInfo {
  id: string;
  start_time: string;
  updated_at: string;
  message_count: number;
  preview: string;
}

export function useConversationList(apiBaseUrl: string = '') {
  const [conversations, setConversations] = useState<ConversationInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(buildApiUrl('/api/conversations', apiBaseUrl));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ConversationInfo[] = await res.json();
      setConversations(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  return { conversations, loading, error, refresh };
}

export interface HistoryMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  name?: string;
  msg_id: string;
  tool_calls?: Array<{
    id: string;
    type: string;
    function: {
      name: string;
      arguments: string;
    };
  }>;
  tool_call_id?: string;
  // Phase 19: discriminator for image-on-resume entries. The backend
  // ``_format_messages`` produces ``kind: "image"`` (not present on
  // any pre-Phase-19 entry) when a tool_follow_up message carried
  // image_url parts. The ``attachments`` field is the rendered shape;
  // ``content`` is empty for image entries.
  kind?: 'image';
  attachments?: Array<{
    kind: 'image';
    url: string;
    mime_type: string;
    caption: string | null;
  }>;
}

export async function fetchConversationMessages(
  conversationId: string,
  apiBaseUrl: string = '',
): Promise<HistoryMessage[]> {
  const res = await fetch(
    buildApiUrl(`/api/conversations/${conversationId}/messages`, apiBaseUrl),
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.messages;
}
