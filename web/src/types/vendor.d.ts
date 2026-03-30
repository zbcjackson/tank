declare module 'openwakeword-wasm-browser';

declare module '@tauri-apps/api/core' {
  export function invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T>;
}

declare module '@tauri-apps/api/event' {
  export type UnlistenFn = () => void;
  export interface Event<T> {
    payload: T;
  }
  export function listen<T>(
    event: string,
    handler: (event: Event<T>) => void,
  ): Promise<UnlistenFn>;
}
