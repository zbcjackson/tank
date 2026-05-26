/**
 * HTTP client that routes through @tauri-apps/plugin-http under Tauri,
 * falling back to window.fetch in browsers.
 *
 * Under Tauri, requests go through Rust (reqwest) and bypass browser CORS.
 * This is the single place where that routing decision lives.
 */

type FetchFn = typeof window.fetch;

let cached: FetchFn | null = null;

async function load(): Promise<FetchFn> {
  if (cached) return cached;
  if ('__TAURI_INTERNALS__' in window) {
    try {
      const mod = await import('@tauri-apps/plugin-http');
      const pluginFetch = mod.fetch;
      if (typeof pluginFetch !== 'function') {
        console.error('[httpClient] plugin-http exported fetch is not a function:', typeof pluginFetch);
        cached = window.fetch.bind(window);
      } else {
        console.info('[httpClient] Using Tauri plugin-http (CORS bypass)');
        cached = pluginFetch as unknown as FetchFn;
      }
    } catch (err) {
      console.error(
        '[httpClient] Tauri detected but plugin-http import failed. ' +
          'Falling back to window.fetch (CORS errors likely). Error:',
        err,
      );
      cached = window.fetch.bind(window);
    }
  } else {
    console.info('[httpClient] Using window.fetch (browser mode)');
    cached = window.fetch.bind(window);
  }
  return cached;
}

export async function httpFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const f = await load();
  return f(input, init);
}
