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
  if ('__TAURI__' in window) {
    const mod = await import('@tauri-apps/plugin-http');
    cached = mod.fetch as unknown as FetchFn;
  } else {
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
