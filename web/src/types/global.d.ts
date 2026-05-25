/**
 * Type declarations for Tauri packages that are only available at runtime.
 * These are externalized in vite.config.ts and lazy-imported under __TAURI__.
 */

declare module '@tauri-apps/api/core' {
  export interface InvokeOptions {
    command: string;
    args?: Record<string, unknown>;
  }

  export function invoke<T = unknown>(command: string, args?: Record<string, unknown>): Promise<T>;
}

declare module '@tauri-apps/api/event' {
  export interface Event<T> {
    once(callback: (payload: T) => void): void;
    listen(callback: (payload: T) => void): void;
  }

  export function listen<T>(event: string, handler: (payload: T) => void): void;
  export function once<T>(event: string, handler: (payload: T) => void): void;
}

declare module '@tauri-apps/plugin-http' {
  import type { RequestInit as WebRequestInit, RequestInfo as WebRequestInfo, Response as WebResponse } from 'node-fetch'; // Using node-fetch types for compatibility

  export type RequestInit = WebRequestInit;
  export type RequestInfo = WebRequestInfo;
  export type Response = WebResponse;

  export function fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
}
