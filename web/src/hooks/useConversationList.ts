/**
 * Hook for fetching and managing the conversation list from the backend.
 */
import { useState, useCallback } from 'react';

import * as api from '../services/api';

// Re-export types for backward compatibility
export type { ConversationInfo, HistoryMessage } from '../services/api';

export function useConversationList() {
  const [conversations, setConversations] = useState<api.ConversationInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.conversations.list();
      setConversations(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  }, []);

  return { conversations, loading, error, refresh };
}

export async function fetchConversationMessages(
  conversationId: string,
): Promise<api.HistoryMessage[]> {
  return api.conversations.getMessages(conversationId);
}
