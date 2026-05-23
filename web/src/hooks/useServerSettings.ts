import { useState, useCallback } from 'react';
import {
  loadServerSettings,
  storeServerSettings,
  clearServerSettings,
  probeProtocol,
  deriveWsBaseUrl,
  type DetectedProtocol,
} from '../services/serverSettings';

export interface UseServerSettingsResult {
  /** Full API base URL, e.g. "https://192.168.1.50:8000". Empty = use browser origin (dev proxy). */
  apiBaseUrl: string;
  /** WebSocket base URL, e.g. "wss://192.168.1.50:8000". Empty = use VoiceAssistantClient default. */
  wsBaseUrl: string;
  /** True when a server is configured (saved or via env var). */
  isConfigured: boolean;
  /** True while probing the server for protocol detection. */
  isProbing: boolean;
  /** Error from the last probe attempt. */
  probeError: string | null;
  /** Probe + save a new host:port. Returns true on success. */
  saveSettings: (hostPort: string) => Promise<boolean>;
  /** Clear saved settings (triggers the settings panel again). */
  clearSettings: () => void;
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
    // Defensive: strip any accidental protocol prefix in saved hostPort
    const bare = saved.hostPort.replace(/^https?:\/\//, '');
    const apiBaseUrl = `${saved.protocol}://${bare}`;
    return { apiBaseUrl, wsBaseUrl: deriveWsBaseUrl(apiBaseUrl), configured: true };
  }

  const envUrl = import.meta.env.VITE_BACKEND_URL as string | undefined;
  if (envUrl) {
    const bare = envUrl.replace(/^https?:\/\//, '');
    // Guess protocol from port — 443 or no-port implies https
    const hasHttpsPort = bare.endsWith(':443') || !bare.includes(':');
    const protocol: DetectedProtocol = hasHttpsPort ? 'https' : 'http';
    const apiBaseUrl = `${protocol}://${bare}`;
    return { apiBaseUrl, wsBaseUrl: deriveWsBaseUrl(apiBaseUrl), configured: true };
  }

  // Browser dev mode with Vite proxy — relative URLs work fine
  // Only auto-configure when on localhost (where the Vite proxy handles routing).
  // Non-localhost HTTPS/HTTP (e.g. Tauri or remote access) needs explicit config.
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return { apiBaseUrl: '', wsBaseUrl: '', configured: true };
  }

  return { apiBaseUrl: '', wsBaseUrl: '', configured: false };
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

    setIsProbing(true);
    setProbeError(null);

    try {
      // If user explicitly prefixed with https:// or http://, skip probing
      let protocol: DetectedProtocol;
      let bare: string;
      if (trimmed.startsWith('https://')) {
        protocol = 'https';
        bare = trimmed.replace(/^https:\/\//, '');
      } else if (trimmed.startsWith('http://')) {
        protocol = 'http';
        bare = trimmed.replace(/^http:\/\//, '');
      } else {
        protocol = await probeProtocol(trimmed);
        bare = trimmed;
      }

      const settings = { hostPort: bare, protocol };
      storeServerSettings(settings);

      const newApiBaseUrl = `${protocol}://${trimmed}`;
      setApiBaseUrl(newApiBaseUrl);
      setWsBaseUrl(deriveWsBaseUrl(newApiBaseUrl));
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
