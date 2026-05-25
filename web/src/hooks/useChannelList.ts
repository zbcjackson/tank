import { useState, useCallback } from 'react';

import * as api from '../services/api';
import type { ChannelInfo } from '../services/api';

export function useChannelList() {
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.channels.list();
      setChannels(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch channels');
    } finally {
      setLoading(false);
    }
  }, []);

  const createChannel = useCallback(
    async (name: string, slug?: string, description?: string): Promise<ChannelInfo | null> => {
      try {
        const channel = await api.channels.create({ name, slug, description });
        await refresh();
        return channel;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to create channel');
        return null;
      }
    },
    [refresh],
  );

  const deleteChannel = useCallback(
    async (slug: string): Promise<boolean> => {
      try {
        await api.channels.delete(slug);
        await refresh();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to delete channel');
        return false;
      }
    },
    [refresh],
  );

  return { channels, loading, error, refresh, createChannel, deleteChannel };
}
