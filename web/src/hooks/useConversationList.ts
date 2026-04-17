/**
 * Hook for fetching and managing the conversation list from the backend.
 */
import { useState, useCallback } from 'react';

export interface ConversationInfo {
  id: string;
  start_time: string;
  message_count: number;
  preview: string;
}

const API_BASE = import.meta.env.VITE_API_URL || '';

export function useConversationList() {
  const [conversations, setConversations] = useState<ConversationInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/conversations`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ConversationInfo[] = await res.json();
      setConversations(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  }, []);

  return { conversations, loading, error, refresh };
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
  name?: string;
  msg_id: string;
}

export async function fetchConversationMessages(conversationId: string): Promise<HistoryMessage[]> {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.messages;
}
