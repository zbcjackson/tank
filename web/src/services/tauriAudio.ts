/**
 * Bridge between the web frontend and Rust native audio (AEC + ANC).
 * Only used when running inside Tauri — feature-detected via `__TAURI__`.
 */

type UnlistenFn = () => void;

export class TauriAudioBridge {
  private unlisten: UnlistenFn | null = null;
  private started = false;
  private onError?: (error: string) => void;

  constructor(onError?: (error: string) => void) {
    this.onError = onError;
  }

  /**
   * Start native audio capture. Invokes the Rust `start_audio_capture` command
   * and listens for `audio-capture` events containing Int16 PCM at 16kHz.
   */
  async startCapture(onAudioChunk: (samples: Int16Array) => void): Promise<void> {
    if (this.started) return;

    const { invoke } = await import('@tauri-apps/api/core');
    const { listen } = await import('@tauri-apps/api/event');

    // Listen for captured audio events from Rust
    this.unlisten = await listen<number[]>('audio-capture', (event) => {
      const bytes = new Uint8Array(event.payload);
      const samples = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
      onAudioChunk(samples);
    });

    // Listen for audio errors from Rust
    const unlistenError = await listen<string>('audio-error', (event) => {
      console.error('[TauriAudioBridge] Audio error from native:', event.payload);
      this.onError?.(event.payload);
    });

    // Store both unlisteners
    const originalUnlisten = this.unlisten;
    this.unlisten = () => {
      originalUnlisten();
      unlistenError();
    };

    await invoke('start_audio_capture');
    this.started = true;
  }

  /**
   * Send TTS audio to Rust for playback through VoiceProcessingIO (AEC reference).
   * Expects raw Int16 PCM ArrayBuffer at 24kHz.
   */
  async playAudio(data: ArrayBuffer): Promise<void> {
    const { invoke } = await import('@tauri-apps/api/core');
    const bytes = Array.from(new Uint8Array(data));
    await invoke('play_audio', { samples: bytes });
  }

  /**
   * Stop current playback (for interruption). Drops and recreates the
   * PlaybackStreamHandle on the Rust side.
   */
  async stopPlayback(): Promise<void> {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('stop_playback');
  }

  /**
   * Stop all native audio capture and playback.
   */
  async stopCapture(): Promise<void> {
    if (!this.started) return;

    this.unlisten?.();
    this.unlisten = null;

    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('stop_audio_capture');
    this.started = false;
  }
}
