/**
 * Runtime server connection settings. Persisted in localStorage so
 * the Tauri app (and browser) remember the last backend address.
 *
 * All connections go through a reverse proxy (Vite in dev, nginx in prod)
 * which serves HTTPS, so no protocol detection is needed.
 */

export interface ServerSettings {
  hostPort: string; // e.g. "192.168.1.50:8000" or "tank.example.com"
}

const STORAGE_KEY = 'tank.serverSettings';

export function loadServerSettings(): ServerSettings | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.hostPort !== 'string' || !parsed.hostPort) return null;
    return { hostPort: parsed.hostPort };
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
 * Verify the server is reachable over HTTPS. Returns true on success.
 * Throws on failure (timeout, network error, non-OK response).
 */
export async function checkServer(
  hostPort: string,
  timeoutMs = 3000,
): Promise<boolean> {
  const bare = hostPort.replace(/^https?:\/\//, '');

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const { httpFetch } = await import('./httpClient');
    const res = await httpFetch(`https://${bare}/health`, { signal: controller.signal });
    clearTimeout(timer);
    if (res.ok || res.type === 'opaque') return true;
    throw new Error(`Server returned HTTP ${res.status}`);
  } catch (err) {
    clearTimeout(timer);
    throw new Error(
      `Cannot reach server at ${bare}: ${err instanceof Error ? err.message : 'unknown error'}`,
    );
  }
}
