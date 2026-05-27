import { useState, useCallback } from 'react';
import {
  loadServerSettings,
  storeServerSettings,
  clearServerSettings,
  checkServer,
} from '../services/serverSettings';

export interface UseServerSettingsResult {
  /** Full API base URL, e.g. "https://192.168.1.50:8000". Empty = use browser origin (dev proxy). */
  apiBaseUrl: string;
  /** WebSocket base URL, e.g. "wss://192.168.1.50:8000". Empty = use VoiceAssistantClient default. */
  wsBaseUrl: string;
  /** True when a server is configured (saved or via env var). */
  isConfigured: boolean;
  /** True while checking the server connection. */
  isProbing: boolean;
  /** Error from the last check attempt. */
  probeError: string | null;
  /** Check + save a new host:port. Returns true on success. */
  saveSettings: (hostPort: string) => Promise<boolean>;
  /** Clear saved settings (triggers the settings panel again). */
  clearSettings: () => void;
}

function buildUrls(hostPort: string): { apiBaseUrl: string; wsBaseUrl: string } {
  return {
    apiBaseUrl: `https://${hostPort}`,
    wsBaseUrl: `wss://${hostPort}`,
  };
}

/**
 * Build the initial API base URL from saved settings or env var fallback.
 * Returns { apiBaseUrl, wsBaseUrl } — empty strings mean "use browser origin".
 */
function resolveInitialUrls(): {
  apiBaseUrl: string;
  wsBaseUrl: string;
  configured: boolean;
} {
  const saved = loadServerSettings();
  if (saved) {
    return { ...buildUrls(saved.hostPort), configured: true };
  }

  const envUrl = import.meta.env.VITE_BACKEND_URL as string | undefined;
  if (envUrl) {
    const bare = envUrl.replace(/^https?:\/\//, '');
    return { ...buildUrls(bare), configured: true };
  }

  // Default: same-origin. The Vite dev proxy (or nginx in prod) routes
  // /api and /ws to the backend, so relative URLs work on every host.
  return { apiBaseUrl: '', wsBaseUrl: '', configured: true };
}

export function useServerSettings(): UseServerSettingsResult {
  const initial = resolveInitialUrls();

  const [apiBaseUrl, setApiBaseUrl] = useState(initial.apiBaseUrl);
  const [wsBaseUrl, setWsBaseUrl] = useState(initial.wsBaseUrl);
  const [isConfigured, setIsConfigured] = useState(initial.configured);
  const [isProbing, setIsProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);

  const saveSettings = useCallback(async (hostPort: string): Promise<boolean> => {
    const trimmed = hostPort.trim().replace(/\/+$/, '');
    if (!trimmed) {
      setProbeError('Please enter a server address');
      return false;
    }

    const bare = trimmed.replace(/^https?:\/\//, '');
    setIsProbing(true);
    setProbeError(null);

    try {
      await checkServer(bare);

      storeServerSettings({ hostPort: bare });
      const urls = buildUrls(bare);
      setApiBaseUrl(urls.apiBaseUrl);
      setWsBaseUrl(urls.wsBaseUrl);
      setIsConfigured(true);
      return true;
    } catch (err) {
      setProbeError(err instanceof Error ? err.message : 'Connection failed');
      return false;
    } finally {
      setIsProbing(false);
    }
  }, []);

  const clearSettingsFn = useCallback(() => {
    clearServerSettings();
    setApiBaseUrl('');
    setWsBaseUrl('');
    setIsConfigured(false);
    setProbeError(null);
  }, []);

  return {
    apiBaseUrl,
    wsBaseUrl,
    isConfigured,
    isProbing,
    probeError,
    saveSettings,
    clearSettings: clearSettingsFn,
  };
}
