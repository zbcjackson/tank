/**
 * Hook for fetching and managing the session list from the backend.
 */
import { useState, useCallback } from 'react';

export interface SessionInfo {
  id: string;
  start_time: string;
  message_count: number;
  preview: string;
}

const API_BASE = import.meta.env.VITE_API_URL || '';

export function useSessionList() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: SessionInfo[] = await res.json();
      setSessions(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  return { sessions, loading, error, refresh };
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
  name?: string;
  msg_id: string;
}

export async function fetchSessionMessages(sessionId: string): Promise<HistoryMessage[]> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.messages;
}
