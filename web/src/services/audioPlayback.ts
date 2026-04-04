/**
 * Audio playback coordinator.
 *
 * Owns the PlatformAudioAdapter and speaking-state timer.
 * Decoupled from WebSocket transport — receives raw audio data
 * via play() and manages playback lifecycle independently.
 */

import type { PlatformAudioAdapter } from './platformAudio';

export class AudioPlayback {
  private platformAdapter: PlatformAudioAdapter | null = null;
  private speakingTimer: ReturnType<typeof setTimeout> | null = null;
  private onSpeakingChange?: (isSpeaking: boolean) => void;
  private stopped: boolean = false;

  setPlatformAdapter(adapter: PlatformAudioAdapter) {
    this.platformAdapter = adapter;
  }

  setOnSpeakingChange(cb: (isSpeaking: boolean) => void) {
    this.onSpeakingChange = cb;
  }

  getAnalyserNode(): AnalyserNode | null {
    return this.platformAdapter?.getAnalyserNode() ?? null;
  }

  async play(data: ArrayBuffer): Promise<void> {
    if (!this.platformAdapter || this.stopped) return;

    try {
      const { durationMs } = await this.platformAdapter.playChunk(data);

      if (this.onSpeakingChange) {
        this.onSpeakingChange(true);
        if (this.speakingTimer) clearTimeout(this.speakingTimer);

        this.speakingTimer = setTimeout(() => {
          this.onSpeakingChange?.(false);
          this.speakingTimer = null;
        }, durationMs);
      }
    } catch (e) {
      console.error('Error playing audio chunk:', e);
    }
  }

  stop(): void {
    this.stopped = true;
    this.platformAdapter?.stopPlayback().catch((e) => {
      console.error('Error stopping playback:', e);
    });

    if (this.speakingTimer) {
      clearTimeout(this.speakingTimer);
      this.speakingTimer = null;
    }
    this.onSpeakingChange?.(false);
  }

  reset(): void {
    this.stopped = false;
    this.platformAdapter?.resetPlayback();
  }

  dispose(): void {
    this.stop();
    this.platformAdapter?.dispose();
    this.platformAdapter = null;
  }
}
