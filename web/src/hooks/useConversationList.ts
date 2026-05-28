/**
 * Hook for fetching and managing the conversation list from the backend.
 */
import { useState, useCallback } from 'react';

import * as api from '../services/api';

// Re-export types for backward compatibility
export type { ConversationInfo, HistoryMessage } from '../services/api';

export interface ConversationMetadataPatch {
  title?: string | null;
}

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

  const applyMetadataUpdate = useCallback(
    (conversationId: string, patch: ConversationMetadataPatch) => {
      setConversations((prev) => {
        let changed = false;
        const next = prev.map((c) => {
          if (c.id !== conversationId) return c;
          changed = true;
          return { ...c, ...patch };
        });
        return changed ? next : prev;
      });
    },
    [],
  );

  return { conversations, loading, error, refresh, applyMetadataUpdate };
}

export async function fetchConversationMessages(
  conversationId: string,
): Promise<api.HistoryMessage[]> {
  return api.conversations.getMessages(conversationId);
}
