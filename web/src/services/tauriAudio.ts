/**
 * Tauri implementation of PlatformAudioAdapter.
 *
 * Routes audio capture and playback through Rust native code (AEC + ANC
 * via CoreAudio VoiceProcessingIO). Only loaded when `__TAURI__` is detected
 * by the factory in platformAudio.ts.
 */

import type { PlatformAudioAdapter, CaptureHandle, PlayChunkResult } from './platformAudio';

type UnlistenFn = () => void;

export class TauriAudioAdapter implements PlatformAudioAdapter {
  private unlisten: UnlistenFn | null = null;
  private started = false;
  private onError?: (error: string) => void;
  private onRmsChange: ((rms: number) => void) | null = null;

  constructor(onError?: (error: string) => void) {
    this.onError = onError;
  }

  async startCapture(onAudio: (samples: Int16Array) => void): Promise<CaptureHandle> {
    if (this.started) return { stop: () => {} };

    const { invoke } = await import('@tauri-apps/api/core');
    const { listen } = await import('@tauri-apps/api/event');

    // Listen for captured audio events from Rust
    this.unlisten = await listen<number[]>('audio-capture', (event) => {
      const bytes = new Uint8Array(event.payload);
      const samples = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
      onAudio(samples);
    });

    // Listen for audio errors from Rust
    const unlistenError = await listen<string>('audio-error', (event) => {
      console.error('[TauriAudioAdapter] Audio error from native:', event.payload);
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

    return { stop: () => this.stopCapture() };
  }

  async playChunk(data: ArrayBuffer): Promise<PlayChunkResult> {
    const { invoke } = await import('@tauri-apps/api/core');
    const bytes = Array.from(new Uint8Array(data));
    await invoke('play_audio', { samples: bytes });

    // Compute RMS for waveform visualization
    if (this.onRmsChange) {
      const int16 = new Int16Array(data);
      let sumSq = 0;
      for (let i = 0; i < int16.length; i++) {
        const s = int16[i] / 32768;
        sumSq += s * s;
      }
      this.onRmsChange(Math.sqrt(sumSq / int16.length));
    }

    // Estimate duration from chunk size (Int16 at 24 kHz)
    const durationMs = (data.byteLength / 2 / 24000) * 1000;
    return { durationMs };
  }

  async stopPlayback(): Promise<void> {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('stop_playback');
    this.onRmsChange?.(0);
  }

  getAnalyserNode(): AnalyserNode | null {
    return null;
  }

  setOnRmsChange(cb: ((rms: number) => void) | null): void {
    this.onRmsChange = cb;
  }

  async dispose(): Promise<void> {
    await this.stopCapture();
  }

  private async stopCapture(): Promise<void> {
    if (!this.started) return;

    this.unlisten?.();
    this.unlisten = null;

    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('stop_audio_capture');
    this.started = false;
  }
}
