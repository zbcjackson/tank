/**
 * HTTP client that routes through @tauri-apps/plugin-http under Tauri,
 * falling back to window.fetch in browsers.
 *
 * Under Tauri, requests go through Rust (reqwest) and bypass browser CORS.
 * This is the single place where that routing decision lives.
 */

let pluginFetch: ((input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) | null = null;

async function load(): Promise<typeof window.fetch> {
  if (pluginFetch) return pluginFetch;
  if ('__TAURI_INTERNALS__' in window) {
    try {
      const mod = await import('@tauri-apps/plugin-http');
      if (typeof mod.fetch !== 'function') {
        console.error('[httpClient] plugin-http exported fetch is not a function:', typeof mod.fetch);
        return window.fetch.bind(window);
      }
      console.info('[httpClient] Using Tauri plugin-http (CORS bypass)');
      pluginFetch = (mod.fetch as unknown as typeof window.fetch).bind(null);
      return pluginFetch;
    } catch (err) {
      console.error(
        '[httpClient] Tauri detected but plugin-http import failed. ' +
          'Falling back to window.fetch (CORS errors likely). Error:',
        err,
      );
      return window.fetch.bind(window);
    }
  } else {
    console.info('[httpClient] Using window.fetch (browser mode)');
    return window.fetch.bind(window);
  }
}

export async function httpFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const f = await load();
  const isTauri = pluginFetch !== null;

  // Under Tauri, plugin-http accepts a `danger` option to skip TLS validation.
  // This is needed for self-signed certs (e.g. development with IP addresses).
  if (isTauri) {
    const tauriInit = { ...init, danger: { acceptInvalidCerts: true, acceptInvalidHostnames: true } };
    return f(input, tauriInit as RequestInit);
  }
  return f(input, init);
}
