import { useState, useCallback } from 'react';

import type { ChannelInfo } from '../types/channel';
import { buildApiUrl } from '../services/serverSettings';
import { httpFetch } from '../services/httpClient';

export function useChannelList(apiBaseUrl: string = '') {
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await httpFetch(buildApiUrl('/api/channels', apiBaseUrl));
      if (!resp.ok) throw new Error(`Failed to fetch channels: ${resp.status}`);
      const data: ChannelInfo[] = await resp.json();
      setChannels(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch channels');
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  const createChannel = useCallback(
    async (name: string, slug?: string, description?: string): Promise<ChannelInfo | null> => {
      try {
        const resp = await httpFetch(buildApiUrl('/api/channels', apiBaseUrl), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, slug: slug || undefined, description: description || '' }),
        });
        if (!resp.ok) throw new Error(`Failed to create channel: ${resp.status}`);
        const channel: ChannelInfo = await resp.json();
        await refresh();
        return channel;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to create channel');
        return null;
      }
    },
    [refresh, apiBaseUrl],
  );

  const deleteChannel = useCallback(
    async (slug: string): Promise<boolean> => {
      try {
        const resp = await httpFetch(buildApiUrl(`/api/channels/${slug}`, apiBaseUrl), {
          method: 'DELETE',
        });
        if (!resp.ok) throw new Error(`Failed to delete channel: ${resp.status}`);
        await refresh();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to delete channel');
        return false;
      }
    },
    [refresh, apiBaseUrl],
  );

  return { channels, loading, error, refresh, createChannel, deleteChannel };
}
