/**
 * Platform audio abstraction.
 *
 * Core files (audio.ts, websocket.ts, useAssistant.ts) depend only on this
 * interface — never on Tauri or browser-specific imports directly.
 * Adding a new platform means implementing the interface and registering it
 * in `createPlatformAudio`.
 */

export interface CaptureHandle {
  stop(): void | Promise<void>;
}

export interface PlayChunkResult {
  /** Estimated playback duration in milliseconds. */
  durationMs: number;
}

export interface PlatformAudioAdapter {
  /** Start capture. Returns a handle whose stop() ends capture. */
  startCapture(onAudio: (samples: Int16Array) => void): Promise<CaptureHandle>;

  /** Play Int16 PCM chunk at 24 kHz. Returns estimated duration in ms. */
  playChunk(data: ArrayBuffer): Promise<PlayChunkResult>;

  /** Stop playback immediately (interruption). Rejects further playChunk calls until reset. */
  stopPlayback(): Promise<void>;

  /** Re-enable playback after a stop. Called when a new response begins. */
  resetPlayback(): void;

  /** AnalyserNode for waveform viz, or null if platform uses RMS instead. */
  getAnalyserNode(): AnalyserNode | null;

  /** Register RMS callback for platforms without AnalyserNode. */
  setOnRmsChange(cb: ((rms: number) => void) | null): void;

  /** Release all resources. */
  dispose(): Promise<void>;
}

/**
 * Factory — the single place where `__TAURI__` is checked.
 * Returns the appropriate adapter for the current runtime.
 */
export async function createPlatformAudio(
  onError?: (error: string) => void,
): Promise<PlatformAudioAdapter> {
  if ('__TAURI__' in window) {
    const { TauriAudioAdapter } = await import('./tauriAudio');
    return new TauriAudioAdapter(onError);
  }
  const { BrowserAudioAdapter } = await import('./browserAudio');
  return new BrowserAudioAdapter();
}
