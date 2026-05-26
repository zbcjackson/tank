/**
 * Runtime server connection settings. Persisted in localStorage so
 * the Tauri app (and browser) remember the last backend address.
 */

export type DetectedProtocol = 'http' | 'https';

export interface ServerSettings {
  hostPort: string; // e.g. "192.168.1.50:8000"
  protocol: DetectedProtocol;
}

const STORAGE_KEY = 'tank.serverSettings';

export function loadServerSettings(): ServerSettings | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.hostPort !== 'string' || !parsed.hostPort) return null;
    const protocol = parsed.protocol === 'https' ? 'https' : 'http';
    return { hostPort: parsed.hostPort, protocol };
  } catch {
    return null;
  }
}

export function storeServerSettings(settings: ServerSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // localStorage unavailable (Safari private mode, quota) — ignore
  }
}

export function clearServerSettings(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

/**
 * Probe the backend to auto-detect whether it speaks HTTPS or plain HTTP.
 * Tries HTTP first (common for intranet/VM), falls back to HTTPS.
 * Throws if neither succeeds within `timeoutMs`.
 */
export async function probeProtocol(
  hostPort: string,
  timeoutMs = 3000,
): Promise<DetectedProtocol> {
  const bare = hostPort.replace(/^https?:\/\//, '');

  // Dynamic import to avoid circular dependency at module load time.
  const { health } = await import('./api');

  // Try HTTP first — most common for intranet/VM setups.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await health.probe(`http://${bare}/health`, controller.signal);
    clearTimeout(timer);
    if (res.ok || res.type === 'opaque') return 'http';
  } catch {
    clearTimeout(timer);
  }

  // Fallback to HTTPS (e.g. production servers behind a reverse proxy)
  const controller2 = new AbortController();
  const timer2 = setTimeout(() => controller2.abort(), timeoutMs);
  try {
    const res = await health.probe(`https://${bare}/health`, controller2.signal);
    clearTimeout(timer2);
    if (res.ok || res.type === 'opaque') return 'https';
  } catch (err) {
    clearTimeout(timer2);
    throw new Error(
      `Cannot reach server at ${bare}: ${err instanceof Error ? err.message : 'unknown error'}`,
    );
  }

  // Should not reach here, but satisfy the type checker
  throw new Error(`Cannot reach server at ${bare}`);
}

/**
 * Derive the WebSocket base URL from an HTTP(S) base URL.
 * "https://host:port" → "wss://host:port"
 * "http://host:port"  → "ws://host:port"
 */
export function deriveWsBaseUrl(apiBaseUrl: string): string {
  return apiBaseUrl.replace(/^http/, 'ws');
}
